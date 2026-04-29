#!/bin/sh

CONTACTS=mc.contacts.ccp

if [ -n "$1" ]; then
  CONTACTS="$1"
fi

nse2_contacts -m -s mc.compose.yml $CONTACTS