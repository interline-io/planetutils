#!/usr/bin/env python
import re
import os
import subprocess
import urllib2

import boto3

from bbox import validate_bbox

class PlanetBase(object):
    def __init__(self, osmpath=None, grain='hour', changeset_url=None, osmosis_workdir=None):
        self.osmpath = osmpath
        d, p = os.path.split(osmpath)
        self.osmosis_workdir = osmosis_workdir or os.path.join(d, '%s.workdir'%p)

    def osmosis(self, *args):
        cmd = ['osmosis'] + list(args)
        print ' '.join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False
        )

    def osmconvert(self, *args):
        cmd = ['osmconvert'] + list(args)
        print ' '.join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False
        )

    def get_timestamp(self):
        timestamp = self.osmconvert(
            self.osmpath,
            '--out-timestamp'
        )
        if 'invalid' in timestamp:
            statistics = self.osmconvert(
                self.osmpath,
                '--out-statistics'
            )
            timestamp = [
                i.partition(':')[2].strip() for i in statistics.split('\n')
                if i.startswith('timestamp max')
            ][0]
        return timestamp.strip()

    def download_planet(self):
        raise NotImplementedError

    def update_planet(self, outpath, grain='hour', changeset_url=None):
        raise NotImplementedError

    def extract_bboxes(self, bboxes, workers=1, outpath='.'):
        args = []
        args += ['--read-pbf-fast', self.osmpath, 'workers=%s'%int(workers)]
        args += ['--tee', str(len(bboxes))]
        for name, bbox in bboxes.items():
            validate_bbox(bbox)
            left, bottom, right, top = bbox
            arg = [
                '--bounding-box',
                'left=%0.5f'%left,
                'bottom=%0.5f'%bottom,
                'right=%0.5f'%right,
                'top=%0.5f'%top,
                '--write-pbf',
                os.path.join(outpath, '%s.osm.pbf'%name)
            ]
            args += arg
        self.osmosis(*args)

    def extract_bbox(self, name, bbox, workers=1, outpath='.'):
        return self.extract_bboxes({name: bbox}, outpath=outpath, workers=workers)

class Planet(PlanetBase):
    pass

class PlanetDownloaderHttp(PlanetBase):
    def _download(self, url, outpath):
        subprocess.check_output([
            'curl',
            '-o', outpath,
            url
        ])

    def download_planet(self, url=None):
        if os.path.exists(self.osmpath):
            raise Exception('planet file exists: %s'%self.osmpath)
        url = url or 'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf'
        self._download(url, self.osmpath)

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
        self.changeset_url = changeset_url or 'https://planet.openstreetmap.org/replication/%s'%grain
        self._initialize()
        self._initialize_state()
        self._get_changeset()
        self._apply_changeset(outpath)

    def _initialize(self):
        configpath = os.path.join(self.osmosis_workdir, 'configuration.txt')
        if os.path.exists(configpath):
            return
        if os.path.exists(self.osmosis_workdir) and not os.path.isdir(self.osmosis_workdir):
            raise Exception('workdir exists and is not a directory: %s'%self.osmosis_workdir)
        try:
            os.makedirs(self.osmosis_workdir)
        except OSError, e:
            pass
        self.osmosis(
            '--read-replication-interval-init',
            'workingDirectory=%s'%self.osmosis_workdir
        )
        with open(configpath, 'w') as f:
            f.write('''
                baseUrl=%s
                maxInterval=0
            '''%self.changeset_url)

    def _initialize_state(self):
        statepath = os.path.join(self.osmosis_workdir, 'state.txt')
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
            'workingDirectory=%s'%self.osmosis_workdir,
            '--simplify-change',
            '--write-xml-change',
            os.path.join(self.osmosis_workdir, 'changeset.osm.gz')
        )

    def _apply_changeset(self, outpath):
        self.osmosis(
            '--read-xml-change',
            os.path.join(self.osmosis_workdir, 'changeset.osm.gz'),
            '--read-pbf',
            self.osmpath,
            '--apply-change',
            '--write-pbf',
            outpath
        )
