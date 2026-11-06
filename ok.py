#!/usr/bin/env python3

FILENAME = "region2.bin"

with open(FILENAME, "rb") as f:
    data = f.read()

signature = bytes.fromhex(
    "ee 00 00 ee "
    "ee 00 00 ee"
)

offset = 0
hits = 0

while True:
    offset = data.find(signature, offset)

    if offset == -1:
        break

    hits += 1
    print("Hit #%d: offset 0x%X (%d)" % (hits, offset, offset))

    offset += 1

if hits == 0:
    print("No matches found.")
else:
    print("\nTotal hits:", hits)
