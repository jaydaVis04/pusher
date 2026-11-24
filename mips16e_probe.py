"""Offline, report-oriented adapter for the reconstructed MIPS16e routine.

Only explicit test memory and one enabled helper stub are emulated.  This is
not MIPS hardware access, a full MIPS interpreter, or modem authentication.
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from mips16e_core import (ENTRY, EXACT, HELPER, HELPER_BYTES, LIMIT, MODIFIED,
                          RETURN_PC, STATE, THUNKS, CoreError, Memory, RoutineCPU)


class EmulationError(Exception):
    pass


class _RegisterView:
    """Named-register adapter over the one authoritative CPU register file."""
    ABI = {"zero": 0, "at": 1, "v0": 2, "v1": 3, "a0": 4, "a1": 5,
           "a2": 6, "a3": 7, "t0": 8, "t1": 9, "t2": 10, "t3": 11,
           "t4": 12, "t5": 13, "t6": 14, "t7": 15, "s0": 16, "s1": 17,
           "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22, "s7": 23,
           "t8": 24, "t9": 25, "k0": 26, "k1": 27, "gp": 28, "sp": 29,
           "fp": 30, "ra": 31}

    def __init__(self, cpu):
        self.cpu = cpu

    def __getitem__(self, name):
        if isinstance(name, int) and not isinstance(name, bool) and 0 <= name < 32:
            return self.cpu.regs[name]
        if isinstance(name, str) and name.lower() in self.ABI:
            return self.cpu.regs[self.ABI[name.lower()]]
        raise KeyError(name)

    def __setitem__(self, name, value):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("register values must be integers")
        if not 0 <= value <= 0xffffffff:
            raise ValueError("register value outside 32-bit space")
        if isinstance(name, int) and not isinstance(name, bool) and 0 <= name < 32:
            index = name
        elif isinstance(name, str) and name.lower() in self.ABI:
            index = self.ABI[name.lower()]
        else:
            raise KeyError(name)
        self.cpu.regs[index] = value
        self.cpu.regs[0] = 0

    def get(self, name, default=None):
        try:
            return self[name]
        except KeyError:
            return default

    def copy(self):
        return {f"r{i}": value for i, value in enumerate(self.cpu.regs)}


def infer_helper(cpu, saved_registers, entry_pc):
    """Classify the observed stub with an explicit value/error ambiguity."""
    changed = {index: (value, cpu.regs[index]) for index, value in enumerate(saved_registers)
               if value != cpu.regs[index]}
    state = cpu.mem.read(cpu.regs[16], 2, "inspect")
    mechanism = "reg-writeback" if changed else "unknown"
    return {"entry_pc": f"0x{entry_pc:08x}", "changed_registers": changed,
            "state": state, "mechanism": mechanism, "confidence": "stub-only",
            "reads_a3": False, "new_abi_claim": False}


class Machine(RoutineCPU):
    """Initialize/check the image once; each run gets explicit clean CPU state."""
    def __init__(self, rom):
        super().__init__(rom)
        self.r = _RegisterView(self)
        self.current_pc = None
        self.current_registers = None
        self.finished = False
        self.frames = []
        self.trace = []
        self.helper_inputs = []
        self.steps = 0

    @property
    def cycle(self):
        return self.instructions

    def snapshot(self):
        result = super().snapshot()
        result.update({"steps": self.steps, "helper_calls": self.helper_calls,
                       "breakpoints": sorted(self.breakpoints), "helper_stub": True})
        return result

    def _bytes(self, pc):
        return self.mem.read(pc, 2, "inspect").to_bytes(2, "big")

    def _read_rom_halfword(self, pc):
        return self._bytes(pc)

    def _decode(self, pc, raw=None):
        """Decode only exact modeled byte locations; projected bytes are not executed."""
        if not isinstance(pc, int) or pc & 1:
            return None
        operations = {0: "addiu sp,-0x20", 2: "sw ra,0x1c(sp)",
                      4: "sw s0,0x18(sp)", 6: "addiu s0,a0,0",
                      8: "lh v0,0(s0)", 0xa: "addiu s2,v0,0",
                      0xc: "addiu s0,a0,0", 0xe: "lh v0,0(s0)",
                      0x10: "adiuw", 0x12: "xor v0,v0", 0x14: "nop",
                      0x16: "skip_zero_if_v0_nonzero", 0x18: "nop",
                      0x1a: "lhu16", 0x1c: "sltu", 0x1e: "skip_zero_if_v0_nonzero",
                      0x20: "save", 0x22: "jal", 0x24: "delay_lui",
                      0x26: "addiu v0,v0,-33152", 0x28: "lhu v1,s2", 0x2a: "lhu v0,s2",
                      0x2c: "addu v0,v0,v1", 0x2e: "sh v0,s0", 0x30: "restore",
                      0x32: "jr ra"}
        if pc == HELPER:
            name, actual = "helper", HELPER_BYTES
        elif pc in THUNKS:
            name, actual = "mov v0,s2", THUNKS[pc]
        elif pc in MODIFIED:
            name, actual = "call_literal", MODIFIED[pc]
        elif pc in EXACT:
            name, actual = operations.get(pc - ENTRY, "exact"), EXACT[pc]
        else:
            return None
        raw = self._bytes(pc) if raw is None else bytes(raw)
        if raw != actual:
            return None
        return {"op": name, "pc": pc, "raw": raw.hex()}

    def replace_entry(self):
        return False

    def _capture_helper_inputs(self):
        self.helper_inputs.append({
            "pc": self.pc, "before": self.r.copy(),
            "memory": {"state_address": self.r["s0"], "state_value": self.mem.u16(self.r["s0"]),
                       "a0": self.r["a0"], "a1": self.r["a1"]},
        })

    def step(self):
        pc = self.pc
        if self.replace_entry():
            self.current_pc = self.pc + 2
            self.current_registers = self.r.copy()
            self.finished = True
            self.result = {"v0": self.r["v0"], "state": 0}
            return []
        if pc == HELPER:
            if not self.helper_enabled:
                raise EmulationError("helper is disabled")
            self._capture_helper_inputs()
            saved = self.r.copy()
            entry_pc = saved[31]
            result = super().step()
            self.helper_inputs[-1].update(infer_helper(self, saved, entry_pc))
            return result
        result = super().step()
        if pc == ENTRY + 0x32 or self.returned:
            self.finished = True
            self.result = {"v0": self.r["v0"], "state": self.mem.u16(self.r["s0"])}
        return result

    def execute(self, count=None):
        raise EmulationError("use run(machine, ...) for fully initialized, bounded execution")


def prepare(machine, a0=0, state=0, state_address=STATE, a3_value=0x1000, **kwargs):
    if kwargs:
        raise EmulationError(f"unrecognized arguments: {', '.join(sorted(kwargs))}")
    if state_address != STATE:
        raise EmulationError("alternate state addresses require an explicitly mapped initial_sp/state region")
    machine.initialize(a0=a0, arg5=state_address, a3_value=a3_value, state=state)
    machine.r = _RegisterView(machine)
    machine.pc, machine.finished, machine.result = ENTRY, False, None
    machine.current_pc = machine.current_registers = None
    machine.frames, machine.trace, machine.helper_inputs = [], [], []
    machine.instructions = machine.steps = machine.helper_calls = 0


def run(machine, a0=0, state=0, state_address=STATE, limit=LIMIT, **kwargs):
    rom_bytes = kwargs.pop("rom_bytes", b"")
    prepare(machine, a0, state, state_address, **kwargs)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise EmulationError("execution limit must be a nonnegative integer")
    machine.helper_enabled = True
    machine.mem.trace_fetches = True
    try:
        for _ in range(limit):
            if machine.finished or machine.returned:
                break
            machine.step()
        else:
            raise EmulationError("instruction limit reached")
    except CoreError as exception:
        raise EmulationError(str(exception)) from exception
    machine.steps = machine.instructions
    machine.trace.append({"pc": RETURN_PC, "breakpoints": sorted(machine.breakpoints),
                          "returned": machine.returned, "finished": machine.finished})
    logs = [dict(entry, address=f"0x{entry['address']:08x}") for entry in machine.mem.accesses]
    digest = hashlib.sha256(rom_bytes).hexdigest()
    return {
        "scenario": {"a0": a0, "state": state, "state_address": f"0x{state_address:08x}"},
        "result": {"v0": f"0x{machine.r['v0']:08x}", "state": f"0x{machine.mem.u16(state_address):04x}",
                   "sp": f"0x{machine.r['sp']:08x}"},
        "frames": machine.frames, "steps": machine.steps, "helper_calls": machine.helper_calls,
        "trace": machine.trace, "accesses": logs, "registers": machine.registers(),
        "helper_inputs": machine.helper_inputs, "input_sha256": digest, "rom_sha256": digest,
    }


def exhaustive(rom, limit=LIMIT):
    return [run(Machine(rom), a0, state, rom_bytes=rom, limit=limit)
            for a0 in (0, 1, 2, 0xffffffff)
            for state in (0, 0x1000, 0x1003, 0x7fff, 0xffff)]


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(exhaustive(args.rom.read_bytes()), indent=2, sort_keys=True))
    except (OSError, CoreError, EmulationError) as exception:
        parser.exit(1, f"offline error: {exception}\n")


if __name__ == "__main__":
    main()
