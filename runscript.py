python3 - <<'PY'
from pathlib import Path

patterns = {
    "Dispatch_live+1": bytes.fromhex("75 4e 9f 64"),
    "Schedule_live+1": bytes.fromhex("49 5b 9f 64"),
    "Nested_live+1":   bytes.fromhex("25 59 fc 68"),
}

for fn in ["var2.bin", "var3.bin", "var4.bin", "var5.bin"]:
    p = Path(fn)
    if not p.exists():
        continue

    data = p.read_bytes()
    print(f"\n=== {fn} ===")

    for name, sig in patterns.items():
        hits = []
        pos = 0

        while True:
            pos = data.find(sig, pos)
            if pos < 0:
                break

            hits.append(pos)
            pos += 1

        print(name, [hex(x) for x in hits[:20]])
PY
