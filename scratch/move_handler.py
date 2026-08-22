import sys

fpath = 'c:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/bot_handlers/all_handlers.py'
with open(fpath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.startswith('    @dp.message(F.text, ~F.text.startswith("/"))'):
        start_idx = i
    if start_idx != -1 and line.startswith('    @dp.message(Command("stats"))'):
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    block = lines[start_idx:end_idx]
    
    del lines[start_idx:end_idx]
    
    # We want to put it before ai_confirm handlers, or just at the very end
    # Let's put it before the ai_confirm handlers which start at 
    # @dp.callback_query(F.data.startswith("ai_confirm_"))
    insert_idx = len(lines)
    for i, line in enumerate(lines):
        if line.startswith('    @dp.callback_query(F.data.startswith("ai_confirm_"))'):
            insert_idx = i
            break
            
    # Remove the menu check logic
    new_block = []
    skip = False
    for l in block:
        if 'menu_texts = [' in l:
            skip = True
        if skip and l.strip() == 'return':
            skip = False
            continue
        if not skip:
            new_block.append(l)

    lines = lines[:insert_idx] + new_block + lines[insert_idx:]
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Successfully moved handle_text_message!")
else:
    print(f"Could not find block. start={start_idx}, end={end_idx}")
