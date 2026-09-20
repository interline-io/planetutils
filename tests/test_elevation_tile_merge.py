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
        # Exact, not approximate: 10 over 0-40 is 63.75, which must round to
        # 64 as gdal_translate does. An abs=1 tolerance here would accept the
        # truncated 63 and hide the regression.
        assert a[0, 0] == 64
        assert a[SIZE, 0] == 128         # 20 -> 127.5 -> 128
        assert a[SIZE, SIZE] == 255      # 40 -> 255

    def test_rounds_rather_than_truncates(self, tmp_path):
        """gdal_translate rounds float values into Byte; astype() truncates."""
        d = tmp_path / 'in'
        d.mkdir()
        write_tile(d / 'a.tif', 0, SIZE * PIXEL, 10.0)
        out = tmp_path / 'out8.tif'
        elevation_tile_merge.scale_tiles(
            elevation_tile_merge.find_tiles(str(d)), str(out), '0', '40')
        with rasterio.open(str(out)) as ds:
            assert ds.read(1)[0, 0] == 64     # 63.75 rounds up, not down to 63

    def test_clips_out_of_range_values(self, tile_block, tmp_path):
        out = tmp_path / 'out8.tif'
        elevation_tile_merge.scale_tiles(
            elevation_tile_merge.find_tiles(str(tile_block)), str(out),
            '0', '20')
        with rasterio.open(str(out)) as d:
            a = d.read(1)
        assert a[SIZE, SIZE] == 255      # 40 clipped to the 20 ceiling
        assert a[0, 0] == 128            # 10 over 0-20 is 127.5 -> 128

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


class TestGdalCompatibility:
    """Behaviors that must match the gdal_merge.py / gdal_translate pipeline
    this replaced. Each was a real divergence found in review."""

    def test_nodata_tag_is_not_set(self, tile_block, tmp_path):
        """`gdal_merge.py -init 0` fills gaps with zero but leaves the nodata
        tag unset. Tagging 0 as nodata would mark every sea-level pixel as
        missing for downstream consumers.

        Note rasterio.merge sets out_profile["nodata"] from the fill value,
        so dst_kwds cannot override this; it must be cleared after the merge.
        """
        out = tmp_path / 'out.tif'
        elevation_tile_merge.merge_tiles(
            elevation_tile_merge.find_tiles(str(tile_block)), str(out))
        with rasterio.open(str(out)) as d:
            assert d.nodata is None

    def test_gaps_are_still_zero_filled(self, tmp_path):
        d = tmp_path / 'in'
        d.mkdir()
        span = SIZE * PIXEL
        write_tile(d / 'a.tif', 0, span * 2, 5.0)
        write_tile(d / 'b.tif', span, span, 7.0)      # diagonal neighbour
        out = tmp_path / 'out.tif'
        elevation_tile_merge.merge_tiles(
            elevation_tile_merge.find_tiles(str(d)), str(out))
        with rasterio.open(str(out)) as ds:
            assert ds.read(1)[0, SIZE] == 0.0
            assert ds.nodata is None

    def test_overlapping_tiles_last_one_wins(self, tmp_path):
        """gdal_merge.py copied each input over the output in sequence, so
        the last file covering a pixel won. rasterio defaults to "first"."""
        d = tmp_path / 'in'
        d.mkdir()
        write_tile(d / 'a.tif', 0, SIZE * PIXEL, 5.0)
        write_tile(d / 'b.tif', 0, SIZE * PIXEL, 7.0)   # fully overlapping
        out = tmp_path / 'out.tif'
        paths = elevation_tile_merge.find_tiles(str(d))
        assert paths[0].endswith('a.tif')               # ordering is defined
        elevation_tile_merge.merge_tiles(paths, str(out))
        with rasterio.open(str(out)) as ds:
            assert ds.read(1)[0, 0] == 7.0

    def test_half_values_round_away_from_zero(self, tmp_path):
        """numpy rounds halves to even (62.5 -> 62); gdal_translate rounds
        halves away from zero (62.5 -> 63)."""
        d = tmp_path / 'in'
        d.mkdir()
        # 62.5/255*40 scales back to exactly 62.5 over the 0-40 range.
        write_tile(d / 'a.tif', 0, SIZE * PIXEL, 62.5 / 255 * 40)
        out = tmp_path / 'out8.tif'
        elevation_tile_merge.scale_tiles(
            elevation_tile_merge.find_tiles(str(d)), str(out), '0', '40')
        with rasterio.open(str(out)) as ds:
            assert ds.read(1)[0, 0] == 63

    def test_merges_more_tiles_than_the_fd_limit(self, tmp_path):
        """Opening every tile up front exhausted the descriptor limit on any
        realistic tile set; paths are handed to rasterio to open lazily."""
        resource = pytest.importorskip('resource')
        d = tmp_path / 'in'
        d.mkdir()
        for i in range(400):
            write_tile(d / ('t%03d.tif' % i), i * SIZE * PIXEL, SIZE * PIXEL,
                       float(i))
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
        try:
            elevation_tile_merge.merge_tiles(
                elevation_tile_merge.find_tiles(str(d)),
                str(tmp_path / 'big.tif'))
        finally:
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
        assert (tmp_path / 'big.tif').exists()
