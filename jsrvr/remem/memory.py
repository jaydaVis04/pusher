from .adb import Adb
from .config import Config
from .models import Region, RememError
from .module import SYSFS
from .regions import parse_info


class Memory:
    def __init__(self, adb: Adb, config: Config):
        self.adb, self.config = adb, config

    async def read(self, region: Region, offset: int, length: int) -> bytes:
        region.check(offset, length)
        if length > self.config.max_read_bytes:
            raise RememError("Read exceeds configured max_read_bytes")
        before = parse_info(await self.adb.text(f"cat {SYSFS}/info"))
        if before != region:
            raise RememError("Selected region or generation changed before read; refresh")
        if self.config.read_mode == "cat":
            if region.size > self.config.max_read_bytes:
                raise RememError("Full-region cat exceeds configured max_read_bytes")
            raw = await self.adb.root("cat /dev/re_mem", binary=True)
            if len(raw) != region.size:
                raise RememError(f"Truncated full-region read: {len(raw)} / {region.size}")
            result = raw[offset : offset + length]
        elif offset == 0 and length == region.size:
            result = await self.adb.root("cat /dev/re_mem", binary=True)
        else:
            result = await self.adb.root(
                f"dd if=/dev/re_mem bs=1 skip={offset} count={length}", binary=True
            )
        if len(result) != length:
            kind = "Short" if len(result) < length else "Excess"
            raise RememError(f"{kind} memory read: expected {length}, received {len(result)}")
        after = parse_info(await self.adb.text(f"cat {SYSFS}/info"))
        if after != before:
            raise RememError("Region changed during read; data discarded")
        return result


def watch_ranges(offsets: list[int], gap: int = 16) -> list[tuple[int, int]]:
    """Coalesce nearby bytes; never read the large gaps between distant candidates."""
    result: list[tuple[int, int]] = []
    for offset in sorted(set(offsets)):
        if result and offset - (result[-1][0] + result[-1][1]) <= gap:
            start, _ = result[-1]
            result[-1] = (start, offset - start + 1)
        else:
            result.append((offset, 1))
    return result
