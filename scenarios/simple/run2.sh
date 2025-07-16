#!/bin/bash

COMPOSE_FILE=lc.compose.yml
CONTACTS_FILE=lc.testing.contacts.ccp
STARTUP_TIMEOUT=30
SESSION_NAME=lc
NUM_NODES=$(cat $COMPOSE_FILE | grep hostname | wc -l)

# function to wait for nodes to start
wait_for_nodes() {
    CNT=0
    echo -n "Waiting for nodes to start..."
    while [ $CNT -lt $STARTUP_TIMEOUT ]; do
        # wait for the nodes to start
        # while true; do
        # check if the nodes are up
        NUM_STARTED=$(docker compose -f $COMPOSE_FILE logs | grep -c "$1")
        if [ "$NUM_STARTED" -eq "$NUM_NODES" ]; then
            echo
            echo "All nodes started successfully."
            break
        fi
        echo -n .
        # echo "Nodes not yet started, waiting..."
        sleep 1
        CNT=$((CNT + 1))
    done
    if [ $CNT -eq $STARTUP_TIMEOUT ]; then
        echo
        echo "Timeout waiting for nodes to start."
        echo "Please check the logs for more information."
        echo
        echo "Press any key to attach to logs..."
        read -s -n1 READ
        
        tmux attach -t $SESSION_NAME
        exit 1
    fi
}

# start scenario with nse2_topo in tmux in the background
tmux new-session -d -s $SESSION_NAME -n "Topo & Contacts" "nse2_topo $COMPOSE_FILE"
wait_for_nodes "Bundle node started successfully"

# split the window horizontally
tmux split-window -t $SESSION_NAME:0 -h

# start the scenario with the contacts plan
tmux send-keys -t $SESSION_NAME "nse2_contacts -l 1 -s -m $COMPOSE_FILE $CONTACTS_FILE" C-m

# split the window vertically
tmux split-window -t $SESSION_NAME:0 -v

# start the actions
tmux send-keys -t $SESSION_NAME "nse2_actions ./lc.actions" C-m

# activate mouse mode
tmux set -g mouse on


# create new window for web uis
tmux new-window -t $SESSION_NAME:1 -n 'Web UIs'
tmux send-keys -t $SESSION_NAME "./start_uis.sh" C-m


# create new window for node terminals
tmux new-window -t $SESSION_NAME:2 -n 'Node Terminals'

# split the window horizontally
tmux send-keys -t $SESSION_NAME "nse2_sh rover1" C-m
tmux split-window -t $SESSION_NAME:2 -h
tmux send-keys -t $SESSION_NAME "nse2_sh u1cc" C-m
tmux split-window -t $SESSION_NAME:2 -h
tmux send-keys -t $SESSION_NAME "nse2_sh r1cc" C-m

# create new window for simulation control
tmux new-window -t $SESSION_NAME:3 -n 'Control'
tmux send-keys -t $SESSION_NAME "tmux kill-session -t $SESSION_NAME"


# select the first window
tmux select-window -t $SESSION_NAME:0

# attach to the tmux session
tmux attach -t $SESSION_NAME