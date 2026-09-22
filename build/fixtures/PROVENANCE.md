# Mock NX-OS Output Fixtures

| Fixture | Source |
|---|---|
| `real_show_interface_missing_subif.txt` | real — Nexus 9000v, NX-OS 10.4(2), DevNet sandbox, 2026-09-21: `show interface Ethernet1/20.100` before the sub-interface existed |
| `real_show_interface_subif_parent_down.txt` | real — same switch, same command, after Port Turn Up (before the parent `no shutdown` fix) |
| `real_show_running_config.txt` | real — same switch, `show running-config`; password hashes and SNMP keys redacted |
| `real_show_version.txt` | real — same switch, 2026-09-22: `show version` (running `10.4(2)`); serial number and hostname replaced |
| `real_dir_image_present.txt` | real — same switch, 2026-09-22: `dir bootflash:///nxos64-cs.10.4.2.F.bin`, an image that is staged |
| `real_dir_image_missing.txt` | real — same switch, 2026-09-22: `dir bootflash:///nxos64-cs.10.5.3.F.bin`, an image that is not |
| `error_invalid_command.txt` | real — ntc-templates `tests/cisco_nxos` capture (NX-OS parser error format) |
| `show_interface_subif_up.txt` | derived — header layout of a real ntc-templates `show interface` capture, renamed to sub-interface `Ethernet1/1.100` and set up |
| `error_invalid_interface_format.txt` | candidate — NX-OS wording for a malformed interface, from Cisco community reports |
| `empty.txt` | edge case — no output at all |
