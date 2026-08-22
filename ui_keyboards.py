"""
ui_keyboards.py — Единый модуль генерации клавиатур (Reply & Inline) для Telegram бота.
Все кнопки и их компоновка изолированы здесь.
"""
from typing import Optional, List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_home_button() -> InlineKeyboardButton:
    """Стандартная инлайн-кнопка возврата в Главное меню."""
    return InlineKeyboardButton(text="🏠 Главное меню", callback_data="delete_msg")


def get_main_reply_keyboard(buffer_count: int = 0) -> ReplyKeyboardMarkup:
    """Нижняя постоянная Reply-клавиатура Telegram для быстрого перехода по разделам."""
    if buffer_count > 0:
        kb = [
            [KeyboardButton(text=f"📥 Буфер ({buffer_count})"), KeyboardButton(text="🚀 Отправить сводку")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🧹 Очистить чат")]
        ]
    else:
        kb = [
            [KeyboardButton(text="📥 Буфер")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🧹 Очистить чат")]
        ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)


def get_settings_keyboard(delivery_mode: str) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура основного экрана Настроек."""
    mode_btn_text = f"⚡ Режим: {'Сводка' if delivery_mode == 'instant' else 'Сразу'}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Управление Банвордами", callback_data="settings_menu_blacklist")],
        [InlineKeyboardButton(text="⏱️ Время и Таймеры", callback_data="settings_menu_time")],
        [InlineKeyboardButton(text="🌙 Ночной режим", callback_data="settings_menu_night")],
        [
            InlineKeyboardButton(text=mode_btn_text, callback_data="settings_toggle_mode"),
            InlineKeyboardButton(text="🧹 Очистить чат", callback_data="prompt_clear_chat")
        ],
        [get_home_button()]
    ])


def get_time_settings_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура подменю «Время и Таймеры»."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱️ Изменить интервал сводки", callback_data="settings_menu_interval")],
        [InlineKeyboardButton(text="🗑️ Изменить время автоудаления", callback_data="settings_menu_autodelete")],
        [InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="settings_main_menu")],
        [get_home_button()]
    ])


def get_night_settings_keyboard(night_mode_enabled: bool) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура подменю «Ночной режим»."""
    toggle_text = "🌙 Включить ночной режим 🟢" if not night_mode_enabled else "🌙 Выключить ночной режим ❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="settings_toggle_night_mode")],
        [InlineKeyboardButton(text="⏰ Часы ночного режима", callback_data="settings_menu_night_hours")],
        [InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="settings_main_menu")],
        [get_home_button()]
    ])


def get_interval_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура выбора интервала сводки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="15 мин", callback_data="set_interval_15"),
            InlineKeyboardButton(text="30 мин", callback_data="set_interval_30"),
            InlineKeyboardButton(text="1 час (60м)", callback_data="set_interval_60")
        ],
        [
            InlineKeyboardButton(text="2 часа (120м)", callback_data="set_interval_120"),
            InlineKeyboardButton(text="4 часа (240м)", callback_data="set_interval_240")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu_time")],
        [get_home_button()]
    ])


def get_autodelete_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура выбора времени резервного автоудаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отключить ❌", callback_data="set_autodelete_0"),
            InlineKeyboardButton(text="1 час", callback_data="set_autodelete_1"),
            InlineKeyboardButton(text="2 часа", callback_data="set_autodelete_2")
        ],
        [
            InlineKeyboardButton(text="4 часа", callback_data="set_autodelete_4"),
            InlineKeyboardButton(text="8 часов", callback_data="set_autodelete_8"),
            InlineKeyboardButton(text="24 часа", callback_data="set_autodelete_24")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu_time")],
        [get_home_button()]
    ])


def get_nighthours_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура выбора часов тишины ночного режима."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="23:00 - 07:00", callback_data="set_nighthours_23_7"),
            InlineKeyboardButton(text="00:00 - 08:00", callback_data="set_nighthours_0_8")
        ],
        [
            InlineKeyboardButton(text="22:00 - 06:00", callback_data="set_nighthours_22_6"),
            InlineKeyboardButton(text="01:00 - 09:00", callback_data="set_nighthours_1_9")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_menu_night")],
        [get_home_button()]
    ])


def get_blacklist_menu_keyboard(email_count: int, vk_count: int) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура меню выбора категорий банвордов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"✉️ Mail.ru ({email_count})", callback_data="bw_view_email_1"),
            InlineKeyboardButton(text=f"💬 ВКонтакте ({vk_count})", callback_data="bw_view_vk_1")
        ],
        [InlineKeyboardButton(text="➕ Добавить банворд", callback_data="add_bw_select_scope")],
        [InlineKeyboardButton(text="🔄 Сбросить все к базовым", callback_data="reset_banwords_confirm")],
        [InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="settings_main_menu")],
        [get_home_button()]
    ])


def get_add_bw_select_scope_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура выбора категории при добавлении нового банворда."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✉️ Mail.ru", callback_data="add_bw_prompt_email"),
            InlineKeyboardButton(text="💬 ВКонтакте", callback_data="add_bw_prompt_vk")
        ],
        [InlineKeyboardButton(text="🔙 К категориям банвордов", callback_data="settings_menu_blacklist")],
        [get_home_button()]
    ])


def get_banwords_list_keyboard(page_bws: List[Dict[str, Any]], page: int, total_pages: int, scope: str, start_idx: int) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура со списком банвордов конкретной категории (Mail.ru или VK)."""
    rows = []
    row_buttons = []
    for idx_in_page, _ in enumerate(page_bws, start=start_idx + 1):
        row_buttons.append(InlineKeyboardButton(text=f"❌ #{idx_in_page}", callback_data=f"remove_bw_{scope}_{idx_in_page}_{page}"))
        if len(row_buttons) == 3:
            rows.append(row_buttons)
            row_buttons = []
    if row_buttons:
        rows.append(row_buttons)

    # Кнопки пагинации
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"bw_view_{scope}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="➕ Добавить банворд", callback_data=f"add_bw_prompt_{scope}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"bw_view_{scope}_{page + 1}"))
    rows.append(nav_row)

    rows.append([InlineKeyboardButton(text="🔙 К категориям банвордов", callback_data="settings_menu_blacklist")])
    rows.append([get_home_button()])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_add_banword_prompt_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура на экране отельного ввода банворда."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_menu_blacklist")],
        [get_home_button()]
    ])


def get_stats_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура экрана Статистики."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="confirm_reset_stats")],
        [get_home_button()]
    ])


def get_buffer_keyboard(buffer_count: int) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура экрана Буфера."""
    if buffer_count > 0:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Отправить сводку", callback_data="flush_now")],
            [get_home_button()]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [get_home_button()]
    ])


def get_help_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура экрана Справки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [get_home_button()]
    ])


def get_logs_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура экрана Логов диагностики."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить логи", callback_data="refresh_logs")],
        [get_home_button()]
    ])


def get_clear_chat_prompt_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура подтверждения очистки чата."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear_chat")],
        [get_home_button()]
    ])


def get_read_notification_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-кнопка «Прочитано» для сообщений-сводок и срочных уведомлений."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Прочитано", callback_data="delete_this_message")]
    ])
