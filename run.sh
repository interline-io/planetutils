#!/usr/bin/env bash
# Run a planetutils command in the container.
#
# Defaults to the locally built `planetutils` image so this can smoke-test a
# build; set IMAGE to use a published one, e.g.
#   IMAGE=ghcr.io/interline-io/planetutils:v0.5.0 ./run.sh <command>
set -euo pipefail
docker run --rm -v "${DATA_DIR:-$HOME/data}:/data" -w /data/planets -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e INTERLINE_API_TOKEN -it "${IMAGE:-planetutils}" "$@"
