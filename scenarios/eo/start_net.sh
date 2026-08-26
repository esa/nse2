#!/bin/sh

CONTACTS=contacts.ccp

if [ -n "$1" ]; then
  CONTACTS="$1"
fi

nse2_contacts -m compose.yml $CONTACTS
