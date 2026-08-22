import re

fpath = 'c:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/bot_handlers/all_handlers.py'
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern for the handle_text_message function
pattern = r'    @dp\.message\(F\.text, ~F\.text\.startswith\("/"\)\)\n    async def handle_text_message\(message: types\.Message\):\n(?:.|\n)*?    @dp\.message\(F\.text\.startswith\(".*? Буфер"\)\)'

match = re.search(pattern, content)
if match:
    block = match.group(0)
    # The matched block includes the decorator for cmd_buffer. We must split it.
    buffer_decorator = r'    @dp.message(F.text.startswith("📥 Буфер"))'
    # Actually wait, let's just use string split!
    
    parts = content.split('    @dp.message(F.text, ~F.text.startswith("/"))\n    async def handle_text_message(message: types.Message):\n')
    part_1 = parts[0]
    part_2 = parts[1]
    
    parts_2 = part_2.split('    @dp.message(F.text.startswith("📥 Буфер"))\n')
    handler_body = parts_2[0]
    rest_of_file = parts_2[1]
    
    # Process handler body to remove the menu block
    new_handler_body = []
    lines = handler_body.split('\n')
    skip = False
    for line in lines:
        if 'menu_texts = [' in line:
            skip = True
        if skip and 'return' in line:
            skip = False
            continue
        if not skip:
            new_handler_body.append(line)
            
    handler_code = '    @dp.message(F.text, ~F.text.startswith("/"))\n    async def handle_text_message(message: types.Message):\n' + '\n'.join(new_handler_body)
    
    new_content = part_1 + '    @dp.message(F.text.startswith("📥 Буфер"))\n' + rest_of_file + '\n\n' + handler_code
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully moved handler!")
else:
    print("Could not match.")
