python3 - <<'PY'
target = 0x63c0748a

for line in open("iomem.txt"):
    try:
        rng = line.split(":", 1)[0].strip()
        start, end = [int(x, 16) for x in rng.split("-", 1)]
    except:
        continue

    if start <= target <= end:
        print(line, end="")
PY
