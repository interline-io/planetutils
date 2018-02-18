#!/usr/bin/env python
import argparse
from elevation import *

from bbox import load_bboxes_csv, bbox_string

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('outpath', help='output path')
    parser.add_argument('--csv', help='csv path with bbox definitions')
    parser.add_argument('--bbox', help='bbox as (left,bottom,right,top)')
    args = parser.parse_args()
    p = ElevationDownloader(args.outpath)
    if args.csv:
        p.download_bboxes(load_bboxes_csv(args.csv))
    elif args.bbox:
        p.download_bbox(bbox_string(args.bbox))
    else:
        p.download_planet()

if __name__ == '__main__':
    main()
