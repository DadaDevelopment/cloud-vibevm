#!/usr/bin/env bash
# Open the Zap UI running in the sandbox from your own machine, the way the image is designed:
# the browser talks to a gateway on ITS OWN 127.0.0.1, so we port-forward the pod's UI port and
# the pod's (random) gateway port, and ask the running owner for a fresh one-time pairing URL.
#
# Needs: kubectl with access to the namespace of your Zap deployment, python3.   (Untested - see ZAP-ACCESS.md)
# Usage: NS=<namespace> ./zap-open.sh <deployment>
set -euo pipefail
NS="${NS:?set NS to the namespace of the Zap deployment}"
DEP="${1:?usage: NS=<namespace> ./zap-open.sh <deployment>}"

# zap-quicklens attaches to the already running owner and prints {"url": "...", ...} with a new ticket.
JSON="$(kubectl -n "$NS" exec "deploy/$DEP" -- zap-quicklens --no-open --state-dir /home/vibe/zap-state | tail -n1)"
URL="$(printf '%s' "$JSON" | python3 -c 'import sys,json;print(json.load(sys.stdin)["url"])')"
GWPORT="$(python3 - "$URL" <<'PY'
import sys, urllib.parse as u
q = u.parse_qs(u.urlparse(sys.argv[1]).query)["workspace-gateway"][0]
print(u.urlparse(q).port)
PY
)"
echo "gateway port in pod: $GWPORT" >&2
kubectl -n "$NS" port-forward "deploy/$DEP" 4174:4174 "$GWPORT:$GWPORT" >/dev/null &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
sleep 2
echo "Open (the ticket is one-time, do not share):" >&2
echo "$URL"
( command -v open >/dev/null && open "$URL" ) || ( command -v xdg-open >/dev/null && xdg-open "$URL" ) || true
echo "port-forward running, Ctrl+C to stop" >&2
wait $PF
