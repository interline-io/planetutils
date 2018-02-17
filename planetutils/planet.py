#!/usr/bin/env python
import re
import os
import csv
import argparse
import subprocess
import urllib2
import math

import boto3

def makedirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        pass

def load_bboxes(csvpath):
    # bbox csv format:
    # name, left, bottom, right, top
    if not os.path.exists(csvpath):
        raise Exception('csvpath does not exist: %s'%csvpath)
    bboxes = []
    with open(csvpath) as f:
        reader = csv.reader(f)
        for row in reader:
            name = row[0]
            left, bottom, right, top = map(float, row[1:])
            assert top >= bottom
            assert right >= left
            bboxes.append([name, left, bottom, right, top])
    return bboxes
    
def download_gzip(url, path):
    with open(path, 'wb') as f:
        ps1 = subprocess.Popen(['curl', '-s', url], stdout=subprocess.PIPE)
        ps2 = subprocess.Popen(['gzip', '-d'], stdin=ps1.stdout, stdout=f)
        ps2.wait()    

class ElevationDownloader(object):
    HGT_SIZE = (3601 * 3601 * 2)
    
    def __init__(self, outpath):
        self.outpath = outpath

    def download_bboxes_csv(self, csvpath):
        self.download_bboxes(load_bboxes(csvpath))

    def download_bboxes(self, bboxes):
        for bbox in bboxes:
            self.download_bbox(bbox)
    
    def download_bbox(self, bbox, bucket='elevation-tiles-prod', prefix='skadi'):
        # map bbox top, left, bottom, right, top to min_x, max_x, min_y, max_y
        name, left, bottom, right, top = bbox
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
        

class PlanetBase(object):
    def __init__(self, osmpath=None, grain='hour', changeset_url=None):
        self.osmpath = osmpath
        self.workdir = '.'

    def osmosis(self, *args):
        cmd = ['osmosis'] + list(args)
        print ' '.join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False,
            cwd=self.workdir
        )

    def osmconvert(self, *args):
        cmd = ['osmconvert'] + list(args)
        print ' '.join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False,
            cwd=self.workdir
        )

    def get_timestamp(self):
        timestamp = self.osmconvert(
            self.osmpath,
            '--out-timestamp'
        )
        if 'invalid' in timestamp:
            print 'no timestamp; falling back to osmconvert --out-statistics'
            statistics = self.osmconvert(
                self.osmpath,
                '--out-statistics'
            )
            timestamp = [
                i.partition(':')[2].strip() for i in statistics.split('\n')
                if i.startswith('timestamp max')
            ][0]
        return timestamp

    def download_planet(self):
        raise NotImplementedError

    def update_planet(self, outpath, grain='hour', changeset_url=None):
        raise NotImplementedError

    def extract_bboxes(self, bboxes, workers=1):
        args = []
        args += ['--read-pbf-fast', self.osmpath, 'workers=%s'%int(workers)]
        args += ['--tee', str(len(bboxes))]
        for name, left, bottom, right, top in bboxes:
            arg = [
                '--bounding-box',
                'left=%0.5f'%left,
                'bottom=%0.5f'%bottom,
                'right=%0.5f'%right,
                'top=%0.5f'%top,
                '--write-pbf',
                '%s.osm.pbf'%name
            ]
            args += arg
        self.osmosis(*args)

    def extract_bbox(self, bbox, workers=1):
        name, left, bottom, right, top = bbox
        args = []
        args += ['--read-pbf', self.osmpath]
        args += [
            '--bounding-box',
            'left=%0.5f'%float(left),
            'bottom=%0.5f'%float(bottom),
            'right=%0.5f'%float(right),
            'top=%0.5f'%float(top),
            '--write-pbf',
            '%s.osm.pbf'%name
        ]
        self.osmosis(*args)

    def extract_bboxes_csv(self, csvpath):
        self.extract_bboxes(load_bboxes(csvpath))

class Planet(PlanetBase):
    pass

class PlanetDownloaderHttp(PlanetBase):
    def download_planet(self, url=None):
        if os.path.exists(self.osmpath):
            raise Exception('planet file exists: %s'%self.osmpath)
        url = url or 'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf'
        subprocess.check_output([
            'curl',
            '-o', self.osmpath,
            url
        ])

class PlanetDownloaderS3(PlanetBase):
    def download_planet(self):
        self.download_planet_latest()

    def download_planet_latest(self, bucket=None, prefix=None, match=None):
        if os.path.exists(self.osmpath):
            raise Exception('planet file exists: %s'%self.osmpath)
        match = match or '.*(planet[-_:T0-9]+.osm.pbf)$'
        bucket = bucket or 'osm-pds'
        objs = self._get_planets(bucket, prefix, match)
        objs = sorted(objs, key=lambda x:x.key)
        for i in objs:
            print 'found planet: s3://%s/%s'%(i.bucket_name, i.key)
        planet = objs[-1]
        print 'downloading: s3://%s/%s to %s'%(planet.bucket_name, planet.key, self.osmpath)
        self._download(planet.bucket_name, planet.key)

    def _download(self, bucket_name, key):
        s3 = boto3.client('s3')
        s3.download_file(bucket_name, key, self.osmpath)

    def _get_planets(self, bucket, prefix, match):
        r = re.compile(match)
        s3 = boto3.resource('s3')
        s3bucket = s3.Bucket(bucket)
        objs = []
        for obj in s3bucket.objects.filter(Prefix=(prefix or '')):
            if r.match(obj.key):
                objs.append(obj)
        return objs

class PlanetUpdaterOsmupdate(PlanetBase):
    pass

class PlanetUpdaterOsmosis(PlanetBase):
    def update_planet(self, outpath, grain='minute', changeset_url=None):
        if not os.path.exists(self.osmpath):
            raise Exception('planet file does not exist: %s'%self.osmpath)
        self.changeset_url = changeset_url or 'http://planet.openstreetmap.org/replication/%s'%grain
        self._initialize()
        self._initialize_state()
        self._get_changeset()
        self._apply_changeset(outpath)

    def _initialize(self):
        configpath = os.path.join(self.workdir, 'configuration.txt')
        if os.path.exists(configpath):
            return
        try:
            os.makedirs(self.workdir)
        except OSError, e:
            # print 'directory already exists: %s'%self.workdir
            pass
        self.osmosis(
            '--read-replication-interval-init',
            'workingDirectory=%s'%self.workdir
        )
        with open(configpath, 'w') as f:
            f.write('''
                baseUrl=%s
                maxInterval=0
            '''%self.changeset_url)

    def _initialize_state(self):
        statepath = os.path.join(self.workdir, 'state.txt')
        if os.path.exists(statepath):
            return
        timestamp = self.get_timestamp()
        url = 'https://replicate-sequences.osm.mazdermind.de/?%s'%timestamp
        state = urllib2.urlopen(url).read()
        with open(statepath, 'w') as f:
            f.write(state)

    def _get_changeset(self):
        self.osmosis(
            '--read-replication-interval',
            'workingDirectory=%s'%self.workdir,
            '--simplify-change',
            '--write-xml-change',
            'changeset.osm.gz'
        )

    def _apply_changeset(self, outpath):
        self.osmosis(
            '--read-xml-change',
            'changeset.osm.gz',
            '--read-pbf',
            self.osmpath,
            '--apply-change',
            '--write-pbf',
            outpath
        )
