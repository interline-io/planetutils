"""Tests for osm_planet_extract --ids."""
import sys

import pytest
from conftest import EXAMPLE_BBOXES_CSV, TEST_GEOJSON

import planetutils.planet as planet
from planetutils import osm_planet_extract


def run(monkeypatch, *argv):
    seen = {}

    def fake_extract(self, bboxes, **kw):
        seen.update(bboxes)

    monkeypatch.setattr(planet.PlanetExtractorOsmium, 'extract_bboxes',
                        fake_extract)
    monkeypatch.setattr(sys, 'argv', [
        'osm_planet_extract', '--toolchain=osmium', *argv, 'planet.osm.pbf'])
    osm_planet_extract.main()
    return seen


def test_without_ids_every_feature_is_cut(monkeypatch):
    seen = run(monkeypatch, '--geojson=%s' % TEST_GEOJSON)
    assert sorted(seen) == ['pentagon', 'union']


def test_ids_selects_geojson_features(monkeypatch):
    seen = run(monkeypatch, '--geojson=%s' % TEST_GEOJSON, '--ids=pentagon')
    assert list(seen) == ['pentagon']


def test_ids_tolerates_whitespace(monkeypatch):
    seen = run(monkeypatch, '--geojson=%s' % TEST_GEOJSON,
               '--ids= pentagon , union ')
    assert sorted(seen) == ['pentagon', 'union']


def test_ids_selects_csv_rows(monkeypatch):
    with open(EXAMPLE_BBOXES_CSV, encoding='utf-8') as f:
        first = f.readline().split(',')[0]
    seen = run(monkeypatch, '--csv=%s' % EXAMPLE_BBOXES_CSV, '--ids=%s' % first)
    assert list(seen) == [first]


def test_ids_matches_features_keyed_by_position(monkeypatch, tmp_path):
    """Features without an id are keyed by their index in the file."""
    path = tmp_path / 'noid.geojson'
    path.write_text('{"type": "FeatureCollection", "features": ['
                    '{"type": "Feature", "properties": {}, "geometry": '
                    '{"type": "Point", "coordinates": [0, 0]}}]}')
    seen = run(monkeypatch, '--geojson=%s' % path, '--ids=0')
    assert list(seen) == [0]


def test_unknown_id_fails_without_extracting(monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, '--geojson=%s' % TEST_GEOJSON,
            '--ids=pentagon,pentagno')
    assert e.value.code == 2
    assert 'pentagno' in capsys.readouterr().err


def test_empty_ids_fails(monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, '--geojson=%s' % TEST_GEOJSON, '--ids=,')
    assert e.value.code == 2
    assert '--ids is empty' in capsys.readouterr().err
