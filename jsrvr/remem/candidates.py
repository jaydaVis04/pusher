import heapq
from dataclasses import dataclass

from .diff import Change
from .models import RememError
from .snapshots import Snapshot, compatible


@dataclass(frozen=True)
class Finding:
    change: Change
    score: int
    nearby: tuple[int, ...]
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class CandidateReport:
    count: int
    findings: list[Finding]


def analyze_candidates(snapshots: list[Snapshot], limit: int = 1000) -> CandidateReport:
    if len(snapshots) < 4 or len(snapshots) % 2:
        raise RememError("Supply at least two OFF/ON pairs in alternating order")
    compatible(snapshots)
    if limit < 1:
        raise RememError("Candidate result limit must be positive")
    off, on = snapshots[::2], snapshots[1::2]
    # One byte per region byte, rather than one Python object per match. Even a
    # completely changed large capture cannot allocate millions of Finding objects.
    offsets = bytearray(len(off[0].data))
    count = 0
    for offset, (a, b) in enumerate(zip(off[0].data, on[0].data, strict=True)):
        if (
            a != b
            and all(s.data[offset] == a for s in off[1:])
            and all(s.data[offset] == b for s in on[1:])
        ):
            offsets[offset] = 1
            count += 1
    best: list[tuple[int, int, Finding]] = []
    for offset, eligible in enumerate(offsets):
        if not eligible:
            continue
        change = Change(offset, off[0].data[offset], on[0].data[offset])
        nearby = tuple(
            i
            for i in range(max(0, offset - 8), min(len(offsets), offset + 9))
            if i != offset and offsets[i]
        )
        patterns = []
        for width in (2, 4, 8):
            start = change.offset // width * width
            end = start + width
            if end > len(off[0].data):
                continue
            off_word, on_word = off[0].data[start:end], on[0].data[start:end]
            if all(s.data[start:end] == off_word for s in off) and all(
                s.data[start:end] == on_word for s in on
            ):
                patterns.append(
                    f"u{width * 8}@0x{start:x} LE "
                    f"0x{int.from_bytes(off_word, 'little'):x}→0x{int.from_bytes(on_word, 'little'):x}"
                )
        score = 10000 if {change.old, change.new} == {0, 1} else 0
        score += (1000 if len(change.bits) == 1 else 0) + 100 + len(nearby) * 10 + len(patterns)
        item = (score, -offset, Finding(change, score, nearby, tuple(patterns)))
        if len(best) < limit:
            heapq.heappush(best, item)
        else:
            heapq.heappushpop(best, item)
    findings = [item[2] for item in sorted(best, key=lambda item: (-item[0], -item[1]))]
    return CandidateReport(count, findings)


def repeated_candidates(snapshots: list[Snapshot], limit: int = 1000) -> list[Finding]:
    return analyze_candidates(snapshots, limit).findings


def neighborhood(old: Snapshot, new: Snapshot, offset: int, radius: int):
    compatible([old, new])
    old.region.check(offset)
    if radius not in (16, 32, 64, 128):
        raise RememError("Neighborhood radius must be 16, 32, 64, or 128")
    start, end = max(0, offset - radius), min(old.region.size, offset + radius + 1)
    return start, old.data[start:end], new.data[start:end]
