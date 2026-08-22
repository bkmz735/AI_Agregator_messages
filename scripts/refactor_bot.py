import re
import os

with open('scratch/handlers_dump.py', 'r', encoding='utf-8') as f:
    dump = f.read()

# Remove the outer `def _setup_handlers(self):` and indent
lines = dump.split('\n')
handlers_content = '\n'.join(line[8:] for line in lines[1:])  # unindent

# Replace self.dp with dp, and self. with master_bot.
# Be careful: `self.` -> `master_bot.`
handlers_content = re.sub(r'@self\.dp\.', '@dp.', handlers_content)
handlers_content = re.sub(r'\bself\.', 'master_bot.', handlers_content)

template = f"""import logging
import html
import io
import asyncio
from aiogram.filters import Command
from aiogram import types, F
import ui_keyboards as kb_ui

logger = logging.getLogger(__name__)

def setup_all_handlers(master_bot):
    dp = master_bot.dp

{handlers_content}
"""

os.makedirs('bot_handlers', exist_ok=True)
with open('bot_handlers/__init__.py', 'w', encoding='utf-8') as f:
    pass

with open('bot_handlers/all_handlers.py', 'w', encoding='utf-8') as f:
    f.write(template)

print("Created bot_handlers/all_handlers.py")
