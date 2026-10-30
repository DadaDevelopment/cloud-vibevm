# Zap on Dada Cloud: where the time goes (corrected 2026-10-30)

> **Correction.** The first version of this file blamed the 5-minute first deploy on the image pull
> (~200 s, "docker.io is throttled"). Kubelet events say otherwise: the image pulls in **28-33 s**.
> The 5 minutes were mostly a ~4-minute wait *before the pod existed*. The pre-pull DaemonSet and the
> slim image proposed earlier therefore buy 15-30 s, not 200 s.

Image `vibevm/vibevm-zap:1.0.7`, profile `small`, a sandbox project on Dada Cloud (4-node cluster).

## Timeline from the cluster itself
| | first deploy `vibevm-zap` | provider deploy `vibevm-zap-prov` |
| --- | --- | --- |
| createApp | 20:31:37 | 00:43:46 |
| pod created / scheduled | 20:35:59 (**+4 min 22 s**) | 00:44:17 (+31 s) |
| image pulled, container started | 20:36:32 (pull ~33 s) | 00:44:46 (pull **27.7 s**, 304 329 868 B) |
| first HTTP 200 seen | ~5 min 00 s | 99 s |
| node | f675c9 | b2a7cd-7dllw (a different node: the layers were NOT cached) |

Pod Ready fires the instant the container starts (no readiness probe), so ~36 s of the second run
after "started" is Zap itself coming up on 127.0.0.1:4174 (socat only opens :8080 once it does) plus
ingress/DNS.

## Platform floor, measured with a tiny image (nginx-unprivileged:alpine, provider, create -> HTTP 200)
71 s, 76 s, 59 s, 64 s (n = 4); image update on a running app 52 s; undeploy 11 s.
So a new app costs **60-75 s** before the image or the app matter. Zap adds pull (~30 s) and start (~10-35 s): **~100 s**.
The one outlier is the very first Zap deploy (262 s before the pod). It did not repeat in 7 later creates.
Cause not established; the app-set Git generator polling is a candidate but I did not verify it.

## What this means for the earlier proposals
| proposal | real saving | verdict |
| --- | --- | --- |
| Pre-pull DaemonSet on all 4 nodes (a pre-pull DaemonSet) | ~28 s of ~100 s, ~650 MB per node | **not worth it; not enabled** |
| Slim image (no electron / foreign node-pty prebuilds): 305 -> ~166 MB | ~13 s of pull (28 s * 0.46) | nice for storage and rate limits, not for latency |
| Looking for the 4-minute pre-pod delay | up to ~260 s, but it happened once | the only thing that could matter; needs the app-set / Argo logs from that moment |

## Image contents (still true, for the slim-image work)
9 layers, 304.8 MB; one layer 237.9 MB. Inside it (624 MB raw, 222 MB gzip): `node_modules/electron`
283 MB raw / 117 MB gz; non-linux `node-pty/prebuilds` 57 MB / 13 MB; `payload/node/bin/node` 125 MB / 44 MB;
`payload/bin/zap` 35 MB / 10 MB. The only reference to electron outside `dist/quicklens/electron/` is the dynamic
`require("electron")` at `zap-quick-lens.js:262`.

## Slim image: built and measured (2026-10-30)
No Docker daemon here, so the platform built it: a throwaway app linked to a Git repo with this directory (`root_dir` = `slim-image`), `triggerBuild` -> success in 1 min 54 s,
image pushed to the project's registry path. The app came up Ready and served the same `index.html` as the original
(HTTP 200, 1131 B, byte-identical). The app was deleted afterwards.

Deploy time through the provider, create -> HTTP 200 (same node pool, run order as listed):

| image | runs, s |
| --- | --- |
| `vibevm/vibevm-zap:1.0.7` (original) | 82, 52 (earlier single run: 99) |
| slim, from the project's registry | 82, 47, 63, 57 |

The spread inside one image (47-82 s) is larger than the gap between images, so the slim image does not
measurably speed up deploy. Consistent with the pull decomposition above (28-33 s pull, ~13 s saved at best).
Worth doing only for storage / registry rate limits. Not checked: that Zap itself (not only the static UI port)
still starts everything it needs without Electron; `slim-image/smoke.sh` was not run.

## Platform bug found while measuring
Re-creating an app under a name that was deleted minutes earlier fails:
`POST .../apps -> 500 {"error":"failed to record default hostname"}` (3 of 3 tries with the name
`ddc-provider-probe`). Fresh names (`ddc-lat-1..3`) work.

Cause: `DeleteApp` demotes the managed `domain_hostnames` row to `failed`, and the table allows one managed row per
(environment, app) (`uniq_domain_hostnames_managed_env_app`); `CreateApp` minted a new random hostname and hit that
index (23505), which the insert's `ON CONFLICT (hostname)` does not cover. Fixed in the Dada Cloud console (merged): `CreateApp` reuses the surviving row's hostname and resets it to `pending`.
Verified on prod 2026-10-30 02:17-02:20 UTC in a sandbox project: create, delete, create again under
`ddc-provider-probe` -> both creates HTTP 200 (95 s and 47 s), same URL
the same URL; app removed afterwards.

## Blocked / not done
- Not enabled: a node pre-pull of the image (it would save ~28 s of ~100 s).
