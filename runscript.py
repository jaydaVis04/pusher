python3 - <<'PY'
off1 = open("r2_off1.bin", "rb").read()
on1  = open("r2_on1.bin",  "rb").read()
off2 = open("r2_off2.bin", "rb").read()
on2  = open("r2_on2.bin",  "rb").read()

n = min(len(off1), len(on1), len(off2), len(on2))

hits = []
interesting = []

for i in range(n):
    off_a = off1[i]
    on_a  = on1[i]
    off_b = off2[i]
    on_b  = on2[i]

    # Must reproduce across both OFF/ON cycles.
    if off_a == off_b and on_a == on_b and off_a != on_a:
        xor = off_a ^ on_a

        hits.append((i, off_a, on_a, xor))

        reasons = []

        # Ideal boolean-looking value.
        if off_a == 0x00 and on_a == 0x01:
            reasons.append("PERFECT 0->1 BOOLEAN")

        elif off_a == 0x01 and on_a == 0x00:
            reasons.append("PERFECT 1->0 BOOLEAN")

        # Only one bit changed.
        if xor != 0 and (xor & (xor - 1)) == 0:
            bit = xor.bit_length() - 1
            reasons.append(f"SINGLE BIT CHANGE (bit {bit})")

        if reasons:
            interesting.append(
                (i, off_a, on_a, xor, reasons)
            )


print(f"repeatable candidates: {len(hits)}")
print()

for i, off, on, xor in hits:
    print(
        f"offset=0x{i:x} "
        f"OFF=0x{off:02x} "
        f"ON=0x{on:02x} "
        f"xor=0x{xor:02x}"
    )


print()
print("=" * 72)
print("INTERESTING CANDIDATES")
print("=" * 72)
print()

if not interesting:
    print("No obvious boolean/single-bit candidates found.")
else:
    for i, off, on, xor, reasons in interesting:
        print(
            f"offset=0x{i:x} "
            f"OFF=0x{off:02x} "
            f"ON=0x{on:02x} "
            f"xor=0x{xor:02x}"
        )

        for reason in reasons:
            print(f"    >>> {reason}")

        print()

print("=" * 72)
print(f"Total repeatable changes: {len(hits)}")
print(f"Interesting candidates:   {len(interesting)}")
print("=" * 72)
PY
