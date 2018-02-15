#!/usr/bin/env python
import argparse
from planet import *

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='osm path')
    parser.add_argument('outpath', help='output path')
    parser.add_argument('--s3', action='store_true', help='download using s3 from osm-pds')
    args = parser.parse_args()
    if not os.path.exists(args.osmpath):
        print "planet does not exist; downloading"
        if args.s3:
            d = PlanetDownloaderS3(args.osmpath)
        else:
            d = PlanetDownloaderHttp(args.osmpath)
        d.download_planet()
    p = PlanetUpdaterOsmosis(args.osmpath)
    p.update_planet(args.outpath)
