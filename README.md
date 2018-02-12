[![current release version](https://img.shields.io/github/release/interline-io/osm-planet-update.svg)](https://github.com/interline-io/osm-planet-update/releases)
[![Docker Hub build status](https://img.shields.io/docker/build/interline/osm-planet-update.svg)](https://hub.docker.com/r/interline/osm-planet-update/)

# OSM Planet Update Tools

Scripts and a Docker container to maintain your own mirror of the [OpenStreetMap](http://www.openstreetmap.org) planet.

## Usage

Using [Osmosis](https://wiki.openstreetmap.org/wiki/Osmosis):

```sh
mkdir -p data
docker run --rm -v data:/data -t interline/osm-planet-update:release-v0.1.1 /scripts/update_planet_osmosis.sh
```

Using [Osmctools](https://github.com/ramunasd/osmctools)

```sh
mkdir -p data
docker run --rm -v data:/data -t interline/osm-planet-update:release-v0.1.1 /scripts/update_planet_osmctools.sh
```