Scenario: Lunar Communication
=============================

## Scenario Definition
The Lunar Communication scenario has two service providers with similar assets. Each service provider has 1 control centre, 1 relay control centre, 1 GS, and 1 Relay and 1 Lunar asset. In addition the lunar gateway is orbiting the moon, able to communicate with all ground stations and relays as well as lunar assets. There are three "end users" in the scenario, a rover and base on the lunar surface as well as a user in the orbiting gateway. All of them have their own control centers on earth.

Further information about the scenario, including data rates, topology and background on the communication planning can be found in the [lunar-communications scenario description](https://github.com/esa/ccsds-dtn-reference-scenarios/blob/main/lunar-communication/v1.0/Lunar%20Communication%20Scenario.adoc) in the [ccsds-dtn-reference-scenarios repository](https://github.com/esa/ccsds-dtn-reference-scenarios).


## Topology

![lc topo](./extras/lc_simple.png)


## Contact Plans

The contact plan [actual_contacts.ccp](actual_contacts.ccp) is generated from `actual_contacts.csv` via `csv_to_ccp.py`.
The additionally provided [planned_contacts.ccp](planned_contacts.ccp) should be used inside the container to schedule communications, so that failure of a connection event can be accurately tested.

The compose file [compose.yml](compose.yml) is generated from the same CSV via `csv_to_compose.py`.

## Docker: Running the Scenario

1. start the docker containers and setup the network: `./start_topo.sh`
2. if you want fluctuating connectivity and bandwidth limitations: `./start_net.sh`
3. *OPTIONALLY: start the network visualization: `./start_viz.sh`*
4. *OPTIONALLY: start the docker test bed manager: `nse2_mgr compose.yml contacts.ccp`*

You can get an interactive shell on any of the nodes through docker: `docker exec -it <node> bash` or `nse2_sh <node>`
