FROM ubuntu:24.04
LABEL maintainer="Ian Rees <ian@interline.io>,Drew Dara-Abrams <drew@interline.io>"
LABEL org.opencontainers.image.source=https://github.com/interline-io/planetutils

ENV DEBIAN_FRONTEND=noninteractive

# Only osm_planet_extract still needs system binaries: a correct bbox
# extract requires reference completion (osmium's complete_ways/smart
# strategies), which pyosmium does not expose. Everything else -- downloads,
# tile merging, timestamps, planet updates -- runs from Python wheels.
#
# osmosis is kept for --toolchain=osmosis and pulls in a JRE.
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        osmosis \
        osmctools \
        osmium-tool \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, so a source change does not invalidate the layer.
COPY pyproject.toml uv.lock README.md LICENSE.txt ./
RUN uv sync --frozen --no-install-project

COPY planetutils ./planetutils
COPY tests ./tests
COPY examples ./examples
# Dev dependencies are included so the image can run its own test suite.
# CI does exactly that with --require-binaries: the container is the one
# environment guaranteed to have osmosis, osmconvert and osmium, so nothing
# is allowed to skip there.
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

COPY planetutils.sh /scripts/planetutils.sh

WORKDIR /data

CMD [ "/scripts/planetutils.sh" ]
