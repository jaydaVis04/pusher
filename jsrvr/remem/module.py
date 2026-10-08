import shlex
from pathlib import Path

from .adb import Adb, resolve_symbol
from .config import Config
from .models import RememError, Status, validate_boot
from .regions import parse_info, parse_regions

SYSFS = "/sys/class/misc/re_mem"


class Module:
    def __init__(self, adb: Adb, config: Config):
        self.adb = adb
        self.config = config
        # No live address is persisted or reused, even within the same boot.
        self.boot_id = ""

    async def boot(self) -> str:
        boot = validate_boot(await self.adb.text("cat /proc/sys/kernel/random/boot_id"))
        if self.boot_id and boot != self.boot_id:
            self.adb.log("WARNING: Android boot changed; previous metadata invalidated")
        self.boot_id = boot
        return boot

    async def status(self) -> Status:
        devices = await self.adb.devices()
        device = next((d for d in devices if d.serial == self.adb.serial), None)
        state = Status(serial=self.adb.serial)
        if device is None or device.state != "device":
            state.error = "Device disconnected, offline, or unauthorized"
            return state
        state.connected, state.model = True, device.model
        try:
            identity = await self.adb.text("id")
            state.root = "uid=0(" in identity or identity.startswith("uid=0 ")
            if not state.root:
                raise RememError("su did not grant root")
            state.boot_id = await self.boot()
            state.kernel = await self.adb.text("uname -r")
            name = shlex.quote(self.config.module_name)
            state.loaded = (
                await self.adb.text(f"test -d /sys/module/{name} && echo yes || echo no") == "yes"
            )
            state.dev_present = (
                await self.adb.text("test -c /dev/re_mem && echo yes || echo no") == "yes"
            )
            if state.loaded:
                state.region = parse_info(await self.adb.text(f"cat {SYSFS}/info"))
                await self.adb.text(f"test -r {SYSFS}/regions && test -w {SYSFS}/region")
                if not state.dev_present:
                    raise RememError("Module loaded but /dev/re_mem is missing")
            elif state.dev_present:
                raise RememError(
                    "Unexpected /dev/re_mem without configured module; refusing insertion"
                )
            if await self.boot() != state.boot_id:
                state.region = None
                raise RememError("Android rebooted during status refresh; refresh again")
        except RememError as exc:
            state.error = str(exc)
        return state

    async def load(self) -> Status:
        state = await self.status()
        if state.loaded:
            if state.error:
                raise RememError(state.error + "; keep module loaded and inspect diagnostics")
            self.adb.log("Module already loaded; using existing instance")
            return state
        if state.error or not state.root:
            raise RememError(state.error or "Root is required")
        if not self.config.abi_verified:
            raise RememError(
                "Module ABI is unverified. Verify the supplied driver layout, build for "
                "this device, then set module.abi_verified=true in config.toml"
            )
        local: Path = self.config.local_path
        if not local.is_file():
            raise RememError(f"Module file missing: {local}")
        boot = state.boot_id
        try:
            address = resolve_symbol(await self.adb.text("cat /proc/kallsyms"), self.config.symbol)
        except RememError as exc:
            visibility = await self.adb.text("cat /proc/sys/kernel/kptr_restrict")
            raise RememError(
                f"{exc}; kptr_restrict={visibility}. No sysctl was changed. "
                "Expose the live symbol explicitly on your test device."
            ) from exc
        self.adb.log(f"RESOLVED {self.config.symbol} = 0x{address:016x} | boot {boot}")
        await self.adb.push(local, self.config.remote_path)
        # Revalidate after transfer, immediately before insertion.
        if await self.boot() != boot:
            raise RememError("Device rebooted before insertion; resolve again")
        verified = resolve_symbol(await self.adb.text("cat /proc/kallsyms"), self.config.symbol)
        if verified != address:
            raise RememError("Live symbol changed before insertion; refusing insmod")
        # Verify boot in the same remote shell that inserts. An ADB reconnect to a
        # new boot between the host-side checks and this command must not call myaddr.
        self.adb.log(f"INSERTING verified live {self.config.symbol} @ 0x{address:016x}")
        await self.adb.text(
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = {shlex.quote(boot)} && '
            f"insmod {shlex.quote(self.config.remote_path)} "
            f"myaddr=0x{address:x} region={self.config.default_region}"
        )
        result = await self.status()
        if result.error or not result.loaded or not result.dev_present or result.boot_id != boot:
            raise RememError(result.error or "Module insertion could not be verified")
        return result

    async def unload(self, confirmed: bool = False) -> None:
        if not confirmed:
            raise RememError("Explicit confirmation is required to unload")
        await self.adb.text("rmmod " + shlex.quote(self.config.module_name))
        if (await self.status()).loaded:
            raise RememError("Module still loaded after rmmod")

    async def select(self, number: int):
        if number not in range(1, 6):
            raise RememError("Region must be 1 through 5")
        await self.adb.text(f"printf '%s\\n' {number} > {SYSFS}/region")
        region = parse_info(await self.adb.text(f"cat {SYSFS}/info"))
        if region.region != number:
            raise RememError("Region changed concurrently; retry")
        self.adb.log(f"Selected region {number}; no module reload")
        return region

    async def regions(self):
        return parse_regions(await self.adb.text(f"cat {SYSFS}/regions"))

    async def logs(self) -> str:
        # Filter locally; a grep no-match status is not an ADB failure.
        return "\n".join(
            line for line in (await self.adb.text("dmesg")).splitlines() if "re_mem" in line
        )
