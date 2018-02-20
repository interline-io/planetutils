import tempfile
import os
import unittest
import planetutils.planet as planet

TESTFILE = os.path.join('.','examples','san-francisco-downtown.osm.pbf')
TESTFILE_TIMESTAMP = '2018-02-02T22:34:43Z'
TEST_BBOX = [-122.430439,37.766508,-122.379670,37.800052]

class TestPlanetBase(unittest.TestCase):
    def test_osmosis(self):
        p = planet.PlanetBase(TESTFILE)
        output = p.osmosis(
            '--read-pbf', TESTFILE,
            '--tf', 'accept-ways', 'highway=pedestrian',
            '--write-xml','-'
        )
        self.assertTrue(output.count('way id=') > 0)
    
    def test_osmconvert(self):
        p = planet.PlanetBase(TESTFILE)
        output = p.osmconvert(p.osmpath, '--out-statistics')
        self.assertIn('timestamp min:', output)
    
    def test_get_timestamp(self):
        p = planet.PlanetBase(TESTFILE)
        self.assertEquals(p.get_timestamp(), TESTFILE_TIMESTAMP)

    def test_extract_bbox(self, name=None, bbox=None):
        name = name or 'test'
        bbox = bbox or TEST_BBOX
        d = tempfile.mkdtemp()
        p = planet.PlanetBase(TESTFILE)
        outfile = os.path.join(d, '%s.osm.pbf'%name)
        p.extract_bbox(name, bbox, outpath=d)
        self.assertTrue(os.path.exists(outfile))
        p2 = planet.PlanetBase(outfile)
        self.assertEquals(p2.get_timestamp(), TESTFILE_TIMESTAMP)
        os.unlink(outfile)
        os.rmdir(d)
        
if __name__ == '__main__':
    unittest.main()
