"""
Banwords management module.
Supports channel-specific filtering (global, email, vk) and default system seed entries.
"""

DEFAULT_SYSTEM_BANWORDS = [
    # Global banwords (Applies to Mail.ru, VK, etc.)
    {"word": "казино", "scope": "global"},
    {"word": "casino", "scope": "global"},
    {"word": "1xbet", "scope": "global"},
    {"word": "1хбет", "scope": "global"},
    {"word": "vulkan", "scope": "global"},
    {"word": "вулкан", "scope": "global"},
    {"word": "pin-up", "scope": "global"},
    {"word": "pinup", "scope": "global"},
    {"word": "pokerdom", "scope": "global"},
    {"word": "покердом", "scope": "global"},
    {"word": "слоты", "scope": "global"},
    {"word": "slots", "scope": "global"},
    {"word": "freespin", "scope": "global"},
    {"word": "фриспин", "scope": "global"},
    {"word": "1win", "scope": "global"},
    {"word": "777", "scope": "global"},
    {"word": "рулетка", "scope": "global"},
    {"word": "джекпот", "scope": "global"},
    {"word": "jackpot", "scope": "global"},
    {"word": "vpn", "scope": "global"},
    {"word": "впн", "scope": "global"},

    # Email-specific banwords
    {"word": "выиграли", "scope": "email"},
    {"word": "выплата одобрена", "scope": "email"},
    {"word": "заберите бонус", "scope": "email"},
    {"word": "перевод средств", "scope": "email"},
    {"word": "пассивный доход", "scope": "email"},

    # VK-specific banwords
    {"word": "ставь лайк", "scope": "vk"},
    {"word": "подпишись на группу", "scope": "vk"},
    {"word": "рассылка бота", "scope": "vk"}
]


def is_text_spam(text: str, channel: str = "global", active_banwords: list = None) -> bool:
    """
    Checks if given text contains any banword matching the given channel or 'global'.
    channel can be 'email', 'vk', or 'global'.
    """
    if not text:
        return False

    lower_text = text.lower()
    words_to_check = active_banwords if active_banwords is not None else DEFAULT_SYSTEM_BANWORDS

    chan_lower = channel.lower()
    for item in words_to_check:
        word = item.get("word", "").lower()
        scope = item.get("scope", "global").lower()
        if not word:
            continue

        # Check if scope is global or matches current channel
        if scope == "global" or scope == chan_lower or (chan_lower in scope) or (scope in chan_lower):
            if word in lower_text:
                return True

    return False
