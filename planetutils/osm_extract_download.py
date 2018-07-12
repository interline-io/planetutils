#!/usr/bin/env python
from __future__ import absolute_import
import os
import argparse

from . import log
from .bbox import bbox_string, load_bboxes_csv
from .osm_extract_downloader import OsmExtractDownloader

def main():
    parser = argparse.ArgumentParser(usage="OSM Extract Download tool.")
    parser.add_argument('id', help='Extract ID')
    # parser.add_argument('--osm-extract-version', help='OSM Extract version', default='latest')
    parser.add_argument('--outpath', help='Output path for Extract; default is <name>.osm.pbf')
    parser.add_argument('--api-token', help='Interline Auth Token; default is read from $INTERLINE_API_TOKEN')
    parser.add_argument('--verbose', help="Verbose output", action='store_true')
    args = parser.parse_args()

    if args.verbose:
        log.set_verbose()

    outpath = args.outpath or "%s.osm.pbf"%(args.id)
    if os.path.exists(outpath):
        log.warning("Warning: output path %s already exists."%outpath)

    downloader = OsmExtractDownloader()
    downloader.download(
        outpath,
        osm_extract_id=args.id,
        api_token=args.api_token or os.getenv('INTERLINE_API_TOKEN')
    )

if __name__ == '__main__':
    main()
