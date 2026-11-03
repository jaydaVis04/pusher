from ghidra.program.model.scalar import Scalar
from ghidra.program.model.lang import Register

TARGET_FUNC = "ccismc_scp_get_instance"
TARGET_OFFSET = 0x5c

listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()
rm = currentProgram.getReferenceManager()

mem_mnemonics = [
    "lw", "sw",
    "lb", "lbu", "sb",
    "lh", "lhu", "sh"
]

# ------------------------------------------------------------
# Find ccismc_scp_get_instance
# ------------------------------------------------------------

target = None

for f in fm.getFunctions(True):
    if f.getName() == TARGET_FUNC:
        target = f
        break

if target is None:
    print("ERROR: could not find %s" % TARGET_FUNC)
    exit()

print("TARGET: %s @ %s" % (target.getName(), target.getEntryPoint()))
print("")

# ------------------------------------------------------------
# Find all caller functions
# ------------------------------------------------------------

callers = {}

for ref in rm.getReferencesTo(target.getEntryPoint()):

    from_addr = ref.getFromAddress()
    caller = fm.getFunctionContaining(from_addr)

    if caller is None:
        continue

    name = caller.getName()

    if name not in callers:
        callers[name] = {
            "func": caller,
            "calls": []
        }

    callers[name]["calls"].append(from_addr)

print("Caller functions: %d" % len(callers))
print("")

# ------------------------------------------------------------
# Look inside each caller for memory accesses using +0x5C
# ------------------------------------------------------------

total_hits = 0

for name in sorted(callers.keys()):

    caller = callers[name]["func"]
    hits = []

    for ins in listing.getInstructions(caller.getBody(), True):

        mnemonic = ins.getMnemonicString().lower()

        if mnemonic not in mem_mnemonics:
            continue

        found_5c = False
        regs = []

        for op_index in range(ins.getNumOperands()):
            for obj in ins.getOpObjects(op_index):

                if isinstance(obj, Scalar):
                    if obj.getUnsignedValue() == TARGET_OFFSET:
                        found_5c = True

                elif isinstance(obj, Register):
                    regs.append(obj.getName().lower())

        if not found_5c:
            continue

        # Ignore stack and PC-relative accesses
        if "pc" in regs or "sp" in regs:
            continue

        hits.append(ins)

    if len(hits) == 0:
        continue

    total_hits += len(hits)

    print("============================================================")
    print("FUNCTION: %s" % caller.getName())
    print("ENTRY:    %s" % caller.getEntryPoint())

    print("CALLS TO %s:" % TARGET_FUNC)
    for call_addr in callers[name]["calls"]:
        print("    %s" % call_addr)

    print("")

    for hit in hits:

        print("------------------------------------------------------------")
        print("0x5C HIT: %s    %s" % (hit.getAddress(), hit))
        print("")

        # Print 5 instructions before
        before = []
        cur = hit

        for _ in range(5):
            prev = listing.getInstructionBefore(cur.getAddress())
            if prev is None:
                break
            before.insert(0, prev)
            cur = prev

        for x in before:
            print("     %s    %s" % (x.getAddress(), x))

        print(" >>> %s    %s" % (hit.getAddress(), hit))

        # Print 7 instructions after
        cur = hit

        for _ in range(7):
            nxt = listing.getInstructionAfter(cur.getAddress())
            if nxt is None:
                break

            print("     %s    %s" % (nxt.getAddress(), nxt))
            cur = nxt

        print("")

print("============================================================")
print("TOTAL MATCHING +0x5C ACCESSES: %d" % total_hits)
print("============================================================")
