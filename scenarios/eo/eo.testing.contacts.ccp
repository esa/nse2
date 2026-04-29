s loop 1

# each entry starts with "a contact" or "a fixed"	
# a contact <begin timestamp in seconds> <end timestamp in seconds> <node id 1 OR name> <node id 2 OR name OR dev:<interfacename> > <bandwidth> [loss%] [delay] [jitter]

# define a symmetric connection between mcc and gs1
a fixed mcc dev:gs1_mcc 10mbit 0.0 300 0
a fixed gs1 dev:gs1_mcc 10mbit 0.0 300 0

# define a symmetric connection between mcc and gs2
a fixed mcc dev:gs2_mcc 10mbit 0.0 300 0
a fixed gs2 dev:gs2_mcc 10mbit 0.0 300 0

# define a symmetric connection between pcc and gs1
a fixed pcc dev:gs1_pcc 10mbit 0.0 300 0
a fixed gs1 dev:gs1_pcc 10mbit 0.0 300 0

# define a symmetric connection between pcc and gs2
a fixed pcc dev:gs2_pcc 10mbit 0.0 300 0
a fixed gs2 dev:gs2_pcc 10mbit 0.0 300 0

# define a symmetric connection between eosat and gs1
# one entry for each direction, defining the outgoing bandwidth 
a contact +30 +60 gs1 dev:eosat_gs1_lo 100kbit 0.0 0 0
a contact +30 +60 eosat dev:eosat_gs1_lo 1mbit 0.0 0 0

a contact +30 +60 gs1 dev:eosat_gs1_hi 100kbit 0.0 0 0
a contact +30 +60 eosat dev:eosat_gs1_hi 1000mbit 0.0 0 0

# define an asymmetric link between gs2 and eosat
a contact +90 +120 gs2 dev:eosat_gs2_lo 100kbit 0.0 00 0
a contact +90 +120 eosat dev:eosat_gs2_lo 1mbit 0.0 0 0

a contact +90 +120 gs2 dev:eosat_gs2_hi 100kbit 0.0 0 0
a contact +90 +120 eosat dev:eosat_gs2_hi 1000mbit 0.0 0 0