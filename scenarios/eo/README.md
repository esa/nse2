Scenario: Earth Observation
===========================

## Scenario Definition
The EO scenario is a simple network scenario with a single satellite, 2 ground stations, 1 mission control centre (MCS) and 1 payload centre.
In this scenario the satellite passes are frequent and data can be downlinked at high speed.

## Topology

![leo topo](./extras/leo.png)


## Datarates
|  from\to                   | Mission Control Centre | Payload Control Centre  | Ground Station 1 | Ground Station 2 | Satellite |
| -                          | -                      | -                       | -                |                  | -         |
| __Mission Control Centre__ | /                      | 0                       | 100 Mbps         | 100 Mbps         | 0         |
| __Payload Control Centre__ | 0                      | /                       | 100 Mbps         | 1000 Mbps        | 0         |
| __Ground Station 1__       | 100 Mbps               | 100 Mbps                | /                | 0                | 64 kbps   |
| __Ground Station 2__       | 100 Mbps               | 100 Mbps                | 0                | /                | 0         |
| __Satellite__              | 0                      | 0                       | 8Mbps            | 1000 Mbps        | /         |  

- TC Uplink: 64 kbps
- HK TM Downlink: 8 Mbps
- Payload TM Downlink: 1 Gbps


## Contacts

For this scenario, two contact plans are provided:
- [actual_contacts_speedup-100.ccp](actual_contacts_speedup-100.ccp): generated from `actual_contacts.csv` with `--speedup 100` for fast simulation runs.
- [actual_contacts.ccp](actual_contacts.ccp): generated from `actual_contacts.csv` with realistic timings in realtime.

By default the `start_net.sh` script runs the testing contacts but you can provide another contact plan as first parameter.

Additionally, the `planned_contacts` are also provided for the realtime and testing scenarios. They differ in relation to the `actual_contacts` by having a few more contacts, for which the reference scenario decided that a contact was planned, but not successful for whatever reason.
Software inside the container should use such a plan to schedule communications, so that failure of a connection event can be accurately tested.

## Actions

An [example action file](eo.actions) is provided. It just starts a few processes and cleans up stuff in the end. Here, one would usually start a BP agent and periodically send some messages.

## Docker: Running the Scenario

1. start the docker containers and setup the network: `./start_topo.sh`
2. if you want fluctuating connectivity and bandwidth limitations: `./start_net.sh`
3. start the automatic actions on the nodes: `./start_actions.sh`
4. *OPTIONALLY: start the network visualization: `./start_viz.sh`*
5. *OPTIONALLY: start the docker test bed manager: `nse2_mgr compose.yml actual_contacts.ccp`*

You can get an interactive shell on any of the nodes through docker: `docker exec -it <node> bash` or `nse2_sh <node>`
