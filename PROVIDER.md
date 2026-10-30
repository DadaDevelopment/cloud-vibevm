# Deploy provider: `dada_deploy.py`

`dada_deploy.py` deploys a container image to Dada Cloud through the console REST API
(`/api/v1`) and speaks the vibevm lifecycle handler contract: optional context
envelope on stdin, one reply envelope `{"envelope":1,"status":...}` on stdout, log on stderr.
Stdlib only, no dependencies.

## Commands
    DDC_TOKEN=sk-dada-pk-... python3 dada_deploy.py apply --name APP --image IMG [--port 8080]
    python3 dada_deploy.py status --name APP
    python3 dada_deploy.py undeploy --name APP   # only if a receipt exists

- `apply` is idempotent: same image and Ready -> no-op; other image -> image update; no app -> create.
  It waits for the operation, for phase Ready and for the first HTTP answer on the app URL.
- A receipt is written to `$DADA_STATE_DIR` (default `~/.vibe-dada-provider`) in vibevm's
  `schemas/deploy_receipt.jtd.json` epoch-1 shape (scope `remote`, status `verified`/`failed`,
  generation counter, 64-hex digests, no secrets). `undeploy` deletes only a resource the receipt owns.
  Example: `examples/receipt-vibevm-zap.json`.
- Pinned to project `agent-sandbox` (a Dada-internal guard). To use your own project set `DADA_PROJECT=<name>` and,
  as a deliberate human step, `DADA_ALLOW_PROJECT=<same name>`; otherwise the provider refuses before any API call.

## Measured live in a sandbox project on Dada Cloud (2026-10-30)
| step | time |
| --- | --- |
| create from public image (nginx-unprivileged:alpine) -> HTTP 200 | 71 s |
| repeat apply, nothing changed | 5 s |
| image update -> HTTP 200 | 52 s |
| undeploy | 11 s |
Four creates with the tiny image: 71, 76, 59, 64 s.

| Zap (vibevm/vibevm-zap:1.0.7, 238 MB layer) as a second app -> HTTP 200 | 99 s |
The earlier manual deploy of the same image took 5 min 00 s. Corrected reading (see COLD-START.md): the pull is
28-33 s on both nodes (the second run was on a different node, the layer was not cached); the first deploy
spent 4 min 22 s before its pod even existed, and that did not repeat.

## Tests
    python3 -I -m unittest discover -s tests -v        # 13 tests, offline, ~0.05 s
Covered: no-op on converged app, PATCH instead of POST on image change, generation counter,
project guard fires before any API call (and `DADA_ALLOW_PROJECT` must match), undeploy without
receipt deletes nothing, token redacted from error replies, receipt and reply validated against the
vibevm schemas (`VIBEVM_REPO`; skipped if absent) by `tests/jtd.py`,
a small RFC 8927 validator.

## Wiring into vibe.toml (NOT yet run through `vibe`; shape copied from the vibevm fixtures)
    [[extension]]
    id = "dada-cloud-deploy"
    point = "phase:deploy"
    handler = { kind = "script", base = "scripts/deploy" }

`scripts/deploy.sh` is the POSIX entry; a `.ps1` twin is needed for Windows.

## Not done
- Not run through a real `vibe deploy`: building the vibevm CLI from the cloned source
  (`cargo build -p vibe-cli`) was not attempted in the authoring session.
  Needs a prebuilt `vibe` binary or a Rust toolchain.
- artifact_digest is sha256 of the image reference string, not the registry manifest digest.
- Receipt is written by the provider itself; vibevm's engine-owned intent journal and checkpoints
  (`deploy_intent`, `deploy_checkpoints`, `deploy_inverse`) are not produced.
- Deleting an app that this provider did not create is refused by design (no receipt).
