FROM ubuntu:16.04

RUN apt-get update && apt-get install awscli osmctools curl -y

COPY scripts /scripts

WORKDIR /app

CMD [ "/bin/bash", "/scripts/update_planet.sh" ]
