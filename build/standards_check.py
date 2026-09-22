#!/usr/bin/env python3
"""Check the built project against the itential/assets AGENTS.md gotchas."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "..", "Cisco", "NX-OS")
OUT = os.path.join(OUT_ROOT, "Studio Projects", "Cisco NX-OS.project.json")
p = json.load(open(OUT))

fails, notes = [], []

# IOS Upgrade ships here as NX-OS Upgrade; compare it under its new name.
RENAMED = {"IOS Upgrade": "NX-OS Upgrade"}


def single_branch_evals(path):
    """Evaluation tasks lacking both a success and a failure transition."""
    d = json.load(open(path))
    found = set()
    for c in d["components"]:
        doc = c["document"] or {}
        doc = dict(doc, name=RENAMED.get(doc.get("name"), doc.get("name")))
        tr = doc.get("transitions") or {}
        for tid, t in (doc.get("tasks") or {}).items():
            if t.get("name") != "evaluation":
                continue
            states = {v.get("state") for v in (tr.get(tid) or {}).values()
                      if isinstance(v, dict)}
            if not ({"success", "failure"} <= states):
                found.add(f"{doc.get('name')}/{tid}")
    return found

# Upstream baseline: these two projects are the source material, so any
# single-branch evaluation present there is inherited, not introduced here.
BASELINE = (single_branch_evals(os.path.join(HERE, "nxos.project.json"))
            | single_branch_evals(os.path.join(HERE, "ios.project.json")))
EVAL_OPS = {"contains", "!contains", "<", "<=", ">", ">=", "==", "!="}
RESERVED = {"workflow_start", "workflow_end", "error_handler"}

for c in p["components"]:
    doc = c["document"] or {}
    wf = doc.get("name")
    tasks = doc.get("tasks") or {}
    trans = doc.get("transitions") or {}

    for tid, t in tasks.items():
        if tid in RESERVED:
            continue
        # 1 -- hex-only task ids
        if not re.fullmatch(r"[0-9a-f]{1,4}", tid):
            fails.append(f"{wf}: task id {tid!r} is not hex [0-9a-f]{{1,4}}")

        inc = (t.get("variables") or {}).get("incoming") or {}

        # 2 -- evaluation operator enum + both success and failure transitions.
        # transitions[tid] maps targetTaskId -> {state, type}; the branch is
        # carried by "state", not by the key.
        if t.get("name") == "evaluation":
            for grp in (inc.get("evaluation_groups") or []):
                for ev in (grp.get("evaluations") or []):
                    op = ev.get("operator")
                    if op is not None and op not in EVAL_OPS:
                        fails.append(f"{wf}/{tid}: evaluation operator {op!r} not in enum")
            states = {v.get("state") for v in (trans.get(tid) or {}).values()
                      if isinstance(v, dict)}
            if not ({"success", "failure"} <= states):
                msg = (f"{wf}/{tid}: evaluation has only "
                       f"{sorted(s for s in states if s)}")
                if f"{wf}/{tid}" in BASELINE:
                    notes.append(msg + " (inherited from upstream)")
                else:
                    fails.append(msg + " (INTRODUCED by conversion)")

        # 3 -- merge uses "variable", childJob uses "value"
        if t.get("name") == "merge":
            for e in (inc.get("data_to_merge") or []):
                v = e.get("value")
                if isinstance(v, dict) and "value" in v and "variable" not in v:
                    fails.append(f"{wf}/{tid}: merge entry uses 'value', must use 'variable'")
        if t.get("name") == "childJob":
            for k, v in (inc.get("variables") or {}).items():
                if isinstance(v, dict) and "variable" in v and "value" not in v:
                    fails.append(f"{wf}/{tid}: childJob var {k} uses 'variable', must use 'value'")

        # 4 -- adapter_id must not carry a foreign environment's instance name
        if "adapter_id" in inc and inc["adapter_id"]:
            notes.append(f"{wf}/{tid}: adapter_id={inc['adapter_id']!r} (must match target env)")

# 5 -- adapter tasks: record which integration instances are referenced
adapters = sorted({t.get("locationType") for c in p["components"]
                   for t in ((c["document"] or {}).get("tasks") or {}).values()
                   if t.get("location") == "Adapter" and t.get("locationType")})

# 6 -- no plausible real secrets
blob = json.dumps(p)
for pat, label in [(r'"password"\s*:\s*"(?!CHANGEME|password|\{\{|\$var)[^"]{6,}"', "hardcoded password"),
                   (r'(?i)(api[_-]?key|secret|token)"\s*:\s*"[A-Za-z0-9+/]{20,}"', "credential-like string")]:
    for m in re.findall(pat, blob):
        fails.append(f"possible {label}: {m[:60]}")

print(f"workflows checked: {sum(1 for c in p['components'] if c['type'] == 'workflow')}")
print(f"adapter instances referenced: {adapters or 'none'}")
for n in notes:
    print("  NOTE:", n)
if fails:
    print(f"\nFAIL ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("\nPASS - AGENTS.md structural gotchas clean")
