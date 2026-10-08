import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .models import Region, RememError, timestamp, validate_boot


@dataclass(frozen=True)
class Snapshot:
    path: Path
    device_serial: str
    boot_id: str
    region: Region
    timestamp: str
    label: str
    sha256: str
    data: bytes


class SnapshotStore:
    def __init__(self, directory: Path, max_bytes: int = 64 * 1024 * 1024):
        self.directory, self.max_bytes = directory, max_bytes

    def save(self, data: bytes, region: Region, serial: str, boot: str, label: str) -> Snapshot:
        if len(data) != region.size or len(data) > self.max_bytes:
            raise RememError("Snapshot size does not match region or exceeds capture limit")
        if not serial:
            raise RememError("Snapshot must have a device serial")
        validate_boot(boot)
        label = label.strip()
        if not label or len(label) > 80:
            raise RememError("Snapshot label must contain 1–80 characters")
        self.directory.mkdir(parents=True, exist_ok=True)
        now = timestamp()
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", label)
        filename = f"region{region.region}_{safe}_{now.replace(':', '').replace('+', '_')}_{uuid.uuid4().hex[:6]}.bin"
        path = self.directory / filename
        digest = hashlib.sha256(data).hexdigest()
        meta = dict(
            schema=1,
            device_serial=serial,
            boot_id=boot,
            region=asdict(region),
            timestamp=now,
            label=label,
            sha256=digest,
        )
        binary_tmp = path.with_suffix(".bin.tmp")
        meta_tmp = path.with_suffix(".json.tmp")
        try:
            binary_tmp.write_bytes(data)
            meta_tmp.write_text(json.dumps(meta, indent=2) + "\n")
            binary_tmp.replace(path)
            # JSON is the commit marker; incomplete writes never appear in the manager.
            meta_tmp.replace(path.with_suffix(".json"))
        finally:
            binary_tmp.unlink(missing_ok=True)
            meta_tmp.unlink(missing_ok=True)
        return Snapshot(path, serial, boot, region, now, label, digest, data)

    def paths(self) -> list[Path]:
        return sorted((p.with_suffix(".bin") for p in self.directory.glob("*.json")), reverse=True)

    def resolve(self, reference: str) -> Path:
        path = Path(reference)
        if path.is_file():
            return path
        matches = []
        for candidate in self.paths():
            try:
                meta = json.loads(candidate.with_suffix(".json").read_text())
                if not isinstance(meta, dict):
                    raise ValueError("Metadata must be an object")
            except (ValueError, OSError) as exc:
                raise RememError(f"Malformed snapshot metadata: {candidate}") from exc
            if meta.get("label") == reference or candidate.name == reference:
                matches.append(candidate)
        if len(matches) != 1:
            raise RememError(
                f"Label {reference!r} matched {len(matches)} captures; use an exact path"
            )
        return matches[0]

    def load(self, path: Path) -> Snapshot:
        try:
            meta = json.loads(path.with_suffix(".json").read_text())
            if not isinstance(meta, dict):
                raise ValueError("Metadata must be an object")
            if meta["schema"] != 1:
                raise ValueError("Unknown snapshot schema")
            region = Region(**meta["region"])
            if not 1 <= region.region <= 5 or region.size <= 0:
                raise ValueError("Invalid region metadata")
            if region.size > self.max_bytes or path.stat().st_size != region.size:
                raise ValueError("Truncated capture or invalid capture size")
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != meta["sha256"]:
                raise ValueError("Capture checksum mismatch")
            if (
                not isinstance(meta["device_serial"], str)
                or not meta["device_serial"]
                or not isinstance(meta["boot_id"], str)
                or not isinstance(meta["label"], str)
            ):
                raise ValueError("Invalid capture provenance")
            stamp = datetime.fromisoformat(meta["timestamp"])
            if stamp.tzinfo is None:
                raise ValueError("Snapshot timestamp must have a timezone")
            validate_boot(meta["boot_id"])
            return Snapshot(
                path,
                meta["device_serial"],
                meta["boot_id"],
                region,
                meta["timestamp"],
                meta["label"],
                digest,
                data,
            )
        except (ValueError, TypeError, KeyError, OSError, AttributeError, RememError) as exc:
            raise RememError(f"Invalid capture {path}: {exc}") from exc


def compatible(snapshots: list[Snapshot]) -> None:
    if not snapshots:
        raise RememError("Select snapshots first")
    first = snapshots[0]
    if any(len(snapshot.data) != snapshot.region.size for snapshot in snapshots):
        raise RememError("Capture length does not match region metadata")
    for item in snapshots[1:]:
        if (
            item.device_serial,
            item.boot_id,
            item.region.region,
            item.region.size,
            item.region.md_phys,
            item.region.ap_phys,
            item.region.ap_virt,
        ) != (
            first.device_serial,
            first.boot_id,
            first.region.region,
            first.region.size,
            first.region.md_phys,
            first.region.ap_phys,
            first.region.ap_virt,
        ):
            raise RememError("Captures must share device, boot, region, size, and address bases")
        if len(item.data) != len(first.data):
            raise RememError("Capture lengths differ")
