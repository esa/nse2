#!/bin/sh

CONTACTS=actual_contacts_speedup-100.ccp

if [ -n "$1" ]; then
  CONTACTS="$1"
fi

nse2_contacts -m compose.yml $CONTACTS
