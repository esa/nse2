# Contact Plan
# Defines scheduled contacts and fixed links between nodes.
#
# Directives:
#   s loop <n>        : loop behaviour — 1 to repeat indefinitely, 0 (or omit) for no loop
#   a <contact|fixed> : add a fixed link or a fluctuating contact with properties described below 
#
# Columns:
#   type      : 'a contact' for scheduled links, 'a fixed' for fixed links
#   start     : contact start time relative to scenario start (seconds, +offset)
#   end       : contact end time relative to scenario start (seconds, +offset)
#   src       : source node (node ID | node name)
#   dst       : destination node (node ID | node name | `dev:<interfacename>`)
#   bw        : bandwidth (e.g. 30mbit)
#   loss      : packet loss percentage (e.g. 0.0)
#   delay     : one-way propagation delay (ms)
#   jitter    : delay jitter (ms)
#   symmetric : '=' to apply the link in both directions, omit for one-way

s loop 1

# n2 has a stable path to the WireGuard gateway.
# n3_wg's wg_transport network is intentionally not part of the contact plan;
# it carries the outer WireGuard traffic without these link conditions.

# <fixed> <src> <dst>    [bw] [loss] [delay] [jitter] [=]
a fixed   n2    n3_wg 100mbit    0.0      50      0.0   =

# n1 is reachable only during this scheduled contact. The contact player
# applies 100% loss to this link outside the active interval.

# <contact> <start> <end> <src> <dst>  [bw] [loss] [delay] [jitter] [=]
a contact       +20   +40 n1    n3_wg 2mbit    0.0      30      0.0   =
