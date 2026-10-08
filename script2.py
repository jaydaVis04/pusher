python3 - <<'PY'
a = open("r3_off1.bin", "rb").read()
b = open("r3_on1.bin", "rb").read()

changed = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]

print("changed bytes:", len(changed))

for i, x, y in changed[:50]:
    print(
        f"offset=0x{i:x} "
        f"OFF=0x{x:02x} "
        f"ON=0x{y:02x} "
        f"xor=0x{x^y:02x}"
    )
PY
