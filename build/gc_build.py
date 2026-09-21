#!/usr/bin/env python3
"""Generate the Cisco NX-OS golden configuration trees.

The `template` string is the source of truth; `lines[]` is derived from it
by rendering with Jinja2 and parsing the Config Manager markers, so the two
representations cannot drift apart.

Markers (matching the upstream Cisco IOS trees):
    <e/>        line severity becomes "error" instead of "warning"
    {d/}        line evalMode becomes "disallowed" instead of "required"
    {/regex/}   the word is matched as a regex rather than a literal
    indentation nests a line under the preceding shallower line
"""
import json, os, secrets, hashlib

import jsonfmt
from jinja2 import Environment, StrictUndefined

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "..", "Cisco", "NX-OS")
# The Configuration Manager config parser name, NOT the NetBox platform slug (`cisco-nxos`).
# Itential ships the NX-OS parser as `cisco-nx`; a tree with any other deviceType fails
# compliance with "No config parser found for the given device type" (Platform 6.5.2,
# DevNet Nexus 9000v, 2026-09-21).
DEVICE_TYPE = "cisco-nx"
NOW = "2026-09-19T00:00:00.000Z"
ENV = Environment(undefined=StrictUndefined, keep_trailing_newline=False)

_counter = [0]
def stable_id(seed, n=16):
    """Deterministic ids so rebuilds produce identical files."""
    _counter[0] += 1
    return hashlib.sha1(f"{seed}:{_counter[0]}".encode()).hexdigest()[:n]

def oid(seed):
    return stable_id(seed, 24)

def parse_lines(rendered, seed):
    """Parse rendered config text into the nested Config Manager line form."""
    root = []
    stack = [(-1, root)]
    for raw in rendered.split("\n"):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.strip()

        severity, eval_mode = "warning", "required"
        changed = True
        while changed:
            changed = False
            if text.startswith("<e/>"):
                severity, text, changed = "error", text[4:].lstrip(), True
            if text.startswith("{d/}"):
                eval_mode, text, changed = "disallowed", text[4:].lstrip(), True
        if not text:
            continue

        words = []
        for tok in text.split():
            if tok.startswith("{/") and tok.endswith("/}"):
                words.append({"type": "regex", "value": tok[2:-2]})
            else:
                words.append({"type": "literal", "value": tok})

        line = {"id": stable_id(seed), "words": words, "lines": [],
                "evalMode": eval_mode, "fixMode": "manual",
                "severity": severity, "ordering": "none",
                "membership": "default"}

        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].append(line)
        stack.append((indent, line["lines"]))
    return root

def node(name, template, variables, seed):
    rendered = ENV.from_string(template).render(**variables)
    cid = oid(seed + name)
    return {
        "name": name,
        "attributes": {
            "devices": [], "deviceGroups": [], "remediationWorkflow": None,
            "configId": cid,
            "export": {
                "_id": cid, "deviceType": DEVICE_TYPE,
                "lines": parse_lines(rendered, seed + name),
                "template": template,
                "created": NOW, "createdBy": "itential",
                "lastUpdated": NOW, "lastUpdatedBy": "itential",
            },
        },
        "children": [],
    }

def tree(name, root_node, variables, description, children=()):
    root_node["children"] = list(children)
    return {"data": [{
        "_id": oid(name + "doc"), "version": "initial", "name": name,
        "description": description,
        "created": NOW, "createdBy": "itential",
        "deviceType": DEVICE_TYPE,
        "gbac": {"read": [], "write": []},
        "lastUpdated": NOW, "lastUpdatedBy": "itential",
        "root": root_node, "tags": [],
        "treeId": oid(name + "tree"), "variables": variables,
    }]}

# NX-OS `show running-config` omits settings left at their default, so a line that
# only restates a default (`feature ssh`, `spanning-tree mode rapid-pvst`,
# `switchport mode access`, `no feature telnet`) is never displayed and would always
# report missing. Verified against a Nexus 9000v on NX-OS 10.4(2), 2026-09-21. To
# forbid a default-off feature, mark its enabled form disallowed: `{d/}feature telnet`.

# ===================================================== 1. Simple (literal)
SIMPLE = """\
<e/>{d/}feature telnet
feature interface-vlan
feature lacp
feature bgp
no ip domain-lookup
ip domain-name lab.itential.io
<e/>aaa authentication login default local
username admin password 5 {/\\S+/} role network-admin
no password strength-check
clock timezone UTC 0 0
ntp server 192.0.2.10 use-vrf management
ntp source-interface mgmt0
logging server 192.0.2.20 6 use-vrf management
logging timestamp milliseconds
logging logfile messages 6
logging monitor 6
snmp-server contact netops@example.com
snmp-server location Itential Lab
{d/}snmp-server community public group network-operator
spanning-tree port type edge bpduguard default
spanning-tree port type network default
no system default switchport shutdown
copp profile strict
vrf context management
  ip route 0.0.0.0/0 192.0.2.1
line vty
  exec-timeout 10
  session-limit 10
"""

# ====================================================== 2. Jinja2 (flexible)
JINJA2_VARS = {
    "hostname": "nxos-device1",
    "interfaces": [
        {"id": 1, "vlan": 10}, {"id": 2, "vlan": 10},
        {"id": 3, "vlan": 20}, {"id": 4, "vlan": 20},
    ],
}
JINJA2 = """\
<e/>version {/10\\.[45]\\([0-9]+\\)/} {/Bios:version.*/}
<e/>hostname {{ hostname }}
{d/}feature telnet
no ip domain-lookup
{% for i in interfaces %}
interface Ethernet1/{{ i.id }}
  switchport access vlan {{ i.vlan }}
  spanning-tree port type edge
  no shutdown
{% endfor %}
"""
JINJA2_EAST = """\
snmp-server community east01 group network-operator
ntp server 198.51.100.10 use-vrf management
"""
JINJA2_WEST = """\
snmp-server community west01 group network-operator
ntp server 203.0.113.10 use-vrf management
"""

# ============================================================== 3. Lab
LAB_VARS = {
    "hostname": "nxos-device1",
    "domain_name": "lab.itential.io",
    "ntp_server_1": "192.0.2.10",
    "ntp_server_2": "192.0.2.11",
    "syslog_host": "192.0.2.20",
    "admin_user": "admin",
    "vty_timeout_minutes": 10,
    "mgmt_gateway": "192.0.2.1",
}
LAB_NODES = [
    ("System Identity", """\
hostname {{ hostname }}
ip domain-name {{ domain_name }}
no ip domain-lookup
"""),
    ("Features", """\
<e/>{d/}feature telnet
feature interface-vlan
feature lacp
{d/}feature nxapi
"""),
    ("System Services", """\
no password strength-check
no system default switchport shutdown
copp profile strict
clock timezone UTC 0 0
"""),
    ("NTP", """\
ntp server {{ ntp_server_1 }} prefer use-vrf management
ntp server {{ ntp_server_2 }} use-vrf management
ntp source-interface mgmt0
"""),
    ("Syslog", """\
logging server {{ syslog_host }} 6 use-vrf management
logging timestamp milliseconds
logging logfile messages 6
logging monitor 6
"""),
    ("Login Banner", """\
banner motd #Authorized access only. Activity is logged and monitored.#
"""),
    ("AAA & Users", """\
<e/>aaa authentication login default local
username {{ admin_user }} password 5 {/\\S+/} role network-admin
"""),
    ("VTY Lines", """\
line vty
  exec-timeout {{ vty_timeout_minutes }}
  session-limit 10
"""),
    ("Spanning Tree", """\
spanning-tree port type edge bpduguard default
spanning-tree port type network default
"""),
    ("Management VRF", """\
vrf context management
  ip route 0.0.0.0/0 {{ mgmt_gateway }}
"""),
]

OUT = os.path.join(OUT_ROOT, "Golden Configurations")
os.makedirs(OUT, exist_ok=True)

def write(name, obj):
    path = os.path.join(OUT, f"{name}.json")
    jsonfmt.dump(obj, path)  # the itential/assets export style (matches the Cisco IOS trees exactly)
    return path

built = []
built.append(("Cisco NX-OS - Simple", tree(
    "Cisco NX-OS - Simple",
    node("base", SIMPLE, {}, "simple"), {},
    "Baseline NX-OS golden config using literal matching. Feature hardening, "
    "SSH, AAA, NTP, syslog, spanning tree and management VRF.")))
built.append(("Cisco NX-OS - Jinja2", tree(
    "Cisco NX-OS - Jinja2",
    node("base", JINJA2, JINJA2_VARS, "jinja2"), JINJA2_VARS,
    "NX-OS golden config using Jinja2 expressions and a regex version match, "
    "with per-region East/West child nodes.",
    children=[node("East", JINJA2_EAST, {}, "jinja2e"),
              node("West", JINJA2_WEST, {}, "jinja2w")])))
built.append(("Cisco NX-OS - Lab", tree(
    "Cisco NX-OS - Lab",
    node("base", "".join(t for _, t in LAB_NODES), LAB_VARS, "lab"), LAB_VARS,
    "Baseline golden config for a lab NX-OS switch. SSH hardening, features, "
    "NTP, syslog, AAA, VTY lockdown, spanning tree and management VRF.",
    children=[node(n, t, LAB_VARS, "lab") for n, t in LAB_NODES])))

for name, obj in built:
    p = write(name, obj)
    d = obj["data"][0]
    def count(n):
        c = 0
        def walk(ls):
            nonlocal c
            for l in ls:
                c += 1
                walk(l["lines"])
        walk(n["attributes"]["export"]["lines"])
        return c + sum(count(k) for k in n["children"])
    print(f"{name}: {count(d['root'])} lines, "
          f"{len(d['root']['children'])} child nodes -> {os.path.basename(p)}")
