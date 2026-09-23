# Cisco NX-OS Assets for itential/assets

A proposed contribution to [`itential/assets`](https://github.com/itential/assets): the Cisco NX-OS
product brought up to the shape of Cisco IOS, with software upgrade, port turn-up, golden
configuration compliance and inventory management, on Itential Gateway 5. Like Cisco IOS, it
uses no child jobs and no JSTs.

This repo stages it for review before the upstream PR is opened. **[`PR-DESCRIPTION.md`](./PR-DESCRIPTION.md)**
is the reviewer-facing summary: what changed, why, the defects fixed, known issues and test results.

## What's Here

| Path | What it is |
|---|---|
| [`Cisco/NX-OS/`](./Cisco/NX-OS) | **The contribution**, laid out exactly as it goes into `itential/assets`: the Studio project, three golden config trees and the product README |
| [`PR-DESCRIPTION.md`](./PR-DESCRIPTION.md) | The upstream PR title and body |
| [`build/`](./build) | Generates `Cisco/NX-OS/` from the upstream Cisco IOS and NX-OS projects, and six offline checks |
| [`devnet/`](./devnet) | How the pack was tested on a real Nexus 9000v from a Cisco DevNet sandbox |

## Review It

Run the offline checks. They need only Python 3.10+ and create their own virtualenv on first run:

```bash
./build/check.sh
```

All six should print `PASS`:

| Check | Proves |
|---|---|
| `verify` | Project structure: every reference resolves; the four Cisco IOS folders, with no child jobs or JSTs; forms are importable; NetBox task parameters match the model's declared types |
| `standards_check` | The mechanical rules in upstream's `AGENTS.md` |
| `baseline_check` | No structural defect was **introduced**; the ones present are inherited from the upstream projects |
| `gc_verify` | The golden config trees match the Cisco IOS tree format, with device type `cisco-nx` |
| `readme_check` | README structure and Table of Contents anchors, per upstream's `STANDARDS.md` |
| `mock_test` | 54 device-facing behaviours against NX-OS output, most of it captured from a real switch |

The build is deterministic, so you can confirm the committed files are exactly what the build
produces:

```bash
./build/rebuild.sh && git status --short Cisco/   # no output = identical
```

## Import It

Import into an Itential Platform (tested on 6.5.2):

1. **Studio → Projects → Import** `Cisco/NX-OS/Studio Projects/Cisco NX-OS.project.json`, then
   check the project has **15 components**. The importer can drop a component without an error.
2. **Configuration Manager → 🔍 → Golden Configurations → Import** each file in
   `Cisco/NX-OS/Golden Configurations/`.

The product README ([`Cisco/NX-OS/README.md`](./Cisco/NX-OS/README.md)) lists the prerequisites
and the environment-specific values to set before running anything.

To replace an existing copy, **delete it first**. A re-import doesn't replace an existing
project's components or an existing tree's lines, and it reports no error.

## Test It on a Real Nexus

See [`devnet/README.md`](./devnet/README.md). Every workflow was run that way on 2026-09-21 and
2026-09-22 -- NX-OS Upgrade up to, but not including, the install that reloads the switch; the
results are in `PR-DESCRIPTION.md`.

## Open Before Submitting Upstream

- **Confirm 6.5.2 is still the current GA release** of Itential Platform (upstream checklist).

## Submitting Upstream

1. Fork `itential/assets` and create a topic branch.
2. Replace `Cisco/NX-OS/` in the fork with this repo's `Cisco/NX-OS/`. Nothing else in
   `itential/assets` changes.
3. Commit, and open the PR with the title and body from `PR-DESCRIPTION.md`.

## Licence

`itential/assets` is Apache 2.0, and this repo carries the same [`LICENSE`](./LICENSE).
[`NOTICE`](./NOTICE) lists the upstream files copied into `build/` as build inputs.
