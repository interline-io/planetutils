#!/usr/bin/env python
import os
import csv

def validate_bbox(bbox):
    left, bottom, right, top = map(float, bbox)
    assert -180 <= left <= 180
    assert -180 <= right <= 180
    assert -90 <= bottom <= 90
    assert -90 <= top <= 90
    assert top >= bottom
    assert right >= left
    return [left, bottom, right, top]

def bbox_string(bbox):
    return validate_bbox(bbox.split(','))

def load_bboxes_csv(csvpath):
    # bbox csv format:
    # name, left, bottom, right, top
    if not os.path.exists(csvpath):
        raise Exception('csvpath does not exist: %s'%csvpath)
    bboxes = {}
    with open(csvpath) as f:
        reader = csv.reader(f)
        for row in reader:
            bboxes[row[0]] = validate_bbox(row[1:])
    return bboxes
