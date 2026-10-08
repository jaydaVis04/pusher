import asyncio
import json
import time
import traceback
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from .candidates import Finding, analyze_candidates, neighborhood
from .config import Config
from .demo import DemoService
from .diff import FILTERS, Change, changed_bits, diff_bytes
from .models import Region, RememError, WatchSample, parse_number
from .service import Service
from .snapshots import compatible
from .widgets.address_map import AddressMap
from .widgets.dialogs import ConfirmUnload, HelpScreen
from .widgets.hex_view import fill_hex

ADDRESS = "#73c9ec"
CHANGED = "#d6a0e7"
MUTED = "#72869a"


class RememApp(App):
    TITLE = "remem"
    SUB_TITLE = "READ-ONLY SHARED MEMORY WORKBENCH"
    CSS_PATH = "app.tcss"
    AUTO_FOCUS = "#refresh"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        *[Binding(str(n), f"region({n})", f"R{n}", show=False) for n in range(1, 6)],
        Binding("w", "tab('watch')", "Watch"),
        Binding("h", "tab('hex')", "Hex"),
        Binding("c", "tab('captures')", "Capture"),
        Binding("d", "tab('analysis')", "Diff"),
        Binding("l", "tab('logs')", "Logs"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, config: Config, demo: bool = False, service: Service | None = None):
        super().__init__()
        self.register_theme(
            Theme(
                name="remem",
                primary=ADDRESS,
                secondary="#a5b7c9",
                accent=ADDRESS,
                foreground="#dde7f0",
                background="#0c111a",
                surface="#121b27",
                panel="#121b27",
                success="#8bcaa1",
                warning="#e7bb73",
                error="#ef9292",
                dark=True,
            )
        )
        self.theme = "remem"
        self.config = config
        self.demo = demo
        self.pending_logs: list[str] = []
        self.service = service or (
            DemoService(config, self.log_message) if demo else Service(config, self.log_message)
        )
        self.watching = True
        self.sampling = False
        self.interval = config.interval_ms / 1000
        self.next_sample = 0.0
        self.flashes: dict[int, float] = {}
        self.transitions: dict[int, WatchSample] = {}
        self.latest: list[WatchSample] = []
        self.selected_offset = 0xFC04
        self.hex_previous: tuple[int, int, int, bytes] | None = None
        self.analysis_region: Region | None = None
        self.findings: dict[int, Finding] = {}
        self.device_options: tuple = ()
        self.status_busy = False
        self.auto_attempted: set[tuple[str, str]] = set()
        self.last_background_error = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Select([], prompt="Select Android device", id="devices")
            yield Button("Refresh", id="refresh")
            yield Button("Load module", id="load", variant="primary", disabled=True)
            yield Button("Unload…", id="unload", variant="error", disabled=True)
        yield Static(
            "DEMO · synthetic data · no ADB commands"
            if self.demo
            else "Waiting for Android device…",
            id="connection",
        )
        with TabbedContent(initial="overview", id="tabs"):
            with TabPane("Overview", id="overview"):
                with VerticalScroll():
                    with Horizontal(id="summary"):
                        yield Static(
                            "DEVICE\nConnecting…", id="device-status", classes="instrument"
                        )
                        yield Static(
                            "MODULE / CURRENT REGION\nWaiting…",
                            id="module-status",
                            classes="instrument",
                        )
                    yield Label("KNOWN CANDIDATES  /  LIVE OBSERVATIONS", classes="section-title")
                    yield DataTable(id="known-table", cursor_type="row")
                    yield Static(
                        "OFF / ON is an observed correlation, not a semantic guarantee.",
                        classes="hint",
                    )
                    yield Label(
                        "REGIONS  /  SELECT TO SWITCH WITHOUT RELOADING", classes="section-title"
                    )
                    yield DataTable(id="region-table", cursor_type="row")
                    with Horizontal(classes="controls"):
                        yield Input("0xfc04", placeholder="Exact address offset", id="map-offset")
                        yield Button("Map offset", id="map")
                    yield AddressMap(id="address-map", classes="instrument")
            with TabPane("Live watch", id="watch"):
                with Vertical():
                    with Horizontal(classes="controls"):
                        yield Input("0xfc04", placeholder="Offset", id="watch-offset")
                        yield Button("Add", id="watch-add", variant="primary")
                        yield Button("Remove", id="watch-remove")
                        yield Select(
                            [
                                (f"{n} ms", n)
                                for n in sorted({100, 250, 500, 1000, self.config.interval_ms})
                            ],
                            value=self.config.interval_ms,
                            allow_blank=False,
                            id="interval",
                        )
                        yield Button("Pause", id="watch-toggle")
                    yield Static("Waiting for samples…", id="watch-status", classes="hint")
                    yield DataTable(id="watch-table", cursor_type="row")
                    yield AddressMap(id="watch-map", classes="instrument")
            with TabPane("Hex reader", id="hex"):
                with Vertical():
                    with Horizontal(classes="controls"):
                        yield Select(
                            [(f"Region {n}", n) for n in range(1, 6)],
                            value=self.config.default_region,
                            allow_blank=False,
                            id="hex-region",
                        )
                        yield Input("0xfbe0", placeholder="Offset", id="hex-offset")
                        yield Input("64", placeholder="Length", id="hex-length")
                        yield Button("Read", id="hex-read", variant="primary")
                    yield Static(
                        "Select a row, or map an exact byte on Overview. Cyan = selected; magenta = changed.",
                        id="hex-status",
                        classes="hint",
                    )
                    yield DataTable(id="hex-table", cursor_type="row")
                    yield AddressMap(id="hex-map", classes="instrument")
            with TabPane("Captures", id="captures"):
                with VerticalScroll():
                    yield Label("CAPTURE CURRENT REGION", classes="section-title")
                    with Horizontal(classes="controls"):
                        yield Input("OFF1", placeholder="Snapshot label", id="capture-label")
                        yield Button("Capture snapshot", id="capture", variant="primary")
                        yield Button("Rescan files", id="rescan")
                    with Horizontal(classes="controls"):
                        for label in ("OFF1", "ON1", "OFF2", "ON2", "OFF3", "ON3"):
                            yield Button(label, id=f"label-{label}", classes="label-button")
                    yield Static(
                        "Captures include boot, region bases, timestamp, label, and SHA-256.\n"
                        "Shared memory keeps changing during capture; captures are sequential, not atomic.",
                        classes="hint",
                    )
                    yield DataTable(id="snapshot-table", cursor_type="row")
                    yield Static(str(self.config.captures), id="capture-status", classes="hint")
            with TabPane("Diff / candidates", id="analysis"):
                with VerticalScroll():
                    yield Label("TWO-CAPTURE DIFF", classes="section-title")
                    with Horizontal(classes="controls"):
                        yield Select([], prompt="Old / OFF capture", id="diff-old")
                        yield Select([], prompt="New / ON capture", id="diff-new")
                        yield Select(
                            [(f, f) for f in FILTERS],
                            value="all",
                            allow_blank=False,
                            id="diff-filter",
                        )
                        yield Button("Compare", id="compare", variant="primary")
                    yield Label("REPEATABLE OFF / ON EXPERIMENT", classes="section-title")
                    for pair in range(1, 4):
                        with Horizontal(classes="controls"):
                            yield Select([], prompt=f"OFF{pair}", id=f"off-{pair}")
                            yield Select([], prompt=f"ON{pair}", id=f"on-{pair}")
                    with Horizontal(classes="controls"):
                        yield Button("Find candidates", id="find-candidates", variant="primary")
                        yield Input(
                            "0xfc04", placeholder="Neighborhood center", id="neighbor-offset"
                        )
                        yield Select(
                            [(f"±{r} bytes", r) for r in (16, 32, 64, 128)],
                            value=32,
                            allow_blank=False,
                            id="neighbor-radius",
                        )
                        yield Button("Neighborhood", id="neighborhood")
                    yield Static(
                        "Select capture pairs to begin. Results show up to 1,000 rows; counts include all matches.",
                        id="analysis-status",
                        classes="hint",
                    )
                    yield DataTable(id="diff-table", cursor_type="row")
                    yield AddressMap(id="analysis-map", classes="instrument")
                    yield Static(
                        "Aligned patterns appear when a candidate row is selected.",
                        id="pattern-status",
                        classes="hint",
                    )
                    yield DataTable(id="neighborhood-table", cursor_type="row")
            with TabPane("Logs", id="logs"):
                with Vertical():
                    with Horizontal(classes="controls"):
                        yield Button("Refresh kernel diagnostics", id="kernel-logs")
                        yield Button("Clear command log", id="clear-logs")
                    yield Label("ADB / OPERATIONS", classes="section-title")
                    yield RichLog(id="command-log", wrap=True, markup=False, max_lines=1500)
                    yield Label("KERNEL DIAGNOSTICS  /  re_mem ONLY", classes="section-title")
                    yield RichLog(id="kernel-log", wrap=True, markup=False, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        columns = {
            "known-table": ("Offset", "Value", "Binary", "Observation / change"),
            "region-table": ("Region", "Size", "MD base", "AP physical", "AP virtual"),
            "watch-table": (
                "Offset",
                "Current",
                "Previous state",
                "XOR",
                "Binary",
                "Changed bits",
                "Change/sample UTC",
                "Observation",
            ),
            "hex-table": ("Offset", "Hex", "ASCII"),
            "snapshot-table": ("Label", "Region", "Size", "Timestamp (UTC)", "File"),
            "diff-table": (
                "Offset",
                "OFF / old",
                "ON / new",
                "XOR",
                "Bits",
                "MD",
                "AP physical",
                "AP virtual",
                "Rank / nearby",
            ),
            "neighborhood-table": ("Offset", "ON hex (magenta = changed)", "ASCII"),
        }
        for widget_id, headers in columns.items():
            table = self.query_one(f"#{widget_id}", DataTable)
            table.cursor_foreground_priority = "renderable"
            if widget_id == "diff-table":
                widths = (10, 9, 9, 6, 15, 18, 18, 18, 20)
                for label, width in zip(headers, widths, strict=True):
                    table.add_column(label, width=width)
            else:
                table.add_columns(*headers)
        for message in self.pending_logs:
            self.query_one("#command-log", RichLog).write(Text(message))
        self.pending_logs.clear()
        self.set_interval(0.05, self.poll)
        if not self.demo:
            self.set_interval(5, self.poll_status)
        self.spawn(self.startup())
        self.spawn(self.rescan())

    def log_message(self, message: str) -> None:
        if not self.is_running or not self.query("#command-log"):
            self.pending_logs.append(message)
            return
        self.query_one("#command-log", RichLog).write(Text(message))
        if message.startswith(("RESOLVED", "INSERTING")):
            self.query_one("#connection", Static).update(Text(message, style="bold #e7bb73"))
            self.notify(message, severity="warning", timeout=8)

    def spawn(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        self.run_worker(self.guarded(coroutine), exit_on_error=False)

    async def guarded(self, coroutine) -> None:
        try:
            await coroutine
        except asyncio.CancelledError:
            raise
        except (RememError, OSError, ValueError) as exc:
            self.log_message(f"ERROR: {exc}")
            self.notify(str(exc), severity="error", timeout=8)
            self.query_one("#connection", Static).update(Text(str(exc), style="#ef9292"))
        except Exception as exc:
            self.log_message("UNEXPECTED ERROR: " + traceback.format_exc())
            self.notify(f"Unexpected error: {exc}. See Logs for details.", severity="error")

    async def startup(self) -> None:
        devices = await self.service.devices()
        options = [(f"{d.serial} · {d.model} · {d.state}", d.serial) for d in devices]
        self.device_options = tuple(options)
        selector = self.query_one("#devices", Select)
        selector.set_options(options)
        available = [d.serial for d in devices if d.state == "device"]
        preferred = self.service.adb.serial
        if preferred:
            if preferred not in available:
                raise RememError(f"Configured device {preferred} is disconnected or unauthorized")
            selector.value = preferred
        elif len(available) == 1:
            selector.value = available[0]
        elif not available:
            self.render_status()
            raise RememError(
                "No authorized ADB device. Connect the phone and approve USB debugging."
            )
        else:
            self.query_one("#connection", Static).update(
                "Multiple devices detected · select a serial above"
            )

    @on(Select.Changed, "#devices")
    async def select_device(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self.spawn(self.connect(str(event.value)))

    async def connect(self, serial: str) -> None:
        self.latest.clear()
        self.flashes.clear()
        self.transitions.clear()
        self.hex_previous = None
        self.query_one("#hex-table", DataTable).clear()
        await self.service.connect(serial)
        await self.refresh_status()
        await self.auto_load_if_needed()

    async def auto_load_if_needed(self) -> None:
        state = self.service.state
        key = (state.serial, state.boot_id)
        if state.root and not state.loaded and not state.error and key not in self.auto_attempted:
            self.auto_attempted.add(key)
            await self.load_module()

    def poll_status(self) -> None:
        if not self.status_busy and not self.sampling and not self.service.lock.locked():
            self.status_busy = True
            self.spawn(self.background_status())

    async def background_status(self) -> None:
        try:
            if not self.service.adb.serial:
                await self.startup()
            else:
                devices = await self.service.devices()
                options = [(f"{d.serial} · {d.model} · {d.state}", d.serial) for d in devices]
                if tuple(options) != self.device_options:
                    self.device_options = tuple(options)
                    selector = self.query_one("#devices", Select)
                    with self.prevent(Select.Changed):
                        selector.set_options(options)
                        if self.service.adb.serial in [d.serial for d in devices]:
                            selector.value = self.service.adb.serial
                await self.refresh_status()
                await self.auto_load_if_needed()
            self.last_background_error = ""
        except (RememError, OSError) as exc:
            message = str(exc)
            if message != self.last_background_error:
                self.log_message("STATUS: " + message)
                self.last_background_error = message
            self.query_one("#connection", Static).update(Text(message, style="#e7bb73"))
        finally:
            self.status_busy = False

    async def refresh_status(self, auto_load: bool = False) -> None:
        old_identity = (
            self.service.state.serial,
            self.service.state.boot_id,
            self.service.state.region,
        )
        try:
            await self.service.refresh(auto_load=auto_load)
        finally:
            new_identity = (
                self.service.state.serial,
                self.service.state.boot_id,
                self.service.state.region,
            )
            if new_identity != old_identity:
                self.latest.clear()
                self.flashes.clear()
                self.transitions.clear()
                self.hex_previous = None
                self.query_one("#hex-table", DataTable).clear()
            self.render_status()
        state = self.service.state
        if state.error:
            raise RememError(state.error)
        if state.loaded and state.region:
            regions = await self.service.regions()
            table = self.query_one("#region-table", DataTable)
            table.clear()
            available = {r.region: r for r in regions}
            for n in range(1, 6):
                region = available.get(n)
                if region:
                    table.add_row(
                        f"{'●' if n == state.region.region else ' '} {n}",
                        f"0x{region.size:X}",
                        *[
                            Text(f"0x{v:X}", style=ADDRESS)
                            for v in (region.md_phys, region.ap_phys, region.ap_virt)
                        ],
                        key=str(n),
                    )
                else:
                    table.add_row(str(n), "unavailable", "—", "—", "—", key=str(n))

    def render_status(self) -> None:
        state = self.service.state
        region = state.region
        text = Text()
        text.append("DEVICE\n", style="bold")
        text.append(f"{state.serial or 'No device selected'} · {state.model}\n", style="#dde7f0")
        text.append(
            f"ADB {'CONNECTED' if state.connected else 'DISCONNECTED'}  ·  "
            f"Root {'YES' if state.root else 'NO'}\n",
            style="#8bcaa1" if state.connected and state.root else "#e7bb73",
        )
        text.append(
            f"Boot ID  {state.boot_id or '—'}\nKernel   {state.kernel or '—'}", style="#a5b7c9"
        )
        self.query_one("#device-status", Static).update(text)
        text = Text()
        text.append("MODULE / CURRENT REGION\n", style="bold")
        text.append(
            f"Module {'LOADED' if state.loaded else 'NOT LOADED'}  ·  "
            f"/dev/re_mem {'PRESENT' if state.dev_present else 'MISSING'}\n",
            style="#8bcaa1" if state.loaded and state.dev_present else "#e7bb73",
        )
        if region:
            text.append(f"Region {region.region}  ·  0x{region.size:X} bytes\n", style="#dde7f0")
            text.append(
                f"MD  0x{region.md_phys:X}   AP  0x{region.ap_phys:X}\n"
                f"AP virtual  0x{region.ap_virt:X}",
                style=ADDRESS,
            )
        self.query_one("#module-status", Static).update(text)
        if not state.error:
            message = (
                "DEMO · synthetic data · no ADB commands"
                if self.demo
                else (
                    f"{'● Connected' if state.connected else '○ Disconnected'}  ·  "
                    f"{state.serial or 'select device'}  ·  read-only shared memory  ·  module persists on quit"
                )
            )
            self.query_one("#connection", Static).update(
                Text(message, style="#8bcaa1" if state.connected else MUTED)
            )
        else:
            self.query_one("#connection", Static).update(Text(state.error, style="#ef9292"))
        self.query_one("#unload", Button).disabled = not state.loaded
        self.query_one("#load", Button).disabled = not state.root or state.loaded
        if not region:
            self.query_one("#region-table", DataTable).clear()
        else:
            self.query_one("#hex-region", Select).value = region.region
        for widget in ("address-map", "watch-map", "hex-map"):
            self.query_one(f"#{widget}", AddressMap).show_address(region, self.selected_offset)
        self.render_samples()

    def poll(self) -> None:
        now = time.monotonic()
        expired = [offset for offset, until in self.flashes.items() if until <= now]
        for offset in expired:
            del self.flashes[offset]
        if expired:
            self.render_samples()
        if (
            not self.watching
            or self.sampling
            or now < self.next_sample
            or not self.service.state.region
            or self.service.state.error
            or self.service.lock.locked()
        ):
            return
        self.sampling = True
        self.spawn(self.sample())

    async def sample(self) -> None:
        start = time.monotonic()
        try:
            self.latest = await self.service.sample()
            for sample in self.latest:
                if sample.xor:
                    self.transitions[sample.offset] = sample
                    self.flashes[sample.offset] = time.monotonic() + 1.5
                    self.log_message(
                        f"CHANGE r{self.service.require_region().region}+0x{sample.offset:X}: "
                        f"0x{sample.previous:02X} → 0x{sample.current:02X} "
                        f"XOR 0x{sample.xor:02X} bits {changed_bits(sample.xor)}"
                    )
            self.render_samples()
            elapsed = time.monotonic() - start
            self.query_one("#watch-status", Static).update(
                f"LIVE · target {self.interval * 1000:.0f} ms · last read {elapsed * 1000:.0f} ms · "
                f"{len(self.latest)} offsets · sequential samples"
            )
        except (RememError, OSError) as exc:
            self.watching = False
            self.query_one("#watch-toggle", Button).label = "Resume"
            self.query_one("#watch-status", Static).update(Text(f"PAUSED · {exc}", style="#ef9292"))
            self.latest.clear()
            self.transitions.clear()
            self.service.previous.clear()
            self.render_samples()
            self.log_message(f"WATCH ERROR: {exc}")
            await self.refresh_status(auto_load=False)
        finally:
            self.sampling = False
            self.next_sample = max(start + self.interval, time.monotonic())

    def render_samples(self) -> None:
        if not self.query("#known-table"):
            return
        known, watch = (self.query_one(f"#{n}", DataTable) for n in ("known-table", "watch-table"))
        region = self.service.state.region
        if not region:
            known.clear()
            watch.clear()
            return
        known_rows: dict[str, tuple[Any, ...]] = {}
        watch_rows: dict[str, tuple[Any, ...]] = {}
        by_offset = {s.offset: s for s in self.latest}
        for candidate in sorted(self.service.watches, key=lambda c: c.offset):
            if candidate.region != region.region:
                continue
            sample = by_offset.get(candidate.offset)
            if sample is None:
                known_rows[str(candidate.offset)] = (
                    f"0x{candidate.offset:X}",
                    "—",
                    "—",
                    candidate.name,
                )
                continue
            style = CHANGED if self.flashes.get(sample.offset, 0) > time.monotonic() else "#dde7f0"
            observation = (
                candidate.correlation(sample.current)
                if candidate.off_value is not None
                else candidate.name
            )
            if sample.offset == 0xFC04 and region.region == 2:
                observation = f"bit 6 = {(sample.current >> 6) & 1} · {observation}"
            transition = self.transitions.get(sample.offset, sample)
            bits = ", ".join(str(b) for b in changed_bits(transition.xor)) or "—"
            known_rows[str(sample.offset)] = (
                Text(f"0x{sample.offset:X}", style=ADDRESS),
                Text(f"0x{sample.current:02X}", style=style),
                f"{sample.current:08b}",
                Text(observation, style=style),
            )
            watch_rows[str(sample.offset)] = (
                Text(f"0x{sample.offset:X}", style=ADDRESS),
                Text(f"0x{sample.current:02X}", style=style),
                "—" if transition.previous is None else f"0x{transition.previous:02X}",
                Text(f"0x{transition.xor:02X}", style=style),
                f"{sample.current:08b}",
                Text(bits, style=style),
                transition.timestamp[11:23],
                Text(observation, style=style),
            )
        for table, rows in ((known, known_rows), (watch, watch_rows)):
            # Update in place: polling must not reset cursor position or horizontal scroll.
            for row_key in list(table.rows):
                if row_key.value not in rows:
                    table.remove_row(row_key)
            columns = list(table.columns)
            for key, cells in rows.items():
                if key not in table.rows:
                    table.add_row(*cells, key=key)
                else:
                    for column, cell in zip(columns, cells, strict=True):
                        table.update_cell(key, column, cell)

    @on(Select.Changed, "#interval")
    def change_interval(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self.interval = int(str(event.value)) / 1000

    @on(Button.Pressed)
    def button(self, event: Button.Pressed) -> None:
        name = event.button.id or ""
        actions = {
            "refresh": self.action_refresh,
            "load": lambda: self.spawn(self.load_module()),
            "unload": self.confirm_unload,
            "map": self.map_offset,
            "watch-add": lambda: self.edit_watch(True),
            "watch-remove": lambda: self.edit_watch(False),
            "watch-toggle": self.toggle_watch,
            "hex-read": lambda: self.spawn(self.read_hex()),
            "capture": lambda: self.spawn(self.capture()),
            "rescan": lambda: self.spawn(self.rescan()),
            "compare": lambda: self.spawn(self.compare()),
            "find-candidates": lambda: self.spawn(self.find_candidates()),
            "neighborhood": lambda: self.spawn(self.show_neighborhood()),
            "kernel-logs": lambda: self.spawn(self.kernel_logs()),
            "clear-logs": lambda: self.query_one("#command-log", RichLog).clear(),
        }
        try:
            if name.startswith("label-"):
                self.query_one("#capture-label", Input).value = name[6:]
            elif name in actions:
                actions[name]()
        except RememError as exc:
            self.notify(str(exc), severity="error")

    def action_tab(self, name: str) -> None:
        # Clear focus before hiding a pane; otherwise TabPane.Focused can reopen
        # the previous pane while Textual searches for a replacement focus target.
        self.set_focus(None)
        self.query_one("#tabs", TabbedContent).active = name
        targets = {
            "overview": "region-table",
            "watch": "watch-table",
            "hex": "hex-table",
            "captures": "capture-label",
            "analysis": "diff-old",
            "logs": "kernel-logs",
        }
        self.query_one(f"#{targets[name]}").focus()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        self.spawn(self.refresh_or_detect())

    async def refresh_or_detect(self) -> None:
        if not self.service.adb.serial:
            await self.startup()
        else:
            await self.refresh_status()
            await self.auto_load_if_needed()

    def action_region(self, number: int) -> None:
        self.spawn(self.select_region(number))

    async def select_region(self, number: int) -> None:
        await self.service.select(number)
        self.latest.clear()
        self.flashes.clear()
        self.transitions.clear()
        self.hex_previous = None
        self.query_one("#hex-table", DataTable).clear()
        await self.refresh_status()

    async def load_module(self) -> None:
        await self.service.load()
        await self.refresh_status()

    def confirm_unload(self) -> None:
        def answer(confirmed: bool | None) -> None:
            if confirmed:
                self.spawn(self.unload_module())

        self.push_screen(ConfirmUnload(), answer)

    async def unload_module(self) -> None:
        # Explicit unload must win over the periodic automatic insertion policy.
        self.auto_attempted.add((self.service.state.serial, self.service.state.boot_id))
        await self.service.unload(True)
        self.latest.clear()
        self.transitions.clear()
        self.render_status()

    def toggle_watch(self) -> None:
        self.watching = not self.watching
        self.query_one("#watch-toggle", Button).label = "Pause" if self.watching else "Resume"
        self.query_one("#watch-status", Static).update(
            "Sampling…" if self.watching else "PAUSED · values frozen"
        )

    def edit_watch(self, add: bool) -> None:
        offset = parse_number(self.query_one("#watch-offset", Input).value)
        if add:
            self.service.add_watch(offset)
        else:
            self.service.remove_watch(offset)
            self.transitions.pop(offset, None)
        self.latest = [s for s in self.latest if s.offset != offset]
        self.render_samples()

    def map_offset(self) -> None:
        self.selected_offset = parse_number(self.query_one("#map-offset", Input).value)
        self.service.require_region().check(self.selected_offset)
        for name in ("address-map", "watch-map", "hex-map"):
            self.query_one(f"#{name}", AddressMap).show_address(
                self.service.state.region, self.selected_offset
            )

    async def read_hex(self) -> None:
        number = int(str(self.query_one("#hex-region", Select).value))
        if self.service.require_region().region != number:
            await self.select_region(number)
        offset = parse_number(self.query_one("#hex-offset", Input).value)
        length = parse_number(self.query_one("#hex-length", Input).value)
        if length > 65536:
            raise RememError("Hex view limit is 65,536 bytes; use captures for full regions")
        data = await self.service.read(offset, length)
        region = self.service.require_region()
        if not offset <= self.selected_offset < offset + length:
            self.selected_offset = offset
        previous = None
        if self.hex_previous and self.hex_previous[:3] == (region.region, offset, length):
            previous = self.hex_previous[3]
        fill_hex(
            self.query_one("#hex-table", DataTable), data, offset, self.selected_offset, previous
        )
        self.hex_previous = (region.region, offset, length, data)
        self.query_one("#hex-status", Static).update(
            f"REGION {region.region} + 0x{offset:X} · {len(data)} bytes · "
            "cyan selection / magenta change"
        )
        self.query_one("#hex-map", AddressMap).show_address(region, self.selected_offset)

    async def capture(self) -> None:
        button = self.query_one("#capture", Button)
        button.disabled = True
        button.label = "Capturing…"
        try:
            snapshot = await self.service.capture(self.query_one("#capture-label", Input).value)
            self.log_message(
                f"CAPTURE: {snapshot.path} ({snapshot.region.size} bytes, SHA-256 {snapshot.sha256})"
            )
            self.query_one("#capture-status", Static).update(
                Text(f"Saved {snapshot.path.name}", style="#8bcaa1")
            )
            await self.rescan()
        finally:
            button.disabled = False
            button.label = "Capture snapshot"

    async def rescan(self) -> None:
        def index():
            rows = []
            for path in self.service.store.paths():
                try:
                    meta = json.loads(path.with_suffix(".json").read_text())
                    rows.append(
                        (
                            path,
                            meta["label"],
                            meta["region"]["region"],
                            meta["region"]["size"],
                            meta["timestamp"],
                        )
                    )
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    rows.append((path, "INVALID", "—", 0, str(exc)))
            return rows

        rows = await asyncio.to_thread(index)
        table = self.query_one("#snapshot-table", DataTable)
        table.clear()
        options = []
        for path, label, region, size, stamp in rows:
            table.add_row(label, str(region), f"0x{size:X}", stamp, path.name, key=str(path))
            if label != "INVALID":
                options.append((f"{label} · R{region} · {stamp}", str(path)))
        for selector_id in (
            "diff-old",
            "diff-new",
            *[f"{kind}-{n}" for n in range(1, 4) for kind in ("off", "on")],
        ):
            selector = self.query_one(f"#{selector_id}", Select)
            old_value = selector.value
            selector.set_options(options)
            if old_value in [value for _, value in options]:
                selector.value = old_value
            else:
                target = {"diff-old": "OFF1", "diff-new": "ON1"}.get(
                    selector_id, selector_id.replace("-", "").upper()
                )
                match = next((str(path) for path, label, *_ in rows if label == target), None)
                if match:
                    selector.value = match

    def snapshot_path(self, selector_id: str) -> Path:
        value = self.query_one(f"#{selector_id}", Select).value
        if value is Select.BLANK:
            raise RememError("Select all required captures first")
        return Path(str(value))

    async def compare(self) -> None:
        old_path, new_path = self.snapshot_path("diff-old"), self.snapshot_path("diff-new")
        mode = str(self.query_one("#diff-filter", Select).value)
        self.query_one("#analysis-status", Static).update("Comparing captures…")

        def analyze():
            old, new = self.service.store.load(old_path), self.service.store.load(new_path)
            compatible([old, new])
            total = sum(a != b for a, b in zip(old.data, new.data, strict=True))
            results: list[Change] = []
            count = 0
            for change in diff_bytes(old.data, new.data, mode):
                count += 1
                if len(results) < 1000:
                    results.append(change)
            return old.region, total, count, results

        region, total, count, changes = await asyncio.to_thread(analyze)
        self.analysis_region = region
        self.findings = {}
        table = self.query_one("#diff-table", DataTable)
        table.clear()
        for change in changes:
            self.add_change_row(table, change, "—")
        self.query_one("#analysis-status", Static).update(
            f"{total:,} changed bytes · {count:,} match '{mode}' · {len(changes):,} displayed"
        )

    def add_change_row(self, table, change, detail):
        if self.analysis_region is None:
            raise RememError("No analysis region selected")
        md, ap, virtual = self.analysis_region.addresses(change.offset)
        table.add_row(
            Text(f"0x{change.offset:X}", style=ADDRESS),
            f"0x{change.old:02X}",
            Text(f"0x{change.new:02X}", style=CHANGED),
            f"0x{change.xor:02X}",
            ",".join(map(str, change.bits)),
            *[Text(f"0x{v:X}", style=ADDRESS) for v in (md, ap, virtual)],
            detail,
            key=str(change.offset),
        )

    async def find_candidates(self) -> None:
        paths = [self.snapshot_path(f"{kind}-{n}") for n in range(1, 4) for kind in ("off", "on")]
        if len(set(paths)) != 6:
            raise RememError(
                "Select six distinct captures to establish three repeated OFF/ON pairs"
            )
        self.query_one("#analysis-status", Static).update(
            "Analyzing repeated OFF / ON transitions…"
        )

        def analyze():
            captures = [self.service.store.load(path) for path in paths]
            return captures[0].region, analyze_candidates(captures)

        region, report = await asyncio.to_thread(analyze)
        findings = report.findings
        self.analysis_region = region
        self.findings = {f.change.offset: f for f in findings[:1000]}
        table = self.query_one("#diff-table", DataTable)
        table.clear()
        for finding in findings[:1000]:
            self.add_change_row(
                table,
                finding.change,
                f"{finding.score} / " + (", ".join(f"0x{n:X}" for n in finding.nearby) or "—"),
            )
        self.query_one("#analysis-status", Static).update(
            f"INTERESTING CANDIDATES · {report.count:,} stable OFF/ON "
            f"transitions · {len(findings):,} displayed"
        )

    async def show_neighborhood(self) -> None:
        paths = [self.snapshot_path(n) for n in ("diff-old", "diff-new")]
        offset = parse_number(self.query_one("#neighbor-offset", Input).value)
        radius = int(str(self.query_one("#neighbor-radius", Select).value))

        def analyze():
            old, new = [self.service.store.load(path) for path in paths]
            return old.region, neighborhood(old, new, offset, radius)

        region, (start, old, new) = await asyncio.to_thread(analyze)
        fill_hex(self.query_one("#neighborhood-table", DataTable), new, start, offset, old)
        changes = list(diff_bytes(old, new, start=start))
        self.analysis_region = region
        self.query_one("#analysis-map", AddressMap).show_address(region, offset)
        self.query_one("#analysis-status", Static).update(
            f"NEIGHBORHOOD 0x{offset:X} ±{radius} · {len(changes)} changed bytes in {len(new)} bytes · "
            + (
                "only the target byte changed"
                if len(changes) == 1 and changes[0].offset == offset
                else "magenta bytes differ between selected captures"
            )
        )

    @on(DataTable.RowSelected)
    def select_row(self, event: DataTable.RowSelected) -> None:
        value = event.row_key.value
        if value is None:
            return
        if event.data_table.id == "region-table":
            self.action_region(int(value))
        elif event.data_table.id in ("known-table", "watch-table", "hex-table"):
            self.selected_offset = int(value)
            self.query_one("#map-offset", Input).value = f"0x{self.selected_offset:X}"
            self.query_one("#watch-offset", Input).value = f"0x{self.selected_offset:X}"
            for name in ("address-map", "watch-map", "hex-map"):
                self.query_one(f"#{name}", AddressMap).show_address(
                    self.service.state.region, self.selected_offset
                )
        elif event.data_table.id == "diff-table":
            offset = int(value)
            self.query_one("#neighbor-offset", Input).value = f"0x{offset:X}"
            self.query_one("#analysis-map", AddressMap).show_address(self.analysis_region, offset)
            finding = getattr(self, "findings", {}).get(offset)
            self.query_one("#pattern-status", Static).update(
                " · ".join(finding.patterns)
                if finding
                else "Select repeated candidates for aligned word patterns"
            )

    @on(Input.Submitted)
    def submit_input(self, event: Input.Submitted) -> None:
        if event.input.id in ("hex-offset", "hex-length"):
            self.spawn(self.read_hex())
        elif event.input.id == "watch-offset":
            try:
                self.edit_watch(True)
            except RememError as exc:
                self.notify(str(exc), severity="error")

    def on_resize(self, event) -> None:
        self.set_class(event.size.width < 115, "compact")

    async def kernel_logs(self) -> None:
        output = await self.service.kernel_logs()
        log = self.query_one("#kernel-log", RichLog)
        log.clear()
        log.write(Text(output or "No re_mem kernel messages"))
