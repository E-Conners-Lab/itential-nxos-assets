#!/usr/bin/env python3
"""Stage 3: add the NX-OS Upgrade Form, drop what IOS does not ship, assemble the project."""
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
# Same three fields as the IOS Upgrade Form (device, version, image_path), which is what
# the NX-OS Upgrade workflow reads. No boolean fields: the Studio project importer
# silently drops a form that has one.
IMAGES = ["bootflash:///nxos64-cs.10.4.5.M.bin",
          "bootflash:///nxos64-cs.10.5.3.F.bin"]
DEFAULT_VERSION = "10.5(3)"  # as `show version` prints it: "NXOS: version 10.5(3)"
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
    "description": "Inputs for the NX-OS Upgrade workflow.",
    "struct": {
        "type": "array",
        "items": [
            {"nodeId": duuid(f"node:{_nid()}"), "type": "string", "title": "Device",
             "description": "Inventory device name (e.g. 'nxos-device1')",
             "placeholder": "nxos-device1", "required": True, "readOnly": False,
             "binding": False, "rel": "item", "targetPointer": "/default",
             "customKey": "device", "default": "nxos-device1"},
            {"nodeId": duuid(f"node:{_nid()}"), "type": "string", "title": "Target Version",
             "description": "Version string the upgrade targets, as show version prints it",
             "placeholder": DEFAULT_VERSION, "required": True, "readOnly": False,
             "binding": False, "rel": "item", "targetPointer": "/default",
             "customKey": "version", "default": DEFAULT_VERSION},
            {"nodeId": duuid(f"node:{_nid()}"), "type": "string", "title": "Image Path on Device",
             "description": "",
             "placeholder": "Select an item", "required": True,
             "enum": enum_items(IMAGES), "enumNames": enum_names(len(IMAGES)),
             "binding": False, "rel": "collection", "targetPointer": "/enum",
             "customKey": "image_path", "default": IMAGES[1]},
        ],
    },
    "schema": {
        "title": "Upgrade Form", "description": "", "type": "object",
        "required": ["device", "version", "image_path"],
        "properties": {
            "device": {"type": "string", "title": "Device",
                       "_id": "/properties/device",
                       "description": "Inventory device name (e.g. 'nxos-device1')",
                       "default": "nxos-device1"},
            "version": {"type": "string", "title": "Target Version",
                        "_id": "/properties/version",
                        "description": "Version string the upgrade targets, as show version prints it",
                        "default": DEFAULT_VERSION},
            "image_path": {"type": "string", "title": "Image Path on Device",
                           "_id": "/properties/image_path",
                           "description": "",
                           "default": IMAGES[1], "enum": IMAGES,
                           "enumNames": ["", ""]},
        },
    },
    "uiSchema": {
        "device": {"ui:placeholder": "nxos-device1"},
        "version": {"ui:placeholder": DEFAULT_VERSION},
        "image_path": {"ui:placeholder": "Select an item"},
        "ui:order": ["device", "version", "image_path", "*"],
    },
    "bindingSchema": {}, "validationSchema": {},
    # JsonForms schema draft, not an asset revision. The importer silently drops
    # a form with any other value -- an integer 1 here cost one failed import.
    "version": "2020.1",
}
ported.append({"iid": None, "reference": form_id, "type": "jsonForm",
               "folder": "/Software Upgrade", "document": upgrade_form})

# ------------------------------------------ upstream NX-OS components removed
# The easiest happy path, in the shape of Cisco IOS: no child jobs, no JSTs. Upstream's
# Software Upgrade ran five child jobs of Command Template Runner (and one of Perform
# Device Connection) and prepared their inputs with a JST; Command Template Runner needs
# a JST of its own. NX-OS Upgrade (ported from IOS Upgrade) replaces all of them, and
# with them go the two required suppress flags that no form could carry.
REMOVED = {("workflow", "Perform Device Connection"), ("workflow", "Command Template Runner"),
           ("workflow", "Software Upgrade"), ("transformation", "Software Upgrade"),
           ("transformation", "Create Command Template Runner Error Message")}
_before = {(c["type"], (c["document"] or {}).get("name")) for c in nx["components"]}
assert REMOVED <= _before, f"upstream no longer ships: {REMOVED - _before}"
nx["components"] = [c for c in nx["components"]
                    if (c["type"], (c["document"] or {}).get("name")) not in REMOVED]

# ------------------------------------------------- NX-OS upgrade command templates
# Upstream's NX-OS templates, rewritten to the variables IOS Upgrade passes: device,
# version (as show version prints it, "10.5(3)") and image_path ("bootflash:///...").
# The output shapes were captured from a Nexus 9000v on NX-OS 10.4(2) (build/fixtures).
def _rule(rule, ev):
    return {"rule": rule, "eval": ev, "severity": "error"}

def _cmd(command, rules, pass_rule=True):
    return {"command": command, "passRule": pass_rule, "rules": rules}

MOPS = {
    "File Verification": [
        # stop if the switch already runs the target version
        _cmd("show version", [_rule("NXOS: version <!version!>", "!contains")]),
        # stop if the image is not staged where the form says
        # "bytes total" closes every NX-OS dir listing, so any other error also stops the run
        _cmd("dir <!image_path!>", [_rule("No such file or directory", "!contains"),
                                     _rule("bytes total", "contains")]),
        _cmd("show running | include boot", [_rule("", "contains")]),
        _cmd("dir", [_rule("", "contains")]),
    ],
    # `non-interruptive` answers install all's own confirmation prompt. Either line is
    # printed once the install is committed and the switch is about to reload (Cisco's
    # documented output; no install was captured here, as it reloads the switch).
    "Install": [
        _cmd("install all nxos <!image_path!> non-interruptive",
             [_rule("Finishing the upgrade", "contains"),
              _rule("Install has been successful", "contains")], pass_rule=False),
    ],
    "Show Version": [
        _cmd("show version", [_rule("NXOS: version <!version!>", "contains")]),
    ],
}
_mops = {(c["document"] or {}).get("name"): c for c in nx["components"]
         if c["type"] == "mopCommandTemplate"}
for name, commands in MOPS.items():
    doc = _mops[name]["document"]
    doc["commands"] = commands
    doc["tags"] = ["NX-OS"]

# IOS names its pre/post snapshot template "Pre and Post Checks"; NX-OS's equivalent is
# "Software Upgrade Checks". Take the IOS name so NX-OS Upgrade's references resolve.
_checks = _mops["Software Upgrade Checks"]
_checks["document"]["name"] = "Pre and Post Checks"
_checks["document"]["tags"] = ["NX-OS"]
_checks["reference"] = f"@{nx['_id']}: Pre and Post Checks"

# ------------------------------------------------------------------ assemble
components = list(nx["components"]) + ported
next_iid = max(c["iid"] for c in nx["components"]) + 1
for c in components:
    if c.get("iid") is None:
        c["iid"] = next_iid
        next_iid += 1

ORDER = ["/Inventory Management", "/Software Upgrade", "/Golden Configuration",
         "/Port Turn Up"]
TYPE_ORDER = {"jsonForm": 0, "workflow": 1, "transformation": 2,
              "template": 3, "mopCommandTemplate": 4}
NAME_ORDER = {"Pre-Checks": 0, "Post-Checks": 1}  # IOS lists the rest alphabetically

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
                     "golden configuration compliance, and inventory management.")
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
