FROM ubuntu:18.04
LABEL maintainer="Ian Rees <ian@interline.io>,Drew Dara-Abrams <drew@interline.io>"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get install \
      python \
      python-pip \
      pypy-setuptools \
      curl \
      osmosis \
      osmctools \
      osmium-tool \
      pyosmium \
      awscli \
      software-properties-common \
      -y

WORKDIR /app
COPY . /app
RUN python setup.py test
RUN pip install .

COPY planetutils.sh /scripts/planetutils.sh

WORKDIR /data

CMD [ "/scripts/planetutils.sh" ]
