#!/usr/bin/env python3
"""Bounded, read-only physical-memory window access through adb and re_mem.

This is not a CSCI client and cannot halt, resume, or modify a modem. It uses
only the sequential-read contract of the small-window re_mem driver preserved
in work/memory/sessions/20261120T175802-e6f6a8d7dd16.md.

The active physical base and map size are never guessed. A single read obtains
exactly one whole declared mapping via adb/stdin-safe dd and slices it locally.
Thus the cost is the map size, not the requested read size.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence

# Only the small-window interface is supported; broad driver mappings require
# a separately validated driver read contract.
MAX_WINDOW = 0x4000
MAX_CHUNK = 0x400
OUTPUT_SUFFIXES = {".bin", ".json"}
HEX_BYTES = re.compile(r"(?:[0-9A-Fa-f]{2})+")


class ClientError(RuntimeError):
    """A failed or inconsistent read, not a valid observation."""


def number(text: str) -> int:
    try:
        return int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {text!r}") from exc


def size(text: str) -> int:
    value = number(text)
    if not 1 <= value <= MAX_WINDOW:
        raise argparse.ArgumentTypeError(
            f"map size must be in 1..{MAX_WINDOW} bytes"
        )
    return value


def bounded_size(text: str) -> int:
    value = number(text)
    if not 1 <= value <= MAX_WINDOW:
        raise argparse.ArgumentTypeError(
            f"length must be in 1..{MAX_WINDOW} bytes"
        )
    return value


def chunk_size(text: str) -> int:
    value = number(text)
    if not 1 <= value <= MAX_CHUNK:
        raise argparse.ArgumentTypeError(
            f"chunk size must be in 1..{MAX_CHUNK} bytes"
        )
    return value


def output_path(text: str) -> Path:
    path = Path(text).expanduser()
    if path.suffix.lower() not in OUTPUT_SUFFIXES:
        raise argparse.ArgumentTypeError("new output must have .bin or .json suffix")
    return path


def checked_range(start: int, length: int, base: int, window_size: int) -> tuple[int, int]:
    """Return zero-based offsets, requiring a nonempty contained range."""
    if length <= 0 or start < base:
        raise ClientError("address/range begins outside the declared mapping")
    offset = start - base
    end = offset + length
    if end > window_size:
        raise ClientError(
            f"requested range ends at 0x{start + length:x}, outside declared mapping "
            f"[0x{base:x}, 0x{base + window_size:x}); change the explicit mapping "
            "arguments only if the loaded module itself uses a different mapping"
        )
    return offset, end


class WindowReader:
    """One-mapped-window-at-a-time adb reader; no device-state changes."""

    def __init__(self, base: int, window_size: int, adb: str, serial: str | None,
                 device: str, remote_command: str, timeout: float):
        self.base = base
        self.size = window_size
        self.adb = adb
        self.serial = serial
        self.device = device
        self.remote_command = remote_command
        self.timeout = timeout
        self._window: bytes | None = None

    def info(self) -> dict[str, object]:
        # Fixed command string, not a shell fragment supplied through --device.
        command = (
            f"dd if={self.device} bs={self.size} count=1 2>/dev/null"
            if self.remote_command == "dd"
            else f"cat {self.device}"
        )
        return {
            "transport": "adb exec-out; re_mem sequential whole-window dd",
            "phys_base": f"0x{self.base:x}",
            "map_size": self.size,
            "mapped_range": [f"0x{self.base:x}", f"0x{self.base + self.size:x}"],
            "adb": self.adb,
            "adb_serial": self.serial,
            "remote_device": self.device,
            "remote_read": command,
            "max_map": MAX_WINDOW,
            "adb_timeout_seconds": self.timeout,
            "writes": False,
            "driver_changes": False,
            "csci_protocol": False,
        }

    def _command(self) -> list[str]:
        command = [self.adb]
        if self.serial is not None:
            command.extend(["-s", self.serial])
        command.extend([
            "exec-out", "su", "-c",
            f"dd if={self.device} bs={self.size} count=1 2>/dev/null",
        ])
        return command

    def fetch(self) -> bytes:
        if self._window is not None:
            return self._window
        try:
            result = subprocess.run(
                self._command(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise ClientError(f"ADB executable not found: {self.adb}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ClientError(f"ADB read exceeded {self.timeout:g} seconds") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise ClientError(
                f"ADB read failed with status {result.returncode}: "
                f"{detail or 'no error text returned; no bytes were captured'}"
            )
        actual = len(result.stdout)
        if actual != self.size:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise ClientError(
                f"incomplete read: expected {self.size} bytes, received {actual}. "
                "This may indicate a wrong map size/base state, read error, or "
                f"nonconforming driver. No output was saved. {detail}"
            )
        self._window = result.stdout
        return self._window

    def read(self, address: int, length: int) -> bytes:
        start, end = checked_range(address, length, self.base, self.size)
        return self.fetch()[start:end]


def locate(args: argparse.Namespace) -> dict[str, object]:
    """Read-side candidate address resolution from the saved virtual mapping."""
    results: list[dict[str, object]] = []
    for address in args.addresses:
        item: dict[str, object] = {"virtual": f"0x{address:x}", "mapping": None}
        if args.rom_base <= address < args.rom_base + args.rom_size:
            physical = address - args.rom_base + args.rom_phys
            item["mapping"] = {
                "physical": f"0x{physical:x}",
                "basis": "physical = virtual - 0x90000000 + 0x64000000",
            }
        elif args.viva_base <= address < args.viva_base + args.viva_size:
            physical = address - args.viva_base + args.viva_phys
            item["mapping"] = {
                "physical": f"0x{physical:x}",
                "basis": "VIVA virtual 0x62c00000 -> physical 0x657c0000",
            }
        results.append(item)
    return {"addresses": results, "device_read": False}


def hexdump(data: bytes, base: int, width: int = 16) -> str:
    lines = []
    for index in range(0, len(data), width):
        block = data[index:index + width]
        hexadecimal = " ".join(f"{byte:02x}" for byte in block)
        printable = "".join(chr(b) if 32 <= b < 127 else "." for b in block)
        lines.append(f"{base + index:08x}  {hexadecimal:<47}  |{printable}|")
    return "\n".join(lines)


def exclusive_write(path: Path, data: bytes) -> None:
    """Create one user-selected evidence file, never replace existing evidence."""
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError as exc:
        raise ClientError(f"refusing to overwrite existing file: {path}") from exc
    except OSError as exc:
        raise ClientError(f"could not create {path}: {exc}") from exc


def parse_hex_bytes(text: str) -> bytes:
    value = text.removeprefix("0x").replace(" ", "").replace(":", "").replace("-", "")
    if not value or not HEX_BYTES.fullmatch(value):
        raise argparse.ArgumentTypeError("expected bytes must be contiguous hex pairs")
    return bytes.fromhex(value)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    result.add_argument("--phys-base", type=number, required=True,
                        help="active loaded mapping base; never inferred")
    result.add_argument("--map-size", type=size, required=True,
                        help=f"active loaded mapping size, <= {MAX_WINDOW}")
    result.add_argument("--serial",
                        help="explicitly selected approved ADB device serial")
    result.add_argument("--adb", default="adb", help="ADB executable (default: adb)")
    result.add_argument("--remote-device", default="/dev/re_mem",
                        help="read-only remote character device")
    result.add_argument("--timeout", type=float, default=20.0,
                        help="ADB subprocess timeout in seconds (default: 20)")
    commands = result.add_subparsers(dest="command", required=True)

    commands.add_parser("info", help="show fixed read transport; do not access ADB")

    locate_parser = commands.add_parser(
        "locate", help="resolve candidate virtual addresses; no device access"
    )
    locate_parser.add_argument("addresses", nargs="+", type=number)
    locate_parser.add_argument("--rom-base", type=number, default=0x90000000)
    locate_parser.add_argument("--rom-phys", type=number, default=0x64000000)
    locate_parser.add_argument("--rom-size", type=number, default=0x1000000)
    locate_parser.add_argument("--viva-base", type=number, default=0x62C00000)
    locate_parser.add_argument("--viva-phys", type=number, default=0x657C0000)
    locate_parser.add_argument("--viva-size", type=number, default=0x28000)

    for name, help_text in (("dump", "bounded memory read"),
                            ("read-mem", "bounded memory read with optional output")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("address", type=number)
        command.add_argument("length_arg", nargs="?", type=bounded_size, default=16,
                             metavar="length")
        command.add_argument("length_keyword", nargs="?", type=bounded_size,
                             metavar=argparse.SUPPRESS)
        command.add_argument("--length", dest="length", type=bounded_size)
        command.add_argument("--out", type=output_path, help="new raw .bin evidence file")

    verify_parser = commands.add_parser(
        "verify", help="verify a designated anchor; no modification"
    )
    verify_parser.add_argument("address", type=number)
    verify_parser.add_argument("expected", type=parse_hex_bytes)

    capture = commands.add_parser(
        "capture", help="capture a range from ONE declared mapping, never across mappings"
    )
    capture.add_argument("--start", type=number, required=True)
    capture.add_argument("--end", type=number, required=True, help="exclusive end address")
    capture.add_argument("--chunk", type=chunk_size, default=MAX_CHUNK,
                         help="local hexdump chunk size; not a device transaction")
    capture.add_argument("--output", type=output_path, default=Path("capture.bin"))
    return result


def read_length(args: argparse.Namespace) -> int:
    """Prefer named length; support historical positional forms without ambiguity."""
    if args.length is not None:
        if args.length_keyword is not None and args.length_keyword != args.length:
            raise ClientError("conflicting positional and --length values")
        if args.length_arg != 16 and args.length_arg != args.length:
            raise ClientError("conflicting positional and --length values")
        return args.length
    if args.length_keyword is not None:
        if args.length_arg != 16 and args.length_arg != args.length_keyword:
            raise ClientError("too many or conflicting positional lengths")
        return args.length_keyword
    return args.length_arg


def main(argv: Sequence[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if args.timeout <= 0:
        cli.error("--timeout must be positive")
    if args.phys_base < 0:
        cli.error("--phys-base cannot be negative")

    try:
        if args.command == "locate":
            if min(args.rom_size, args.viva_size) < 0:
                raise ClientError("registration sizes cannot be negative")
            print(json.dumps(locate(args), indent=2))
            return 0

        reader = WindowReader(
            args.phys_base, args.map_size, args.adb, args.serial,
            args.remote_device, "dd", args.timeout,
        )
        if args.command == "info":
            print(json.dumps(reader.info(), indent=2))
            return 0

        if args.command == "verify":
            observed = reader.read(args.address, len(args.expected))
            print(f"observed @0x{args.address:x}: {observed.hex()}")
            print(f"expected @0x{args.address:x}: {args.expected.hex()}")
            if observed != args.expected:
                raise ClientError("anchor mismatch; do not use this mapping as verified")
            print("MATCH: the selected anchor was observed; mapping remains read-only")
            return 0

        if args.command in ("dump", "read-mem"):
            length = read_length(args)
            data = reader.read(args.address, length)
            print(hexdump(data, args.address))
            print(f"read {len(data)} bytes at 0x{args.address:x}")
            if args.out is not None:
                exclusive_write(args.out, data)
                print(f"created {args.out}: {len(data)} bytes")
            return 0

        if args.command == "capture":
            if args.end <= args.start:
                raise ClientError("capture end must be greater than start")
            data = reader.read(args.start, args.end - args.start)
            exclusive_write(args.output, data)
            print(f"created {args.output}: {len(data)} bytes; chunksize={args.chunk}")
            print(hexdump(data[:args.chunk], args.start))
            return 0
        raise ClientError(f"unsupported command: {args.command}")
    except ClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
