#!/usr/bin/env python
import math
import os
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
    try:
        n = int(workers)
    except (TypeError, ValueError):
        raise ValueError(
            'workers must be an integer, got %r' % (workers,)) from None
    if n < 1:
        log.warning('workers=%s is below 1; using 1' % n)
        return 1
    if n > MAX_WORKERS:
        log.warning('workers=%s exceeds the maximum of %s; using %s'
                    % (n, MAX_WORKERS, MAX_WORKERS))
        return MAX_WORKERS
    return n


def makedirs(path):
    try:
        os.makedirs(path)
    except OSError:
        pass

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
            session.close()

    def _download_all(self, pending, bucket, prefix, session):
        """Download `pending` concurrently, stopping at the first failure.

        Only a bounded number of futures is kept in flight. Submitting every
        tile up front would pin a Future per tile for the whole run, which at
        planet scale is many gigabytes allocated before the first byte.

        A failure propagates, matching the serial loop this replaces; the
        remaining work is cancelled rather than left to drain, so Ctrl-C and
        errors both stop promptly.
        """
        queue = iter(pending)
        in_flight = set()
        window = self.workers * 2
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            while True:
                while len(in_flight) < window:
                    try:
                        z, x, y = next(queue)
                    except StopIteration:
                        break
                    in_flight.add(pool.submit(
                        self.download_tile, bucket, prefix, z, x, y,
                        session=session))
                if not in_flight:
                    break
                done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    future.result()      # re-raises the first failure
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
        if os.path.exists(op) and os.stat(op).st_size == self.HGT_SIZE:
            return True

    def download_tile(self, bucket, prefix, z, x, y, suffix='', session=None):
        super().download_tile(bucket, 'skadi', z, x, y, suffix='.gz',
                              session=session)

    def tile_path(self, z, x, y):
        def ns(i):
            return 'S%02d'%abs(i) if i < 0 else 'N%02d'%abs(i)

        def ew(i):
            return 'W%03d'%abs(i) if i < 0 else 'E%03d'%abs(i)
        return [ns(y), '%s%s.hgt'%(ns(y), ew(x))]

    def _download(self, url, op, session=None):
        download.download_gzip(url, op, session=session)
