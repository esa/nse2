#!/usr/bin/env python3

import sys
import argparse
import socket

sock = None

def send_udp_command(command, host='localhost', port=9966):
    """Send a command via UDP to the specified host and port."""
    global sock
    global verbose
    if sock is None:
      sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(command.encode(), (host, port))
        if verbose:
            print(f"Sent command: {command} to {host}:{port}", file=sys.stderr)
    except Exception as e:
        print(f"Failed to send command: {e}", file=sys.stderr)
        sys.exit(1)

def receive_udp_response(host='localhost', port=9966):
    """Receive a response via UDP from the specified host and port."""
    global sock
    global verbose
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(5)  # Set a timeout for receiving
        data, addr = sock.recvfrom(1024*64)  # Buffer size is 1024 bytes
        if verbose:
            print(f"Received response from {addr}: {data.decode()}", file=sys.stderr)
    except socket.timeout:
        print("No response received within the timeout period.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Failed to receive response: {e}", file=sys.stderr)
        return None
    return data.decode() if 'data' in locals() else None

def query_udp_command(command, host='localhost', port=9966):
    """Send a command and wait for a response."""
    send_udp_command(command, host, port)
    return receive_udp_response(host, port)

verbose = False
def main():
    global verbose
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="NSE2 Command Line Tool")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("command", help="The command to execute", choices=["pause", "resume", "next", "time", "scenario", "links"])
    # parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the command")

    args = parser.parse_args()
    verbose = args.verbose

    if args.command == "pause":
        print(f"Pause contact event processing")
        send_udp_command("pause")
    elif args.command == "next":
        print(f"Advancing to next contacts event")
        send_udp_command("next") 
    elif args.command == "resume":
        print(f"Resume contacts event processing")
        send_udp_command("resume") 
    elif args.command == "time":
        print(f"Querying simulation time and next event")
        res = query_udp_command("time")
        if res:
            sim_time, next_event = res.split()
            print(f"Simulation time: {sim_time}, Next event: {next_event}")
        else:
            print("Failed to retrieve simulation time.", file=sys.stderr)
    elif args.command == "scenario":
        print(f"Querying current scenario and contacts plan")
        res = query_udp_command("scenario")
        if res:
            scenario_name, ccp = res.split()
            print(f"Current scenario: {scenario_name}, Contacts plan: {ccp}")
    elif args.command == "links":
        print(f"Querying current links")
        res = query_udp_command("links")
        if res:
            print("Current links:")
            for line in res.splitlines():
                print(line)
        else:
            print("Failed to retrieve links.", file=sys.stderr) 
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()