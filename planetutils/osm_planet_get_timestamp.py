#!/usr/bin/env python
import argparse
from planet import *
import log

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('osmpath', help='OSM file')
    args = parser.parse_args()
    p = Planet(args.osmpath)
    log.set_quiet()
    print p.get_timestamp()

if __name__ == '__main__':
    main()
