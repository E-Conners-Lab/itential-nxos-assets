#!/usr/bin/env python3
"""Mock-connection tests for the Cisco NX-OS Studio Project.

No device, Platform or Gateway is contacted. Every template, rule and code block
is read out of the shipped project JSON and exercised against canned NX-OS output
(`fixtures/`, provenance in fixtures/PROVENANCE.md) or a canned API response.

Covers what this contribution adds: Port Turn Up (pre/post checks, config
template, inventory object), the NetBox inventory payload, Run Compliance
(tree lookup code, HTML report) and NX-OS Upgrade (its checks and form). The
install itself reloads the switch, so its output is not modelled here.

MOP semantics modelled (from the Itential MOP docs, not observed on a Platform):
  - `<!var!>` in a command or rule is replaced by that template variable
  - a command passes when all of its rules pass (passRule true) or any does (false)
  - `contains` / `!contains` are substring tests; `RegEx` is a regex search
"""
import json, os, re, subprocess, sys
from jinja2 import Environment, StrictUndefined, meta

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(HERE, "..", "Cisco", "NX-OS", "Studio Projects", "Cisco NX-OS.project.json")
IOS_PROJECT = os.path.join(HERE, "ios.project.json")
FIXTURES = os.path.join(HERE, "fixtures")
ENV = Environment(undefined=StrictUndefined)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def components(path):
    with open(path) as f:
        return {(c["type"], c["document"]["name"]): c["document"]
                for c in json.load(f)["components"]}


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


# ------------------------------------------------------------------ MOP model
def substitute(text, variables):
    def repl(m):
        if m.group(1) not in variables:
            raise KeyError(f"template variable <!{m.group(1)}!> not supplied")
        return str(variables[m.group(1)])
    return re.sub(r"<!(\w+)!>", repl, text)


def rule_passes(rule, output, variables):
    pattern = substitute(rule["rule"], variables)
    if rule["eval"] == "contains":
        return pattern in output
    if rule["eval"] == "!contains":
        return pattern not in output
    if rule["eval"] == "RegEx":
        return re.search(pattern, output, re.MULTILINE) is not None
    raise ValueError(f"unmodelled MOP eval {rule['eval']!r}")


def template_passes(template, outputs, variables):
    """outputs maps each substituted command to the canned device output."""
    for cmd in template["commands"]:
        output = outputs[substitute(cmd["command"], variables)]
        verdicts = [rule_passes(r, output, variables) for r in cmd["rules"]]
        if not (all(verdicts) if cmd.get("passRule", True) else any(verdicts)):
            return False
    return True


# ------------------------------------------------------------------ fixtures
C = components(PROJECT)
IOS = components(IOS_PROJECT)
WF = {name: doc for (kind, name), doc in C.items() if kind == "workflow"}

# The values the Port Turn Up form submits by default (form defaults in adapt.py).
PTU_VARS = {"device": "nxos-device1", "type": "Ethernet", "interface": "1/1",
            "subInterface": 100, "description": "test", "ipAddress": "10.0.0.2",
            "subnetMask": "255.255.255.252", "vlan": 100}
SHOW_SUBIF = "show interface Ethernet1/1.100"

# ------------------------------------------------------ 1. Port Turn Up checks
FRESH_PORT = ["real_show_interface_missing_subif.txt", "error_invalid_command.txt",
              "error_invalid_interface_format.txt", "empty.txt"]
# (fixture, the interface it reports) -- the real capture was taken on Ethernet1/20.
EXISTING = [("show_interface_subif_up.txt", "1/1"),
            ("real_show_interface_subif_parent_down.txt", "1/20")]

pre = C[("mopCommandTemplate", "Pre-Checks")]
post = C[("mopCommandTemplate", "Post-Checks")]
ios_pre = IOS[("mopCommandTemplate", "Pre-Checks")]

for fx in FRESH_PORT:
    out = {SHOW_SUBIF: fixture(fx)}
    check(f"pre-check passes on a fresh port ({fx})", template_passes(pre, out, PTU_VARS))
    check(f"post-check fails when nothing was created ({fx})",
          not template_passes(post, out, PTU_VARS))
for fx, port in EXISTING:
    variables = dict(PTU_VARS, interface=port)
    out = {f"show interface Ethernet{port}.100": fixture(fx)}
    check(f"pre-check blocks an existing sub-interface ({fx})",
          not template_passes(pre, out, variables))
    check(f"post-check passes once the sub-interface exists ({fx})",
          template_passes(post, out, variables))

# The inherited IOS rule, run against the same NX-OS output, shows the bug fixed here.
ios_rule_nxos_cmd = dict(ios_pre, commands=[dict(ios_pre["commands"][0], command=pre["commands"][0]["command"])])
check("regression: the IOS pre-check rule fails every NX-OS fresh port",
      not any(template_passes(ios_rule_nxos_cmd, {SHOW_SUBIF: fixture(fx)}, PTU_VARS)
              for fx in FRESH_PORT))

# ------------------------------------------------ 2. Port Turn Up config render
tpl = C[("template", "Port Turn Up")]["template"]
merge_keys = {d["key"] for d in WF["Port Turn Up"]["tasks"]["2d67"]["variables"]["incoming"]["data_to_merge"]}
tpl_vars = meta.find_undeclared_variables(ENV.parse(tpl))
check("config template only uses variables the merge task supplies",
      tpl_vars <= merge_keys, f"missing: {sorted(tpl_vars - merge_keys)}")
for t in (pre, post):
    used = {v for cmd in t["commands"] for v in re.findall(r"<!(\w+)!>", json.dumps(cmd))}
    check(f"{t['name']} only uses variables the merge task supplies",
          used <= merge_keys, f"missing: {sorted(used - merge_keys)}")

rendered = [l.strip() for l in ENV.from_string(tpl).render(**PTU_VARS).splitlines() if l.strip()]
check("config renders the routed, enabled parent before the sub-interface",
      rendered[:4] == ["interface Ethernet1/1", "no switchport", "no shutdown", "exit"], rendered[:4])
check("config renders the NX-OS sub-interface block",
      rendered[4:10] == ["interface Ethernet1/1.100", "description test", "encapsulation dot1q 100",
                        "ip address 10.0.0.2 255.255.255.252", "no shutdown", "exit"], rendered[4:10])
no_vlan = ENV.from_string(tpl).render(**dict(PTU_VARS, vlan=""))
check("config omits encapsulation when no VLAN is given", "encapsulation" not in no_vlan)

inv_tpl = WF["Port Turn Up"]["tasks"]["841a"]["variables"]["incoming"]["template"]
inv = json.loads(ENV.from_string(inv_tpl).render(name="nxos::nxos-device1"))
check("inventory object splits a prefixed Config Manager device name",
      inv == [{"inventory": "nxos", "nodeNames": ["nxos-device1"]}], inv)
# A Device Broker with prepend_inventory_name: false gives plain names; the device record
# still carries the inventory and node (the real devnet-n9k record, 2026-09-21).
inv = json.loads(ENV.from_string(inv_tpl).render(
    name="devnet-n9k", _inventory_name="nxos-devnet", _original_node_name="devnet-n9k"))
check("inventory object uses the device record when names are not prefixed",
      inv == [{"inventory": "nxos-devnet", "nodeNames": ["devnet-n9k"]}], inv)
check("inventory object never renders an empty node name (the upstream failure)",
      all(n for n in inv[0]["nodeNames"]), inv)

# --------------------------------------------------- 3. NetBox inventory payload
nb_task = WF["Create & Update Inventory from NetBox"]["tasks"]
nb_tpl = nb_task["7814"]["variables"]["incoming"]["template"]


def nb_device(name, platform, status="active", ip="192.0.2.11/24", **extra):
    return dict({"name": name, "platform": {"slug": platform} if platform else None,
                 "device_type": {"slug": "n9k-c9300v"},
                 "status": {"value": status}, "primary_ip4": {"address": ip} if ip else None,
                 "config_context": {}, "role": {"slug": "leaf"}, "site": {"slug": "lab"}}, **extra)


# The Integration Model task's output is the HTTP envelope; the payload is in .body.
envelope = {"status": 200, "body": {"count": 5, "results": [
    nb_device("nxos-leaf1", "cisco-nxos"),
    nb_device("nxos-leaf2", "nx-os", ip=None, config_context={"ipAddress": "192.0.2.12"}),
    nb_device("nxos-planned", "cisco-nxos", status="planned"),
    nb_device("nxos-noip", "cisco-nxos", ip=None),
    nb_device("mystery", "unknown-os"),
]}}
nodes = json.loads(ENV.from_string(nb_tpl).render(**envelope))
names = [n["name"] for n in nodes]
check("NetBox payload keeps only active, addressed, mapped devices",
      names == ["nxos-leaf1", "nxos-leaf2"], names)
leaf1 = nodes[0]["attributes"]
check("NetBox payload builds a cisco_nxos netmiko node",
      (leaf1["itential_host"], leaf1["itential_platform"], leaf1["itential_driver"], leaf1["itential_port"])
      == ("192.0.2.11", "cisco_nxos", "netmiko", 22), leaf1)
check("NetBox payload falls back to config_context.ipAddress",
      nodes[1]["attributes"]["itential_host"] == "192.0.2.12")
check("NetBox payload carries only placeholder credentials",
      all(n["attributes"]["itential_password"].startswith("CHANGEME") for n in nodes))
check("NetBox payload renders an empty list for zero devices",
      json.loads(ENV.from_string(nb_tpl).render(body={"results": []})) == [])
check("pin: NetBox query filter is still cisco-nxos / active (as written by adapt.py)",
      (nb_task["c036"]["variables"]["incoming"]["platform"], nb_task["c036"]["variables"]["incoming"]["status"])
      == (["cisco-nxos"], ["active"]))

# ------------------------------------------------------- 4. Run Compliance
code = WF["Run Compliance"]["tasks"]["b2a3"]["variables"]["incoming"]["code"]
trees = [{"id": "t1", "name": "Cisco NX-OS - Simple"}, {"id": "t2", "name": "Cisco NX-OS - Lab"}]


def run_lookup(tree_name):
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10,
                          input=json.dumps({"golden_config_trees": trees, "tree_name": tree_name}))
    return proc.returncode, json.loads(proc.stdout)


rc, out = run_lookup("Cisco NX-OS - Lab")
check("tree lookup returns the tree the workflow reads at /stdout_json/tree/id",
      rc == 0 and out.get("tree", {}).get("id") == "t2", out)
rc, out = run_lookup("No Such Tree")
check("tree lookup reports an unknown tree name", rc == 0 and "error" in out and "tree" not in out, out)

html_tpl = WF["Run Compliance"]["tasks"]["9342"]["variables"]["incoming"]["template"]
batch = {"batchId": "b-1", "status": "complete", "reports": [
    {"device": "nxos::nxos-leaf1", "nodePath": "base", "score": 88, "grade": "fail",
     "totals": {"warnings": 1, "errors": 1, "passes": 14}, "deviceType": "cisco-nx",
     "timestamp": "2026-09-21T00:00:00Z",
     "issues": [{"severity": "error", "type": "missing",
                 "spec": {"words": [{"value": "feature"}, {"value": "lacp"}], "fixMode": "manual"}}]},
    {"device": "nxos::nxos-leaf2", "nodePath": "base", "score": 100, "grade": "pass",
     "totals": {"warnings": 0, "errors": 0, "passes": 16}, "deviceType": "cisco-nx",
     "timestamp": "2026-09-21T00:00:00Z", "issues": []},
]}
html = ENV.from_string(html_tpl).render(**batch)
check("compliance report renders both devices and the missing line",
      all(s in html for s in ("nxos::nxos-leaf1", "nxos::nxos-leaf2", "feature lacp", "No issues found.",
                              "2 device report(s)")))

# ------------------------------------- 5. Golden config trees vs a real running-config
# fixtures/real_show_running_config.txt is `show running-config` from a Nexus 9000v on
# NX-OS 10.4(2). NX-OS hides settings left at their default, so a required tree line
# that only restates a default can never match. These were each confirmed absent there.
HIDDEN_DEFAULTS = {"feature ssh", "no feature telnet", "ssh key rsa 2048 force",
                   "spanning-tree mode rapid-pvst", "switchport", "switchport mode access",
                   "system default switchport", "ssh login-attempts 3"}
real_lines = {l.strip() for l in fixture("real_show_running_config.txt").splitlines() if l.strip()}
check("fixture: the hidden defaults really are absent from the real running-config",
      not HIDDEN_DEFAULTS & real_lines, sorted(HIDDEN_DEFAULTS & real_lines))


def tree_lines(node):
    def walk(lines):
        for line in lines:
            yield " ".join(w["value"] for w in line["words"]), line["evalMode"]
            yield from walk(line["lines"])
    yield from walk(node["attributes"]["export"]["lines"])
    for child in node["children"]:
        yield from tree_lines(child)


GC_DIR = os.path.join(HERE, "..", "Cisco", "NX-OS", "Golden Configurations")
for name in ("Simple", "Jinja2", "Lab"):
    with open(os.path.join(GC_DIR, f"Cisco NX-OS - {name}.json")) as f:
        root = json.load(f)["data"][0]["root"]
    lines = list(tree_lines(root))
    stale = sorted({text for text, mode in lines if mode == "required" and text in HIDDEN_DEFAULTS})
    check(f"{name} tree requires no line NX-OS hides as a default", not stale, stale)
    check(f"{name} tree forbids telnet as a disallowed line",
          ("feature telnet", "disallowed") in lines)

# Lines whose exact rendering the real switch shows -- proves the trees' syntax, not a policy.
for text in ("no password strength-check", "copp profile strict", "vrf context management",
             "feature interface-vlan"):
    check(f"real running-config renders {text!r} exactly as the trees do", text in real_lines)

# ------------------------------------------------------------ 6. NX-OS Upgrade
# The switch in the real captures runs 10.4(2) from bootflash:///nxos64-cs.10.4.2.F.bin.
upg = WF["NX-OS Upgrade"]
upg_keys = {d["key"] for d in upg["tasks"]["a1ef"]["variables"]["incoming"]["data_to_merge"]}
for name in ("File Verification", "Install", "Show Version", "Pre and Post Checks"):
    t = C[("mopCommandTemplate", name)]
    used = {v for cmd in t["commands"] for v in re.findall(r"<!(\w+)!>", json.dumps(cmd))}
    check(f"{name} only uses variables NX-OS Upgrade supplies", used <= upg_keys,
          f"missing: {sorted(used - upg_keys)}")

form = C[("jsonForm", "Upgrade Form")]
check("Upgrade Form submits exactly the inputs NX-OS Upgrade reads",
      set(form["schema"]["properties"]) == upg_keys == set(upg["inputSchema"]["required"]) - {"_id"},
      (sorted(form["schema"]["properties"]), sorted(upg_keys)))

fv = C[("mopCommandTemplate", "File Verification")]
show_ver = fixture("real_show_version.txt")
STAGED = "bootflash:///nxos64-cs.10.4.2.F.bin"


def fv_outputs(image_path, dir_fixture):
    return {"show version": show_ver, f"dir {image_path}": fixture(dir_fixture),
            "show running | include boot": "boot nxos bootflash:/nxos64-cs.10.4.2.F.bin", "dir": "listing"}


# The captures come from one switch: the staged-image listing is of the image it runs, so it
# stands in for "a newer image is staged" -- only the dir output's shape matters here.
check("File Verification passes: newer target, image staged",
      template_passes(fv, fv_outputs(STAGED, "real_dir_image_present.txt"),
                      {"version": "10.5(3)", "image_path": STAGED}))
check("File Verification stops when the image is not staged",
      not template_passes(fv, fv_outputs("bootflash:///nxos64-cs.10.5.3.F.bin", "real_dir_image_missing.txt"),
                          {"version": "10.5(3)", "image_path": "bootflash:///nxos64-cs.10.5.3.F.bin"}))
check("File Verification stops when the switch already runs the target",
      not template_passes(fv, fv_outputs(STAGED, "real_dir_image_present.txt"),
                          {"version": "10.4(2)", "image_path": STAGED}))

check("File Verification stops on any other dir error (no file listing came back)",
      not template_passes(fv, dict(fv_outputs(STAGED, "real_dir_image_present.txt"),
                                   **{f"dir {STAGED}": fixture("error_invalid_command.txt")}),
                          {"version": "10.5(3)", "image_path": STAGED}))

sv = C[("mopCommandTemplate", "Show Version")]
check("Show Version passes once the switch runs the target version",
      template_passes(sv, {"show version": show_ver}, {"version": "10.4(2)"}))
check("Show Version fails while the old version still runs (the reattempt loop continues)",
      not template_passes(sv, {"show version": show_ver}, {"version": "10.5(3)"}))

inst = C[("mopCommandTemplate", "Install")]
check("Install runs install all non-interruptively on the chosen image",
      [substitute(c["command"], {"image_path": STAGED}) for c in inst["commands"]]
      == [f"install all nxos {STAGED} non-interruptive"])

# ------------------------------------------------------------------ report
width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {'' if ok else detail}")
failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} passed")
sys.exit(1 if failed else 0)
