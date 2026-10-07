python3 - <<'PY'
data = open("var3.bin", "rb").read()

patterns = {
    "Dispatch": [
        bytes.fromhex("75 4e 9f 90"),  # +1
        bytes.fromhex("74 4e 9f 90"),  # raw function
    ],
    "Schedule": [
        bytes.fromhex("49 5b 9f 90"),  # +1
        bytes.fromhex("48 5b 9f 90"),  # raw function
    ],
}

for name, variants in patterns.items():
    print(name)
    for sig in variants:
        hits = []
        pos = 0
        while True:
            off = data.find(sig, pos)
            if off < 0:
                break
            hits.append(off)
            pos = off + 1
        print(sig.hex(" "), [hex(x) for x in hits[:20]])
PY
