#!/usr/bin/env bash
# Configures iptables forwarding and NAT for a WireGuard gateway container.
# It automatically detects all attached Docker network interfaces, allows
# traffic between them and WireGuard, and redirects traffic addressed to the
# gateway's Docker IPs to its single WireGuard peer.
# Rules are added idempotently on "up" and removed on "down".

set -euo pipefail

if (( $# < 1 || $# > 2 )); then
    echo "Usage: $0 {up|down} [wireguard-interface]" >&2
    exit 2
fi

ACTION="$1"
WG_INTERFACE="${2:-wg0}"
STATE_FILE="/run/iptables-${WG_INTERFACE}.state"

# All container interfaces except loopback and WireGuard.
mapfile -t LAN_INTERFACES < <(
    find /sys/class/net -mindepth 1 -maxdepth 1 -printf '%f\n' |
        grep -vE "^(lo|${WG_INTERFACE})$" |
        sort
)

if [[ ${#LAN_INTERFACES[@]} -eq 0 ]]; then
    echo "No Docker network interfaces found" >&2
    exit 1
fi

add_rule() {
    local table="$1"
    shift

    iptables -w -t "$table" -C "$@" 2>/dev/null ||
        iptables -w -t "$table" -A "$@"
}

remove_rule() {
    local table="$1"
    shift

    while iptables -w -t "$table" -C "$@" 2>/dev/null; do
        iptables -w -t "$table" -D "$@"
    done
}

configure_rules() {
    # Determine the tunnel IP of the gateway's single WireGuard peer.
    mapfile -t peer_ips < <(
        wg show "$WG_INTERFACE" allowed-ips |
            grep -oE '[0-9]+(\.[0-9]+){3}/32' |
            cut -d/ -f1
    )

    if [[ ${#peer_ips[@]} -ne 1 ]]; then
        echo "Expected exactly one peer /32 address, found ${#peer_ips[@]}" >&2
        exit 1
    fi

    TARGET_PEER_IP="${peer_ips[0]}"
    WIREGUARD_PORT="$(wg show "$WG_INTERFACE" listen-port)"

    if [[ -z "$WIREGUARD_PORT" || "$WIREGUARD_PORT" == "0" ]]; then
        echo "Could not determine the WireGuard listening port" >&2
        exit 1
    fi

    # PostDown runs after the WireGuard interface is removed, so preserve the
    # values required to remove the rules.
    printf '%s\n%s\n' \
        "$TARGET_PEER_IP" \
        "$WIREGUARD_PORT" > "$STATE_FILE"

    for lan_interface in "${LAN_INTERFACES[@]}"; do
        # Allow WireGuard peers to access this Docker network.
        add_rule filter FORWARD \
            -i "$WG_INTERFACE" -o "$lan_interface" \
            -j ACCEPT

        # Allow response traffic from this Docker network back through WireGuard.
        add_rule filter FORWARD \
            -i "$lan_interface" -o "$WG_INTERFACE" \
            -m conntrack --ctstate ESTABLISHED,RELATED \
            -j ACCEPT

        # Hide WireGuard source addresses behind this interface's address.
        add_rule nat POSTROUTING \
            -o "$lan_interface" \
            -j MASQUERADE

        # Keep the outer WireGuard traffic on the gateway itself.
        # This rule must precede the catch-all DNAT rule below.
        add_rule nat PREROUTING \
            -i "$lan_interface" \
            -p udp --dport "$WIREGUARD_PORT" \
            -j ACCEPT

        # Redirect all other traffic addressed to the gateway to its peer.
        add_rule nat PREROUTING \
            -i "$lan_interface" \
            -m addrtype --dst-type LOCAL \
            -j DNAT --to-destination "$TARGET_PEER_IP"

        # Allow DNAT-translated traffic to reach the peer through WireGuard.
        add_rule filter FORWARD \
            -i "$lan_interface" -o "$WG_INTERFACE" \
            -d "$TARGET_PEER_IP" \
            -j ACCEPT
    done

    # Allow response traffic from the remote peer.
    add_rule filter FORWARD \
        -i "$WG_INTERFACE" \
        -s "$TARGET_PEER_IP" \
        -m conntrack --ctstate ESTABLISHED,RELATED \
        -j ACCEPT

    # Ensure the peer sends responses back through this gateway.
    add_rule nat POSTROUTING \
        -o "$WG_INTERFACE" \
        -d "$TARGET_PEER_IP" \
        -j MASQUERADE
}

remove_rules() {
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "State file not found: $STATE_FILE" >&2
        exit 1
    fi

    mapfile -t state < "$STATE_FILE"
    TARGET_PEER_IP="${state[0]}"
    WIREGUARD_PORT="${state[1]}"

    # Remove shared peer rules first.
    remove_rule nat POSTROUTING \
        -o "$WG_INTERFACE" \
        -d "$TARGET_PEER_IP" \
        -j MASQUERADE

    remove_rule filter FORWARD \
        -i "$WG_INTERFACE" \
        -s "$TARGET_PEER_IP" \
        -m conntrack --ctstate ESTABLISHED,RELATED \
        -j ACCEPT

    # Remove interface-specific rules in reverse order.
    for lan_interface in "${LAN_INTERFACES[@]}"; do
        remove_rule filter FORWARD \
            -i "$lan_interface" -o "$WG_INTERFACE" \
            -d "$TARGET_PEER_IP" \
            -j ACCEPT

        remove_rule nat PREROUTING \
            -i "$lan_interface" \
            -m addrtype --dst-type LOCAL \
            -j DNAT --to-destination "$TARGET_PEER_IP"

        remove_rule nat PREROUTING \
            -i "$lan_interface" \
            -p udp --dport "$WIREGUARD_PORT" \
            -j ACCEPT

        remove_rule nat POSTROUTING \
            -o "$lan_interface" \
            -j MASQUERADE

        remove_rule filter FORWARD \
            -i "$lan_interface" -o "$WG_INTERFACE" \
            -m conntrack --ctstate ESTABLISHED,RELATED \
            -j ACCEPT

        remove_rule filter FORWARD \
            -i "$WG_INTERFACE" -o "$lan_interface" \
            -j ACCEPT
    done

    rm -f "$STATE_FILE"
}

case "$ACTION" in
    up)
        configure_rules
        ;;
    down)
        remove_rules
        ;;
    *)
        echo "Usage: $0 {up|down} [wireguard-interface]" >&2
        exit 2
        ;;
esac
