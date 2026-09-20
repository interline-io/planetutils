"""Contract tests for planet timestamp extraction.

get_timestamp() currently shells out to osmconvert: it tries
`--out-timestamp` and, when that returns "(invalid timestamp)", falls back to
parsing `timestamp max:` out of `--out-statistics`.

The parsing contract is pinned here WITHOUT the binary, so it survives the
port to pyosmium. The port must keep returning the identical
'%Y-%m-%dT%H:%M:%SZ' string -- this value is consumed by shell scripts.
"""
import planetutils.planet as planet

from conftest import PLANET_PBF, PLANET_PBF_TIMESTAMP, needs

OSMPATH = str(PLANET_PBF)

# Captured verbatim from:
#   osmconvert examples/san-francisco-downtown.osm.pbf --out-statistics
STATISTICS = """timestamp min: 2008-05-12T05:41:03Z
timestamp max: 2018-02-02T22:34:43Z
lon min: -122.4195392
lon max: -122.3957703
lat min: 37.7753615
lat max: 37.7917798
nodes: 30165
ways: 4581
relations: 458
"""

INVALID_TIMESTAMP = '(invalid timestamp)\n'
VALID_TIMESTAMP = '2018-02-02T22:34:43Z\n'


def planet_with_responses(*responses):
    """PlanetBase whose external command returns the given canned outputs."""
    p = planet.PlanetBase(OSMPATH)
    queue = list(responses)
    p._run = lambda args: queue.pop(0)
    return p


class TestGetTimestampParsing:
    def test_fast_path_uses_out_timestamp(self):
        p = planet_with_responses(VALID_TIMESTAMP)
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP

    def test_falls_back_to_statistics_when_invalid(self):
        p = planet_with_responses(INVALID_TIMESTAMP, STATISTICS)
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP

    def test_picks_max_not_min(self):
        p = planet_with_responses(INVALID_TIMESTAMP, STATISTICS)
        assert p.get_timestamp() != '2008-05-12T05:41:03Z'

    def test_result_is_stripped(self):
        p = planet_with_responses('  %s  \n' % PLANET_PBF_TIMESTAMP)
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP

    def test_argv_for_fast_path(self):
        p = planet.PlanetBase(OSMPATH)
        calls = []

        def runner(args):
            calls.append(args)
            return VALID_TIMESTAMP

        p._run = runner
        p.get_timestamp()
        assert calls == [['osmconvert', OSMPATH, '--out-timestamp']]


class TestGetTimestampEndToEnd:
    @needs('osmconvert')
    def test_real_file(self):
        p = planet.PlanetBase(OSMPATH)
        assert p.get_timestamp() == PLANET_PBF_TIMESTAMP
