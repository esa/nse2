Scenario: Mars Communication
============================

## Scenario Definition
The Mars communication scenario keeps a similar topology to the Lunar scenario, however relays cannot communicate between each others and links have much larger delays between Earth and Mars. In this scenario we have two service providers, with respectively one and two relay orbiters. Both providers have a low altitude orbiter and the second provider a high altitude one as well that provides coverage for both rovers. In this scenario the contacts are much more sparse and shorter in time, providing a more challenging communication environment. Direct links with Earth are not available, and relays do not communicate between each other to relay data, as the current Mars Orbiters are alos not communicating with each other. 

Further information about the scenario, including data rates, topology and background on the communication planning can be found in the [mars-communications scenario description](https://github.com/esa/ccsds-dtn-reference-scenarios/blob/main/mars-communication/v1.0/Mars%20Communication%20Scenario.adoc) in the [ccsds-dtn-reference-scenarios repository](https://github.com/esa/ccsds-dtn-reference-scenarios).


## Topology
![mc topo](./extras/mc.png)

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
