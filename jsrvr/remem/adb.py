import asyncio
import re
import shlex
from collections.abc import Callable
from pathlib import Path

from .models import Device, RememError


def parse_devices(output: str) -> list[Device]:
    devices = []
    for line in output.splitlines():
        if not line.strip() or line.startswith(("List of devices", "*")):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise RememError(f"Malformed adb devices row: {line!r}")
        model = next((p[6:] for p in parts[2:] if p.startswith("model:")), "unknown")
        devices.append(Device(parts[0], parts[1], model))
    return devices


def resolve_symbol(output: str, symbol: str) -> int:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol):
        raise RememError("Invalid symbol name")
    matches = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == symbol:
            if (
                len(parts) != 3
                or parts[1] not in ("T", "t")
                or not re.fullmatch(r"[0-9a-fA-F]{16}", parts[0])
            ):
                raise RememError("Symbol is not a unique built-in ARM64 text symbol")
            matches.append(int(parts[0], 16))
    if len(matches) != 1:
        raise RememError(f"Expected exactly one live {symbol} text symbol; found {len(matches)}")
    address = matches[0]
    if address == 0:
        raise RememError("Kernel symbol addresses are hidden (zero); no address was guessed")
    if address >> 48 != 0xFFFF or address % 4:
        raise RememError("Symbol is not an aligned ARM64 kernel virtual address")
    return address


class Adb:
    def __init__(
        self,
        serial: str = "",
        timeout: float = 30,
        log: Callable[[str], None] = lambda message: None,
    ):
        self.serial = serial
        self.timeout = timeout
        self.log = log

    async def run(self, *args: str, binary: bool = False, device: bool = True) -> bytes:
        if device and not self.serial:
            raise RememError("Select a connected device first")
        command = ["adb", *(["-s", self.serial] if device else []), *args]
        self.log("$ " + shlex.join(command))
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError as exc:
            raise RememError("adb is missing; install Android platform-tools") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            process.kill()
            await process.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RememError(f"ADB command timed out after {self.timeout}s") from exc
        if stderr:
            self.log("stderr: " + stderr.decode(errors="replace").strip())
        if process.returncode:
            raise RememError(
                f"ADB failed ({process.returncode}): "
                + (stderr or stdout).decode(errors="replace").strip()
            )
        if not binary and stdout:
            rendered = stdout.decode(errors="replace").strip()
            self.log(
                rendered[:3000] + ("\n[output abbreviated in log]" if len(rendered) > 3000 else "")
            )
        return stdout

    async def devices(self) -> list[Device]:
        return parse_devices((await self.run("devices", "-l", device=False)).decode())

    async def root(self, command: str, binary: bool = False) -> bytes:
        # One shell-escaped remote command; user values are separately quoted by callers.
        remote = "su -c " + shlex.quote(command)
        # The non-PTY shell protocol preserves binary stdout, separates stderr,
        # and forwards exit status. exec-out can mix dd diagnostics into raw data.
        return await self.run("shell", "-T", remote, binary=binary)

    async def text(self, command: str) -> str:
        return (await self.root(command)).decode(errors="strict").strip()

    async def push(self, local: Path, remote: str) -> None:
        await self.run("push", str(local), remote)
