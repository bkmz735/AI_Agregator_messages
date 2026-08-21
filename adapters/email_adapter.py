import asyncio
import logging
import ssl
import email
from email.header import decode_header
from adapters.base_adapter import BaseAdapter
from config import config

logger = logging.getLogger(__name__)

def _create_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

SPAM_KEYWORDS = [
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

class EmailAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(name="Email (Mail.ru)")
        self.server = config.IMAP_SERVER
        self.port = config.IMAP_PORT
        self.user = config.IMAP_USER
        self.password = config.IMAP_PASSWORD
        self._running = False
        self._task = None
        # Track already-seen message numbers to avoid re-processing read emails
        self._seen_nums: set = set()

    async def start(self):
        self._running = True
        if self.user and self.password:
            logger.info(f"Starting Email IMAP adapter for [{self.user}] on {self.server}:{self.port}...")
            self._task = asyncio.create_task(self._poll_imap())
        else:
            logger.info("No IMAP credentials configured. Running Email adapter in standby mode.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    def _decode_str(self, header_val):
        if not header_val:
            return ""
        try:
            decoded_parts = decode_header(header_val)
            res = []
            for decoded, encoding in decoded_parts:
                if isinstance(decoded, bytes):
                    res.append(decoded.decode(encoding or "utf-8", errors="ignore"))
                else:
                    res.append(str(decoded))
            return "".join(res)
        except Exception:
            return str(header_val)

    def _extract_raw_email(self, lines) -> bytes | None:
        """Extract raw email bytes from aioimaplib fetch response lines.
        
        aioimaplib returns lines as a mix of bytes, bytearray, and str.
        The actual email body is always the LARGEST bytes/bytearray element.
        """
        best = None
        best_len = 0

        for line in lines:
            candidates = []
            if isinstance(line, tuple):
                candidates.extend(line)
            else:
                candidates.append(line)

            for part in candidates:
                if isinstance(part, (bytes, bytearray)):
                    part_len = len(part)
                    if part_len > best_len:
                        best = bytes(part)
                        best_len = part_len

        # Sanity check: a real email should be at least ~50 bytes
        if best and best_len > 50:
            return best
        return None

    async def _poll_imap(self):
        """Polls emails periodically."""
        import aioimaplib
        ssl_ctx = _create_ssl_context()

        while self._running:
            try:
                imap_client = aioimaplib.IMAP4_SSL(host=self.server, port=self.port, ssl_context=ssl_ctx)
                await imap_client.wait_hello_from_server()
                
                login_resp = await imap_client.login(self.user, self.password)
                if login_resp.result != 'OK':
                    logger.error(f"Mail.ru IMAP login failed for {self.user}: {login_resp}")
                    await asyncio.sleep(60)
                    continue

                await imap_client.select('INBOX')

                # Only fetch UNSEEN (unread) emails
                status_resp, data = await imap_client.search('UNSEEN')
                msg_numbers = data[0].split() if status_resp == 'OK' and data and data[0] else []

                if not msg_numbers:
                    # No unread mail — nothing to do
                    await imap_client.logout()
                    await asyncio.sleep(45)
                    continue

                logger.info(f"Mail.ru IMAP found {len(msg_numbers)} UNSEEN emails to process.")
                for num in msg_numbers:
                    try:
                        num_str = num.decode() if isinstance(num, bytes) else str(num)

                        # Skip if we already processed this message number in this session
                        if num_str in self._seen_nums:
                            continue

                        fetch_resp = await imap_client.fetch(num_str, '(RFC822)')
                        
                        if fetch_resp.result == 'OK':
                            raw_email = self._extract_raw_email(fetch_resp.lines)
                            
                            if raw_email:
                                msg = email.message_from_bytes(raw_email)
                                subject = self._decode_str(msg.get("Subject", "Без темы"))
                                from_addr = self._decode_str(msg.get("From", "Неизвестный отправитель"))

                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/plain":
                                            payload = part.get_payload(decode=True)
                                            if payload:
                                                body = payload.decode("utf-8", errors="ignore")
                                            break
                                else:
                                    payload = msg.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode("utf-8", errors="ignore")

                                # Check for Casino / VPN / Financial Scam Spam
                                combined_search_text = f"{subject} {from_addr} {body}".lower()
                                matched_spam_kw = next((kw for kw in SPAM_KEYWORDS if kw in combined_search_text), None)
                                
                                if matched_spam_kw:
                                    logger.warning(
                                        f"🚫 [SPAM AUTO-DELETE] Deleting Casino/VPN/Scam email #{num_str} from '{from_addr}' "
                                        f"(Trigger keyword: '{matched_spam_kw}', Subject: '{subject}')"
                                    )
                                    try:
                                        await imap_client.store(num_str, '+FLAGS', '(\\Deleted)')
                                        await imap_client.expunge()
                                    except Exception as de:
                                        logger.error(f"Failed to delete spam email #{num_str} via IMAP: {de}")
                                    self._seen_nums.add(num_str)
                                    continue

                                channel_name = "Email (Mail.ru)"
                                if "avito" in from_addr.lower() or "авито" in subject.lower():
                                    channel_name = "Avito (Email)"
                                elif "instagram" in from_addr.lower():
                                    channel_name = "Instagram (Email)"

                                msg_id_val = msg.get('Message-ID')
                                if msg_id_val:
                                    msg_uid = f"email_{str(msg_id_val).strip('<> ')}"
                                else:
                                    date_val = msg.get('Date', '')
                                    msg_uid = f"email_fallback_{from_addr}_{subject}_{date_val}"
                                text_full = f"Тема: {subject}\n\n{body[:500]}"
                                
                                logger.info(f"Emitting email: [{channel_name}] From: {from_addr} Subject: {subject}")
                                await self.emit_message(sender=from_addr, text=text_full, msg_uid=msg_uid, channel_override=channel_name)
                                self._seen_nums.add(num_str)
                            else:
                                logger.warning(f"Email #{num_str}: could not extract raw body from IMAP response.")
                        else:
                            logger.warning(f"Email #{num_str}: FETCH returned {fetch_resp.result}")
                    except Exception as fe:
                        logger.warning(f"Error fetching email #{num}: {fe}")

                await imap_client.logout()
                await asyncio.sleep(45)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Email IMAP adapter: {e}")
                await asyncio.sleep(30)
