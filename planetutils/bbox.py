#!/usr/bin/env python
import csv
import json
import os


def flatcoords(coords, fc=None):
    if fc is None:
        fc = []
    try:
        coords[0][0] # check if iterable of iterables
        for c in coords:
            flatcoords(c, fc)
    except (TypeError, IndexError):
        fc.append(coords)
    return fc

class Feature:
    def __init__(self, properties=None, geometry=None, **kwargs):
        self.properties = properties or {}
        self.geometry = geometry or {}
        if not self.geometry:
            self.set_bbox([0.0, 0.0, 0.0, 0.0])

    def bbox(self):
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
        """Whether this extent is exactly its bounding box.

        A Polygon is a rectangle only if it is axis-aligned: one ring with
        exactly the four corners of its bounding box, and no holes. Counting
        distinct coordinates is not enough: a right triangle such as (0,0)
        (1,0) (0,1) has only two of each. A MultiPolygon is never a
        rectangle, even when it holds a single axis-aligned one; it is
        always cut along its boundary, which gives the same result. Any
        other geometry -- the LineString that set_bbox() builds, a Point --
        stands for its bounding box.
        """
        gtype = self.geometry.get('type')
        if gtype == 'MultiPolygon':
            return False
        if gtype != 'Polygon':
            return True
        rings = self.geometry.get('coordinates', [])
        if len(rings) != 1:
            # No exterior ring, or a hole in it.
            return False
        ring = [tuple(p[:2]) for p in rings[0]]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) != 4:
            return False
        lons = sorted({p[0] for p in ring})
        lats = sorted({p[1] for p in ring})
        if len(lons) != 2 or len(lats) != 2:
            return False
        corners = {(x, y) for x in lons for y in lats}
        if set(ring) != corners:
            return False
        # Walking the ring, each step must move along exactly one axis: a
        # step across the diagonal draws a self-intersecting bowtie.
        return all((a[0] == b[0]) != (a[1] == b[1])
                   for a, b in zip(ring, ring[1:] + ring[:1], strict=True))

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
    with open(csvpath, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) != 5:
                raise Exception('5 columns required')
            f = Feature()
            f.set_bbox(row[1:])
            bboxes[row[0]] = f
    return bboxes

def load_features_poly(path):
    """Load extents from an Osmosis .poly file.

    https://wiki.openstreetmap.org/wiki/Osmosis/Polygon_Filter_File_Format

    The file opens with a name line, then one or more polygon sections: a
    section name, coordinate lines given as `longitude latitude`, and END.
    A final END closes the file. A section name prefixed with `!` subtracts
    that ring from the area, which maps onto a GeoJSON interior ring.

    Coordinates are conventionally in scientific notation, but the format is
    flexible about it, so float() does the parsing.

    Every section becomes one Feature keyed by the file's name line, so a
    multi-section file produces a single named extract -- matching how
    osmium and osmosis treat these files.
    """
    if not os.path.exists(path):
        raise Exception('file does not exist: %s'%path)
    with open(path, encoding='utf-8') as f:
        lines = [line.strip() for line in f]

    # Drop blank lines: multi-section files separate sections with them.
    lines = [line for line in lines if line]
    if not lines:
        raise Exception('empty poly file: %s'%path)

    name = lines.pop(0)
    # Each polygon is [outer, *holes]. A `!` section cuts the ring it
    # follows, which is the format's convention, so holes attach to the most
    # recent outer rather than all landing on the first.
    polygons = []
    while lines:
        section = lines.pop(0)
        if section == 'END':
            break
        is_hole = section.startswith('!')
        ring = []
        while lines:
            line = lines.pop(0)
            if line == 'END':
                break
            parts = line.split()
            if len(parts) < 2:
                raise Exception(
                    'invalid coordinate line in %s: %r'%(path, line))
            try:
                lon, lat = float(parts[0]), float(parts[1])
            except ValueError:
                raise Exception(
                    'invalid coordinate line in %s: %r'%(path, line)) from None
            ring.append([lon, lat])
        else:
            raise Exception('unterminated section %r in %s'%(section, path))
        # Count distinct points, not lines: an already-closed ring of three
        # lines has only two corners, and would otherwise pass as a polygon
        # that is really a line segment.
        if len({tuple(point) for point in ring} ) < 3:
            raise Exception(
                'section %r in %s needs at least 3 distinct points'
                % (section, path))
        # The closing point may be omitted; GeoJSON requires it.
        if ring[0] != ring[-1]:
            ring.append(list(ring[0]))
        if is_hole:
            if not polygons:
                raise Exception(
                    'hole section %r precedes any polygon in %s'
                    % (section, path))
            polygons[-1].append(ring)
        else:
            polygons.append([ring])

    if not polygons:
        raise Exception('no polygons found in %s'%path)

    if len(polygons) == 1:
        geometry = {'type': 'Polygon', 'coordinates': polygons[0]}
    else:
        geometry = {'type': 'MultiPolygon', 'coordinates': polygons}

    return {name: Feature(geometry=geometry)}

def load_features_geojson(path):
    if not os.path.exists(path):
        raise Exception('file does not exist: %s'%path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    # check if this is a single feature
    if data.get('type') == 'FeatureCollection':
        features = data.get('features', [])
    else:
        features = [data]
    bboxes = {}
    for count,feature in enumerate(features):
        key = feature.get('properties',{}).get('id') or feature.get('id') or count
        bboxes[key] = Feature(**feature)
    return bboxes
