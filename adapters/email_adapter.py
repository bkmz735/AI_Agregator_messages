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
            logger.info("Starting Email IMAP adapter...")
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
        decoded, encoding = decode_header(header_val)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(encoding or "utf-8", errors="ignore")
        return str(decoded)

    async def _poll_imap(self):
        """Polls unread emails periodically."""
        import aioimaplib
        ssl_ctx = _create_ssl_context()

        while self._running:
            try:
                imap_client = aioimaplib.IMAP4_SSL(host=self.server, port=self.port, ssl_context=ssl_ctx)
                await imap_client.wait_hello_from_server()
                await imap_client.login(self.user, self.password)
                await imap_client.select('INBOX')

                # Search UNSEEN
                status, data = await imap_client.search('UNSEEN')
                if status == 'OK' and data[0]:
                    msg_nums = data[0].split()
                    for num in msg_nums:
                        status, msg_data = await imap_client.fetch(num, '(RFC822)')
                        if status == 'OK':
                            raw_email = msg_data[1]
                            msg = email.message_from_bytes(raw_email)
                            subject = self._decode_str(msg.get("Subject"))
                            from_addr = self._decode_str(msg.get("From"))

                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                            channel_name = "Email"
                            if "avito" in from_addr.lower() or "авито" in subject.lower():
                                channel_name = "Avito (Email)"
                            elif "instagram" in from_addr.lower():
                                channel_name = "Instagram (Email)"

                            msg_uid = f"email_{msg.get('Message-ID', num.decode())}"
                            text_full = f"Тема: {subject}\n\n{body}"
                            await self.emit_message(sender=from_addr, text=text_full, msg_uid=msg_uid)

                await imap_client.logout()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Email IMAP adapter: {e}")
                await asyncio.sleep(30)
