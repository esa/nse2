import random
import json
from copy import deepcopy

try:
    import pons
    import pons.routing
except ImportError:
    print("Please install the pons-dtn package")

RANDOM_SEED = 42
CAPACITY = 1_000_000
# CAPACITY = 0
DEFAULT_TTL = 3600 * 72  # 72h


random.seed(RANDOM_SEED)

netplan = pons.net.NetworkPlan.from_graphml("mc.graphml")

print(netplan.nodes())
print(netplan.connections())

contactplan = pons.CoreContactPlan.from_file("mc.contacts.ccp", netplan.mapping)
netplan.set_contacts(contactplan)

import sys

# epidemic = pons.routing.EpidemicRouter(capacity=CAPACITY)

# static routing needs to be passed the full contact graph with all POSSIBLE edges
static = pons.routing.StaticRouter(capacity=CAPACITY, graph=netplan.full_graph)

nodes = pons.generate_nodes_from_graph(
    netplan.G, router=static, contactplan=contactplan
)
config = {
    "movement_logger": False,
    "peers_logger": False,
    "event_logging": True,
    "event_filter": ["NET"],
    "real_scan": False,
}

SIM_TIME = contactplan.get_max_time() + 0.5
# SIM_TIME = 20000

netsim = pons.NetSim(SIM_TIME, nodes, config=config)


isp_a_tm_hk_sender = pons.apps.PingApp(
    dst=netplan.mapping["rcc1"],
    interval=300,
    ttl=DEFAULT_TTL,
    size=1024,
    rnd_start=True,
)
isp_b_tm_hk_sender = pons.apps.PingApp(
    dst=netplan.mapping["rcc2"],
    interval=300,
    ttl=DEFAULT_TTL,
    size=1024,
    rnd_start=True,
)
rover1_tm_hk_sender = pons.apps.PingApp(
    dst=netplan.mapping["r1cc"],
    interval=300,
    ttl=DEFAULT_TTL,
    size=1024,
    rnd_start=True,
)
rover2_tm_hk_sender = pons.apps.PingApp(
    dst=netplan.mapping["r2cc"],
    interval=300,
    ttl=DEFAULT_TTL,
    size=1024,
    rnd_start=True,
)


tm_receiver = pons.apps.PingApp(dst=0, interval=-1, ttl=0, size=0)


netsim.install_app("gs1", isp_a_tm_hk_sender)
netsim.install_app("relay1", isp_a_tm_hk_sender)
netsim.install_app("rcc1", tm_receiver)

netsim.install_app("gs2", isp_b_tm_hk_sender)
netsim.install_app("relay2", isp_b_tm_hk_sender)
netsim.install_app("relay3", isp_b_tm_hk_sender)
netsim.install_app("rcc2", tm_receiver)

netsim.install_app("rover1", rover1_tm_hk_sender)
netsim.install_app("r1cc", tm_receiver)

netsim.install_app("rover2", rover2_tm_hk_sender)
netsim.install_app("r2cc", tm_receiver)


for n in netsim.nodes.values():
    print("node: ", n)

netsim.setup()
# cProfile.run("netsim.run()")
netsim.run()

# print(json.dumps(netsim.net_stats, indent=4))
print(json.dumps(netsim.routing_stats, indent=4))
