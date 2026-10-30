# syntax=docker/dockerfile:1
# DRAFT - NOT BUILT, NOT PUSHED. Slim server image for Zap: the same files as
# vibevm/vibevm-zap, minus what zap-server never loads.
#
# Removed (sizes from the 1.0.7 layer, gzip):
#   node_modules/electron           117 MB   desktop shell; the only reference outside
#                                            dist/quicklens/electron/ is a dynamic
#                                            require("electron") behind `zap-quicklens --electron`
#                                            (dist/zap-quick-lens.js:262)
#   node_modules/@electron*           1 MB   helpers of the same package
#   node-pty/prebuilds/*             13 MB   win32 / darwin only; linux uses build/Release/pty.node
# Expected: 305 MB -> ~166 MB compressed (-46 %). Note: pull latency is only ~28 s of a ~100 s deploy, see COLD-START.md.
#
# Why a second stage onto scratch: deleting files in a RUN layer only hides them, the
# original 238 MB layer would still be pulled. Copying the pruned filesystem into one fresh
# layer is what actually shrinks the pull. Trade-off: one big layer, so no layer reuse
# between versions.
ARG ZAP_TAG=1.0.7

FROM vibevm/vibevm-zap:${ZAP_TAG} AS prune
USER root
RUN set -eu; \
    G="$(ls -d /home/vibe/.vibe/opt/apps/zap/generations/*)"; \
    N="$G/payload/app/node_modules"; \
    rm -rf "$N/electron" "$N/@electron" "$N/@electron-internal" "$N/node-pty/prebuilds"; \
    test -f "$N/node-pty/build/Release/pty.node"; \
    if grep -rq 'require("electron")' "$G/payload/app/dist" --include=*.js \
         --exclude-dir=electron --exclude=zap-quick-lens.js; then \
      echo "another module requires electron - do not prune it" >&2; exit 1; \
    fi

FROM scratch
COPY --from=prune / /
ENV PATH=/home/vibe/.vibe/opt/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIBE_SETTINGS=/home/vibe/.vibe \
    ZAP_STATE_DIR=/home/vibe/zap-state
USER vibe
EXPOSE 8080
CMD ["vibevm-zap"]
