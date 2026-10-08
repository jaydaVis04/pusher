from ghidra.program.model.scalar import Scalar

listing = currentProgram.getListing()

print("====================================================")
print("ANDI instructions using immediate 0x40")
print("====================================================")

hits = 0

for ins in listing.getInstructions(True):
    if ins.getMnemonicString().lower() != "andi":
        continue

    found = False

    for i in range(ins.getNumOperands()):
        for obj in ins.getOpObjects(i):
            if isinstance(obj, Scalar):
                if obj.getUnsignedValue() == 0x40:
                    found = True

    if not found:
        continue

    hits += 1

    print("\n====================================================")
    print("HIT #%d @ %s" % (hits, ins.getAddress()))
    print("====================================================")

    # 3 instructions before
    context = []
    cur = ins

    for _ in range(3):
        prev = listing.getInstructionBefore(cur.getAddress())
        if prev is None:
            break
        context.insert(0, prev)
        cur = prev

    context.append(ins)

    # 4 instructions after
    cur = ins
    for _ in range(4):
        nxt = listing.getInstructionAfter(cur.getAddress())
        if nxt is None:
            break
        context.append(nxt)
        cur = nxt

    for x in context:
        marker = " >>> " if x.getAddress() == ins.getAddress() else "     "
        print(marker + str(x.getAddress()) + "    " + str(x))

print("\n====================================================")
print("TOTAL EXACT ANDI 0x40 HITS:", hits)
print("====================================================")
