#!/usr/bin/env python
import argparse
from planet import *
from bbox import bbox_string, load_bboxes_csv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='osm path')
    parser.add_argument('--csv', help='csv path with bbox definitions')
    parser.add_argument('--name', help='extract name')
    parser.add_argument('--bbox', help='bbox as (left,bottom,right,top)')
    args = parser.parse_args()
    p = Planet(args.osmpath)
    if args.csv:
        p.extract_bboxes(load_bboxes_csv(args.csv))
    elif (args.bbox and args.name):
        p.extract_bbox(args.name, bbox_string(args.bbox))
    else:
        parser.error('must specify --csv or --bbox and --name')

if __name__ == '__main__':
    main()
