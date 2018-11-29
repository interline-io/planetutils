#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals
import argparse
import sys
import fnmatch
import os
import subprocess
import tempfile

from . import log

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scale', help="Resample to 8 bit with (min,max) range")
    parser.add_argument('outpath', help='Output filename')
    parser.add_argument('inpath', help='Input directory')
    args = parser.parse_args()

    outpath = args.outpath
    tmppath = args.outpath

    if args.scale and len(args.scale.split(',')) != 2:
        print "Must provide min, max values"
        sys.exit(1)
    elif args.scale:
        # Output to tmp file
        _, tmppath = tempfile.mkstemp(suffix='.tif')

    matches = []
    for root, dirnames, filenames in os.walk(args.inpath):
        for filename in fnmatch.filter(filenames, '*.tif'):
            matches.append(os.path.join(root, filename))

    if len(matches) == 0:
        print "No input files"
        sys.exit(0)

    print "Found %s files:"%len(matches)
    for i in matches:
        print "\t%s"%(i)

    # gdal_merge.py -init 0 -o out.tif
    print "Merging... %s"%(tmppath)
    cmd = ['gdal_merge.py', '-init', '0', '-o', tmppath]
    cmd += matches
    p = subprocess.check_call(cmd)

    # gdal_translate -of GTiff -ot Byte -scale 0 255 0 255 out.tif out8.tif
    if args.scale:
        print "Scaling: %s -> %s"%(tmppath, outpath)
        a = args.scale.split(",")
        cmd = ['gdal_translate', '-of', 'GTiff', '-ot', 'Byte', '-scale', a[0], a[1], '0', '255', tmppath, outpath]
        subprocess.check_call(cmd)
        # cleanup
        try: os.unlink('%s.aux.xml'%outpath)
        except: pass
        try: os.unlink(tmppath)
        except: pass

if __name__ == '__main__':
    main()
