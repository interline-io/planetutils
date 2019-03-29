#!/bin/bash
set -e

OSM_PLANET=${OSM_PLANET:-"planet-latest.osm.pbf"}
OSM_PLANET_TMP=${OSM_PLANET_TMP:-"planet-new.osm.pbf"}
OSM_TOOLCHAIN=${OSM_TOOLCHAIN:-"osmium"}

osm_planet_update --toolchain=${OSM_TOOLCHAIN} ${OSM_PLANET} ${OSM_PLANET_TMP}
mv ${OSM_PLANET_TMP} ${OSM_PLANET}

if [ -n "${BBOX}" ]; then
    osm_planet_extract --toolchain=${OSM_TOOLCHAIN} --csv=${BBOX} --outpath=${EXTRACTS} ${OSM_PLANET}
fi

if [ -n "${ELEVATION}" ]; then
    elevation_tile_download --csv=${BBOX} --outpath=${ELEVATION}
fi

