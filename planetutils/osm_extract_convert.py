#!/usr/bin/env python
import argparse
import os

from . import log
from .cli import handle_missing_binary
from .planet import (
    EXPORT_FORMATS,
    ExtractConverterOsmium,
    PlanetPathError,
    export_output_path,
)


@handle_missing_binary
def main():
    parser = argparse.ArgumentParser(
        description='Convert OSM PBF extracts to GeoJSON or GeoJSONL, '
                    'with the same feature properties that OSM Extracts '
                    'by Interline published.')
    parser.add_argument('osmpath', nargs='+', help='One or more OSM PBF files, e.g. from osm_planet_extract.')
    parser.add_argument('--outpath', help='Output directory; each file is named after its input, e.g. berlin.osm.pbf -> berlin.geojson', default='.')
    parser.add_argument('--format', dest='data_format', help='Output format: geojson (one FeatureCollection) or geojsonl (one Feature per line)', choices=sorted(EXPORT_FORMATS), default='geojson')
    parser.add_argument('--overwrite', help='Replace output files that already exist', action='store_true')
    parser.add_argument('--verbose', help="Verbose output", action='store_true')
    parser.add_argument('--commands', help='Output a command list instead of performing action, e.g. for parallel usage', action='store_true')
    args = parser.parse_args()

    if args.verbose:
        log.set_verbose()

    # Outputs are named by basename, so a/berlin.osm.pbf and b/berlin.osm.pbf
    # would write the same file. Refuse before converting anything.
    outputs = {}
    for osmpath in args.osmpath:
        output = os.path.normcase(os.path.abspath(
            export_output_path(osmpath, args.data_format, outpath=args.outpath)))
        if output in outputs:
            parser.error('%s and %s would both write %s' % (outputs[output], osmpath, output))
        outputs[output] = osmpath

    for osmpath in args.osmpath:
        p = ExtractConverterOsmium(osmpath)
        if args.commands:
            for i in p.convert_commands(data_format=args.data_format, outpath=args.outpath, overwrite=args.overwrite):
                print(" ".join(i))
            continue
        if not os.path.exists(osmpath):
            raise PlanetPathError('file does not exist: %s' % osmpath)
        output = p.convert(data_format=args.data_format, outpath=args.outpath, overwrite=args.overwrite)
        log.info('wrote %s' % output)

if __name__ == '__main__':
    main()
