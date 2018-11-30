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
        self.assertEqual(bbox.validate_bbox([1,2,3]), [1.0, 2.0, 3.0, 4.0])

class TestLoadBboxesCsv(unittest.TestCase):
    def test_load(self):
        f = tempfile.NamedTemporaryFile(delete=False, mode='w')
        f.write("%s,%0.2f,%0.2f,%0.2f,%0.2f"%(
            'CA',
            CA[0], CA[1], CA[2], CA[3]
        ))
        f.close()
        self.assertEqual(bbox.load_bboxes_csv(f.name)['CA'], CA)

class TestBboxString(unittest.TestCase):
    def test_returns_array(self):
        self.assertEqual(bbox.bbox_string('1.0,2.0,3.0,4.0'), [1.0,2.0,3.0,4.0])

    def test_validates(self):
        self.assertRaises(AssertionError, bbox.bbox_string, ('10,-10,20,-20'))

class TestLoadBboxGeojson(unittest.TestCase):
    def test_load(self):
        bboxes = bbox.load_bboxes_geojson(TESTGEOJSON)
        union = (-122.42400169372557, 37.7860125252054, -122.40559101104735, 37.7985943621788)
        pentagon = (-122.39975452423094, 37.78370618798191, -122.38949775695801, 37.791879793952084)
        for a,b in zip(bboxes['union'], union):
            self.assertAlmostEqual(a,b)
        for a,b in zip(bboxes['pentagon'], pentagon):
            self.assertAlmostEqual(a,b)

if __name__ == '__main__':
    unittest.main()
