python3 - current-6478f000.bin <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = path.read_bytes()
base = 0x6478f000

patterns = {
    "historical anchor": bytes.fromhex(
        "11ec0f6a017440c540c6586703220274"
    ),
    "newly observed bytes": bytes.fromhex(
        "04f0843055e51f4d04f0a430e91bc318"
    ),
}

print(f"file: {path}")
print(f"size: {len(data)} bytes")

for name, pattern in patterns.items():
    offsets = []
    start = 0

    while True:
        offset = data.find(pattern, start)
        if offset < 0:
            break
        offsets.append(offset)
        start = offset + 1

    if offsets:
        for offset in offsets:
            print(
                f"{name}: offset=0x{offset:x}, "
                f"physical=0x{base + offset:x}"
            )
    else:
        print(f"{name}: NOT PRESENT in this 4096-byte window")
PY
