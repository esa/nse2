# Generated: 2026-09-02
# Command: random-contacts.py scenarios/eo/contacts.ccp scenarios/eo/contacts_testing.ccp --length 120 --min-contact 30 --max-contact 30 --seed 0
s loop 1

a fixed  gs1 mcc 100mbit 0 150 0 =
a fixed  gs1 pcc 100mbit 0 150 0 =
a fixed  gs2 mcc 100mbit 0 150 0 =
a fixed  gs2 pcc 1gbit 0 10 0 =
a fixed  mcc pcc 100mbit 0 150 0 =

a contact +5 +35 sat gs1 8mbit 0 57 0
a contact +49 +79 gs1 sat 64kbit 0 57 0
a contact +65 +95 sat gs2 10gbit 0 57 0
