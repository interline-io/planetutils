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
    output_path,
)

SOURCES = ('interline', 'geofabrik', 'sliceosm')


class SourceParser(argparse.ArgumentParser):
    """Adds a migration hint when SOURCE is missing or not a source.

    Before 1.0.0 there was no source: osm_extract_download --api-token=abcd us-ca
    """
    argv = None

    def error(self, message):
        if self.argv and 'SOURCE' in message:
            message = (
                'a source is now required: %s. The old form is now: '
                'osm_extract_download interline %s (changed in 1.0.0)' % (
                    ', '.join(SOURCES), ' '.join(redact_token(self.argv))))
        super().error(message)


def redact_token(argv):
    redacted, hide_next = [], False
    for arg in argv:
        if hide_next:
            arg, hide_next = '...', False
        elif arg == '--api-token':
            hide_next = True
        elif arg.startswith('--api-token='):
            arg = '--api-token=...'
        redacted.append(arg)
    return redacted


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--outpath', help='Output directory; files are named <id>.osm.pbf', default='.')
    common.add_argument('--overwrite', help='Replace output files that already exist', action='store_true')
    common.add_argument('--verbose', help="Verbose output", action='store_true')

    parser = SourceParser(
        description='Download OSM extracts in PBF format.',
        epilog='Run "osm_extract_download SOURCE -h" for help on each source.')
    sources = parser.add_subparsers(dest='source', metavar='SOURCE', required=True,
                                    parser_class=argparse.ArgumentParser)

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
    p.add_argument('--timeout', help='Seconds to wait for the extract to be prepared', type=int, default=SliceOsmDownloader.DEFAULT_TIMEOUT)
    return parser


# OSError covers the filesystem: an unwritable --outpath, a full disk.
@handle_cli_errors(ExtractDownloadError, OSError)
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    parser.argv = argv
    args = parser.parse_args(argv)

    if args.verbose:
        log.set_verbose()

    if args.source == 'interline':
        outpath = output_path(args.outpath, args.id, args.overwrite)
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
        outpath = output_path(args.outpath, downloader.name(args.id), args.overwrite)
        downloader.download(args.id, outpath)

    elif args.source == 'sliceosm':
        extents = load_extents(args, parser)
        # One area per run, to go easy on SliceOSM's volunteer-run service.
        if len(extents) != 1:
            parser.error(
                'sliceosm downloads one area per run, and %s were given; pick one '
                'with --ids. Heavy automated use of SliceOSM is not permitted. For '
                'many areas, download a planet or Geofabrik region and cut it with '
                'osm_planet_extract.' % len(extents))
        (name, feature), = extents.items()
        outpath = output_path(args.outpath, name, args.overwrite)
        SliceOsmDownloader().download(name, feature, outpath, timeout=args.timeout)

if __name__ == '__main__':
    main()
