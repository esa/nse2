# AGSA Labs Network Simulation & Emulation Environment (NSE2)

`NSE2` is a docker-compose-based network simulator/emulator that can also simulate fluctuating network connectivity with contact plans and automated playback of commands on the virtual nodes.


## Requirements

- python3
- docker
- docker compose

## Installation

To install `NSE2`, you need to set up a Python virtual environment, install the required dependencies, and make the `nse2` tools accessible in your PATH.

First, create a clean virtual environment:
```
$ python3 -m venv .venv
```

The recommended approach to activate the environment and set up your PATH is to source `load_env.sh`. Do this before installing the dependencies:
```
$ source load_env.sh
Activating virtual environment
Adding tools/bin and tools/helpers to PATH
$ pip3 install -r requirements.txt
```

**Alternative approach using symlinks:**
If you prefer not to source `load_env.sh` every time you start a new shell session, you can manually activate the environment, install the dependencies, and use the `install_symlinks.sh` script. This script installs all tools into your `.venv/bin` directory (or a user-supplied path), so they are automatically available whenever the virtual environment is active:
```
$ source .venv/bin/activate
$ pip3 install -r requirements.txt
$ ./install_symlinks.sh
```

Afterwards, all `nse2` tools are available to run network simulations.

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
