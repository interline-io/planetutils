import tempfile
import os
import unittest
import planetutils.bbox as bbox

CA = [-126.38,32.15,-113.53,42.24]

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
        self.assertEquals(bbox.validate_bbox([1,2,3,4]), [1.0, 2.0, 3.0, 4.0])

class TestLoadBboxesCsv(unittest.TestCase):
    def test_load(self):
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write("%s,%0.2f,%0.2f,%0.2f,%0.2f"%(
            'CA',
            CA[0], CA[1], CA[2], CA[3]
        ))
        f.close()
        self.assertEquals(bbox.load_bboxes_csv(f.name)['CA'], CA)

class TestBboxString(unittest.TestCase):
    def test_returns_array(self):
        self.assertEquals(bbox.bbox_string('1.0,2.0,3.0,4.0'), [1.0,2.0,3.0,4.0])
    
    def test_validates(self):
        self.assertRaises(AssertionError, bbox.bbox_string, ('10,-10,20,-20'))

if __name__ == '__main__':
    unittest.main()
