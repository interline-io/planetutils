"""Entry-point smoke tests.

The console_scripts list is read from pyproject.toml rather than duplicated
here, so it cannot drift from packaging. This is the test that catches a CLI
broken by the star-import removal, so it must stay ahead of that change.
"""
import importlib
import tomllib

import pytest
from conftest import REPO_ROOT


def console_scripts():
    with open(REPO_ROOT / 'pyproject.toml', 'rb') as f:
        return tomllib.load(f)['project']['scripts']


SCRIPTS = console_scripts()


def test_pyproject_declares_all_eight_commands():
    assert len(SCRIPTS) == 8


@pytest.mark.parametrize('name,target', sorted(SCRIPTS.items()))
def test_entry_point_is_importable_and_callable(name, target):
    module_name, _, func_name = target.partition(':')
    module = importlib.import_module(module_name)
    assert hasattr(module, func_name), f'{module_name} has no {func_name}'
    assert callable(getattr(module, func_name))


@pytest.mark.parametrize('name,target', sorted(SCRIPTS.items()))
def test_entry_point_help_exits_zero(name, target, monkeypatch, capsys):
    """--help must work without any external binary or network access."""
    import sys
    module_name, _, func_name = target.partition(':')
    module = importlib.import_module(module_name)
    monkeypatch.setattr(sys, 'argv', [name, '--help'])
    with pytest.raises(SystemExit) as e:
        getattr(module, func_name)()
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith('usage:')


def test_osm_planet_update_defaults_to_osmium(capsys):
    """osmium needs no system binaries; osmosis needs Java. The container
    script planetutils.sh already defaults to osmium."""
    import sys
    import unittest.mock as mock

    import pytest as _pytest

    from planetutils import osm_planet_update
    with mock.patch.object(sys, 'argv', ['osm_planet_update', '--help']):
        with _pytest.raises(SystemExit):
            osm_planet_update.main()
    out = capsys.readouterr().out
    assert 'osmium (default' in out


def test_missing_binary_is_reported_cleanly(monkeypatch, capsys):
    """A missing external tool must be a message and exit 1, not a traceback."""
    import sys

    import pytest as _pytest

    from planetutils import osm_planet_extract, planet
    monkeypatch.setattr(planet.shutil, 'which', lambda n: None)
    monkeypatch.setattr(planet.os.path, 'isfile', lambda p: False)
    monkeypatch.setattr(sys, 'argv', [
        'osm_planet_extract', '--toolchain=osmium',
        '--bbox=-1,-1,1,1', '--name=x', 'planet.osm.pbf'])
    with _pytest.raises(SystemExit) as e:
        osm_planet_extract.main()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith('error: osmium not found on PATH')
    assert 'Traceback' not in err


def test_osm_planet_update_rejects_identical_input_and_output(tmp_path,
                                                              monkeypatch,
                                                              capsys):
    """Issue #5: this used to run to completion and corrupt the planet."""
    import sys

    from planetutils import osm_planet_update
    osmpath = tmp_path / 'planet.osm.pbf'
    osmpath.write_bytes(b'x')
    monkeypatch.setattr(sys, 'argv', [
        'osm_planet_update', str(osmpath), str(osmpath)])
    with pytest.raises(SystemExit) as e:
        osm_planet_update.main()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert 'same file' in err
    assert 'Traceback' not in err


def test_osm_planet_update_checks_paths_before_downloading(tmp_path,
                                                           monkeypatch,
                                                           capsys):
    """The planet is downloaded when missing, so reporting the same-file
    error afterwards would mean fetching tens of gigabytes first."""
    import sys
    from unittest import mock

    from planetutils import osm_planet_update
    missing = str(tmp_path / 'missing.osm.pbf')
    monkeypatch.setattr(sys, 'argv',
                        ['osm_planet_update', missing, missing])
    with mock.patch.object(osm_planet_update, 'PlanetDownloaderHttp') as http, \
         mock.patch.object(osm_planet_update, 'PlanetDownloaderS3') as s3:
        with pytest.raises(SystemExit) as e:
            osm_planet_update.main()
    assert e.value.code == 1
    assert 'same file' in capsys.readouterr().err
    assert not http.called and not s3.called, 'downloaded before validating'
