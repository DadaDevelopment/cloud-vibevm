#!/usr/bin/env python3
"""Dada Cloud deploy provider for a VibeVM `phase:deploy` script handler.

Stdlib only. The handler contract it follows (schemas/lifecycle/e1 in vibevm):
  stdin  : optional lifecycle context envelope (JSON, epoch 1) - only
           `point` and `project` are read, unknown fields are ignored
  stdout : exactly one reply envelope {"envelope":1,"status":"ok|fail|skip",
           "artifacts":[{"id","path","kind"}],"tasks":[],"message":"..."}
  stderr : progress log (never contains the token)

Usage:
  dada_deploy.py apply    --image IMG --name APP --port N [--env prod] [--replicas 1]
  dada_deploy.py status   --name APP
  dada_deploy.py undeploy --name APP        (removes only what the receipt owns)

Auth: DDC_TOKEN (a console key, sk-dada-pk-...). Base URL: DADA_API
(default https://console.dada-tuda.ru/api/v1). Project is pinned to the
sandbox on purpose: DADA_PROJECT defaults to agent-sandbox and any other value
is refused unless DADA_ALLOW_PROJECT=<same value> is also set by a human.
"""
import argparse, hashlib, json, os, sys, time, urllib.error, urllib.request

API = os.environ.get("DADA_API", "https://console.dada-tuda.ru/api/v1").rstrip("/")
SANDBOX = "agent-sandbox"
PROVIDER_VERSION = "0.2.0"
STATE_DIR = os.environ.get("DADA_STATE_DIR", os.path.expanduser("~/.vibe-dada-provider"))
TERMINAL_OK = {"Ready", "Committed", "Succeeded", "Done"}
TERMINAL_BAD = {"Failed", "Cancelled", "Rejected"}


def log(msg):
    print(f"[dada-deploy] {msg}", file=sys.stderr, flush=True)


def reply(status, message, artifacts=None, code=0):
    print(json.dumps({"envelope": 1, "status": {"ok": "ok", "fail": "fail", "skip": "skip"}[status],
                      "artifacts": artifacts or [], "tasks": [], "message": message}, ensure_ascii=False))
    sys.exit(code)


class Api:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None, ok=(200, 201, 202), timeout=30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            payload = {"raw": raw[:200].decode("utf-8", "replace")}
        if code not in ok:
            raise RuntimeError(f"{method} {path} -> {code} {json.dumps(payload, ensure_ascii=False)[:300]}")
        return code, payload


def resolve(api, env_name):
    project = os.environ.get("DADA_PROJECT", SANDBOX)
    if project != SANDBOX and os.environ.get("DADA_ALLOW_PROJECT") != project:
        reply("fail", f"refusing project '{project}': this provider is pinned to {SANDBOX}", code=2)
    _, d = api.call("GET", "/projects")
    proj = next((p for p in d["projects"] if p["name"] == project), None)
    if not proj:
        reply("fail", f"project '{project}' is not visible to this key", code=2)
    _, d = api.call("GET", f"/projects/{proj['id']}")
    env = next((e for e in d["environments"] if e["name"] == env_name), None)
    if not env:
        reply("fail", f"environment '{env_name}' not found in {project}", code=2)
    return proj["id"], env["id"]


def find_app(api, pid, eid, name):
    _, d = api.call("GET", f"/projects/{pid}/environments/{eid}/apps?view=summary&name={name}")
    return next((a for a in d.get("apps", []) if a["name"] == name), None)


def wait_op(api, pid, op, timeout):
    op_id = op.get("id") if isinstance(op, dict) else None
    if not op_id:
        return None
    t0, last = time.time(), None
    while time.time() - t0 < timeout:
        _, d = api.call("GET", f"/projects/{pid}/operations/{op_id}")
        o = d.get("operation", d)
        st = o.get("status") or o.get("phase")
        if st != last:
            log(f"operation {op_id[:8]} {st} (+{int(time.time() - t0)}s)")
            last = st
        if st in TERMINAL_BAD:
            raise RuntimeError(f"operation {op_id} ended {st}: {str(o.get('error') or o.get('message') or '')[:200]}")
        if st in TERMINAL_OK:
            return st
        time.sleep(5)
    raise RuntimeError(f"operation {op_id} still '{last}' after {timeout}s")


def wait_http(url, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status, int(time.time() - t0)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 404:
                return e.code, int(time.time() - t0)
        except Exception:
            pass
        time.sleep(5)
    return None, int(time.time() - t0)


def receipt_path(project, env, name):
    return os.path.join(STATE_DIR, f"{project}.{env}.{name}.receipt.json")


def sha256_hex(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def now_rfc3339():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def prior_generation(project, env, name):
    try:
        with open(receipt_path(project, env, name)) as f:
            return json.load(f).get("generation", 0)
    except (OSError, ValueError):
        return 0


def build_receipt(project, a, url, action, http_code, seconds, prior):
    """A schemas/deploy_receipt.jtd.json (epoch 1) record. Digests are 64 hex.

    artifact_digest is sha256 of the image reference string, not the registry
    manifest digest (the registry is not asked); desired_config_digest covers
    everything this provider reconciles. No secret ever enters the record.
    """
    config = {"project": project, "env": a.env, "app": a.name, "image": a.image,
              "port": a.port, "replicas": a.replicas}
    resource = f"dada:{project}/{a.env}/{a.name}"
    verified = http_code is not None
    with open(os.path.abspath(__file__), "rb") as f:
        own_hash = sha256_hex(f.read())
    ts = now_rfc3339()
    rec = {
        "schema": 1,
        "identity": {"project": project},
        "profile": os.environ.get("DADA_PROFILE", "default"),
        "target": "dada-cloud",
        "generation": prior + 1,
        "artifact_digest": sha256_hex(a.image),
        "provider": {"key": "org.dada/cloud", "version": PROVIDER_VERSION, "content_hash": own_hash},
        "desired_config_digest": sha256_hex(json.dumps(config, sort_keys=True, separators=(",", ":"))),
        "scope": "remote",
        "resources": [{"resource": resource, "post_digest": sha256_hex(f"{resource}|{a.image}|{url}")}],
        "reversible": True,
        "applied_at": ts,
        "status": "verified" if verified else "failed",
        "evidence": f"{action}: GET {url} -> {http_code} after {seconds}s" if verified
                    else f"{action}: {url} never answered after {seconds}s",
        "finalized_at": ts,
    }
    return rec


def write_receipt(project, env, name, rec):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = receipt_path(project, env, name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1)
    os.replace(tmp, receipt_path(project, env, name))


def apply(api, a):
    t0 = time.time()
    pid, eid = resolve(api, a.env)
    project = os.environ.get("DADA_PROJECT", SANDBOX)
    app = find_app(api, pid, eid, a.name)
    base = f"/projects/{pid}/environments/{eid}/apps"
    if app and app.get("image") == a.image and app.get("phase") == "Ready":
        log("already at desired image and Ready - nothing to do")
        action = "noop"
    elif app:
        log(f"app exists with image {app.get('image')} -> updating to {a.image}")
        _, d = api.call("PATCH", f"{base}/{a.name}/image", {"image": a.image})
        wait_op(api, pid, d.get("operation"), a.timeout)
        action = "update"
    else:
        log(f"creating {a.name} from {a.image}:{a.port}")
        _, d = api.call("POST", base, {"name": a.name, "image": a.image, "port": a.port, "replicas": a.replicas})
        wait_op(api, pid, d.get("operation"), a.timeout)
        action = "create"
    url, phase = None, None
    while time.time() - t0 < a.timeout:
        app = find_app(api, pid, eid, a.name)
        phase, url = (app or {}).get("phase"), (app or {}).get("url")
        if phase == "Ready" and url:
            break
        time.sleep(5)
    if phase != "Ready":
        reply("fail", f"{a.name} not Ready after {a.timeout}s (phase={phase})", code=1)
    code, http_s = wait_http(url, max(30, a.timeout - int(time.time() - t0)))
    total = int(time.time() - t0)
    rec = build_receipt(project, a, url, action, code, total, prior_generation(project, a.env, a.name))
    write_receipt(project, a.env, a.name, rec)
    if code is None:
        reply("fail", f"{a.name} Ready but {url} never answered (action={action}, {total}s)", code=1)
    reply("ok", f"{action} {a.name}: HTTP {code} at {url} in {total}s",
          [{"id": f"dada:{project}/{a.env}/{a.name}", "path": url, "kind": "deployment"}])


def undeploy(api, a):
    project = os.environ.get("DADA_PROJECT", SANDBOX)
    rp = receipt_path(project, a.env, a.name)
    if not os.path.exists(rp):
        reply("skip", f"no receipt for {a.name}: refusing to delete what this provider does not own")
    with open(rp) as f:
        owned = [r["resource"] for r in json.load(f).get("resources", [])]
    if f"dada:{project}/{a.env}/{a.name}" not in owned:
        reply("skip", f"receipt for {a.name} does not own it: refusing to delete")
    pid, eid = resolve(api, a.env)
    if not find_app(api, pid, eid, a.name):
        os.remove(rp)
        reply("skip", f"{a.name} already gone")
    _, d = api.call("DELETE", f"/projects/{pid}/environments/{eid}/apps/{a.name}")
    wait_op(api, pid, d.get("operation"), a.timeout)
    t0 = time.time()
    while time.time() - t0 < a.timeout and find_app(api, pid, eid, a.name):
        time.sleep(5)
    if find_app(api, pid, eid, a.name):
        reply("fail", f"{a.name} still listed after delete", code=1)
    os.remove(rp)
    reply("ok", f"removed {project}/{a.env}/{a.name}")


def status(api, a):
    pid, eid = resolve(api, a.env)
    app = find_app(api, pid, eid, a.name)
    reply("ok" if app else "skip", json.dumps(app or {"app": a.name, "found": False}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["apply", "undeploy", "status"])
    p.add_argument("--name", required=True)
    p.add_argument("--image")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--replicas", type=int, default=1)
    p.add_argument("--env", default="prod")
    p.add_argument("--timeout", type=int, default=900)
    a = p.parse_args()
    if not sys.stdin.isatty():
        try:
            ctx = json.loads(sys.stdin.read() or "{}")
            log(f"context point={ctx.get('point')} project={json.dumps(ctx.get('project'))[:80]}")
        except ValueError:
            log("stdin was not a JSON envelope - ignored")
    token = os.environ.get("DDC_TOKEN")
    if not token:
        reply("fail", "DDC_TOKEN is not set", code=2)
    if a.cmd == "apply" and not a.image:
        reply("fail", "--image is required for apply", code=2)
    api = Api(token)
    try:
        {"apply": apply, "undeploy": undeploy, "status": status}[a.cmd](api, a)
    except RuntimeError as e:
        reply("fail", str(e).replace(token, "***"), code=1)


if __name__ == "__main__":
    main()
