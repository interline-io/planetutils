#!/usr/bin/env python
import argparse
from planet import *

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='osm path')
    parser.add_argument('csvpath', help='csv path with bbox definitions')
    args = parser.parse_args()
    p = Planet(args.osmpath)
    p.extract_bboxes_csv(args.csvpath)
