#!/usr/bin/env python3
"""Stage 2: adapt ported IOS components to NX-OS and assemble the project."""
import json, copy, os, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
NXOS_ID = "66d0d1ba21161b4df27174c2"

def _digest(seed):
    return hashlib.sha1(f"nxos-assets:{seed}".encode()).hexdigest()


def duuid(seed):
    """Deterministic UUID-shaped value, so rebuilds are byte-stable."""
    h = _digest(seed)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

with open(os.path.join(HERE, "nxos.project.json")) as f:
    nx = json.load(f)
with open(os.path.join(HERE, "ported_raw.json")) as f:
    ported = json.load(f)

by = {(c["type"], (c["document"] or {}).get("name")): c for c in ported}

# ---------------------------------------------------------------- template
tpl = by[("template", "Port Turn Up")]["document"]
# The parent needs its own `no shutdown`: Nexus ports ship admin-down, and on a
# Nexus 9000v (NX-OS 10.4(2)) the sub-interface came up "down (Parent Interface
# Admin down)" without it.
tpl["template"] = (
    "interface {{type}}{{interface}}\n"
    "  no switchport\n"
    "  no shutdown\n"
    "exit\n"
    "interface {{type}}{{interface}}.{{subInterface}}\n"
    "  description {{description}}\n"
    "{% if vlan %}\n"
    "  encapsulation dot1q {{vlan}}\n"
    "{% endif %}\n"
    "  ip address {{ipAddress}} {{subnetMask}}\n"
    "  no shutdown\n"
    "exit\n"
    "copy running-config startup-config"
)
tpl["data"] = json.dumps({
    "type": "Ethernet", "interface": "1/1", "subInterface": "100",
    "description": "test", "ipAddress": "10.0.0.2",
    "subnetMask": "255.255.255.252", "vlan": "100",
}, indent=2)
tpl["group"] = "Cisco NX-OS Configs"
tpl["description"] = "Renders an NX-OS L3 sub-interface turn-up configuration."

# ------------------------------------------------- port turn up pre/post
for nm, cmdfmt in (("Pre-Checks", "show interface <!type!><!interface!>.<!subInterface!>"),
                   ("Post-Checks", "show interface <!type!><!interface!>.<!subInterface!>")):
    doc = by[("mopCommandTemplate", nm)]["document"]
    for cmd in doc.get("commands", []):
        cmd["command"] = cmdfmt
    doc["tags"] = ["NX-OS"]

# The IOS pre-check passes on IOS's "Invalid input detected" error, which NX-OS never
# prints -- its parser says "Invalid command" / "Invalid interface format", so on a
# Nexus the check failed for every fresh port. Instead pass unless the switch reports
# the sub-interface as existing ("Ethernet1/1.100 is up|down"), which does not depend
# on the wording of any NX-OS error message.
pre = by[("mopCommandTemplate", "Pre-Checks")]["document"]
for cmd in pre["commands"]:
    assert [r["rule"] for r in cmd["rules"]] == ["Invalid input detected at '^' marker."]
    cmd["rules"] = [{"rule": "<!type!><!interface!>.<!subInterface!> is ",
                     "eval": "!contains", "severity": "error"}]

# ------------------------------------------------------- port turn up form
form = by[("jsonForm", "Port Turn Up Form")]["document"]
form["struct"]["items"] = [it for it in form["struct"]["items"]]
for it in form["struct"]["items"]:
    t = it.get("title")
    if t == "Device":
        it["default"] = "nxos-device1"
        it["placeholder"] = "nxos-device1"
    elif t == "Type":
        it["enum"] = [{"id": duuid(f"ptu-type-enum:{v}"), "label": v, "value": v}
                      for v in ("Ethernet", "port-channel")]
        it["enumNames"] = [{"id": duuid(f"ptu-type-enumname:{i}"),
                            "label": "", "value": ""} for i in range(2)]
        it["default"] = "Ethernet"
    elif t == "Interface":
        # NX-OS uses slot/port notation, so this is a string not a number
        for k in ("widget", "minimum", "maximum"):
            it.pop(k, None)
        it.update({"type": "string", "default": "1/1",
                   "placeholder": "1/1", "rel": "item",
                   "targetPointer": "/default",
                   "description": "Slot/port, e.g. 1/1"})
    elif t == "Sub Interface":
        it.update({"minimum": 1, "maximum": 4093, "default": 100})
    elif t == "Subnet Mask":
        it["default"] = "255.255.255.252"

sp = form["schema"]["properties"]
sp["device"]["default"] = "nxos-device1"
sp["type"].update({"enum": ["Ethernet", "port-channel"], "enumNames": ["", ""],
                   "default": "Ethernet"})
sp["interface"] = {"type": "string", "title": "Interface",
                   "_id": "/properties/interface",
                   "description": "Slot/port, e.g. 1/1", "default": "1/1"}
sp["subInterface"].update({"minimum": 1, "maximum": 4093, "default": 100})
sp["subnetMask"]["default"] = "255.255.255.252"
form["uiSchema"]["interface"] = {"ui:placeholder": "1/1"}

# ------------------------------------------------ netbox inventory wiring
# Upstream fires "Create a new inventory" from "Inventory Payload" on SUCCESS, so it
# runs on every job even when the inventory already exists -- and then fails, leaving a
# red task inside a job the platform still reports Complete. The task already has the
# edge it actually needs: "Get a single inventory by identifier" on ERROR. Drop the
# spurious success edge so the existing-inventory path runs clean.
inv_wf = by[("workflow", "Create & Update Inventory from NetBox")]["document"]
_names = {t: (v.get("summary") or v.get("name")) for t, v in inv_wf["tasks"].items()}
_payload = next(t for t, n in _names.items() if n == "Inventory Payload")
_create = next(t for t, n in _names.items() if n == "Create a new inventory")
assert _create in inv_wf["transitions"][_payload], "spurious edge already absent"
del inv_wf["transitions"][_payload][_create]
# the error edge from the lookup must survive -- it is the real trigger
_get = next(t for t, n in _names.items() if n == "Get a single inventory by identifier")
assert inv_wf["transitions"][_get][_create]["state"] == "error"

# ------------------------------------------------- port turn up wiring
# Upstream IOS points these at the generic "Pre and Post Checks" template
# (which lives in the Software Upgrade folder and has no NX-OS counterpart),
# leaving its own interface-specific checks unreferenced. Wire ours to the
# interface checks instead -- the merged object already carries
# type/interface/subInterface, which is what those templates interpolate.
ptu = by[("workflow", "Port Turn Up")]["document"]
WIRE = {"Pre Check": "Pre-Checks", "Post Check": "Post-Checks"}
rewired = 0
for tid, t in ptu["tasks"].items():
    tgt = WIRE.get(t.get("summary"))
    if tgt and t.get("name") == "RunCommandTemplate":
        t["variables"]["incoming"]["template"] = f"@{NXOS_ID}: {tgt}"
        rewired += 1
assert rewired == 2, f"expected to rewire 2 tasks, rewired {rewired}"

# Upstream builds sendConfig's inventory filter by splitting the Config Manager device
# name on "::", which only works when the Device Broker adapter prepends inventory names
# (prepend_inventory_name: true). With plain names the node name renders empty and
# Gateway Manager rejects the filter ("nodeNames/0 must NOT have fewer than 1
# characters" -- DevNet Nexus 9000v, Platform 6.5.2, 2026-09-21). The device record
# carries _inventory_name and _original_node_name either way: prefer them, and keep the
# split as the fallback so a prefixed name still works.
INV_OBJECT = """\
{%- if _inventory_name is defined and _inventory_name -%}
{%- set inv = _inventory_name -%}
{%- else -%}
{%- set inv = name.split('::')[0] -%}
{%- endif -%}
{%- if _original_node_name is defined and _original_node_name -%}
{%- set node = _original_node_name -%}
{%- else -%}
{%- set node = name.split('::')[-1] -%}
{%- endif -%}
[
  {
    "inventory": "{{ inv }}",
    "nodeNames": [
        "{{ node }}"
    ]
  }
]"""
_inv_obj = [t for t in ptu["tasks"].values() if t.get("summary") == "Inventory Object"]
assert len(_inv_obj) == 1 and "split('::')[1]" in _inv_obj[0]["variables"]["incoming"]["template"]
_inv_obj[0]["variables"]["incoming"]["template"] = INV_OBJECT

# ------------------------------------------------------ netbox inventory
inv = by[("workflow", "Create & Update Inventory from NetBox")]["document"]
for tid, t in inv["tasks"].items():
    if t.get("name") == "createInventory":
        inc = t["variables"]["incoming"]
        inc["description"] = "Cisco NX-OS Inventory"
        inc["tags"] = ["NX-OS"]
    if t.get("name") == "renderJinja2ContextWithCast":
        tmpl = t["variables"]["incoming"]["template"]
        tmpl = tmpl.replace(
            "NetBox -> IAG5 Inventory Template — NON-JUNOS / netmiko",
            "NetBox -> Itential Inventory Template — Cisco NX-OS / netmiko")
        tmpl = tmpl.replace(
            "Filters: active devices, must have IP, must have a mapped platform,\n           and platform is NOT Junos.",
            "Filters: active devices, must have an IP, and platform maps to cisco_nxos.")
        # NetBox platform slugs vary by install: the upstream map only carries
        # 'cisco-nxos', but real deployments also use bare 'nxos' / 'nx-os'.
        # Accept all three so the render step does not silently drop devices.
        old_map = "    'cisco-nxos':        'cisco_nxos',"
        new_map = ("    'cisco-nxos':        'cisco_nxos',\n"
                   "    'nxos':              'cisco_nxos',\n"
                   "    'nx-os':             'cisco_nxos',")
        assert old_map in tmpl, "platform_map entry for cisco-nxos not found"
        tmpl = tmpl.replace(old_map, new_map)
        t["variables"]["incoming"]["template"] = tmpl
    if t.get("name") == "dcim_devices_list":
        # The NetBox -latest integration model declares these filters as ARRAY
        # parameters. Itential enforces the declared type: an array parameter given
        # a scalar string fails with "Could not parse parameter value string as JSON
        # Object or JSON Array", so they must be literal arrays -- and literal, not
        # ["$var.x"], which sends the text unresolved.
        inc = t["variables"]["incoming"]
        if "platform" in inc:
            inc["platform"] = ["cisco-nxos"]
        if "status" in inc:
            inc["status"] = ["active"]
        # Environment-specific, and documented as such in the README: the name of the
        # integration instance created from the NetBox:latest model. It cannot be
        # "NetBox" on a platform that already runs a classic adapter by that name.
        inc["adapter_id"] = "netbox-latest"

with open(os.path.join(HERE, "ported_adapted.json"), "w") as f:
    json.dump(ported, f, indent=1)

print("adapted OK")
print("  template:\n" + "\n".join("    " + l for l in tpl["template"].split("\n")))
print("  netbox platform filter:", [t["variables"]["incoming"].get("platform")
      for t in inv["tasks"].values() if t.get("name") == "dcim_devices_list"])
