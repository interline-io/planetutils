#!/usr/bin/env python
import os
import argparse

import log
import tilepack
from bbox import bbox_string, load_bboxes_csv

def main():
    parser = argparse.ArgumentParser(usage="Valhalla Tilepack Download tool. If no Tilepack ID is provided, the latest Tilepack is used.")
    parser.add_argument('--id', help='Tilepack ID', default='latest')
    parser.add_argument('--outpath', help='Output path for Valhalla Tilepack; default is tiles.tar', default='tiles.tar')
    parser.add_argument('--api-token', help='Interline Auth Token; default is read from $INTERLINE_API_TOKEN')
    parser.add_argument('--compressed', help='Do not decompress Tilepack', action='store_true')
    args = parser.parse_args()

    outpath = args.outpath
    if args.compressed:
        if not (outpath.endswith('.tar') or outpath.endswith('.tgz')):
            log.warning("Warning: compressed output path %s does not in end in .tar.gz or .tgz"%outpath)
    else:
        if not outpath.endswith('.tar'):
            log.warning("Warning: decompressed output path %s does not end in .tar"%outpath)
    if os.path.exists(outpath):
        log.warning("Warning: output path %s already exists."%outpath)

    tp = tilepack.Tilepack()
    tp.download(
        args.outpath,
        version=args.id,
        compressed=args.compressed,
        api_token=args.api_token or os.getenv('INTERLINE_API_TOKEN')
    )

if __name__ == '__main__':
    main()
