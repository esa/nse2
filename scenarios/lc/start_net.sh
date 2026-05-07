#!/bin/sh

CONTACTS=lc.contacts.ccp

if [ -n "$1" ]; then
  CONTACTS="$1"
fi

nse2_contacts -m lc.compose.yml $CONTACTS
