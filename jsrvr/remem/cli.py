import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .candidates import analyze_candidates, neighborhood
from .config import Config
from .demo import DemoService
from .diff import FILTERS, changed_bits, diff_bytes
from .models import RememError, parse_number
from .service import Service
from .snapshots import compatible


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="remem · read-only Android shared-memory workbench")
    root.add_argument("--config", type=Path, default=Path("config.toml"))
    root.add_argument(
        "--serial", help="Select ADB serial (required when multiple devices are connected)"
    )
    root.add_argument("--demo", action="store_true", help="Synthetic backend; never runs ADB")
    root.add_argument("--verbose", action="store_true", help="Log ADB commands to stderr")
    commands = root.add_subparsers(dest="command")
    commands.add_parser("tui", help="Launch interactive workbench (default)")
    commands.add_parser(
        "status", help="Inspect connection/root/module without inserting"
    ).add_argument("--json", action="store_true")
    commands.add_parser("regions", help="List live available regions")
    commands.add_parser("region", help="Switch region through sysfs").add_argument(
        "number", type=int, choices=range(1, 6)
    )
    read = commands.add_parser("read", help="Bounded read from current region")
    read.add_argument("offset")
    read.add_argument("--length", default="1")
    read.add_argument("--raw", action="store_true", help="Write raw bytes to stdout")
    watch = commands.add_parser("watch", help="Sample selected offsets until Ctrl-C")
    watch.add_argument("offsets", nargs="+")
    watch.add_argument("--interval", type=int, choices=(100, 250, 500, 1000), default=None)
    commands.add_parser("capture", help="Capture full region with provenance").add_argument("label")
    diff = commands.add_parser("diff", help="Compare saved snapshots (labels or exact paths)")
    diff.add_argument("old")
    diff.add_argument("new")
    diff.add_argument("--filter", choices=FILTERS, default="all")
    diff.add_argument("--limit", type=int, default=1000)
    diff.add_argument("--offset", help="Show a neighborhood around this offset")
    diff.add_argument("--radius", type=int, choices=(16, 32, 64, 128), default=32)
    candidates = commands.add_parser("candidates", help="Find repeated stable OFF/ON transitions")
    candidates.add_argument("snapshots", nargs="+", help="OFF1 ON1 OFF2 ON2 [OFF3 ON3 ...]")
    candidates.add_argument("--limit", type=int, default=1000)
    commands.add_parser("logs", help="Filtered re_mem kernel diagnostics")
    commands.add_parser("load", help="Resolve a fresh live symbol and load once if needed")
    commands.add_parser("unload", help="Explicitly unload module (asks for confirmation)")
    return root


def changes_table(changes, region=None) -> Table:
    table = Table("Offset", "Old / OFF", "New / ON", "XOR", "Bits", title="Memory transitions")
    if region:
        for title in ("MD", "AP physical", "AP virtual"):
            table.add_column(title, style="cyan")
    for c in changes:
        addresses = [f"0x{a:X}" for a in region.addresses(c.offset)] if region else []
        table.add_row(
            f"0x{c.offset:X}",
            f"0x{c.old:02X}",
            f"0x{c.new:02X}",
            f"0x{c.xor:02X}",
            ",".join(map(str, c.bits)),
            *addresses,
        )
    return table


async def connect(service: Service, serial: str | None, auto_load=True):
    devices = await service.devices()
    available = [d.serial for d in devices if d.state == "device"]
    chosen = serial or service.config.serial
    if not chosen:
        if len(available) != 1:
            raise RememError(
                "Select --serial; authorized devices: " + (", ".join(available) or "none")
            )
        chosen = available[0]
    if chosen not in available:
        raise RememError(f"Device {chosen} is disconnected/offline/unauthorized")
    await service.connect(chosen)
    await service.refresh(auto_load=auto_load)


async def execute(args, config: Config, console: Console) -> None:
    def log(message):
        if args.verbose or message.startswith(("RESOLVED", "INSERTING", "WARNING")):
            print(message, file=sys.stderr, flush=True)

    service = DemoService(config, log) if args.demo else Service(config, log)
    if args.command in ("diff", "candidates"):
        if args.limit < 1:
            raise RememError("--limit must be positive")
        if args.command == "diff":
            snapshots = [
                service.store.load(service.store.resolve(ref)) for ref in (args.old, args.new)
            ]
            compatible(snapshots)
            old, new = snapshots
            if args.offset is not None:
                start, a, b = neighborhood(old, new, parse_number(args.offset), args.radius)
                changes = list(diff_bytes(a, b, args.filter, start))
                console.print(f"Neighborhood ±{args.radius}: {len(changes)} matching changed bytes")
                console.print(changes_table(changes[: args.limit], old.region))
                return
            count, changes = 0, []
            total = sum(a != b for a, b in zip(old.data, new.data, strict=True))
            for change in diff_bytes(old.data, new.data, args.filter):
                count += 1
                if len(changes) < args.limit:
                    changes.append(change)
            console.print(
                f"{total:,} changed bytes; {count:,} match {args.filter}; {len(changes):,} displayed"
            )
            console.print(changes_table(changes, old.region))
        else:
            paths = [service.store.resolve(ref) for ref in args.snapshots]
            if len(set(p.resolve() for p in paths)) != len(paths):
                raise RememError("Repeated experiment requires distinct capture files")
            snapshots = [service.store.load(path) for path in paths]
            report = analyze_candidates(snapshots, args.limit)
            findings = report.findings
            console.print(
                f"{report.count:,} repeated OFF/ON candidates; ranked boolean, single bit, neighbors, words"
            )
            console.print(
                changes_table([f.change for f in findings[: args.limit]], snapshots[0].region)
            )
            for finding in findings[: args.limit]:
                console.print(
                    f"0x{finding.change.offset:X}: rank {finding.score}; "
                    f"nearby {','.join(hex(n) for n in finding.nearby) or 'none'}; "
                    + "; ".join(finding.patterns)
                )
        return
    await connect(service, args.serial, auto_load=args.command not in ("status", "unload", "logs"))
    if args.command == "status":
        state = asdict(service.state)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            console.print_json(data=state)
        if service.state.error:
            raise RememError(service.state.error)
    elif args.command == "regions":
        regions = await service.regions()
        table = Table("Region", "Size", "MD", "AP physical", "AP virtual")
        for r in regions:
            table.add_row(
                str(r.region),
                f"0x{r.size:X}",
                f"0x{r.md_phys:X}",
                f"0x{r.ap_phys:X}",
                f"0x{r.ap_virt:X}",
            )
        console.print(table)
    elif args.command == "region":
        region = await service.select(args.number)
        console.print(f"Selected region {region.region}; {region.size} bytes")
    elif args.command == "read":
        offset = parse_number(args.offset)
        data = await service.read(offset, parse_number(args.length))
        if args.raw:
            sys.stdout.buffer.write(data)
        else:
            for row in range(0, len(data), 16):
                chunk = data[row : row + 16]
                console.print(
                    f"{offset + row:08X}  "
                    + " ".join(f"{b:02X}" for b in chunk).ljust(47)
                    + "  "
                    + "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                )
            console.print(
                "MD / AP physical / AP virtual: "
                + " / ".join(f"0x{a:X}" for a in service.require_region().addresses(offset))
            )
    elif args.command == "watch":
        service.watches.clear()
        for offset in args.offsets:
            service.add_watch(parse_number(offset))
        interval = (args.interval or config.interval_ms) / 1000
        while True:
            start = asyncio.get_running_loop().time()
            for sample in await service.sample():
                console.print(
                    f"{sample.timestamp}  0x{sample.offset:X}  "
                    f"{'--' if sample.previous is None else f'{sample.previous:02X}'} → "
                    f"{sample.current:02X}  {sample.current:08b}  XOR {sample.xor:02X} "
                    f"bits {changed_bits(sample.xor)}"
                )
            await asyncio.sleep(max(0, interval - (asyncio.get_running_loop().time() - start)))
    elif args.command == "capture":
        snapshot = await service.capture(args.label)
        console.print(str(snapshot.path))
    elif args.command == "logs":
        console.print(await service.kernel_logs(), markup=False)
    elif args.command == "load":
        await service.load()
        console.print("Module loaded; it will remain loaded after remem exits")
    elif args.command == "unload":
        if input("Unload re_mem and stop readers? Type UNLOAD: ") != "UNLOAD":
            console.print("Cancelled")
            return
        await service.unload(True)
        console.print("Module unloaded explicitly")


def main() -> None:
    args = parser().parse_args()
    try:
        config = Config.load(args.config)
        if args.serial:
            config.serial = args.serial
        if args.command in (None, "tui"):
            from .app import RememApp

            RememApp(config, demo=args.demo).run()
        else:
            asyncio.run(execute(args, config, Console()))
    except (RememError, OSError, ValueError) as exc:
        print(f"remem: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
