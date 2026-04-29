#!/bin/bash

# This script applies link properties to the ccp

# require a link props file and ccp file as parameters
if [ $# -lt 2 ]; then
    echo "Usage: $0 <link-props-file> <ccp-file> [-s]"
    echo "  link-props-file: file containing link properties"	
    echo "  ccp-file: file containing ccp"
    echo "  -s: optional flag to apply link properties symmetrically in both directions"
    exit 1
fi

LINK_PROPS_FILE=$1
CCP_FILE=$2
SYMMETRIC=false
if [ $# -eq 3 ] && [ $3 == "-s" ]; then
    SYMMETRIC=true
fi

# parse link properties file and skip lines beginning with #
while read line || [ -n "$line" ]; do
    if [ "${line:0:1}" != "#" ]; then
        # extract link properties
        NODE1=$(echo $line | awk '{print $1}')
        NODE2=$(echo $line | awk '{print $2}')
        BW=$(echo $line | awk '{print $3}')

        # apply link properties to ccp
        # sed -i "s/^\($LINK_ID.*$PROP_NAME.*\)=.*$/\1=$PROP_VALUE/" $CCP_FILE
        echo "Applying link properties to ccp: $NODE1 $NODE2 $BW"
        sed -i -E "s/($NODE1) ($NODE2) ([a-zA-Z0-9]+) ([a-zA-Z0-9\.]+) ([a-zA-Z0-9\.]+)/\1 \2 $BW \4 \5/" $CCP_FILE
        if [ $SYMMETRIC == true ]; then
            echo "Applying link properties to ccp: $NODE2 $NODE1 $BW"
            sed -i -E "s/($NODE2) ($NODE1) ([a-zA-Z0-9]+) ([a-zA-Z0-9\.]+) ([a-zA-Z0-9\.]+)/\1 \2 $BW \4 \5/" $CCP_FILE
        fi
    fi
done < $LINK_PROPS_FILE