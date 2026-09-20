"""Golden-argv characterization tests for planet.py.

These pin the exact command lines planetutils builds for osmosis, osmconvert
and osmium. They need no external binaries and no network, so they run
everywhere -- including Windows CI -- and they are the safety net for the
portability rewrites.

If a change here is intentional, re-baseline it in its own commit.
"""
import json
import os

import pytest

import planetutils.planet as planet
from planetutils.bbox import Feature

from conftest import PLANET_PBF

OSMPATH = str(PLANET_PBF)
BBOX = [-122.430439, 37.766508, -122.379670, 37.800052]


def record(obj):
    """Replace the external-command seam with a recorder."""
    calls = []
    obj._run = calls.append
    return calls


def record_with_config(obj):
    """Recorder that also snapshots the osmium -c config file.

    planet.py unlinks the temp config immediately after running the command,
    so it must be read *during* the call, not afterwards.
    """
    calls = []

    def runner(args):
        cfg = None
        if '-c' in args:
            with open(args[args.index('-c') + 1]) as f:
                cfg = json.load(f)
        calls.append((args, cfg))

    obj._run = runner
    return calls


def rect_feature(bbox=BBOX):
    f = Feature()
    f.set_bbox(bbox)
    return f


class TestExtractorOsmosis:
    def test_single_bbox_argv(self):
        p = planet.PlanetExtractorOsmosis(OSMPATH)
        calls = record(p)
        p.extract_bboxes({'test': BBOX}, outpath='/out')
        assert calls == [[
            'osmosis',
            '--read-pbf-fast', OSMPATH, 'workers=1',
            '--tee', '1',
            '--bounding-box',
            'left=-122.43044', 'bottom=37.76651',
            'right=-122.37967', 'top=37.80005',
            '--write-pbf', os.path.join('/out', 'test.osm.pbf'),
        ]]

    def test_tee_count_tracks_bbox_count(self):
        p = planet.PlanetExtractorOsmosis(OSMPATH)
        calls = record(p)
        p.extract_bboxes({'a': BBOX, 'b': BBOX}, outpath='/out', workers=4)
        argv = calls[0]
        assert argv[:4] == ['osmosis', '--read-pbf-fast', OSMPATH, 'workers=4']
        assert argv[4:6] == ['--tee', '2']
        assert argv.count('--bounding-box') == 2
        assert argv.count('--write-pbf') == 2


class TestExtractorOsmconvert:
    def test_argv(self):
        p = planet.PlanetExtractorOsmconvert(OSMPATH)
        calls = record(p)
        p.extract_bboxes({'test': BBOX}, outpath='/out')
        assert calls == [[
            'osmconvert',
            OSMPATH,
            '-b=-122.430439,37.766508,-122.37967,37.800052',
            '-o=%s' % os.path.join('/out', 'test.osm.pbf'),
        ]]


class TestExtractorOsmium:
    """Note: unlike the other extractors, this one requires a Feature --
    it calls bbox.is_rectangle(). A plain 4-sequence raises AttributeError."""

    def test_rejects_plain_sequence(self):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        record(p)
        with pytest.raises(AttributeError):
            p.extract_bboxes({'test': BBOX}, outpath='/out')

    def test_rectangle_writes_bbox_config(self, tmp_path):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        calls = record_with_config(p)
        p.extract_bboxes({'test': rect_feature()}, outpath=str(tmp_path),
                         strategy='complete_ways')
        argv, config = calls[0]
        assert argv[0] == 'osmium'
        assert argv[1] == 'extract'
        assert argv[2:4] == ['-s', 'complete_ways']
        assert argv[4] == '-c'
        assert argv[6] == OSMPATH
        assert config['directory'] == str(tmp_path)
        assert len(config['extracts']) == 1
        extract = config['extracts'][0]
        assert extract['output'] == 'test.osm.pbf'
        assert extract['output_format'] == 'pbf'
        assert extract['bbox'] == {
            'left': -122.430439, 'bottom': 37.766508,
            'right': -122.37967, 'top': 37.800052,
        }

    def test_polygon_uses_geometry_branch(self, tmp_path):
        coords = [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.5],
                   [1.0, 0.0], [0.0, 0.0]]]
        f = Feature(geometry={'type': 'Polygon', 'coordinates': coords})
        assert not f.is_rectangle()
        p = planet.PlanetExtractorOsmium(OSMPATH)
        calls = record_with_config(p)
        p.extract_bboxes({'poly': f}, outpath=str(tmp_path))
        _argv, config = calls[0]
        extract = config['extracts'][0]
        assert 'bbox' not in extract
        assert extract['polygon'] == coords

    def test_default_strategy_is_complete_ways(self, tmp_path):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        calls = record_with_config(p)
        p.extract_bboxes({'test': rect_feature()}, outpath=str(tmp_path))
        assert calls[0][0][2:4] == ['-s', 'complete_ways']


class TestUpdaterOsmium:
    def test_argv(self):
        p = planet.PlanetUpdaterOsmium(OSMPATH)
        calls = record(p)
        p.update_planet('/out/new.osm.pbf', size='2048',
                        changeset_url='https://example.org/replication/hour')
        assert calls == [[
            'pyosmium-up-to-date',
            '-s', '2048',
            '--server', 'https://example.org/replication/hour',
            '-v', OSMPATH,
            '-o', '/out/new.osm.pbf',
        ]]

    def test_default_changeset_url_uses_grain(self):
        p = planet.PlanetUpdaterOsmium(OSMPATH)
        calls = record(p)
        p.update_planet('/out/new.osm.pbf')
        assert ('https://planet.openstreetmap.org/replication/minute'
                in calls[0])

    def test_missing_planet_raises(self):
        p = planet.PlanetUpdaterOsmium('/nonexistent/planet.osm.pbf')
        record(p)
        with pytest.raises(Exception, match='planet file does not exist'):
            p.update_planet('/out/new.osm.pbf')


class TestDownloaderHttp:
    def test_curl_argv(self):
        p = planet.PlanetDownloaderHttp('/tmp/does-not-exist.osm.pbf')
        calls = record(p)
        p.download_planet()
        assert calls == [[
            'curl', '-L', '-o', '/tmp/does-not-exist.osm.pbf',
            'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf',
        ]]

    def test_custom_mirror_url(self):
        p = planet.PlanetDownloaderHttp('/tmp/does-not-exist.osm.pbf')
        calls = record(p)
        p.download_planet(url='https://mirror.example.org/planet.osm.pbf')
        assert calls[0][-1] == 'https://mirror.example.org/planet.osm.pbf'

    def test_refuses_to_overwrite_existing(self):
        p = planet.PlanetDownloaderHttp(OSMPATH)
        record(p)
        with pytest.raises(Exception, match='planet file exists'):
            p.download_planet()


class TestExtractCommands:
    """--commands prints the command instead of running it."""

    def test_osmosis_commands_are_returned_not_run(self):
        p = planet.PlanetExtractorOsmosis(OSMPATH)
        calls = record(p)
        got = p.extract_commands({'test': BBOX}, outpath='/out')
        assert calls == []
        assert got[0][0] == 'osmosis'
        assert got[0][1] == '--read-pbf-fast'


class TestOsmiumCommandsTempfileBug:
    """--commands with the osmium toolchain emits an unrunnable command.

    planet.py writes the extract config to a tempfile, emits a command line
    referencing it, then unlinks it -- so the printed command can never be
    run by hand, which is the entire point of --commands.
    """

    def test_current_behavior_config_is_gone_after_the_call(self, tmp_path):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        calls = record(p)
        p.extract_bboxes({'test': rect_feature()}, outpath=str(tmp_path))
        config_path = calls[0][5]
        assert not os.path.exists(config_path)

    @pytest.mark.xfail(strict=True,
                       reason='config tempfile is unlinked before the emitted '
                              'command could ever be run')
    def test_emitted_command_should_be_runnable(self, tmp_path):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        cmds = p.extract_commands({'test': rect_feature()},
                                  outpath=str(tmp_path))
        config_path = cmds[0][5]
        assert os.path.exists(config_path), (
            'the config referenced by the emitted command must still exist')
