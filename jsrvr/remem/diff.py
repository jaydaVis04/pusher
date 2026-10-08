from collections.abc import Iterator
from dataclasses import dataclass

from .models import RememError


def changed_bits(xor: int) -> tuple[int, ...]:
    return tuple(bit for bit in range(8) if xor & (1 << bit))


@dataclass(frozen=True)
class Change:
    offset: int
    old: int
    new: int

    @property
    def xor(self) -> int:
        return self.old ^ self.new

    @property
    def bits(self) -> tuple[int, ...]:
        return changed_bits(self.xor)


FILTERS = ("all", "single-bit", "0-to-1", "1-to-0", "boolean")


def matches(change: Change, mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "single-bit":
        return len(change.bits) == 1
    if mode == "0-to-1":
        return change.old & ~change.new == 0
    if mode == "1-to-0":
        return change.new & ~change.old == 0
    if mode == "boolean":
        return {change.old, change.new} == {0, 1} or len(change.bits) == 1
    raise RememError(f"Unknown change filter: {mode}")


def diff_bytes(old: bytes, new: bytes, mode: str = "all", start: int = 0) -> Iterator[Change]:
    if len(old) != len(new):
        raise RememError("Cannot diff truncated or unequal-length buffers")
    if mode not in FILTERS:
        raise RememError(f"Unknown change filter: {mode}")
    for offset, (a, b) in enumerate(zip(old, new, strict=True), start):
        if a != b:
            change = Change(offset, a, b)
            if matches(change, mode):
                yield change
