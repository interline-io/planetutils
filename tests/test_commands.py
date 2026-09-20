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
    import pytest as _pytest
    from planetutils import osm_planet_update
    import unittest.mock as mock
    with mock.patch.object(sys, 'argv', ['osm_planet_update', '--help']):
        with _pytest.raises(SystemExit):
            osm_planet_update.main()
    out = capsys.readouterr().out
    assert 'osmium (default' in out
