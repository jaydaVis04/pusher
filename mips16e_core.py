"""Shared, exact-byte, bounded CPU and memory model for the two offline tools.

This is not a general/cycle-accurate MIPS emulator. The SAVE/RESTORE sequence
is modeled per instruction from the verified bytes. Fetches have separate
emulation records and never trigger debugger watchpoints. Initialization writes
can populate read-only ROM and never trigger watchpoints.
"""
from dataclasses import dataclass
from types import MappingProxyType

BASE = 0x90000000
ENTRY = 0x900E4358
HELPER = 0x900DE4FC
STACK = 0x70000000
TOP = STACK + 0x1000
DATA = 0x70100000
STATE = DATA + 0x300
RETURN_PC = 0xDEADBEEC
MASK = 0xFFFFFFFF
NAMES = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
         "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra").split()
REGISTERS = MappingProxyType({name: index for index, name in enumerate(NAMES)})
EXACT = MappingProxyType({
    ENTRY: "08f0e364", ENTRY + 4: "0174", ENTRY + 6: "0a90",
    ENTRY + 8: "0861", ENTRY + 0xa: "0702", ENTRY + 0xc: "40de",
    ENTRY + 0xe: "809f", ENTRY + 0x10: "40a8", ENTRY + 0x12: "09b5",
    ENTRY + 0x14: "51e4", ENTRY + 0x16: "016f", ENTRY + 0x18: "0510",
    ENTRY + 0x1a: "809f", ENTRY + 0x1c: "40a8", ENTRY + 0x1e: "07b5",
    ENTRY + 0x20: "51e4", ENTRY + 0x22: "006f", ENTRY + 0x24: "60183f79",
    ENTRY + 0x28: "0065", ENTRY + 0x2a: "60a8", ENTRY + 0x2c: "69e2",
    ENTRY + 0x2e: "40c8", ENTRY + 0x30: "6364a0e8", ENTRY + 0x32: "a0e8",
})
HELPER_BYTES = bytes.fromhex("03e02000")
LITERALS = MappingProxyType({ENTRY + 0x38: 1, ENTRY + 0x3c: 0x10, ENTRY + 0x40: STATE})
REASONS = frozenset(("inspect", "load", "data", "write", "initialize", "fetch"))


class CoreError(Exception):
    """Expected guest-model or memory error."""


@dataclass(frozen=True)
class Event:
    address: int
    kind: str
    size: int
    old: int
    new: int

    def as_dict(self):
        return {"address": f"0x{self.address:08x}", "kind": self.kind,
                "size": self.size, "old": f"0x{self.old:x}", "new": f"0x{self.new:x}"}


@dataclass(frozen=True)
class Instruction:
    pc: int
    raw: bytes
    before: tuple
    after_pc: int
    registers: tuple
    returned: bool


def number(text):
    try:
        value = int(text, 0)
    except (TypeError, ValueError):
        raise CoreError(f"invalid integer: {text!r}") from None
    if not 0 <= value <= MASK:
        raise CoreError(f"integer outside unsigned 32-bit range: {text!r}")
    return value


def register(name):
    try:
        return REGISTERS[name.lower()]
    except (AttributeError, KeyError):
        raise CoreError(f"unknown register {name!r}") from None


def test_rom():
    """Return the shared byte image used by the offline tools and their tests."""
    rom = bytearray(STACK - BASE)
    for address, expected in EXACT.items():
        raw = bytes.fromhex(expected)
        start = address - BASE
        rom[start:start + len(raw)] = raw
    start = HELPER - BASE
    rom[start:start + len(HELPER_BYTES)] = HELPER_BYTES
    for address, value in LITERALS.items():
        rom[address - BASE:address - BASE + 4] = value.to_bytes(4, "little")
    return bytes(rom)


class Memory:
    """Integer guest memory with common probe records and debugger events."""
    def __init__(self):
        self.regions = []
        self.events = []
        self.accesses = []
        self.watchpoints = set()
        self.watch_reads = False
        self.trace_fetches = False

    def map(self, base, size, data=None, writable=True, name=""):
        if (not isinstance(base, int) or not isinstance(size, int) or
                not 0 <= base < 0x100000000 or base & 1 or size <= 0 or
                base + size > 0x100000000):
            raise CoreError("invalid or wrapping guest mapping")
        if data is not None and len(data) != size:
            raise CoreError("mapping data length mismatch")
        if any(base < other + len(block) and other < base + size
               for other, block, _, _ in self.regions):
            raise CoreError("overlapping guest mappings")
        self.regions.append((base, bytearray(size) if data is None else bytearray(data), writable, name))
        self.regions.sort(key=lambda row: row[0])

    def region(self, address, size):
        if (not isinstance(address, int) or not isinstance(size, int) or
                size not in (1, 2, 4) or address < 0 or address + size > 0x100000000):
            raise CoreError("invalid guest access; choose size 1, 2, or 4")
        for base, data, writable, name in self.regions:
            if base <= address and address + size <= base + len(data):
                return data, address - base, writable
        raise CoreError(f"unmapped/boundary-crossing access at 0x{address:08x} ({size} bytes)")

    def _find(self, address, size):
        data, offset, writable = self.region(address, size)
        return address - offset, data, writable

    def read(self, address, size=4, reason="inspect"):
        if reason not in REASONS or reason == "initialize":
            raise CoreError(f"invalid read reason: {reason}")
        data, offset, _ = self.region(address, size)
        value = int.from_bytes(data[offset:offset + size], "little")
        if reason != "fetch" or self.trace_fetches:
            self.accesses.append({"op": "read", "address": address, "size": size,
                                  "bytes": data[offset:offset + size].hex(), "reason": reason})
        if reason == "inspect" or (reason in ("load", "data") and self.watch_reads):
            point = self._watched(address, size)
            if point is not None:
                self.events.append(Event(point, "load" if reason in ("load", "data") else "read",
                                         size, value, value))
        return value

    def write(self, address, size=4, value=0, reason="write"):
        if reason not in ("write", "data", "initialize"):
            raise CoreError(f"invalid write reason: {reason}")
        data, offset, writable = self.region(address, size)
        if not writable and reason != "initialize":
            raise CoreError(f"write to read-only memory at 0x{address:08x}")
        if not isinstance(value, int) or not 0 <= value < 1 << (size * 8):
            raise CoreError("value does not fit guest access")
        old = int.from_bytes(data[offset:offset + size], "little")
        data[offset:offset + size] = value.to_bytes(size, "little")
        self.accesses.append({"op": "write", "address": address, "size": size,
                              "bytes": value.to_bytes(size, "little").hex(), "reason": reason})
        if reason != "initialize":
            point = self._watched(address, size)
            if point is not None:
                self.events.append(Event(point, "write", size, old, value))
        return old, value

    def _watched(self, address, size):
        for point, width in sorted(self.watchpoints):
            if point < address + size and address < point + width:
                return address
        return None

    def fetch(self, address, size):
        return self.read(address, size, "fetch").to_bytes(size, "little")

    def initialize(self, address, size, value):
        return self.write(address, size, value, "initialize")

    def u16(self, address, reason="inspect"):
        return self.read(address, 2, reason)

    def u32(self, address, reason="inspect"):
        return self.read(address, 4, reason)

    def put16(self, address, value):
        return self.write(address, 2, value & 0xffff, "write")

    def put32(self, address, value):
        return self.write(address, 4, value & MASK, "write")


class RoutineCPU:
    def __init__(self, memory, rom):
        if len(rom) <= HELPER - BASE + len(HELPER_BYTES):
            raise CoreError("ROM is too short for the verified entry/helper")
        self.mem = memory
        self.regs = [0] * 32
        self.pc = ENTRY
        self.instructions = self.helper_calls = 0
        self.helper_delay = False
        self.helper_enabled = False
        self.helper_hook = None
        self.returned = False
        self.saved = None
        self.original_sp = TOP
        for address, expected in EXACT.items():
            raw = bytes.fromhex(expected)
            if rom[address - BASE:address - BASE + len(raw)] != raw:
                raise CoreError(f"ROM differs at 0x{address:08x}")
        if rom[HELPER - BASE:HELPER - BASE + len(HELPER_BYTES)] != HELPER_BYTES:
            raise CoreError("helper differs from identified jalr/nop encoding")

    def initialize(self, a0=0, arg5=STATE, a3_value=0x1000, state=0):
        if not all(isinstance(v, int) and 0 <= v <= MASK for v in (a0, arg5, a3_value)):
            raise CoreError("initialization value outside unsigned 32-bit range")
        if not isinstance(state, int) or not 0 <= state <= 0xffff:
            raise CoreError("state must fit 16 bits")
        for address, size in ((TOP, 4), (DATA + 0x200, 4), (STATE, 4)):
            self.mem.region(address, size)
        self.regs = [0] * 32
        self.regs[29], self.regs[16] = TOP, STATE
        self.regs[4], self.regs[6], self.regs[7] = a0, DATA + 0x100, DATA + 0x200
        self.regs[31] = RETURN_PC
        self.pc, self.instructions, self.helper_calls = ENTRY, 0, 0
        self.helper_delay, self.saved, self.returned = False, None, False
        self.original_sp = TOP
        self.mem.events.clear()
        self.mem.accesses.clear()
        self.mem.initialize(TOP, 4, arg5)
        self.mem.initialize(DATA + 0x200, 4, a3_value)
        self.mem.initialize(STATE, 4, state)
        self.mem.accesses.clear()

    def registers(self, pc=None):
        return {"pc": f"0x{self.pc if pc is None else pc:08x}",
                **{name: f"0x{value:08x}" for name, value in zip(NAMES, self.regs)}}

    def snapshot(self):
        return {"pc": RETURN_PC if self.returned else self.pc,
                "registers": self.regs[:], "instructions": self.instructions,
                "helper_calls": self.helper_calls, "helper_delay": self.helper_delay,
                "state": "returned" if self.returned else "stopped",
                "returned": self.returned,
                "saved": None if self.saved is None else self.saved.copy()}

    def step(self):
        pc = self.pc
        if pc == HELPER:
            return self.helper()
        if pc not in EXACT:
            raise CoreError(f"unverified guest PC: 0x{pc:08x}")
        expected = EXACT[pc]
        raw = self.mem.fetch(pc, len(expected) // 2)
        if raw.hex() != expected:
            raise CoreError(f"instruction differs at 0x{pc:08x}: {raw.hex()}")
        before, r, branch = tuple(self.regs), self.regs, None
        if pc == ENTRY:
            sp = r[29] - 0x28
            if sp < STACK or sp + 0x28 > TOP:
                raise CoreError("SAVE outside the test stack")
            self.saved = {name: r[REGISTERS[name]] for name in ("s0", "a0", "a1", "ra")}
            for offset, name in ((0x18, "s0"), (0x1c, "ra"), (0x20, "a0"), (0x24, "a1")):
                self.mem.write(sp + offset, 4, r[REGISTERS[name]], "write")
            r[29] = sp
        elif pc in (ENTRY + 4, ENTRY + 0x28):
            pass
        elif pc == ENTRY + 6:
            r[16] = self.mem.read(r[29] + 0x28, 4, "load")
        elif pc == ENTRY + 8:
            branch = ENTRY + 0x1a if r[4] == 1 else ENTRY + 0xa
        elif pc == ENTRY + 0xa:
            r[2] = r[29] + 0x1c
        elif pc == ENTRY + 0xc:
            self.mem.write(r[6], 4, r[2], "write")
        elif pc in (ENTRY + 0xe, ENTRY + 0x1a):
            r[4] = self.mem.read(r[7], 4, "load")
        elif pc in (ENTRY + 0x10, ENTRY + 0x1c):
            r[2] = self.mem.read(r[16], 2, "load")
        elif pc == ENTRY + 0x12:
            r[5] = self.mem.read(pc + 2 + 0x24, 4, "load")
        elif pc == ENTRY + 0x1e:
            r[5] = self.mem.read(pc + 2 + 0x1c, 4, "load")
        elif pc in (ENTRY + 0x14, ENTRY + 0x20):
            r[4] += r[2]
            r[4] &= MASK
        elif pc == ENTRY + 0x16:
            r[7] = 1
        elif pc == ENTRY + 0x22:
            r[7] = 0
        elif pc == ENTRY + 0x18:
            branch = ENTRY + 0x24
        elif pc == ENTRY + 0x24:
            r[31] = ENTRY + 0x2a
            branch = HELPER
        elif pc == ENTRY + 0x2a:
            r[3] = self.mem.read(r[16], 2, "load")
        elif pc == ENTRY + 0x2c:
            r[2] = (r[2] + r[3]) & MASK
        elif pc == ENTRY + 0x2e:
            self.mem.write(r[16], 2, r[2] & 0xffff, "write")
        elif pc == ENTRY + 0x30:
            if self.saved is None:
                raise CoreError("RESTORE without an earlier SAVE")
            for name, value in self.saved.items():
                r[REGISTERS[name]] = value
            r[29] += 0x28
            self.saved = None
        elif pc == ENTRY + 0x32:
            if r[29] != self.original_sp:
                raise CoreError("stack pointer not restored")
            branch = r[31]
            self.returned = True
        self.pc = (pc + len(raw)) & MASK if branch is None else branch
        self.helper_delay = pc == ENTRY + 0x28
        self.instructions += 1
        r[0] = 0
        return Instruction(pc, raw, before, self.pc, tuple(r), self.returned)

    def helper(self):
        if self.pc != HELPER or not self.helper_enabled:
            raise CoreError("helper stub disabled or PC is not at helper")
        if self.regs[31] != ENTRY + 0x2a or not self.helper_delay:
            raise CoreError("helper stub requires the verified delay-slot boundary")
        pc, before = self.pc, tuple(self.regs)
        if self.helper_hook is not None:
            self.helper_hook()
        self.helper_calls += 1
        self.helper_delay = False
        self.pc = self.regs[31]
        return Instruction(pc, HELPER_BYTES[:2], before, self.pc, tuple(self.regs), False)
