"""HTTP download helpers.

Everything here used to shell out to `curl`, and the Skadi path piped curl
into `gzip -d`. Neither is available by default on Windows, and neither
checked its exit status -- a 404 or a 403 silently produced a truncated or
empty file that then looked like a valid cached tile forever.

These are now pure `requests` + stdlib `gzip`, so they work identically on
macOS, Linux and Windows, and they fail loudly.
"""
import gzip
import os
import shutil

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from . import log

# Connect/read timeout, applied per read rather than to the whole transfer.
# Suits small, numerous tile downloads.
TIMEOUT = (10, 60)

# Used for multi-hour, multi-gigabyte transfers such as the OSM planet. The
# transfer is not resumable, so a stalled read discards everything already
# fetched; a short read timeout that suits tiles is actively harmful here.
# `curl -L -o` applied no read timeout at all.
LARGE_FILE_TIMEOUT = (10, 900)

CHUNK_SIZE = 1024 * 1024

# Retry policy. urllib3 supplies the backoff, the retryable status list,
# Retry-After handling and its cap, so there is no retry loop here.
# retry_after_max matters: without it a proxy answering `Retry-After: 3600`
# parks a worker thread for an hour per attempt.
RETRY = Retry(
    total=5,
    connect=5,
    read=5,
    status=5,
    backoff_factor=0.5,
    status_forcelist=(408, 429, 500, 502, 503, 504),
    allowed_methods=frozenset(['GET']),
    respect_retry_after_header=True,
    retry_after_max=60,
    raise_on_status=False,
)

DEFAULT_POOL_SIZE = 16


def make_session(pool_size=DEFAULT_POOL_SIZE):
    """A requests Session with connection pooling and retries.

    Reusing one Session keeps TLS connections alive across a run, which
    matters more than bandwidth here: tile downloads are latency-bound.

    Deliberately opt-in. Routing every caller through this would change the
    behavior of the planet, extract and tilepack downloads, which this
    feature is not about -- and urllib3 logs the full URL on each retry, so
    the api_token those callers put in their query string would reach the
    logs.
    """
    session = requests.Session()
    # pool_connections is the count of cached per-host pools; every tile
    # comes from one S3 host, so pool_maxsize is the knob that matters.
    adapter = HTTPAdapter(max_retries=RETRY, pool_maxsize=pool_size)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def _get(url, compressed=False, timeout=TIMEOUT, session=None):
    """Start a streaming GET, raising on any error status.

    `compressed` mirrors the old curl behavior: when the payload is already
    compressed we ask for it verbatim, otherwise we let the server use
    transfer compression (curl's --compressed).
    """
    headers = {'Accept-Encoding': 'identity'} if compressed else {}
    get = session.get if session is not None else requests.get
    r = get(url, stream=True, timeout=timeout, headers=headers)
    try:
        r.raise_for_status()
    except BaseException:
        # With stream=True the pooled connection is only returned once the
        # body is read to EOF or closed. An unread error body would hold the
        # socket until GC, which exhausts the pool across a tile run.
        r.close()
        raise
    return r


def _write_atomically(response, outpath, transform=None):
    """Stream `response` to `outpath` via a temporary file.

    Writing through a .part file means an interrupted or failed download
    never leaves a partial file behind that tile_exists() would later treat
    as a valid cached tile.
    """
    partpath = '%s.part' % outpath
    try:
        with open(partpath, 'wb') as f:
            body = transform(response) if transform else response.raw
            shutil.copyfileobj(body, f, CHUNK_SIZE)
        os.replace(partpath, outpath)
    except BaseException:
        # Close the response for the same reason _get does on an error
        # status: with stream=True the pooled connection is only released
        # once the body is read or closed, so a mid-body failure would hold
        # the socket until GC.
        try:
            response.close()
        except Exception:
            pass
        try:
            os.unlink(partpath)
        except OSError:
            pass
        raise


def download(url, outpath, session=None, compressed=False):
    """Download `url` to `outpath`.

    `compressed` asks for the payload verbatim, for a body that is already
    compressed and should be stored that way.
    """
    r = _get(url, compressed=compressed, session=session)
    # Always strip transfer encoding: with Accept-Encoding: identity there
    # should be none, and if a server applies one anyway this recovers the
    # stored bytes rather than leaving them doubly encoded.
    r.raw.decode_content = True
    _write_atomically(r, outpath)


def download_gzip(url, outpath, session=None):
    """Download a gzipped `url`, writing the decompressed body to `outpath`.

    Replaces the old `curl ... | gzip -d` pipeline, which left zombie
    processes, could hang when the reader exited early, and checked neither
    process's exit status.
    """
    r = _get(url, compressed=True, session=session)
    _write_atomically(r, outpath, transform=lambda resp: gzip.GzipFile(
        fileobj=resp.raw, mode='rb'))


def download_curl(url, outpath, compressed=False, timeout=TIMEOUT,
                  session=None):
    """Download `url` to `outpath`.

    Kept under its original name because it is part of the module's public
    surface, but it no longer invokes curl.
    """
    if os.path.exists(outpath):
        log.warning("Warning: output path %s already exists." % outpath)

    log.info("Downloading to %s" % outpath)
    # NOTE: the URL is deliberately not logged. It can carry an api_token in
    # its query string, which would otherwise end up in logs.
    r = _get(url, compressed=compressed, timeout=timeout, session=session)
    r.raw.decode_content = True
    _write_atomically(r, outpath)
    log.info("Done")
