"""Serialise JSON the way itential/assets stores its exports.

Two-space indent, UTF-8 as-is, no trailing newline, and an array whose items are all
scalars written on one line (`"required": ["deviceName", "_id"]`). Python's json module
always spreads arrays across lines, which made every such array show up as a change in
the diff against upstream. `check()` proves the style by round-tripping upstream files.
"""
import json


def _scalar(v):
    return not isinstance(v, (dict, list))


def dumps(obj, level=0):
    pad, inner = "  " * level, "  " * (level + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(v, level + 1)}" for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if all(_scalar(v) for v in obj):
            return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in obj) + "]"
        return "[\n" + ",\n".join(inner + dumps(v, level + 1) for v in obj) + "\n" + pad + "]"
    return json.dumps(obj, ensure_ascii=False)


def dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(obj))


def check(paths):
    """Return the upstream files this formatter does NOT reproduce byte for byte."""
    bad = []
    for p in paths:
        raw = open(p, encoding="utf-8").read()
        if dumps(json.loads(raw)) != raw.rstrip("\n"):
            bad.append(p)
    return bad
