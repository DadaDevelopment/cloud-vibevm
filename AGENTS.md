# AGENTS.md - how to work with this repo

Goal of the repo: run VibeVM (`vibe`, registry packages, Zap) remotely on Dada Cloud and keep the evidence. Read README.md for status and numbers.

## Run the runner locally or on any container platform
1. `docker build -t cloud-vibevm-runner cloud-runner` (base debian trixie; the `vibe` bootstrap needs glibc 2.39).
2. `docker run --rm -p 8080:8080 cloud-vibevm-runner`. `cloud-runner/run.sh` copies `demo-project/` (a `vibe.toml` + `vibe.lock` for redbook), runs
   `vibe install --assume-yes --quiet`, `vibe check`, then serves `/log.txt`, `/vibe.lock`, `/tree.txt` and `/project/...` (installed files, including
   `vibevm/vibespecs/boot/STATIC.md`) on :8080. Without a `vibe.lock` it bootstraps a new project and installs `org.vibevm.world/redbook`.
3. Optional agent step: set `ANTHROPIC_API_KEY` (the image must contain `claude`; it does not by default) and `AGENT_PROMPT`.
4. To run your own project: replace `cloud-runner/demo-project/` with your project directory containing `vibe.lock`.

## Deploy an image to Dada Cloud with the provider
    export DDC_TOKEN=<Dada Cloud console key>      # never commit it, never print it
    export DADA_PROJECT=<your project> DADA_ALLOW_PROJECT=<same name>
    python3 -I dada_deploy.py apply --name my-app --image <image> --port 8080
Output: one JSON reply envelope on stdout, progress on stderr, receipt in `$DADA_STATE_DIR` (default `~/.vibe-dada-provider`).
You need a Dada Cloud account (https://cloud.dada-tuda.ru); this repo does not provide credentials. `undeploy` only removes what a receipt owns.

## Rules
- Stdlib-only Python; keep it that way.
- Run `python3 -I -m unittest discover -s tests -v` before committing; set `VIBEVM_REPO` to a vibevm checkout to include the 3 schema tests.
- Do not claim something works unless you ran it. README.md separates "works" from "not verified"; keep that split.
- Never commit tokens, kubeconfigs, internal hostnames or customer data. Receipts must contain no secrets.
- Do not create extra projects on Dada Cloud for experiments; reuse one test app and remove it afterwards.
