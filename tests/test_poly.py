"""Tests for Osmosis .poly extent files (issue #19).

Format reference:
https://wiki.openstreetmap.org/wiki/Osmosis/Polygon_Filter_File_Format
"""
import pytest

from planetutils.bbox import load_features_poly

AUSTRALIA = """australia_v
first_area
     0.1446763E+03    -0.3826313E+02
     0.1440632E+03    -0.3825894E+02
     0.1440683E+03    -0.3824400E+02
     0.1446789E+03    -0.3824825E+02
     0.1446763E+03    -0.3826313E+02
END
second_area
     0.1461230E+03    -0.3824600E+02
     0.1461240E+03    -0.3823000E+02
     0.1462200E+03    -0.3823000E+02
     0.1462200E+03    -0.3824600E+02
END
END
"""

SIMPLE = """sf
area
   -122.5 37.7
   -122.3 37.7
   -122.3 37.9
   -122.5 37.9
END
END
"""

WITH_HOLE = """hole_example
outer
   10.0 10.0
   20.0 10.0
   20.0 20.0
   10.0 20.0
END
!inner
   12.0 12.0
   18.0 12.0
   18.0 18.0
   12.0 18.0
END
END
"""


def write(tmp_path, text, name='x.poly'):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


class TestParsing:
    def test_name_line_keys_the_extract(self, tmp_path):
        got = load_features_poly(write(tmp_path, SIMPLE))
        assert list(got) == ['sf']

    def test_scientific_notation(self, tmp_path):
        """Coordinates are conventionally written in scientific notation."""
        feat = load_features_poly(write(tmp_path, AUSTRALIA))['australia_v']
        left, bottom, right, top = feat.bbox()
        assert left == pytest.approx(144.0632, abs=1e-4)
        assert right == pytest.approx(146.22, abs=1e-4)
        assert bottom == pytest.approx(-38.26313, abs=1e-5)
        assert top == pytest.approx(-38.23, abs=1e-4)

    def test_coordinates_are_lon_lat_not_lat_lon(self, tmp_path):
        """The format is longitude first; swapping them would put this
        extract in the wrong hemisphere."""
        feat = load_features_poly(write(tmp_path, SIMPLE))['sf']
        left, bottom, right, top = feat.bbox()
        assert -123 < left < -122
        assert 37 < bottom < 38

    def test_single_section_is_a_polygon(self, tmp_path):
        feat = load_features_poly(write(tmp_path, SIMPLE))['sf']
        assert feat.geometry['type'] == 'Polygon'

    def test_multiple_sections_become_a_multipolygon(self, tmp_path):
        feat = load_features_poly(write(tmp_path, AUSTRALIA))['australia_v']
        assert feat.geometry['type'] == 'MultiPolygon'
        assert len(feat.geometry['coordinates']) == 2

    def test_unclosed_ring_is_closed(self, tmp_path):
        """The closing point may be omitted; GeoJSON requires it."""
        feat = load_features_poly(write(tmp_path, SIMPLE))['sf']
        ring = feat.geometry['coordinates'][0]
        assert ring[0] == ring[-1]
        assert len(ring) == 5          # 4 given + the closing repeat

    def test_already_closed_ring_is_not_double_closed(self, tmp_path):
        feat = load_features_poly(write(tmp_path, AUSTRALIA))['australia_v']
        ring = feat.geometry['coordinates'][0][0]
        assert ring[0] == ring[-1]
        assert len(ring) == 5          # given closed; unchanged

    def test_bang_section_becomes_an_interior_ring(self, tmp_path):
        """A `!` prefix subtracts that area, i.e. a hole."""
        feat = load_features_poly(write(tmp_path, WITH_HOLE))['hole_example']
        rings = feat.geometry['coordinates']
        assert len(rings) == 2, 'hole was not recorded as an interior ring'
        assert feat.bbox() == [10.0, 10.0, 20.0, 20.0]

    def test_blank_lines_between_sections_are_tolerated(self, tmp_path):
        """Combined multi-section files separate sections with a blank line."""
        text = AUSTRALIA.replace('END\nsecond_area', 'END\n\nsecond_area')
        feat = load_features_poly(write(tmp_path, text))['australia_v']
        assert len(feat.geometry['coordinates']) == 2

    def test_is_rectangle_false_for_a_real_polygon(self, tmp_path):
        """Drives which branch osm_planet_extract takes for osmium."""
        tri = "t\narea\n 0 0\n 1 0\n 0.5 1\nEND\nEND\n"
        assert not load_features_poly(write(tmp_path, tri))['t'].is_rectangle()


class TestErrors:
    def test_missing_file(self, tmp_path):
        with pytest.raises(Exception, match='does not exist'):
            load_features_poly(str(tmp_path / 'nope.poly'))

    def test_empty_file(self, tmp_path):
        with pytest.raises(Exception, match='empty poly file'):
            load_features_poly(write(tmp_path, ''))

    def test_no_polygons(self, tmp_path):
        with pytest.raises(Exception, match='no polygons'):
            load_features_poly(write(tmp_path, 'justaname\nEND\n'))

    def test_unterminated_section(self, tmp_path):
        text = "x\narea\n 0 0\n 1 0\n 1 1\n"
        with pytest.raises(Exception, match='unterminated'):
            load_features_poly(write(tmp_path, text))

    def test_too_few_points(self, tmp_path):
        text = "x\narea\n 0 0\n 1 0\nEND\nEND\n"
        with pytest.raises(Exception, match='at least 3 points'):
            load_features_poly(write(tmp_path, text))

    def test_non_numeric_coordinate(self, tmp_path):
        text = "x\narea\n 0 0\n north east\n 1 1\nEND\nEND\n"
        with pytest.raises(Exception, match='invalid coordinate'):
            load_features_poly(write(tmp_path, text))

    def test_single_value_coordinate_line(self, tmp_path):
        text = "x\narea\n 0 0\n 1\n 1 1\nEND\nEND\n"
        with pytest.raises(Exception, match='invalid coordinate'):
            load_features_poly(write(tmp_path, text))

    def test_out_of_range_coordinates_are_rejected(self, tmp_path):
        text = "x\narea\n 0 0\n 200 0\n 200 100\nEND\nEND\n"
        feat = load_features_poly(write(tmp_path, text))['x']
        with pytest.raises(AssertionError):
            feat.bbox()


class TestCliWiring:
    """--poly must reach both commands that accept extents."""

    def test_osm_planet_extract_accepts_poly(self, tmp_path, monkeypatch):
        import sys

        import planetutils.planet as planet
        from planetutils import osm_planet_extract

        polypath = write(tmp_path, SIMPLE)
        seen = {}

        def fake_extract(self, bboxes, **kw):
            seen.update(bboxes)

        monkeypatch.setattr(planet.PlanetExtractorOsmium, 'extract_bboxes',
                            fake_extract)
        monkeypatch.setattr(sys, 'argv', [
            'osm_planet_extract', '--toolchain=osmium',
            '--poly=%s' % polypath, '--outpath=%s' % tmp_path,
            'planet.osm.pbf'])
        osm_planet_extract.main()
        assert list(seen) == ['sf']
        assert seen['sf'].geometry['type'] == 'Polygon'

    def test_elevation_tile_download_accepts_poly(self, tmp_path,
                                                  monkeypatch):
        import sys

        from planetutils import elevation_tile_download
        from planetutils.elevation_tile_downloader import (
            ElevationGeotiffDownloader,
        )

        polypath = write(tmp_path, SIMPLE)
        seen = {}

        def fake_download(self, bboxes):
            seen.update(bboxes)

        monkeypatch.setattr(ElevationGeotiffDownloader, 'download_bboxes',
                            fake_download)
        monkeypatch.setattr(sys, 'argv', [
            'elevation_tile_download', '--poly=%s' % polypath,
            '--zoom=8', '--outpath=%s' % tmp_path])
        elevation_tile_download.main()
        assert list(seen) == ['sf']

    def test_extract_help_lists_poly(self, monkeypatch, capsys):
        import sys

        from planetutils import osm_planet_extract
        monkeypatch.setattr(sys, 'argv', ['osm_planet_extract', '--help'])
        with pytest.raises(SystemExit):
            osm_planet_extract.main()
        assert '--poly' in capsys.readouterr().out
