#!/usr/bin/env bash
set -euo pipefail
docker run --rm -v "${DATA_DIR:-$HOME/data}:/data" -w /data -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e INTERLINE_API_TOKEN -it ghcr.io/interline-io/planetutils:v0.5.0 "$@"
