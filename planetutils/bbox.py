#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals
import json
import os
import csv

def flatcoords(coords, fc=None):
    if fc is None:
        fc = []
    try:
        coords[0][0] # check if iterable of iterables
        for c in coords:
            flatcoords(c, fc)
    except:
        fc.append(coords)
    return fc

class Feature(object):
    def __init__(self, properties=None, geometry=None, **kwargs):
        self.properties = properties or {}
        self.geometry = geometry or {}
        if not self.geometry:
            self.set_bbox([0.0, 0.0, 0.0, 0.0])

    def bbox(self):
        gt = self.geometry.get('type')
        coords = self.geometry.get('coordinates', [])
        fc = flatcoords(coords)
        lons = [i[0] for i in fc]
        lats = [i[1] for i in fc]
        left, right = min(lons), max(lons)
        bottom, top = min(lats), max(lats)
        return validate_bbox([left, bottom, right, top])

    def set_bbox(self, bbox):
        left, bottom, right, top = validate_bbox(bbox)
        self.geometry = {
            "type": "LineString",
            "coordinates": [
                [left, bottom],
                [right, top],
            ]
        }

    def is_rectangle(self):
        fc = flatcoords(self.geometry.get('coordinates', []))
        lons = set([i[0] for i in fc])
        lats = set([i[1] for i in fc])
        return len(lons) <= 2 and len(lats) <= 2

    # act like [left, bottom, right, top]
    def __getitem__(self, item):
        return self.bbox()[item] 


def validate_bbox(bbox):
    left, bottom, right, top = map(float, bbox)
    assert -180 <= left <= 180
    assert -180 <= right <= 180
    assert -90 <= bottom <= 90
    assert -90 <= top <= 90
    assert top >= bottom
    assert right >= left
    return [left, bottom, right, top]

def load_feature_string(bbox):
    f = Feature()
    f.set_bbox(bbox.split(','))
    return f
    
def load_features_csv(csvpath):
    # bbox csv format:
    # name, left, bottom, right, top
    if not os.path.exists(csvpath):
        raise Exception('file does not exist: %s'%csvpath)
    bboxes = {}
    with open(csvpath) as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) != 5:
                raise Exception('5 columns required')
            f = Feature()
            f.set_bbox(row[1:])
            bboxes[row[0]] = f
    return bboxes

def load_features_geojson(path):
    if not os.path.exists(path):
        raise Exception('file does not exist: %s'%path)
    with open(path) as f:
        data = json.load(f)
    features = data.get('features', [])
    bboxes = {}
    for count,feature in enumerate(features):
        key = feature.get('properties',{}).get('id') or feature.get('id') or count
        bboxes[key] = Feature(**feature)
    return bboxes
