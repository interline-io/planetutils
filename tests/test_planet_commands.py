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
from conftest import PLANET_PBF

import planetutils.planet as planet
from planetutils.bbox import Feature

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
    """Downloads a missing planet over HTTP. This used to shell out to curl,
    which is neither installed in the container nor present by default on
    Windows."""

    def _record(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            planet.download, 'download_curl',
            lambda url, outpath, **kw: calls.append((url, outpath, kw)))
        return calls

    def test_downloads_default_planet_url(self, monkeypatch, tmp_path):
        out = str(tmp_path / 'planet.osm.pbf')
        calls = self._record(monkeypatch)
        planet.PlanetDownloaderHttp(out).download_planet()
        assert len(calls) == 1
        url, outpath, kw = calls[0]
        assert url == 'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf'
        assert outpath == out
        assert kw['compressed'] is True

    def test_custom_mirror_url(self, monkeypatch, tmp_path):
        out = str(tmp_path / 'planet.osm.pbf')
        calls = self._record(monkeypatch)
        planet.PlanetDownloaderHttp(out).download_planet(
            url='https://mirror.example.org/planet.osm.pbf')
        assert calls[0][0] == 'https://mirror.example.org/planet.osm.pbf'

    def test_uses_the_long_read_timeout(self, monkeypatch, tmp_path):
        """The planet is tens of GB and the transfer is not resumable, so the
        short tile timeout would discard hours of work on a single stall."""
        out = str(tmp_path / 'planet.osm.pbf')
        calls = self._record(monkeypatch)
        planet.PlanetDownloaderHttp(out).download_planet()
        timeout = calls[0][2]['timeout']
        assert timeout == planet.download.LARGE_FILE_TIMEOUT
        assert timeout[1] > planet.download.TIMEOUT[1]

    def test_does_not_shell_out(self, monkeypatch, tmp_path):
        """Regression guard: no external binary on the planet download path."""
        out = str(tmp_path / 'planet.osm.pbf')
        self._record(monkeypatch)
        p = planet.PlanetDownloaderHttp(out)

        def explode(args):
            raise AssertionError('shelled out to %r' % (args,))

        p._run = explode
        p.download_planet()

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
    """--commands with the osmium toolchain emits a runnable command.

    planet.py writes the extract config to a tempfile. When the command is
    actually run the config is cleaned up afterwards; when it is only being
    printed it must survive, or the printed command could never be run by
    hand -- which is the entire point of --commands.
    """

    def test_current_behavior_config_is_gone_after_the_call(self, tmp_path):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        calls = record(p)
        p.extract_bboxes({'test': rect_feature()}, outpath=str(tmp_path))
        config_path = calls[0][5]
        assert not os.path.exists(config_path)

    def test_emitted_command_is_runnable(self, tmp_path):
        p = planet.PlanetExtractorOsmium(OSMPATH)
        cmds = p.extract_commands({'test': rect_feature()},
                                  outpath=str(tmp_path))
        config_path = cmds[0][5]
        assert os.path.exists(config_path), (
            'the config referenced by the emitted command must still exist')


class TestUpdaterOsmosis:
    """The osmosis update path is retained, so it gets pinned too.

    _initialize_state used to write the bytes from urlopen() into a
    text-mode file, raising TypeError, so this path had not worked since the
    Python 3 migration. Now fixed and covered.
    """

    def _updater(self, tmp_path):
        osmpath = tmp_path / 'planet.osm.pbf'
        osmpath.write_bytes(b'')
        p = planet.PlanetUpdaterOsmosis(str(osmpath))
        p.changeset_url = 'https://example.org/replication/hour'
        p.get_timestamp = lambda: '2018-02-02T22:34:43Z'
        return p

    def test_get_changeset_argv(self, tmp_path):
        p = self._updater(tmp_path)
        calls = record(p)
        p._get_changeset()
        assert calls == [[
            'osmosis',
            '--read-replication-interval',
            'workingDirectory=%s' % p.osmosis_workdir,
            '--simplify-change',
            '--write-xml-change',
            os.path.join(p.osmosis_workdir, 'changeset.osm.gz'),
        ]]

    def test_apply_changeset_argv(self, tmp_path):
        p = self._updater(tmp_path)
        calls = record(p)
        p._apply_changeset('/out/new.osm.pbf')
        assert calls == [[
            'osmosis',
            '--read-xml-change',
            os.path.join(p.osmosis_workdir, 'changeset.osm.gz'),
            '--read-pbf', p.osmpath,
            '--apply-change',
            '--write-pbf', '/out/new.osm.pbf',
        ]]

    def test_initialize_writes_configuration(self, tmp_path):
        p = self._updater(tmp_path)
        calls = record(p)
        p._initialize()
        assert calls[0][0] == 'osmosis'
        assert calls[0][1] == '--read-replication-interval-init'
        with open(os.path.join(p.osmosis_workdir,
                               'configuration.txt')) as f:
            config = f.read()
        assert 'baseUrl=https://example.org/replication/hour' in config
        assert 'maxInterval=0' in config

    def test_initialize_is_idempotent(self, tmp_path):
        p = self._updater(tmp_path)
        record(p)
        p._initialize()
        calls = record(p)
        p._initialize()
        assert calls == []

    def test_missing_planet_raises(self, tmp_path):
        p = planet.PlanetUpdaterOsmosis(str(tmp_path / 'nope.osm.pbf'))
        record(p)
        with pytest.raises(Exception, match='planet file does not exist'):
            p.update_planet('/out/new.osm.pbf')

    def test_initialize_state_writes_sequence_file(self, tmp_path,
                                                   monkeypatch):
        p = self._updater(tmp_path)
        record(p)
        os.makedirs(p.osmosis_workdir, exist_ok=True)
        monkeypatch.setattr(
            planet, 'urlopen',
            lambda url: type('R', (), {
                'read': staticmethod(lambda: b'sequenceNumber=123\n')})())
        p._initialize_state()
        statepath = os.path.join(p.osmosis_workdir, 'state.txt')
        with open(statepath) as f:
            assert 'sequenceNumber=123' in f.read()


class TestWorkdirOverride:
    def test_defaults_alongside_the_planet_file(self, tmp_path):
        osmpath = tmp_path / 'planet.osm.pbf'
        p = planet.PlanetUpdaterOsmosis(str(osmpath))
        assert p.osmosis_workdir == str(tmp_path / 'planet.osm.pbf.workdir')

    def test_explicit_workdir_is_honored(self, tmp_path):
        osmpath = tmp_path / 'planet.osm.pbf'
        p = planet.PlanetUpdaterOsmosis(str(osmpath),
                                        osmosis_workdir='/custom/wd')
        assert p.osmosis_workdir == '/custom/wd'

    def test_none_workdir_falls_back_to_default(self, tmp_path):
        osmpath = tmp_path / 'planet.osm.pbf'
        p = planet.PlanetUpdaterOsmosis(str(osmpath), osmosis_workdir=None)
        assert p.osmosis_workdir == str(tmp_path / 'planet.osm.pbf.workdir')


class TestMissingBinaryPreflight:
    def test_actionable_error_instead_of_filenotfound(self, monkeypatch):
        monkeypatch.setattr(planet.shutil, 'which', lambda n: None)
        p = planet.PlanetBase(OSMPATH)
        with pytest.raises(planet.MissingBinaryError) as e:
            p.osmosis('--version')
        msg = str(e.value)
        assert 'osmosis not found on PATH' in msg
        assert 'brew install osmosis' in msg
        assert 'ghcr.io/interline-io/planetutils' in msg

    def test_osmium_hint_mentions_conda_for_windows(self, monkeypatch):
        monkeypatch.setattr(planet.shutil, 'which', lambda n: None)
        p = planet.PlanetExtractorOsmium(OSMPATH)
        with pytest.raises(planet.MissingBinaryError) as e:
            p.extract_bboxes({'t': rect_feature()}, outpath='/out')
        assert 'conda install conda-forge::osmium-tool' in str(e.value)

    def test_commands_mode_works_without_any_binary(self, monkeypatch):
        """--commands only prints; it must not require the toolchain."""
        monkeypatch.setattr(planet.shutil, 'which', lambda n: None)
        p = planet.PlanetExtractorOsmosis(OSMPATH)
        cmds = p.extract_commands({'test': BBOX}, outpath='/out')
        assert cmds[0][0] == 'osmosis'

    def test_resolves_console_scripts_next_to_the_interpreter(self,
                                                              tmp_path,
                                                              monkeypatch):
        """pyosmium-up-to-date lives in the venv's bin/Scripts dir, which is
        not on PATH when the venv is not activated."""
        fake_bin = tmp_path / 'python'
        fake_bin.write_text('')
        script = tmp_path / 'pyosmium-up-to-date'
        script.write_text('')
        script.chmod(0o755)
        monkeypatch.setattr(planet.sys, 'executable', str(fake_bin))
        monkeypatch.setattr(planet.shutil, 'which', lambda n: None)
        assert planet.require_binary('pyosmium-up-to-date') == str(script)
