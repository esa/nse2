#!/bin/sh

CONTACTS=eo.testing.contacts.ccp

if [ -n "$1" ]; then
  CONTACTS="$1"
fi

nse2_contacts -m eo.compose.yml $CONTACTS