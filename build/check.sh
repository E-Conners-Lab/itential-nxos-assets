#!/usr/bin/env bash
# Runs all six offline checks against Cisco/NX-OS/. Exits non-zero if any fails.
set -uo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}
[ -x "$PY" ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
fail=0
for s in verify standards_check baseline_check gc_verify readme_check mock_test; do
  if out=$("$PY" "$s.py" 2>&1); then printf '%-16s PASS\n' "$s"
  else printf '%-16s FAIL\n' "$s"; printf '%s\n' "$out" | tail -15 | sed 's/^/    /'; fail=1; fi
done
exit $fail
