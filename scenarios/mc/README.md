Scenario: Mars Communication
============================

## Scenario Definition
The mars communication scenario keeps a similar infrastructure to the [lunar scenario](../lc), however relays cannot communicate and links have much larger delays.


## Topology
:::mermaid
flowchart LR
    style Earth rx:50,ry:50
    style Mars rx:50,ry:50

    payload1(fa:fa-computer Rover 1<br>Control Centre<br>ipn:10.0)
    rover1(fa:fa-robot Rover 1<br>ipn:15.0)

    rcc1(fa:fa-server Relay Control Centre 1<br>ipn:100.0)
    gs1(fa:fa-satellite-dish GS 1<br>ipn:110.0)
    r1(fa:fa-satellite Relay 1<br>ipn:120.0)
    
    payload2(fa:fa-computer Rover 2<br>Control Centre<br>ipn:20.0)
    rover2(fa:fa-robot Rover 2<br>ipn:25.0)
    
    rcc2(fa:fa-server Relay Control Centre 2<br>ipn:200.0)
    gs2(fa:fa-satellite-dish GS 2<br>ipn:210.0)
    r2(fa:fa-satellite Relay 2<br>ipn:220.0)
    r3(fa:fa-satellite Relay 3<br>ipn:221.0)

    subgraph Earth
      payload1 --- rcc1
      payload1 --- rcc2

      subgraph Service provider 1
        rcc1 --- gs1
      end
      rcc1 --- gs2

      payload2 --- rcc2
      payload2 --- rcc1

      subgraph Service provider 2
        rcc2 --- gs2
        rcc2 --- gs1
      end
      
      rcc1 --- rcc2
    end

    gs1 -.- r1
    gs2 -.- r2
    gs2 -.- r3


    r1 -.- rover1
    r1 -.- rover2

    r2 -.- rover1
    r2 -.- rover2
    
    r3 -.- rover1
    r3 -.- rover2
    
    subgraph Mars
      rover1
      rover2
    end
:::

## Datarates


|  from\to     | User Control Centre | Relay Control Centre  | Ground Station | Relay | Lunar Asset |
| -            | -              | -                     | -              | -     | -           |
| __User Control Centre__ | /   | 100                   | 100            | 0     | 0           |
| __Relay Control Centre__ | 100| /                     | 100            | 0     | 0           |
| __Ground Station__ | 100      | 100                   | /              | 30    | 30          |      
| __Relay__ | 0                 | 0                     | 100            | 0   | 100         | 
| __Lunar Asset__ | 0           | 0                     | 100            | 15    | /


## Docker: Running the Scenario

1. start the docker containers and setup the network: `./start_topo.sh`
2. if you want fluctuating connectivity and bandwidth limitations: `./start_net.sh`
3. start the automatic actions on the nodes: `./start_actions.sh`
4. *OPTIONALLY: start the network visualization: `./start_viz.sh`*
5. *OPTIONALLY: start the docker test bed manager: `dtbm mc.compose.yml mc.contacts.ccp`*
