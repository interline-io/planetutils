#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals
import os
import subprocess
import math

from . import download
from . import log
from .bbox import validate_bbox

def makedirs(path):
    try:
        os.makedirs(path)
    except OSError as e:
        pass

class ElevationDownloader(object):
    """Downloads elevation tiles from AWS Open Data Registry's Terrain Tiles dataset.
    
    This class handles downloading of elevation data from the Terrain Tiles dataset
    hosted on AWS S3. The dataset is available in both US (us-east-1) and EU (eu-central-1)
    regions through the buckets elevation-tiles-prod and elevation-tiles-prod-eu respectively.
    
    Data source: https://registry.opendata.aws/terrain-tiles/
    """
    def __init__(self, outpath='.', region='us-east-1'):
        self.outpath = outpath
        self.region = region
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
        for name, bbox in bboxes.items():
            self.download_bbox(bbox)
    
    def download_bbox(self, bbox, bucket='elevation-tiles-prod', prefix='geotiff'):
        tiles = self.get_bbox_tiles(bbox)
        found = set()
        download = set()
        for z,x,y in tiles:
            od = self.tile_path(z, x, y)
            op = os.path.join(self.outpath, *od)
            if self.tile_exists(op):
                found.add((x,y))
            else:
                download.add((x,y))
        log.info("found %s tiles; %s to download"%(len(found), len(download)))
        for x,y in sorted(download):
            self.download_tile(bucket, prefix, z, x, y)

    def tile_exists(self, op):
        if os.path.exists(op):
            return True

    def download_tile(self, bucket, prefix, z, x, y, suffix=''):
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
        self._download(url, op)
        
    def tile_path(self, z, x, y):
        raise NotImplementedError

    def get_bbox_tiles(self, bbox):
        raise NotImplementedError

    def _download(self, url, op):
        download.download(url, op)

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
        super(ElevationSkadiDownloader, self).download_tile(bucket, 'skadi', z, x, y, suffix='.gz')

    def tile_path(self, z, x, y):
        ns = lambda i:'S%02d'%abs(i) if i < 0 else 'N%02d'%abs(i)
        ew = lambda i:'W%03d'%abs(i) if i < 0 else 'E%03d'%abs(i)
        return [ns(y), '%s%s.hgt'%(ns(y), ew(x))]

    def _download(self, url, op):
        download.download_gzip(url, op)
