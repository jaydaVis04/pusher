from io import StringIO
from unittest.mock import AsyncMock

import pytest
from rich.console import Console
from test_logic import BOOT, INFO

from remem.cli import connect, execute, main, parser
from remem.config import Config
from remem.models import Device, RememError
from remem.regions import parse_info
from remem.service import Service
from remem.snapshots import SnapshotStore


async def test_cli_requires_selection_for_multiple_devices():
    service = Service(Config())
    service.devices = AsyncMock(return_value=[Device("A", "device"), Device("B", "device")])
    service.connect = AsyncMock()
    service.refresh = AsyncMock()
    with pytest.raises(RememError, match="--serial"):
        await connect(service, None)
    service.connect.assert_not_awaited()
    await connect(service, "B", auto_load=False)
    service.connect.assert_awaited_once_with("B")
    service.refresh.assert_awaited_once_with(auto_load=False)


async def test_offline_cli_diff_and_candidates(tmp_path):
    region = parse_info(INFO)
    store = SnapshotStore(tmp_path)
    for pair in range(1, 4):
        off, on = bytearray(256), bytearray(256)
        off[32] = 0x40
        store.save(bytes(off), region, "serial", BOOT, f"OFF{pair}")
        store.save(bytes(on), region, "serial", BOOT, f"ON{pair}")
    output = StringIO()
    console = Console(file=output, width=160, color_system=None)
    config = Config(captures=tmp_path)
    await execute(parser().parse_args(["diff", "OFF1", "ON1"]), config, console)
    assert "1 changed bytes" in output.getvalue() and "0x20" in output.getvalue()
    output.truncate(0)
    output.seek(0)
    await execute(
        parser().parse_args(["candidates", "OFF1", "ON1", "OFF2", "ON2", "OFF3", "ON3"]),
        config,
        console,
    )
    assert "1 repeated OFF/ON candidates" in output.getvalue()


def test_no_arguments_launches_tui(monkeypatch, tmp_path):
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["remem"])
    monkeypatch.setattr("remem.app.RememApp.run", lambda self: calls.append(self))
    main()
    assert len(calls) == 1 and not calls[0].demo
