## WireGuard External Service Example

Brings an external service (different machine, cloud container, hardware) into a nse2 simulation through a WireGuard tunnel. The `wg-client` acts as a transparent proxy: nodes send traffic to its Docker IPs, iptables DNAT forwards it over the
tunnel.

```
n1 (curl wg-client@172.30.0.2) -> wg-client -> WG tunnel -> external app
n2 (curl wg-client@172.31.0.2) -> wg-client -> WG tunnel -> external app
external app (curl n1@172.30.3) -> wg-server -> WG tunnel -> n1
```

The WireGuard server and application run on a separate host using the compose file in `server/`. After server startup the resulting configuration in `./server/runtime/config/peer_nse2client/peer_nse2client.conf` needs to be copied over to the client.

### Setup

**1.** Create the environment file:

```sh
cp .env.example .env
```

Edit `.env` and set `SERVER_URL` to the public IP of the external host.

**2.** On the external host, start the WireGuard server and the example application:

```sh
cd server
cp ../.env .
docker compose up -d
```

This starts `wg-server` (LinuxServer.io image in server mode, auto-generating keys) and `app` (Alpine HTTP server on port 80, sharing the server's network namespace).

**3.** Copy the generated client config to the NSE2 host:

```sh
# Same machine:
cp server/runtime/config/peer_nse2client/peer_nse2client.conf runtime/wg-confs/wg0.conf

# Different machine:
scp server/runtime/config/peer_nse2client/peer_nse2client.conf \
    user@nse2-host:scenarios/wireguard/runtime/wg-confs/wg0.conf
```

**4.** Start the NSE2 scenario:

```sh
nse2_topo ./compose.yml
```

### Testing

```sh
# From n1 (on wg_n1 network):
docker compose exec n1 curl http://172.30.0.2
docker compose exec n1 curl http://wg-client

# From n2 (on wg_n2 network):
docker compose exec n2 curl http://172.31.0.2
docker compose exec n2 curl http://wg-client

# All should return: Hello from external WireGuard service!
```

From the server side, the app can reach NSE2 nodes through the tunnel:

```sh
docker compose -f ./server/compose.yml exec wg-server ping -c 2 172.30.0.3
```
