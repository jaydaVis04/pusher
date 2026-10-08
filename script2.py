python3 - <<'PY'
files = [
    ("OFF1", "r2_off1.bin"),
    ("ON1",  "r2_on1.bin"),
    ("OFF2", "r2_off2.bin"),
    ("ON2",  "r2_on2.bin"),
    ("OFF3", "r2_off3.bin"),
    ("ON3",  "r2_on3.bin"),
]

offsets = [0xfc04, 0xa40b4, 0xa40b8]

data = [(name, open(path, "rb").read()) for name, path in files]

for off in offsets:
    print(f"\n===== OFFSET 0x{off:x} =====")
    for name, buf in data:
        print(f"{name:4s}: 0x{buf[off]:02x}")
PY
