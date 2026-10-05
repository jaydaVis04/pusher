#!/usr/bin/env python3

import subprocess
import sys

# Known symbol and its address in your ELF/Ghidra
KNOWN_SYMBOL = "getthisguy"
KNOWN_ELF_ADDR = 0xffffff8008795ed4


def get_live_symbol(name):
    cmd = [
        "adb", "shell", "su", "-c",
        f"grep -w ' {name}$' /proc/kallsyms"
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Could not find {name} in /proc/kallsyms")

    line = result.stdout.strip().splitlines()[0]

    # Example:
    # ffffff9edc595ed4 T getthisguy
    return int(line.split()[0], 16)


if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <ghidra_address>")
    sys.exit(1)

ghidra_addr = int(sys.argv[1], 16)

live_known = get_live_symbol(KNOWN_SYMBOL)

slide = live_known - KNOWN_ELF_ADDR

live_addr = ghidra_addr + slide

print(f"Known symbol : {KNOWN_SYMBOL}")
print(f"ELF address  : 0x{KNOWN_ELF_ADDR:016x}")
print(f"Live address : 0x{live_known:016x}")
print(f"KASLR slide  : 0x{slide:x}")
print()
print(f"Ghidra       : 0x{ghidra_addr:016x}")
print(f"Live         : 0x{live_addr:016x}")
