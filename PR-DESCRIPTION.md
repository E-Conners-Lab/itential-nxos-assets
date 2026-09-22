# feat(nxos): bring Cisco NX-OS to the Cisco IOS shape

## Summary

The Cisco NX-OS product folder shipped a Software Upgrade built from child jobs and JSTs, a
generic Command Template Runner, and a README that predates Itential Gateway 5. The Cisco IOS
product is the mature pattern in this repo: software upgrade, port turn-up, golden
configuration compliance and inventory management, each one flat workflow, wired to
Inventory Manager and Itential Gateway 5.

This PR brings Cisco NX-OS to the same shape, aiming at the simplest path to a first
successful run. Customers can extend it from there.

- **Studio Project `Cisco NX-OS`**: 15 components in the same four folders as Cisco IOS
  (Inventory Management, Software Upgrade, Golden Configuration, Port Turn Up). No child
  jobs and no JSTs. The existing project `_id` (`66d0d1ba21161b4df27174c2`) is preserved, so
  existing `@<projectId>: <name>` references stay valid.
- **NX-OS Upgrade** replaces Software Upgrade. It is IOS Upgrade task for task, with NX-OS's
  own install step in place of the IOS boot-marker and reload (see below).
- **Three golden configuration trees** for Config Manager device type `cisco-nx`: `Simple`
  (literal matching), `Jinja2` (Jinja2 expressions, a regex version match, East/West child
  nodes) and `Lab` (a ten-section lab baseline).
- **README rewritten** in the Cisco IOS layout, following STANDARDS.md: Itential Platform /
  Itential Gateway branding, Table of Contents, node attributes, and a "Before importing"
  note next to every environment-specific value.

Every workflow was **run against a real Nexus 9000v through the Platform** (see Testing);
NX-OS Upgrade up to, but not including, the install that reloads the switch. That run found defects that no offline check could, two of them
inherited from Cisco IOS. All are fixed here and described below.

## Removed from the Existing NX-OS Project

| Component | Why |
|---|---|
| Workflow **Software Upgrade** | Ran five child jobs of Command Template Runner and one of Perform Device Connection, fed by a JST. Replaced by NX-OS Upgrade |
| Workflow **Perform Device Connection** | Only called by Software Upgrade. NX-OS Upgrade waits for the switch with IOS's reattempt loop instead |
| Workflow **Command Template Runner** | Only called by Software Upgrade; Cisco IOS ships no equivalent. It also could not start as shipped: its error-message task pointed at a transformation the project doesn't ship |
| Transformations **Software Upgrade** and **Create Command Template Runner Error Message** | Used only by the two workflows above |

With them go `suppressSuccessMessage` and `suppressFailureMessage`, two required inputs that no
form could carry, so the Upgrade Form now carries every input NX-OS Upgrade needs.

**Breaking change:** anything that starts the removed Software Upgrade or Command Template
Runner workflows by name must move to NX-OS Upgrade.

The NX-OS command templates are kept and rewritten; **Software Upgrade Checks** takes the IOS
name **Pre and Post Checks**.

## What Changed Versus Cisco IOS, and Why

The folders were ported from Cisco IOS and adapted to NX-OS. Each change below was driven by
NX-OS behaviour observed on a real Nexus 9000v (NX-OS 10.4(2)), not assumed:

| Area | Change | Reason |
|---|---|---|
| NX-OS Upgrade install step | One **Install** task, `install all nxos <image_path> non-interruptive`, replaces IOS's Get Device Details, Inventory Object, Boot Marker Config, Send Config, Eval Boot Marker and Reload | `install all` runs the compatibility checks, sets the boot variable and reloads the switch in one command, and is Cisco's supported method. An Install that errors because the reload drops the session goes to the same reattempt loop IOS uses after its reload; Show Version proves the new image. The install output is kept in `installOutput` |
| NX-OS Upgrade checks | File Verification and Show Version match `NXOS: version <version>`; the image check requires a file listing (`bytes total`) and no `No such file or directory` | The exact lines `show version` and `dir` print on NX-OS |
| Upgrade Form | Same fields as IOS: device, version (as `show version` prints it, e.g. `10.5(3)`), image path | NX-OS Upgrade reads the same inputs as IOS Upgrade |
| Golden config device type | `cisco-nx` | That is the name of Config Manager's built-in NX-OS parser. `cisco-nxos` (the NetBox slug) names no parser, and compliance fails with `No config parser found for the given device type` |
| Golden config lines | No line only restates a default (`feature ssh`, `spanning-tree mode rapid-pvst`, `ssh login-attempts 3`, ...); telnet is `{d/}feature telnet` at `error` severity | `show running-config` on NX-OS omits defaults, so a required default is reported missing on a compliant switch |
| Golden config lines | `username admin password 5 {/\S+/} role network-admin`; `version {/10\.[45]\([0-9]+\)/} {/Bios:version.*/}` | Matching is whole-line. NX-OS prints the password hash inside the username line and appends `Bios:version` to the version line |
| Port Turn Up pre-check | Passes unless the switch reports the sub-interface as existing (`Ethernet1/1.100 is up\|down`) | The IOS rule expects `Invalid input detected at '^' marker.`, which NX-OS never prints. Ported unchanged, the pre-check fails for every fresh port |
| Port Turn Up template | Sends `no switchport` and `no shutdown` to the parent interface | NX-OS sub-interfaces need a routed parent; an admin-down parent held the sub-interface `down (Parent Interface Admin down)` |
| Port Turn Up form | Interface is a string (`1/1`) | NX-OS addresses ports as slot/port |
| NetBox inventory | Filters on platform `cisco-nxos`; `platform_map` also accepts `nxos` and `nx-os` | NX-OS devices only |

## Fixes to Inherited Behaviour

These change logic that exists in the current Cisco IOS project. Each is small, commented in
the build, and guarded by a check that fails if it regresses.

1. **Port Turn Up's inventory filter.** The Inventory Object task splits the Config Manager
   device name on `::`, which only works when the Device Broker adapter prepends inventory
   names. With plain names the node name renders empty and `sendConfig` is rejected
   (`nodeNames/0 must NOT have fewer than 1 characters`). The template now uses the device
   record's `_inventory_name` and `_original_node_name`, and keeps the split as the fallback.
   **Cisco IOS has the same issue.**
2. **Create & Update Inventory from NetBox: one transition removed.** `Inventory Payload →
   Create a new inventory` fired on **success**, so that task ran on every job, failed when the
   inventory already existed, and left a red task inside a job reported **Complete**. The task
   already had the edge it needs: the error edge from `Get a single inventory by identifier`.
   **Cisco IOS has the same bug.**

I'd suggest separate `fix(ios):` PRs for both.

## Environment-Specific Values (Shipped as Documented Placeholders)

Per AGENTS.md, instance names are not carried between environments. Each value is documented
in the README next to its workflow:

- NetBox task `adapter_id`: `netbox-latest` (the instance created from the `NetBox:latest`
  Integration Model)
- `createInventory`: `defaultClusterId` (`cluster-itential`) and `groups` (`admins`), inherited
  from Cisco IOS
- `clusterId` on Port Turn Up's `sendConfig` and on Run Compliance's `runCode`, inherited from
  Cisco IOS
- The Upgrade Form's example image paths

## Known Issues Not Changed Here

- **NX-OS Upgrade's install step was not run against a device.** It needs a second NX-OS image
  staged on the switch, and the install reloads it. The workflow was started on the switch and
  stopped, as designed, at File Verification; its checks were also tested offline against real
  NX-OS `show version` and `dir` output. The Install task's success lines (`Finishing the upgrade`,
  `Install has been successful`) follow Cisco's documented `install all` output and were not
  captured. If an install ends without either, the workflow waits out the Show Version retries
  before reporting failure; its output is in `installOutput`.
- **Six `evaluation` tasks have a `success` transition but no `failure` one.** All are
  inherited from Cisco IOS, none introduced (verified by a baseline comparison against
  upstream). Fixing them belongs in its own `fix:` PR.
- **The NetBox Jinja payload's `credential_map`** carries `CHANGEME_*` placeholders plus the
  `itential` / `password` pair inherited from the Cisco IOS original. NX-OS nodes only ever
  receive a `CHANGEME_*` value.

## Testing

**Platform:** Itential Platform 6.5.2, Itential Gateway 5.5.2.

**Import.** The 15-component project was imported through the Platform UI and read back through
the API: 15 of 15 components in the four folders, and NX-OS Upgrade's tasks, transitions and
all four upgrade command templates match the shipped file exactly. Checked component by
component, because the importer can drop a component silently. The three trees were imported
the same way and match the exported files line for line.

**Real Nexus 9000v.** A private Cisco DevNet sandbox reservation, NX-OS 10.4(2), onboarded
through Inventory Manager with netmiko's `cisco_nxos` driver and published to Configuration
Manager through the Device Broker. Every run below was started on the Platform. These
workflows, their forms, templates and trees are unchanged by the restructure:

| Workflow / asset | Result |
|---|---|
| Run Compliance, all three trees | Complete. Every remaining finding checked against the switch's running config: all are real gaps on an unconfigured sandbox switch. The three line fixes above were first proven with a throwaway probe tree bound to the same switch |
| Port Turn Up (`Ethernet1/20.100`, `Ethernet1/20.200`) | Complete, all tasks green, started from Studio and by API. The switch's running config matches the rendered template exactly; the parent is admin-up |
| Create & Update Inventory from NetBox | Complete on the **create** path (new inventory created, two nodes populated) and on the **update** path (drift reconciled in both directions) |
| Clear & Delete Inventory | Complete; the inventory is removed |
| NX-OS Upgrade, safe start (`version: 10.4(2)`, the running image) | Started as shipped with device, version and image path only. Pre Check passed; File Verification stopped the run because the switch already runs the target version, so Install never ran and the switch did not reload. The image check passed live (`dir` listing, `bytes total`) |

The sandbox port has no link, so the sub-interface is operationally `down (Parent interface
down)` with the parent admin-up. That's expected on an unconnected virtual port.

**Offline checks,** shipped with the build tooling rather than in this PR: project structure and
references, the four Cisco IOS folders with no child jobs and no JSTs, the AGENTS.md rules, a
baseline comparison proving no inherited defect was introduced, golden config format and
device type, README structure and TOC anchors, and 54 mock-connection tests built from real
NX-OS output.

## Checklist

- [x] Tested against the current GA release of Itential Platform: 6.5.2 <!-- confirm still current GA -->
- [ ] Free from errors <!-- tick after the 15-component import and a Platform start of NX-OS Upgrade -->
- [x] Enough detail to replicate the setup (README prerequisites and "Before importing" notes)
- [x] Explains what the contribution does and why
- [x] No sensitive or private data, and no customer or partner names. Example addresses use
      RFC 5737 documentation ranges
- [x] Root README: no change needed. The Asset Type table already lists Golden Configurations,
      and the Vendor Index already lists Cisco NX-OS
- [x] Reviewed against STANDARDS.md for Studio Projects and Golden Configurations
