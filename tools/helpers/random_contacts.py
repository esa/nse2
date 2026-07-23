#!/usr/bin/env python3

import argparse
import csv
import random

START_TIME_DEFAULT = 0
END_TIME_DEFAULT = 60
MIN_CON_LENGTH_DEFAULT = 5
MAX_CON_LENGTH_DEFAULT = 15

parser = argparse.ArgumentParser()
parser.add_argument("contacts", help="The contacts file to create short contacts from.")
parser.add_argument("output", help="The output file.")
parser.add_argument("-l", "--length",
                    help="The length of the contact plan in seconds (default=60)",
                    default=END_TIME_DEFAULT,
                    type=int)
parser.add_argument("-min",
                    help="The minimum contact length in seconds (default=5)",
                    default=MIN_CON_LENGTH_DEFAULT,
                    type=int)
parser.add_argument("-max",
                    help="The maximum contact length in seconds (default=15)",
                    default=MAX_CON_LENGTH_DEFAULT,
                    type=int)

args = parser.parse_args()
contacts_file = args.contacts
output_file = args.output
end_time = args.length
min_con_length = args.min
max_con_length = args.max

unique_pairs = set()
fixed_contacts = []

with open(contacts_file) as file:
    reader = csv.reader(file, delimiter=' ')
    for row in reader:
        if len(row) < 2:
            continue

        if row[1] == "contact":
            node_a = row[4]
            node_b = row[5]
            unique_pairs.add((node_a, node_b))
            unique_pairs.add((node_b, node_a))
        elif row[1] == "fixed":
            fixed_contacts.append(row)

contacts = []
for pair in unique_pairs:
    new_start = random.randrange(START_TIME_DEFAULT, end_time - max_con_length)
    new_end = new_start + random.randrange(min_con_length, max_con_length)

    contacts.append(["a", "contact", f"+{new_start}", f"+{new_end}", f"{pair[0]}", f"{pair[1]}", "100mbit", 0.0, 0, 0])

contacts.sort(key=lambda l: int(l[2]))

with open(output_file, 'w') as file:
    file.write("s loop 1\n")

    writer = csv.writer(file, delimiter=' ')
    writer.writerow([])

    for contact in fixed_contacts:
        writer.writerow(contact)

    writer.writerow([])
    for contact in contacts:
        writer.writerow(contact)
