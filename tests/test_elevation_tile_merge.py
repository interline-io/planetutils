"""Characterization tests for elevation_tile_merge's GDAL command lines.

This module currently shells out to gdal_merge.py / gdal_translate. These
tests pin the argv so the port to rasterio is a deliberate, reviewable change.

Note: argv pinning is NOT sufficient safety for that port -- the rasterio
rewrite deletes the argv entirely. A numeric golden (array checksum, shape,
dtype, transform, CRS, nodata) must be captured before porting.
"""
import sys

import pytest

from planetutils import elevation_tile_merge


@pytest.fixture
def gdal_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(elevation_tile_merge.subprocess, 'check_call',
                        lambda cmd: calls.append(cmd) or 0)
    return calls


def make_tiles(tmp_path, names=('a.tif', 'b.tif')):
    d = tmp_path / 'tiles'
    (d / '13' / '1303').mkdir(parents=True)
    paths = []
    for n in names:
        p = d / '13' / '1303' / n
        p.write_bytes(b'')
        paths.append(str(p))
    return d, sorted(paths)


def run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, 'argv', ['elevation_tile_merge'] + argv)
    elevation_tile_merge.main()


class TestMergeArgv:
    def test_merge_without_scale(self, tmp_path, monkeypatch, gdal_calls):
        tiles, paths = make_tiles(tmp_path)
        out = str(tmp_path / 'out.tif')
        run_cli(monkeypatch, [out, str(tiles)])
        assert len(gdal_calls) == 1
        cmd = gdal_calls[0]
        assert cmd[:5] == ['gdal_merge.py', '-init', '0', '-o', out]
        assert sorted(cmd[5:]) == paths

    def test_merge_with_scale_uses_tempfile_then_translates(
            self, tmp_path, monkeypatch, gdal_calls):
        tiles, _paths = make_tiles(tmp_path)
        out = str(tmp_path / 'out.tif')
        run_cli(monkeypatch, ['--scale', '0,4000', out, str(tiles)])
        assert len(gdal_calls) == 2

        merge_cmd, translate_cmd = gdal_calls
        # merge writes to a temp file, not directly to outpath
        tmpname = merge_cmd[4]
        assert merge_cmd[:4] == ['gdal_merge.py', '-init', '0', '-o']
        assert tmpname != out
        assert tmpname.endswith('.tif')

        assert translate_cmd == [
            'gdal_translate', '-of', 'GTiff', '-ot', 'Byte',
            '-scale', '0', '4000', '0', '255', tmpname, out]

    def test_no_input_files_exits_zero(self, tmp_path, monkeypatch, gdal_calls):
        empty = tmp_path / 'empty'
        empty.mkdir()
        with pytest.raises(SystemExit) as e:
            run_cli(monkeypatch, [str(tmp_path / 'out.tif'), str(empty)])
        assert e.value.code == 0
        assert gdal_calls == []

    def test_malformed_scale_exits_one(self, tmp_path, monkeypatch, gdal_calls):
        tiles, _ = make_tiles(tmp_path)
        with pytest.raises(SystemExit) as e:
            run_cli(monkeypatch,
                    ['--scale', '0', str(tmp_path / 'out.tif'), str(tiles)])
        assert e.value.code == 1
        assert gdal_calls == []

    def test_only_tif_files_are_collected(self, tmp_path, monkeypatch,
                                          gdal_calls):
        tiles, paths = make_tiles(tmp_path)
        (tiles / '13' / '1303' / 'ignored.txt').write_text('x')
        (tiles / '13' / '1303' / 'ignored.hgt').write_bytes(b'')
        run_cli(monkeypatch, [str(tmp_path / 'out.tif'), str(tiles)])
        assert sorted(gdal_calls[0][5:]) == paths
