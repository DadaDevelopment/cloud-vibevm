#!/bin/bash
set -u
OUT=/home/vibe/out
WORK=/home/vibe/work
mkdir -p "$OUT" "$WORK"
python3 /home/vibe/serve.py "$OUT" 8080 &
now() { date +%s.%N; }
T0=$(now)
step() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$OUT/log.txt"; }
elapsed() { python3 -c "print(round($(now)-$T0,1))"; }
: > "$OUT/log.txt"
step "vibe $(vibe --version 2>&1 | head -1)"
if [ -f /home/vibe/project-src/vibe.lock ]; then
  cp -a /home/vibe/project-src/. "$WORK/project"
  MODE=from-lock
else
  mkdir -p "$WORK/project" && cd "$WORK/project"
  git init -q -b main . && git config user.email runner@dada.invalid && git config user.name runner
  vibe init demo --path . >>"$OUT/log.txt" 2>&1 || vibe init demo >>"$OUT/log.txt" 2>&1
  MODE=bootstrap
fi
cd "$WORK/project" && [ -f vibe.toml ] || cd "$WORK/project/demo"
step "mode=$MODE project=$(pwd)"
S=$(now)
if [ "$MODE" = from-lock ]; then
  vibe install --assume-yes --quiet >>"$OUT/log.txt" 2>&1
else
  vibe install org.vibevm.world/redbook --assume-yes --quiet >>"$OUT/log.txt" 2>&1
fi
RC=$?
step "vibe install rc=$RC in $(python3 -c "print(round($(now)-$S,1))")s"
vibe check >>"$OUT/log.txt" 2>&1; step "vibe check rc=$?"
[ -f vibe.lock ] && cp vibe.lock "$OUT/vibe.lock" && step "vibe.lock sha256=$(sha256sum vibe.lock | cut -c1-16) lines=$(wc -l < vibe.lock)"
[ -f vibe.toml ] && cp vibe.toml "$OUT/vibe.toml"
find . -path ./.git -prune -o -type f -print | sort | head -400 > "$OUT/tree.txt"
rm -rf "$OUT/project" && mkdir -p "$OUT/project" && tar --exclude=./.git -cf - . | tar -xf - -C "$OUT/project"
step "files=$(wc -l < "$OUT/tree.txt") boot=$(ls vibevm/vibespecs/boot 2>/dev/null | tr '\n' ' ')"
if [ -n "${ANTHROPIC_API_KEY:-}" ] && command -v claude >/dev/null; then
  step "agent: claude -p"
  claude -p "${AGENT_PROMPT:-Summarize the working rules this project gives you, in five lines.}" >"$OUT/agent.txt" 2>&1; step "agent rc=$?"
else
  step "agent: skipped (no ANTHROPIC_API_KEY / claude not in image)"
fi
step "ready after ${T0:+$(elapsed)}s from container start"
wait
