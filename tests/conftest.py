"""Shared test fixtures and binary-gating helpers.

Fixture paths are resolved relative to this file rather than the process CWD;
the suite previously only passed when invoked from the repository root.
"""
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"

PLANET_PBF = EXAMPLES / "san-francisco-downtown.osm.pbf"
PLANET_PBF_TIMESTAMP = "2018-02-02T22:34:43Z"
TEST_GEOJSON = EXAMPLES / "test.geojson"
EXAMPLE_BBOXES_CSV = EXAMPLES / "example-bboxes.csv"


def needs(binary):
    """Mark a test as requiring `binary` on PATH.

    Skipped when the binary is absent, so the suite stays green on machines
    (and CI runners) without the OSM/GDAL toolchain. Pass --require-binaries
    to turn those skips into hard failures; the Docker CI job does this so the
    binary-backed paths are genuinely exercised exactly once.
    """
    return pytest.mark.requires_binary(binary)


def pytest_addoption(parser):
    parser.addoption(
        "--require-binaries",
        action="store_true",
        default=False,
        help="Fail, rather than skip, tests whose external binaries are missing.",
    )


def pytest_collection_modifyitems(config, items):
    # With --require-binaries we add no marker at all, so the test runs and
    # fails on its own (FileNotFoundError) -- that is the signal we want in
    # the one environment guaranteed to have the toolchain.
    if config.getoption("--require-binaries"):
        return
    for item in items:
        for mark in item.iter_markers(name="requires_binary"):
            binary = mark.args[0]
            if shutil.which(binary) is None:
                item.add_marker(
                    pytest.mark.skip(reason=f"{binary!r} not found on PATH")
                )


@pytest.fixture
def planet_pbf():
    return str(PLANET_PBF)
