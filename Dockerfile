# syntax=docker/dockerfile:1

# uv is pinned by digest: an unpinned :latest would make the same git tag
# produce different images on different days.
FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv

FROM ubuntu:24.04 AS base
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

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"

# Dependencies first, so a source change does not invalidate the layer.
COPY pyproject.toml uv.lock README.md LICENSE.txt ./

# --- test stage: dev dependencies and the suite, for CI to target ---
FROM base AS test
RUN uv sync --frozen --extra s3 --no-install-project
COPY planetutils ./planetutils
COPY tests ./tests
COPY examples ./examples
RUN uv sync --frozen --extra s3

# --- runtime stage: what gets published ---
FROM base AS runtime
# --extra s3 installs boto3, which osm_planet_update --s3 needs. --no-dev
# keeps pytest and ruff out of the published image.
RUN uv sync --frozen --no-dev --extra s3 --no-install-project
COPY planetutils ./planetutils
COPY examples ./examples
RUN uv sync --frozen --no-dev --extra s3

COPY planetutils.sh /scripts/planetutils.sh

WORKDIR /data

CMD [ "/scripts/planetutils.sh" ]
