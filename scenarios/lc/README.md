Scenario: Lunar Communication
=============================

## Scenario Definition
The Lunar Communication scenario has two service providers with similar assets. Each service provider has 1 control centre, 1 relay control centre, 1 GS, and 1 Relay and 1 Lunar asset. In addition the lunar gateway is orbiting the moon, able to communicate with all ground stations and relays as well as lunar assets. There are three "end users" in the scenario, a rover and base on the lunar surface as well as a user in the orbiting gateway. All of them have their own control centers on earth.


## Topology
:::mermaid
flowchart LR
    style Earth rx:50,ry:50
    style Moon rx:50,ry:50

    rcc1(fa:fa-computer Relay Control Centre 1<br>ipn:100.0)
    gs1(fa:fa-satellite-dish GS 1<br>ipn:110.0)
    b1cc(Base 1<br>Control Centre<br>ipn:10.0)
    r1cc(Rover 1<br>Control Centre<br>ipn:20.0)

    r1(fa:fa-satellite Relay 1<br>ipn:120.0)
    base1(fa:fa-tower-cell Base 1<br>ipn:11.0)
    rover1(fa:fa-robot Rover 1<br>ipn:21.0)
    
    rcc2(fa:fa-computer Relay Control Centre 2<br>ipn:200.0)
    gs2(fa:fa-satellite-dish GS 2<br>ipn:210.0)
    u1cc(User 1<br>Control Centre<br>ipn:30.0)
    r2(fa:fa-satellite Relay 2<br>ipn:221.0)
    user1(fa:fa-person User 1<br>ipn:31.0)
    gw(fa:fa-satellite Lunar Gateway<br>ipn:220.0)

    subgraph Earth
        b1cc <--> rcc1
        b1cc <--> rcc2
        r1cc <--> rcc1
        r1cc <--> rcc2

      subgraph Service Provider 1
        rcc1 <--> gs1
      end

        rcc1 <--> gs2
        u1cc <--> rcc2
        u1cc <--> rcc1

      subgraph Service Provider 2
        rcc2 <--> gs2
        rcc2 <--> gs1
      end

      rcc1 <--> rcc2
    end

    gs1 <-..-> r1
    gs1 <-.-> gw
    gs1 <-...-> base1

    gs2 <-..-> r2
    gs2 <-.-> gw
    gs2 <-...-> base1

    gw <-.-> r1
    gw <-.-> r2


    r1 <-.-> base1
    r2 <-.-> base1
    gw <-.-> base1

    rover1 <-.-> gw
    rover1 <-.-> r1
    rover1 <-.-> r2

    subgraph Lunar Gateway
        gw <--> user1
    end

    subgraph Moon
      base1      
      rover1
    end
:::

## Datarates


|  from\to     | User Control Centre | Relay Control Centre  | Ground Station | Gateway | Relay | Lunar Asset |
| -            | -              | -                     | -              | -       | -     | -           |
| __User Control Centre__ | /   | 100                   | 100            | 0       | 0     | 0           |
| __Relay Control Centre__ | 100| /                     | 100            | 0       | 0     | 0           |
| __Ground Station__ | 100      | 100                   | /              | 30      | 30    | 30          |
| __Gateway__ | 0               | 0                     | 100            | /       | ?     | 100         |           
| __Relay__ | 0                 | 0                     | 100            | 100     | 100   | 100         | 
| __Lunar Asset__ | 0           | 0                     | 100            | 15      | 15    | /

## Docker: Running the Scenario

1. start the docker containers and setup the network: `./start_topo.sh`
2. if you want fluctuating connectivity and bandwidth limitations: `./start_net.sh`
3. *OPTIONALLY: start the network visualization: `./start_viz.sh`*
4. *OPTIONALLY: start the docker test bed manager: `nse2_mgr lc.compose.yml lc.contacts.ccp`*

You can get an interactive shell on any of the nodes through docker: `docker exec -it <node> bash` or `nse2_sh <node>`
