#!/usr/bin/env python3

import sys
import os
import time
import socket
import argparse
import configparser
import signal
import select
from threading import Thread
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
parser.add_argument("config", help="Configuration file")
args = parser.parse_args()

config = configparser.ConfigParser()
config.read(args.config)
sockets = []
mapping = {}


def find_dev_for_ip(ip):
    output = (
        subprocess.run(["ip", "route", "get", ip], check=True, stdout=subprocess.PIPE)
        .stdout.decode("utf-8")
        .split("\n")
    )
    for line in output:
        if "dev" in line:
            return line.split(" ")[3]
    return None


for section in config.sections():
    print(f"[{section}]")
    for key, value in config[section].items():
        print(f"{key} = {value}")
    print()
    if "port" in config[section]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        port = int(config[section]["port"])
        delay = 0
        dst = config[section]["dst"].split(":")
        dst_ip = dst[0]
        dst_port = int(dst[1])
        if "delay" in config[section]:
            delay = float(config[section]["delay"]) / 1000
        s.bind(("", port))
        sockets.append(s)
        mapping[port] = {
            "name": section,
            "delay": delay,
            "dst": (dst_ip, dst_port),
            "available": True,
            "dev": find_dev_for_ip(dst_ip),
        }

running = True


def signal_handler(sig, frame):
    global running
    running = False
    print("Exiting...")


def check_qdisc_status():
    global running
    global mapping
    global args
    while running:
        output = (
            subprocess.run(["tc", "qdisc", "show"], check=True, stdout=subprocess.PIPE)
            .stdout.decode("utf-8")
            .split("\n")
        )
        for line in output:
            if len(line) == 0:
                continue
            data = line.split(" ")
            for key, value in mapping.items():
                dev = data[4]
                if dev == value["dev"]:
                    if "loss 100%" in output:
                        if value["available"] and args.verbose:
                            print(f"Disabling {value['name']} due to 100% loss")
                        value["available"] = False
                    else:
                        if not value["available"] and args.verbose:
                            print(f"Enabling {value['name']} due to no loss")
                        value["available"] = True
        time.sleep(1)


def delayed_send(s, data, dst, delay):
    time.sleep(delay)
    s.sendto(data, dst)


Thread(target=check_qdisc_status).start()

signal.signal(signal.SIGINT, signal_handler)
while running:
    rlist, wlist, xlist = select.select(sockets, [], [], 1.0)
    for s in rlist:
        data, addr = s.recvfrom(65535)
        lport = s.getsockname()[1]
        print(f"Received {data} from {addr} on port {lport} -> {mapping[lport]}")
        if mapping[lport]["delay"] == 0:
            s.sendto(data, mapping[lport]["dst"])
        else:
            if mapping[lport]["available"]:
                tid = Thread(
                    target=delayed_send,
                    args=(s, data, mapping[lport]["dst"], mapping[lport]["delay"]),
                    daemon=True,
                ).start()
            else:
                if args.verbose:
                    print(
                        f"Packet dropped due to 100% loss on {mapping[lport]['name']}"
                    )

for s in sockets:
    s.close()
