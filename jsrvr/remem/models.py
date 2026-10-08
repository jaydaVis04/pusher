import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


class RememError(Exception):
    """An actionable device, protocol, or analysis error."""


def parse_number(value: str | int) -> int:
    """Digits alone are decimal; 0x or a-f denotes hexadecimal."""
    text = str(value).strip().lower()
    if not re.fullmatch(r"(?:0x[0-9a-f]+|[0-9a-f]+)", text):
        raise RememError(f"Invalid non-negative number: {value!r}")
    return int(text, 16 if text.startswith("0x") or re.search("[a-f]", text) else 10)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_boot(value: str) -> str:
    try:
        return str(uuid.UUID(value.strip()))
    except ValueError as exc:
        raise RememError("Missing or malformed Android boot ID") from exc


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    model: str = "unknown"


@dataclass(frozen=True)
class Region:
    region: int
    size: int
    md_phys: int
    ap_phys: int
    ap_virt: int
    generation: int = 0

    def __post_init__(self) -> None:
        values = (self.region, self.size, self.md_phys, self.ap_phys, self.ap_virt, self.generation)
        if any(type(value) is not int for value in values):
            raise RememError("Region metadata must contain integers")
        if not 1 <= self.region <= 5 or not 0 < self.size < 1 << 63 or self.generation < 0:
            raise RememError("Invalid region number, size, or generation")
        if not self.ap_virt or any(
            base < 0 or base + self.size > 1 << 64
            for base in (self.md_phys, self.ap_phys, self.ap_virt)
        ):
            raise RememError("Invalid region address bounds")

    def check(self, offset: int, length: int = 1) -> None:
        if offset < 0 or length < 1 or offset >= self.size or length > self.size - offset:
            raise RememError(
                f"Range 0x{offset:x}+0x{length:x} exceeds region {self.region} "
                f"(0x{self.size:x} bytes)"
            )

    def addresses(self, offset: int) -> tuple[int, int, int]:
        self.check(offset)
        return self.md_phys + offset, self.ap_phys + offset, self.ap_virt + offset


@dataclass
class Status:
    serial: str = ""
    model: str = "unknown"
    connected: bool = False
    root: bool = False
    boot_id: str = ""
    kernel: str = ""
    loaded: bool = False
    dev_present: bool = False
    region: Region | None = None
    error: str = ""


@dataclass(frozen=True)
class Candidate:
    region: int
    offset: int
    name: str = "User watch"
    off_value: int | None = None
    on_value: int | None = None

    def correlation(self, value: int) -> str:
        if self.off_value is not None and value == self.off_value:
            return "observed OFF correlation"
        if self.on_value is not None and value == self.on_value:
            return "observed ON correlation"
        return "no observed correlation"


@dataclass(frozen=True)
class WatchSample:
    offset: int
    current: int
    previous: int | None
    timestamp: str

    @property
    def xor(self) -> int:
        return 0 if self.previous is None else self.previous ^ self.current
