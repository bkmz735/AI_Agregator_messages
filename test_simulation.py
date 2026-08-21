import asyncio
import logging
import os
import sys
from main import MessageAggregatorApp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("TestSimulation")

TEST_MESSAGES = [
    {
        "channel": "Авито (Email)",
        "sender": "Покупатель Алексей",
        "text": "Здравствуйте! Срочно куплю ваш ноутбук за наличные, напишите номер для связи!",
        "msg_uid": "test_avito_urgent_002"
    },
    {
        "channel": "VK",
        "sender": "Группа Спам",
        "text": "Срочный вывод средств! Забери свой бонус 50 000 рублей по ссылке!",
        "msg_uid": "test_vk_spam_002"
    },
    {
        "channel": "Instagram (Email)",
        "sender": "Ольга Маркетинг",
        "text": "Привет! Предлагаем бартерное сотрудничество по рекламе на 50k подписчиков.",
        "msg_uid": "test_insta_buffer_002"
    },
    {
        "channel": "Telegram",
        "sender": "Чат Соседей",
        "text": "Ребята, кто-нибудь знает, во сколько сегодня включают горячую воду?",
        "msg_uid": "test_tg_buffer_002"
    }
]

async def run_test():
    logger.info("Initializing App for Buffer & Digest Test...")
    app = MessageAggregatorApp()
    await app.storage.init_db()

    logger.info("\n--- SIMULATING INCOMING MESSAGES ---\n")
    for msg in TEST_MESSAGES:
        await app.process_incoming_message(
            channel=msg["channel"],
            sender=msg["sender"],
            text=msg["text"],
            msg_uid=msg["msg_uid"]
        )
        await asyncio.sleep(0.5)

    buf_count = await app.storage.get_buffer_count()
    logger.info(f"\n📥 Current Buffer Count: {buf_count} messages pending.")

    logger.info("\n🚀 FLUSHING BUFFER (MANUAL DIGEST)...")
    flushed = await app.bot.flush_buffer_now()
    logger.info(f"Flushed {flushed} messages from buffer.")

    logger.info("\n--- FETCHING AGGREGATED STATS ---")
    stats = await app.storage.get_stats()
    logger.info(f"Final DB Statistics: {stats}")

if __name__ == "__main__":
    asyncio.run(run_test())
