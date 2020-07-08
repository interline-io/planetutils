#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals

import os
import math

import urllib3
from retry import retry
from concurrent import futures

from urllib3 import Timeout

from planetutils import download
from planetutils import log
from planetutils.bbox import validate_bbox

def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        pass

class ElevationDownloader(object):
    zoom = 0
    timeout = Timeout(connect=3.0, read=7.0)
    http = urllib3.PoolManager(maxsize=50, timeout=timeout)

    def __init__(self, outpath='.', exist_path=None):
        self.outpath = outpath
        self.exist_path = exist_path

    def download_planet(self):
        self.download_bbox([-180, -90, 180, 90])

    def download_bboxes(self, bboxes):
        for name, bbox in bboxes.items():
            self.download_bbox(bbox)

    def download_bbox(self, bbox, bucket='elevation-tiles-prod', prefix='geotiff'):
        tiles = self.get_bbox_tiles(bbox)
        found = set()
        download = set()
        for z, x, y in tiles:
            exist_dir = self.exist_path if self.exist_path else self.outpath
            od = self.tile_path(z, x, y)
            op = os.path.join(self.outpath, *od)
            cp = os.path.join(exist_dir, *od)
            if self.tile_exists(cp):
                found.add((x, y))
            else:
                download.add((x, y))
        log.info("found %s tiles; %s to download" % (len(found), len(download)))
        tasks = {self._tile_url_path(bucket, prefix, self.zoom, x, y) for x, y in sorted(download)}

        with futures.ThreadPoolExecutor() as executor:
            # Start the load operations and mark each future with its URL
            future_to_url = {
                executor.submit(self._download_multi, url_op): url_op for url_op in tasks
            }
            for future in futures.as_completed(future_to_url):
                try:
                    future.result()
                except Exception as exc:
                    log.error('generated an exception: %s' % exc)
                    pass

    def tile_exists(self, op):
        if os.path.exists(op):
            return True

    def _tile_url_path(self, bucket, prefix, z, x, y, suffix=''):
        od = self.tile_path(z, x, y)
        op = os.path.join(self.outpath, *od)
        makedirs(os.path.join(self.outpath, *od[:-1]))
        if prefix:
            od = [prefix]+od
        url = 'http://s3.amazonaws.com/%s/%s%s' % (bucket, '/'.join(od), suffix)
        return url, op

    def tile_path(self, z, x, y):
        raise NotImplementedError

    def get_bbox_tiles(self, bbox):
        raise NotImplementedError

    def _download(self, url, op):
        download.download(url, op)

    @retry(exceptions=Exception, tries=5, delay=2, backoff=2, logger=log)
    def _download_multi(self, url_op):
        url, op = url_op
        log.info("downloading %s to %s" % (url, op))
        request = self.http.request('GET', url)
        with open(op, 'wb') as f:
            try:
                f.write(request.data)
            except Exception as exc:
                raise Exception("Error downloading %r - %s", (url, exc))


class ElevationGeotiffDownloader(ElevationDownloader):
    def __init__(self, *args, **kwargs):
        self.zoom = kwargs.pop('zoom', 0)
        super(ElevationGeotiffDownloader, self).__init__(*args, **kwargs)

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
        xt = lambda x:int((x + 180.0) / 360.0 * size)
        yt = lambda y:int((1.0 - math.log(math.tan(math.radians(y)) + (1 / math.cos(math.radians(y)))) / math.pi) / 2.0 * size)
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
        expect = (max_x - min_x + 1) * (max_y - min_y + 1)
        tiles = set()
        for x in range(min_x, max_x):
            for y in range(min_y, max_y):
                tiles.add((0, x, y))
        return tiles

    def tile_exists(self, op):
        if os.path.exists(op) and os.stat(op).st_size == self.HGT_SIZE:
            return True

    def download_tile(self, bucket, prefix, z, x, y, suffix=''):
        super(ElevationSkadiDownloader, self)._tile_url_path(bucket, 'skadi', z, x, y, suffix='.gz')

    def tile_path(self, z, x, y):
        ns = lambda i:'S%02d'%abs(i) if i < 0 else 'N%02d'%abs(i)
        ew = lambda i:'W%03d'%abs(i) if i < 0 else 'E%03d'%abs(i)
        return [ns(y), '%s%s.hgt'%(ns(y), ew(x))]

    def _download(self, url, op):
        download.download_gzip(url, op)
