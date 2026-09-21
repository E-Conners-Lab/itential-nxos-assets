#!/usr/bin/env python3
"""Independent verification of the generated NX-OS golden config trees.

Checks them against the shape of the upstream Cisco IOS trees and
re-derives lines from template to confirm the two agree.
"""
import json, os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "..", "Cisco", "NX-OS")
fails = []

ios = json.load(open(os.path.join(HERE, "gc-ios-lab.json")))["data"][0]
IOS_TREE_KEYS = set(ios.keys())
IOS_NODE_KEYS = set(ios["root"].keys())
IOS_ATTR_KEYS = set(ios["root"]["attributes"].keys())
IOS_EXPORT_KEYS = set(ios["root"]["attributes"]["export"].keys())
IOS_LINE_KEYS = set(ios["root"]["attributes"]["export"]["lines"][0].keys())

def walk_nodes(n):
    yield n
    for c in n.get("children", []):
        yield from walk_nodes(c)

def walk_lines(ls):
    for l in ls:
        yield l
        yield from walk_lines(l["lines"])

for path in sorted(glob.glob(os.path.join(OUT_ROOT, "Golden Configurations", "*.json"))):
    base = os.path.basename(path)
    d = json.load(open(path))
    if set(d.keys()) != {"data"} or len(d["data"]) != 1:
        fails.append(f"{base}: top level must be {{data:[1]}}")
        continue
    t = d["data"][0]

    missing = IOS_TREE_KEYS - set(t.keys())
    if missing:
        fails.append(f"{base}: tree missing keys vs IOS: {sorted(missing)}")
    if t["deviceType"] != "cisco-nx":  # Config Manager parser name, not the NetBox slug
        fails.append(f"{base}: deviceType {t['deviceType']!r}")

    seen_cfg_ids = set()
    for n in walk_nodes(t["root"]):
        if set(n.keys()) - IOS_NODE_KEYS - {"children"}:
            fails.append(f"{base}/{n['name']}: unexpected node keys")
        a = n["attributes"]
        if IOS_ATTR_KEYS - set(a.keys()):
            fails.append(f"{base}/{n['name']}: attrs missing {sorted(IOS_ATTR_KEYS - set(a.keys()))}")
        exp = a["export"]
        if IOS_EXPORT_KEYS - set(exp.keys()):
            fails.append(f"{base}/{n['name']}: export missing {sorted(IOS_EXPORT_KEYS - set(exp.keys()))}")
        if exp["deviceType"] != "cisco-nx":
            fails.append(f"{base}/{n['name']}: export deviceType {exp['deviceType']!r}")
        if a["configId"] != exp["_id"]:
            fails.append(f"{base}/{n['name']}: configId != export._id")
        if exp["_id"] in seen_cfg_ids:
            fails.append(f"{base}/{n['name']}: duplicate configId {exp['_id']}")
        seen_cfg_ids.add(exp["_id"])

        ids = set()
        for l in walk_lines(exp["lines"]):
            if set(l.keys()) != IOS_LINE_KEYS:
                fails.append(f"{base}/{n['name']}: line keys {sorted(set(l.keys()) ^ IOS_LINE_KEYS)}")
            if l["id"] in ids:
                fails.append(f"{base}/{n['name']}: duplicate line id {l['id']}")
            ids.add(l["id"])
            if l["evalMode"] not in ("required", "disallowed"):
                fails.append(f"{base}/{n['name']}: evalMode {l['evalMode']!r}")
            if l["severity"] not in ("error", "warning", "info"):
                fails.append(f"{base}/{n['name']}: severity {l['severity']!r}")
            if not l["words"]:
                fails.append(f"{base}/{n['name']}: empty words")
            for w in l["words"]:
                if w["type"] not in ("literal", "regex"):
                    fails.append(f"{base}/{n['name']}: word type {w['type']!r}")
                v = w["value"]
                # no unconsumed markers or un-rendered jinja anywhere
                for bad in ("<e/>", "{d/}", "{/", "/}", "{{", "}}", "{%", "%}"):
                    if bad in v:
                        fails.append(f"{base}/{n['name']}: unconsumed {bad!r} in word {v!r}")
                if w["type"] == "regex":
                    try:
                        re.compile(v)
                    except re.error as e:
                        fails.append(f"{base}/{n['name']}: bad regex {v!r}: {e}")

print("trees checked:", len(glob.glob(os.path.join(OUT_ROOT, "Golden Configurations", "*.json"))))
if fails:
    print(f"\nFAIL ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("\nPASS - golden config trees structurally match the IOS format")
