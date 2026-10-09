from ghidra.program.model.scalar import Scalar

listing = currentProgram.getListing()
shown = 0

for ins in listing.getInstructions(True):

    if ins.getMnemonicString().lower() != "andi":
        continue

    found = False

    for i in range(ins.getNumOperands()):
        for obj in ins.getOpObjects(i):
            if isinstance(obj, Scalar) and obj.getUnsignedValue() == 0x40:
                found = True

    if not found:
        continue

    print("%s    %s" % (ins.getAddress(), ins))

    shown += 1
    if shown >= 20:
        break
