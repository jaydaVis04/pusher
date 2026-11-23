  from __future__ import annotations

  import argparse
  import json
  from pathlib import Path
  import re
  import subprocess
  import sys


  ADB = "adb"
  REMOTE_DEVICE = "/dev/re_mem"
  MAX_MAP_SIZE = 0x4000
  MAX_PREVIEW = 0x400


  class ClientError(RuntimeError):
      """A failed read or invalid observation."""


  def integer(text: str) -> int:
      try:
          return int(text, 0)
      except ValueError as exc:
          raise argparse.ArgumentTypeError(
              f"invalid integer: {text!r}"
          ) from exc


  def mapping_size(text: str) -> int:
      value = integer(text)
      if not 1 <= value <= MAX_MAP_SIZE:
          raise argparse.ArgumentTypeError(
              f"mapping size must be between 1 and {MAX_MAP_SIZE} bytes"
          )
      return value


  def read_size(text: str) -> int:
      value = integer(text)
      if not 1 <= value <= MAX_MAP_SIZE:
          raise argparse.ArgumentTypeError(
              f"read size must be between 1 and {MAX_MAP_SIZE} bytes"
          )
      return value


  def preview_size(text: str) -> int:
      value = integer(text)
      if not 1 <= value <= MAX_PREVIEW:
          raise argparse.ArgumentTypeError(
              f"preview size must be between 1 and {MAX_PREVIEW} bytes"
          )
      return value


  def expected_bytes(text: str) -> bytes:
      value = text.strip()

      if value.startswith("0x"):
          value = value[2:]

      value = (
          value.replace(" ", "")
          .replace(":", "")
          .replace("-", "")
      )

      if not value or not re.fullmatch(r"(?:[0-9A-Fa-f]{2})+", value):
          raise argparse.ArgumentTypeError(
              "expected value must contain complete hexadecimal byte pairs"
          )

      return bytes.fromhex(value)


  def binary_output(text: str) -> Path:
      path = Path(text).expanduser()

      if path.suffix.lower() != ".bin":
          raise argparse.ArgumentTypeError(
              "binary output filename must end in .bin"
          )

      return path


  def checked_offsets(
      address: int,
      length: int,
      base: int,
      size: int,
  ) -> tuple[int, int]:
      """Validate a nonempty range contained entirely in the mapping."""
      if length <= 0:
          raise ClientError("read length must be positive")

      mapping_end = base + size
      requested_end = address + length

      if address < base or requested_end > mapping_end:
          raise ClientError(
              f"requested range [0x{address:x}, 0x{requested_end:x}) "
              f"is outside the declared mapping "
              f"[0x{base:x}, 0x{mapping_end:x})"
          )

      start = address - base
      return start, start + length


  def hexdump(data: bytes, base: int, width: int = 16) -> str:
      lines = []

      for offset in range(0, len(data), width):
          block = data[offset:offset + width]
          hexadecimal = " ".join(f"{byte:02x}" for byte in block)
          printable = "".join(
              chr(byte) if 32 <= byte < 127 else "."
              for byte in block
          )
          lines.append(
              f"{base + offset:08x}  {hexadecimal:<47}  |{printable}|"
          )

      return "\n".join(lines)


  def exclusive_write(path: Path, data: bytes) -> None:
      """Create a new evidence file without replacing an existing file."""
      try:
          with path.open("xb") as stream:
              stream.write(data)
      except FileExistsError as exc:
          raise ClientError(
              f"refusing to overwrite existing file: {path}"
          ) from exc
      except OSError as exc:
          raise ClientError(f"could not create {path}: {exc}") from exc


  class WindowReader:
      """Read one whole mapping through ADB and cache it for this invocation."""

      def __init__(self, base: int, size: int, timeout: float):
          self.base = base
          self.size = size
          self.timeout = timeout
          self.cached_window: bytes | None = None

      def remote_read_command(self) -> str:
          return (
              f"dd if={REMOTE_DEVICE} "
              f"bs={self.size} count=1 2>/dev/null"
          )

      def fetch(self) -> bytes:
          if self.cached_window is not None:
              return self.cached_window

          command = [
              ADB,
              "exec-out",
              "su",
              "-c",
              self.remote_read_command(),
          ]

          try:
              result = subprocess.run(
                  command,
                  stdin=subprocess.DEVNULL,
                  stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE,
                  check=False,
                  timeout=self.timeout,
              )
          except FileNotFoundError as exc:
              raise ClientError(
                  "adb was not found in PATH; install Android platform-tools"
              ) from exc
          except subprocess.TimeoutExpired as exc:
              raise ClientError(
                  f"ADB read exceeded {self.timeout:g} seconds"
              ) from exc
          except OSError as exc:
              raise ClientError(f"could not start ADB: {exc}") from exc

          error_text = result.stderr.decode(
              "utf-8", errors="replace"
          ).strip()

          if result.returncode != 0:
              detail = error_text or "no error text returned"
              raise ClientError(
                  f"ADB read failed with status {result.returncode}: {detail}\n"
                  "Confirm that exactly one intended ADB device is connected, "
                  "root access works, and re_mem is already loaded."
              )

          actual_size = len(result.stdout)

          if actual_size != self.size:
              raise ClientError(
                  f"incomplete or inconsistent read: expected {self.size} "
                  f"bytes but received {actual_size}. No observation was "
                  "accepted and no output file was created. Check the active "
                  "mapping base/size and the re_mem read contract."
              )

          self.cached_window = result.stdout
          return self.cached_window

      def read(self, address: int, length: int) -> bytes:
          start, end = checked_offsets(
              address, length, self.base, self.size
          )
          return self.fetch()[start:end]


  def make_parser() -> argparse.ArgumentParser:
      parser = argparse.ArgumentParser(
          description=__doc__,
          formatter_class=argparse.RawDescriptionHelpFormatter,
      )

      parser.add_argument(
          "--phys-base",
          required=True,
          type=integer,
          help="actual physical base of the already-loaded mapping",
      )
      parser.add_argument(
          "--map-size",
          required=True,
          type=mapping_size,
          help="actual mapping size, at most 0x4000 bytes",
      )
      parser.add_argument(
          "--timeout",
          type=float,
          default=20.0,
          help="ADB timeout in seconds; default is 20",
      )

      commands = parser.add_subparsers(
          dest="command",
          required=True,
      )

      commands.add_parser(
          "info",
          help="print the configuration without contacting ADB",
      )

      verify = commands.add_parser(
          "verify",
          help="compare bytes at an address with an expected anchor",
      )
      verify.add_argument("address", type=integer)
      verify.add_argument("expected", type=expected_bytes)

      read = commands.add_parser(
          "read",
          help="read and hexdump bytes from the declared mapping",
      )
      read.add_argument("address", type=integer)
      read.add_argument(
          "length",
          nargs="?",
          type=read_size,
          default=16,
          help="number of bytes; default is 16",
      )
      read.add_argument(
          "--out",
          type=binary_output,
          help="also save raw bytes to a new .bin file",
      )

      capture = commands.add_parser(
          "capture",
          help="save a range from one declared mapping",
      )
      capture.add_argument("--start", required=True, type=integer)
      capture.add_argument(
          "--end",
          required=True,
          type=integer,
          help="exclusive end address",
      )
      capture.add_argument(
          "--output",
          required=True,
          type=binary_output,
          help="new .bin evidence file",
      )
      capture.add_argument(
          "--preview",
          type=preview_size,
          default=64,
          help="bytes to display after capture; default is 64",
      )

      return parser


  def main() -> int:
      parser = make_parser()
      args = parser.parse_args()

      if args.phys_base < 0:
          parser.error("--phys-base cannot be negative")

      if args.timeout <= 0:
          parser.error("--timeout must be positive")

      reader = WindowReader(
          base=args.phys_base,
          size=args.map_size,
          timeout=args.timeout,
      )

      if args.command == "info":
          print(json.dumps({
              "transport": "ADB exec-out, su, dd",
              "remote_device": REMOTE_DEVICE,
              "remote_read": reader.remote_read_command(),
              "phys_base": f"0x{args.phys_base:x}",
              "map_size": args.map_size,
              "mapped_range": [
                  f"0x{args.phys_base:x}",
                  f"0x{args.phys_base + args.map_size:x}",
              ],
              "adb_contacted": False,
              "serial_port_used": False,
              "device_writes": False,
              "csci_debugger": False,
          }, indent=2))
          return 0

      try:
          if args.command == "verify":
              observed = reader.read(
                  args.address,
                  len(args.expected),
              )

              print(
                  f"observed @0x{args.address:x}: "
                  f"{observed.hex()}"
              )
              print(
                  f"expected @0x{args.address:x}: "
                  f"{args.expected.hex()}"
              )

              if observed != args.expected:
                  raise ClientError(
                      "anchor mismatch; do not treat this mapping as verified"
                  )

              print("MATCH: expected anchor bytes were observed")
              return 0

          if args.command == "read":
              data = reader.read(args.address, args.length)

              print(hexdump(data, args.address))
              print(
                  f"read {len(data)} bytes at 0x{args.address:x}"
              )

              if args.out is not None:
                  exclusive_write(args.out, data)
                  print(f"created {args.out}: {len(data)} bytes")

              return 0

          if args.command == "capture":
              length = args.end - args.start

              if length <= 0:
                  raise ClientError(
                      "capture end must be greater than capture start"
                  )

              data = reader.read(args.start, length)
              exclusive_write(args.output, data)

              print(
                  f"created {args.output}: {len(data)} bytes"
              )
              print(hexdump(
                  data[:args.preview],
                  args.start,
              ))
              return 0

          raise ClientError(f"unsupported command: {args.command}")

      except ClientError as exc:
          print(f"ERROR: {exc}", file=sys.stderr)
          return 1
      except KeyboardInterrupt:
          print("ERROR: interrupted", file=sys.stderr)
          return 130


  if __name__ == "__main__":
      sys.exit(main())
