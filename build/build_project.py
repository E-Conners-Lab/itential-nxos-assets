#!/usr/bin/env python3
"""Build the converted Cisco NX-OS Studio project.

Starts from the upstream NX-OS project (preserving its _id so existing
internal "@<projectId>: <name>" references stay valid) and ports the
folders IOS has but NX-OS lacks: Golden Configuration, Inventory
Management, Port Turn Up -- plus IOS Upgrade as the base of the NX-OS upgrade.
"""
import json, copy, os, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
NXOS_ID = "66d0d1ba21161b4df27174c2"
IOS_ID = "66d0304521161b4df2717497"
NOW = "2026-09-19T00:00:00.000Z"

def _digest(seed):
    return hashlib.sha1(f"nxos-assets:{seed}".encode()).hexdigest()


def oid(seed):
    """Deterministic 24-hex ObjectId-shaped value, so rebuilds are byte-stable."""
    return _digest(seed)[:24]


def duuid(seed):
    """Deterministic UUID-shaped value derived from the same seed space."""
    h = _digest(seed)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def load(n):
    with open(os.path.join(HERE, n)) as f:
        return json.load(f)

nx = load("nxos.project.json")
ios = load("ios.project.json")

ios_by_name = {}
for c in ios["components"]:
    doc = c.get("document") or {}
    ios_by_name[(c["type"], doc.get("name"))] = c

def retarget(obj):
    """Rewrite IOS project-scoped refs to the NX-OS project id."""
    s = json.dumps(obj)
    s = s.replace(f"@{IOS_ID}:", f"@{NXOS_ID}:")
    return json.loads(s)

def port(ctype, name, folder, new_name=None):
    c = copy.deepcopy(ios_by_name[(ctype, name)])
    c = retarget(c)
    doc = c["document"]
    if new_name:
        doc["name"] = new_name
    # fresh identity so IOS and NX-OS projects can coexist on one platform
    seed = f"{ctype}:{doc['name']}"
    if ctype == "workflow":
        c["reference"] = duuid(seed)
    elif ctype == "mopCommandTemplate":
        c["reference"] = f"@{NXOS_ID}: {doc['name']}"
    else:
        new = oid(seed)
        c["reference"] = new
        for k in ("_id", "id"):
            if k in doc:
                doc[k] = new
    c["folder"] = folder
    c["iid"] = None  # reassigned at assembly; IOS iids collide with NX-OS ones
    return c

ported = []

# ---- Golden Configuration (device-agnostic, ports unchanged) ----
ported.append(port("workflow", "Run Compliance", "/Golden Configuration"))
ported.append(port("jsonForm", "Compliance Form", "/Golden Configuration"))

# ---- Inventory Management ----
inv = port("workflow", "Create & Update Inventory from NetBox", "/Inventory Management")
clr = port("workflow", "Clear & Delete Inventory", "/Inventory Management")
ported += [inv, clr]

# ---- Software Upgrade ----
# The upstream NX-OS upgrade drives five child jobs through Command Template Runner and a
# JST. IOS Upgrade is one flat workflow of MOP tasks and evaluations, so it is the base;
# adapt.py swaps its IOS boot-marker + reload tasks for NX-OS's single `install all`.
ported.append(port("workflow", "IOS Upgrade", "/Software Upgrade", new_name="NX-OS Upgrade"))

# ---- Port Turn Up ----
ported.append(port("workflow", "Port Turn Up", "/Port Turn Up"))
ported.append(port("jsonForm", "Port Turn Up Form", "/Port Turn Up"))
ported.append(port("template", "Port Turn Up", "/Port Turn Up"))
ported.append(port("mopCommandTemplate", "Pre-Checks", "/Port Turn Up"))
ported.append(port("mopCommandTemplate", "Post-Checks", "/Port Turn Up"))

with open(os.path.join(HERE, "ported_raw.json"), "w") as f:
    json.dump(ported, f, indent=1)

print(f"ported {len(ported)} components:")
for c in ported:
    print(f"  {c['type']:<18} {(c['document'] or {}).get('name'):<40} -> {c['folder']}")
