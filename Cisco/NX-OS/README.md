# Cisco NX-OS

Cisco NX-OS is the network operating system running Cisco's Nexus switches — a modular, feature-gated CLI platform deployed across data center access, aggregation, and spine-and-leaf fabrics.

This project provides a Studio Project covering software upgrade, port turn-up, golden configuration compliance, inventory management, and a reusable command template runner for Cisco NX-OS devices — see **Projects** below.

**Requirements:** Itential Platform >= 6.4 · Itential Gateway >= 5.0

## Table of Contents

- [Contents](#contents)
- [Inventory Manager Configuration](#inventory-manager-configuration)
  - [Node Attributes](#node-attributes)
- [Projects](#projects)
  - [Cisco NX-OS](#cisco-nx-os-1)
- [Golden Configurations](#golden-configurations)
  - [Cisco NX-OS - Simple](#cisco-nx-os---simple)
  - [Cisco NX-OS - Jinja2](#cisco-nx-os---jinja2)
  - [Cisco NX-OS - Lab](#cisco-nx-os---lab)

## Contents

| Asset | Description |
|---|---|
| [Studio Projects/Cisco NX-OS](./Studio%20Projects/Cisco%20NX-OS.project.json) | Itential Platform project — software upgrade, port turn-up, compliance, inventory management, command template runner |
| [Golden Configurations/Cisco NX-OS - Simple](./Golden%20Configurations/Cisco%20NX-OS%20-%20Simple.json) | Golden config tree using literal matching |
| [Golden Configurations/Cisco NX-OS - Jinja2](./Golden%20Configurations/Cisco%20NX-OS%20-%20Jinja2.json) | Golden config tree using Jinja2 expressions and a regex version match |
| [Golden Configurations/Cisco NX-OS - Lab](./Golden%20Configurations/Cisco%20NX-OS%20-%20Lab.json) | Golden config tree for lab baseline configuration |

---

## Inventory Manager Configuration

Itential Platform ships with a netmiko driver for Cisco NX-OS. Broker actions (`is-alive`, `run-command`, `get-config`, `set-config`) are wired automatically when the inventory is created with `createBrokerActions: true` — no manual action configuration is required.

### Node Attributes

Set these attributes on each node in Inventory Manager:

```json
{
  "name": "my-nxos-device",
  "attributes": {
    "itential_host": "192.0.2.1",
    "itential_port": 22,
    "itential_driver": "netmiko",
    "itential_platform": "cisco_nxos",
    "itential_user": "username",
    "itential_password": "changeme",
    "itential_driver_options": {
      "netmiko": {
        "banner_timeout": 60,
        "conn_timeout": 60,
        "enable_fast_mode": true,
        "global_delay_factor": 3,
        "read_timeout_override": 1800,
        "session_timeout": 300
      }
    }
  }
}
```

| Attribute | Type | Unit | Description |
|---|---|---|---|
| `itential_host` | string | — | Management IP or hostname of the device |
| `itential_port` | integer | — | SSH port (default: `22`) |
| `itential_driver` | string | — | Driver to use — must be `netmiko` |
| `itential_platform` | string | — | Netmiko device type — `cisco_nxos` for NX-OS |
| `itential_user` | string | — | SSH username |
| `itential_password` | string | — | SSH password |
| `banner_timeout` | integer | seconds | Time to wait for the login banner before timing out |
| `conn_timeout` | integer | seconds | TCP connection timeout |
| `enable_fast_mode` | boolean | — | Skip unnecessary delays between commands when `true` |
| `global_delay_factor` | integer | — | Multiplier applied to all internal netmiko delays — increase for slow devices |
| `read_timeout_override` | integer | seconds | Override the default read timeout for command responses |
| `session_timeout` | integer | seconds | Max lifetime of the SSH session |

> **On `read_timeout_override`:** `install all nxos` runs as a single long-lived command rather than a reload-and-reconnect, and on a real Nexus it can hold the session for well over ten minutes while it compacts and installs the image. The `1800` above is sized for that. Lower it for read-only use cases if you prefer a tighter timeout.

> **Prerequisite for Configuration Manager:** Run Compliance, the Port Turn Up checks, and
> Command Template Runner reach the device through Configuration Manager, not Inventory Manager
> directly. The node must be published there by a Device Broker adapter (the built-in Inventory
> Manager adapter) whose `inventories` list includes this node's inventory. If a node never
> appears in Configuration Manager, check that list and give the node a `cluster_id` attribute
> naming your Gateway cluster.

---

## Projects

### Cisco NX-OS

An Itential Platform project covering software upgrade, port turn-up, golden configuration compliance, inventory management, and a reusable command template runner for Cisco NX-OS devices, organized into five folders.

**Software Upgrade**
- **Software Upgrade** — runs a connection test and pre-checks, verifies the staged image, installs it, then re-verifies and runs post-checks, comparing pre against post
- **Perform Device Connection** — reusable connection test with retry and delay, called by the upgrade
- Command templates: File Verification · Install · Show Version · Software Upgrade Checks
- Transformation: Software Upgrade
- Form: **Upgrade Form** — input for device name, target image, and flash filesystem

> **On the message-suppression flags:** **Software Upgrade** and **Command Template Runner**
> require `suppressSuccessMessage` and `suppressFailureMessage`, and a job started without
> both is refused. Pass them as booleans (`false` shows the summary message). The Platform
> derives a workflow's required inputs from the job variables its tasks reference, so the
> flags cannot be made optional from the asset. The Upgrade Form does not offer them: a JSON
> Form carrying a `boolean` field is dropped by the Studio project importer without an error.

> **Before importing:** The Upgrade Form contains example image names
> (`nxos64-cs.10.4.5.M.bin`, `nxos64-cs.10.5.3.F.bin`) and filesystem prefixes
> (`bootflash:///`, `usb1:///`). Update the form's `enum` fields under "Target Version"
> and "Flash Memory Path" to match the images staged in your environment. The upgrade
> concatenates the two into the path it verifies and installs.

**Port Turn Up**
- **Port Turn Up** — configure and activate a Layer 3 sub-interface
- Template: Port Turn Up
- Command templates: Pre-Checks · Post-Checks
- Form: **Port Turn Up Form** — input for device, interface type, interface, sub-interface, description, IP address, subnet mask, and VLAN

> **On NX-OS interface naming:** the Interface field is a string (`1/1`), not the
> integer the Cisco IOS project uses, because NX-OS addresses ports as slot/port.
> The template issues `no switchport` and `no shutdown` on the parent interface before
> creating the sub-interface: NX-OS sub-interfaces require a routed parent, and one left
> administratively down holds the sub-interface down with it.

> **On the pre-check:** Pre-Checks passes unless the switch reports the sub-interface as
> existing (`Ethernet1/1.100 is up`). The match is literal, so when starting **Port Turn Up**
> programmatically, pass the interface type exactly as NX-OS prints it (`Ethernet`,
> `port-channel`) and the port without leading zeros (`1/1`) — an abbreviation such as
> `Eth` would not match, and an existing sub-interface would be reconfigured. The form
> already constrains the type to those two values.

> **Before importing:** the **Send Config: Port Turn Up** task's `clusterId`
> (`cluster-itential`) is environment-specific — set it to your Gateway cluster name.

**Golden Configuration**
- **Run Compliance** — runs a compliance check against a golden config tree
- Form: **Compliance Form** — select the golden config tree name and version to run against

> **Before importing:** the **Get treeId** task runs a short Python lookup on a Gateway, and
> its `clusterId` (`cluster-itential`) is environment-specific — set it to your Gateway
> cluster name.

**Inventory Management**
- **Create & Update Inventory from NetBox** — creates or updates an Inventory Manager inventory using NetBox as the source of truth, filtered to devices whose NetBox platform is `cisco-nxos`
- **Clear & Delete Inventory** — removes all nodes from an inventory and deletes it

> **Prerequisite:** **Create & Update Inventory from NetBox** calls the `dcim_devices_list`
> operation of an Integration Model identified as `NetBox:latest`. Import
> [`NetBox/OpenAPIs/netbox-latest.json`](../../NetBox/OpenAPIs/netbox-latest.json) as an
> Integration Model and create an integration instance from it **before** running the
> workflow, or the task fails validation with `No config found for Adapter: NetBox:latest`.
> The task's `adapter_id` must be that instance's name. A classic NetBox *adapter* does not
> satisfy this — the model is addressed by `title:version`, not by the instance.
>
> That model declares `platform` and `status` as **array** parameters. Itential enforces
> declared types, so they are set as literal arrays (`["cisco-nxos"]`, `["active"]`); a
> scalar string fails with `Could not parse parameter value string as JSON Object or JSON
> Array`, and a `["$var.x"]` sends the text unresolved and silently returns nothing.

> **Before importing:** three values in **Create & Update Inventory from NetBox** are
> environment-specific and will not match a fresh Platform:
> - the NetBox task's `adapter_id` (`netbox-latest`) — set it to the name of your integration instance created from the `NetBox:latest` model
> - the `createInventory` task's `defaultClusterId` (`cluster-itential`) — set it to your Gateway cluster name
> - the `createInventory` task's `groups` (`admins`) — set it to an authorization group you belong to,
>   with the `inventory:read` and `inventory:update` roles, or the call returns `403`
>
> The NetBox task requests only devices whose platform slug is `cisco-nxos`. If your NetBox
> uses a different slug for NX-OS, change the task's `platform` filter to your slug **and**
> add it to the Jinja2 payload's `platform_map`, which maps NetBox slugs to netmiko platforms
> (it already accepts `nxos` and `nx-os`). List only slugs that exist in your NetBox — it
> rejects an unknown slug in that filter. The payload also carries placeholder credentials
> per platform.

**Command Template Runner**
- **Command Template Runner** — runs any command template against a device with optional retry, and formats pass, fail, and error results
- Transformation: Create Command Template Runner Error Message

---

## Golden Configurations

Three golden configuration trees are provided. All ship with no device bindings — bind each tree to your devices in Config Manager after importing.

> **On the device type:** the trees use `cisco-nx`, the name of Config Manager's built-in
> NX-OS config parser. It is not the NetBox platform slug `cisco-nxos` used by the inventory
> workflow, and the two are not interchangeable: a tree whose device type names no parser
> fails compliance with `No config parser found for the given device type`.

> **On NX-OS defaults:** `show running-config` on NX-OS omits any setting left at its
> default, so the trees never require a line that only restates one (`feature ssh`,
> `spanning-tree mode rapid-pvst`, `switchport mode access`) — it would be reported missing
> on a compliant switch. To forbid a feature that is off by default, mark its enabled form
> disallowed, as these trees do with `feature telnet`, rather than requiring `no feature telnet`.

### Cisco NX-OS - Simple

Device type: `cisco-nx`

Baseline configuration using literal matching. Feature hardening, SSH, AAA, NTP, syslog, spanning tree, and the management VRF default route. Use this as a starting point when all devices in a group are expected to share identical configuration values with no variation.

`feature telnet` is disallowed and `aaa authentication login default local` is required, both at `error` severity; an SNMP `public` community is marked disallowed so it is flagged if present.

### Cisco NX-OS - Jinja2

Device type: `cisco-nx`

Baseline configuration using Jinja2 template expressions and a regex version match for flexible value matching. Use this when your environment has multiple allowed values for a field — the version line matches any `10.4(x)` or `10.5(x)` release, permitting a phased upgrade rollout.

Includes `East` and `West` child nodes carrying region-specific SNMP and NTP, and a Jinja2 loop that expands a list of access ports.

### Cisco NX-OS - Lab

Device type: `cisco-nx`

Lab baseline configuration, split into ten child nodes — System Identity, Features, System Services, NTP, Syslog, Login Banner, AAA & Users, VTY Lines, Spanning Tree, and Management VRF. Captures a reference configuration for lab devices — useful as a starting point before tailoring to production standards.
