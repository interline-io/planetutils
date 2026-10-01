"""Tests for osm_extract_convert."""
import json
import os
import sys

import pytest
from conftest import PLANET_PBF, needs

import planetutils.planet as planet
from planetutils import osm_extract_convert

OSMPATH = str(PLANET_PBF)


def record_with_config(obj):
    """Capture argv and the -c config, which is unlinked after the call."""
    calls = []

    def runner(args):
        with open(args[args.index('-c') + 1]) as f:
            calls.append((args, json.load(f)))

    obj._run = runner
    return calls


class TestOutputPath:
    @pytest.mark.parametrize('name,expected', [
        ('berlin.osm.pbf', 'berlin.geojson'),
        ('berlin.pbf', 'berlin.geojson'),
        ('berlin.osm', 'berlin.geojson'),
        ('us-ca.osm.pbf', 'us-ca.geojson'),
    ])
    def test_named_after_input(self, name, expected):
        got = planet.export_output_path('/in/%s' % name, 'geojson', outpath='/out')
        assert got == os.path.join('/out', expected)

    def test_geojsonl_extension(self):
        got = planet.export_output_path('berlin.osm.pbf', 'geojsonl')
        assert got == os.path.join('.', 'berlin.geojsonl')


class TestConverterArgv:
    def test_geojson(self):
        p = planet.ExtractConverterOsmium(OSMPATH)
        calls = record_with_config(p)
        p.convert(data_format='geojson', outpath='/out')
        (args, config), = calls
        cfg = args[args.index('-c') + 1]
        assert args == [
            'osmium', 'export', '-c', cfg, '-u', 'type_id',
            '-f', 'geojson', '-o', os.path.join('/out', 'san-francisco-downtown.geojson'),
            OSMPATH]
        assert config == planet.EXPORT_CONFIG
        assert not os.path.exists(cfg)

    def test_geojsonl_has_no_record_separator(self):
        p = planet.ExtractConverterOsmium(OSMPATH)
        calls = record_with_config(p)
        p.convert(data_format='geojsonl', outpath='/out')
        (args, _), = calls
        assert args[args.index('-f') + 1] == 'geojsonseq'
        assert '--format-option=print_record_separator=false' in args
        assert args[-1] == OSMPATH

    def test_overwrite(self):
        p = planet.ExtractConverterOsmium(OSMPATH)
        calls = record_with_config(p)
        p.convert(overwrite=True)
        (args, _), = calls
        assert '--overwrite' in args

    def test_config_is_removed_when_osmium_fails(self):
        p = planet.ExtractConverterOsmium(OSMPATH)
        seen = []

        def failing(args):
            seen.append(args[args.index('-c') + 1])
            raise RuntimeError('osmium failed')

        p._run = failing
        with pytest.raises(RuntimeError):
            p.convert()
        assert not os.path.exists(seen[0])

    def test_unknown_format(self):
        with pytest.raises(ValueError):
            planet.ExtractConverterOsmium(OSMPATH).convert(data_format='shp')

    def test_commands_keep_config(self):
        p = planet.ExtractConverterOsmium(OSMPATH)
        (args,) = p.convert_commands(data_format='geojson')
        cfg = args[args.index('-c') + 1]
        try:
            with open(cfg) as f:
                assert json.load(f) == planet.EXPORT_CONFIG
        finally:
            os.unlink(cfg)


class TestCli:
    def test_converts_each_input(self, monkeypatch, tmp_path):
        seen = []
        monkeypatch.setattr(planet.ExtractConverterOsmium, 'convert',
                            lambda self, **kw: seen.append((self.osmpath, kw)))
        monkeypatch.setattr(sys, 'argv', [
            'osm_extract_convert', '--format=geojsonl',
            '--outpath=%s' % tmp_path, OSMPATH, OSMPATH])
        osm_extract_convert.main()
        assert seen == [(OSMPATH, {'data_format': 'geojsonl',
                                   'outpath': str(tmp_path),
                                   'overwrite': False})] * 2

    def test_inputs_writing_the_same_output_are_rejected(self, monkeypatch, capsys):
        monkeypatch.setattr(planet.ExtractConverterOsmium, 'convert',
                            lambda self, **kw: pytest.fail('converted'))
        monkeypatch.setattr(sys, 'argv', [
            'osm_extract_convert', '--overwrite',
            os.path.join('a', 'berlin.osm.pbf'), os.path.join('b', 'berlin.pbf')])
        with pytest.raises(SystemExit) as e:
            osm_extract_convert.main()
        assert e.value.code == 2
        assert 'would both write' in capsys.readouterr().err

    def test_missing_input_is_a_clean_error(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, 'argv', [
            'osm_extract_convert', 'does-not-exist.osm.pbf'])
        with pytest.raises(SystemExit) as e:
            osm_extract_convert.main()
        assert e.value.code == 1
        assert 'does not exist' in capsys.readouterr().err

    def test_unknown_format_is_a_usage_error(self, monkeypatch):
        monkeypatch.setattr(sys, 'argv', [
            'osm_extract_convert', '--format=shp', OSMPATH])
        with pytest.raises(SystemExit) as e:
            osm_extract_convert.main()
        assert e.value.code == 2

    def test_commands_print_without_running(self, monkeypatch, capsys):
        monkeypatch.setattr(planet.ExtractConverterOsmium, '_run',
                            lambda self, args: pytest.fail('ran a command'))
        monkeypatch.setattr(sys, 'argv', [
            'osm_extract_convert', '--commands', 'missing.osm.pbf'])
        osm_extract_convert.main()
        line = capsys.readouterr().out.strip()
        assert line.startswith('osmium export -c ')
        os.unlink(line.split()[3])


@needs('osmium')
class TestOsmium:
    def test_geojson(self, tmp_path):
        out = planet.ExtractConverterOsmium(OSMPATH).convert(
            data_format='geojson', outpath=str(tmp_path))
        with open(out, encoding='utf-8') as f:
            data = json.load(f)
        assert data['type'] == 'FeatureCollection'
        props = data['features'][0]['properties']
        assert {'@type', '@id', '@timestamp'} <= set(props)
        assert data['features'][0]['id'][0] in 'nwa'

    def test_geojsonl(self, tmp_path):
        out = planet.ExtractConverterOsmium(OSMPATH).convert(
            data_format='geojsonl', outpath=str(tmp_path))
        with open(out, 'rb') as f:
            lines = f.read().splitlines()
        assert len(lines) > 1
        assert not lines[0].startswith(b'\x1e')
        assert json.loads(lines[0])['type'] == 'Feature'

    def test_existing_output_needs_overwrite(self, tmp_path):
        p = planet.ExtractConverterOsmium(OSMPATH)
        p.convert(outpath=str(tmp_path))
        with pytest.raises(planet.PlanetPathError, match='--overwrite'):
            p.convert(outpath=str(tmp_path))
        p.convert(outpath=str(tmp_path), overwrite=True)
