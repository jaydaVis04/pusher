from ghidra.program.model.scalar import Scalar
from ghidra.program.model.lang import Register

listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()

TARGET = 0x5c

keywords = [
    "ccism",
    "ccismc",
    "ccismq",
    "scp",
]

# Memory-access instructions worth caring about
mem_mnemonics = [
    "lw", "sw",
    "lb", "lbu", "sb",
    "lh", "lhu", "sh",
]

hits = 0

print("============================================================")
print("CCISM/SCP MEMORY ACCESSES USING OFFSET +0x5C")
print("============================================================")

for ins in listing.getInstructions(True):

    func = fm.getFunctionContaining(ins.getAddress())
    if func is None:
        continue

    fname = func.getName().lower()

    if not any(k in fname for k in keywords):
        continue

    mnemonic = ins.getMnemonicString().lower()

    if mnemonic not in mem_mnemonics:
        continue

    found_5c = False
    registers = []

    for op_index in range(ins.getNumOperands()):
        for obj in ins.getOpObjects(op_index):

            if isinstance(obj, Scalar):
                if obj.getUnsignedValue() == TARGET:
                    found_5c = True

            elif isinstance(obj, Register):
                registers.append(obj.getName().lower())

    if not found_5c:
        continue

    # Ignore PC-relative accesses such as 0x5c(pc)
    if "pc" in registers:
        continue

    hits += 1

    print("")
    print("============================================================")
    print("HIT #%d" % hits)
    print("FUNCTION: %s" % func.getName())
    print("ENTRY:    %s" % func.getEntryPoint())
    print("ADDRESS:  %s" % ins.getAddress())
    print("INSTR:    %s" % ins)
    print("============================================================")

    # 5 instructions before
    before = []
    cur = ins

    for _ in range(5):
        prev = listing.getInstructionBefore(cur.getAddress())
        if prev is None:
            break

        before.insert(0, prev)
        cur = prev

    for x in before:
        print("     %s    %s" % (x.getAddress(), x))

    print(" >>> %s    %s" % (ins.getAddress(), ins))

    # 8 instructions after
    cur = ins

    for _ in range(8):
        nxt = listing.getInstructionAfter(cur.getAddress())
        if nxt is None:
            break

        print("     %s    %s" % (nxt.getAddress(), nxt))
        cur = nxt

print("")
print("============================================================")
print("TOTAL HITS: %d" % hits)
print("============================================================")
