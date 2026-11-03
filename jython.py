addr = toAddr("63c5b588")

rm = currentProgram.getReferenceManager()
fm = currentProgram.getFunctionManager()

keywords = [
    "ccism",
    "ccismc",
    "ccismq",
    "ccci",
    "scp"
]

seen = set()

print("====================================================")
print("CCISM/SCP XREFS TO DAT_63c5b588")
print("====================================================")

for ref in rm.getReferencesTo(addr):

    from_addr = ref.getFromAddress()
    func = fm.getFunctionContaining(from_addr)

    if func is None:
        continue

    name = func.getName()

    if name in seen:
        continue

    seen.add(name)

    if any(k in name.lower() for k in keywords):
        print("%-40s %s" % (name, func.getEntryPoint()))
