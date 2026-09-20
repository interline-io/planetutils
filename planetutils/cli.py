"""Shared CLI helpers."""
import functools
import sys

from .planet import MissingBinaryError


def handle_missing_binary(main):
    """Report a missing external tool as a clean message, not a traceback.

    osm_planet_extract still needs osmium-tool, osmosis or osmctools; a user
    without one should see how to install it, with exit status 1.
    """
    @functools.wraps(main)
    def wrapper(*args, **kwargs):
        try:
            return main(*args, **kwargs)
        except MissingBinaryError as e:
            print('error: %s' % e, file=sys.stderr)
            sys.exit(1)
    return wrapper
