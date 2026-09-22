# Testing the Pack on a Real Nexus from Cisco DevNet

How the pack was tested on a real Nexus 9000v: a reserved Cisco DevNet sandbox, driven by an
Itential Platform through its Gateway. Everything here is temporary test scaffolding. None of it
belongs in the contribution, and the last section removes it again.

Replace every `<placeholder>` with your own value.

## What You Need

- An Itential Platform (tested on 6.5.2) with an Itential Gateway 5 cluster, and API access to it.
- A DevNet sandbox reservation that includes an NX-OS 9000v, for example a CML-based lab. You get
  the VPN host, VPN credentials, and the switch's address and login from the reservation email.
- `openconnect` on your workstation (`brew install openconnect` on macOS), and SSH access to the
  Gateway host.
- The pack imported: the project and the three golden config trees.

## How It Fits Together

```
Platform -> Gateway runner (container) -> bridge forwarder on the Gateway host
         -> reverse SSH tunnel -> your workstation -> DevNet VPN -> Nexus switch
```

Only your workstation can reach the sandbox, over its VPN. The Gateway runner reaches the switch
through a reverse SSH tunnel to the Gateway host. The runner usually runs in a container on a
Docker bridge network, and `sshd` binds a reverse tunnel to loopback only, so a small forwarder
on the bridge's gateway address connects the two.

## Steps

**1. Connect the VPN (window 1).** Keep it open.

```bash
sudo openconnect --no-dtls --script ./devnet/devnet-split.sh <sandbox-vpn-host>:<port>
```

- `--no-dtls` keeps all traffic on the TCP channel, which survives Wi-Fi blips. The UDP channel
  failed repeatedly in testing.
- `devnet-split.sh` routes only the sandbox subnet (`SANDBOX_NET`, default `10.10.20.0/24`)
  through the VPN. The sandbox VPN otherwise becomes your default DNS resolver, and
  everything else on your workstation stops resolving while it's up.

**2. Find the runner's bridge address** on the Gateway host:

```bash
docker network inspect <gateway-network> --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'
```

**3. Start the tunnel and forwarder (window 2),** from the repo root. Keep it open.

```bash
ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -R 127.0.0.1:2222:<switch-ip>:22 <user>@<gateway-host> \
  "LISTEN_ADDR=<bridge-address> PORT=2222 python3 -c 'import base64;exec(base64.b64decode(\"$(base64 -i devnet/bridge_fwd.py | tr -d '\n')\"))'"
```

Wait for `bridge forwarder: <bridge-address>:2222 -> tunnel -> switch`.

**4. Create an inventory for the switch** with the built-in broker actions on your Gateway
cluster. The Inventory Manager UI may not offer these two options; the API does:

```
POST /inventory_manager/v1/inventories
{"name": "nxos-devnet", "groups": ["<your-group>"], "createBrokerActions": true,
 "defaultClusterId": "<gateway-cluster>"}
```

**5. Add the switch as a node.** `cluster_id` is required: without it the device never
appears in Configuration Manager.

```
POST /inventory_manager/v1/nodes/bulk
{"inventory_identifier": "nxos-devnet", "nodes": [{"name": "devnet-n9k", "attributes": {
  "itential_host": "<bridge-address>", "itential_port": 2222, "itential_driver": "netmiko",
  "itential_platform": "cisco_nxos", "itential_user": "<switch-user>",
  "itential_password": "<switch-password>", "cluster_id": "<gateway-cluster>"}}]}
```

**6. Publish it to Configuration Manager.** Add `nxos-devnet` to the `inventories` list of your
Device Broker adapter (the built-in Inventory Manager adapter). Note the current list first so
you can restore it. Then call `POST /configuration_manager/devices/refresh`.

**7. Set the placeholders on your Platform copy only.** The repo keeps them as documented
placeholders. In Studio:

| Workflow | Task | Field |
|---|---|---|
| Run Compliance | Get treeId | `clusterId` → your Gateway cluster |
| Port Turn Up | Send Config: Port Turn Up | `clusterId` → your Gateway cluster |
| Create & Update Inventory from NetBox | Create a new inventory | `groups`, `defaultClusterId` |

**8. Bind the switch to each tree's `base` node.** Look the tree IDs up by name first, because
they change whenever a tree file's content changes:

```
POST /configuration_manager/configs/<tree-id>/initial/base/devices   {"devices": ["devnet-n9k"]}
```

**9. Prove the path.** `GET /configuration_manager/devices/devnet-n9k/isAlive` must return
`true` within a few seconds. A `false` after about 60 seconds is the connection timeout: the
VPN or the tunnel is down.

## What Was Run, and What to Expect

| Run | Inputs | Expected |
|---|---|---|
| Run Compliance | `tree_name` each of the three trees, `version: initial` | Complete. An unconfigured sandbox switch scores low, and every remaining finding is a real gap. None of `username`, `version`, `ssh login-attempts` is flagged |
| Port Turn Up | a spare, unconfigured port, e.g. `Ethernet1/20`, sub-interface `100`, a documentation address | Complete; the switch shows the parent routed and admin-up and the sub-interface configured. With no cable it reports `down (Parent interface down)` |
| NX-OS Upgrade | not run on the sandbox: it needs a second NX-OS image staged in `bootflash:`, and `install all` reloads the switch | With an image staged, Complete; `show version` reports the target version |
| Create & Update Inventory from NetBox | an inventory name that doesn't exist yet | Complete; the lookup errors (by design), the inventory is created and populated |
| Clear & Delete Inventory | that same inventory | Complete; the inventory is gone |

## Troubleshooting

**Name resolution breaks for everything once the VPN is up.** The default openconnect script
made the sandbox VPN your default DNS resolver. Use `--script ./devnet/devnet-split.sh`.

**`isAlive` goes from `true` to a 60-second `false` and stays there.** The VPN or the tunnel
dropped, and the Gateway host kept the tunnel's far end open: its listeners accept connections
that lead nowhere. On the Gateway host, end the orphaned `sshd` session that owns the port, and
its forwarder, then restart step 3. If your workstation's address changed (for example Wi-Fi
rejoined another network), restart the VPN too.

**`Adapter:undefined failed to invoke getDevice`.** The node isn't in Configuration Manager.
Check `cluster_id` (step 5) and the broker's `inventories` list (step 6), then refresh.

## Clean Up

1. Unbind the switch from the trees, and restore the placeholders you changed in step 7, or
   re-import the project.
2. Restore the Device Broker adapter's `inventories` list.
3. Delete the `nxos-devnet` inventory.
4. Remove the test sub-interface from the switch, or let the reservation expire.
5. Close the tunnel and VPN windows.
