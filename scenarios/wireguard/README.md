## WireGuard External Service Example

This scenario connects one external service to NSE2 through a WireGuard tunnel.
NSE2 runs the WireGuard server alongside the example nodes `n1` and `n2`.
The external host runs the WireGuard client and an application that shares the client's network namespace.

This example uses the [LinuxServer.io WireGuard container](https://github.com/linuxserver/docker-wireguard).
Refer to its documentation for additional configuration options and container requirements.


```mermaid
flowchart LR
    subgraph NSE2["NSE2 Host"]
        n1["Node n1"]
        n2["Node n2"]
        server["'Virtual Node' n3_wg<br/>WG server / Transparent Proxy"]

        n1 <--> server
        n2 <--> server
    end

    subgraph External["External Host"]
        client["WireGuard Client"]
        app["External Application"]
        client --- app
    end

    server <-->|"WireGuard Tunnel"| client
```

Traffic addressed to either of the `n3_wg` Docker addresses is DNATed by `server/setup-iptables.sh` to the external peer's tunnel address.
The external application shares the WireGuard client's network namespace and therefore requires no additional routing configuration.

This setup needs one WireGuard server for each external Node / peer.

### Configuration

Before starting the server, review the following values in `compose.yml`:

- `SERVERURL` must be an address through which the external host can reach the NSE2 host. Use `host.docker.internal` when testing both sides on the same machine.
- `SERVERPORT` must match the UDP port published by the `n3_wg` service.
- `ALLOWEDIPS` must include every NSE2 network that the external service should be able to reach through the tunnel.

The templates `server/templates/server.conf` and `server/templates/peer.conf` are mounted into the WireGuard container.
The peer template adds `PersistentKeepalive = 25` to the generated client configuration: the external peer sits behind NAT and must initiate and periodically refresh the tunnel, since the server cannot reach it otherwise.


### Topology Setup 

The topology consists of the NSE2-side services/nodes with the WireGuard server in the `compose.yml` file.
And the WireGuard client with its external application in `compose-client.yml`.
First, the NSE2 nodes are started with:

```sh
nse2_topo compose.yml
```

The WireGuard server (`n3_wg`) generates its keys and the external peer configuration under `server/runtime`.
The generated client configuration is then available at:

```text
server/runtime/peer_external/peer_external.conf
```

Copy this file to `client/wg0.conf` on the external host, to let the WireGuard client and the external app connect to NSE2:

```sh
scp server/runtime/peer_external/peer_external.conf \
    user@external-host:/path/to/examples/wireguard/client/wg0.conf
```

The configuration contains the external peer's private key and must not be committed to Git. 
Start the WireGuard client and external application:

```sh
docker compose -f compose-client.yml up -d
```


### Topology Setup Testing

Check that the tunnel has been established successfully and client and peer exchanged a handshake:

```sh
docker compose exec n3_wg wg show
docker compose -f compose-client.yml exec wg-client wg show
```

The output should show the `latest handshake` to be a few seconds ago.
The tunnel has been established successfully.
If that line is missing from the output, the connection has not been established correctly!

#### NSE2 Nodes to external App Connectivity
The external application in this example listens on port 80. Test it from both NSE2 nodes:

```sh
docker compose exec n1 curl --fail http://172.30.0.2
docker compose exec n2 curl --fail http://172.31.0.2
```

Both requests should return:

```text
Hello from external WireGuard service!
```

Within the Compose networks, Docker DNS can resolve the WireGuard server by its service name.
The application can therefore also be reached through `n3_wg`:

```sh
docker compose exec n1 curl --fail http://n3_wg
docker compose exec n2 curl --fail http://n3_wg
```

#### External App to NSE2 Nodes Connectivity
The generated client configuration routes the NSE2 Docker networks listed in `ALLOWEDIPS` through the WireGuard tunnel.
It also uses the DNS server configured by the WireGuard container, allowing the external side to resolve and connect to `n1` and `n2` by name.

```sh
docker compose -f compose-client.yml exec wg-client ping n1
docker compose -f compose-client.yml exec wg-client ping n2
```

