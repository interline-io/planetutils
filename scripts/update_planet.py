#!/usr/bin/env python
import argparse
from planet import *

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='osm path')
    parser.add_argument('outpath', help='output path')
    args = parser.parse_args()
    if not os.path.exists(args.osmpath):
        print "planet does not exist; downloading"
        d = PlanetDownloaderS3(args.osmpath)
        d.download_planet_latest()
    p = PlanetUpdaterOsmosis(args.osmpath)
    p.update_planet(args.outpath)
