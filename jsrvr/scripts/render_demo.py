"""Render real Textual screens for visual review, without an Android device."""

import asyncio
import os
import tempfile
from pathlib import Path

from textual.widgets import DataTable

from remem.app import RememApp
from remem.config import Config
from remem.demo import DemoService


async def render():
    # Preview actual colors independently of the automation runner's NO_COLOR.
    os.environ.pop("NO_COLOR", None)
    output = Path("doc/previews")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="remem-preview-") as temporary:
        config = Config(captures=Path(temporary))
        service = DemoService(config)
        service.auto_toggle = False
        for n in range(1, 4):
            for kind in ("OFF", "ON"):
                service.off = kind == "OFF"
                await service.capture(f"{kind}{n}")
        app = RememApp(config, demo=True, service=service)
        async with app.run_test(size=(140, 48)) as pilot:
            await pilot.pause(0.2)
            app.watching = False
            service.off = True
            await app.sample()
            app.watching = False
            app.save_screenshot("overview.svg", path=str(output))
            service.off = False
            await app.sample()
            app.watching = False
            app.action_tab("watch")
            await pilot.pause(0.35)
            app.save_screenshot("watch.svg", path=str(output))
            app.action_tab("hex")
            await app.read_hex()
            await pilot.pause(0.35)
            app.save_screenshot("hex.svg", path=str(output))
            app.action_tab("analysis")
            await app.find_candidates()
            await app.show_neighborhood()
            await pilot.pause(0.35)
            app.save_screenshot("analysis.svg", path=str(output))
            app.query_one("#neighborhood-table", DataTable).scroll_visible()
            await pilot.pause(0.35)
            app.save_screenshot("neighborhood.svg", path=str(output))
        for width, height in ((100, 35), (80, 24)):
            app = RememApp(config, demo=True)
            async with app.run_test(size=(width, height)) as pilot:
                await pilot.pause(0.2)
                app.save_screenshot(f"overview-{width}.svg", path=str(output))


if __name__ == "__main__":
    asyncio.run(render())
