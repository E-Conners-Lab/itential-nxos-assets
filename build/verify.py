#!/usr/bin/env python3
"""Independent structural verification of the built NX-OS project.

Reads only the output file -- it shares no state with the build scripts.
"""
import json, re, os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "..", "Cisco", "NX-OS")
IOS_ID = "66d0304521161b4df2717497"
OUT = os.path.join(OUT_ROOT, "Studio Projects", "Cisco NX-OS.project.json")

with open(OUT) as f:
    p = json.load(f)

fails, warns = [], []
def check(cond, msg):
    (fails if not cond else warns.__class__()).append(msg) if not cond else None

comps = p["components"]
pid = p["_id"]

# 1 -- unique iids
iids = [c["iid"] for c in comps]
dupes = [i for i, n in collections.Counter(iids).items() if n > 1]
if dupes:
    fails.append(f"duplicate iids: {dupes}")

# 2 -- folder children resolve, and every component is in exactly one folder
byiid = {c["iid"]: c for c in comps}
listed = []
for fo in p["folders"]:
    for ch in fo["children"]:
        if ch["iid"] not in byiid:
            fails.append(f"folder {fo['name']}: dangling iid {ch['iid']}")
        else:
            listed.append(ch["iid"])
            if byiid[ch["iid"]].get("folder") != "/" + fo["name"]:
                fails.append(f"iid {ch['iid']} folder field "
                             f"{byiid[ch['iid']].get('folder')!r} != /{fo['name']}")
dupe_listed = [i for i, n in collections.Counter(listed).items() if n > 1]
if dupe_listed:
    fails.append(f"components listed in >1 folder: {dupe_listed}")
missing = set(iids) - set(listed)
if missing:
    fails.append(f"components not in any folder: "
                 f"{[(i, (byiid[i]['document'] or {}).get('name')) for i in missing]}")

# 3 -- no residual IOS project id anywhere
blob = json.dumps(p)
if IOS_ID in blob:
    fails.append(f"residual IOS project id {IOS_ID} present")

# 4 -- every "@<pid>: <name>" reference resolves to a component in this project
names = {(c["document"] or {}).get("name") for c in comps}
for m in sorted(set(re.findall(r'@([0-9a-f]{24}): ([^"\\]+)', blob))):
    ref_pid, ref_name = m
    if ref_pid != pid:
        fails.append(f"reference to foreign project {ref_pid}: {ref_name}")
    elif ref_name not in names:
        fails.append(f"dangling reference: @{ref_pid}: {ref_name}")

# 5 -- reference/_id agreement for id-addressed types
for c in comps:
    doc = c["document"] or {}
    t, ref = c["type"], c.get("reference")
    if t == "mopCommandTemplate":
        if ref != f"@{pid}: {doc.get('name')}":
            fails.append(f"{t} {doc.get('name')}: bad reference {ref!r}")
    elif t == "workflow":
        if not re.fullmatch(r"[0-9a-f-]{36}", ref or ""):
            fails.append(f"{t} {doc.get('name')}: reference not a uuid: {ref!r}")
    else:
        docid = doc.get("_id") or doc.get("id")
        if ref != docid:
            fails.append(f"{t} {doc.get('name')}: reference {ref!r} != doc id {docid!r}")

# 6 -- uniqueness of references
refs = [c.get("reference") for c in comps]
dupe_refs = [r for r, n in collections.Counter(refs).items() if n > 1]
if dupe_refs:
    fails.append(f"duplicate references: {dupe_refs}")

# 7 -- NX-OS correctness: no IOS-only artefacts left in adapted assets
IOS_MARKERS = ["GigabitEthernet", "c8000v", "cisco_ios", "cisco_xe",
               "aws-lab-iosxe", "Cisco IOS Configs", "encapsulation dot1Q",
               "Invalid input detected"]
for c in comps:
    doc = c["document"] or {}
    nm, t = doc.get("name"), c["type"]
    s = json.dumps(doc)
    for mk in IOS_MARKERS:
        if mk in s:
            # the NetBox platform_map legitimately lists other platforms
            if nm == "Create & Update Inventory from NetBox" and mk in (
                    "cisco_ios", "cisco_xe"):
                continue
            fails.append(f"IOS marker {mk!r} left in {t} {nm!r}")

# 8 -- workflows referenced by childJob tasks exist
for c in comps:
    doc = c["document"] or {}
    for tid, t in (doc.get("tasks") or {}).items():
        wf = ((t.get("variables") or {}).get("incoming") or {}).get("workflow")
        if isinstance(wf, str) and wf.startswith("@"):
            nm = wf.split(": ", 1)[1]
            if nm not in names:
                fails.append(f"{doc.get('name')}/{tid}: childJob -> missing {nm!r}")

# 8a -- every transformation task references a transformation this project ships.
# A dangling tr_id imports the workflow as a draft that the Platform refuses to start.
shipped_tr = {(c["document"] or {}).get("_id") for c in comps if c.get("type") == "transformation"}
for c in comps:
    doc = c["document"] or {}
    for tid, t in (doc.get("tasks") or {}).items():
        tr = ((t.get("variables") or {}).get("incoming") or {}).get("tr_id")
        if tr and tr not in shipped_tr:
            fails.append(f"{doc.get('name')}/{tid}: tr_id {tr} is not a transformation in this project")

# 8b -- jsonForm conformance against the known-good upstream forms.
# Forms are the one asset type built by hand here, so compare their shape to
# the IOS forms that are known to import cleanly.
ios_path = os.path.join(HERE, "ios.project.json")
if os.path.exists(ios_path):
    with open(ios_path) as f:
        _ios = json.load(f)
    ref_forms = [c["document"] for c in _ios["components"] if c["type"] == "jsonForm"]
    ref_versions = {f.get("version") for f in ref_forms}
    ref_keys = set(ref_forms[0].keys())
    for c in comps:
        if c["type"] != "jsonForm":
            continue
        doc = c["document"] or {}
        nm = doc.get("name")
        if doc.get("version") not in ref_versions:
            fails.append(f"jsonForm {nm!r}: version {doc.get('version')!r} not one of "
                         f"{sorted(ref_versions)} - the importer drops it")
        missing_k = ref_keys - set(doc.keys())
        if missing_k:
            fails.append(f"jsonForm {nm!r}: missing keys {sorted(missing_k)}")
        props = (doc.get("schema") or {}).get("properties") or {}
        req = set((doc.get("schema") or {}).get("required") or [])
        if req - set(props):
            fails.append(f"jsonForm {nm!r}: required names absent from properties: "
                         f"{sorted(req - set(props))}")
        # Field types and the placeholder key: the Studio project importer drops a
        # form it dislikes SILENTLY, so hold every item to shapes observed in forms
        # that are known to import (string and number; boolean is NOT among them).
        ref_types = {i.get("type") for f in ref_forms
                     for i in (f.get("struct") or {}).get("items", [])}
        for it in (doc.get("struct") or {}).get("items", []):
            if it.get("type") not in ref_types:
                fails.append(f"jsonForm {nm!r}: item {it.get('title')!r} has type "
                             f"{it.get('type')!r}, not among the types upstream forms "
                             f"use ({sorted(ref_types)}) - the importer drops it silently")
            if "placeholder" not in it:
                fails.append(f"jsonForm {nm!r}: item {it.get('title')!r} has no "
                             f"'placeholder'; every upstream form item carries one")

        # Every struct item must resolve to a schema property. Without an
        # explicit customKey the platform camelCases the title:
        # "Sub Interface" -> subInterface, "IP Address" -> ipAddress.
        def _camel(title):
            parts = (title or "").split()
            if not parts:
                return ""
            return parts[0].lower() + "".join(w[:1].upper() + w[1:] for w in parts[1:])

        for it in (doc.get("struct") or {}).get("items", []):
            key = it.get("customKey") or _camel(it.get("title"))
            if key not in props:
                fails.append(f"jsonForm {nm!r}: struct item {it.get('title')!r} "
                             f"maps to {key!r}, absent from schema.properties")

# 8c -- integration-model task parameters must match the types the model declares.
# Itential enforces this: an array parameter given a scalar string errors at run time
# with "Could not parse parameter value string as JSON Object or JSON Array", and a
# ["$var.x"] sends the text unresolved and silently returns nothing.
ref_path = os.path.join(HERE, "netbox-latest-params.json")
if os.path.exists(ref_path):
    with open(ref_path) as f:
        ref = json.load(f)
    JSON_TYPE = {str: "string", int: "integer", float: "number",
                 bool: "boolean", list: "array", dict: "object"}
    for c in comps:
        doc = c["document"] or {}
        for tid, task in (doc.get("tasks") or {}).items():
            if task.get("name") != ref["operation"]:
                continue
            if task.get("locationType") != ref["model"]:
                fails.append(f"{doc.get('name')}/{tid}: targets "
                             f"{task.get('locationType')!r}, not {ref['model']!r}")
            for k, val in ((task.get("variables") or {}).get("incoming") or {}).items():
                if val == "" or val is None or k == "adapter_id":
                    continue
                declared = ref["params"].get(k)
                if declared is None:
                    fails.append(f"{doc.get('name')}/{tid}: parameter {k!r} is not "
                                 f"declared by {ref['model']}")
                    continue
                actual = JSON_TYPE.get(type(val))
                if actual != declared:
                    fails.append(f"{doc.get('name')}/{tid}: parameter {k!r} is "
                                 f"{actual} but the model declares {declared}")
                if isinstance(val, list) and any(
                        isinstance(x, str) and "$var." in x for x in val):
                    fails.append(f"{doc.get('name')}/{tid}: parameter {k!r} holds a "
                                 f"$var inside an array; it will not resolve")

# 8d -- "Create a new inventory" must be reachable ONLY from the lookup's error
# edge. Upstream also fires it from "Inventory Payload" on success, so it runs on
# every job and fails whenever the inventory already exists, leaving a red task
# inside a job the platform still reports as Complete.
for c in comps:
    doc = c["document"] or {}
    if doc.get("name") != "Create & Update Inventory from NetBox":
        continue
    names = {tid: (tk.get("summary") or tk.get("name"))
             for tid, tk in (doc.get("tasks") or {}).items()}
    create = [tid for tid, n in names.items() if n == "Create a new inventory"]
    if not create:
        fails.append("inventory workflow: 'Create a new inventory' task missing")
        continue
    create = create[0]
    incoming = [(names.get(src, src), meta.get("state"))
                for src, outs in (doc.get("transitions") or {}).items()
                for dst, meta in (outs or {}).items() if dst == create]
    if incoming != [("Get a single inventory by identifier", "error")]:
        fails.append("inventory workflow: 'Create a new inventory' incoming edges are "
                     f"{incoming}, expected exactly one error edge from the lookup - "
                     "it will fire on every run and redden a Complete job")

# 9 -- required folders present
want = {"Inventory Management", "Software Upgrade", "Golden Configuration",
        "Port Turn Up", "Command Template Runner"}
got = {f["name"] for f in p["folders"]}
if want - got:
    fails.append(f"missing folders: {want - got}")

print(f"components: {len(comps)}  folders: {len(p['folders'])}  project _id: {pid}")
if fails:
    print(f"\nFAIL ({len(fails)}):")
    for f_ in fails:
        print("  -", f_)
    sys.exit(1)
print("\nPASS - all structural checks clean")
