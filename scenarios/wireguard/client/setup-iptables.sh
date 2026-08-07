#!/usr/bin/env bash
# Configures iptables forwarding and NAT for a WireGuard gateway container.
# It automatically detects all attached Docker network interfaces, allows
# traffic between them and WireGuard, and redirects traffic addressed to the
# gateway's Docker IPs to the application specified by APPLICATION_IP.
# Rules are added idempotently on "up" and removed on "down".
 
set -euo pipefail

if (( $# < 1 || $# > 2 )); then
    echo "Usage: $0 {up|down} [wireguard-interface]" >&2
    exit 2
fi

ACTION="$1"
WG_INTERFACE="${2:-wg0}"

APPLICATION_IP="${APPLICATION_IP:?APPLICATION_IP must be set}"

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

        # Redirect traffic addressed to this interface to the remote application.
        add_rule nat PREROUTING \
            -i "$lan_interface" \
            -m addrtype --dst-type LOCAL \
            -j DNAT --to-destination "$APPLICATION_IP"

        # Allow DNAT-translated traffic to reach the application through WireGuard.
        add_rule filter FORWARD \
            -i "$lan_interface" -o "$WG_INTERFACE" \
            -d "$APPLICATION_IP" \
            -j ACCEPT
    done

    # Allow response traffic from the remote application.
    add_rule filter FORWARD \
        -i "$WG_INTERFACE" \
        -s "$APPLICATION_IP" \
        -m conntrack --ctstate ESTABLISHED,RELATED \
        -j ACCEPT

    # Ensure the application sends responses back through this WireGuard client.
    add_rule nat POSTROUTING \
        -o "$WG_INTERFACE" \
        -d "$APPLICATION_IP" \
        -j MASQUERADE
}

remove_rules() {
    # Remove shared application rules first.
    remove_rule nat POSTROUTING \
        -o "$WG_INTERFACE" \
        -d "$APPLICATION_IP" \
        -j MASQUERADE

    remove_rule filter FORWARD \
        -i "$WG_INTERFACE" \
        -s "$APPLICATION_IP" \
        -m conntrack --ctstate ESTABLISHED,RELATED \
        -j ACCEPT

    # Remove interface-specific rules in reverse order.
    for lan_interface in "${LAN_INTERFACES[@]}"; do
        remove_rule filter FORWARD \
            -i "$lan_interface" -o "$WG_INTERFACE" \
            -d "$APPLICATION_IP" \
            -j ACCEPT

        remove_rule nat PREROUTING \
            -i "$lan_interface" \
            -m addrtype --dst-type LOCAL \
            -j DNAT --to-destination "$APPLICATION_IP"

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
