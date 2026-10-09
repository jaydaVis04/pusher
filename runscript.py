listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()

addresses = [
    "9006b534",
    "9006ff60",
    "90074ca8",
    "90077e6a",
]

print("============================================================")
print("ANDI 0x40 FUNCTION CONTEXT")
print("============================================================")

for s in addresses:
    addr = toAddr(s)
    ins = listing.getInstructionAt(addr)
    func = fm.getFunctionContaining(addr)

    print("")
    print("============================================================")
    print("ADDRESS: %s" % addr)

    if func:
        print("FUNCTION: %s" % func.getName())
        print("ENTRY:    %s" % func.getEntryPoint())
    else:
        print("FUNCTION: <none>")

    print("------------------------------------------------------------")

    cur = ins

    before = []
    for _ in range(6):
        prev = listing.getInstructionBefore(cur.getAddress())
        if prev is None:
            break
        before.insert(0, prev)
        cur = prev

    for x in before:
        print("     %s    %s" % (x.getAddress(), x))

    print(" >>> %s    %s" % (ins.getAddress(), ins))

    cur = ins
    for _ in range(8):
        nxt = listing.getInstructionAfter(cur.getAddress())
        if nxt is None:
            break
        print("     %s    %s" % (nxt.getAddress(), nxt))
        cur = nxt
