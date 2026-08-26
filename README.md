# AGSA Labs Network Simulation & Emulation Environment (NSE2)

`NSE2` is a docker-compose-based network simulator/emulator that can also simulate fluctuating network connectivity with contact plans and automated playback of commands on the virtual nodes.


## Requirements

- python3
- docker
- docker compose

## Installation

Create a virtual environment and install the project:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

When developing, use an editable install so changes take effect immediately:

```sh
pip install -e ".[dev]"
```

To pin dependencies to the exact versions tested in this repo (recommended), add `-c constraints.txt` to either command.

Once installed, all `nse2_*` tools and helpers are available on PATH whenever the venv is active.

## Documentation

For a comprehensive guide, please see the [NSE2 User Manual](doc/manual/manual.pdf) (AsciiDoc source available in [doc/manual/manual.adoc](doc/manual/manual.adoc)).

## Usage

There are a few main commands for running and controlling a simulation:
- `nse2_topo` to start the containers and setup topology.
- `nse2_contacts` to playback a contact file.
- `nse2_actions` to execute actions at specific points in time. 
- `nse2_sh` to open a shell on any of the containers. 
- `nse2_cmd` to interact with the simulation contacts backend and control playback.
- `nse2_netviz` to run the web visualizer. 
- `nse2_mgr` to run the docker testbed manager webui for live changes to link properties. 

## Examples

Various example scenarios are provided under `scenarios/` that include network topologies, contact plans and demo actions.

- [scenarios/simple](scenarios/simple) is a basic 3-node testing scenario.
- [scenarios/eo](scenarios/eo) is a simple earth observation scenario.
- [scenarios/lc](scenarios/lc) is complex scenario modelling lunar communication.
- [scenarios/mc](scenarios/mc) is a mid-size mars communication scenario.
