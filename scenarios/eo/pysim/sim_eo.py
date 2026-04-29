import random
import json
from copy import deepcopy
import json

try:
    import pons
    import pons.routing
except ImportError:
    print("Please install the pons-dtn package")

RANDOM_SEED = 42
CAPACITY = 5_000_000_000
# CAPACITY = 0
DEFAULT_TTL = 3600 * 24  # 24h


random.seed(RANDOM_SEED)

import_map = json.load(open("node_mapping.json"))
print(import_map)

netplan = pons.net.NetworkPlan.from_graphml("eo.graphml")

print(netplan.nodes())
print(netplan.connections())

contactplan = pons.CoreContactPlan.from_file("eo.contacts.ccp", netplan.mapping)
# contactplan2 = pons.CoreContactPlan.from_csv_file(
#     "../contacts.csv",
#     netplan.mapping,
#     parse_header=True,
#     node_rename_mapping=import_map,
# )
print(contactplan)
# print(contactplan2)
# contactplan = contactplan2
# sys.exit(0)
netplan.set_contacts(contactplan)

# router = pons.routing.EpidemicRouter(capacity=CAPACITY)

# static routing needs to be passed the full contact graph with all POSSIBLE edges
router = pons.routing.StaticRouter(capacity=CAPACITY, graph=netplan.full_graph)

nodes = pons.generate_nodes_from_graph(
    netplan.G, router=router, contactplan=contactplan
)
config = {
    "movement_logger": False,
    "peers_logger": False,
    "event_logging": False,
    "event_filter": ["NET"],
}

SIM_TIME = contactplan.get_max_time() + 0.5
# SIM_TIME = 20000

netsim = pons.NetSim(SIM_TIME, nodes, config=config)

eosat_tm_hk_sender = pons.apps.PingApp(
    dst=netplan.mapping["mcc"], interval=300, ttl=DEFAULT_TTL, size=1024, rnd_start=True
)

print(netplan.mapping["pcc"])
eosat_tm_payload_sender = pons.apps.PingApp(
    dst=netplan.mapping["pcc"],
    interval=30,
    ttl=DEFAULT_TTL,
    size=1024 * 1024,
    rnd_start=True,
)

tm_receiver = pons.apps.PingApp(dst=0, interval=-1, ttl=0, size=0)


netsim.install_app("eosat", eosat_tm_hk_sender)
netsim.install_app("eosat", eosat_tm_payload_sender)
netsim.install_app("mcc", tm_receiver)
netsim.install_app("pcc", tm_receiver)

for n in netsim.nodes.values():
    print("node: ", n)

netsim.setup()
# cProfile.run("netsim.run()")
netsim.run()

# print(json.dumps(netsim.net_stats, indent=4))
print(json.dumps(netsim.routing_stats, indent=4))
