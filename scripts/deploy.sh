#!/usr/bin/env sh
# phase:deploy handler. Context envelope arrives on stdin and is passed through.
# Config via env: DADA_IMAGE, DADA_APP, DADA_PORT (optional), DDC_TOKEN (required).
set -eu
here="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 -I "$here/dada_deploy.py" apply --name "$DADA_APP" --image "$DADA_IMAGE" --port "${DADA_PORT:-8080}"
