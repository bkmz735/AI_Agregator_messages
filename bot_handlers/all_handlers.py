import logging
import html
import io
import asyncio
from typing import Any, Dict
from aiogram.filters import Command
from aiogram import types, F
import ui_keyboards as kb_ui

logger = logging.getLogger(__name__)

def setup_all_handlers(master_bot):
    dp = master_bot.dp

    from aiogram.filters import Command
    from aiogram import types, F
    
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        master_bot.current_menu_state = 'main'
        if master_bot.master_chat_id != message.chat.id:
            master_bot.master_chat_id = message.chat.id
            await master_bot.settings.update_master_chat_id(master_bot.master_chat_id)
            logger.info(f"New Master Chat ID set: {master_bot.master_chat_id}")
        try:
            await message.delete()
        except Exception:
            pass
        await master_bot.update_status_banner(master_bot.master_chat_id, force_new=True)
    
    @dp.message(F.text == "🏠 Главное меню")
    async def cmd_main_menu_button(message: types.Message):
        master_bot.current_menu_state = 'main'
        try:
            await message.delete()
        except Exception:
            pass
        await master_bot.update_status_banner(force_new=False)
    
    @dp.message(Command("help"))
    async def cmd_help(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        help_text = (
            "📖 <b>Справка по командам:</b>\n\n"
            "🔹 `/start` — Показать главное меню\n"
            "🔹 `/help` — Эта справка\n"
            "🔹 `/settings` (или ⚙️ Настройки) — Изменить интервал сводки, режим работы и автоудаление\n"
            "🔹 `/flush` (или 🚀 Отправить сводку) — Прислать сообщения из буфера прямо сейчас\n"
            "🔹 `/stats` (или 📊 Статистика) — Посмотреть статистику сообщений\n"
            "🔹 `/clear` (или 🧹 Очистить чат) — Стереть сообщения в чате\n\n"
            "🏛️ <b>Умный помощник:</b> Бот автоматически находит и выделяет штрафы, налоги и уведомления от Госуслуг!\n\n"
            "🎙️ <b>Расшифровка голосовых:</b> перешлите или отправьте голосовое сообщение, и оно автоматически переведется в текст!\n\n"
            "🤖 <b>Чат с ИИ:</b> Вы можете просто написать любой текст в чат (если бот не ждет от вас настройки), и умный ИИ ответит на ваш вопрос!"
        )
        await master_bot.show_or_edit_ui_panel(text=help_text, keyboard=kb_ui.get_help_keyboard(), force_new=False)
    
    @dp.message(F.voice | F.audio)
    async def handle_voice_message(message: types.Message):
        """Transcribes voice or audio messages via AI Multimodal API."""
        status_msg = await message.answer("🎙️ <i>Расшифровываю голосовое сообщение...</i>", parse_mode="HTML")
        try:
            voice_or_audio = message.voice or message.audio
            file_info = await master_bot.bot.get_file(voice_or_audio.file_id)
            audio_stream = io.BytesIO()
            await master_bot.bot.download_file(file_info.file_path, destination=audio_stream)
            audio_bytes = audio_stream.getvalue()
            
            mime_type = getattr(voice_or_audio, 'mime_type', 'audio/ogg') or 'audio/ogg'
            sender_name = message.from_user.full_name or message.from_user.username or "Пользователь"
    
            if master_bot.ai_engine:
                res = await master_bot.ai_engine.transcribe_and_analyze_audio(audio_bytes, mime_type=mime_type)
            else:
                from ai_engine import AudioAnalysisResult
                res = AudioAnalysisResult(
                    transcription="[Расшифровка недоступна]",
                    category="important",
                    summary="Голосовое сообщение",
                    action_required=True,
                    suggested_reply="Спасибо за сообщение!"
                )
    
            text_response = (
                f"🎙️ <b>РАСШИФРОВКА ГОЛОСОВОГО</b>\n\n"
                f"🗣️ <b>Текст записи:</b>\n<i>{html.escape(res.transcription)}</i>\n\n"
                f"📝 <b>Краткое содержание:</b>\n{html.escape(res.summary)}"
            )
    
            await status_msg.edit_text(text_response, parse_mode="HTML")
    
            # Also queue it in DB
            await master_bot.storage.save_message(
                msg_uid=f"tg_voice_{message.message_id}",
                channel="Telegram Voice",
                sender=sender_name,
                text=f"[Voice] {res.transcription}",
                category=res.category,
                summary=res.summary,
                action_required=res.action_required,
                suggested_reply=res.suggested_reply,
                is_delivered=True
            )
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            await status_msg.edit_text(f"❌ Ошибка расшифровки голосового: {e}")
    
    @dp.message(F.text.startswith("📥 Буфер"))
    async def cmd_buffer(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
            
        buffered_msgs = await master_bot.storage.get_buffered_messages(mark_as_delivered=False)
        buf_count = len(buffered_msgs)
        if buf_count > 0:
            senders = [msg['sender'] for msg in buffered_msgs]
            # Group senders and count them
            from collections import Counter
            sender_counts = Counter(senders)
            senders_str = ", ".join([f"<b>{s}</b>" + (f" ({c})" if c > 1 else "") for s, c in sender_counts.most_common(5)])
            if len(sender_counts) > 5:
                senders_str += " и другие"

            text = (
                f"📥 <b>В буфере ожидают отправки:</b> {buf_count} сообщ.\n"
                f"<i>От: {senders_str}</i>\n\n"
                "Нажмите «🚀 Отправить сводку», чтобы получить их прямо сейчас, или дождитесь отправки по расписанию."
            )
        else:
            text = (
                "📥 <b>Буфер пуст!</b> Новых сообщений для сводки пока нет.\n"
                "Бот собирает входящие письма и сообщения в фоновом режиме."
            )
        await master_bot.show_or_edit_ui_panel(text=text, keyboard=kb_ui.get_buffer_keyboard(buf_count), force_new=False)
    
    @dp.callback_query(F.data == "flush_now")
    async def process_flush_now_callback(callback_query: types.CallbackQuery):
        sent_count = await master_bot.flush_buffer_now()
        if sent_count == 0:
            await callback_query.answer("📥 Буфер пуст!", show_alert=True)
        else:
            await callback_query.answer("🚀 Сводка отправлена!")
        await master_bot.update_status_banner()
    
    @dp.message(F.text.startswith("🚀 Отправить сводку"))
    @dp.message(Command("flush"))
    async def cmd_send_digest(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
            
        try:
            sent_count = await master_bot.flush_buffer_now()
            if sent_count == 0:
                await master_bot.update_status_banner(force_new=True)
        except Exception as e:
            logger.error(f"Error in manual digest flush: {e}", exc_info=True)
    
    @dp.message(F.text.startswith("📊 Статистика"))
    @dp.message(Command("stats"))
    async def cmd_stats(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
    
        stats_msg = await master_bot._get_formatted_stats_text()
        await master_bot.show_or_edit_ui_panel(text=stats_msg, keyboard=kb_ui.get_stats_keyboard(), force_new=False)
    
    @dp.message(Command("logs"))
    @dp.message(Command("debug"))
    async def cmd_logs(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
        text, kb = await master_bot._get_diagnostic_logs_text_and_keyboard()
        await master_bot.show_or_edit_ui_panel(text=text, keyboard=kb)
    
    @dp.callback_query(F.data == "refresh_logs")
    async def process_refresh_logs(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_diagnostic_logs_text_and_keyboard()
        await master_bot.show_or_edit_ui_panel(text=text, keyboard=kb, force_new=False)
        await callback_query.answer("Логи обновлены!")
    
    @dp.message(F.text.startswith("⚙️ Настройки"))
    @dp.message(Command("settings"))
    async def cmd_settings(message: types.Message):
        master_bot.current_menu_state = 'settings'
        try:
            await message.delete()
        except Exception:
            pass
    
        text, kb = await master_bot._get_settings_text_and_keyboard()
        await master_bot.show_or_edit_ui_panel(text=text, keyboard=kb, force_new=False)
    
    # Handle inline settings menu navigation and callbacks
    @dp.callback_query(F.data == "settings_main_menu")
    async def process_settings_main_menu(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data == "settings_toggle_mode")
    async def process_settings_toggle_mode(callback_query: types.CallbackQuery):
        master_bot.delivery_mode = "instant" if master_bot.delivery_mode == "digest" else "digest"
        await master_bot.settings.update_delivery_mode(master_bot.delivery_mode)
        
        text, kb = await master_bot._get_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer("Режим отправки изменен!")

    @dp.callback_query(F.data == "settings_menu_content_filter")
    async def process_settings_menu_content_filter(callback_query: types.CallbackQuery):
        text = (
            "🎛️ <b>Фильтр контента</b>\n\n"
            "Здесь собраны все настройки модерации входящих сообщений:\n\n"
            "🚫 <b>Строгие Банворды</b> — удаление сообщений по точным словам.\n"
            "🧠 <b>Категории ИИ</b> — умная фильтрация спама, рекламы и различных тематик.\n"
            "📰 <b>Темы новостей</b> — управление тем, какие новости вам интересны, а какие нет."
        )
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_content_filter_keyboard(), parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data == "settings_menu_tg_channels")
    async def process_settings_menu_tg_channels(callback_query: types.CallbackQuery):
        await master_bot._show_tg_channels_page(1)
        await callback_query.answer()
    
    @dp.callback_query(F.data == "settings_menu_topics")
    async def process_settings_menu_topics(callback_query: types.CallbackQuery):
        await master_bot._show_topics_main_page()
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("topics_view_"))
    async def process_topics_view(callback_query: types.CallbackQuery):
        parts = callback_query.data.split("_")
        preference = parts[2]
        page = int(parts[3])
        await master_bot._show_topics_list_page(preference, page)
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("remove_topic_"))
    async def process_remove_topic(callback_query: types.CallbackQuery):
        parts = callback_query.data.split("_")
        preference = parts[2]
        idx_in_page = parts[3]
        page_val = int(parts[4])
        
        removed = await master_bot.storage.remove_news_topic(idx_in_page, preference=preference)
        if removed:
            await callback_query.answer("Тема удалена!")
        else:
            await callback_query.answer("Тема не найдена!")
        await master_bot._show_topics_list_page(preference, page_val)
    
    @dp.callback_query(F.data.startswith("add_topic_prompt_"))
    async def process_add_topic_prompt(callback_query: types.CallbackQuery):
        preference = callback_query.data.split("_")[-1]
        if preference == "liked":
            master_bot._waiting_for_liked_topic = True
            icon = "💚"
            pref_name = "Желаемой"
        else:
            master_bot._waiting_for_disliked_topic = True
            icon = "🛑"
            pref_name = "Запретной"
    
        text = (
            f"{icon} <b>Добавление {pref_name} темы</b>\n\n"
            "Отправьте тему следующим сообщением в чат.\n\n"
            "<i>Например:</i>\n"
            "• <code>IT технологии</code>\n"
            "• <code>Убийства</code>"
        )
        
        kb = kb_ui.get_add_topic_prompt_keyboard(preference)
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("tg_chan_page_"))
    async def process_tg_chan_page(callback_query: types.CallbackQuery):
        page_val = int(callback_query.data.split("_")[-1])
        await master_bot._show_tg_channels_page(page_val)
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("tg_chan_del_"))
    async def process_tg_chan_del(callback_query: types.CallbackQuery):
        parts = callback_query.data.split("_")
        chan_id = int(parts[3])
        page_val = int(parts[4]) if len(parts) > 4 else 1
    
        removed = await master_bot.storage.remove_tg_channel_by_id(chan_id)
        if removed:
            await callback_query.answer("Канал удален из отслеживания!")
        else:
            await callback_query.answer("Канал не найден!")
        await master_bot._show_tg_channels_page(page_val)
    
    @dp.callback_query(F.data == "tg_chan_add_prompt")
    async def process_tg_chan_add_prompt(callback_query: types.CallbackQuery):
        master_bot._waiting_for_tg_channel = True
        text = (
            "✏️ <b>Добавление ТГ-канала новостей</b>\n\n"
            "Отправьте юзернейм или ссылку на открытый Telegram-канал следующим сообщением в чат.\n\n"
            "<i>Примеры формата:</i>\n"
            "• <code>@mash</code>\n"
            "• <code>rian_ru</code>\n"
            "• <code>https://t.me/baza</code>"
        )
        try:
            await callback_query.message.edit_text(
                text=text,
                reply_markup=kb_ui.get_add_tg_channel_prompt_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data == "settings_menu_time")
    async def process_settings_menu_time(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_time_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data == "settings_menu_night")
    async def process_settings_menu_night(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_night_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data == "settings_menu_interval")
    async def process_settings_menu_interval(callback_query: types.CallbackQuery):
        text = (
            "⏱️ <b>Настройка интервала выгрузки сводки:</b>\n\n"
            f"Текущий интервал: <b>{master_bot.digest_interval} мин</b>\n"
            "Выберите новый интервал ниже:"
        )
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_interval_keyboard(), parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("set_interval_"))
    async def process_set_interval(callback_query: types.CallbackQuery):
        interval_val = int(callback_query.data.split("_")[-1])
        master_bot.digest_interval = interval_val
        await master_bot.settings.update_digest_interval_minutes(master_bot.digest_interval)
        
        text, kb = await master_bot._get_time_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer(f"Интервал изменен на {interval_val} минут!")
    
    @dp.callback_query(F.data == "settings_menu_autodelete")
    async def process_settings_menu_autodelete(callback_query: types.CallbackQuery):
        autodelete_label = f"<b>{master_bot.auto_delete_delay_hours} ч</b>" if master_bot.auto_delete_delay_hours > 0 else "<b>Выключено</b>"
        text = (
            "🗑️ <b>Настройка времени автоудаления сообщений:</b>\n\n"
            f"Текущее время автоудаления: {autodelete_label}\n"
            "Выберите время жизни сообщений бота в чате (по истечении которого они будут стерты):"
        )
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_autodelete_keyboard(), parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("set_autodelete_"))
    async def process_set_autodelete(callback_query: types.CallbackQuery):
        delay_val = int(callback_query.data.split("_")[-1])
        master_bot.auto_delete_delay_hours = delay_val
        await master_bot.settings.update_auto_delete_delay_hours(master_bot.auto_delete_delay_hours)
        
        text, kb = await master_bot._get_time_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        msg = f"Автоудаление изменено на {delay_val} ч!" if delay_val > 0 else "Автоудаление выключено!"
        await callback_query.answer(msg)
    
    @dp.callback_query(F.data == "settings_menu_timezone")
    async def process_settings_menu_timezone(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_timezone_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()

    @dp.callback_query(F.data == "settings_menu_ai")
    async def process_settings_menu_ai(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_ai_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()

    @dp.callback_query(F.data == "settings_toggle_ai_chat")
    async def process_settings_toggle_ai_chat(callback_query: types.CallbackQuery):
        current = await master_bot.settings.get_ai_text_chat_enabled()
        await master_bot.settings.update_ai_text_chat_enabled(not current)
        text, kb = await master_bot._get_ai_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        msg = "Умный чат включен!" if not current else "Умный чат выключен!"
        await callback_query.answer(msg)

    @dp.callback_query(F.data == "settings_toggle_ai_suggestions")
    async def process_settings_toggle_ai_suggestions(callback_query: types.CallbackQuery):
        current = await master_bot.settings.get_ai_suggestions_enabled()
        await master_bot.settings.update_ai_suggestions_enabled(not current)
        text, kb = await master_bot._get_ai_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        msg = "Подсказки ИИ включены!" if not current else "Подсказки ИИ выключены!"
        await callback_query.answer(msg)

    @dp.callback_query(F.data == "settings_menu_ai_filters")
    async def process_settings_menu_ai_filters(callback_query: types.CallbackQuery):
        text, kb = await master_bot._get_ai_filters_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()

    @dp.callback_query(F.data.startswith("toggle_ai_filter_"))
    async def process_toggle_ai_filter(callback_query: types.CallbackQuery):
        category = callback_query.data.replace("toggle_ai_filter_", "")
        new_state = await master_bot.settings.toggle_ai_category_filter(category)
        text, kb = await master_bot._get_ai_filters_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        msg = f"Категория {category}: {'Пропускать' if new_state else 'Фильтровать'}!"
        await callback_query.answer(msg)

    @dp.callback_query(F.data.startswith("set_tz_"))
    async def process_set_timezone(callback_query: types.CallbackQuery):
        offset = int(callback_query.data.replace("set_tz_", ""))
        master_bot.timezone_offset = offset
        await master_bot.settings.update_timezone_offset(offset)
        text, kb = await master_bot._get_timezone_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer(f"Часовой пояс изменен на UTC{'+' if offset >= 0 else ''}{offset}!")
    
    @dp.callback_query(F.data == "settings_toggle_night_mode")
    async def process_toggle_night_mode(callback_query: types.CallbackQuery):
        master_bot.night_mode_enabled = not master_bot.night_mode_enabled
        await master_bot.settings.update_night_mode_enabled(master_bot.night_mode_enabled)
        
        text, kb = await master_bot._get_night_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        msg = "Ночной режим включен! 🌙" if master_bot.night_mode_enabled else "Ночной режим выключен!"
        await callback_query.answer(msg)
    
    @dp.callback_query(F.data == "settings_menu_night_hours")
    async def process_settings_menu_night_hours(callback_query: types.CallbackQuery):
        text = (
            "🌙 <b>Настройка часов тишины ночного режима:</b>\n\n"
            f"Текущий интервал: <b>{master_bot.night_start_hour:02d}:00 - {master_bot.night_end_hour:02d}:00</b>\n"
            "Выберите удобный промежуток сна (в это время ИИ отключается, а сообщения не беспокоят):"
        )
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_nighthours_keyboard(), parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("set_nighthours_"))
    async def process_set_nighthours(callback_query: types.CallbackQuery):
        parts = callback_query.data.split("_")
        start_h, end_h = int(parts[2]), int(parts[3])
        master_bot.night_start_hour = start_h
        master_bot.night_end_hour = end_h
        
        await master_bot.settings.update_night_start_hour(start_h)
        await master_bot.settings.update_night_end_hour(end_h)
        
        text, kb = await master_bot._get_night_settings_text_and_keyboard()
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer(f"Часы тишины установлены: {start_h:02d}:00 - {end_h:02d}:00!")
    
    @dp.callback_query(F.data == "settings_menu_blacklist")
    async def process_settings_menu_blacklist(callback_query: types.CallbackQuery):
        bws_email = await master_bot.storage.get_banwords(scope="email")
        bws_vk = await master_bot.storage.get_banwords(scope="vk")
        
        text = (
            "🚫 <b>Управление банвордами</b>\n\n"
            "Выберите категорию для просмотра списка и управления банвордами:\n\n"
            f"✉️ <b>Mail.ru:</b> {len(bws_email)} банвордов\n"
            f"💬 <b>ВКонтакте (VK):</b> {len(bws_vk)} банвордов"
        )
    
        try:
            await callback_query.message.edit_text(text=text, reply_markup=kb_ui.get_blacklist_menu_keyboard(len(bws_email), len(bws_vk)), parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("bw_view_email_"))
    async def process_bw_view_email(callback_query: types.CallbackQuery):
        page = int(callback_query.data.replace("bw_view_email_", ""))
        bws = await master_bot.storage.get_banwords(scope="email")
        
        per_page = 9
        total_pages = max(1, (len(bws) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        page_bws = bws[start_idx:start_idx + per_page]
    
        lines = [f"✉️ <b>Банворды Mail.ru</b>\n<i>(Стр. {page}/{total_pages}, всего: {len(bws)})</i>\n"]
        if not bws:
            lines.append("<i>Список банвордов Mail.ru пуст.</i>")
        else:
            for idx_in_page, b in enumerate(page_bws, start=start_idx + 1):
                lines.append(f"{idx_in_page}. <code>{html.escape(b['word'])}</code>")
            lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления:</i>")
    
        kb = kb_ui.get_banwords_list_keyboard(page_bws, page, total_pages, "email", start_idx)
        try:
            await callback_query.message.edit_text(text="\n".join(lines), reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("bw_view_vk_"))
    async def process_bw_view_vk(callback_query: types.CallbackQuery):
        page = int(callback_query.data.replace("bw_view_vk_", ""))
        bws = await master_bot.storage.get_banwords(scope="vk")
        
        per_page = 9
        total_pages = max(1, (len(bws) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        page_bws = bws[start_idx:start_idx + per_page]
    
        lines = [f"💬 <b>Банворды ВКонтакте</b>\n<i>(Стр. {page}/{total_pages}, всего: {len(bws)})</i>\n"]
        if not bws:
            lines.append("<i>Список банвордов VK пуст.</i>")
        else:
            for idx_in_page, b in enumerate(page_bws, start=start_idx + 1):
                lines.append(f"{idx_in_page}. <code>{html.escape(b['word'])}</code>")
            lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления:</i>")
    
        kb = kb_ui.get_banwords_list_keyboard(page_bws, page, total_pages, "vk", start_idx)
        try:
            await callback_query.message.edit_text(text="\n".join(lines), reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data.startswith("remove_bw_email_"))
    async def process_remove_bw_email(callback_query: types.CallbackQuery):
        parts = callback_query.data.replace("remove_bw_email_", "").split("_")
        idx = parts[0]
        page = parts[1] if len(parts) > 1 else "1"
        await master_bot.storage.remove_banword(idx, scope="email")
        callback_query.data = f"bw_view_email_{page}"
        await process_bw_view_email(callback_query)
    
    @dp.callback_query(F.data.startswith("remove_bw_vk_"))
    async def process_remove_bw_vk(callback_query: types.CallbackQuery):
        parts = callback_query.data.replace("remove_bw_vk_", "").split("_")
        idx = parts[0]
        page = parts[1] if len(parts) > 1 else "1"
        await master_bot.storage.remove_banword(idx, scope="vk")
        callback_query.data = f"bw_view_vk_{page}"
        await process_bw_view_vk(callback_query)
    
    @dp.callback_query(F.data == "add_bw_select_scope")
    async def process_add_bw_select_scope(callback_query: types.CallbackQuery):
        await callback_query.answer()
        try:
            await callback_query.message.edit_text(
                "➕ <b>Выберите категорию для добавления банворда:</b>",
                reply_markup=kb_ui.get_add_bw_select_scope_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    @dp.callback_query(F.data == "add_bw_prompt_email")
    async def process_add_bw_prompt_email(callback_query: types.CallbackQuery):
        await callback_query.answer()
        master_bot._waiting_for_banword_scope = "email"
        try:
            await callback_query.message.edit_text(
                "✏️ <b>Отправьте слово или фразу для добавления (Mail.ru):</b>",
                reply_markup=kb_ui.get_add_banword_prompt_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    @dp.callback_query(F.data == "add_bw_prompt_vk")
    async def process_add_bw_prompt_vk(callback_query: types.CallbackQuery):
        await callback_query.answer()
        master_bot._waiting_for_banword_scope = "vk"
        try:
            await callback_query.message.edit_text(
                "✏️ <b>Отправьте слово или фразу для добавления (VK):</b>",
                reply_markup=kb_ui.get_add_banword_prompt_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    
    
    @dp.message(Command("block"))
    async def cmd_block(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            sent_msg = await message.answer(
                "⚠️ <b>Использование /block:</b>\n"
                "• <code>/block слово</code> (для всех каналов)\n"
                "• <code>/block слово email</code> (для Mail.ru)\n"
                "• <code>/block слово vk</code> (для VK)",
                parse_mode="HTML"
            )
        else:
            word = args[1].strip()
            scope = args[2].strip().lower() if len(args) >= 3 else "global"
            if scope not in ("email", "vk", "global"):
                scope = "global"
            res = await master_bot.storage.add_banword(word, scope)
            if res:
                scope_label = "Общий" if res['scope'] == 'global' else res['scope'].upper()
                sent_msg = await message.answer(
                    f"🚫 Банворд #{res['id']} <b>«{html.escape(res['word'])}»</b> ({scope_label}) добавлен!",
                    parse_mode="HTML"
                )
            else:
                sent_msg = await message.answer(f"ℹ️ Банворд <b>«{html.escape(word)}»</b> уже есть в списке.", parse_mode="HTML")
        await master_bot.storage.save_sent_notification(chat_id=master_bot.master_chat_id, message_id=sent_msg.message_id, delay_seconds=10)
    
    @dp.message(Command("unblock"))
    async def cmd_unblock(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            sent_msg = await message.answer(
                "⚠️ <b>Использование /unblock:</b>\n"
                "• <code>/unblock номер email</code> (удалить из Mail.ru)\n"
                "• <code>/unblock номер vk</code> (удалить из VK)\n"
                "• <code>/unblock слово</code> (удалить слово по названию)",
                parse_mode="HTML"
            )
        else:
            target = args[1].strip()
            scope = args[2].strip().lower() if len(args) >= 3 else None
            deleted_word = await master_bot.storage.remove_banword(target, scope=scope)
            if deleted_word:
                sent_msg = await message.answer(f"✅ Банворд <b>«{html.escape(deleted_word)}»</b> удален из списка!", parse_mode="HTML")
            else:
                sent_msg = await message.answer(f"ℹ️ Банворд <b>«{html.escape(target)}»</b> не найден.", parse_mode="HTML")
        await master_bot.storage.save_sent_notification(chat_id=master_bot.master_chat_id, message_id=sent_msg.message_id, delay_seconds=10)
    
    @dp.message(Command("reset_banwords"))
    async def cmd_reset_banwords(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
        await master_bot.storage.reset_banwords_to_default()
        sent_msg = await message.answer("🔄 Все банворды сброшены к базовым системным настройкам!", parse_mode="HTML")
        await master_bot.storage.save_sent_notification(chat_id=master_bot.master_chat_id, message_id=sent_msg.message_id, delay_seconds=10)
    
    @dp.message(Command("banwords"))
    @dp.message(Command("blacklist"))
    async def cmd_blacklist(message: types.Message):
        try:
            await message.delete()
        except Exception:
            pass
        bws = await master_bot.storage.get_banwords()
        
        lines = ["🚫 <b>Единый список банвордов (Banwords)</b>\n"]
        globals_list = [b for b in bws if b.get("scope", "global") == "global"]
        emails_list = [b for b in bws if b.get("scope") == "email"]
        vks_list = [b for b in bws if b.get("scope") == "vk"]
    
        if globals_list:
            lines.append("🌐 <b>Общие (для всех каналов):</b>")
            for b in globals_list:
                lines.append(f"{b['id']}. <code>{html.escape(b['word'])}</code>")
            lines.append("")
    
        if emails_list:
            lines.append("✉️ <b>Mail.ru / Email:</b>")
            for b in emails_list:
                lines.append(f"{b['id']}. <code>{html.escape(b['word'])}</code>")
            lines.append("")
    
        if vks_list:
            lines.append("💬 <b>ВКонтакте (VK):</b>")
            for b in vks_list:
                lines.append(f"{b['id']}. <code>{html.escape(b['word'])}</code>")
            lines.append("")
    
    
        
        inline_kb = kb_ui.get_home_only_keyboard()
        await master_bot.show_or_edit_ui_panel(text="\n".join(lines), keyboard=inline_kb)
    
    @dp.callback_query(F.data == "confirm_reset_stats")
    async def process_confirm_reset_stats(callback_query: types.CallbackQuery):
        inline_kb = kb_ui.get_confirm_reset_stats_keyboard()
        try:
            await callback_query.message.edit_text(
                "⚠️ <b>Вы действительно хотите сбросить всю накопленную статистику сообщений?</b>",
                reply_markup=inline_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback_query.answer()
    
    @dp.callback_query(F.data == "do_reset_stats")
    async def process_do_reset_stats(callback_query: types.CallbackQuery):
        await master_bot.storage.reset_stats()
        stats_msg = await master_bot._get_formatted_stats_text(" (Сброшено ✅)")
        
        inline_kb = kb_ui.get_stats_keyboard()
        try:
            await callback_query.message.edit_text(stats_msg, reply_markup=inline_kb, parse_mode="HTML")
        except Exception:
            pass
        await callback_query.answer("Статистика успешно сброшена!")
    
    @dp.callback_query(F.data == "cmd_buf_inline")
    async def process_cmd_buf_inline(callback_query: types.CallbackQuery):
        await callback_query.answer()
        master_bot.current_menu_state = 'buffer'
        buffered_msgs = await master_bot.storage.get_buffered_messages(mark_as_delivered=False)
        buf_count = len(buffered_msgs)
        if buf_count > 0:
            senders = [msg['sender'] for msg in buffered_msgs]
            from collections import Counter
            sender_counts = Counter(senders)
            senders_str = ", ".join([f"<b>{s}</b>" + (f" ({c})" if c > 1 else "") for s, c in sender_counts.most_common(5)])
            if len(sender_counts) > 5:
                senders_str += " и другие"

            text = (
                f"📥 <b>В буфере ожидают отправки:</b> {buf_count} сообщ.\n"
                f"<i>От: {senders_str}</i>\n\n"
                "Нажмите «🚀 Отправить сводку» для немедленного получения."
            )
        else:
            text = (
                "📥 <b>Буфер пуст!</b> Новых сообщений для сводки пока нет.\n"
                "Бот собирает входящие письма и сообщения в фоновом режиме."
            )
        kb = kb_ui.get_buffer_keyboard(buf_count)
    
        await master_bot.show_or_edit_ui_panel(text=text, keyboard=kb)
    
    @dp.callback_query(F.data == "cmd_stats_inline")
    async def process_cmd_stats_inline(callback_query: types.CallbackQuery):
        await callback_query.answer()
        master_bot.current_menu_state = 'stats'
        stats_msg = await master_bot._get_formatted_stats_text()
        inline_kb = kb_ui.get_stats_keyboard()
        await master_bot.show_or_edit_ui_panel(text=stats_msg, keyboard=inline_kb)
    
    @dp.callback_query(F.data == "prompt_clear_chat")
    @dp.message(Command("clear"))
    @dp.message(F.text.startswith("🧹 Очистить чат"))
    async def cmd_clear_chat(event: Any):
        master_bot.current_menu_state = 'main'
        if isinstance(event, types.Message):
            try:
                await event.delete()
            except Exception:
                pass
        elif isinstance(event, types.CallbackQuery):
            await event.answer()
    
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        text = "⚠️ <b>Вы действительно хотите очистить последние сообщения в чате?</b>\n<i>(Сообщения останутся в базе данных)</i>"
        await master_bot.show_or_edit_ui_panel(text=text, keyboard=kb_ui.get_clear_chat_prompt_keyboard(), force_new=False)
    
    # Handle inline "Close / Cancel" button click — returns UI to active status banner with ReplyKeyboard refreshed
    @dp.callback_query(F.data == "delete_msg")
    async def process_delete_msg(callback_query: types.CallbackQuery):
        await master_bot.update_status_banner(callback_query.message.chat.id, force_new=True)
        await callback_query.answer()
    
    @dp.callback_query(F.data == "delete_this_message")
    async def process_delete_this_message(callback_query: types.CallbackQuery):
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        # Refresh the active banner so that the bottom reply buttons reappear at the bottom
        await master_bot.update_status_banner(callback_query.message.chat.id, force_new=True)
        await callback_query.answer()
    
    # Handle inline confirmation of chat clearing
    @dp.callback_query(F.data == "confirm_clear_chat")
    async def process_confirm_clear_chat(callback_query: types.CallbackQuery):
        await callback_query.answer("Очистка чата...")
        
        # Reset UI msg id so fresh status banner is sent after purge
        master_bot._last_ui_msg_id = None
        target_chat = callback_query.message.chat.id
        current_id = callback_query.message.message_id
    
        async def _do_delete_bg():
            for msg_id in range(current_id, current_id - 30, -1):
                try:
                    await master_bot.bot.delete_message(chat_id=target_chat, message_id=msg_id)
                except Exception:
                    pass
    
            await master_bot.update_status_banner(target_chat)
    
        asyncio.create_task(_do_delete_bg())
    
    @dp.callback_query(F.data.startswith("ai_confirm_"))
    async def process_ai_action_confirm(callback_query: types.CallbackQuery):
        action_id = callback_query.data.replace("ai_confirm_", "")
        action_data = master_bot.pending_ai_actions.pop(action_id, None)
        
        if not action_data:
            await callback_query.answer("Действие устарело.", show_alert=True)
            await callback_query.message.edit_reply_markup(reply_markup=None)
            return
            
        action = action_data.get("action")
        args = action_data.get("args", {})
        user_text = action_data.get("user_text", "")
        
        try:
            if action == "add_banword":
                word = args.get("word")
                await master_bot.storage.add_spam_keyword(word)
                result_msg = f"✅ Банворд «{word}» добавлен ИИ."
            elif action == "add_news_topic":
                topic = args.get("topic")
                pref = args.get("preference")
                await master_bot.storage.add_news_topic(topic, pref)
                result_msg = f"✅ Тема «{topic}» добавлена ИИ ({pref})."
            elif action == "remove_news_topic":
                topic = args.get("topic")
                pref = args.get("preference")
                await master_bot.storage.remove_news_topic(topic, pref)
                result_msg = f"✅ Тема «{topic}» удалена ИИ ({pref})."
            elif action == "add_tg_channel":
                channel = args.get("channel_username")
                await master_bot.storage.add_tg_channel(channel)
                result_msg = f"✅ Telegram канал «{channel}» добавлен ИИ."
            elif action == "clear_chat":
                await master_bot.storage.clear_all_messages()
                result_msg = "✅ История сообщений полностью очищена."
            else:
                result_msg = "❌ Неизвестное действие."
                
            await master_bot.storage.add_ai_chat_message("user", user_text)
            await master_bot.storage.add_ai_chat_message("model", result_msg)
            
            await callback_query.message.edit_text(f"{callback_query.message.text}\n\n{result_msg}", parse_mode="HTML")
        except Exception as e:
            await callback_query.message.edit_text(f"❌ Ошибка выполнения: {e}")
    
    @dp.callback_query(F.data.startswith("ai_reject_"))
    async def process_ai_action_reject(callback_query: types.CallbackQuery):
        action_id = callback_query.data.replace("ai_reject_", "")
        action_data = master_bot.pending_ai_actions.pop(action_id, None)
        
        if action_data:
            user_text = action_data.get("user_text", "")
            await master_bot.storage.add_ai_chat_message("user", user_text)
            await master_bot.storage.add_ai_chat_message("model", "Пользователь отменил действие.")
            
        await callback_query.message.edit_text(f"{callback_query.message.text}\n\n❌ Действие отменено.", parse_mode="HTML")


    @dp.message(F.text, ~F.text.startswith("/"))
    async def handle_text_message(message: types.Message):
        # If user tapped a ReplyButton while in input mode, cancel pending inputs
    
        if master_bot._waiting_for_tg_channel:
            master_bot._waiting_for_tg_channel = False
            raw_input = message.text.strip()
            try:
                await message.delete()
            except Exception:
                pass
    
            added_id = await master_bot.storage.add_tg_channel(raw_input)
            clean_user = raw_input.strip().lstrip("@").lower()
            if "t.me/" in clean_user:
                clean_user = clean_user.split("t.me/")[-1].split("/")[0].strip()
    
            if added_id:
                sent_msg = await message.answer(f"✅ Канал <b>«@{html.escape(clean_user)}»</b> добавлен в отслеживание!", parse_mode="HTML")
            else:
                sent_msg = await message.answer(f"ℹ️ Канал <b>«@{html.escape(clean_user)}»</b> уже есть в отслеживании.", parse_mode="HTML")
    
            await master_bot.storage.save_sent_notification(chat_id=master_bot.master_chat_id, message_id=sent_msg.message_id, delay_seconds=10)
            await master_bot._show_tg_channels_page(1)
            return
            
        if master_bot._waiting_for_liked_topic or master_bot._waiting_for_disliked_topic:
            preference = "liked" if master_bot._waiting_for_liked_topic else "disliked"
            master_bot._waiting_for_liked_topic = False
            master_bot._waiting_for_disliked_topic = False
            
            raw_input = message.text.strip()
            try:
                await message.delete()
            except Exception:
                pass
                
            added = await master_bot.storage.add_news_topic(raw_input, preference=preference)
            pref_name = "Желаемые" if preference == "liked" else "Запретные"
            
            if added:
                sent_msg = await message.answer(f"✅ Тема <b>«{html.escape(raw_input)}»</b> добавлена в {pref_name}!", parse_mode="HTML")
            else:
                sent_msg = await message.answer(f"ℹ️ Тема <b>«{html.escape(raw_input)}»</b> уже есть в {pref_name}.", parse_mode="HTML")
                
            await master_bot.storage.save_sent_notification(chat_id=master_bot.master_chat_id, message_id=sent_msg.message_id, delay_seconds=10)
            await master_bot._show_topics_list_page(preference, 1)
            return
    
        # Check if bot is waiting for interactive banword text input
        if master_bot._waiting_for_banword_scope:
            word_to_add = message.text.strip()
            scope = master_bot._waiting_for_banword_scope
            master_bot._waiting_for_banword_scope = None
    
            try:
                await message.delete()
            except Exception:
                pass
    
            added = await master_bot.storage.add_banword(word_to_add, scope=scope)
            scope_name = "Mail.ru" if scope == "email" else ("ВКонтакте" if scope == "vk" else "Общие")
    
            if added:
                sent_msg = await message.answer(f"✅ Банворд <b>«{html.escape(word_to_add)}»</b> успешно добавлен в {scope_name}!", parse_mode="HTML")
            else:
                sent_msg = await message.answer(f"ℹ️ Банворд <b>«{html.escape(word_to_add)}»</b> уже есть в {scope_name}.", parse_mode="HTML")
    
            await master_bot.storage.save_sent_notification(chat_id=master_bot.master_chat_id, message_id=sent_msg.message_id, delay_seconds=10)
            
            # Refresh UI panel to show banword list cleanly (per_page = 9)
            bws = await master_bot.storage.get_banwords(scope=scope)
            per_page = 9
            total_pages = max(1, (len(bws) + per_page - 1) // per_page)
            page_bws = bws[:per_page]
    
            lines = [f"{'✉️' if scope == 'email' else '💬'} <b>Банворды {scope_name}</b>\n<i>(Стр. 1/{total_pages}, всего: {len(bws)})</i>\n"]
            if not bws:
                lines.append(f"<i>Список банвордов {scope_name} пуст.</i>")
            else:
                for idx_in_page, b in enumerate(page_bws, start=1):
                    lines.append(f"{idx_in_page}. <code>{html.escape(b['word'])}</code>")
                lines.append("\n📌 <i>Нажмите ❌ #№ ниже для удаления:</i>")
    
            kb = kb_ui.get_banwords_list_keyboard(page_bws, 1, total_pages, scope, 0)
            await master_bot.show_or_edit_ui_panel(text="\n".join(lines), keyboard=kb, force_new=False)
            return

        # If not waiting for anything and not a menu button, it's a direct AI question!
        chat_enabled = await master_bot.settings.get_ai_text_chat_enabled()
        if master_bot.current_menu_state != 'main' or not chat_enabled:
            sent_msg = await message.answer("⚠️ <b>Чат с ИИ недоступен</b>\nФункция отключена в настройках или вы находитесь не в Главном меню.", parse_mode="HTML")
            await master_bot.storage.save_sent_notification(chat_id=message.chat.id, message_id=sent_msg.message_id, delay_seconds=5)
            return

        if master_bot.user_agent:
            status_msg = await message.answer("⏳ <i>ИИ думает...</i>", parse_mode="HTML")
            try:
                result = await master_bot.user_agent.process_message(message.text)
                reply_text = result.get("text", "Ошибка ИИ.")
                pending_action = result.get("pending_action")
                
                if pending_action:
                    action_name = pending_action.get("action")
                    args = pending_action.get("args", {})
                    user_text = pending_action.get("user_text", "")
                    
                    if action_name in ["set_timezone", "set_digest_interval"]:
                        if action_name == "set_timezone":
                            offset = int(args.get("offset_hours", 0))
                            await master_bot.settings.update_timezone_offset(offset)
                            master_bot.timezone_offset = offset
                            master_bot.start_digest_scheduler()
                            result_msg = f"✅ Часовой пояс изменен на UTC{'+' if offset >= 0 else ''}{offset}."
                        elif action_name == "set_digest_interval":
                            mins = int(args.get("minutes", 60))
                            await master_bot.settings.update_digest_interval_minutes(mins)
                            master_bot.start_digest_scheduler()
                            result_msg = f"✅ Интервал сводок изменен на {mins} минут."
                            
                        await master_bot.storage.add_ai_chat_message("user", user_text)
                        await master_bot.storage.add_ai_chat_message("model", result_msg)
                        
                        await status_msg.edit_text(result_msg, parse_mode="HTML")
                        
                        async def delayed_delete(msg):
                            await asyncio.sleep(5)
                            try:
                                await msg.delete()
                            except:
                                pass
                        asyncio.create_task(delayed_delete(status_msg))
                    else:
                        import uuid
                        action_id = str(uuid.uuid4())[:8]
                        master_bot.pending_ai_actions[action_id] = pending_action
                        await status_msg.edit_text(reply_text, parse_mode="HTML", reply_markup=kb_ui.get_ai_action_confirm_keyboard(action_id))
                else:
                    await status_msg.edit_text(reply_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"AI Chat error: {e}")
                await status_msg.edit_text(f"❌ Ошибка: {e}")
        elif master_bot.ai_engine:
            status_msg = await message.answer("⏳ <i>ИИ думает...</i>", parse_mode="HTML")
            try:
                response = await master_bot.ai_engine.ask_ai_question(message.text)
                await status_msg.edit_text(f"🤖 <b>Ответ ИИ:</b>\n\n{html.escape(response)}", parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error asking AI question: {e}")
                await status_msg.edit_text(f"❌ Ошибка обращения к ИИ: {e}")
        else:
            await message.answer("🤖 ИИ не настроен. Для работы этой функции требуется API-ключ.")
    
