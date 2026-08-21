"""
Banwords management module.
Centralizes built-in system banwords (casino, VPN, phishing, scam)
and provides helpers for checking text against both system and user-defined banwords.
"""

# Default system banwords automatically filtered at source/ingestion level
SYSTEM_BANWORDS = [
    # Casino & Gambling
    "казино", "casino", "1xbet", "1хбет", "vulkan", "вулкан", "pin-up", "pinup",
    "pokerdom", "покердом", "слоты", "slots", "freespin", "фриспин", "ставка",
    "ставки", "букмекер", "1win", "joycasino", "джойказино", "777",
    "бездеп", "бездепозитный", "азартн", "игровой автомат", "игровые автоматы",
    "рулетка", "рулетк", "джекпот", "jackpot",

    # VPN Spam
    "vpn", "впн", "бесплатный vpn", "скачать vpn",

    # Winnings / Phishing / Fraud
    "выигрыш", "выиграли", "бонус 500", "заберите бонус", "вам начислено",
    "выплата одобрена", "перевод средств", "криптобонус", "финансовая пирамида",
    "пассивный доход"
]


def get_system_banwords() -> list[str]:
    """Returns the list of built-in system banwords."""
    return list(SYSTEM_BANWORDS)


def is_spam_text(text: str, custom_banwords: list[str] = None) -> bool:
    """
    Checks if given text contains any system or custom banwords.
    Returns True if spam is detected.
    """
    if not text:
        return False
        
    lower_text = text.lower()
    
    # 1. Check system banwords
    for kw in SYSTEM_BANWORDS:
        if kw in lower_text:
            return True
            
    # 2. Check custom user banwords
    if custom_banwords:
        for kw in custom_banwords:
            if kw and kw.strip().lower() in lower_text:
                return True
                
    return False
