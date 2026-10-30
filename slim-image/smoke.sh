#!/usr/bin/env bash
# Build the slim image and check it still serves the UI. Needs a running Docker daemon
# (none in the authoring session, so this has never been run).
set -euo pipefail
cd "$(dirname "$0")"
TAG="${1:-vibevm-zap-slim:test}"
docker build -t "$TAG" .
docker image inspect "$TAG" --format 'size: {{.Size}} bytes'
docker image inspect vibevm/vibevm-zap:1.0.7 --format 'original: {{.Size}} bytes' 2>/dev/null || true
CID="$(docker run -d --rm -p 18080:8080 "$TAG")"
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT
for i in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/ || true)"
  [ "$code" = 200 ] && { echo "UI answered 200 after ${i}s"; break; }
  sleep 1
done
[ "$code" = 200 ] || { docker logs "$CID" | tail -20; echo "FAIL: UI did not answer"; exit 1; }
docker exec "$CID" sh -c 'zap-server --help | head -3'
echo OK
