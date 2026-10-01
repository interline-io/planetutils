#!/usr/bin/env python
import argparse
import os
import sys

from . import log
from .cli import add_extent_arguments, handle_cli_errors, load_extents
from .osm_extract_downloader import (
    ExtractDownloadError,
    GeofabrikDownloader,
    InterlineExtractDownloader,
    SliceOsmDownloader,
    check_outpath,
)

SOURCES = ('interline', 'geofabrik', 'sliceosm')


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--outpath', help='Output directory; files are named <id>.osm.pbf', default='.')
    common.add_argument('--overwrite', help='Replace output files that already exist', action='store_true')
    common.add_argument('--verbose', help="Verbose output", action='store_true')

    parser = argparse.ArgumentParser(
        description='Download OSM extracts in PBF format.',
        epilog='Run "osm_extract_download SOURCE -h" for help on each source.')
    sources = parser.add_subparsers(dest='source', metavar='SOURCE', required=True)

    p = sources.add_parser(
        'interline', parents=[common],
        help='the regions OSM Extracts by Interline still publishes (API token required)')
    p.add_argument('id', help='Extract ID, e.g. us-ca')
    p.add_argument('--api-token', help='Interline API token; default is read from $INTERLINE_API_TOKEN')

    p = sources.add_parser(
        'geofabrik', parents=[common],
        help='countries and regions from download.geofabrik.de, updated daily')
    p.add_argument('id', nargs='?', help='Geofabrik region ID, e.g. us/california or berlin')
    p.add_argument('--list', help='List region IDs instead of downloading', action='store_true')
    p.add_argument('--search', help='List region IDs whose ID or name contains this text')

    p = sources.add_parser(
        'sliceosm', parents=[common],
        help='any area, on demand, from slice.openstreetmap.us (operated by OSM US; '
             'heavy automated use is not permitted)')
    add_extent_arguments(p, name_help='Name for the extract given by --bbox.')
    p.add_argument('--timeout', help='Seconds to wait for each extract to be prepared', type=int, default=1800)
    return parser


@handle_cli_errors(ExtractDownloadError)
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    if argv and not argv[0].startswith('-') and argv[0] not in SOURCES:
        parser.error(
            'the first argument is now the source: %s. For example: '
            'osm_extract_download interline %s (changed in 1.0.0)' % (
                ', '.join(SOURCES), argv[0]))
    args = parser.parse_args(argv)

    if args.verbose:
        log.set_verbose()

    if args.source == 'interline':
        outpath = os.path.join(args.outpath, '%s.osm.pbf' % args.id)
        check_outpath(outpath, args.overwrite)
        InterlineExtractDownloader().download(
            args.id, outpath, api_token=args.api_token or os.getenv('INTERLINE_API_TOKEN'))

    elif args.source == 'geofabrik':
        downloader = GeofabrikDownloader()
        if args.list or args.search:
            for region in downloader.search(args.search):
                print('%s\t%s' % (region['id'], region.get('name', '')))
            return
        if not args.id:
            parser.error('geofabrik needs a region ID, or --list or --search to find one')
        outpath = os.path.join(args.outpath, downloader.filename(args.id))
        check_outpath(outpath, args.overwrite)
        downloader.download(args.id, outpath)

    elif args.source == 'sliceosm':
        extents = load_extents(args, parser)
        if len(extents) > SliceOsmDownloader.MAX_EXTENTS:
            parser.error(
                '%s extents requested; sliceosm takes at most %s per run. Heavy '
                'automated use of SliceOSM is not permitted. For many areas, '
                'download a planet or Geofabrik region and cut it with '
                'osm_planet_extract.' % (len(extents), SliceOsmDownloader.MAX_EXTENTS))
        outpaths = {name: os.path.join(args.outpath, '%s.osm.pbf' % name) for name in extents}
        # Check every output before submitting any work to SliceOSM.
        for outpath in outpaths.values():
            check_outpath(outpath, args.overwrite)
        downloader = SliceOsmDownloader()
        for name, feature in extents.items():
            downloader.download(name, feature, outpaths[name], timeout=args.timeout)

if __name__ == '__main__':
    main()
