"""Download OSM extracts in PBF format from Interline, Geofabrik or SliceOSM."""
import hashlib
import json
import os
import re
import time
from importlib import metadata
from urllib.parse import urlencode

import requests

from . import download, log


class ExtractDownloadError(Exception):
    """Raised when an extract cannot be downloaded, with a message for users."""


def user_agent():
    # Geofabrik and SliceOSM run on donated and volunteer infrastructure;
    # identify ourselves so their operators can tell who is calling.
    try:
        version = metadata.version('interline-planetutils')
    except metadata.PackageNotFoundError:
        version = 'dev'
    return 'interline-planetutils/%s (+https://github.com/interline-io/planetutils)' % version


def output_path(outdir, name):
    """<outdir>/<name>.osm.pbf, refusing names that would leave outdir.

    Names come from region ids, GeoJSON properties and .poly name lines, so
    a separator or `..` in one must not pick the directory.
    """
    name = str(name)
    if (not name or name in ('.', '..') or '/' in name or '\\' in name
            or os.path.basename(name) != name):
        raise ExtractDownloadError(
            'cannot name an output file after %r: names must not contain path '
            'separators' % name)
    return os.path.join(outdir, '%s.osm.pbf' % name)


def check_outpath(outpath, overwrite=False):
    outdir = os.path.dirname(outpath) or '.'
    if not os.path.isdir(outdir):
        raise ExtractDownloadError('output directory does not exist: %s' % outdir)
    if os.path.exists(outpath) and not overwrite:
        raise ExtractDownloadError(
            'output file exists: %s\nUse --overwrite to replace it.' % outpath)


class HashingReader:
    """Wraps a file-like body, hashing what is read through it."""

    def __init__(self, raw):
        self.raw = raw
        self.md5 = hashlib.md5()

    def read(self, *args):
        chunk = self.raw.read(*args)
        self.md5.update(chunk)
        return chunk


class Downloader:
    def __init__(self, session=None, retry=False):
        # Retries suit the public sources, but not Interline: urllib3 logs
        # the full URL on each retry, and Interline's carries an api_token.
        self.session = session or (download.make_session() if retry else requests.Session())
        self.session.headers['User-Agent'] = user_agent()

    def _request(self, method, url, timeout=download.TIMEOUT, **kw):
        # Status codes are left to the caller, which knows what each means.
        # NOTE: the URL is deliberately not logged or put in messages:
        # Interline's carries an api_token in its query string.
        try:
            return self.session.request(method, url, timeout=timeout, **kw)
        except requests.RequestException as e:
            raise ExtractDownloadError('request failed: %s' % type(e).__name__) from None

    def _get(self, url, timeout=download.TIMEOUT, stream=False):
        return self._request('GET', url, timeout=timeout, stream=stream)

    def _save(self, response, outpath, transform=None, verify=None):
        log.info('Downloading to %s' % outpath)
        response.raw.decode_content = True
        download._write_atomically(response, outpath, transform=transform, verify=verify)
        log.info('Done')


class InterlineExtractDownloader(Downloader):
    """The few regions OSM Extracts by Interline still publishes, in PBF."""
    HOST = 'https://app.interline.io'

    def url(self, extract_id, api_token=None):
        q = {'string_id': extract_id, 'data_format': 'pbf'}
        if api_token:
            q['api_token'] = api_token
        return '%s/osm_extracts/download_latest?%s' % (self.HOST, urlencode(q))

    def download(self, extract_id, outpath, api_token=None):
        r = self._get(self.url(extract_id, api_token=api_token),
                      timeout=download.LARGE_FILE_TIMEOUT, stream=True)
        if r.status_code == 403:
            r.close()
            raise ExtractDownloadError(
                'Interline rejected the API token. Pass --api-token or set '
                '$INTERLINE_API_TOKEN to the token for an active OSM Extracts '
                'subscription.')
        if r.status_code >= 400:
            detail = self._error_detail(r)
            raise ExtractDownloadError(
                'Interline could not provide %s (HTTP %s)%s' % (
                    extract_id, r.status_code, ': %s' % detail if detail else ''))
        self._save(r, outpath)

    @staticmethod
    def _error_detail(response):
        # Errors are JSON:API: {"errors": [{"detail": "..."}]}. A 410 explains
        # that the region or format is retired and where to go instead.
        try:
            errors = response.json().get('errors', [])
            return ' '.join(e['detail'] for e in errors if e.get('detail'))
        except (ValueError, AttributeError, TypeError):
            return ''
        finally:
            response.close()


class GeofabrikDownloader(Downloader):
    """Regions from Geofabrik's download server, updated daily.

    https://download.geofabrik.de/technical.html describes the index.
    """
    INDEX_URL = 'https://download.geofabrik.de/index-v1-nogeom.json'

    def __init__(self, session=None):
        super().__init__(session=session, retry=True)

    def regions(self):
        r = self._get(self.INDEX_URL)
        if r.status_code != 200:
            raise ExtractDownloadError(
                'could not fetch the Geofabrik index (HTTP %s)' % r.status_code)
        try:
            features = r.json()['features']
            return [f['properties'] for f in features
                    if 'pbf' in f['properties'].get('urls', {})]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ExtractDownloadError('the Geofabrik index is not in the expected format') from None

    def search(self, query=None):
        regions = self.regions()
        if query:
            q = query.lower()
            regions = [i for i in regions
                       if q in i['id'].lower() or q in i.get('name', '').lower()]
        return sorted(regions, key=lambda i: i['id'])

    def find(self, region_id):
        for region in self.regions():
            if region['id'] == region_id:
                return region
        raise ExtractDownloadError(
            'no Geofabrik region with id %r. Find ids with: '
            'osm_extract_download geofabrik --search=<name>' % region_id)

    @staticmethod
    def name(region_id):
        # Ids can be nested, and the last part alone is ambiguous: georgia is
        # the country, us/georgia the state. Keep the whole id.
        return region_id.replace('/', '-')

    def download(self, region_id, outpath):
        url = self.find(region_id)['urls']['pbf']
        expected = self._md5(url)
        r = self._get(url, timeout=download.LARGE_FILE_TIMEOUT, stream=True)
        if r.status_code != 200:
            r.close()
            raise ExtractDownloadError(
                'could not download %s from Geofabrik (HTTP %s)' % (region_id, r.status_code))
        reader = None

        def hashing(response):
            nonlocal reader
            reader = HashingReader(response.raw)
            return reader

        def verify():
            # Before the download replaces outpath, so a bad file never
            # displaces a good one.
            if not expected:
                return
            actual = reader.md5.hexdigest()
            if actual != expected:
                raise ExtractDownloadError(
                    'checksum mismatch for %s: expected %s, got %s. Geofabrik '
                    'may have published a new file mid-download; try again.' % (
                        region_id, expected, actual))
            log.info('Checksum verified')

        self._save(r, outpath, transform=hashing, verify=verify)

    def _md5(self, url):
        # A checksum is a check, not a requirement: any failure to get one
        # warns and downloads unverified.
        try:
            r = self._get(url + '.md5')
            parts = r.text.split() if r.status_code == 200 else []
        except ExtractDownloadError:
            parts = []
        if not parts:
            log.warning('No checksum available for %s; skipping verification' % url)
            return None
        # "<hash>  <filename>"
        return parts[0].lower()


class SliceOsmDownloader(Downloader):
    """On-demand extracts of any area, with minutely updated data.

    SliceOSM is operated by OpenStreetMap US on a best-effort, volunteer
    basis, and heavy automated use of its API is not permitted. Requests go
    one at a time, polling slowly, and a run is capped at MAX_EXTENTS.
    https://github.com/SliceOSM/sliceosm-api
    """
    API_URL = 'https://slice.openstreetmap.us/api/'
    FILES_URL = 'https://slice.openstreetmap.us/files/'
    MAX_EXTENTS = 5
    UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

    def __init__(self, session=None, sleep=time.sleep, clock=time.monotonic):
        # Retries cover a transient 5xx or 429 while polling, so a job that
        # is still running isn't abandoned and resubmitted. Only GETs are
        # retried, so a submission is never sent twice.
        super().__init__(session=session, retry=True)
        self.sleep = sleep
        self.clock = clock

    @staticmethod
    def region(feature):
        """The RegionType and RegionData SliceOSM expects for an extent."""
        geometry = feature.geometry
        if not feature.is_rectangle() and geometry.get('type') in ('Polygon', 'MultiPolygon'):
            return 'geojson', geometry
        # SliceOSM's bbox is latitude first: min_lat,min_lon,max_lat,max_lon.
        left, bottom, right, top = feature.bbox()
        return 'bbox', [bottom, left, top, right]

    def submit(self, name, feature):
        region_type, region_data = self.region(feature)
        body = json.dumps({'Name': str(name), 'RegionType': region_type,
                           'RegionData': region_data})
        r = self._request('POST', self.API_URL, data=body)
        task = r.text.strip()
        if r.status_code == 503:
            raise ExtractDownloadError(
                "SliceOSM's queue is full; try again later.")
        if r.status_code not in (200, 201) or not self.UUID.match(task):
            raise ExtractDownloadError(
                'SliceOSM did not accept %s (HTTP %s)%s. The area may be too '
                'large: see the limits at https://slice.openstreetmap.us/' % (
                    name, r.status_code, ': %s' % task if task else ''))
        return task

    def wait(self, task, timeout):
        # Back off from 2s to 30s between polls: small areas finish in
        # seconds, and large ones don't need to be asked about often.
        #
        # SliceOSM doesn't report a task that failed: its status stays
        # incomplete, just like a slow or queued one. So the timeout is the
        # only way out of a failed task.
        deadline = self.clock() + timeout
        interval = 2
        while True:
            r = self._get(self.API_URL + task)
            if r.status_code == 404:
                raise ExtractDownloadError('SliceOSM has no record of task %s' % task)
            if r.status_code != 200:
                raise ExtractDownloadError(
                    'SliceOSM returned HTTP %s for task %s' % (r.status_code, task))
            try:
                progress = r.json()
            except ValueError:
                raise ExtractDownloadError(
                    'SliceOSM returned an invalid status for task %s' % task) from None
            if progress.get('Complete'):
                return progress
            log.debug('SliceOSM task %s: %s of %s elements' % (
                task, progress.get('ElemsProg'), progress.get('ElemsTotal')))
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise ExtractDownloadError(
                    'SliceOSM task %s did not finish within %s seconds. It may '
                    'still be running, or it may have failed: SliceOSM does '
                    'not report failures. If it finishes, the result is kept '
                    'for 24 hours at %s%s.osm.pbf' % (
                        task, timeout, self.FILES_URL, task))
            self.sleep(min(interval, remaining))
            interval = min(interval * 1.5, 30)

    def download(self, name, feature, outpath, timeout=1800):
        task = self.submit(name, feature)
        log.info('SliceOSM task %s submitted for %s' % (task, name))
        self.wait(task, timeout)
        r = self._get(self.FILES_URL + task + '.osm.pbf',
                      timeout=download.LARGE_FILE_TIMEOUT, stream=True)
        if r.status_code != 200:
            r.close()
            raise ExtractDownloadError(
                'could not download the SliceOSM result for %s (HTTP %s)' % (name, r.status_code))
        self._save(r, outpath)
