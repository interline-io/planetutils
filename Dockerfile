FROM ubuntu:18.04
LABEL maintainer="Ian Rees <ian@interline.io>,Drew Dara-Abrams <drew@interline.io>"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -y && apt-get install \
      python3 \
      python3-pip \
      pypy-setuptools \
      curl \
      osmosis \
      osmctools \
      osmium-tool \
      pyosmium \
      python-gdal \
      gdal-bin \
      awscli \
      software-properties-common \
      -y

# Ubuntu Java SSL issue - https://stackoverflow.com/questions/6784463/error-trustanchors-parameter-must-be-non-empty/25188331#25188331
RUN /usr/bin/printf '\xfe\xed\xfe\xed\x00\x00\x00\x02\x00\x00\x00\x00\xe2\x68\x6e\x45\xfb\x43\xdf\xa4\xd9\x92\xdd\x41\xce\xb6\xb2\x1c\x63\x30\xd7\x92' > /etc/ssl/certs/java/cacerts
RUN /var/lib/dpkg/info/ca-certificates-java.postinst configure

WORKDIR /app
COPY . /app
RUN python3 setup.py test
RUN pip3 install .

COPY planetutils.sh /scripts/planetutils.sh

WORKDIR /data

CMD [ "/scripts/planetutils.sh" ]
