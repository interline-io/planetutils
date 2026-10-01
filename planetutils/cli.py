"""Shared CLI helpers."""
import functools
import sys

from . import bbox
from .planet import MissingBinaryError, PlanetPathError


def handle_cli_errors(*exceptions):
    """Report the given exceptions as a clean message, not a traceback.

    Exits 1 with `error: <message>` on stderr.
    """
    if not exceptions:
        raise ValueError('at least one exception type is required')

    def decorator(main):
        @functools.wraps(main)
        def wrapper(*args, **kwargs):
            try:
                return main(*args, **kwargs)
            except exceptions as e:
                print('error: %s' % e, file=sys.stderr)
                sys.exit(1)
        return wrapper
    return decorator


def handle_missing_binary(main):
    """Report a missing external tool, or an unusable planet path, as a
    clean message rather than a traceback.

    osm_planet_extract still needs osmium-tool, osmosis or osmctools; a user
    without one should see how to install it, with exit status 1.
    """
    return handle_cli_errors(MissingBinaryError, PlanetPathError)(main)


def add_extent_arguments(parser, name_help='Name to give to extract file.'):
    """The --csv/--geojson/--poly/--bbox/--name/--ids options for naming
    extents, shared by the commands that take them."""
    parser.add_argument('--csv', help='Path to CSV file with bounding box definitions.')
    parser.add_argument('--geojson', help='Path to GeoJSON file: bbox for each feature is extracted.')
    parser.add_argument('--poly', help='Path to Osmosis .poly file.')
    parser.add_argument('--name', help=name_help)
    parser.add_argument('--bbox', help='Bounding box for extract file. Format for coordinates: left,bottom,right,top')
    parser.add_argument('--ids', help='Comma-separated extract names to cut from the --csv, --geojson or --poly file; default is every extent in the file')


def load_extents(args, parser):
    """Load the extents named by add_extent_arguments' options."""
    if not (args.csv or args.geojson or args.poly or (args.bbox and args.name)):
        parser.error('must specify --csv, --geojson, --poly, or --bbox and --name')
    # The loaders signal a missing file or bad content with plain Exception,
    # and validate_bbox with AssertionError; report either as a usage error
    # rather than a traceback.
    try:
        if args.csv:
            bboxes = bbox.load_features_csv(args.csv)
        elif args.geojson:
            bboxes = bbox.load_features_geojson(args.geojson)
        elif args.poly:
            bboxes = bbox.load_features_poly(args.poly)
        else:
            bboxes = {args.name: bbox.load_feature_string(args.bbox)}
    except AssertionError:
        parser.error('invalid bounding box: coordinates must be left,bottom,right,top in degrees')
    except Exception as e:
        parser.error('could not load extents: %s' % (e or type(e).__name__))
    if args.ids is not None:
        bboxes = select_ids(bboxes, args.ids, parser)
    return bboxes


def select_ids(bboxes, ids, parser):
    """Keep only the named extents, failing on any name not in the file.

    A misspelled id must not quietly cut nothing: against a planet, that is
    an hour of work with no output.
    """
    # GeoJSON features without an id are keyed by position, so compare as
    # strings.
    by_name = {str(name): name for name in bboxes}
    wanted = [i.strip() for i in ids.split(',') if i.strip()]
    if not wanted:
        parser.error('--ids is empty')
    unknown = [i for i in wanted if i not in by_name]
    if unknown:
        parser.error('--ids not found in the extents file: %s' % ', '.join(unknown))
    return {by_name[i]: bboxes[by_name[i]] for i in wanted}
