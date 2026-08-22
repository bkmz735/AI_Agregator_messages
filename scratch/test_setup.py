import asyncio
from master_bot import MasterBot
from storage import Storage

async def test():
    bot = MasterBot(Storage())
    bot._setup_handlers()
    print('Handlers setup OK')

if __name__ == '__main__':
    asyncio.run(test())
