#!/bin/sh

if [ -z "$1" ]; then
  echo "Usage: $0 <compose-file>"
  echo "  contacts-file: compose file containing networks"
  exit 1
fi

COMPOSE=$1

TMPFILE=$(mktemp)
trap "rm -f $TMPFILE" EXIT


TMPFILE2=$(mktemp)
trap "rm -f $TMPFILE2" EXIT

cat $COMPOSE | grep -B1 "driver: bridge" | grep -v "driver:" | grep ":" | awk '{print $1}' | tr -d ':' | tr '_' ' ' | sort -u > $TMPFILE

while read line || [ -n "$line" ]; do        
        # print nodes in sort order
        line=$(echo $line | tr ' ' '\n' | sort | tr '\n' ' ')
        echo "$line" >> $TMPFILE2
done < $TMPFILE
cat $TMPFILE2 | sort -u

