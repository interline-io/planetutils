"""Tests for planet timestamp extraction.

get_timestamp() used to shell out to osmconvert: `--out-timestamp` first,
falling back to parsing `timestamp max:` out of `--out-statistics`. It now
uses pyosmium, so it needs no external binary on any platform.

The contract is unchanged and deliberately pinned: the same
'%Y-%m-%dT%H:%M:%SZ' string, preferring the header's replication timestamp
and falling back to the newest object. That output is consumed by shell
scripts, so its exact shape matters.
"""
import datetime
import re

import pytest

import planetutils.planet as planet

from conftest import PLANET_PBF, PLANET_PBF_TIMESTAMP

OSMPATH = str(PLANET_PBF)


class TestGetTimestamp:
    def test_matches_the_known_fixture_value(self):
        p = planet.PlanetBase(OSMPATH)
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP

    def test_requires_no_external_binary(self, monkeypatch):
        """Regression guard: this must not shell out any more."""
        p = planet.PlanetBase(OSMPATH)

        def explode(args):
            raise AssertionError('get_timestamp shelled out to %r' % (args,))

        p._run = explode
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP

    def test_output_format_is_iso8601_zulu(self):
        p = planet.PlanetBase(OSMPATH)
        got = p.get_timestamp()
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', got)
        datetime.datetime.strptime(got, planet.PlanetBase.TIMESTAMP_FORMAT)

    def test_prefers_the_header_replication_timestamp(self, monkeypatch):
        """The fixture has an empty header, so the fast path needs a stub.

        A real planet file does carry this, and it must win over a scan.
        """
        p = planet.PlanetBase(OSMPATH)
        import osmium

        class FakeHeader:
            def get(self, key):
                return '2024-06-01T00:00:00Z'

        class FakeReader:
            def __init__(self, *a, **kw):
                pass

            def header(self):
                return FakeHeader()

            def close(self):
                pass

        monkeypatch.setattr(osmium.io, 'Reader', FakeReader)

        def explode(*a, **kw):
            raise AssertionError('should not have scanned the file')

        monkeypatch.setattr(osmium, 'FileProcessor', explode)
        assert p.get_timestamp() == '2024-06-01T00:00:00Z'

    def test_falls_back_to_scanning_when_header_is_empty(self):
        # This is the real behavior for the fixture: empty header, so the
        # value comes from the newest of its 35204 objects.
        p = planet.PlanetBase(OSMPATH)
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP

    def test_missing_file_raises(self):
        p = planet.PlanetBase('/nonexistent/planet.osm.pbf')
        with pytest.raises(Exception):
            p.get_timestamp()
