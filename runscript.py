python3 - <<'PY'
off1 = open("r3_off1.bin", "rb").read()
on1  = open("r3_on1.bin",  "rb").read()
off2 = open("r3_off2.bin", "rb").read()
on2  = open("r3_on2.bin",  "rb").read()

n = min(len(off1), len(on1), len(off2), len(on2))

for i in range(n):
    a, b, c, d = off1[i], on1[i], off2[i], on2[i]

    if a == c and b == d and a != b:
        print(
            f"offset=0x{i:x} "
            f"OFF=0x{a:02x} "
            f"ON=0x{b:02x} "
            f"xor=0x{a ^ b:02x}"
        )
PY
