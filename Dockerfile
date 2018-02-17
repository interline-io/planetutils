FROM ubuntu:16.04
LABEL maintainer="Ian Rees <ian@interline.io>,Drew Dara-Abrams <drew@interline.io>"

RUN apt-get update -y
RUN apt-get install \
      python \
      python-pip \
      python-boto3 \
      curl \
      osmosis \
      osmctools \
      awscli \
      software-properties-common \
      -y

COPY . /app
RUN pip install /app

WORKDIR /data

CMD [ "planet_update", "--overwrite", "planet-latest.osm.pbf", "planet-new.osm.pbf" ]
