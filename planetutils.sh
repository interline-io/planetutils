#!/usr/bin/env bash
# Default container entrypoint: update a local planet, then optionally cut
# extracts and download matching elevation tiles.
#
# Configured by environment variables; every one has a default except BBOX,
# EXTRACTS and ELEVATION, which are opt-in.
set -euo pipefail

OSM_PLANET="${OSM_PLANET:-planet-latest.osm.pbf}"
OSM_PLANET_TMP="${OSM_PLANET_TMP:-planet-new.osm.pbf}"
OSM_TOOLCHAIN="${OSM_TOOLCHAIN:-osmium}"
OSM_UPDATE_MEMORY="${OSM_UPDATE_MEMORY:-1024}"
BBOX="${BBOX:-}"
EXTRACTS="${EXTRACTS:-}"
ELEVATION="${ELEVATION:-}"

osm_planet_update \
    --toolchain="${OSM_TOOLCHAIN}" \
    --size="${OSM_UPDATE_MEMORY}" \
    "${OSM_PLANET}" "${OSM_PLANET_TMP}"
mv "${OSM_PLANET_TMP}" "${OSM_PLANET}"

if [ -n "${BBOX}" ]; then
    if [ -z "${EXTRACTS}" ]; then
        echo "error: BBOX is set but EXTRACTS (the output directory) is not" >&2
        exit 1
    fi
    osm_planet_extract \
        --toolchain="${OSM_TOOLCHAIN}" \
        --csv="${BBOX}" \
        --outpath="${EXTRACTS}" \
        "${OSM_PLANET}"
fi

if [ -n "${ELEVATION}" ]; then
    # Elevation tiles are selected by the same extent file as the extracts.
    # Previously an unset BBOX here produced `--csv=` and a confusing failure.
    if [ -z "${BBOX}" ]; then
        echo "error: ELEVATION is set but BBOX (the extent CSV) is not" >&2
        exit 1
    fi
    elevation_tile_download --csv="${BBOX}" --outpath="${ELEVATION}"
fi
