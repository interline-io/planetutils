"""Shared CLI helpers."""
import functools
import sys

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
