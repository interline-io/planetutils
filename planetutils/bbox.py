#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals
import json
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
        raise Exception('file does not exist: %s'%csvpath)
    bboxes = {}
    with open(csvpath) as f:
        reader = csv.reader(f)
        for row in reader:
            bboxes[row[0]] = validate_bbox(row[1:])
    return bboxes

def load_bboxes_geojson(path):
    if not os.path.exists(path):
        raise Exception('file does not exist: %s'%path)
    with open(path) as f:
        data = json.load(f)
    return feature_bboxes(data.get('features',[]))

def feature_bboxes(features):
    bboxes = {}
    for count,feature in enumerate(features):
        key = feature.get('properties',{}).get('id') or feature.get('id') or count
        bbox = feature_bbox(feature)
        bboxes[key] = bbox
    return bboxes

def feature_bbox(feature):
    g = feature.get('geometry',{})
    if g.get('type') != 'Polygon':
        raise Exception('Only Polygon geometries are supported')
    coords = g.get('coordinates',[])[0]
    lons = [i[0] for i in coords]
    lats = [i[1] for i in coords]
    left, right = min(lons), max(lons)
    bottom, top = min(lats), max(lats)
    return validate_bbox([left, bottom, right, top])