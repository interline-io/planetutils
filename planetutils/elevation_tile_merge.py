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
import tempfile

import numpy as np
import rasterio
from rasterio.merge import merge as rasterio_merge

from . import log

# Bound on the working buffer rasterio uses while merging, in MB. Output is
# written to disk incrementally, so a large tile set need not fit in RAM.
MEM_LIMIT_MB = 256

# gdal_merge.py copied each input over the output in sequence, so the last
# file to cover a pixel won. rasterio defaults to "first"; match the old
# behavior for anyone whose inputs overlap.
MERGE_METHOD = 'last'


def find_tiles(inpath):
    matches = []
    for root, _dirnames, filenames in os.walk(inpath):
        for filename in fnmatch.filter(filenames, '*.tif'):
            matches.append(os.path.join(root, filename))
    return sorted(matches)


def _output_profile(paths):
    """Profile for the merged output, taken from the first input tile."""
    with rasterio.open(paths[0]) as src:
        profile = src.profile.copy()
    profile.update(driver='GTiff')
    return profile


def _merge_to(paths, outpath):
    """Merge `paths` into `outpath`, streaming to disk.

    The source paths are handed to rasterio directly rather than pre-opened:
    opening every tile up front exhausts the file-descriptor limit on any
    realistically sized tile set.
    """
    profile = _output_profile(paths)
    rasterio_merge(
        paths,
        nodata=0,
        method=MERGE_METHOD,
        dst_path=outpath,
        dst_kwds=profile,
        mem_limit=MEM_LIMIT_MB,
    )
    # rasterio.merge sets out_profile["nodata"] from the fill value, so the
    # tag has to be cleared afterwards; dst_kwds cannot override it. We want
    # the zero fill of `gdal_merge.py -init 0` without declaring 0 to be
    # no-data, which would mask every sea-level pixel downstream.
    with rasterio.open(outpath, 'r+') as dst:
        dst.nodata = None


def merge_tiles(paths, outpath):
    """Merge `paths` into `outpath`.

    nodata=0 reproduces `gdal_merge.py -init 0`: gaps between tiles are
    filled with zero rather than left undefined.
    """
    _merge_to(paths, outpath)


def scale_tiles(paths, outpath, smin, smax):
    """Merge and linearly rescale to 8-bit.

    Reproduces `gdal_translate -of GTiff -ot Byte -scale <min> <max> 0 255`:
    values are clipped to [smin, smax] and mapped onto 0-255.

    Merges to a temporary file and rescales window by window, so neither the
    merged raster nor its rescaled copy has to fit in memory. This mirrors
    the old two-step pipeline, which streamed through a temp .tif.
    """
    span = float(smax) - float(smin)
    if span == 0:
        raise ValueError('--scale min and max must differ')

    fd, tmppath = tempfile.mkstemp(suffix='.tif')
    os.close(fd)
    try:
        _merge_to(paths, tmppath)
        with rasterio.open(tmppath) as src:
            profile = src.profile.copy()
            profile.update(driver='GTiff', dtype='uint8', nodata=None)
            with rasterio.open(outpath, 'w', **profile) as dst:
                for _ji, window in src.block_windows(1):
                    block = src.read(window=window).astype('float64')
                    scaled = (block - float(smin)) / span * 255.0
                    scaled = np.clip(scaled, 0, 255)
                    # floor(x + 0.5), not np.round: numpy rounds halves to
                    # even (62.5 -> 62), while gdal_translate's float-to-Byte
                    # conversion rounds halves away from zero (62.5 -> 63).
                    scaled = np.floor(scaled + 0.5).astype('uint8')
                    dst.write(scaled, window=window)
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass


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
