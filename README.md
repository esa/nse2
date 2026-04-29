# AGSA Labs Network Simulation & Emulation Environment (NSE2)

`NSE2` is a docker-compose-based network simulator/emulator that can also simulate fluctuating network connectivity with contact plans and automated playback of commands on the virtual nodes.


## Requirements

- python3
- docker
- docker compose

## Installation

You need a bunch of python libraries installed, preferably in a virtual environment, and the `nse2` tools should be added to your PATH environment variable.

First step should be creating a clean venv and installing the python dependencies.
```
$ python3 -m venv .venv
$ pip3 install -r requirements.txt
``` 

Then all relevant tools should be added to the PATH for convenience.

```
$ . load_env.sh
Activating virtual environment
Adding tools/bin and tools/helpers to PATH
```

Alternatively, you can use the `install_symlinks.sh` script to install all tools in your `.venv/bin` (default) or a user supplied path.

Afterwards, all `nse2` tools are available to run network simulations.

## Usage

There are a few main commands for running and controlling a simulation:
- `nse2_run` to start the containers and setup topology.
- `nse2_contacts` to playback a contact file.
- `nse2_actions` to execute actions at specific points in time. 
- `nse2_sh` to open a shell on any of the containers. 
- `nse2_netviz` to run the web visualizer. 
- `nse2_mgr` to run the docker testbed manager webui for live changes to link properties. 

## Examples

Various example scenarios are provided under `scenarios/` that include network topologies, contact plans and demo actions.

- [scenarios/eo](scenarios/eo) is a simple earth observation scenario.
- [scenarios/lc](scenarios/lc) is complex scenario modelling lunar communication.
- [scenarios/mc](scenarios/mc) is a mid-size mars communication scenario.
