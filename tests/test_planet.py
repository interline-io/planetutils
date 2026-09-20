from __future__ import absolute_import, unicode_literals
import tempfile
import types
import os
import unittest
import pytest

import planetutils.planet as planet
from conftest import PLANET_PBF, PLANET_PBF_TIMESTAMP, needs

TESTFILE = str(PLANET_PBF)
TESTFILE_TIMESTAMP = PLANET_PBF_TIMESTAMP
TEST_BBOX = [-122.430439,37.766508,-122.379670,37.800052]

# import planetutils.log as log
# log.set_verbose()

class TestPlanetBase(unittest.TestCase):
    @needs('osmosis')
    def test_osmosis(self):
        p = planet.PlanetBase(TESTFILE)
        output = p.osmosis(
            '--read-pbf', TESTFILE,
            '--tf', 'accept-ways', 'highway=pedestrian',
            '--write-xml','-'
        )
        self.assertTrue(output.count('way id=') > 0)
    
    @needs('osmconvert')
    def test_osmconvert(self):
        p = planet.PlanetBase(TESTFILE)
        output = p.osmconvert(p.osmpath, '--out-statistics')
        self.assertIn('timestamp min:', output)
    
    @needs('osmconvert')
    def test_get_timestamp(self):
        p = planet.PlanetBase(TESTFILE)
        self.assertEqual(p.get_timestamp(), TESTFILE_TIMESTAMP)

class TestPlanetExtractor(unittest.TestCase):
    kls = None
    def extract_bbox(self):
        name = 'test'
        bbox = TEST_BBOX
        d = tempfile.mkdtemp()
        p = self.kls(TESTFILE)
        outfile = os.path.join(d, '%s.osm.pbf'%name)
        p.extract_bbox(name, bbox, outpath=d)
        self.assertTrue(os.path.exists(outfile))
        p2 = planet.PlanetBase(outfile)
        self.assertEqual(p2.get_timestamp(), TESTFILE_TIMESTAMP)
        os.unlink(outfile)
        os.rmdir(d)

class TestPlanetExtractorOsmconvert(TestPlanetExtractor):
    kls = planet.PlanetExtractorOsmconvert
    @needs('osmconvert')
    def test_extract_bbox(self):
        self.extract_bbox()

class TestPlanetExtractorOsmosis(TestPlanetExtractor):
    kls = planet.PlanetExtractorOsmosis
    @needs('osmosis')
    def test_extract_bbox(self):
        self.extract_bbox()

class TestPlanetDownloaderHttp(unittest.TestCase):
    def test_download_planet(self):
        p = planet.PlanetDownloaderHttp('test.osm.pbf')
        # mock curl
        COUNT = []
        def c(self, url, outpath):
            COUNT.append([url,outpath])
        p._download = types.MethodType(c, planet.PlanetDownloaderHttp)
        p.download_planet()
        self.assertEqual(COUNT[0], ['https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf', 'test.osm.pbf'])
        
if __name__ == '__main__':
    unittest.main()
