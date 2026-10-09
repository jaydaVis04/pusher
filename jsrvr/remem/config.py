import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .models import Candidate, RememError, parse_number

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class Config:
    serial: str = ""
    timeout: float = 30
    local_path: Path = Path("kernel/re_mem.ko")
    remote_path: str = "/data/local/tmp/re_mem.ko"
    symbol: str = "getthisguy"
    module_name: str = "re_mem"
    abi_verified: bool = False
    default_region: int = 2
    interval_ms: int = 250
    read_mode: str = "bounded"
    max_read_bytes: int = 64 * 1024 * 1024
    captures: Path = Path("captures")
    candidates: list[Candidate] = field(
        default_factory=lambda: [
            Candidate(2, 0xFC04, "Display state (observed correlation)", 0x40, 0x00),
            Candidate(2, 0xA40B4, "Display-related A", 0x08, 0x88),
            Candidate(2, 0xA40B8, "Display-related B", 0x08, 0x88),
        ]
    )

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        try:
            data = tomllib.loads(path.read_text())
            adb, mod, ui = (data.get(k, {}) for k in ("adb", "module", "ui"))
            mem = data.get("memory", {})
            base = path.resolve().parent
            config = cls(
                serial=adb.get("serial", ""),
                timeout=float(adb.get("timeout_seconds", 30)),
                local_path=base / mod.get("local_path", "kernel/re_mem.ko"),
                remote_path=mod.get("remote_path", "/data/local/tmp/re_mem.ko"),
                symbol=mod.get("symbol", "getthisguy"),
                module_name=mod.get("name", "re_mem"),
                abi_verified=mod.get("abi_verified", False),
                default_region=int(ui.get("default_region", 2)),
                interval_ms=int(ui.get("watch_interval_ms", 250)),
                read_mode=mem.get("read_mode", "bounded"),
                max_read_bytes=int(mem.get("max_read_bytes", 64 * 1024 * 1024)),
                captures=base / data.get("captures", {}).get("directory", "captures"),
            )
            if "candidate" in data:
                config.candidates = [
                    Candidate(
                        int(c["region"]),
                        parse_number(c["offset"]),
                        c.get("name", "User watch"),
                        parse_number(c["off_value"]) if "off_value" in c else None,
                        parse_number(c["on_value"]) if "on_value" in c else None,
                    )
                    for c in data["candidate"]
                ]
            if (
                config.read_mode not in ("bounded", "cat")
                or config.timeout <= 0
                or not math.isfinite(config.timeout)
                or config.interval_ms < 100
                or not 1 <= config.default_region <= 5
                or config.max_read_bytes < 1
                or not isinstance(config.abi_verified, bool)
            ):
                raise ValueError("Invalid read mode, timeout, interval, region, or limit")
            if (
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.symbol)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config.module_name)
                or not config.remote_path.startswith("/")
                or "\x00" in config.remote_path
                or not isinstance(config.serial, str)
            ):
                raise ValueError("Invalid symbol/module name, remote path, or serial")
            for candidate in config.candidates:
                if not 1 <= candidate.region <= 5 or any(
                    v is not None and not 0 <= v <= 255
                    for v in (candidate.off_value, candidate.on_value)
                ):
                    raise ValueError("Invalid candidate region or byte")
            return config
        except (ValueError, TypeError, KeyError) as exc:
            raise RememError(f"Invalid config {path}: {exc}") from exc
