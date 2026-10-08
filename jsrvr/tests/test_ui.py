from unittest.mock import AsyncMock

import pytest
from textual.widgets import Button, DataTable, Input, TabbedContent

from remem.app import RememApp
from remem.config import Config
from remem.demo import DemoService
from remem.models import Device
from remem.service import Service
from remem.widgets.dialogs import ConfirmUnload


async def test_dashboard_watch_hex_region_and_unload_cancel(tmp_path):
    config = Config(captures=tmp_path)
    app = RememApp(config, demo=True)
    async with app.run_test(size=(140, 48)) as pilot:
        await pilot.pause(0.2)
        assert app.service.state.loaded
        assert app.query_one("#region-table", DataTable).row_count == 5
        assert app.query_one("#known-table", DataTable).row_count == 3
        app.watching = False
        app.action_tab("hex")
        await app.read_hex()
        assert app.query_one("#hex-table", DataTable).row_count == 4
        app.action_region(3)
        await pilot.pause(0.1)
        assert app.service.state.region.region == 3
        assert app.query_one("#hex-table", DataTable).row_count == 0
        assert app.query_one("#known-table", DataTable).row_count == 0
        await app.select_region(2)
        app.confirm_unload()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmUnload)
        await pilot.press("escape")
        await pilot.pause()
        assert app.service.state.loaded
        app.action_tab("watch")
        app.query_one("#watch-offset", Input).value = "0x100"
        app.edit_watch(True)
        assert any(c.offset == 256 for c in app.service.watches)
        app.edit_watch(False)
        assert not any(c.offset == 256 for c in app.service.watches)
        await app.unload_module()
        await app.auto_load_if_needed()
        assert not app.service.state.loaded  # Periodic checks must respect explicit unload.
        await app.load_module()
        assert app.service.state.loaded
    # Exiting the TUI leaves the synthetic module loaded; no unload lifecycle hook.
    assert app.service.state.loaded


async def test_capture_diff_candidates_neighborhood(tmp_path):
    config = Config(captures=tmp_path)
    service = DemoService(config)
    service.auto_toggle = False
    app = RememApp(config, demo=True, service=service)
    async with app.run_test(size=(140, 48)) as pilot:
        await pilot.pause(0.1)
        app.watching = False
        for n in range(1, 4):
            for kind in ("OFF", "ON"):
                service.off = kind == "OFF"
                app.query_one("#capture-label", Input).value = f"{kind}{n}"
                await app.capture()
        assert app.query_one("#snapshot-table", DataTable).row_count == 6
        await app.compare()
        assert app.query_one("#diff-table", DataTable).row_count == 3
        await app.find_candidates()
        assert app.query_one("#diff-table", DataTable).row_count == 3
        await app.show_neighborhood()
        assert app.query_one("#neighborhood-table", DataTable).row_count == 5
        await app.kernel_logs()
        assert app.query_one("#capture", Button).label == "Capture snapshot"


async def test_watch_preserves_cursor_and_last_transition(tmp_path):
    config = Config(captures=tmp_path)
    service = DemoService(config)
    service.auto_toggle = False
    app = RememApp(config, demo=True, service=service)
    async with app.run_test(size=(140, 48)) as pilot:
        await pilot.pause(0.1)
        app.watching = False
        await app.workers.wait_for_complete()
        service.off = True
        await app.sample()
        app.action_tab("watch")
        await pilot.pause(0.1)
        table = app.query_one("#watch-table", DataTable)
        table.move_cursor(row=2)
        service.off = False
        await app.sample()
        await app.sample()  # Same value: last transition should remain visible.
        assert table.cursor_row == 2
        assert app.transitions[0xFC04].previous == 0x40
        assert app.transitions[0xFC04].current == 0x00
        assert app.transitions[0xFC04].xor == 0x40


@pytest.mark.parametrize("size", [(100, 35), (80, 24)])
async def test_small_terminal_navigation(tmp_path, size):
    app = RememApp(Config(captures=tmp_path), demo=True)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.1)
        app.set_focus(None)
        await pilot.press("w")
        await pilot.pause(0.1)
        assert app.query_one("#tabs", TabbedContent).active == "watch"
        await pilot.press("h")
        await pilot.pause(0.1)
        assert app.query_one("#tabs", TabbedContent).active == "hex"


@pytest.mark.parametrize("devices", [[], [Device("A", "device"), Device("B", "device")]])
async def test_zero_devices_and_explicit_multi_device_selection(tmp_path, devices):
    service = Service(Config(captures=tmp_path))
    service.devices = AsyncMock(return_value=devices)
    service.connect = AsyncMock()
    service.refresh = AsyncMock()
    app = RememApp(service.config, service=service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause(0.1)
        await app.workers.wait_for_complete()
        service.connect.assert_not_awaited()
        assert app.query_one("#load", Button).disabled
        if devices:
            from textual.widgets import Select

            app.query_one("#devices", Select).value = "B"
            await pilot.pause(0.1)
            await app.workers.wait_for_complete()
            service.connect.assert_awaited_once_with("B")
