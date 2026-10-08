python3 - <<'PY'
a = open("screen_off.bin", "rb").read()
b = open("screen_on.bin", "rb").read()

BASE = 0x63c07000

for i, (x, y) in enumerate(zip(a, b)):
    if x != y:
        print(
            f"offset 0x{i:03x}  "
            f"phys 0x{BASE+i:08x}  "
            f"OFF=0x{x:02x} ON=0x{y:02x}  "
            f"xor=0x{x^y:02x}"
        )
PY
