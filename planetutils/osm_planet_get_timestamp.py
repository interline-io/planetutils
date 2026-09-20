#!/usr/bin/env python
import argparse

from . import log
from .cli import handle_missing_binary
from .planet import Planet


@handle_missing_binary
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='OSM file')
    args = parser.parse_args()
    p = Planet(args.osmpath)
    log.set_quiet()
    print(p.get_timestamp())

if __name__ == '__main__':
    main()
