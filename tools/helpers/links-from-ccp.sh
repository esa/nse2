#!/bin/sh

if [ -z "$1" ]; then
  echo "Usage: $0 <contacts-file>"
  echo "  contacts-file: file containing contacts"
  exit 1
fi

CONTACTS=$1

TMPFILE=$(mktemp)
trap "rm -f $TMPFILE" EXIT


TMPFILE2=$(mktemp)
trap "rm -f $TMPFILE2" EXIT

cat $CONTACTS | grep "a contact" | cut -d ' ' -f 5,6 | sort -u > $TMPFILE
cat $CONTACTS | grep "a fixed" | cut -d ' ' -f 3,4 | sort -u >> $TMPFILE
# cat $TMPFILE | sort -u
while read line || [ -n "$line" ]; do        
        # print nodes in sort order
        line=$(echo $line | tr ' ' '\n' | sort | tr '\n' ' ')
        echo "$line" >> $TMPFILE2
done < $TMPFILE

cat $TMPFILE2 | sort -u
