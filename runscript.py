from ghidra.program.model.scalar import Scalar

listing = currentProgram.getListing()


def scalar_is_40(ins):
    if ins.getMnemonicString().lower() != "andi":
        return False

    for i in range(ins.getNumOperands()):
        for obj in ins.getOpObjects(i):
            if isinstance(obj, Scalar):
                if obj.getUnsignedValue() == 0x40:
                    return True
    return False


def reg_text(ins, operand):
    try:
        return ins.getDefaultOperandRepresentation(operand).strip()
    except:
        return ""


hits = []

for ins in listing.getInstructions(True):

    if not scalar_is_40(ins):
        continue

    # MIPS:
    # andi DEST, SOURCE, 0x40
    if ins.getNumOperands() < 3:
        continue

    dest = reg_text(ins, 0)
    source = reg_text(ins, 1)

    if not dest or not source:
        continue

    # --------------------------------------------------
    # Search up to 5 instructions backward for:
    #
    # lw SOURCE, ...
    # --------------------------------------------------

    load = None
    cur = ins

    for _ in range(5):

        prev = listing.getInstructionBefore(cur.getAddress())

        if prev is None:
            break

        mnem = prev.getMnemonicString().lower()

        if mnem == "lw" and prev.getNumOperands() >= 1:

            load_dest = reg_text(prev, 0)

            if load_dest == source:
                load = prev
                break

        cur = prev

    if load is None:
        continue

    # --------------------------------------------------
    # Search next 5 instructions for branch using DEST
    # --------------------------------------------------

    branch = None
    cur = ins

    for _ in range(5):

        nxt = listing.getInstructionAfter(cur.getAddress())

        if nxt is None:
            break

        mnem = nxt.getMnemonicString().lower()

        if (
            mnem.startswith("beq") or
            mnem.startswith("bne")
        ):

            text = str(nxt)

            if dest in text:
                branch = nxt
                break

        cur = nxt

    if branch is None:
        continue

    hits.append((load, ins, branch))


print("")
print("============================================================")
print("LW -> ANDI 0x40 -> BRANCH CANDIDATES")
print("============================================================")
print("")

for number, (load, mask, branch) in enumerate(hits, 1):

    print("============================================================")
    print("CANDIDATE #%d" % number)
    print("============================================================")

    # print a little surrounding context
    cur = load

    print("%s    %s" % (load.getAddress(), load))

    while True:

        nxt = listing.getInstructionAfter(cur.getAddress())

        if nxt is None:
            break

        print("%s    %s" % (nxt.getAddress(), nxt))

        if nxt.getAddress() == branch.getAddress():
            break

        cur = nxt

        # safety in case something weird happens
        if cur.getAddress().subtract(load.getAddress()) > 40:
            break

    print("")

print("============================================================")
print("TOTAL STRONG CANDIDATES: %d" % len(hits))
print("============================================================")
