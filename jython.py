from ghidra.program.model.scalar import Scalar

listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()

keywords = [
    "scp",
    "ccism",
    "ccci",
    "smem",
    "shm",
    "ipi",
    "apccci"
]

print("============================================================")
print("SCP/CCISM FUNCTIONS USING SCALAR 0x204")
print("============================================================")

hits = 0

for ins in listing.getInstructions(True):

    found_204 = False

    for i in range(ins.getNumOperands()):
        for obj in ins.getOpObjects(i):
            if isinstance(obj, Scalar):
                if obj.getUnsignedValue() == 0x204:
                    found_204 = True

    if not found_204:
        continue

    func = fm.getFunctionContaining(ins.getAddress())

    if func is None:
        continue

    name = func.getName().lower()

    if not any(k in name for k in keywords):
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

    # context: 5 before
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

    # context: 7 after
    cur = ins

    for _ in range(7):
        nxt = listing.getInstructionAfter(cur.getAddress())
        if nxt is None:
            break

        print("     %s    %s" % (nxt.getAddress(), nxt))
        cur = nxt

print("")
print("============================================================")
print("TOTAL RELEVANT HITS: %d" % hits)
print("============================================================")
