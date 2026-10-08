import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from remem.adb import parse_devices, resolve_symbol
from remem.candidates import analyze_candidates, neighborhood, repeated_candidates
from remem.config import Config
from remem.diff import changed_bits, diff_bytes
from remem.memory import watch_ranges
from remem.models import Region, RememError, parse_number, timestamp
from remem.regions import parse_info, parse_regions
from remem.snapshots import SnapshotStore, compatible

BOOT = "01234567-89ab-4cde-8fab-0123456789ab"
INFO = "region=2\nsize=0x100\nmd_phys=0x40000000\nap_phys=0x60000000\nap_virt=0xffffff800a28b000\ngeneration=1\n"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0xfc04", 64516),
        ("fc04", 64516),
        ("64516", 64516),
        ("10", 10),
        ("0x10", 16),
        ("0XFC04", 64516),
        (" 00 ", 0),
    ],
)
def test_parse_number(value, expected):
    assert parse_number(value) == expected


@pytest.mark.parametrize("value", ["-1", "", "0x", "1.2", "; reboot", "1_000", "xyz"])
def test_bad_number(value):
    with pytest.raises(RememError):
        parse_number(value)


def test_translation_and_bounds():
    r = Region(2, 0x900000, 0x40000000, 0x60000000, 0xFFFFFF800A28B000)
    assert r.addresses(0xFC04) == (0x4000FC04, 0x6000FC04, 0xFFFFFF800A29AC04)
    r.check(r.size - 1)
    for offset, length in [(-1, 1), (r.size, 1), (0, 0), (r.size - 1, 2), (1, -1)]:
        with pytest.raises(RememError):
            r.check(offset, length)


def test_sysfs():
    r = parse_info(INFO)
    assert r.size == 256 and r.generation == 1
    assert parse_regions(INFO + "\n" + INFO.replace("region=2", "region=3"))[1].region == 3
    for malformed in [
        "",
        "dmesg: re_mem",
        INFO + "region=2\n",
        INFO.replace("0x100", "0"),
        INFO.replace("0x100", "-1"),
        INFO.replace("region=2", "region=9"),
        INFO.replace("size=0x100", "size=banana"),
    ]:
        with pytest.raises(RememError):
            parse_info(malformed)
    with pytest.raises(RememError):
        parse_regions(INFO + "\n" + INFO)


def test_adb_devices():
    devices = parse_devices(
        "List of devices attached\nA device product:foo model:Pixel_8\nB unauthorized\nC offline\n"
    )
    assert [(d.serial, d.state, d.model) for d in devices] == [
        ("A", "device", "Pixel_8"),
        ("B", "unauthorized", "unknown"),
        ("C", "offline", "unknown"),
    ]
    assert parse_devices("List of devices attached\n") == []
    with pytest.raises(RememError):
        parse_devices("malformed")


def test_symbol_resolution():
    address = resolve_symbol(
        "ffffff8001234000 t getthisguy\n0000000000000000 T other", "getthisguy"
    )
    assert address == 0xFFFFFF8001234000
    for output in [
        "0000000000000000 T getthisguy",
        "0000000040000000 T getthisguy",
        "ffffff8001234001 T getthisguy",
        "ffffff8001234000 D getthisguy",
        "ffffff8001234000 T getthisguy [module]",
        "ffffff8001234000 T getthisguy\n" * 2,
        "ffffff8001234000 T getthisguy_suffix",
        "garbage T getthisguy",
    ]:
        with pytest.raises(RememError):
            resolve_symbol(output, "getthisguy")


def test_xor_diff_filters():
    old, new = bytes([0x40, 8, 0, 3, 5]), bytes([0, 0x88, 1, 4, 5])
    changes = list(diff_bytes(old, new))
    assert [c.xor for c in changes] == [0x40, 0x80, 1, 7]
    assert changes[0].bits == (6,) and changed_bits(0x81) == (0, 7)
    assert len(list(diff_bytes(old, new, "single-bit"))) == 3
    assert [c.offset for c in diff_bytes(old, new, "0-to-1")] == [1, 2]
    assert [c.offset for c in diff_bytes(old, new, "1-to-0")] == [0]
    assert len(list(diff_bytes(old, new, "boolean"))) == 3
    with pytest.raises(RememError):
        list(diff_bytes(b"xx", b"x"))


def test_watch_coalescing():
    assert watch_ranges([0xFC04, 0xA40B4, 0xA40B8, 0xFC04]) == [(0xFC04, 1), (0xA40B4, 5)]


def test_snapshot_roundtrip_and_corruption(tmp_path):
    store = SnapshotStore(tmp_path)
    region = parse_info(INFO)
    saved = store.save(bytes(256), region, "serial", BOOT, "OFF1")
    loaded = store.load(saved.path)
    assert loaded == saved and store.resolve("OFF1") == saved.path
    meta = json.loads(saved.path.with_suffix(".json").read_text())
    assert meta["device_serial"] == "serial" and meta["region"]["ap_phys"] == 0x60000000
    assert meta["boot_id"] == BOOT and meta["label"] == "OFF1" and meta["timestamp"]
    saved.path.write_bytes(bytes(255))
    with pytest.raises(RememError, match="Truncated"):
        store.load(saved.path)
    saved.path.write_bytes(b"x" * 256)
    with pytest.raises(RememError, match="checksum"):
        store.load(saved.path)
    saved.path.with_suffix(".json").write_text("not json")
    with pytest.raises(RememError):
        store.load(saved.path)


def test_snapshot_size_labels_and_compatibility(tmp_path):
    store = SnapshotStore(tmp_path)
    region = parse_info(INFO)
    with pytest.raises(RememError):
        store.save(b"x", region, "serial", BOOT, "OFF1")
    a = store.save(bytes(256), region, "serial", BOOT, "OFF1")
    b = store.save(bytes(256), replace(region, generation=9), "serial", BOOT, "OFF1")
    compatible([a, b])  # A selector generation is not capture identity.
    with pytest.raises(RememError, match="matched 2"):
        store.resolve("OFF1")
    with pytest.raises(RememError):
        compatible([a, replace(b, device_serial="other")])
    with pytest.raises(RememError):
        compatible([a, replace(b, boot_id="00000000-0000-4000-8000-000000000001")])


def test_repeated_candidates_and_neighborhood(tmp_path):
    store = SnapshotStore(tmp_path)
    region = parse_info(INFO)
    captures = []
    for pair in range(3):
        off, on = bytearray(256), bytearray(256)
        off[32], on[32] = 0x40, 0
        off[40], on[40] = 0, 1
        off[44], on[44] = 8, 0x88
        off[100], on[100] = pair, 8  # unstable across OFF captures
        for label, data in ((f"OFF{pair + 1}", off), (f"ON{pair + 1}", on)):
            captures.append(store.save(bytes(data), region, "serial", BOOT, label))
    findings = repeated_candidates(captures)
    assert {f.change.offset for f in findings} == {32, 40, 44}
    assert findings[0].change.offset == 40  # exact boolean comes first
    assert 44 in findings[0].nearby and findings[0].patterns
    start, off, on = neighborhood(captures[0], captures[1], 32, 16)
    assert start == 16 and len(off) == 33 and len(list(diff_bytes(off, on))) == 3
    start, off, on = neighborhood(captures[0], captures[1], 0, 32)
    assert start == 0 and len(off) == 33
    with pytest.raises(RememError):
        repeated_candidates(captures[:3])


def test_config(tmp_path):
    config = Config.load(tmp_path / "missing.toml")
    assert config.default_region == 2 and not config.abi_verified
    path = tmp_path / "bad.toml"
    path.write_text("[ui]\nwatch_interval_ms=0\n")
    with pytest.raises(RememError):
        Config.load(path)


def test_config_toml_parsing_and_relative_paths(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[module]\nlocal_path="kernel/test.ko"\n'
        "[ui]\ndefault_region=3\n"
        '[[candidate]]\nregion=3\noffset="0xfc04"\noff_value="0x40"\non_value="0x00"\n'
    )
    config = Config.load(path)
    assert config.local_path == tmp_path / "kernel" / "test.ko"
    assert config.default_region == 3
    assert config.candidates[0].offset == 0xFC04
    assert config.candidates[0].off_value == 0x40
    path.write_text('[ui\ndefault_region="unterminated')
    with pytest.raises(RememError, match="Invalid config"):
        Config.load(path)


def test_timestamp_includes_utc_timezone():
    parsed = datetime.fromisoformat(timestamp())
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_candidate_limit_keeps_full_count_and_best_rank(tmp_path):
    store = SnapshotStore(tmp_path)
    region = parse_info(INFO)
    off, on = bytes(256), bytes([1] * 256)
    snapshots = [
        store.save(data, region, "serial", BOOT, label)
        for label, data in (("OFF1", off), ("ON1", on), ("OFF2", off), ("ON2", on))
    ]
    report = analyze_candidates(snapshots, limit=2)
    assert report.count == 256 and len(report.findings) == 2
    # Central aligned words have the most nearby evidence; ties sort by offset.
    assert report.findings[0].change.offset == 8
    assert report.findings[1].change.offset == 9


@pytest.mark.parametrize(
    "bad",
    [[], {"schema": 999}, {"schema": 1, "region": {}}, {"schema": 1, "region": {"region": True}}],
)
def test_malformed_capture_metadata(tmp_path, bad):
    path = tmp_path / "bad.bin"
    path.write_bytes(bytes(256))
    path.with_suffix(".json").write_text(json.dumps(bad))
    with pytest.raises(RememError):
        SnapshotStore(tmp_path).load(path)
