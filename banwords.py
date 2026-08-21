"""
Banwords management module.
Supports 2 primary channel categories: 'email' (Mail.ru) and 'vk' (ВКонтакте).
All banwords (including defaults) are fully editable and removable by the user.
"""

DEFAULT_SYSTEM_BANWORDS = [
    # Mail.ru / Email Category
    {"word": "казино", "scope": "email"},
    {"word": "casino", "scope": "email"},
    {"word": "1xbet", "scope": "email"},
    {"word": "1хбет", "scope": "email"},
    {"word": "vulkan", "scope": "email"},
    {"word": "вулкан", "scope": "email"},
    {"word": "pin-up", "scope": "email"},
    {"word": "pinup", "scope": "email"},
    {"word": "pokerdom", "scope": "email"},
    {"word": "покердом", "scope": "email"},
    {"word": "слоты", "scope": "email"},
    {"word": "slots", "scope": "email"},
    {"word": "freespin", "scope": "email"},
    {"word": "фриспин", "scope": "email"},
    {"word": "1win", "scope": "email"},
    {"word": "777", "scope": "email"},
    {"word": "рулетка", "scope": "email"},
    {"word": "джекпот", "scope": "email"},
    {"word": "jackpot", "scope": "email"},
    {"word": "vpn", "scope": "email"},
    {"word": "впн", "scope": "email"},
    {"word": "выиграли", "scope": "email"},
    {"word": "выплата одобрена", "scope": "email"},
    {"word": "заберите бонус", "scope": "email"},
    {"word": "перевод средств", "scope": "email"},
    {"word": "пассивный доход", "scope": "email"},

    # VK Category
    {"word": "ставь лайк", "scope": "vk"},
    {"word": "подпишись на группу", "scope": "vk"},
    {"word": "рассылка бота", "scope": "vk"},
    {"word": "казино", "scope": "vk"},
    {"word": "1xbet", "scope": "vk"},
    {"word": "впн", "scope": "vk"}
]


def is_text_spam(text: str, channel: str = "email", active_banwords: list = None) -> bool:
    """
    Checks if given text contains any active banword for the given channel category ('email' or 'vk').
    """
    if not text:
        return False

    lower_text = text.lower()
    words_to_check = active_banwords if active_banwords is not None else DEFAULT_SYSTEM_BANWORDS

    chan_clean = "vk" if "vk" in channel.lower() else "email"

    for item in words_to_check:
        word = item.get("word", "").lower()
        scope = item.get("scope", "email").lower()
        if not word:
            continue

        if scope == chan_clean or scope == "global":
            if word in lower_text:
                return True

    return False
