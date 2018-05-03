#!/usr/bin/env python
import argparse
from elevation import *

from bbox import load_bboxes_csv, bbox_string

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outpath', help='Output path for elevation tiles.', default='.')
    parser.add_argument('--csv', help='Path to CSV file with bounding box definitions.')
    parser.add_argument('--bbox', help='Bounding box for extract file. Format for coordinates: left,bottom,right,top')
    parser.add_argument('--verbose', help="Verbose output", action='store_true')
    args = parser.parse_args()

   if args.verbose:
        log.set_verbose()

    p = ElevationDownloader(args.outpath)
    if args.csv:
        p.download_bboxes(load_bboxes_csv(args.csv))
    elif args.bbox:
        p.download_bbox(bbox_string(args.bbox))
    else:
        p.download_planet()

if __name__ == '__main__':
    main()
