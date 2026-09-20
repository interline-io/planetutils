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

from . import log

# Connect/read timeout. Terrain tiles are small, but the planet file is not,
# so this is a per-read timeout rather than a deadline for the whole transfer.
TIMEOUT = (10, 60)

CHUNK_SIZE = 1024 * 1024


def _get(url, compressed=False, timeout=TIMEOUT):
    """Start a streaming GET, raising on any error status.

    `compressed` mirrors the old curl behavior: when the payload is already
    compressed we ask for it verbatim, otherwise we let the server use
    transfer compression (curl's --compressed).
    """
    headers = {'Accept-Encoding': 'identity'} if compressed else {}
    r = requests.get(url, stream=True, timeout=timeout, headers=headers)
    r.raise_for_status()
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
        try:
            os.unlink(partpath)
        except OSError:
            pass
        raise


def download(url, outpath):
    """Download `url` to `outpath`."""
    r = _get(url)
    r.raw.decode_content = True
    _write_atomically(r, outpath)


def download_gzip(url, outpath):
    """Download a gzipped `url`, writing the decompressed body to `outpath`.

    Replaces the old `curl ... | gzip -d` pipeline, which left zombie
    processes, could hang when the reader exited early, and checked neither
    process's exit status.
    """
    r = _get(url, compressed=True)
    _write_atomically(r, outpath, transform=lambda resp: gzip.GzipFile(
        fileobj=resp.raw, mode='rb'))


def download_curl(url, outpath, compressed=False):
    """Download `url` to `outpath`.

    Kept under its original name because it is part of the module's public
    surface, but it no longer invokes curl.
    """
    if os.path.exists(outpath):
        log.warning("Warning: output path %s already exists." % outpath)

    log.info("Downloading to %s" % outpath)
    # NOTE: the URL is deliberately not logged. It can carry an api_token in
    # its query string, which would otherwise end up in logs.
    r = _get(url, compressed=compressed)
    r.raw.decode_content = True
    _write_atomically(r, outpath)
    log.info("Done")
