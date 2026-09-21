#!/bin/sh
# Split-tunnel script for openconnect on macOS. Use it in place of the default vpnc-script:
#
#   sudo openconnect --no-dtls --script /path/to/devnet-split.sh <sandbox-vpn-host>:<port>
#
# The DevNet sandbox VPN otherwise installs itself as the default DNS resolver, which breaks
# name resolution for everything else on the workstation while it is up. This script brings
# up the tunnel interface and routes ONLY the sandbox device subnet through it. It never
# touches DNS or the default route. Set SANDBOX_NET to your reservation's device subnet.
SANDBOX_NET=${SANDBOX_NET:-10.10.20.0/24}

case "$reason" in
  connect)
    ifconfig "$TUNDEV" inet "$INTERNAL_IP4_ADDRESS" "$INTERNAL_IP4_ADDRESS" \
      netmask 255.255.255.255 mtu "${INTERNAL_IP4_MTU:-1300}" up
    route -n add -net "$SANDBOX_NET" -interface "$TUNDEV" >/dev/null
    echo "split tunnel up: $SANDBOX_NET via $TUNDEV ($INTERNAL_IP4_ADDRESS); DNS untouched"
    ;;
  disconnect)
    route -n delete -net "$SANDBOX_NET" >/dev/null 2>&1
    echo "split tunnel down"
    ;;
esac
exit 0
