import asyncio
import logging
import ssl
from typing import Optional, Any
import aiohttp
from adapters.base_adapter import BaseAdapter
from config import config

logger = logging.getLogger(__name__)

def _create_ssl_context():
    """Creates SSL context ignoring self-signed/missing Windows root CA errors."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

class VKAdapter(BaseAdapter):
    def __init__(self, ai_engine: Optional[Any] = None):
        super().__init__(name="VK")
        self.ai_engine = ai_engine
        self.token = config.VK_TOKEN
        self.group_id = config.VK_GROUP_ID
        self._running = False
        self._task = None
        self._user_cache = {}
        self._group_cache = {}

    async def start(self):
        self.token = config.VK_TOKEN
        self.group_id = config.VK_GROUP_ID
        self._running = True
        
        if self.token:
            logger.info("Starting VK Adapter...")
            self._task = asyncio.create_task(self._listen_vk())
        else:
            logger.info("No VK_TOKEN configured. Running VK adapter in standby / mock mode.")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _resolve_user_name(self, session: aiohttp.ClientSession, user_id: int) -> str:
        """Resolves VK numeric user/group ID to actual name, with caching."""
        if not user_id:
            return "Неизвестный отправитель"
            
        if user_id > 2000000000:
            return f"Чат_{user_id - 2000000000}"
            
        if user_id < 0:
            group_id = abs(user_id)
            if group_id in self._group_cache:
                return self._group_cache[group_id]
            try:
                params = {
                    "group_ids": group_id,
                    "access_token": self.token,
                    "v": "5.131"
                }
                async with session.get("https://api.vk.com/method/groups.getById", params=params) as resp:
                    res = await resp.json()
                    if "response" in res and res["response"]:
                        name = res["response"][0].get("name", f"Группа_{group_id}")
                        self._group_cache[group_id] = name
                        return name
            except Exception as e:
                logger.debug(f"Error resolving VK group name: {e}")
            return f"Группа_{group_id}"

        # Regular User
        if user_id in self._user_cache:
            return self._user_cache[user_id]
            
        try:
            params = {
                "user_ids": user_id,
                "access_token": self.token,
                "v": "5.131"
            }
            async with session.get("https://api.vk.com/method/users.get", params=params) as resp:
                res = await resp.json()
                if "response" in res and res["response"]:
                    u = res["response"][0]
                    first_name = u.get("first_name", "")
                    last_name = u.get("last_name", "")
                    name = f"{first_name} {last_name}".strip()
                    if name:
                        self._user_cache[user_id] = name
                        return name
        except Exception as e:
            logger.warning(f"Error resolving VK user name: {e}")
            
        return f"VK_User_{user_id}"

    async def _listen_vk(self):
        """Supported User & Group LongPoll polling loop."""
        ssl_ctx = _create_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        async with aiohttp.ClientSession(connector=connector) as session:
            while self._running:
                try:
                    if self.group_id > 0:
                        params = {
                            "group_id": self.group_id,
                            "access_token": self.token,
                            "v": "5.131"
                        }
                        method = "https://api.vk.com/method/groups.getLongPollServer"
                    else:
                        params = {
                            "access_token": self.token,
                            "v": "5.131",
                            "lp_version": "3"
                        }
                        method = "https://api.vk.com/method/messages.getLongPollServer"

                    async with session.get(method, params=params) as resp:
                        data = await resp.json()
                        if "error" in data:
                            err = data["error"]
                            err_code = err.get("error_code")
                            err_msg = err.get("error_msg", "Unknown error")
                            if err_code in (4, 5, 27, 28):
                                logger.error(f"VK Auth Error (code {err_code}): {err_msg}. Invalid/expired VK_TOKEN. Pausing VK checks for 5 minutes to prevent log spam.")
                                await asyncio.sleep(300)
                            else:
                                logger.warning(f"VK LongPoll Server Error (code {err_code}): {err_msg}. Retrying in 60s...")
                                await asyncio.sleep(60)
                            continue
                        
                        res = data["response"]
                        server = res["server"]
                        key = res["key"]
                        ts = res["ts"]
                        if not server.startswith("http"):
                            server = f"https://{server}"

                    # Continuous Long Poll Loop
                    while self._running:
                        try:
                            if self.group_id > 0:
                                lp_url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25"
                            else:
                                lp_url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25&mode=2&version=3"

                            timeout = aiohttp.ClientTimeout(total=35)
                            async with session.get(lp_url, timeout=timeout) as lp_resp:
                                lp_data = await lp_resp.json()
                                if "failed" in lp_data:
                                    logger.warning(f"VK LongPoll failed code {lp_data.get('failed')}, reconnecting...")
                                    break
                                
                                ts = lp_data.get("ts", ts)
                                updates = lp_data.get("updates", [])
                                for event in updates:
                                    if self.group_id > 0:
                                        if event.get("type") == "message_new":
                                            msg = event["object"]["message"]
                                            user_id = msg.get("from_id")
                                            text = msg.get("text", "")
                                            
                                            atts = msg.get("attachments", [])
                                            if not text and atts:
                                                for att in atts:
                                                    if att["type"] == "audio_message":
                                                        am = att["audio_message"]
                                                        if "transcript" in am and am["transcript"]:
                                                            text = f"[Голосовое] {am['transcript']}"
                                                        else:
                                                            audio_url = am.get("link_ogg")
                                                            if audio_url:
                                                                transcript = await self._transcribe_vk_audio(audio_url)
                                                                if transcript:
                                                                    text = f"[Голосовое] {transcript}"
                                                                else:
                                                                    text = "[Голосовое сообщение]"
                                                            else:
                                                                text = "[Голосовое сообщение]"
                                                        break
                                                    elif att["type"] == "photo":
                                                        text = "[Фотография]"
                                                        break
                                            
                                            if text:
                                                raw_id = msg.get("id") or msg.get("conversation_message_id")
                                                if not raw_id or raw_id == 0:
                                                    raw_id = f"{user_id}_{msg.get('date', 0)}"
                                                msg_id = f"vk_grp_{raw_id}"
                                                
                                                sender_name = await self._resolve_user_name(session, user_id)
                                                await self.emit_message(sender=sender_name, text=text, msg_uid=msg_id)
                                    else:
                                        # User LongPoll format: [4, message_id, flags, peer_id, timestamp, text, ...]
                                        if isinstance(event, list) and len(event) > 5 and event[0] == 4:
                                            msg_id = event[1]
                                            flags = event[2]
                                            peer_id = event[3]
                                            text = event[5]
                                            
                                            is_outbox = bool(flags & 2)
                                            if not is_outbox:
                                                uid = f"vk_user_msg_{msg_id}"
                                                attachments = event[6] if len(event) > 6 else {}
                                                
                                                if not text and attachments:
                                                    # Launch an async task that fetches the full message and emits it
                                                    asyncio.create_task(self._process_vk_attachment_async(session, msg_id, uid, peer_id))
                                                elif text:
                                                    sender_name = await self._resolve_user_name(session, peer_id)
                                                    await self.emit_message(sender=sender_name, text=text, msg_uid=uid)
                        except asyncio.CancelledError:
                            raise
                        except Exception as inner_e:
                            logger.error(f"Network or parsing error in VK LongPoll inner loop: {inner_e}")
                            await asyncio.sleep(30)
                            # Do not break to outer loop unless necessary, to preserve 'ts'

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in VK listener: {e}")
                    await asyncio.sleep(30)

    async def _transcribe_vk_audio(self, audio_url: str) -> str:
        """Downloads audio and sends it to Gemini for transcription."""
        try:
            if not self.ai_engine:
                from ai_engine import AIEngine
                self.ai_engine = AIEngine()
            ai = self.ai_engine
            async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as session:
                async with session.get(audio_url) as resp:
                    if resp.status == 200:
                        audio_bytes = await resp.read()
                        res = await ai.transcribe_and_analyze_audio(audio_bytes, mime_type="audio/ogg")
                        # Return just the transcription text, stripped of brackets if any
                        t = res.transcription.strip()
                        if t and not t.startswith("[Обработка"):
                            return t
        except Exception as e:
            logger.error(f"Error downloading/transcribing VK audio: {e}")
        return ""

    async def _process_vk_attachment_async(self, session, msg_id, uid, peer_id):
        full_msg_params = {
            "message_ids": msg_id,
            "access_token": self.token,
            "v": "5.131"
        }
        text = ""
        try:
            async with session.get("https://api.vk.com/method/messages.getById", params=full_msg_params) as fm_resp:
                fm_data = await fm_resp.json()
                if "response" in fm_data and fm_data["response"]["items"]:
                    atts = fm_data["response"]["items"][0].get("attachments", [])
                    for att in atts:
                        if att["type"] == "audio_message":
                            am = att["audio_message"]
                            if "transcript" in am and am["transcript"]:
                                text = f"[Голосовое] {am['transcript']}"
                            else:
                                audio_url = am.get("link_ogg")
                                if audio_url:
                                    transcript = await self._transcribe_vk_audio(audio_url)
                                    text = f"[Голосовое] {transcript}" if transcript else "[Голосовое сообщение без текстовой расшифровки]"
                                else:
                                    text = "[Голосовое сообщение без текстовой расшифровки]"
                            break
                        elif att["type"] == "photo":
                            text = "[Фотография]"
                            break
                        elif att["type"] == "doc":
                            text = "[Документ]"
                            break
                        elif att["type"] == "video":
                            text = "[Видеозапись]"
                            break
                        elif att["type"] == "sticker":
                            text = "[Стикер]"
                            break
                        elif att["type"] == "wall":
                            text = "[Запись на стене]"
                            break
                        elif att["type"] == "link":
                            text = "[Ссылка]"
                            break
        except Exception as e:
            logger.warning(f"Could not fetch full VK message {msg_id}: {e}")
            
        if not text:
            text = "[Вложение]"
            
        if text:
            sender_name = await self._resolve_user_name(session, peer_id)
            await self.emit_message(sender=sender_name, text=text, msg_uid=uid)
