python3 - <<'PY'
data = open("var3.bin", "rb").read()

sig = bytes.fromhex(
    "00 f0 04 00 22 00 00 00 65 1d a0 90"
)

start = 0

while True:
    off = data.find(sig, start)

    if off < 0:
        break

    print(f"match offset: 0x{off:x}")
    start = off + 1
PY
