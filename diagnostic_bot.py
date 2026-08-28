import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("DiagnosticBot")

async def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не задан в .env файле!")
        sys.exit(1)

    logger.info("🤖 Запуск диагностического бота...")
    bot = Bot(token=token)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        logger.info(f"📩 Получена команда /start от user_id={message.from_user.id} ({message.from_user.full_name})")
        await message.answer("✅ <b>Диагностический бот работает отлично!</b>\nПолучена команда <code>/start</code>.", parse_mode="HTML")

    @dp.message(F.text)
    async def echo(message: types.Message):
        logger.info(f"📩 Получено сообщение: '{message.text}' от user_id={message.from_user.id}")
        await message.answer(f"✅ <b>Получено сообщение:</b> {message.text}", parse_mode="HTML")

    try:
        me = await bot.get_me()
        logger.info(f"🟢 Подключено к Telegram API: @{me.username} (ID: {me.id})")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🚀 Запуск polling loop. Отправьте /start или любое сообщение боту...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка во время работы бота: {e}", exc_info=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
