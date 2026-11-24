"""Regression tests for the shared, offline MIPS16e routine tools."""
import hashlib
import unittest

import mips16e_core as core
import mips16e_debugger as dbg
import mips16e_probe as probe


def make_rom(exact=True):
    """Create an input from the shared byte-level instruction table."""
    rom = core.rom_image()
    if not exact:
        image = bytearray(rom)
        image[core.ENTRY - core.BASE] ^= 1
        rom = bytes(image)
    return rom


def complete_cpu(a0=0, state=0, helper=True):
    rom = make_rom()
    memory = core.Memory()
    memory.map(core.BASE, len(rom), rom, writable=False, name="exact ROM")
    cpu = core.RoutineCPU(memory, rom)
    cpu.helper_enabled = helper
    cpu.initialize(a0=a0, state=state)
    return cpu


class CoreTests(unittest.TestCase):
    def test_initialization_and_byte_validation(self):
        cpu = complete_cpu()
        self.assertEqual((cpu.pc, cpu.regs[31], cpu.regs[29]),
                         (core.ENTRY, core.RETURN_PC, core.TOP))
        with self.assertRaises(core.CoreError):
            core.RoutineCPU(core.Memory(), b"")
        with self.assertRaises(core.CoreError):
            memory = core.Memory()
            memory.map(core.BASE, len(make_rom()), make_rom(), writable=False)
            core.RoutineCPU(memory, make_rom(exact=False))

    def test_jal_link_survives_execute_and_record_delay_slot(self):
        for helper in (False, True):
            cpu = complete_cpu(a0=1, helper=helper)
            while cpu.pc != core.ENTRY + 0x24:
                cpu.step()
            cpu.step()
            self.assertEqual((cpu.pc, cpu.regs[31], cpu.helper_delay),
                             (core.ENTRY + 0x28, core.ENTRY + 0x2a, False))
            cpu.step()
            self.assertEqual((cpu.pc, cpu.regs[31], cpu.helper_delay),
                             (core.HELPER, core.ENTRY + 0x2a, True))
            if helper:
                self.assertEqual(cpu.regs[2], 0)
                cpu.step()
                self.assertEqual(cpu.regs[31], core.ENTRY + 0x2a)
                self.assertEqual(cpu.helper_calls, 1)

    def test_positive_guest_sequences_and_guest_helper_disabled(self):
        cpu = complete_cpu()
        cpu.run_guest()
        self.assertTrue(cpu.returned)
        self.assertEqual(cpu.regs[2], 1)
        cpu = complete_cpu(a0=1)
        cpu.run_guest()
        self.assertTrue(cpu.returned)
        self.assertEqual(cpu.regs[2], 4)
        self.assertEqual(cpu.regs[29], core.TOP)
        self.assertEqual(cpu.helper_calls, 1)
        cpu = complete_cpu(a0=1, helper=False)
        with self.assertRaises(core.CoreError):
            cpu.run_guest()
        self.assertEqual((cpu.pc, cpu.helper_calls), (core.HELPER, 0))

    def test_selected_helper_input_matrix(self):
        expected = {(0, 0): 1, (1, 0): 4, (2, 0x1000): 0,
                    (0xffffffff, 0x7fff): 2, (0, 0x1000): 0}
        for (a0, state), result in expected.items():
            with self.subTest(a0=a0, state=state):
                cpu = complete_cpu(a0=a0, state=state)
                cpu.run_guest()
                self.assertTrue(cpu.returned)
                self.assertEqual(cpu.regs[2], result)
                self.assertEqual(cpu.mem.u16(core.STATE), state)
                self.assertEqual(cpu.regs[29], core.TOP)
                self.assertEqual(cpu.regs[31], core.RETURN_PC)


class DebuggerTests(unittest.TestCase):
    def setUp(self):
        self.controller = dbg.initial(make_rom())

    def test_step_breakpoint_helper_and_run(self):
        self.controller.step()
        self.assertEqual(self.controller.command_count, 1)
        self.assertEqual(self.controller.trace[-1]["before"]["pc"],
                         f"0x{core.ENTRY:08x}")
        self.controller.reset()
        self.controller.breakpoints.add(core.ENTRY)
        self.controller.run()
        self.assertEqual(self.controller.state, "breakpoint")
        self.controller = dbg.initial(make_rom())
        while self.controller.pc != core.HELPER:
            self.controller.step()
        self.assertEqual(self.controller.state, "helper")
        self.controller.helper_enabled = False
        with self.assertRaises(core.CoreError):
            self.controller.step()
        self.controller.helper_enabled = True
        self.controller.step()
        self.assertEqual(self.controller.command_count, 30)
        self.assertEqual(self.controller.mem.u32(core.DATA + 0x200), 1)
        self.controller.run()
        self.assertEqual(self.controller.state, "returned")
        self.controller.step()
        self.assertEqual(self.controller.state, "returned")

    def test_trace_and_wait_helpers(self):
        self.controller.wait(core.COMMAND, 1)
        self.assertTrue(self.controller.mem.u32(core.COMMAND))
        self.controller.execute_trace(core.ENTRY + 2)
        self.assertEqual(len(self.controller.trace), 2)
        self.assertEqual(self.controller.trace[-1]["after"]["pc"],
                         f"0x{core.ENTRY + 2:08x}")

    def test_watch_read_and_console_validation(self):
        self.controller.watch(core.STATE, 2)
        self.controller.mem.read(core.STATE, 2, "inspect")
        self.assertEqual([(event.address, event.kind) for event in self.controller.mem.events],
                         [(core.STATE, "read")])
        self.controller.reset()
        self.assertEqual((self.controller.mem.events, self.controller.mem.records), ([], []))
        for command in ("", "set reg nope 1", "break 0x1f009785",
                        "watch 0x70000000 3", "read x 4", "nonsense", "helper bad"):
            self.assertFalse(self.controller.line(command)["ok"], command)
        self.assertEqual(self.controller.line("break 0x1f009784")["state"], "stopped")
        self.assertEqual(self.controller.line("continue")["state"], "breakpoint")
        self.assertEqual(self.controller.line("set reg zero 0xffffffff")["registers"]["zero"],
                         "0x00000000")

    def test_console_run_and_scripting(self):
        response = self.controller.line("continue")
        self.assertEqual((response["state"], response["registers"]["r31"]),
                         ("returned", f"0x{core.RETURN_PC:08x}"))
        self.assertFalse(response["breakpoints"])
        self.assertFalse(self.controller.ram_accesses)
        replies = list(dbg.script(make_rom(), ("step", "continue")))
        self.assertEqual((replies[0]["pc"], replies[-1]["state"]),
                         (f"0x{core.ENTRY + 2:08x}", "returned"))
        self.assertEqual(dbg.format_snapshot(self.controller.snapshot())["pc"],
                         f"0x{core.RETURN_PC:08x}")


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.rom = make_rom()

    def test_register_aliases_values_and_bounds(self):
        machine = probe.prepare(probe.Machine(self.rom), a0=1, state=0)
        self.assertEqual(machine.r["s0"], core.STATE)
        self.assertEqual(machine.r["a1"], core.DATA + 0x100)
        self.assertEqual(machine.r["a3"], core.DATA + 0x200)
        machine.r["v0"], machine.r[8] = 5, 6
        machine.r["zero"] = 0xffffffff
        self.assertEqual((machine.r["v0"], machine.r["t0"], machine.r["zero"]), (5, 6, 0))
        for name in ("bogus", -1, 32, True):
            with self.assertRaises(KeyError):
                machine.r[name]
        for value in (True, -1, 1 << 32, "1"):
            with self.assertRaises(ValueError):
                machine.r["v0"] = value
        with self.assertRaises(probe.EmulationError):
            machine.r["missing"] = 1

    def test_result_matches_core_and_serializable_public_shape(self):
        row = probe.run(probe.Machine(self.rom), a0=1, state=0)
        cpu = complete_cpu(a0=1)
        cpu.run_guest()
        self.assertEqual(int(row["result"]["v0"], 16), cpu.regs[2])
        self.assertEqual(int(row["result"]["sp"], 16), core.TOP)
        self.assertTrue(row["trace"][-1]["returned"])
        for key in ("scenario", "result", "frames", "steps", "helper_calls", "trace",
                    "accesses", "registers", "memory_writes", "reason", "disassembly",
                    "helper_inputs"):
            self.assertIn(key, row)
        self.assertEqual(row["input_sha256"], row["rom_sha256"])
        self.assertEqual(row["input_sha256"], hashlib.sha256(self.rom).hexdigest())
        self.assertTrue(all("bytes" in event for event in row["accesses"]))
        self.assertTrue(all("helper" in item for item in row["helper_inputs"]))
        self.assertIsInstance(row["disassembly"], list)

    def test_matrix_limits_and_explicit_address_failure(self):
        self.assertEqual(len(probe.exhaustive(self.rom)), 20)
        for a0, state in ((0, 0), (1, 0), (2, 0x1000), (0xffffffff, 0x7fff)):
            row = probe.run(probe.Machine(self.rom), a0=a0, state=state,
                            rom_bytes=self.rom)
            self.assertIn(int(row["result"]["v0"], 16), range(5))
        with self.assertRaises(probe.EmulationError):
            probe.run(probe.Machine(self.rom), state_address=0x70000000)
        with self.assertRaises(probe.EmulationError):
            probe.run(probe.Machine(self.rom), limit=0)
        with self.assertRaises(probe.EmulationError):
            probe.run(probe.Machine(self.rom), limit=True)


if __name__ == "__main__":
    unittest.main()
