lines = []
with open("storage.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        c = line.count('"""')
        if c > 0:
            lines.append((i, c, line.strip()))
for i, c, l in lines:
    print(f"L{i} [{c}]: {l}")
