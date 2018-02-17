#!/usr/bin/env python
import os
import csv

def load_bboxes(csvpath):
    # bbox csv format:
    # name, left, bottom, right, top
    if not os.path.exists(csvpath):
        raise Exception('csvpath does not exist: %s'%csvpath)
    bboxes = []
    with open(csvpath) as f:
        reader = csv.reader(f)
        for row in reader:
            name = row[0]
            left, bottom, right, top = map(float, row[1:])
            assert top >= bottom
            assert right >= left
            bboxes.append([name, left, bottom, right, top])
    return bboxes
