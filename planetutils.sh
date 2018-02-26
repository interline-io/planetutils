#!/bin/bash
set -e

OSM_PLANET=${OSM_PLANET:-"planet-latest.osm.pbf"}
OSM_PLANET_TMP=${OSM_PLANET_TMP:-"planet-new.osm.pbf"}

osm_planet_update ${OSM_PLANET} ${OSM_PLANET_TMP}
mv ${OSM_PLANET} ${OSM_PLANET_TMP}

if [ -n "${BBOX}" ]; then
    osm_planet_extract --csv=${BBOX} --outpath=${EXTRACTS} ${OSM_PLANET}
fi

if [ -n "${ELEVATION}" ]; then
    elevation_tile_download --csv=${BBOX} --outpath=${ELEVATION}
fi

