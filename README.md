**Live:** https://cloud.dada-tuda.ru (Dada Cloud, the platform this was run on; this repo has no standalone deployment yet)

# Cloud VibeVM: running VibeVM on Dada Cloud

Experiments by [Dada Development](https://github.com/DadaDevelopment) for [Oleg Chirukhin](https://vibevm.org): can the
`vibe` CLI, the registry packages and the Zap UI run remotely on a PaaS, without changing anything on the VibeVM side?
Everything here was measured on 2026-10-30 against Dada Cloud (https://cloud.dada-tuda.ru). Numbers are real runs,
not estimates; what was **not** verified is listed explicitly.

If you are an agent: read [AGENTS.md](AGENTS.md) first.

## What is in the repo

| path | what | status |
| --- | --- | --- |
| `cloud-runner/` | Docker image of a pod that installs `vibe` (official `install.sh`), runs `vibe install` from a `vibe.lock`, `vibe check`, publishes the result on :8080 | works |
| `dada_deploy.py`, `scripts/deploy.sh` | `phase:deploy` script handler in vibevm's lifecycle-envelope format; deploys an image to Dada Cloud over REST, writes a `deploy_receipt` (epoch 1) | works standalone; **not** run through a real `vibe deploy` |
| `tests/` | 13 offline unit tests + a small RFC 8927 validator for vibevm's JTD schemas | green (3 schema tests need a vibevm checkout) |
| `slim-image/` | Dockerfile for `vibevm/vibevm-zap` without Electron (305 -> ~166 MB) | built and served by the platform; no measurable deploy-time gain |
| `zap-open.sh` | open the Zap UI through `kubectl port-forward` the way the image is designed | untested |
| `ZAP-ACCESS.md` | why the public Zap URL shows a password screen and what a real remote login would need | findings |
| `COLD-START.md` | where deploy time goes (kubelet events) | findings |
| `PROVIDER.md` | provider usage, receipt, wiring into `vibe.toml` | reference |

## Results

**Cloud VibeVM runner** (pod with `vibe` 1.0.7 from the official installer, sha256-verified bootstrap):
- `vibe install` of the 27 redbook packages: 82-115 s (about 10 runs without a lock); with a ready `vibe.lock` two runs reached ready in 82 s and 184 s.
  `vibe check` clean; versions and hashes from `vibe.lock` were applied.
- Image build on the platform: about 2.5 min.
- Agent on top of the installed context (STATIC.md, `git-atomic-commits`, `git-conventional-commits`): the platform's default model broke the main rule
  (one coherent change = one commit) in both answers that arrived. GLM-5.3 followed it in 3 of 3 runs (12.9, 14.7, 17.7 s per answer) with small nits
  (a 62-char subject against a 60 limit, one imprecise body, one debatable split). Claude Code with a top model was not run in the pod.
- Honest floor: there is no warm pool, so start-to-ready-context is about 1.5-2 min, not seconds.

**Deploy provider** (create -> first HTTP 200): 59-76 s for a tiny image (4 runs), 5 s for a repeat apply, 52 s for an image change, 11 s for undeploy.

**Zap** `vibevm/vibevm-zap:1.0.7` on Dada Cloud: 47-99 s to HTTP 200 (first ever deploy: 5 min, of which 4 min 22 s passed before the pod existed; not repeated in 7 later creates, cause unknown).
The image pull itself is 28-33 s. Details: [COLD-START.md](COLD-START.md).

## Zap and the password screen

`vibevm/vibevm-zap` is **Oleg's public image, not a Dada product**. The public URL shows "Secure Web Profile -> Password" because the image
only serves the static UI: `zap-server` binds its gateway to a random loopback port and the UI is meant to be opened on the viewer's own `127.0.0.1`.
No default password exists. A real remote password login needs `quicklens-web/1` config, a broker and four ZAP store connections; the ZAP binary in this build
is read-only (no store creation). Full analysis and the open question for Oleg: [ZAP-ACCESS.md](ZAP-ACCESS.md).

## Open questions for the VibeVM side
1. Licence of `vibe` and the registry packages: may they run in a cloud for third-party users?
2. Are `vibe.lock` and `deploy_receipt` formats stable within 1.x, or still changing in the Developer Preview?
3. An example `quicklens-web/1` config and how to run broker + ZAP services next to `zap-server` in one container.

## Not done
- No real `vibe deploy` run; no engine-owned intent journal / checkpoints in receipts (the provider writes the receipt itself).
- `artifact_digest` is sha256 of the image reference string, not the registry manifest digest.
- `slim-image/smoke.sh` and `zap-open.sh` never ran.
- Windows twin of `scripts/deploy.sh` is missing.

## Quick start
    python3 -I -m unittest discover -s tests -v          # offline, ~0.05 s
    docker build -t cloud-vibevm-runner cloud-runner && docker run --rm -p 8080:8080 cloud-vibevm-runner

Licence: MIT (see LICENSE).
