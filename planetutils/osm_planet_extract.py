#!/usr/bin/env python
import argparse
from planet import *
from bbox import bbox_string, load_bboxes_csv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='Name or path to OSM planet file. Use planet_update if you do not have a copy locally.')
    parser.add_argument('--outpath', help='Extract output directory', default='.')
    parser.add_argument('--csv', help='Path to CSV file with bounding box definitions.')
    parser.add_argument('--name', help='Name to give to extract file.')
    parser.add_argument('--bbox', help='Bounding box for extract file. Format for coordinates: left,bottom,right,top')
    args = parser.parse_args()
    p = Planet(args.osmpath)
    if args.csv:
        p.extract_bboxes(load_bboxes_csv(args.csv), outpath=args.outpath)
    elif (args.bbox and args.name):
        p.extract_bbox(args.name, bbox_string(args.bbox), outpath=args.outpath)
    else:
        parser.error('must specify --csv or --bbox and --name')

if __name__ == '__main__':
    main()
