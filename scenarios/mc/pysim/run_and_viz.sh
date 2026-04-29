#!/bin/bash

set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <event-log-file> <mp4-out>"
    echo "  event-log-file: file containing event log"
    echo "  mp4-out: output mp4 file"
    exit 1
fi
export LOG_FILE=$1
# check if SKIP_SIM is set
if [ -z ${SKIP_SIM+x} ]; then
  time PYTHONPATH=~/src/gh0st42/pons:$PYTHONPATH pypy3 sim_mc.py
else
  echo "SKIP_SIM is set, skipping simulation"
fi

MP4_OUT=$2

TMP_FILE=$(mktemp -q /tmp/$MP4_OUT.XXXXXX.mp4)
if [ $? -ne 0 ]; then
    echo "$0: Can't create temp file, bye.."
    exit 1
fi
trap 'rm -f -- "$TMP_FILE"' EXIT

PYTHONPATH=~/src/gh0st42/pons:$PYTHONPATH ~/src/gh0st42/pons/tools/ponsanim/ponsanim.py -o $TMP_FILE -e $LOG_FILE -s 600 -d 50 -H
echo "Converting and optimizing $TMP_FILE to $MP4_OUT"
ffmpeg -i $TMP_FILE -c:v libx264 -pix_fmt yuv420p -y $MP4_OUT

# clean up logic
rm -f -- "$TMP_FILE"
trap - EXIT
exit