import asyncio
from collections.abc import Callable

from .adb import Adb
from .config import Config
from .memory import Memory, watch_ranges
from .models import Candidate, RememError, Status, WatchSample, timestamp
from .module import Module
from .snapshots import SnapshotStore


class Service:
    """Serialize device mutations and reads; analysis can run independently."""

    def __init__(
        self,
        config: Config,
        log: Callable[[str], None] = lambda message: None,
        adb: Adb | None = None,
    ):
        self.config = config
        self.adb = adb or Adb(config.serial, config.timeout, log)
        self.module = Module(self.adb, config)
        self.memory = Memory(self.adb, config)
        self.store = SnapshotStore(config.captures, config.max_read_bytes)
        self.state = Status()
        self.lock = asyncio.Lock()
        self.previous: dict[tuple[int, int], int] = {}
        self.watches = list(config.candidates)

    async def devices(self):
        return await self.adb.devices()

    async def regions(self):
        async with self.lock:
            return await self.module.regions()

    async def kernel_logs(self):
        async with self.lock:
            return await self.module.logs()

    async def connect(self, serial: str) -> Status:
        async with self.lock:
            self.adb.serial = serial
            self.previous.clear()
            self.state = await self.module.status()
            return self.state

    async def refresh(self, auto_load: bool = False) -> Status:
        async with self.lock:
            previous_boot = self.state.boot_id
            self.state = await self.module.status()
            if self.state.boot_id != previous_boot:
                self.previous.clear()
            if auto_load and self.state.root and not self.state.loaded and not self.state.error:
                self.state = await self.module.load()
            return self.state

    async def select(self, number: int):
        async with self.lock:
            self.state.region = await self.module.select(number)
            self.previous.clear()
            return self.state.region

    async def load(self):
        async with self.lock:
            self.state = await self.module.load()
            return self.state

    async def unload(self, confirmed: bool):
        async with self.lock:
            await self.module.unload(confirmed)
            self.state = await self.module.status()
            self.previous.clear()

    def require_region(self):
        if self.state.error or not self.state.region or not self.state.root:
            raise RememError(
                self.state.error or "Connect a rooted device and load the module first"
            )
        return self.state.region

    async def read(self, offset: int, length: int):
        async with self.lock:
            region = self.require_region()
            if await self.module.boot() != self.state.boot_id:
                raise RememError("Android rebooted; refresh before reading")
            result = await self.memory.read(region, offset, length)
            if await self.module.boot() != self.state.boot_id:
                raise RememError("Android rebooted during read; data discarded")
            return result

    async def sample(self) -> list[WatchSample]:
        async with self.lock:
            region = self.require_region()
            # Boot is checked every cycle so same-looking metadata after reboot is rejected.
            if await self.module.boot() != self.state.boot_id:
                self.previous.clear()
                raise RememError("Android rebooted; refresh device status")
            offsets = [c.offset for c in self.watches if c.region == region.region]
            for offset in offsets:
                region.check(offset)
            values = {}
            for start, length in watch_ranges(offsets):
                data = await self.memory.read(region, start, length)
                values.update({o: data[o - start] for o in offsets if start <= o < start + length})
            if await self.module.boot() != self.state.boot_id:
                self.previous.clear()
                raise RememError("Android rebooted during sampling; data discarded")
            now = timestamp()
            samples = [
                WatchSample(o, value, self.previous.get((region.region, o)), now)
                for o, value in sorted(values.items())
            ]
            self.previous.update({(region.region, o): v for o, v in values.items()})
            return samples

    def add_watch(self, offset: int):
        region = self.require_region()
        region.check(offset)
        if not any(c.region == region.region and c.offset == offset for c in self.watches):
            self.watches.append(Candidate(region.region, offset))

    def remove_watch(self, offset: int):
        region = self.require_region()
        self.watches[:] = [
            c for c in self.watches if (c.region, c.offset) != (region.region, offset)
        ]
        self.previous.pop((region.region, offset), None)

    async def capture(self, label: str):
        async with self.lock:
            region = self.require_region()
            boot = await self.module.boot()
            if boot != self.state.boot_id:
                raise RememError("Boot changed; refresh before capture")
            data = await self.memory.read(region, 0, region.size)
            if await self.module.boot() != boot:
                raise RememError("Device rebooted during capture; data discarded")
            return await asyncio.to_thread(
                self.store.save, data, region, self.adb.serial, boot, label
            )
