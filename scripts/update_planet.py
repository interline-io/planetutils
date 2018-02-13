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
        self.osmosis_path = '/usr/local/bin/osmosis'
        self.osmconvert_path = '/usr/local/bin/osmconvert'
        self.env = {
            'JAVACMD_OPTIONS': '-Djava.io.tmpdir=tmp'
        }

    def osmosis(self, *args):
        cmd = [self.osmosis_path] + list(args)
        print " ".join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False,
            cwd=self.workdir
        )

    def osmconvert(self, *args):
        cmd = [self.osmconvert_path] + list(args)
        print " ".join(cmd)
        return subprocess.check_output(
            cmd,
            shell=False,
            cwd=self.workdir
        )

    def update_planet(self, outpath):
        self.initialize()
        self.get_state()
        self.get_changeset()
        self.apply_changeset(outpath)

    def initialize(self):
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

    def get_state(self):
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

    def get_changeset(self):
        self.osmosis(
            '--read-replication-interval',
            'workingDirectory=%s'%self.workdir,
            '--simplify-change',
            '--write-xml-change',
            'changeset.osm.gz'
        )

    def apply_changeset(self, outpath):
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
    parser.add_argument('osmpath', help='osm output path')
    args = parser.parse_args()
    p = PlanetUpdater(args.osmpath)
    p.update_planet('updated.osm.pbf')
