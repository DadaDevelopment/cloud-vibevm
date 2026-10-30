# Getting into Zap on Dada Cloud

State on 2026-10-30. The image `vibevm/vibevm-zap:1.0.7` is Oleg Chirukhin's public vibevm image, not a Dada product; we only run it.
Source of facts: the public image `vibevm/vibevm-zap:1.0.7` (layers read, nothing run), not the closed `vibevm/zap` repo.

## Why the public URL shows "Secure Web Profile -> Password"
- `CMD vibevm-zap` is a 15-line shell script: it starts `zap-server`, waits for `127.0.0.1:4174`,
  then `socat` forwards `0.0.0.0:8080 -> 127.0.0.1:4174`. That is the **static UI only**.
- `zap-server` also starts the Wayfinder gateway on a **random loopback port** (`port: 0`) with a
  one-time pairing ticket. The UI attaches to it from the browser through
  `/?workspace-gateway=http://127.0.0.1:PORT/...#workspace-pair=TICKET`. Gateway CORS allows only
  `http://127.0.0.1:4174` and `quicklens://app`. So the page must be served from, and talk to, the
  viewer's own 127.0.0.1. A public HTTPS URL cannot satisfy that by design.
- With no gateway in the URL the UI falls back to the web-profile login. There is no default
  password: `zap-server` never mounts the web gateway (`/api/v1/login` -> 404 on both apps).

## Way in that works with the image as shipped (needs kubectl, untested)
`zap-open.sh` in this folder does: `kubectl exec ... zap-quicklens --no-open` (attaches to the running
owner, prints a fresh pairing URL), parses the gateway port, port-forwards `4174` and that port,
opens the URL. Everything stays on your machine; nothing public.
Not run end to end by the authors (no kubectl in the authoring session). Treat the exact flags as unverified.

## A real remote login (password) - what it takes
The `quicklens-web` entry exists in the image but needs things the image does not contain.
`QUICKLENS_WEB_CONFIG_FILE` must be a strict `quicklens-web/1` JSON:

| key | what | where from |
| --- | --- | --- |
| `source.protocol`, `workspaceId`, `conversationId` | ids | choose |
| `source.broker.endpoint` + `humanPrincipalToken` | Quicklens broker | **not in image** |
| `source.zap.{reader,data,coordinator,owner}` each `{endpoint, credentialId, bearer}` | four ZAP service connections | **not in image** |
| `source.workflowDatabasePath`, `specifications[]` | sqlite path, spec roots | choose |
| `auth.verifierPath` | password verifier file | `quicklens-web-auth init` (accepts piped stdin when not a TTY) |
| `gateway.publicOrigin` (https), `proxyProofToken` (24-512 chars), `host` (loopback only), `port`, `role`, `allowedOperations` | web gateway | choose |

Plus a reverse proxy in front of the loopback listener that injects `X-Quicklens-Proxy-Proof`,
`X-Forwarded-Proto: https` and the exact `X-Forwarded-Host`. The README says the package "does not
install or launch a tunnel". The broker and the four ZAP connections are the blocker: they describe
services of Oleg's stack, and no example config ships in the image (`WAYFINDER-GUIDE.md` is absent).

### What the image does and does not contain for this (checked 2026-10-30)
- The **broker** is in the image: `codlens setup '{"workspaceId":..,"conversationId":..}'` creates the
  database and a credential file (agent + human responder principals), `codlens start` serves it
  (`CODLENS_DATABASE_PATH`, `CODLENS_CREDENTIAL_FILE`, `CODLENS_STATUS_TOKEN`, `CODLENS_PORT`).
  The human responder token is the `source.broker.humanPrincipalToken` of the web config.
- The password verifier is `quicklens-web-auth init` (reads the password from stdin when not a TTY).
- The four ZAP connections (`reader`, `data`, `coordinator`, `owner`, each `{endpoint, credentialId, bearer}`)
  point at a **ZAP store service**, which is the Rust binary `zap`. In this build `zap capabilities` reports
  only read operations (`snapshot`, `events`, `query`, `serve`, `follow`) and **no command operations**;
  `serve-runtime`, `import-legacy`, `rebuild-indexes` are "not registered". So the image can serve an existing
  store read-only but cannot create or populate one, and `zap serve <read-config.json>` refuses a guessed
  config with a deliberately generic diagnostic (no field names). Config structure is not documented anywhere
  in the image.
- Result: a password login backed by real planning data cannot be assembled from `vibevm/vibevm-zap:1.0.7`
  alone. It needs a ZAP build with store creation (or a seeded store) and the service config from the vendor.
  Everything else in the chain (broker, auth verifier, web gateway) is present.

**Ask for Oleg** (one message): "Give me an example `quicklens-web/1` config and how to start the
broker + ZAP data services next to `zap-server` in one container, so that `vibevm-zap` can serve the
web profile on :8080 with a password." With that, the start command + env secrets on the platform
(`updateAppStartCommand`, `setEnvVar secret`) are enough; no platform change is needed.
