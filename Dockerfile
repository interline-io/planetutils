FROM ubuntu:16.04

RUN apt-get update -y
RUN apt-get install awscli osmctools -y

WORKDIR /app

CMD [ "/bin/bash", "scripts/update_planet.sh" ]
