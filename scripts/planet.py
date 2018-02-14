#!/usr/bin/env python
import os
import csv
import argparse
import subprocess
import urllib2

def get_planet(bucket=None):
    bucket = bucket or 'osm-pds'
    return 'planet-latest.osm.pbf'

class PlanetUpdater(object):
    def __init__(self, osmpath):
        self.osmpath = osmpath
        self.workdir = '.'

    def update_planet(self, outpath):
        pass

class PlanetUpdaterOsmupdate(PlanetUpdater):
    def update_planet(self, outpath):
        pass

class PlanetUpdaterOsmosis(PlanetUpdater):
    def update_planet(self, outpath):
        self._initialize()
        self._initialize_state()
        self._get_changeset()
        self._apply_changeset(outpath)

    def osmosis(self, *args):
        cmd = ['osmosis'] + list(args)
        print " ".join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False,
            cwd=self.workdir
        )

    def osmconvert(self, *args):
        cmd = ['osmconvert'] + list(args)
        print " ".join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False,
            cwd=self.workdir
        )

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

    def _initialize_state(self):
        statepath = os.path.join(self.workdir, 'state.txt')
        if os.path.exists(statepath):
            return
        timestamp = self.osmconvert(
            self.osmpath,
            '--out-timestamp'
        )
        if 'invalid' in timestamp:
            raise Exception('invalid timestamp: %s'%self.osmpath)
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='osm path')
    parser.add_argument('outpath', help='output path')
    args = parser.parse_args()
    p = PlanetUpdaterOsmosis(args.osmpath)
    p.update_planet(args.outpath)
