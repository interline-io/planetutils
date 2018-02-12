#!/usr/bin/env python
import os
import csv
import argparse
import subprocess

# bbox csv format:
# name, top, left, bottom, right

def load_bboxes(csvpath):
    if not os.path.exists(csvpath):
        raise Exception('csvpath does not exist: %s'%csvpath)
    bboxes = []
    with open(csvpath) as f:
        reader = csv.reader(f)
        for row in reader:
            bboxes.append(row)
    return bboxes

def extract_bboxes(osmpath, bboxes, workers=2):
    if not os.path.exists(osmpath):
        raise Exception('osmpath does not exist: %s'%osmpath)
    args = ["osmosis"]
    args += ['--read-pbf-fast', osmpath, 'workers=%s'%int(workers)]
    args += ['--tee', str(len(bboxes))]
    for name,top,left,bottom,right in bboxes:
        arg = [
            "--bounding-box",
            'top=%0.5f'%float(top),
            'left=%0.5f'%float(left),
            'bottom=%0.5f'%float(bottom),
            'right=%0.5f'%float(right),
            '--write-pbf',
            '%s.osm.pbf'%name
        ]
        args += arg
    print " ".join(args)
    subprocess.check_output(args, shell=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("osmpath", help="osm path")
    parser.add_argument("csvpath", help="csv path with bbox definitions")
    args = parser.parse_args()
    extract_bboxes(args.osmpath, load_bboxes(args.csvpath))
