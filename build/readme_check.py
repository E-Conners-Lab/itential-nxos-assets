#!/usr/bin/env python3
"""Verify the README against STANDARDS.md / AGENTS.md rules.

Anchors are computed with GitHub's slug algorithm: lowercase, strip
everything but [a-z0-9_ -], spaces -> hyphens, no collapsing, duplicates
get -1/-2 suffixes.
"""
import re, sys, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "..", "Cisco", "NX-OS")
path = os.path.join(OUT_ROOT, "README.md")
text = open(path).read()
fails = []

def slug(h):
    s = h.lower()
    s = "".join(c for c in s if c.isalnum() or c in " _-" or ord(c) > 127)
    s = "".join(c for c in s if not (ord(c) > 127))
    return s.replace(" ", "-")

# collect headings outside fenced code blocks
lines, in_fence = [], False
for ln in text.split("\n"):
    if ln.strip().startswith("```"):
        in_fence = not in_fence
        continue
    if not in_fence:
        lines.append(ln)

headings = [(len(m.group(1)), m.group(2).strip())
            for ln in lines if (m := re.match(r"^(#{1,6})\s+(.*)$", ln))]

seen = collections.Counter()
anchors = {}
for lvl, h in headings:
    s = slug(h)
    n = seen[s]
    seen[s] += 1
    anchors[(lvl, h)] = s if n == 0 else f"{s}-{n}"

# 1 -- every TOC link resolves
toc_links = re.findall(r"^\s*-\s+\[([^\]]+)\]\(#([^)]+)\)", text, re.M)
valid = set(anchors.values())
for label, anc in toc_links:
    if anc not in valid:
        fails.append(f"TOC link [{label}](#{anc}) has no matching heading "
                     f"(valid: {sorted(valid)})")

# 2 -- every ## and ### heading appears in the TOC (excluding the TOC heading itself)
linked = {a for _, a in toc_links}
for (lvl, h), a in anchors.items():
    if lvl in (2, 3) and h != "Table of Contents" and a not in linked:
        fails.append(f"heading {'#'*lvl} {h} (#{a}) missing from TOC")

# 3 -- no heading deeper than ###
for lvl, h in headings:
    if lvl > 3:
        fails.append(f"heading too deep ({'#'*lvl}): {h}")

# 4 -- structure: single H1, TOC before Contents, no ## Overview
h1 = [h for lvl, h in headings if lvl == 1]
if len(h1) != 1:
    fails.append(f"expected exactly one H1, got {h1}")
order = [h for _, h in headings]
if "Table of Contents" not in order or "Contents" not in order:
    fails.append("missing 'Table of Contents' or 'Contents'")
elif order.index("Table of Contents") > order.index("Contents"):
    fails.append("Table of Contents must come before Contents")
if "Overview" in order:
    fails.append("STANDARDS.md forbids a separate '## Overview' heading")

# 5 -- branding
for bad in (r"\bIAP\b", r"\bIAG\b", r"Assets for the Itential Platform"):
    for m in re.findall(bad, text):
        fails.append(f"forbidden phrase: {m}")

# 6 -- no generic import click-paths
for bad in ("Automation Studio > Projects > Import", "Import via", "navigate to Automation Studio"):
    if bad.lower() in text.lower():
        fails.append(f"generic import instructions present: {bad!r}")

# 7 -- relative asset links resolve on disk
for label, target in re.findall(r"\[([^\]]+)\]\((\./[^)]+)\)", text):
    from urllib.parse import unquote
    f = os.path.join(OUT_ROOT, unquote(target[2:]))
    if not os.path.exists(f):
        fails.append(f"broken asset link [{label}]({target})")

print(f"headings: {len(headings)}  TOC links: {len(toc_links)}")
for (lvl, h), a in anchors.items():
    if lvl in (2, 3):
        print(f"  {'#'*lvl} {h}  ->  #{a}")
if fails:
    print(f"\nFAIL ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("\nPASS - README matches STANDARDS.md structure and anchors resolve")
