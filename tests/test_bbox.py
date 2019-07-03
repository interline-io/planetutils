from __future__ import absolute_import, unicode_literals
from builtins import zip
import tempfile
import os
import unittest
import planetutils.bbox as bbox

CA = [-126.38,32.15,-113.53,42.24]
TESTGEOJSON = os.path.join('.','examples','test.geojson')

class TestValidateBbox(unittest.TestCase):
    def test_bounds(self):
        # bounds
        bbox.validate_bbox((-180,-90,180,90))
        bbox.validate_bbox((180,-90,180,90))
        self.assertRaises(AssertionError, bbox.validate_bbox, (-180.1,-90,180,90))
        self.assertRaises(AssertionError, bbox.validate_bbox, (-180,-90.1,180,90))
        self.assertRaises(AssertionError, bbox.validate_bbox, (-180,-90,180.1,90))
        self.assertRaises(AssertionError, bbox.validate_bbox, (-180,-90,180,90.1))
        # left < right, bottom < top
        self.assertRaises(AssertionError, bbox.validate_bbox, (180,0,0,0))
        self.assertRaises(AssertionError, bbox.validate_bbox, (0,0,-180,0))
        self.assertRaises(AssertionError, bbox.validate_bbox, (0,90,0,0))
        self.assertRaises(AssertionError, bbox.validate_bbox, (0,0,0,-90))

    def test_returns_array(self):
        self.assertEqual(bbox.validate_bbox([1,2,3,4]), [1.0, 2.0, 3.0, 4.0])

class TestLoadBboxesCsv(unittest.TestCase):
    def test_load(self):
        f = tempfile.NamedTemporaryFile(delete=False, mode='w')
        f.write("%s,%0.2f,%0.2f,%0.2f,%0.2f"%(
            'CA',
            CA[0], CA[1], CA[2], CA[3]
        ))
        f.close()
        bboxes = bbox.load_features_csv(f.name)
        feat = bboxes['CA']
        self.assertEqual(feat.bbox(), CA)

class TestBboxString(unittest.TestCase):
    def test_returns_array(self):
        feat = bbox.load_feature_string('1.0,2.0,3.0,4.0')
        self.assertEqual(feat.bbox(), [1.0,2.0,3.0,4.0])

    def test_validates(self):
        self.assertRaises(AssertionError, bbox.load_feature_string, ('10,-10,20,-20'))

class TestLoadBboxGeojson(unittest.TestCase):
    def test_load(self):
        feats = bbox.load_features_geojson(TESTGEOJSON)
        union = (-122.42400169372557, 37.7860125252054, -122.40559101104735, 37.7985943621788)
        pentagon = (-122.39975452423094, 37.78370618798191, -122.38949775695801, 37.791879793952084)
        for a,b in zip(feats['union'].bbox(), union):
            self.assertAlmostEqual(a,b)
        for a,b in zip(feats['pentagon'].bbox(), pentagon):
            self.assertAlmostEqual(a,b)

class TestFlatcoords(unittest.TestCase):
    def test_point(self):
        c = [30, 10]
        exp = [[30, 10]]
        self.assertEqual(bbox.flatcoords(c), exp)

    def test_linestring(self):
        c = [
            [30, 10], [10, 30], [40, 40]
        ]
        exp = [[30, 10], [10, 30], [40, 40]]
        self.assertEqual(bbox.flatcoords(c), exp)

    def test_polygon(self):
        c = [
            [[35, 10], [45, 45], [15, 40], [10, 20], [35, 10]], 
            [[20, 30], [35, 35], [30, 20], [20, 30]]
        ]
        fc = bbox.flatcoords(c)
        exp = [[35, 10], [45, 45], [15, 40], [10, 20], [35, 10], [20, 30], [35, 35], [30, 20], [20, 30]]
        self.assertEqual(fc, exp)

    def test_multipoint(self):
        c = [
            [10, 40], [40, 30], [20, 20], [30, 10]
        ]
        fc = bbox.flatcoords(c)
        exp = [[10, 40], [40, 30], [20, 20], [30, 10]]
        self.assertEqual(fc, exp)

    def test_multilinestring(self):
        c = [
            [[10, 10], [20, 20], [10, 40]], 
            [[40, 40], [30, 30], [40, 20], [30, 10]]
        ]
        fc = bbox.flatcoords(c)
        exp = [[10, 10], [20, 20], [10, 40], [40, 40], [30, 30], [40, 20], [30, 10]]
        self.assertEqual(fc, exp)

    def test_multipolygon(self):
        c = [
            [
                [[40, 40], [20, 45], [45, 30], [40, 40]]
            ],
            [
                [[20, 35], [10, 30], [10, 10], [30, 5], [45, 20], [20, 35]],
                [[30, 20], [20, 15], [20, 25], [30, 20]]
            ]
        ]
        fc = bbox.flatcoords(c)
        exp = [[40, 40], [20, 45], [45, 30], [40, 40], [20, 35], [10, 30], [10, 10], [30, 5], [45, 20], [20, 35], [30, 20], [20, 15], [20, 25], [30, 20]]
        self.assertEqual(fc, exp)

if __name__ == '__main__':
    unittest.main()
