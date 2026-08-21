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

class EmailAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(name="Email (Avito/Instagram)")
        self.server = config.IMAP_SERVER
        self.port = config.IMAP_PORT
        self.user = config.IMAP_USER
        self.password = config.IMAP_PASSWORD
        self._running = False
        self._task = None

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

                # Search both UNSEEN and recent messages
                status, data = await imap_client.search('UNSEEN')
                
                # Fallback to ALL if no unseen found, check latest 5 messages
                if status == 'OK' and not data[0]:
                    status, data = await imap_client.search('ALL')
                    if status == 'OK' and data[0]:
                        nums = data[0].split()
                        # Pick last 3 messages for safety
                        data = [b" ".join(nums[-3:])]

                if status == 'OK' and data[0]:
                    msg_nums = data[0].split()
                    logger.info(f"Mail.ru IMAP fetched {len(msg_nums)} emails to process.")
                    for num in msg_nums:
                        try:
                            fetch_status, msg_data = await imap_client.fetch(num.decode(), '(RFC822)')
                            if fetch_status == 'OK':
                                raw_email = None
                                for item in msg_data:
                                    if isinstance(item, bytes) and len(item) > 50:
                                        raw_email = item
                                        break
                                
                                if not raw_email and len(msg_data) >= 2:
                                    raw_email = msg_data[1]

                                if raw_email and isinstance(raw_email, bytes):
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

                                    channel_name = "Email (Mail.ru)"
                                    if "avito" in from_addr.lower() or "авито" in subject.lower():
                                        channel_name = "Avito (Email)"
                                    elif "instagram" in from_addr.lower():
                                        channel_name = "Instagram (Email)"

                                    msg_id = msg.get('Message-ID', num.decode())
                                    msg_uid = f"email_{msg_id}"
                                    text_full = f"Тема: {subject}\n\n{body[:500]}"
                                    
                                    await self.emit_message(sender=from_addr, text=text_full, msg_uid=msg_uid)
                        except Exception as fe:
                            logger.warning(f"Error fetching email #{num}: {fe}")

                await imap_client.logout()
                await asyncio.sleep(45)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Email IMAP adapter: {e}")
                await asyncio.sleep(30)
