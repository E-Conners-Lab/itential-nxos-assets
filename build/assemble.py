#!/usr/bin/env python3
"""Stage 3: add the NX-OS Upgrade Form and assemble the final project."""
import json, os, hashlib

import jsonfmt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "..", "Cisco", "NX-OS")
NOW = "2026-09-19T00:00:00.000Z"

def _digest(seed):
    return hashlib.sha1(f"nxos-assets:{seed}".encode()).hexdigest()


def oid(seed):
    return _digest(seed)[:24]


def duuid(seed):
    h = _digest(seed)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

with open(os.path.join(HERE, "nxos.project.json")) as f:
    nx = json.load(f)
with open(os.path.join(HERE, "ported_adapted.json")) as f:
    ported = json.load(f)

# -------------------------------------------------------- NX-OS Upgrade Form
IMAGES = ["bootflash:///nxos64-cs.10.4.5.M.bin",
          "bootflash:///nxos64-cs.10.5.3.F.bin"]
VERSIONS = ["nxos64-cs.10.4.5.M.bin", "nxos64-cs.10.5.3.F.bin"]
form_id = oid("jsonForm:Upgrade Form")

_n = [0]


def _nid():
    _n[0] += 1
    return _n[0]


def enum_items(vals):
    return [{"id": duuid(f"node:{_nid()}"), "label": v, "value": v} for v in vals]

def enum_names(n):
    return [{"id": duuid(f"node:{_nid()}"), "label": "", "value": ""} for _ in range(n)]

upgrade_form = {
    "id": form_id,
    "created": NOW, "createdBy": "itential",
    "lastUpdated": NOW, "lastUpdatedBy": "itential",
    "name": "Upgrade Form",
    "description": "Inputs for the NX-OS Software Upgrade workflow.",
    "struct": {
        "type": "array",
        "items": [
            {"nodeId": duuid(f"node:{_nid()}"), "type": "string", "title": "Device",
             "description": "Inventory device name (e.g. 'nxos-device1')",
             "placeholder": "nxos-device1", "required": True, "readOnly": False,
             "binding": False, "rel": "item", "targetPointer": "/default",
             "customKey": "deviceName", "default": "nxos-device1"},
            {"nodeId": duuid(f"node:{_nid()}"), "type": "string", "title": "Target Version",
             "description": "NX-OS image filename the upgrade targets",
             "placeholder": "Select an item", "required": True,
             "enum": enum_items(VERSIONS), "enumNames": enum_names(len(VERSIONS)),
             "binding": False, "rel": "collection", "targetPointer": "/enum",
             "customKey": "version", "default": VERSIONS[1]},
            {"nodeId": duuid(f"node:{_nid()}"), "type": "string", "title": "Flash Memory Path",
             "description": "Filesystem prefix the image is staged on",
             "placeholder": "Select an item", "required": True,
             "enum": enum_items(["bootflash:///", "usb1:///"]),
             "enumNames": enum_names(2),
             "binding": False, "rel": "collection", "targetPointer": "/enum",
             "customKey": "flashMemory", "default": "bootflash:///"},
        ],
    },
    "schema": {
        "title": "Upgrade Form", "description": "", "type": "object",
        "required": ["deviceName", "version", "flashMemory"],
        "properties": {
            "deviceName": {"type": "string", "title": "Device",
                           "_id": "/properties/deviceName",
                           "description": "Inventory device name (e.g. 'nxos-device1')",
                           "default": "nxos-device1"},
            "version": {"type": "string", "title": "Target Version",
                        "_id": "/properties/version",
                        "description": "NX-OS image filename the upgrade targets",
                        "default": VERSIONS[1], "enum": VERSIONS,
                        "enumNames": ["", ""]},
            "flashMemory": {"type": "string", "title": "Flash Memory Path",
                            "_id": "/properties/flashMemory",
                            "description": "Filesystem prefix the image is staged on",
                            "default": "bootflash:///",
                            "enum": ["bootflash:///", "usb1:///"],
                            "enumNames": ["", ""]},
        },
    },
    "uiSchema": {
        "deviceName": {"ui:placeholder": "nxos-device1"},
        "version": {"ui:placeholder": "Select an item"},
        "flashMemory": {"ui:placeholder": "Select an item"},
        "ui:order": ["deviceName", "version", "flashMemory", "*"],
    },
    "bindingSchema": {}, "validationSchema": {},
    # JsonForms schema draft, not an asset revision. The importer silently drops
    # a form with any other value -- an integer 1 here cost one failed import.
    "version": "2020.1",
}
ported.append({"iid": None, "reference": form_id, "type": "jsonForm",
               "folder": "/Software Upgrade", "document": upgrade_form})

# suppressSuccessMessage / suppressFailureMessage stay REQUIRED, exactly as upstream ships
# them. Removing them from inputSchema.required, or giving them a default, has no effect:
# the Platform rebuilds a workflow's input schema on import from the $var.job references in
# its tasks, and a job started without both is refused (Platform 6.5.2, DevNet test,
# 2026-09-21). Callers must pass both; the README says so.

# Upstream's Command Template Runner points its "Create Command Template Runner Error
# Message" task at tr_id 6553e5b9fb4afe017442d30c, a transformation the project does not
# ship (it ships 66d0d175cddf0c8da2752c79 under that name). The Platform imports the
# workflow as a draft and refuses to start it: "Transformation tasks must reference an
# existing transformation" (Platform 6.5.2, 2026-09-21). Point it at the shipped one.
_shipped_tr = {(_c["document"] or {}).get("name"): (_c["document"] or {}).get("_id")
               for _c in nx["components"] if _c.get("type") == "transformation"}
_ctr = next(_c["document"] for _c in nx["components"]
            if _c.get("type") == "workflow" and _c["document"]["name"].endswith("Command Template Runner"))
_err = _ctr["tasks"]["a7f3"]["variables"]["incoming"]
assert _err["tr_id"] not in _shipped_tr.values(), "dangling tr_id already fixed upstream"
_err["tr_id"] = _shipped_tr["Create Command Template Runner Error Message"]

# ------------------------------------------------------------------ assemble
components = list(nx["components"]) + ported
next_iid = max(c["iid"] for c in nx["components"]) + 1
for c in components:
    if c.get("iid") is None:
        c["iid"] = next_iid
        next_iid += 1

ORDER = ["/Inventory Management", "/Software Upgrade", "/Golden Configuration",
         "/Port Turn Up", "/Command Template Runner"]
TYPE_ORDER = {"jsonForm": 0, "workflow": 1, "transformation": 2,
              "template": 3, "mopCommandTemplate": 4}
NAME_ORDER = {"Pre-Checks": 0, "Post-Checks": 1}

folders = []
for fname in ORDER:
    kids = [c for c in components if c.get("folder") == fname]
    kids.sort(key=lambda c: (TYPE_ORDER.get(c["type"], 9),
                             NAME_ORDER.get((c["document"] or {}).get("name"), 9),
                             (c["document"] or {}).get("name") or ""))
    folders.append({"nodeType": "folder", "name": fname.lstrip("/"),
                    "children": [{"iid": c["iid"], "nodeType": "component"}
                                 for c in kids]})

orphans = [c for c in components if c.get("folder") not in ORDER]
assert not orphans, [f"{c['type']}:{(c['document'] or {}).get('name')}" for c in orphans]

nx["components"] = components
nx["folders"] = folders
nx["description"] = ("Cisco NX-OS project with assets for software upgrade, port turn up, "
                     "golden configuration compliance, inventory management, and a command "
                     "template runner.")
nx["lastUpdated"] = NOW

out = os.path.join(OUT_ROOT, "Studio Projects", "Cisco NX-OS.project.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
jsonfmt.dump(nx, out)  # the itential/assets export style, so the diff against upstream is real changes only

print(f"wrote {out}")
byiid = {c["iid"]: c for c in components}
for fo in nx["folders"]:
    print(f"FOLDER: {fo['name']}")
    for ch in fo["children"]:
        c = byiid[ch["iid"]]
        print(f"   [{c['type']:<18}] {(c['document'] or {}).get('name')}")
