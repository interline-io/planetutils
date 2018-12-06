from __future__ import absolute_import, unicode_literals
import tempfile
import types
import os
import unittest

class TestCommandImports(unittest.TestCase):
    def test_command_imports(self):
        commands = [
            'osm_planet_update=planetutils.osm_planet_update:main',
            'osm_planet_extract=planetutils.osm_planet_extract:main',
            'osm_planet_get_timestamp=planetutils.osm_planet_get_timestamp:main',
            'osm_extract_download=planetutils.osm_extract_download:main',
            'elevation_tile_download=planetutils.elevation_tile_download:main',
            'elevation_tile_merge=planetutils.elevation_tile_merge:main',
            'valhalla_tilepack_download=planetutils.tilepack_download:main',
            'valhalla_tilepack_list=planetutils.tilepack_list:main'
        ]
        for i in commands:
            a, _, b = i.partition('=')[-1].partition(':')
            exec('import %s'%(a))
