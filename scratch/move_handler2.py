import sys
fpath = 'c:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/bot_handlers/all_handlers.py'
with open(fpath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = 110
end_idx = 267

block = lines[start_idx:end_idx]

# filter out the menu checking block
new_block = []
skip = False
for line in block:
    if 'menu_texts = [' in line:
        skip = True
    if skip and 'return\n' in line:
        skip = False
        continue
    if not skip:
        new_block.append(line)

# remove from original place
del lines[start_idx:end_idx]

# insert before ai_confirm
insert_idx = len(lines)
for i, line in enumerate(lines):
    if '@dp.callback_query(F.data.startswith("ai_confirm_"))' in line:
        insert_idx = i
        break

lines = lines[:insert_idx] + new_block + lines[insert_idx:]

with open(fpath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("Moved correctly!")
