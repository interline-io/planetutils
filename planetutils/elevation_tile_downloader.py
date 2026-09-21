#!/usr/bin/env python
import math
import os
import struct
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from . import download, log
from .bbox import validate_bbox

# Tile downloads are latency-bound rather than bandwidth-bound, so fetching
# several at once is worth far more than any per-request tuning.
DEFAULT_WORKERS = 16

# Each worker is an OS thread and the pool grows to max_workers because real
# downloads block. Past a few dozen the remote host is the bottleneck, and a
# large enough value exhausts the process thread limit.
MAX_WORKERS = 64


def clamp_workers(workers):
    """Coerce `workers` into a usable range, warning when it is adjusted."""
    if workers is None:
        return DEFAULT_WORKERS
    # bool is an int subclass, so True would silently become 1 worker.
    if isinstance(workers, bool):
        raise ValueError('workers must be an integer, got %r' % (workers,))
    try:
        n = int(workers)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            'workers must be an integer, got %r' % (workers,)) from None
    if n != workers:
        raise ValueError('workers must be a whole number, got %r' % (workers,))
    if n < 1:
        log.warning('workers=%s is below 1; using 1' % n)
        return 1
    if n > MAX_WORKERS:
        log.warning('workers=%s exceeds the maximum of %s; using %s'
                    % (n, MAX_WORKERS, MAX_WORKERS))
        return MAX_WORKERS
    return n


def makedirs(path):
    # exist_ok rather than swallowing OSError: with many threads creating the
    # same parent concurrently the race is benign, but a genuine ENOSPC,
    # EACCES or EROFS must propagate instead of surfacing later as a
    # confusing FileNotFoundError on the .part file.
    os.makedirs(path, exist_ok=True)

class ElevationDownloader:
    """Downloads elevation tiles from AWS Open Data Registry's Terrain Tiles dataset.

    This class handles downloading of elevation data from the Terrain Tiles dataset
    hosted on AWS S3. The dataset is available in both US (us-east-1) and EU (eu-central-1)
    regions through the buckets elevation-tiles-prod and elevation-tiles-prod-eu respectively.

    Data source: https://registry.opendata.aws/terrain-tiles/
    """
    def __init__(self, outpath='.', region='us-east-1',
                 workers=DEFAULT_WORKERS):
        self.outpath = outpath
        self.region = region
        self.workers = clamp_workers(workers)
        # Map regions to buckets
        self.region_buckets = {
            'us-east-1': 'elevation-tiles-prod',
            'eu-central-1': 'elevation-tiles-prod-eu'
        }

    def get_bucket_for_region(self, default_bucket):
        """Get the appropriate bucket based on region, falling back to default"""
        return self.region_buckets.get(self.region, default_bucket)

    def download_planet(self):
        self.download_bbox([-180, -90, 180, 90])

    def download_bboxes(self, bboxes):
        for _name, bbox in bboxes.items():
            self.download_bbox(bbox)

    def download_bbox(self, bbox, bucket='elevation-tiles-prod', prefix='geotiff'):
        tiles = self.get_bbox_tiles(bbox)
        found = set()
        # NB: named `pending`, not `download` -- the latter shadows the
        # imported download module within this function.
        pending = set()
        for z,x,y in tiles:
            od = self.tile_path(z, x, y)
            op = os.path.join(self.outpath, *od)
            if self.tile_exists(op):
                found.add((z,x,y))
            else:
                pending.add((z,x,y))
        log.info("found %s tiles; %s to download"%(len(found), len(pending)))
        if not pending:
            return
        session = download.make_session(pool_size=self.workers)
        try:
            self._download_all(sorted(pending), bucket, prefix, session)
        finally:
            # _download_all only returns once the pool has shut down, so no
            # worker is still using the session here. Closing it while
            # threads were live would give them ClosedPoolError and let them
            # keep writing tiles after the caller saw the failure.
            session.close()

    def _download_all(self, pending, bucket, prefix, session):
        """Download `pending` concurrently, stopping at the first failure.

        Only a bounded number of futures is kept in flight. Submitting every
        tile up front would pin a Future per tile for the whole run, which at
        planet scale is many gigabytes allocated before the first byte.

        A failure propagates, matching the serial loop this replaces, and
        queued work is cancelled rather than left to drain.

        Note that tiles already running cannot be cancelled: they are
        non-daemon pool threads that the interpreter joins at exit, so a
        Ctrl-C still waits for up to `workers` in-flight requests to finish
        or time out. The bounded window keeps that to a small, fixed cost
        instead of the whole queue.
        """
        queue = iter(pending)
        in_flight = set()
        order = {}
        window = self.workers * 2
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            while True:
                while len(in_flight) < window:
                    try:
                        z, x, y = next(queue)
                    except StopIteration:
                        break
                    future = pool.submit(
                        self.download_tile, bucket, prefix, z, x, y,
                        session=session)
                    order[future] = (z, x, y)
                    in_flight.add(future)
                if not in_flight:
                    break
                done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                # `done` is a set, so iterate the tiles in a defined order
                # and report the lowest-numbered failure rather than an
                # arbitrary one. Sibling errors are logged so a disk-full is
                # not hidden behind an incidental 403.
                failures = [(order[f], f.exception()) for f in done
                            if f.exception() is not None]
                if failures:
                    failures.sort()
                    for tile, exc in failures[1:]:
                        log.error('also failed %s/%s/%s: %s'
                                  % (tile + (exc or type(exc).__name__,)))
                    raise failures[0][1]
        except BaseException:
            # A plain `with ThreadPoolExecutor` exits via shutdown(wait=True)
            # with no cancellation, so the queue would drain first and Ctrl-C
            # would appear to hang.
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)

    def tile_exists(self, op):
        if os.path.exists(op):
            return True

    def download_tile(self, bucket, prefix, z, x, y, suffix='', session=None):
        od = self.tile_path(z, x, y)
        op = os.path.join(self.outpath, *od)
        makedirs(os.path.join(self.outpath, *od[:-1]))
        if prefix:
            od = [prefix]+od

        # Use the region-specific bucket if available
        actual_bucket = self.get_bucket_for_region(bucket)

        # Use virtual-hosted style URL
        if self.region == 'us-east-1':
            url = f'https://{actual_bucket}.s3.amazonaws.com/{"/".join(od)}{suffix}'
        else:
            url = f'https://{actual_bucket}.s3.{self.region}.amazonaws.com/{"/".join(od)}{suffix}'

        log.info("downloading %s to %s"%(url, op))
        self._download(url, op, session=session)

    def tile_path(self, z, x, y):
        raise NotImplementedError

    def get_bbox_tiles(self, bbox):
        raise NotImplementedError

    def _download(self, url, op, session=None):
        download.download(url, op, session=session)

class ElevationGeotiffDownloader(ElevationDownloader):
    def __init__(self, *args, **kwargs):
        self.zoom = kwargs.pop('zoom', 0)
        super().__init__(*args, **kwargs)

    def get_bbox_tiles(self, bbox):
        left, bottom, right, top = validate_bbox(bbox)
        ybound = 85.0511
        if bottom <= -ybound:
            bottom = -ybound
        if top > ybound:
            top = ybound
        if right >= 180:
            right = 179.999
        size = 2**self.zoom
        def xt(x):
            return int((x + 180.0) / 360.0 * size)

        def yt(y):
            return int((1.0 - math.log(math.tan(math.radians(y)) + (1 / math.cos(math.radians(y)))) / math.pi) / 2.0 * size)
        tiles = []
        for x in range(xt(left), xt(right)+1):
            for y in range(yt(top), yt(bottom)+1):
                tiles.append([self.zoom, x, y])
        return tiles

    def tile_path(self, z, x, y):
        return list(map(str, [z, x, str(y)+'.tif']))

class ElevationSkadiDownloader(ElevationDownloader):
    HGT_SIZE = (3601 * 3601 * 2)

    # gzip magic; a .hgt.gz has no predictable size, so this is what
    # distinguishes a real tile from a truncated download or an error body.
    GZIP_MAGIC = b'\x1f\x8b'

    def __init__(self, *args, **kwargs):
        # Skadi tiles are served gzipped and inflated on write, so what lands
        # on disk is several times larger than what came over the wire -- a
        # full planet is ~1.6 TB inflated against ~350-500 GB compressed.
        # Valhalla reads .hgt.gz natively, so keeping them packed is an
        # option rather than a conversion step.
        self.keep_compressed = kwargs.pop('keep_compressed', False)
        # Tiles satisfied by the other form, reported after a run: switching
        # the flag does not convert an existing cache, so a run can complete
        # having written nothing.
        self.matched_other_form = 0
        super().__init__(*args, **kwargs)

    def download_bbox(self, bbox, bucket='elevation-tiles-prod',
                      prefix='geotiff'):
        self.matched_other_form = 0
        super().download_bbox(bbox, bucket=bucket, prefix=prefix)
        if self.matched_other_form:
            wanted = '.hgt.gz' if self.keep_compressed else '.hgt'
            log.info(
                '%s tiles were already present in the other form; '
                '--keep-compressed does not convert an existing cache, so '
                'no %s was written for them'
                % (self.matched_other_form, wanted))

    def get_bbox_tiles(self, bbox):
        left, bottom, right, top = validate_bbox(bbox)
        min_x = int(math.floor(left))
        max_x = int(math.ceil(right))
        min_y = int(math.floor(bottom))
        max_y = int(math.ceil(top))
        tiles = set()
        for x in range(min_x, max_x):
            for y in range(min_y, max_y):
                tiles.add((0, x, y))
        return tiles

    def tile_exists(self, op):
        """True when a complete tile is already on disk, in either form.

        Accepting both means switching --keep-compressed on or off does not
        re-download a cache that is already complete; Valhalla reads either.

        The form this run would write is checked first and must be intact: a
        corrupt file there is re-downloaded even when a good copy of the
        other form sits beside it, since that is the file being replaced.
        """
        raw = op[:-3] if op.endswith('.gz') else op
        gz = raw + '.gz'
        target, other = (gz, raw) if op.endswith('.gz') else (raw, gz)
        if os.path.exists(target):
            return self.tile_is_complete(target)
        if self.tile_is_complete(other):
            self.matched_other_form += 1
            return True
        return False

    def tile_is_complete(self, path):
        if path.endswith('.gz'):
            return self.gzip_tile_exists(path)
        try:
            return os.stat(path).st_size == self.HGT_SIZE
        except OSError:
            return False

    def gzip_tile_exists(self, path):
        """True when `path` is a complete gzip stream of one Skadi tile.

        The magic bytes alone would accept a truncated stream, since they
        survive any truncation. gzip's trailer ends with ISIZE, the
        uncompressed length, so comparing that to HGT_SIZE gives the same
        guarantee the inflated form gets from its exact size. HGT_SIZE is
        well under the 2^32 that ISIZE wraps at.
        """
        try:
            with open(path, 'rb') as f:
                if f.read(2) != self.GZIP_MAGIC:
                    return False
                if os.fstat(f.fileno()).st_size < 18:
                    return False    # too short to hold header and trailer
                f.seek(-4, os.SEEK_END)
                isize = struct.unpack('<I', f.read(4))[0]
        except OSError:
            return False
        return isize == self.HGT_SIZE

    def download_tile(self, bucket, prefix, z, x, y, suffix='', session=None):
        # The remote object is always .hgt.gz. download_tile builds the URL
        # from tile_path() plus this suffix, so when the local name already
        # carries .gz no extra suffix belongs on the URL.
        super().download_tile(
            bucket, 'skadi', z, x, y,
            suffix='' if self.keep_compressed else '.gz',
            session=session)

    def tile_path(self, z, x, y):
        def ns(i):
            return 'S%02d'%abs(i) if i < 0 else 'N%02d'%abs(i)

        def ew(i):
            return 'W%03d'%abs(i) if i < 0 else 'E%03d'%abs(i)
        suffix = '.hgt.gz' if self.keep_compressed else '.hgt'
        return [ns(y), '%s%s%s'%(ns(y), ew(x), suffix)]

    def _download(self, url, op, session=None):
        if self.keep_compressed:
            # Store the gzip stream as it arrived, rather than inflating it.
            download.download(url, op, session=session, compressed=True)
        else:
            download.download_gzip(url, op, session=session)
