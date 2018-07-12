#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals, print_function
import argparse
from .planet import *
from . import log

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='OSM file')
    args = parser.parse_args()
    p = Planet(args.osmpath)
    log.set_quiet()
    print(p.get_timestamp())

if __name__ == '__main__':
    main()
