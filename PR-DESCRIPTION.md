# feat(nxos): add golden config, inventory, port turn up and compliance assets

## Summary

The Cisco NX-OS product folder shipped two asset folders and a README that still described
Itential Automation Gateway 4. The Cisco IOS product is the mature pattern in this repo:
software upgrade, port turn-up, golden configuration compliance and inventory management,
wired to Inventory Manager and Itential Gateway 5.

This PR brings Cisco NX-OS up to the same shape:

- **Studio Project `Cisco NX-OS`**: 19 components in five folders (Software Upgrade, Port
  Turn Up, Golden Configuration, Inventory Management, Command Template Runner). The
  existing project `_id` (`66d0d1ba21161b4df27174c2`) is preserved, so existing
  `@<projectId>: <name>` references stay valid.
- **Three golden configuration trees** for Config Manager device type `cisco-nx`: `Simple`
  (literal matching), `Jinja2` (Jinja2 expressions, a regex version match, East/West child
  nodes) and `Lab` (a ten-section lab baseline).
- **README rewritten** to the current STANDARDS.md structure: Itential Platform / Itential
  Gateway branding, Table of Contents, node attributes, and a "Before importing" note next
  to every environment-specific value.

Every workflow except Software Upgrade was **run against a real Nexus 9000v through the
Platform** (see Testing). That run found six defects that no offline check could, four of
them inherited from the existing projects. All are fixed here and described below.

## What Changed Versus Cisco IOS, and Why

The new folders were ported from Cisco IOS and adapted to NX-OS. Each change below was driven
by NX-OS behaviour observed on a real Nexus 9000v (NX-OS 10.4(2)), not assumed:

| Area | Change | Reason |
|---|---|---|
| Golden config device type | `cisco-nx` | That is the name of Config Manager's built-in NX-OS parser. `cisco-nxos` (the NetBox slug) names no parser, and compliance fails with `No config parser found for the given device type` |
| Golden config lines | No line only restates a default (`feature ssh`, `spanning-tree mode rapid-pvst`, `ssh login-attempts 3`, ...); telnet is `{d/}feature telnet` at `error` severity | `show running-config` on NX-OS omits defaults, so a required default is reported missing on a compliant switch |
| Golden config lines | `username admin password 5 {/\S+/} role network-admin`; `version {/10\.[45]\([0-9]+\)/} {/Bios:version.*/}` | Matching is whole-line. NX-OS prints the password hash inside the username line and appends `Bios:version` to the version line |
| Port Turn Up pre-check | Passes unless the switch reports the sub-interface as existing (`Ethernet1/1.100 is up\|down`) | The IOS rule expects `Invalid input detected at '^' marker.`, which NX-OS never prints. Ported unchanged, the pre-check fails for every fresh port |
| Port Turn Up template | Sends `no switchport` and `no shutdown` to the parent interface | NX-OS sub-interfaces need a routed parent; an admin-down parent held the sub-interface `down (Parent Interface Admin down)` |
| Port Turn Up form | Interface is a string (`1/1`) | NX-OS addresses ports as slot/port |
| NetBox inventory | Filters on platform `cisco-nxos`; `platform_map` also accepts `nxos` and `nx-os` | NX-OS devices only |

## Fixes to Inherited Behaviour

These change logic that exists in the current NX-OS or IOS projects. Each is small, commented
in the build, and guarded by a check that fails if it regresses.

1. **Command Template Runner could never start** (inherited from the existing NX-OS project).
   Its error-message task references transformation `6553e5b9fb4afe017442d30c`, which the
   project does not ship. It ships the same transformation as `66d0d175cddf0c8da2752c79`. The
   Platform imports the workflow as a draft and refuses to start it: `Transformation tasks
   must reference an existing transformation`. The reference now points at the shipped
   transformation.
2. **Port Turn Up's inventory filter** (inherited from Cisco IOS). The Inventory Object task
   splits the Config Manager device name on `::`, which only works when the Device Broker
   adapter prepends inventory names. With plain names the node name renders empty and
   `sendConfig` is rejected (`nodeNames/0 must NOT have fewer than 1 characters`). The
   template now uses the device record's `_inventory_name` and `_original_node_name`, and
   keeps the split as the fallback. **Cisco IOS has the same issue.**
3. **Create & Update Inventory from NetBox: one transition removed** (inherited from Cisco
   IOS). `Inventory Payload → Create a new inventory` fired on **success**, so that task ran on
   every job, failed when the inventory already existed, and left a red task inside a job
   reported **Complete**. The task already had the edge it needs: the error edge from
   `Get a single inventory by identifier`. **Cisco IOS has the same bug.**
4. **Upgrade Form: no boolean fields.** The Studio project importer silently drops a JSON Form
   containing a `type: boolean` item: the project reports a successful import with one
   component fewer.

I'd suggest separate `fix(ios):` PRs for items 2 and 3.

## Environment-Specific Values (Shipped as Documented Placeholders)

Per AGENTS.md, instance names are not carried between environments. Each value is documented
in the README next to its workflow:

- NetBox task `adapter_id`: `netbox-latest` (the instance created from the `NetBox:latest`
  Integration Model)
- `createInventory`: `defaultClusterId` (`cluster-itential`) and `groups` (`admins`), inherited
  from Cisco IOS
- `clusterId` on Port Turn Up's `sendConfig` and on Run Compliance's `runCode`, inherited from
  Cisco IOS

## Known Issues Not Changed Here

- **Software Upgrade cannot be started from the Upgrade Form as shipped.** Software Upgrade and
  Command Template Runner require `suppressSuccessMessage` and `suppressFailureMessage`. The
  Platform derives required inputs from the `$var.job` references in a workflow's tasks when
  it imports it, so they can't be made optional or given a default from the asset (both were
  tried and discarded on import). The form can't carry them, because boolean form fields are
  dropped by the importer (fix 4). API callers pass both flags; the README says so. A proper
  fix changes how the upgrade reads those flags, which is upstream logic and needs its own
  discussion.
- **Software Upgrade was not run against a device.** It needs a second NX-OS image staged on
  the switch, and the install reloads it.
- **Seven `evaluation` tasks have a `success` transition but no `failure` one.** All are
  inherited, none introduced (verified by a baseline comparison against upstream). Fixing them
  belongs in its own `fix:` PR.
- **The NetBox Jinja payload's `credential_map`** carries `CHANGEME_*` placeholders plus the
  `itential` / `password` pair inherited from the Cisco IOS original. NX-OS nodes only ever
  receive a `CHANGEME_*` value.

## Testing

**Platform:** Itential Platform 6.5.2, Itential Gateway 5.5.2.

**Import.** The project and all three trees were imported through the Platform UI and read back
through the API: 19 of 19 components, and every golden config node matches the exported files
line for line. Verified by component count, not by the absence of an import error, because the
importer can drop a component silently.

**Real Nexus 9000v.** A private Cisco DevNet sandbox reservation, NX-OS 10.4(2), onboarded
through Inventory Manager with netmiko's `cisco_nxos` driver and published to Configuration
Manager through the Device Broker. Every run below was started on the Platform:

| Workflow / asset | Result |
|---|---|
| Run Compliance, all three trees | Complete. Every remaining finding checked against the switch's running config: all are real gaps on an unconfigured sandbox switch. The three line fixes above were first proven with a throwaway probe tree bound to the same switch |
| Port Turn Up (`Ethernet1/20.100`) | Complete, all tasks green. The switch's running config matches the rendered template exactly; the parent is admin-up |
| Command Template Runner (Post-Checks) | Complete, with both suppress flags passed |
| Create & Update Inventory from NetBox | Complete on the **create** path (new inventory created, two nodes populated) and on the **update** path (drift reconciled in both directions) |
| Clear & Delete Inventory | Complete; the inventory is removed |

The sandbox port has no link, so the sub-interface is operationally `down (Parent interface
down)` with the parent admin-up. That's expected on an unconnected virtual port.

**Offline checks,** shipped with the build tooling rather than in this PR: project structure and
references (now including transformation references), the AGENTS.md rules, a baseline
comparison proving no inherited defect was introduced, golden config format and device type,
README structure and TOC anchors, and 42 mock-connection tests built from real NX-OS output.

## Checklist

- [x] Tested against the current GA release of Itential Platform: 6.5.2 <!-- confirm still current GA -->
- [x] Free from errors
- [x] Enough detail to replicate the setup (README prerequisites and "Before importing" notes)
- [x] Explains what the contribution does and why
- [x] No sensitive or private data, and no customer or partner names. Example addresses use
      RFC 5737 documentation ranges
- [x] Root README: no change needed. The Asset Type table already lists Golden Configurations,
      and the Vendor Index already lists Cisco NX-OS
- [x] Reviewed against STANDARDS.md for Studio Projects and Golden Configurations
