#!/usr/bin/env python
import os
import subprocess
import math

from bbox import validate_bbox

def makedirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        pass

def download_gzip(url, path):
    with open(path, 'wb') as f:
        ps1 = subprocess.Popen(['curl', '-s', url], stdout=subprocess.PIPE)
        ps2 = subprocess.Popen(['gzip', '-d'], stdin=ps1.stdout, stdout=f)
        ps2.wait()    

class ElevationDownloader(object):
    HGT_SIZE = (3601 * 3601 * 2)
    
    def __init__(self, outpath='.'):
        self.outpath = outpath

    def download_planet(self):
        self.download_bbox([-180, -90, 180, 90])

    def download_bboxes(self, bboxes):
        for name, bbox in bboxes.items():
            self.download_bbox(bbox)
    
    def download_bbox(self, bbox, bucket='elevation-tiles-prod', prefix='skadi'):
        left, bottom, right, top = validate_bbox(bbox)
        min_x = int(math.floor(left))
        max_x = int(math.ceil(right))
        min_y = int(math.floor(bottom))
        max_y = int(math.ceil(top))
        expect = (max_x - min_x + 1) * (max_y - min_y + 1)
        found = set()
        download = set()
        for x in xrange(min_x, max_x):
            for y in xrange(min_y, max_y):
                od, key = self.hgtpath(x, y)
                op = os.path.join(self.outpath, od, key)
                if os.path.exists(op) and os.stat(op).st_size == self.HGT_SIZE:
                    found.add((x,y))
                else:
                    download.add((x,y))
        print "found %s tiles; %s to download"%(len(found), len(download))
        if len(download) > 100:
            print "  warning: downloading %s tiles will take an additional %0.2f GiB disk space"%(
                len(download),
                (len(download) * self.HGT_SIZE) / (1024.0**3)
            )
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
        print "downloading %s to %s"%(url, op)
        download_gzip(url, op)
        
