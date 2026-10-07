python3 - <<'PY'
data = open("var3.bin", "rb").read()

patterns = {
    "Dispatch_LISR": bytes.fromhex("75 4e 9f 90"),
    "Schedule": bytes.fromhex("49 5b 9f 90"),
    "Nested_LISR": bytes.fromhex("25 59 fc 94"),
}

for name, sig in patterns.items():
    print(name)
    pos = 0
    while True:
        off = data.find(sig, pos)
        if off < 0:
            break
        print(f"  offset 0x{off:x}")
        pos = off + 1
PY
