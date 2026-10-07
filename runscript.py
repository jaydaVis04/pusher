python3 - <<'PY'
data = open("var2.bin", "rb").read()

patterns = {
    "Dispatch+1": bytes.fromhex("75 4e 9f 90"),
    "Schedule+1": bytes.fromhex("49 5b 9f 90"),
    "Nested+1":   bytes.fromhex("25 59 fc 94"),

    # Also test the live/code-mapped forms.
    "Dispatch_live+1": bytes.fromhex("75 4e 9f 64"),
    "Schedule_live+1": bytes.fromhex("49 5b 9f 64"),
}

for name, sig in patterns.items():
    hits = []
    p = 0

    while True:
        p = data.find(sig, p)
        if p < 0:
            break
        hits.append(p)
        p += 1

    print(name, [hex(x) for x in hits[:20]])
PY
