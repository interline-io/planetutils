#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals
import argparse
import sys

from . import log
from .bbox import load_bboxes_csv, bbox_string
from .elevation_tile_downloader import ElevationGeotiffDownloader, ElevationSkadiDownloader

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outpath', help='Output path for elevation tiles.', default='.')
    parser.add_argument('--csv', help='Path to CSV file with bounding box definitions.')
    parser.add_argument('--bbox', help='Bounding box for extract file. Format for coordinates: left,bottom,right,top')
    parser.add_argument('--verbose', help="Verbose output", action='store_true')
    parser.add_argument('--format', help='Download format', default='geotiff')
    parser.add_argument('--zoom', help='Zoom level', default=0, type=int)

    args = parser.parse_args()

    if args.verbose:
        log.set_verbose()

    if args.format == 'geotiff':
        p = ElevationGeotiffDownloader(args.outpath, zoom=args.zoom)
    elif args.format == 'skadi':
        p = ElevationSkadiDownloader(args.outpath)
    else:
        print "Unknown format: %s"%args.format
        sys.exit(1)

    if args.csv:
        p.download_bboxes(load_bboxes_csv(args.csv))
    elif args.bbox:
        p.download_bbox(bbox_string(args.bbox))
    else:
        p.download_planet()


if __name__ == '__main__':
    main()
