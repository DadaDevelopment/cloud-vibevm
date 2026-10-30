# syntax=docker/dockerfile:1
# Cloud VibeVM runner: a pod that installs a project's vibe.lock and exposes the result.
# vibe comes from the official installer (https://vibevm.org/install.sh, sha256-verified bootstrap).
FROM debian:trixie-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git python3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 -s /bin/bash vibe
USER vibe
WORKDIR /home/vibe
ENV VIBE_SETTINGS=/home/vibe/.vibe \
    PATH=/home/vibe/.vibe/opt/bin:/home/vibe/.vibe/bin:/home/vibe/.local/bin:/usr/local/bin:/usr/bin:/bin
RUN curl -fsSL https://vibevm.org/install.sh | bash \
 && command -v vibe && vibe --version
COPY --chown=vibe:vibe run.sh serve.py /home/vibe/
COPY --chown=vibe:vibe demo-project /home/vibe/project-src
EXPOSE 8080
CMD ["bash", "/home/vibe/run.sh"]
