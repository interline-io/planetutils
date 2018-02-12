![current release version](https://img.shields.io/github/release/interline-io/osm-planet-update.svg)
![Docker Hub build status](https://img.shields.io/docker/build/interline/osm-planet-update.svg)

# OSM Planet Update Tools

Scripts and a Docker container to maintain your own mirror of the [OpenStreetMap](http://www.openstreetmap.org) planet.

## Usage

Using [Osmosis](https://wiki.openstreetmap.org/wiki/Osmosis):

```sh
docker run --rm -v /mnt:/data -t interline/osm-planet-update:latest /scripts/minutely_update_osmosis.sh
```

Using [Osmctools](https://github.com/ramunasd/osmctools)

```sh
docker run --rm -v /mnt:/data -t interline/osm-planet-update:latest /scripts/minutely_update_osmctools.sh
```