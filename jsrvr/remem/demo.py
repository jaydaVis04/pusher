"""Synthetic backend. Never executes ADB or represents real-device verification."""

import asyncio
import time

from .config import Config
from .models import Device, Region, RememError, Status, WatchSample, timestamp
from .service import Service

DEMO_BOOT = "00000000-0000-4000-8000-000000000001"


class DemoService(Service):
    def __init__(self, config: Config, log=lambda message: None):
        super().__init__(config, log)
        self.log = log
        self.off = True
        self.auto_toggle = True
        self.synthetic_regions = [
            Region(i, 0xB0000, i << 28, (i + 5) << 28, 0xFFFF000000000000 + (i << 24))
            for i in range(1, 6)
        ]
        self.state = Status(
            "DEMO",
            "Synthetic ARM64",
            True,
            True,
            DEMO_BOOT,
            "demo · no device",
            True,
            True,
            self.synthetic_regions[config.default_region - 1],
        )
        self.adb.serial = "DEMO"

    async def devices(self):
        return [Device("DEMO", "device", "Synthetic_ARM64")]

    async def connect(self, serial):
        return self.state

    async def refresh(self, auto_load=False):
        return self.state

    async def select(self, number):
        if number not in range(1, 6):
            raise RememError("Region must be 1 through 5")
        self.state.region = self.synthetic_regions[number - 1]
        self.previous.clear()
        self.log(f"DEMO: select region {number}; no ADB")
        return self.state.region

    async def load(self):
        self.state.loaded = self.state.dev_present = True
        self.state.region = self.synthetic_regions[self.config.default_region - 1]
        self.state.error = ""
        self.log("DEMO: module load simulated")
        return self.state

    async def unload(self, confirmed):
        if not confirmed:
            raise RememError("Confirmation required")
        self.state.loaded = self.state.dev_present = False
        self.state.region = None
        self.previous.clear()
        self.log("DEMO: explicit unload simulated")

    def data(self, start, length):
        region = self.require_region()
        region.check(start, length)
        result = bytearray(length)
        if region.region == 2:
            for offset, value in (
                (0xFC04, 0x40 if self.off else 0),
                (0xA40B4, 8 if self.off else 0x88),
                (0xA40B8, 8 if self.off else 0x88),
            ):
                if start <= offset < start + length:
                    result[offset - start] = value
        return bytes(result)

    async def read(self, offset, length):
        return self.data(offset, length)

    async def sample(self):
        region = self.require_region()
        if self.auto_toggle:
            self.off = int(time.monotonic() / 3) % 2 == 0
        now = timestamp()
        samples = []
        for candidate in sorted(self.watches, key=lambda c: c.offset):
            if candidate.region == region.region:
                value = self.data(candidate.offset, 1)[0]
                key = (region.region, candidate.offset)
                samples.append(WatchSample(candidate.offset, value, self.previous.get(key), now))
                self.previous[key] = value
        return samples

    async def capture(self, label):
        async with self.lock:
            region = self.require_region()
            return await asyncio.to_thread(
                self.store.save, self.data(0, region.size), region, "DEMO", DEMO_BOOT, label
            )

    async def regions(self):
        return self.synthetic_regions

    async def kernel_logs(self):
        return "DEMO: re_mem read-only module ready (synthetic; no real device)"
