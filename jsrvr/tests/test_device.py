from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from test_logic import BOOT, INFO

from remem.adb import Adb
from remem.config import Config
from remem.memory import Memory
from remem.models import Device, RememError, Status
from remem.module import Module
from remem.regions import parse_info
from remem.service import Service


@pytest.mark.asyncio
async def test_bounded_read_and_protocol_errors():
    adb = Adb("serial")
    adb.text = AsyncMock(side_effect=[INFO, INFO])
    adb.root = AsyncMock(return_value=b"\x40")
    memory = Memory(adb, Config())
    assert await memory.read(parse_info(INFO), 32, 1) == b"\x40"
    adb.root.assert_awaited_once_with("dd if=/dev/re_mem bs=1 skip=32 count=1", binary=True)
    adb.text = AsyncMock(side_effect=[INFO, INFO.replace("generation=1", "generation=2")])
    with pytest.raises(RememError, match="during read"):
        await memory.read(parse_info(INFO), 32, 1)
    adb.text = AsyncMock(return_value=INFO)
    adb.root = AsyncMock(return_value=b"")
    with pytest.raises(RememError, match="Short"):
        await memory.read(parse_info(INFO), 32, 1)
    adb.root.reset_mock()
    with pytest.raises(RememError):
        await memory.read(parse_info(INFO), 256, 1)
    adb.root.assert_not_awaited()


async def test_cat_fallback_validates_full_region():
    adb = Adb("serial")
    adb.text = AsyncMock(return_value=INFO)
    adb.root = AsyncMock(return_value=bytes(range(256)))
    memory = Memory(adb, Config(read_mode="cat"))
    assert await memory.read(parse_info(INFO), 32, 2) == bytes([32, 33])
    adb.root.assert_awaited_once_with("cat /dev/re_mem", binary=True)
    adb.root = AsyncMock(return_value=bytes(200))
    with pytest.raises(RememError, match="Truncated"):
        await memory.read(parse_info(INFO), 32, 1)


async def test_switch_uses_sysfs_only():
    adb = Adb("serial")
    adb.text = AsyncMock(side_effect=["", INFO])
    module = Module(adb, Config())
    assert (await module.select(2)).region == 2
    commands = [call.args[0] for call in adb.text.await_args_list]
    assert commands == [
        "printf '%s\\n' 2 > /sys/class/misc/re_mem/region",
        "cat /sys/class/misc/re_mem/info",
    ]
    with pytest.raises(RememError):
        await module.select(6)
    with pytest.raises(RememError):
        await module.unload(False)


async def test_load_reuses_existing_module():
    adb = Adb("serial")
    adb.root = AsyncMock()
    module = Module(adb, Config())
    state = Status(
        "serial",
        connected=True,
        root=True,
        loaded=True,
        dev_present=True,
        boot_id=BOOT,
        region=parse_info(INFO),
    )
    module.status = AsyncMock(return_value=state)
    assert await module.load() is state
    adb.root.assert_not_awaited()


async def test_load_verifies_address_and_boot(tmp_path):
    path = tmp_path / "test.ko"
    path.write_bytes(b"fake")
    config = Config(local_path=path, abi_verified=True)
    adb = Adb("serial")
    adb.push = AsyncMock()
    symbol = "ffffff8001234000 T getthisguy"
    adb.text = AsyncMock(side_effect=[symbol, symbol, ""])
    module = Module(adb, config)
    initial = Status("serial", connected=True, root=True, boot_id=BOOT)
    loaded = replace(initial, loaded=True, dev_present=True, region=parse_info(INFO))
    module.status = AsyncMock(side_effect=[initial, loaded])
    module.boot = AsyncMock(return_value=BOOT)
    assert (await module.load()).loaded
    command = adb.text.await_args_list[-1].args[0]
    assert "insmod" in command and "myaddr=0xffffff8001234000" in command
    adb.text = AsyncMock(return_value=symbol)
    module.status = AsyncMock(return_value=initial)
    module.boot = AsyncMock(return_value="00000000-0000-4000-8000-000000000001")
    with pytest.raises(RememError, match="rebooted"):
        await module.load()
    assert not any("insmod" in call.args[0] for call in adb.text.await_args_list)


async def test_load_hidden_or_changed_symbol_never_inserts(tmp_path):
    path = tmp_path / "test.ko"
    path.write_bytes(b"fake")
    adb = Adb("serial")
    adb.push = AsyncMock()
    module = Module(adb, Config(local_path=path, abi_verified=True))
    module.status = AsyncMock(
        return_value=Status("serial", connected=True, root=True, boot_id=BOOT)
    )
    module.boot = AsyncMock(return_value=BOOT)
    for replies in [
        ["0000000000000000 T getthisguy", "2"],
        ["ffffff8001234000 T getthisguy", "ffffff8001234004 T getthisguy"],
    ]:
        adb.text = AsyncMock(side_effect=replies)
        with pytest.raises(RememError):
            await module.load()
        assert not any(
            "insmod" in call.args[0] or "kptr_restrict=" in call.args[0]
            for call in adb.text.await_args_list
        )


async def test_status_offline_and_root_disappears():
    adb = Adb("serial")
    adb.devices = AsyncMock(return_value=[Device("serial", "offline")])
    module = Module(adb, Config())
    assert not (await module.status()).connected
    adb.devices = AsyncMock(return_value=[Device("serial", "device", "Pixel")])
    adb.text = AsyncMock(return_value="uid=2000(shell) gid=2000(shell)")
    state = await module.status()
    assert not state.root and "root" in state.error


async def test_capture_boot_change_discards_data(tmp_path):
    service = Service(Config(captures=tmp_path))
    service.state = Status("serial", root=True, boot_id=BOOT, region=parse_info(INFO))
    service.module.boot = AsyncMock(side_effect=[BOOT, "00000000-0000-4000-8000-000000000001"])
    service.memory.read = AsyncMock(return_value=bytes(256))
    with pytest.raises(RememError, match="rebooted during capture"):
        await service.capture("OFF1")
    assert not list(tmp_path.glob("*.bin"))


async def test_boot_changes_clear_watch_history():
    service = Service(Config())
    service.state = Status("serial", root=True, boot_id=BOOT, region=parse_info(INFO))
    service.previous[(2, 32)] = 64
    service.module.boot = AsyncMock(return_value="00000000-0000-4000-8000-000000000001")
    with pytest.raises(RememError, match="rebooted"):
        await service.sample()
    assert not service.previous
