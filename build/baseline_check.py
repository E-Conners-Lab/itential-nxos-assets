#!/usr/bin/env python3
"""Run the same evaluation-transition check against the UPSTREAM projects,
to separate inherited conditions from ones introduced by the conversion."""
import json, sys

# IOS Upgrade ships here as NX-OS Upgrade; compare it under its new name.
RENAMED = {"IOS Upgrade": "NX-OS Upgrade"}


def scan(path, label):
    p = json.load(open(path))
    out = []
    for c in p["components"]:
        doc = c["document"] or {}
        wf, trans = RENAMED.get(doc.get("name"), doc.get("name")), doc.get("transitions") or {}
        for tid, t in (doc.get("tasks") or {}).items():
            if t.get("name") != "evaluation":
                continue
            states = {v.get("state") for v in (trans.get(tid) or {}).values()
                      if isinstance(v, dict)}
            if not ({"success", "failure"} <= states):
                out.append(f"{wf}/{tid} -> {sorted(s for s in states if s)}")
    print(f"--- {label}: {len(out)} single-branch evaluations")
    for o in out:
        print("     ", o)
    return set(out)

up_nx = scan("nxos.project.json", "UPSTREAM Cisco NX-OS")
up_ios = scan("ios.project.json", "UPSTREAM Cisco IOS")
built = scan("../Cisco/NX-OS/Studio Projects/Cisco NX-OS.project.json", "BUILT Cisco NX-OS")

inherited = built & (up_nx | up_ios)
introduced = built - (up_nx | up_ios)
print(f"\ninherited from upstream: {len(inherited)}")
print(f"introduced by conversion: {len(introduced)}")
for i in sorted(introduced):
    print("   INTRODUCED:", i)
sys.exit(1 if introduced else 0)
