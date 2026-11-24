"""Offline interactive debugger for the one exactly modeled MIPS16e routine.

Reads only an explicit, correctly mapped test image. No modem or hardware I/O.
"""
import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shlex
import sys
from mips16e_core import (BASE, ENTRY, EXACT, HELPER, CoreError, Memory,
                         RoutineCPU, NAMES, Instruction, number)


class Debugger:
    """Small controller sharing routine execution, memory and event records."""
    def __init__(self, rom):
        self.mem = Memory()
        self.cpu = RoutineCPU(self.mem, rom)
        if len(rom) != 0x70000000:
            raise CoreError("test ROM must map 0x90000000 through 0x70000000")
        self.mem.map(BASE, 0x70000000, rom, False, "ROM")
        self.mem.map(0x70000000, 0x10000, name="stack")
        self.mem.map(0x70100000, 0x10000, name="data")
        self.cpu.initialize()
        self.breakpoints = set()
        self.watches = []
        self.trace = []
        self.command_count = 0
        self.steps = 0
        self.state = "stopped"
        self.reason = "initial stop"

    @property
    def pc(self):
        return self.cpu.pc

    @pc.setter
    def pc(self, value):
        self.cpu.pc = number(value)

    @property
    def regs(self):
        return self.cpu.regs

    @property
    def r(self):
        return self.cpu.regs

    @property
    def returned(self):
        return self.cpu.returned

    @property
    def helper_enabled(self):
        return self.cpu.helper_enabled

    @helper_enabled.setter
    def helper_enabled(self, value):
        self.cpu.helper_enabled = value

    @property
    def helper(self):
        return self.cpu.helper

    def reset(self):
        self.cpu.reset()
        self.cpu.initialize()
        self.command_count = self.steps = 0
        self.state, self.reason = "stopped", "reset"
        self.mem.events.clear()
        self.trace.clear()

    def watch(self, address, size=4):
        point, width = number(address), int(size)
        if width not in (1, 2, 4):
            raise CoreError("watch size must be 1, 2 or 4")
        self.mem.region(point, width)
        self.watches.append((point, width))
        self.mem.watchpoints.add((point, width))

    def step(self):
        if self.returned or self.state == "breakpoint":
            return []
        before = self.cpu.snapshot()
        ins = self.cpu.step()
        self.steps += 1
        self.command_count += 1
        self.trace.append({"pc": f"0x{before['pc']:08x}", "raw": ins.raw.hex(),
                           "before": format_snapshot(before), "after_pc": f"0x{self.pc:08x}"})
        if self.pc == HELPER:
            self.state = "helper"
            self.reason = "helper call reached"
        elif self.returned:
            self.state = "returned"
            self.reason = "routine returned to test return PC"
        else:
            self.state = "stopped"
        return []

    def run(self):
        if self.returned:
            return []
        if self.pc in self.breakpoints:
            self.state, self.reason = "breakpoint", "entry breakpoint"
            return []
        for _ in range(0x1000):
            if self.returned:
                self.state, self.reason = "returned", "routine returned to test return PC"
                break
            if self.pc in self.breakpoints:
                self.state, self.reason = "breakpoint", "breakpoint reached"
                break
            if self.pc == HELPER and not self.helper_enabled:
                self.state, self.reason = "helper", "helper evaluation required"
                break
            self.step()
        else:
            raise CoreError("execution exceeded 4096 instructions")
        return []

    def snapshot(self, ok=True, **extra):
        regs = {name: f"0x{self.cpu.regs[i]:08x}" for i, name in enumerate(NAMES)}
        reply = {"ok": ok, "pc": f"0x{self.pc:08x}", "state": self.state,
                 "status": self.state, "reason": self.reason,
                 "returned": self.returned, "registers": regs,
                 "command_count": self.command_count, "steps": self.steps,
                 "helper_calls": self.cpu.helper_calls, "helper_enabled": self.helper_enabled,
                 "events": [event.as_dict() for event in self.mem.events], "trace": self.trace,
                 "breakpoints": [f"0x{x:08x}" for x in sorted(self.breakpoints)],
                 "watchpoints": [{"address": f"0x{x:08x}", "size": size} for x, size in self.watches]}
        reply.update(extra)
        return reply

    def line(self, command):
        try:
            tokens = shlex.split(command)
            if not tokens:
                raise CoreError("empty command")
            op, args = tokens[0], tokens[1:]
            if op in ("help", "quit", "exit"):
                return self.snapshot(message="offline commands: step continue reset read write set break watch regs help")
            if op in ("step", "s"):
                if args:
                    raise CoreError("step accepts no arguments")
                self.step()
            elif op in ("continue", "run", "c"):
                self.run()
            elif op == "reset":
                self.reset()
            elif op == "regs":
                pass
            elif op == "read":
                if len(args) != 2:
                    raise CoreError("read requires address and size")
                address, size = number(args[0]), int(args[1])
                data = self.mem.read(address, size, "inspect")
                return self.snapshot(address=f"0x{address:08x}", size=size,
                                     value=f"0x{data:x}", bytes=data.to_bytes(size, "little").hex())
            elif op == "write":
                if len(args) != 3:
                    raise CoreError("write requires address, size, value")
                address, size, value = number(args[0]), int(args[1]), int(args[2], 0)
                self.mem.write(address, size, value)
            elif op == "set":
                if len(args) != 3 or args[0] != "reg":
                    raise CoreError("set reg NAME VALUE")
                name = args[1].lower()
                index = int(name[1:]) if name.startswith("r") and name[1:].isdigit() else NAMES.index(name)
                if not 0 <= index < 32:
                    raise CoreError("register index out of range")
                self.cpu.regs[index] = number(args[2]) if index else 0
            elif op == "break":
                if len(args) != 1:
                    raise CoreError("break requires an address")
                point = number(args[0])
                if point & 1 or any(point + size >= 0x900e4358 and point <= 0x900e438b
                                    for size in (2, 4)):
                    base = point & ~3
                    fields = (EXACT.get(base, "0000"), EXACT.get(base + 2, "0000"))
                    raw = bytes.fromhex(fields[0] + fields[1])
                    offset = point - base
                    self.trace.append({"breakpoint": {"offset": offset, "bytes": raw[offset:offset + 2].hex(),
                                                      "extend": point - base, "length": 2}})
                self.breakpoints.add(point)
                self.state = "stopped"
            elif op == "watch":
                if len(args) != 2:
                    raise CoreError("watch requires an address and size")
                self.watch(args[0], args[1])
            elif op == "helper":
                if len(args) != 1 or args[0] not in ("on", "off", "enable", "disable"):
                    raise CoreError("helper on/off")
                self.helper_enabled = args[0] in ("on", "enable")
            elif op == "stopback":
                return self.snapshot(message="per-step only; no unverified reverse execution")
            else:
                raise CoreError(f"unknown command {op!r}")
            return self.snapshot()
        except (CoreError, ValueError) as exc:
            return self.snapshot(False, error=str(exc))


def format_snapshot(snapshot):
    return {"pc": f"0x{snapshot['pc']:08x}", "state": snapshot["state"],
            "returned": snapshot["returned"],
            "registers": {name: f"0x{snapshot['registers'][index]:08x}" for index, name in enumerate(NAMES)},
            "instructions": snapshot["instructions"], "helper_calls": snapshot["helper_calls"]}


def initial(rom):
    return Debugger(rom)


def script(rom, commands):
    controller = Debugger(rom)
    for command in commands:
        yield controller.line(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("offline_rom", type=Path)
    parser.add_argument("--script", action="append", default=[])
    args = parser.parse_args()
    try:
        return_code = 0
        for row in script(args.offline_rom.read_bytes(), args.script):
            print(json.dumps(row, sort_keys=True))
            return_code |= not row["ok"]
        return return_code
    except (OSError, CoreError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
