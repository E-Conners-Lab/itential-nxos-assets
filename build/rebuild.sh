#!/usr/bin/env bash
# Regenerates Cisco/NX-OS/ from the upstream inputs in this folder. Deterministic: IDs derive
# from stable seeds, so a rebuild of an unchanged tree produces no git diff.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}
[ -x "$PY" ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
"$PY" build_project.py   # port the IOS components
"$PY" adapt.py           # adapt them to NX-OS
"$PY" assemble.py        # add the Upgrade Form, fix inherited defects, assemble the project
"$PY" gc_build.py        # generate the three golden config trees
