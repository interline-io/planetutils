[![current release version](https://img.shields.io/github/release/interline-io/planetutils.svg)](https://github.com/interline-io/planetutils/releases)
[![Docker Hub container image build status](https://img.shields.io/docker/build/interline/planetutils.svg)](https://hub.docker.com/r/interline/planetutils/)
[![CircleCI code test status](https://circleci.com/gh/interline-io/planetutils.svg?style=svg)](https://circleci.com/gh/interline-io/planetutils)

# Interline PlanetUtils

Python scripts and a Docker container to work with planet-scale geographic data. Using PlanetUtils, you can:

- maintain your own copy of the [OpenStreetMap](http://www.openstreetmap.org) planet
- cut your copy of the OSM planet into named bounding boxes (a.k.a., mini Mapzen Metro Extracts)
- download [Mapzen Terrain Tiles from AWS](https://aws.amazon.com/public-datasets/terrain/) for the planet or your bounding boxes

PlanetUtils is packaged for use as a:

- Docker container, for use on any operating system
- Python package, for use on any operating system
- Homebrew formula, for use on Mac OS

## Installation

### Using Docker container

```sh
docker pull interline/planetutils:release-v0.1.3
```

### Using Homebrew on Mac OS***

```sh
brew install interline-io/planetutils/planetutils
```

### Using Python package

If you want to install and use the Python package directly, you'll need to provide:

- Python 2.x
- Java
- [Osmosis](https://wiki.openstreetmap.org/wiki/Osmosis)
- [OSM C tools](https://gitlab.com/osm-c-tools/osmctools/)

```sh
git clone https://github.com/interline-io/planetutils.git
tox
pip install .
```

## Usage

***

```sh
mkdir -p data
docker run --rm -v data:/data -t interline/planetutils:release-v0.1.3
```
