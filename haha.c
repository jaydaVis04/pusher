python3 - <<'PY'
data = open("var3.bin", "rb").read()

patterns = {
    "Dispatch_LISR+1": bytes.fromhex("75 4e 9f 90"),
    "Dispatch_LISR":   bytes.fromhex("74 4e 9f 90"),
    "Schedule+1":      bytes.fromhex("49 5b 9f 90"),
    "Schedule":        bytes.fromhex("48 5b 9f 90"),
    "Nested_LISR+1":   bytes.fromhex("25 59 fc 94"),
    "Nested_LISR":     bytes.fromhex("24 59 fc 94"),
}

for name, sig in patterns.items():
    hits = []
    pos = 0

    while True:
        off = data.find(sig, pos)
        if off < 0:
            break

        hits.append(off)
        pos = off + 1

    print(name, [hex(x) for x in hits[:20]])
PY
