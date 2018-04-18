#!/usr/bin/env python
import os
import argparse

import tilepack
from bbox import bbox_string, load_bboxes_csv

def main():
    parser = argparse.ArgumentParser(usage="List Valhalla Tilepacks.")
    args = parser.parse_args()
    tp = tilepack.Tilepack()
    tp.list()

if __name__ == '__main__':
    main()
