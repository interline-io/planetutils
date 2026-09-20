from __future__ import absolute_import, unicode_literals
import tempfile
import os
import types
import unittest

from planetutils.elevation_tile_downloader import ElevationSkadiDownloader, ElevationGeotiffDownloader

CA = [-126.386719,32.157012,-113.532715,42.244785]

class TestGeotiffDownloader(unittest.TestCase):
    def test_tile_path(self):
        e = ElevationGeotiffDownloader('.')
        expect = ('0', '37', '122.tif')
        tile_path = e.tile_path(0, 37, 122)
        self.assertEqual(tile_path[0], expect[0])
        self.assertEqual(tile_path[1], expect[1])
        self.assertEqual(tile_path[2], expect[2])

    def test_get_bbox_tiles(self):
        e = ElevationGeotiffDownloader('.', zoom=8)
        tiles = e.get_bbox_tiles(CA)
        self.assertEqual(len(tiles), 100)
        tiles = e.get_bbox_tiles([-180,-90,180,90])
        self.assertEqual(len(tiles), 2**16)

class TestElevationSkadiDownloader(unittest.TestCase):
    def test_download_bboxes(self):
        pass
        
    def test_hgtpath(self):
        e = ElevationSkadiDownloader('.')
        expect = ('N122', 'N122E037.hgt')
        hgtpath = e.tile_path(0, 37, 122)
        self.assertEqual(hgtpath[0], expect[0])
        self.assertEqual(hgtpath[1], expect[1])
    
    def test_get_bbox_tiles(self):
        e = ElevationSkadiDownloader('.')
        tiles = e.get_bbox_tiles(CA)
        self.assertEqual(len(tiles), 154)
        tiles = e.get_bbox_tiles([-180,-90,180,90])
        self.assertEqual(len(tiles), 64800)
    
    def download_bbox(self, e, method, args, expect):
        COUNT = []
        # def c(self, url, op):
        def c(self, bucket, prefix, z, x, y, suffix=''):
            COUNT.append([x, y])
        e.download_tile = types.MethodType(c, ElevationSkadiDownloader)
        method(*args)
        self.assertEqual(len(COUNT), expect)
    
    def test_download_planet(self):
        e = ElevationSkadiDownloader('.')
        self.download_bbox(e, e.download_planet, [], 64800)
    
    def test_download_bbox(self):
        e = ElevationSkadiDownloader('.')
        self.download_bbox(e, e.download_bbox, [CA], 154)
    
    def test_download_bbox_found(self):
        d = tempfile.mkdtemp()
        e = ElevationSkadiDownloader(d)
        # correct size
        path = e.tile_path(0, -119, 37)
        os.makedirs(os.path.join(d, path[0]))
        dp1 = os.path.join(d, *path)
        with open(dp1, 'w') as f:
            f.write('0'*e.HGT_SIZE)
        # incorrect size
        path = e.tile_path(0, -119, 36)
        os.makedirs(os.path.join(d, path[0]))
        dp2 = os.path.join(d, *path)
        with open(dp2, 'w') as f:
            f.write('0')        
        # expect 154 - 1
        self.download_bbox(e, e.download_bbox, [CA], 154-1)
        # cleanup
        for i in [dp1, dp2]:
            os.unlink(i)
        for i in [dp1, dp2]:
            os.rmdir(os.path.dirname(i))
        os.rmdir(d)


class TestDegenerateAndEdgeBboxes(unittest.TestCase):
    """Regression guards for the tile-enumeration edges.

    NOTE: 154 and 64800 are CORRECT, not buggy. For 1-degree Skadi tiles,
    range(floor(left), ceil(right)) is exactly the set of tiles intersecting
    the bbox, and the planet is 360*180 = 64800. The unused `expect` variable
    in get_bbox_tiles holds an over-counting formula (65341) that was
    correctly abandoned -- do not "fix" the loop to match it.
    """

    def test_zero_area_bbox_yields_no_tiles(self):
        e = ElevationSkadiDownloader('.')
        self.assertEqual(len(e.get_bbox_tiles([0, 0, 0, 0])), 0)

    def test_zero_area_bbox_download_is_a_safe_noop(self):
        # The leaked `z` from the enumeration loop is never evaluated here,
        # because the download loop is empty. Guards the cleanup of that name.
        e = ElevationSkadiDownloader('.')
        calls = []
        e.download_tile = lambda *a, **kw: calls.append(a)
        e.download_bbox([0, 0, 0, 0])
        self.assertEqual(calls, [])

    def test_single_degree_bbox_yields_one_tile(self):
        e = ElevationSkadiDownloader('.')
        self.assertEqual(len(e.get_bbox_tiles([0, 0, 1, 1])), 1)

    def test_planet_is_360_by_180(self):
        e = ElevationSkadiDownloader('.')
        self.assertEqual(len(e.get_bbox_tiles([-180, -90, 180, 90])),
                         360 * 180)

    def test_geotiff_zoom_zero_is_a_single_tile(self):
        e = ElevationGeotiffDownloader('.', zoom=0)
        self.assertEqual(len(e.get_bbox_tiles([-180, -85, 180, 85])), 1)
