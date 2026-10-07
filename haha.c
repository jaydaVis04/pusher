#!/usr/bin/env python3

import re
import sys
from pathlib import Path


# ============================================================
# EDIT ONLY THIS SECTION
# ============================================================

NAMES = {
    "THISGUY": "YOUR_THISGUY_NAME",

    "struct x": "struct YOUR_X_NAME",
    "struct y": "struct YOUR_Y_NAME",

    "var1": "YOUR_VAR1",
    "var2": "YOUR_VAR2",
    "var3": "YOUR_VAR3",
    "var4": "YOUR_VAR4",
    "var5": "YOUR_VAR5",

    "guy": "YOUR_GUY_NAME",

    "getthisguy_fn_t": "YOUR_GET_FN_TYPE",
    "getthisguy_fn": "YOUR_GET_FN",

    "myaddr": "YOUR_ADDR_NAME",

    "print_x": "YOUR_PRINT_X",
    "print_y": "YOUR_PRINT_Y",
}


# ============================================================
# DON'T NEED TO EDIT BELOW HERE
# ============================================================

def parse_args():
    input_file = None
    output_file = None

    for arg in sys.argv[1:]:
        if arg.startswith("if="):
            input_file = arg[3:]
        elif arg.startswith("of="):
            output_file = arg[3:]

    if not input_file or not output_file:
        print(
            f"Usage: {sys.argv[0]} "
            "if=<input_file> of=<output_file>"
        )
        sys.exit(1)

    return Path(input_file), Path(output_file)


def replace_identifier(text, old, new):
    # Handle things like "struct x" separately.
    if " " in old:
        return re.sub(
            r"(?<![A-Za-z0-9_])" +
            re.escape(old) +
            r"(?![A-Za-z0-9_])",
            new,
            text,
        )

    # Replace complete C identifiers only.
    return re.sub(
        r"\b" + re.escape(old) + r"\b",
        new,
        text,
    )


def main():
    input_file, output_file = parse_args()

    if not input_file.exists():
        print(f"ERROR: input file does not exist: {input_file}")
        sys.exit(1)

    text = input_file.read_text()

    # Longest names first avoids partial/overlapping replacements.
    replacements = sorted(
        NAMES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for old, new in replacements:
        text = replace_identifier(text, old, new)

    output_file.write_text(text)

    print(f"[+] Input:  {input_file}")
    print(f"[+] Output: {output_file}")
    print("[+] Replacements:")

    for old, new in replacements:
        print(f"    {old} -> {new}")


if __name__ == "__main__":
    main()
