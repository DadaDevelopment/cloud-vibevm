"""Offline tests for dada_deploy.py: idempotency, the project guard, receipt and
reply conformance to vibevm's epoch-1 schemas.

    python3 -I -m unittest discover -s tests -v

Schema tests need a vibevm checkout (VIBEVM_REPO, default /path/to/vibevm)
and are skipped when it is absent. Nothing here touches the network or a token.
"""
import contextlib, io, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import dada_deploy as dd  # noqa: E402
import jtd  # noqa: E402

REPO = os.environ.get("VIBEVM_REPO", "/path/to/vibevm")
SECRET = "sk-dada-pk-0000000000000000000000000000000000000000"
PID, EID = "p-1", "e-1"


class FakeApi:
    """In-memory stand-in for the console endpoints the provider uses."""

    def __init__(self, projects=("agent-sandbox", "internal")):
        self.apps, self.calls, self.projects = {}, [], projects

    def call(self, method, path, body=None, ok=(200, 201, 202), timeout=30):
        self.calls.append((method, path))
        if (method, path) == ("GET", "/projects"):
            return 200, {"projects": [{"id": PID, "name": n} for n in self.projects]}
        if (method, path) == ("GET", f"/projects/{PID}"):
            return 200, {"environments": [{"id": EID, "name": "prod"}]}
        base = f"/projects/{PID}/environments/{EID}/apps"
        if method == "GET" and path.startswith(base + "?"):
            name = path.split("name=")[1]
            return 200, {"apps": [dict(a) for a in self.apps.values() if name in a["name"]]}
        if method == "POST" and path == base:
            self.apps[body["name"]] = {"name": body["name"], "image": body["image"], "phase": "Ready",
                                       "url": f"https://{body['name']}.example.test"}
            return 202, {"operation": {"id": "op-create", "status": "Committed"}}
        if method == "PATCH" and path.endswith("/image"):
            self.apps[path.split("/")[-2]]["image"] = body["image"]
            return 202, {"operation": {"id": "op-image", "status": "Committed"}}
        if method == "DELETE":
            self.apps.pop(path.split("/")[-1])
            return 202, {"operation": {"id": "op-del", "status": "Committed"}}
        if "/operations/" in path:
            return 200, {"operation": {"id": path.split("/")[-1], "status": "Committed"}}
        raise AssertionError(f"unexpected call {method} {path}")

    def writes(self):
        return [c for c in self.calls if c[0] in ("POST", "PATCH", "DELETE")]


class Args:
    def __init__(self, **kw):
        self.name, self.image, self.port, self.replicas = "probe", "img:1", 8080, 1
        self.env, self.timeout = "prod", 60
        self.__dict__.update(kw)


class ProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._saved = (dd.STATE_DIR, dd.time.sleep, dd.wait_http, dict(os.environ), dd.Api)
        dd.STATE_DIR = self.tmp.name
        dd.time.sleep = lambda s: None
        dd.wait_http = lambda url, timeout: (200, 1)
        os.environ.pop("DADA_PROJECT", None)
        os.environ.pop("DADA_ALLOW_PROJECT", None)
        self.api = FakeApi()

    def tearDown(self):
        dd.STATE_DIR, dd.time.sleep, dd.wait_http, _, dd.Api = self._saved
        os.environ.clear(); os.environ.update(self._saved[3])

    def run_cmd(self, fn, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                fn(self.api, Args(**kw))
        return json.loads(out.getvalue()), cm.exception.code

    def receipt(self, name="probe"):
        with open(dd.receipt_path("agent-sandbox", "prod", name)) as f:
            return json.load(f)

    # --- idempotency -------------------------------------------------------
    def test_second_apply_is_a_noop(self):
        r1, c1 = self.run_cmd(dd.apply)
        self.assertEqual((r1["status"], c1), ("ok", 0))
        self.assertIn("create", r1["message"])
        n = len(self.api.writes())
        r2, _ = self.run_cmd(dd.apply)
        self.assertEqual(r2["status"], "ok")
        self.assertIn("noop", r2["message"])
        self.assertEqual(len(self.api.writes()), n, "a converged app must cause no writes")

    def test_changed_image_patches_instead_of_creating(self):
        self.run_cmd(dd.apply)
        self.run_cmd(dd.apply, image="img:2")
        verbs = [c[0] for c in self.api.writes()]
        self.assertEqual(verbs, ["POST", "PATCH"])
        self.assertEqual(self.api.apps["probe"]["image"], "img:2")

    def test_generation_increments(self):
        self.run_cmd(dd.apply)
        self.assertEqual(self.receipt()["generation"], 1)
        self.run_cmd(dd.apply, image="img:2")
        self.assertEqual(self.receipt()["generation"], 2)

    # --- project guard -----------------------------------------------------
    def test_foreign_project_is_refused_before_any_call(self):
        os.environ["DADA_PROJECT"] = "internal"
        r, code = self.run_cmd(dd.apply)
        self.assertEqual((r["status"], code), ("fail", 2))
        self.assertIn("pinned", r["message"])
        self.assertEqual(self.api.calls, [], "the guard must fire before the API is touched")

    def test_allow_must_name_the_same_project(self):
        os.environ["DADA_PROJECT"] = "internal"
        os.environ["DADA_ALLOW_PROJECT"] = "platform"
        r, code = self.run_cmd(dd.apply)
        self.assertEqual((r["status"], code), ("fail", 2))
        self.assertEqual(self.api.calls, [])

    def test_explicit_allow_by_a_human_lifts_the_guard(self):
        os.environ["DADA_PROJECT"] = "internal"
        os.environ["DADA_ALLOW_PROJECT"] = "internal"
        r, _ = self.run_cmd(dd.apply)
        self.assertEqual(r["status"], "ok")

    # --- undeploy ownership ------------------------------------------------
    def test_undeploy_without_receipt_deletes_nothing(self):
        self.api.apps["foreign"] = {"name": "foreign", "image": "x", "phase": "Ready", "url": "u"}
        r, _ = self.run_cmd(dd.undeploy, name="foreign")
        self.assertEqual(r["status"], "skip")
        self.assertIn("foreign", self.api.apps)
        self.assertEqual(self.api.writes(), [])

    def test_undeploy_removes_owned_app_and_receipt(self):
        self.run_cmd(dd.apply)
        r, _ = self.run_cmd(dd.undeploy)
        self.assertEqual(r["status"], "ok")
        self.assertNotIn("probe", self.api.apps)
        self.assertFalse(os.path.exists(dd.receipt_path("agent-sandbox", "prod", "probe")))

    def test_token_is_redacted_from_error_replies(self):
        class Leaky:
            def __init__(self, token):
                self.token = token

            def call(self, *a, **kw):
                raise RuntimeError(f"upstream echoed Authorization: Bearer {self.token}")

        os.environ["DDC_TOKEN"] = SECRET
        dd.Api, saved_argv, saved_in = Leaky, sys.argv, sys.stdin
        sys.argv = ["dada_deploy.py", "status", "--name", "probe"]
        sys.stdin = io.StringIO("")
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    dd.main()
        finally:
            sys.argv, sys.stdin = saved_argv, saved_in
        self.assertEqual(cm.exception.code, 1)
        self.assertNotIn(SECRET, out.getvalue())
        self.assertIn("***", out.getvalue())

    def test_receipt_holds_no_secret(self):
        os.environ["DDC_TOKEN"] = SECRET
        self.run_cmd(dd.apply)
        self.assertNotIn(SECRET, json.dumps(self.receipt()))

    # --- schema conformance ------------------------------------------------
    def _schema(self, rel):
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            self.skipTest(f"{p} not found; set VIBEVM_REPO")
        with open(p) as f:
            return json.load(f)

    def test_receipt_matches_deploy_receipt_schema(self):
        schema = self._schema("schemas/deploy_receipt.jtd.json")
        self.run_cmd(dd.apply)
        rec = self.receipt()
        self.assertEqual(jtd.validate(schema, rec), [])
        for k in ("artifact_digest", "desired_config_digest"):
            self.assertRegex(rec[k], r"^[0-9a-f]{64}$")
        self.assertRegex(rec["profile"], r"^[a-z0-9][a-z0-9._-]{0,63}$")
        self.assertRegex(rec["target"], r"^[a-z0-9][a-z0-9._-]{0,63}$")

    def test_schema_validator_rejects_a_broken_receipt(self):
        schema = self._schema("schemas/deploy_receipt.jtd.json")
        self.run_cmd(dd.apply)
        bad = self.receipt()
        bad["scope"], bad["extra"] = "cloud", 1
        del bad["status"]
        errs = jtd.validate(schema, bad)
        self.assertTrue(any("scope" in e for e in errs) and any("extra" in e for e in errs)
                        and any("status" in e for e in errs), errs)

    def test_reply_matches_lifecycle_reply_schema(self):
        schema = self._schema("schemas/lifecycle/e1/reply.jtd.json")
        vocab = self._schema("formats/vocabularies.json")
        defs = vocab.get("definitions", vocab)
        for fn, kw in ((dd.apply, {}), (dd.undeploy, {}), (dd.undeploy, {"name": "nope"})):
            r, _ = self.run_cmd(fn, **kw)
            self.assertEqual(jtd.validate(schema, r, defs), [], r)


if __name__ == "__main__":
    unittest.main()
