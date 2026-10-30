"""Tiny RFC 8927 (JSON Type Definition) validator, stdlib only.

Covers the forms the vibevm lifecycle/deploy schemas use: ref, type, enum,
elements, values, properties/optionalProperties (extra keys rejected).
"""
import re

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$")


def validate(schema, instance, extra_defs=None):
    defs = dict(extra_defs or {})
    defs.update(schema.get("definitions", {}))
    errors = []
    _walk(schema, instance, defs, "", errors, root=True)
    return errors


def _type_ok(t, v):
    if t == "string":
        return isinstance(v, str)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "timestamp":
        return isinstance(v, str) and bool(_TS.match(v))
    if t in ("uint8", "uint16", "uint32", "int8", "int16", "int32"):
        return isinstance(v, int) and not isinstance(v, bool) and (v >= 0 if t.startswith("u") else True)
    if t in ("float32", "float64"):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return False


def _walk(s, v, defs, path, errors, root=False):
    if "ref" in s and not (root and False):
        target = defs.get(s["ref"])
        if target is None:
            errors.append(f"{path or '/'}: unknown ref {s['ref']}")
            return
        _walk(target, v, defs, path, errors)
        return
    if "type" in s:
        if not _type_ok(s["type"], v):
            errors.append(f"{path or '/'}: not a {s['type']}: {v!r}")
    elif "enum" in s:
        if v not in s["enum"]:
            errors.append(f"{path or '/'}: {v!r} not in {s['enum']}")
    elif "elements" in s:
        if not isinstance(v, list):
            errors.append(f"{path or '/'}: not an array")
            return
        for i, x in enumerate(v):
            _walk(s["elements"], x, defs, f"{path}/{i}", errors)
    elif "values" in s:
        if not isinstance(v, dict):
            errors.append(f"{path or '/'}: not an object")
            return
        for k, x in v.items():
            _walk(s["values"], x, defs, f"{path}/{k}", errors)
    elif "properties" in s or "optionalProperties" in s:
        if not isinstance(v, dict):
            errors.append(f"{path or '/'}: not an object")
            return
        req, opt = s.get("properties", {}), s.get("optionalProperties", {})
        for k in req:
            if k not in v:
                errors.append(f"{path}/{k}: required key missing")
        for k, x in v.items():
            if k in req:
                _walk(req[k], x, defs, f"{path}/{k}", errors)
            elif k in opt:
                _walk(opt[k], x, defs, f"{path}/{k}", errors)
            elif not s.get("additionalProperties"):
                errors.append(f"{path}/{k}: unexpected key")
