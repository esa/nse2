# contact player

This tool replays a core contact plan for docker compose scenarios.
It can optionally write a node map with the `-m` parameter.

Additionally, it can also be controlled via UDP messages to port *9966*.
The following commands are currently supported:
- Pause contact plan playback: `echo pause | ncat -u localhost 9966`
- Resume contact plan playback: `echo resume | ncat -u localhost 9966`
- Skip to next event: `echo next | ncat -u localhost 9966`