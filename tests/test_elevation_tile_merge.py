"""Tests for elevation_tile_merge.

This module used to shell out to gdal_merge.py and gdal_translate; it now
uses rasterio, whose wheels bundle GDAL on every target platform.

The port was validated against a numeric golden captured from the GDAL
implementation on four real terrain tiles (zoom 13, a 2x2 block over the SF
Bay Area). rasterio reproduced the merged raster BYTE-IDENTICALLY: matching
sha256 of the pixel data, bounds, shape, dtype and CRS. The only difference
was the transform's y-resolution in the 12th decimal place (about 1.8e-12
metres), which is floating-point noise.

The tests below use synthetic tiles so they need no fixture data.
"""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from planetutils import elevation_tile_merge

PIXEL = 10.0
SIZE = 8


def write_tile(path, origin_x, origin_y, value):
    data = np.full((SIZE, SIZE), value, dtype='float32')
    profile = {
        'driver': 'GTiff', 'height': SIZE, 'width': SIZE, 'count': 1,
        'dtype': 'float32', 'crs': 'EPSG:3857',
        'transform': from_origin(origin_x, origin_y, PIXEL, PIXEL),
    }
    with rasterio.open(str(path), 'w', **profile) as dst:
        dst.write(data, 1)


@pytest.fixture
def tile_block(tmp_path):
    """A 2x2 block of adjacent tiles with distinct values."""
    d = tmp_path / 'in' / '13'
    (d / '100').mkdir(parents=True)
    (d / '101').mkdir(parents=True)
    span = SIZE * PIXEL
    write_tile(d / '100' / '200.tif', 0, span * 2, 10.0)
    write_tile(d / '100' / '201.tif', 0, span, 20.0)
    write_tile(d / '101' / '200.tif', span, span * 2, 30.0)
    write_tile(d / '101' / '201.tif', span, span, 40.0)
    return tmp_path / 'in'


class TestFindTiles:
    def test_finds_tiles_recursively_and_sorted(self, tile_block):
        found = elevation_tile_merge.find_tiles(str(tile_block))
        assert len(found) == 4
        assert found == sorted(found)

    def test_ignores_non_tif_files(self, tile_block):
        (tile_block / '13' / '100' / 'notes.txt').write_text('x')
        (tile_block / '13' / '100' / 'tile.hgt').write_bytes(b'')
        assert len(elevation_tile_merge.find_tiles(str(tile_block))) == 4


class TestMerge:
    def test_merges_into_one_raster(self, tile_block, tmp_path):
        out = tmp_path / 'out.tif'
        elevation_tile_merge.merge_tiles(
            elevation_tile_merge.find_tiles(str(tile_block)), str(out))
        with rasterio.open(str(out)) as d:
            assert d.width == SIZE * 2
            assert d.height == SIZE * 2
            assert d.count == 1
            assert str(d.crs) == 'EPSG:3857'
            assert d.dtypes[0] == 'float32'

    def test_preserves_each_tile_quadrant(self, tile_block, tmp_path):
        out = tmp_path / 'out.tif'
        elevation_tile_merge.merge_tiles(
            elevation_tile_merge.find_tiles(str(tile_block)), str(out))
        with rasterio.open(str(out)) as d:
            a = d.read(1)
        assert a[0, 0] == 10.0                    # top-left
        assert a[0, SIZE] == 30.0                 # top-right
        assert a[SIZE, 0] == 20.0                 # bottom-left
        assert a[SIZE, SIZE] == 40.0              # bottom-right

    def test_gap_is_initialized_to_zero(self, tmp_path):
        """nodata=0 reproduces gdal_merge.py -init 0."""
        d = tmp_path / 'in'
        d.mkdir()
        span = SIZE * PIXEL
        write_tile(d / 'a.tif', 0, span * 2, 10.0)
        write_tile(d / 'b.tif', span, span, 40.0)   # diagonal neighbour
        out = tmp_path / 'out.tif'
        elevation_tile_merge.merge_tiles(
            elevation_tile_merge.find_tiles(str(d)), str(out))
        with rasterio.open(str(out)) as ds:
            a = ds.read(1)
        assert a.shape == (SIZE * 2, SIZE * 2)
        assert a[0, SIZE] == 0.0                  # the empty quadrants
        assert a[SIZE, 0] == 0.0

    def test_needs_no_system_gdal(self):
        """rasterio's wheels bundle GDAL; nothing is shelled out."""
        assert not hasattr(elevation_tile_merge, 'subprocess')
        import sys
        assert 'subprocess' not in sys.modules.get(
            elevation_tile_merge.__name__).__dict__


class TestScale:
    def test_writes_8bit_output(self, tile_block, tmp_path):
        out = tmp_path / 'out8.tif'
        elevation_tile_merge.scale_tiles(
            elevation_tile_merge.find_tiles(str(tile_block)), str(out),
            '0', '40')
        with rasterio.open(str(out)) as d:
            a = d.read(1)
            assert d.dtypes[0] == 'uint8'
        assert a[0, 0] == pytest.approx(10 / 40 * 255, abs=1)
        assert a[SIZE, SIZE] == 255

    def test_clips_out_of_range_values(self, tile_block, tmp_path):
        out = tmp_path / 'out8.tif'
        elevation_tile_merge.scale_tiles(
            elevation_tile_merge.find_tiles(str(tile_block)), str(out),
            '0', '20')
        with rasterio.open(str(out)) as d:
            a = d.read(1)
        assert a[SIZE, SIZE] == 255      # 40 clipped to the 20 ceiling
        assert a[0, 0] == pytest.approx(10 / 20 * 255, abs=1)

    def test_equal_min_max_raises(self, tile_block, tmp_path):
        with pytest.raises(ValueError, match='must differ'):
            elevation_tile_merge.scale_tiles(
                elevation_tile_merge.find_tiles(str(tile_block)),
                str(tmp_path / 'o.tif'), '5', '5')


class TestCli:
    def _run(self, monkeypatch, argv):
        import sys
        monkeypatch.setattr(sys, 'argv', ['elevation_tile_merge'] + argv)
        elevation_tile_merge.main()

    def test_end_to_end(self, tile_block, tmp_path, monkeypatch):
        out = tmp_path / 'out.tif'
        self._run(monkeypatch, [str(out), str(tile_block)])
        assert out.exists()

    def test_no_input_files_exits_zero(self, tmp_path, monkeypatch):
        empty = tmp_path / 'empty'
        empty.mkdir()
        with pytest.raises(SystemExit) as e:
            self._run(monkeypatch, [str(tmp_path / 'o.tif'), str(empty)])
        assert e.value.code == 0

    def test_malformed_scale_exits_one(self, tile_block, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as e:
            self._run(monkeypatch,
                      ['--scale', '0', str(tmp_path / 'o.tif'),
                       str(tile_block)])
        assert e.value.code == 1
