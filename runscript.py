from ghidra.program.model.scalar import Scalar

listing = currentProgram.getListing()

LOADS = ["lw", "lbu", "lb", "lhu", "lh"]
BRANCHES = ["beq", "bne", "beqz", "bnez"]


def has_40(ins):
    if ins.getMnemonicString().lower() != "andi":
        return False

    for i in range(ins.getNumOperands()):
        for obj in ins.getOpObjects(i):
            if isinstance(obj, Scalar):
                if obj.getUnsignedValue() == 0x40:
                    return True

    return False


candidates = []

for ins in listing.getInstructions(True):

    if not has_40(ins):
        continue

    previous = []
    following = []

    # Look 10 instructions backward.
    cur = ins
    for _ in range(10):
        prev = listing.getInstructionBefore(cur.getAddress())

        if prev is None:
            break

        previous.insert(0, prev)
        cur = prev

    # Look 10 instructions forward.
    cur = ins
    for _ in range(10):
        nxt = listing.getInstructionAfter(cur.getAddress())

        if nxt is None:
            break

        following.append(nxt)
        cur = nxt

    nearby_loads = [
        x for x in previous
        if x.getMnemonicString().lower() in LOADS
    ]

    if not nearby_loads:
        continue

    nearby_branches = [
        x for x in following
        if x.getMnemonicString().lower() in BRANCHES
        or x.getMnemonicString().lower().startswith("beq")
        or x.getMnemonicString().lower().startswith("bne")
    ]

    candidates.append(
        (ins, previous, following, nearby_loads, nearby_branches)
    )


print("")
print("============================================================")
print("ANDI 0x40 + NEARBY MEMORY LOAD")
print("============================================================")
print("")

for num, item in enumerate(candidates, 1):

    ins, previous, following, loads, branches = item

    print("============================================================")
    print("CANDIDATE #%d @ %s" % (num, ins.getAddress()))
    print(
        "Nearby loads: %d | Nearby branches: %d"
        % (len(loads), len(branches))
    )
    print("============================================================")

    for x in previous:
        print("     %s    %s" % (x.getAddress(), x))

    print(" >>> %s    %s" % (ins.getAddress(), ins))

    for x in following:
        print("     %s    %s" % (x.getAddress(), x))

    print("")


print("============================================================")
print("TOTAL CANDIDATES: %d" % len(candidates))
print("============================================================")
