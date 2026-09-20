#!/usr/bin/env python
"""Merge downloaded GeoTIFF elevation tiles into a single raster.

This used to shell out to gdal_merge.py and gdal_translate. gdal_merge.py is
a Python utility that requires the GDAL Python bindings to be installed
separately, is not directly executable on Windows, and is superseded by
`gdal raster mosaic` in current GDAL. rasterio bundles GDAL in its wheels on
every platform we target, so the merge now runs in-process with no system
GDAL at all.
"""
import argparse
import fnmatch
import os
import sys

import numpy as np
import rasterio
from rasterio.merge import merge as rasterio_merge

from . import log


def find_tiles(inpath):
    matches = []
    for root, _dirnames, filenames in os.walk(inpath):
        for filename in fnmatch.filter(filenames, '*.tif'):
            matches.append(os.path.join(root, filename))
    return sorted(matches)


def merge_tiles(paths, outpath):
    """Merge `paths` into `outpath`.

    nodata=0 reproduces `gdal_merge.py -init 0`: gaps between tiles are
    initialized to zero rather than left undefined.
    """
    sources = [rasterio.open(p) for p in paths]
    try:
        array, transform = rasterio_merge(sources, nodata=0)
        profile = sources[0].profile.copy()
        profile.update(
            driver='GTiff',
            height=array.shape[1],
            width=array.shape[2],
            count=array.shape[0],
            transform=transform,
        )
        with rasterio.open(outpath, 'w', **profile) as dst:
            dst.write(array)
    finally:
        for s in sources:
            s.close()


def scale_tiles(paths, outpath, smin, smax):
    """Merge and linearly rescale to 8-bit.

    Reproduces `gdal_translate -of GTiff -ot Byte -scale <min> <max> 0 255`:
    values are clipped to [smin, smax] and mapped onto 0-255.
    """
    sources = [rasterio.open(p) for p in paths]
    try:
        array, transform = rasterio_merge(sources, nodata=0)
        profile = sources[0].profile.copy()
    finally:
        for s in sources:
            s.close()

    span = float(smax) - float(smin)
    if span == 0:
        raise ValueError('--scale min and max must differ')
    scaled = (array.astype('float64') - float(smin)) / span * 255.0
    scaled = np.clip(scaled, 0, 255).astype('uint8')

    profile.update(
        driver='GTiff',
        dtype='uint8',
        height=scaled.shape[1],
        width=scaled.shape[2],
        count=scaled.shape[0],
        transform=transform,
        nodata=None,
    )
    with rasterio.open(outpath, 'w', **profile) as dst:
        dst.write(scaled)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scale', help="Resample to 8 bit with (min,max) range")
    parser.add_argument('outpath', help='Output filename')
    parser.add_argument('inpath', help='Input directory')
    args = parser.parse_args()

    scale = None
    if args.scale:
        parts = args.scale.split(',')
        if len(parts) != 2:
            print("Must provide min, max values")
            sys.exit(1)
        scale = parts

    matches = find_tiles(args.inpath)
    if len(matches) == 0:
        print("No input files")
        sys.exit(0)

    print("Found %s files:" % len(matches))
    for i in matches:
        print("\t%s" % (i))

    print("Merging... %s" % (args.outpath))
    if scale:
        scale_tiles(matches, args.outpath, scale[0], scale[1])
    else:
        merge_tiles(matches, args.outpath)
    log.info("Done")


if __name__ == '__main__':
    main()
