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

class ElevationTileDownloader(object):
    HGT_SIZE = (3601 * 3601 * 2)
    
    def __init__(self, outpath='.'):
        self.outpath = outpath

    def download_planet(self):
        self.download_bbox([-180, -90, 180, 90])

    def download_bboxes(self, bboxes):
        for name, bbox in bboxes.items():
            self.download_bbox(bbox)
    
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
                tiles.add((x,y))
        return tiles
    
    def download_bbox(self, bbox, bucket='elevation-tiles-prod', prefix='skadi'):
        tiles = self.get_bbox_tiles(bbox)
        found = set()
        download = set()
        for x,y in tiles:
            od, key = self.hgtpath(x, y)
            op = os.path.join(self.outpath, od, key)
            if os.path.exists(op) and os.stat(op).st_size == self.HGT_SIZE:
                found.add((x,y))
            else:
                download.add((x,y))
        log.info("found %s tiles; %s to download"%(len(found), len(download)))
        if len(download) > 100:
            log.warning("  warning: downloading %s tiles will take an additional %0.2f GiB disk space"%(
                len(download),
                (len(download) * self.HGT_SIZE) / (1024.0**3)
            ))
        for x,y in sorted(download):
            self.download_hgt(bucket, prefix, x, y)
    
    def hgtpath(self, x, y):
        ns = lambda i:'S%02d'%abs(i) if i < 0 else 'N%02d'%abs(i)
        ew = lambda i:'W%03d'%abs(i) if i < 0 else 'E%03d'%abs(i)
        return ns(y), '%s%s.hgt'%(ns(y), ew(x))

    def download_hgt(self, bucket, prefix, x, y):
        od, key = self.hgtpath(x, y)
        op = os.path.join(self.outpath, od, key)
        makedirs(os.path.join(self.outpath, od))
        url = 'http://s3.amazonaws.com/%s/%s/%s/%s.gz'%(bucket, prefix, od, key)
        log.info("downloading %s to %s"%(url, op))
        download.download_gzip(url, op)
        
