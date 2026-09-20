#!/usr/bin/env python
import argparse

from .tilepack_downloader import TilepackDownloader

def main():
    parser = argparse.ArgumentParser(usage="List Valhalla Tilepacks.")
    args = parser.parse_args()
    downloader = TilepackDownloader()
    downloader.list()

if __name__ == '__main__':
    main()
