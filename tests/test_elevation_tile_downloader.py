from __future__ import absolute_import, unicode_literals
import tempfile
import os
import types
import unittest

from planetutils.elevation_tile_downloader import ElevationTileDownloader

CA = [-126.386719,32.157012,-113.532715,42.244785]

class TestElevationTileDownloader(unittest.TestCase):
    def test_download_bboxes(self):
        pass
        
    def test_hgtpath(self):
        e = ElevationTileDownloader('.')
        expect = ('N122', 'N122E037.hgt')
        hgtpath = e.hgtpath(37, 122)
        self.assertEqual(hgtpath[0], expect[0])
        self.assertEqual(hgtpath[1], expect[1])
    
    def test_get_bbox_tiles(self):
        e = ElevationTileDownloader('.')
        tiles = e.get_bbox_tiles(CA)
        self.assertEqual(len(tiles), 154)
        tiles = e.get_bbox_tiles([-180,-90,180,90])
        self.assertEqual(len(tiles), 64800)
    
    def download_bbox(self, e, method, args, expect):
        COUNT = []
        def c(self, bucket, prefix, x, y):
            COUNT.append([x,y])
        e.download_hgt = types.MethodType(c, ElevationTileDownloader)
        method(*args)
        self.assertEqual(len(COUNT), expect)
    
    def test_download_planet(self):
        e = ElevationTileDownloader('.')
        self.download_bbox(e, e.download_planet, [], 64800)
    
    def test_download_bbox(self):
        e = ElevationTileDownloader('.')
        self.download_bbox(e, e.download_bbox, [CA], 154)
    
    def test_download_bbox_found(self):
        d = tempfile.mkdtemp()
        e = ElevationTileDownloader(d)
        # correct size
        path = e.hgtpath(-119, 37)
        os.makedirs(os.path.join(d, path[0]))
        dp1 = os.path.join(d, *path)
        with open(dp1, 'w') as f:
            f.write('0'*e.HGT_SIZE)
        # incorrect size
        path = e.hgtpath(-119, 36)
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
