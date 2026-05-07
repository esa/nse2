# Contact Plan
# Defines scheduled contacts and fixed links between nodes.
#
# Directives:
#   s loop <n> : loop behaviour — 1 to repeat indefinitely, 0 (or omit) for no loop
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


# enable looping of the contact plan
s loop 1

# define a symmetric connection between mcc and gs1
# <type> <src>  <dst>       [bw]  [loss] [delay] [jitter] [=]
a fixed   mcc  gs1         10mbit  0.0    300     0        =

# define both directions explicitly, for mcc and gs2
a fixed   mcc  gs2         10mbit  0.0    300     0
a fixed   gs2  mcc         10mbit  0.0    300     0

# instead of node names, specific interfaces can also be used
a fixed   pcc  dev:gs1_pcc 10mbit  0.0    300     0
a fixed   gs1  dev:gs1_pcc 10mbit  0.0    300     0

a fixed   pcc  dev:gs2_pcc 10mbit  0.0    300     0
a fixed   gs2  dev:gs2_pcc 10mbit  0.0    300     0


# define the asymmetric, fluctuating connections between eosat and gs1
# one entry for each direction, defining the outgoing bandwidth 
# <type>  <start> <end> <src>  <dst>             [bw]    [loss] [delay] [jitter] [=]
a contact  +30     +60  gs1    dev:eosat_gs1_lo  100kbit  0.0    0       0
a contact  +30     +60  eosat  dev:eosat_gs1_lo    1mbit  0.0    0       0

a contact  +30     +60  gs1    dev:eosat_gs1_hi  100kbit  0.0    0       0
a contact  +30     +60  eosat  dev:eosat_gs1_hi 1000mbit  0.0    0       0

# eosat and gs2
a contact  +90    +120  gs2    dev:eosat_gs2_lo  100kbit  0.0    0       0
a contact  +90    +120  eosat  dev:eosat_gs2_lo    1mbit  0.0    0       0

a contact  +90    +120  gs2    dev:eosat_gs2_hi  100kbit  0.0    0       0
a contact  +90    +120  eosat  dev:eosat_gs2_hi 1000mbit  0.0    0       0
