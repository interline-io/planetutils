#!/usr/bin/env python
import argparse
from planet import *
import bbox
from bbox import bbox_string, load_bboxes_csv

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='Name or path to OSM planet file. Use planet_update if you do not have a copy locally.')
    parser.add_argument('--outpath', help='Extract output directory', default='.')
    parser.add_argument('--csv', help='Path to CSV file with bounding box definitions.')
    parser.add_argument('--geojson', help='Path to GeoJSON file: bbox for each feature is extracted.')
    parser.add_argument('--name', help='Name to give to extract file.')
    parser.add_argument('--bbox', help='Bounding box for extract file. Format for coordinates: left,bottom,right,top')
    args = parser.parse_args()
    p = Planet(args.osmpath)

    bboxes = {}
    if args.csv:
        bboxes = bbox.load_bboxes_csv(args.csv)        
    elif args.geojson:
        bboxes = bbox.load_bboxes_geojson(args.geojson)
    elif (args.bbox and args.name):
        bboxes[args.name] = bbox.bbox_string(args.bbox)
    else:
        parser.error('must specify --csv, --geojson, or --bbox and --name')
    print bboxes

    p.extract_bboxes(bboxes, outpath=args.outpath)

if __name__ == '__main__':
    main()
