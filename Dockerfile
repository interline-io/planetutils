FROM ubuntu:16.04
LABEL maintainer="Ian Rees <ian@interline.io>,Drew Dara-Abrams <drew@interline.io>"

RUN apt-get update -y
RUN apt-get install \
      python \
      python-pip \
      curl \
      osmosis \
      osmctools \
      awscli \
      software-properties-common \
      -y

WORKDIR /app
COPY . /app
RUN python setup.py test
RUN pip install .

WORKDIR /data

CMD [ "planet_update", "planet-latest.osm.pbf", "planet-new.osm.pbf" ]
