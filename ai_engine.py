import json
import asyncio
import logging
import socket
import time
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from config import config as app_config

logger = logging.getLogger(__name__)

# SmartDNS / AI DNS Servers configuration (Comss.one + Xbox SmartDNS for bypassing AI geo-blocks)
AI_DNS_SERVERS: List[str] = []
SMART_DNS_ENABLED: bool = True

if app_config.AI_DNS_SERVERS and app_config.AI_DNS_SERVERS.lower() not in ("none", "off", "false", "0"):
    AI_DNS_SERVERS = [ip.strip() for ip in app_config.AI_DNS_SERVERS.split(",") if ip.strip()]


def update_active_dns_servers(servers: List[str], enabled: bool = True):
    """Dynamically updates active SmartDNS servers and enabled state."""
    global AI_DNS_SERVERS, SMART_DNS_ENABLED
    SMART_DNS_ENABLED = bool(enabled)
    AI_DNS_SERVERS.clear()
    for s in servers:
        s_clean = s.strip()
        if s_clean and s_clean not in AI_DNS_SERVERS:
            AI_DNS_SERVERS.append(s_clean)
    logger.info(f"SmartDNS Resolver updated: enabled={SMART_DNS_ENABLED}, servers={AI_DNS_SERVERS}")


# Enable Custom SmartDNS Resolver for Google / AI domains
try:
    import dns.resolver
    _original_getaddrinfo = socket.getaddrinfo

    def _smart_dns_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if SMART_DNS_ENABLED and AI_DNS_SERVERS and isinstance(host, str) and ("googleapis.com" in host or "google" in host):
            try:
                resolver = dns.resolver.Resolver(configure=False)
                ip_servers = [s for s in AI_DNS_SERVERS if not s.startswith("http")]
                doh_servers = [s for s in AI_DNS_SERVERS if s.startswith("http")]
                
                if ip_servers:
                    resolver.nameservers = ip_servers
                if doh_servers:
                    import dns.nameserver
                    for doh in doh_servers:
                        try:
                            resolver.nameservers.append(dns.nameserver.DoHNameserver(doh))
                        except Exception:
                            pass
                
                resolver.timeout = 1.5
                resolver.lifetime = 1.5
                record_type = "AAAA" if family == socket.AF_INET6 else "A"
                answers = resolver.resolve(host, record_type)
                for rdata in answers:
                    ip = rdata.address
                    return _original_getaddrinfo(ip, port, family, type, proto, flags)
            except Exception as e:
                logger.debug(f"SmartDNS fallback for {host}: {e}")
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _smart_dns_getaddrinfo
    if AI_DNS_SERVERS:
        logger.info(f"SmartDNS Resolver enabled for AI domains: {', '.join(AI_DNS_SERVERS)}")
except Exception as e:
    logger.warning(f"Could not initialize SmartDNS Resolver: {e}")

from models import AnalysisResult, AnalysisBatchResponse, AudioAnalysisResult

class AIEngine:
    def __init__(self, api_key: Optional[str] = None, storage=None):
        self.api_key = api_key or app_config.AI_API_KEY
        self.client = None
        self.storage = storage
        
        # Quota and Rate Limit trackers
        self.requests_today = 0
        self.last_reset_date = date.today()
        self.minute_request_timestamps: List[float] = []
        self.rate_limit_until: float = 0.0
        self.last_error_reason: Optional[str] = None

        # Priority order: Lite models first (500 RPD, 15 RPM), then standard Flash models (20 RPD, 5 RPM)
        self.priority_models = [
            'gemini-3.5-flash-lite', 
            'gemini-3.1-flash-lite',
            'gemini-3.7-flash', 
            'gemini-3.6-flash', 
            'gemini-3.5-flash',
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-1.5-flash'
        ]
        self.exhausted_models: set[str] = set()       # Daily exhausted models (reset daily)
        self.unsupported_models: set[str] = set()     # Deprecated/invalid models (permanent during session)
        self.model_cooldowns: Dict[str, float] = {}   # Temporary cooldowns per model for minute-limit (429)

        if self.api_key:
            try:
                import os
                if app_config.AI_PROXY:
                    os.environ["HTTPS_PROXY"] = app_config.AI_PROXY
                    os.environ["HTTP_PROXY"] = app_config.AI_PROXY
                    os.environ["https_proxy"] = app_config.AI_PROXY
                    os.environ["http_proxy"] = app_config.AI_PROXY
                    logger.info("Configured AI_PROXY for Google Gemini client.")

                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info("AI API client initialized successfully.")
            except Exception as e:
                logger.warning(f"Could not initialize google.genai Client: {e}. Falling back to rule-based analysis.")
        else:
            logger.info("No AI_API_KEY set. Running in rule-based simulation mode.")

    def _track_request(self):
        """Updates internal rate limit counters."""
        now = time.time()
        today = date.today()

        # Reset daily counter at midnight
        if today != self.last_reset_date:
            self.requests_today = 0
            self.exhausted_models.clear()
            self.last_reset_date = today

        self.requests_today += 1
        self.minute_request_timestamps.append(now)

        # Keep only timestamps within the last 60 seconds
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if now - t <= 60]

    def _get_active_models(self) -> List[str]:
        """Returns list of currently usable models sorted by priority."""
        now = time.time()
        return [
            m for m in self.priority_models 
            if m not in self.exhausted_models 
            and m not in self.unsupported_models 
            and self.model_cooldowns.get(m, 0.0) <= now
        ]

    def _get_cooldown_wait_time(self) -> int:
        """Calculates minimum wait time for models in minute cooldown."""
        now = time.time()
        active_cooldowns = [
            self.model_cooldowns[m] - now 
            for m in self.priority_models 
            if m not in self.exhausted_models and m not in self.unsupported_models and self.model_cooldowns.get(m, 0.0) > now
        ]
        if active_cooldowns:
            return max(1, int(min(active_cooldowns)))
        return 60

    async def get_quota_stats(self) -> Dict[str, Any]:
        """Returns current AI API rate limit and usage statistics."""
        now = time.time()
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if now - t <= 60]
        
        is_paused = now < self.rate_limit_until
        pause_seconds_left = int(self.rate_limit_until - now) if is_paused else 0

        from settings_manager import SettingsManager
        settings = SettingsManager(self.storage) if self.storage else None
        max_rpm = (await settings.get_ai_max_rpm()) if settings else app_config.AI_MAX_RPM

        return {
            "requests_today": self.requests_today,
            "requests_this_minute": len(self.minute_request_timestamps),
            "max_rpm": max_rpm,
            "is_paused": is_paused,
            "pause_seconds_left": pause_seconds_left,
            "status_text": f"🔴 Пауза лимита ({pause_seconds_left}с)" if is_paused else "🟢 API Активен"
        }

    async def generate_content_with_retry(self, contents: Any, genai_config: Any = None, config: Any = None) -> Any:
        """Executes a AI API request with priority models fallback and rate limit protections."""
        actual_config = genai_config if genai_config is not None else config
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            raise RuntimeError(f"AI API rate limit active. Resuming in {wait_time}s.")
            
        from settings_manager import SettingsManager
        settings = SettingsManager(self.storage) if self.storage else None
        max_rpm = (await settings.get_ai_max_rpm()) if settings else app_config.AI_MAX_RPM

        rpm_count = len([t for t in self.minute_request_timestamps if time.time() - t <= 60])
        if rpm_count >= max_rpm:
            self.rate_limit_until = time.time() + 60.0
            raise RuntimeError(f"AI API RPM limit reached ({rpm_count}/{max_rpm}). Pausing API calls for 60s.")
            
        if not self.client:
            raise RuntimeError("AI client not initialized.")
            
        active_models = self._get_active_models()
        if not active_models:
            wait_time = self._get_cooldown_wait_time()
            self.rate_limit_until = time.time() + wait_time
            raise RuntimeError(f"Все модели ИИ временно на паузе (лимит). Возобновление через {wait_time}с.")
            
        last_error = None
        for model_name in active_models:
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=actual_config
                    ),
                    timeout=25.0
                )
                self._track_request()
                return response
            except Exception as e:
                err_str = str(e)
                last_error = e
                # Handle 404 (model unsupported or not found in region)
                if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                    logger.warning(f"AI model {model_name} is unsupported (404).")
                    self.unsupported_models.add(model_name)
                    continue
                # Handle 429 (quota exhausted)
                if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if "day" in err_str.lower() or "daily" in err_str.lower():
                        logger.error(f"AI model {model_name} hit daily quota: {e}")
                        self.exhausted_models.add(model_name)
                        continue
                    else:
                        logger.warning(f"AI model {model_name} hit minute rate limit (429): {e}. Cooling down for 60s.")
                        self.model_cooldowns[model_name] = time.time() + 60.0
                        continue
                logger.warning(f"Model {model_name} failed: {e}")
                continue
                
        if not self._get_active_models():
            wait_time = self._get_cooldown_wait_time()
            self.rate_limit_until = time.time() + wait_time
            raise RuntimeError(f"Все модели ИИ временно на паузе (минутный лимит). Возобновление через {wait_time}с.")

        raise RuntimeError(f"All models failed. Last error: {last_error}")

    async def transcribe_and_analyze_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> AudioAnalysisResult:
        """Transcribes audio/voice message using AI multimodal capabilities and analyzes it."""
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            logger.warning(f"AI API rate limited. Skipping audio API call for {wait_time}s.")
            return AudioAnalysisResult(
                transcription="[Обработка приостановлена: превышен лимит AI API (429)]",
                category="important",
                summary=f"Голосовое сообщение будет обработано через {wait_time} сек после возобновления лимита.",
                action_required=True,
                suggested_reply="Здравствуйте! Получил ваше голосовое, отвечу чуть позже."
            )

        if self.client and audio_bytes:
            from google.genai import types
            part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
            prompt = (
                "Сделай ДОСЛОВНУЮ транскрипцию (слово в слово) этого голосового сообщения на русском языке и сохрани её в поле 'transcription'. "
                "КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ пересказывать смысл в поле 'transcription', там должен быть только оригинальный текст аудиозаписи! "
                "Затем определи его категорию (spam, urgent, important, gov_debt, gov_service, news, media, general, politics, interesting, bullshit), "
                "составь краткое резюме (summary) о чем это сообщение, проверь требуется ли ответ (action_required), "
                "и предложи готовый черновик ответа (suggested_reply).\n"
                "Ответ верни строго в формате JSON с ключами: transcription, category, summary, action_required, suggested_reply."
            )
            active_models = self._get_active_models()
            if not active_models:
                logger.warning("No active AI models available for audio transcription.")
            
            for model_name in active_models:
                try:
                    response = await asyncio.wait_for(
                        self.client.aio.models.generate_content(
                            model=model_name,
                            contents=[part, prompt],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        ),
                        timeout=20.0
                    )
                    self._track_request()
                    if response and response.text:
                        parsed = json.loads(response.text)
                        logger.info(f"Successfully transcribed audio ({len(audio_bytes)} bytes) using AI {model_name}.")
                        return AudioAnalysisResult(
                            transcription=parsed.get("transcription", "Расшифровка недоступна"),
                            category=parsed.get("category", "important"),
                            summary=parsed.get("summary", "Голосовое сообщение"),
                            action_required=parsed.get("action_required", True),
                            suggested_reply=parsed.get("suggested_reply", "Спасибо за голосовое сообщение! Прослушал, отвечу в ближайшее время.")
                        )
                except Exception as e:
                    err_str = str(e)
                    # Handle 404 (model deprecated / unsupported)
                    if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                        logger.warning(f"AI model {model_name} is unsupported (404).")
                        self.unsupported_models.add(model_name)
                        continue
                    
                    # Handle 429 (quota exhausted)
                    if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if "day" in err_str.lower() or "daily" in err_str.lower():
                            logger.error(f"AI model {model_name} hit daily quota limit: {e}")
                            self.exhausted_models.add(model_name)
                            continue
                        else:
                            logger.warning(f"AI model {model_name} hit minute limit (429) during audio: {e}. Cooling down.")
                            self.model_cooldowns[model_name] = time.time() + 60.0
                            continue
                    logger.warning(f"Audio transcription model {model_name} failed: {e}")
                    continue

        return AudioAnalysisResult(
            transcription="[Голосовое сообщение полученo, но расшифровка временно недоступна]",
            category="important",
            summary="Получено новое голосовое сообщение",
            action_required=True,
            suggested_reply="Здравствуйте! Прослушал ваше голосовое сообщение, скоро отвечу."
        )

    async def analyze_batch_messages(self, messages_batch: List[Dict[str, str]], custom_prompt_suffix: str = "") -> List[AnalysisResult]:
        """
        Analyzes a BATCH of raw incoming messages.
        If batch size exceeds AI_BATCH_CHUNK_SIZE (default 3), automatically splits into chunks for optimal AI accuracy.
        """
        if not messages_batch:
            return []

        results_map = {}
        messages_to_ai = []
        
        for i, m in enumerate(messages_batch):
            text = m.get('text', '')
            if text == "[Голосовое сообщение без текстовой расшифровки]" or text == "[Голосовое сообщение]":
                results_map[i] = AnalysisResult(
                    msg_uid=m.get("msg_uid", ""),
                    category="general",
                    summary="🎤 Голосовое сообщение (без текста)",
                    action_required=False,
                    suggested_reply=None
                )
            elif text == "[Фотография]":
                results_map[i] = AnalysisResult(
                    msg_uid=m.get("msg_uid", ""),
                    category="general",
                    summary="📷 Фотография",
                    action_required=False,
                    suggested_reply=None
                )
            else:
                messages_to_ai.append((i, m))

        if not messages_to_ai:
            return [results_map[i] for i in range(len(messages_batch))]

        ai_batch = [m for i, m in messages_to_ai]

        # Chunking: split large batches into sub-batches
        from settings_manager import SettingsManager
        settings = SettingsManager(self.storage) if self.storage else None
        CHUNK_SIZE = (await settings.get_ai_batch_chunk_size()) if settings else app_config.AI_BATCH_CHUNK_SIZE
        
        all_ai_results = []
        if len(ai_batch) > CHUNK_SIZE:
            chunks = [ai_batch[i:i + CHUNK_SIZE] for i in range(0, len(ai_batch), CHUNK_SIZE)]
            logger.info(f"Splitting batch of {len(ai_batch)} messages into {len(chunks)} sub-chunks (max {CHUNK_SIZE} msgs each)...")
            
            for idx, chunk in enumerate(chunks, 1):
                logger.info(f"Processing chunk {idx}/{len(chunks)} ({len(chunk)} messages)...")
                while True:
                    try:
                        chunk_results = await self._analyze_single_batch_chunk(chunk, custom_prompt_suffix)
                        all_ai_results.extend(chunk_results)
                        break
                    except RuntimeError as e:
                        if "rate limit" in str(e).lower() or "rpm limit" in str(e).lower() or "minute limit" in str(e).lower() or "429" in str(e):
                            logger.warning(f"Rate limit hit during chunking: {e}. Sleeping 60s...")
                            await asyncio.sleep(60)
                        else:
                            raise e
        else:
            while True:
                try:
                    all_ai_results = await self._analyze_single_batch_chunk(ai_batch, custom_prompt_suffix)
                    break
                except RuntimeError as e:
                    if "rate limit" in str(e).lower() or "rpm limit" in str(e).lower() or "minute limit" in str(e).lower() or "429" in str(e):
                        logger.warning(f"Rate limit hit during chunking: {e}. Sleeping 60s...")
                        await asyncio.sleep(60)
                    else:
                        raise e

        # Map results back to original positions
        for (i, _), res in zip(messages_to_ai, all_ai_results):
            results_map[i] = res

        return [results_map[i] for i in range(len(messages_batch))]

    async def _analyze_single_batch_chunk(self, messages_batch: List[Dict[str, str]], custom_prompt_suffix: str = "") -> List[AnalysisResult]:
        """Analyzes a single chunk (up to AI_BATCH_CHUNK_SIZE messages) in ONE AI API call."""
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            raise RuntimeError(f"AI API minute rate limit active. Resuming in {wait_time}s.")

        if self.client:
            from settings_manager import SettingsManager
            settings = SettingsManager(self.storage) if self.storage else None
            max_rpm = (await settings.get_ai_max_rpm()) if settings else app_config.AI_MAX_RPM

            # Pre-check: don't waste an API call if we already know we're over limit
            rpm_count = len([t for t in self.minute_request_timestamps if time.time() - t <= 60])
            if rpm_count >= max_rpm:
                self.rate_limit_until = time.time() + 60.0
                raise RuntimeError(f"AI API RPM limit reached ({rpm_count}/{max_rpm}). Pausing API calls for 60s.")
            else:
                # Map to anonymized payload with channel: id, channel, text
                anonymized_batch = [
                    {"id": i, "channel": m.get("channel", ""), "text": m["text"]}
                    for i, m in enumerate(messages_batch)
                ]
                batch_json_input = json.dumps(anonymized_batch, ensure_ascii=False)
                prompt = (
                    f"{app_config.AI_FILTER_PROMPT}\n"
                    f"{custom_prompt_suffix}\n\n"
                    f"Проанализируй список входящих сообщений ниже и верни массив JSON ответов для каждого сообщения:\n"
                    f"{batch_json_input}"
                )
                active_models = self._get_active_models()
                if not active_models:
                    wait_time = self._get_cooldown_wait_time()
                    self.rate_limit_until = time.time() + wait_time
                    raise RuntimeError(f"Все модели ИИ на паузе лимита. Ожидание {wait_time}с.")
                
                from google.genai import types
                for model_name in active_models:
                    try:
                        response = await asyncio.wait_for(
                            self.client.aio.models.generate_content(
                                model=model_name,
                                contents=prompt,
                                config=types.GenerateContentConfig(response_mime_type="application/json")
                            ),
                            timeout=20.0
                        )
                        self._track_request()
                        if response and response.text:
                            text_resp = response.text
                            # Fallback strip markdown backticks just in case
                            if text_resp.strip().startswith("```json"):
                                text_resp = text_resp.strip()[7:-3].strip()
                            elif text_resp.strip().startswith("```"):
                                text_resp = text_resp.strip()[3:-3].strip()
                                
                            try:
                                parsed = json.loads(text_resp)
                            except json.JSONDecodeError as je:
                                logger.error(f"JSON decode error from AI: {je}. Response text: {text_resp[:200]}")
                                raise Exception("Invalid JSON returned by AI API")
                                
                            items = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
                            results = []
                            if isinstance(items, list):
                                for i, item in enumerate(items):
                                    # Fallback if AI forgot to include id
                                    item_id = item.get("id")
                                    if item_id is None and i < len(messages_batch):
                                        item_id = i
                                    elif item_id is None:
                                        continue # skip invalid response item
                                        
                                    orig_msg = messages_batch[item_id] if 0 <= item_id < len(messages_batch) else None
                                    if not orig_msg:
                                        continue
                                        
                                    item["msg_uid"] = orig_msg["msg_uid"]
                                    if "id" in item:
                                        del item["id"]
                                        
                                    # ENFORCE: tg_news/Telegram can NEVER be urgent/important
                                    orig_channel = str(orig_msg.get("channel", "")).lower()
                                    orig_uid = str(orig_msg.get("msg_uid", "")).lower()
                                    if "telegram" in orig_channel or "tg_news" in orig_channel or orig_uid.startswith("tg_news_"):
                                        cat = item.get("category", "")
                                        if cat in ["urgent", "important", "gov_debt", "gov_service"]:
                                            item["category"] = "news"
                                        if item.get("action_required"):
                                            item["action_required"] = False
                                            
                                    results.append(AnalysisResult(**item))
                                logger.info(f"Successfully analyzed CHUNK of {len(results)} messages via AI API ({model_name}).")
                                return results
                    except Exception as e:
                        err_str = str(e)
                        # Handle 404 (model deprecated / unsupported)
                        if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                            logger.warning(f"AI model {model_name} is unsupported (404).")
                            self.unsupported_models.add(model_name)
                            continue
                        
                        # Handle 429 (quota exhausted)
                        if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            if "day" in err_str.lower() or "daily" in err_str.lower():
                                logger.error(f"AI model {model_name} hit daily quota limit: {e}")
                                self.exhausted_models.add(model_name)
                                continue
                            else:
                                logger.warning(f"AI model {model_name} hit minute limit (429) during batch: {e}. Cooling down.")
                                self.model_cooldowns[model_name] = time.time() + 60.0
                                continue
                        logger.warning(f"Batch analysis model {model_name} failed: {e}")
                        continue

        # Fallback / Mock analysis engine for batch
        results = []
        for msg in messages_batch:
            mock = self._mock_analyze(msg.get("channel", ""), msg.get("sender", ""), msg.get("text", ""))
            cat = mock.category
            act = mock.action_required
            orig_channel = str(msg.get("channel", "")).lower()
            orig_uid = str(msg.get("msg_uid", "")).lower()
            if "telegram" in orig_channel or "tg_news" in orig_channel or orig_uid.startswith("tg_news_"):
                if cat in ["urgent", "important", "gov", "gov_debt", "gov_service"]:
                    cat = "news"
                act = False
            results.append(AnalysisResult(
                msg_uid=msg.get("msg_uid", ""),
                category=cat,
                summary=mock.summary,
                action_required=act,
                suggested_reply=mock.suggested_reply
            ))
        return results

    async def analyze_message(self, channel: str, sender: str, text: str, msg_uid: str = "single_msg") -> AnalysisResult:
        """Single message wrapper around batch engine."""
        res_list = await self.analyze_batch_messages([
            {"msg_uid": msg_uid, "channel": channel, "sender": sender, "text": text}
        ])
        if res_list:
            return res_list[0]
        mock = self._mock_analyze(channel, sender, text)
        return AnalysisResult(
            msg_uid=msg_uid,
            category=mock.category,
            summary=mock.summary,
            action_required=mock.action_required,
            suggested_reply=mock.suggested_reply
        )

    def _mock_analyze(self, channel: str, sender: str, text: str) -> AnalysisResult:
        text_lower = text.lower()
        spam_keywords = [
            "выигрыш", "казино", "ставка", "заработок в интернете", "крипта 100%",
            "кредит", "подпишись на канал", "бесплатно жми", "служба по контракту",
            "розыгрыш", "акция", "скидка 90%", "заработай", "пирамида",
            "инвестиции без риска", "пассивный доход", "рассылка", "unsubscribe",
            "noreply", "newsletter", "промокод"
        ]
        urgent_keywords = ["срочно", "купить", "цена", "где забрать", "оплата", "доставка", "когда отправите"]
        gov_keywords = ["госуслуги", "налог", "штраф", "фнс", "гибдд", "пенсионный", "сфр", "извещение", "повестка", "суд", "госпошлина"]
        news_keywords = ["новость", "дайджест", "статья", "выпуск", "анонс", "событие"]
        media_keywords = ["youtube", "rutube", "vk.com/video", "видео", "посмотри роли", "подкаст", "запись эфира", "стрим"]
        
        clean_text = text.strip()[:80].replace('\n', ' ')
        if len(text.strip()) > 80:
            clean_text += "..."
        snippet = clean_text if clean_text else "Без текста"
        
        if any(kw in text_lower for kw in spam_keywords):
            category = "spam"
            summary = "Обнаружены признаки рекламы или мошенничества."
            action_required = False
            suggested_reply = None
        elif any(kw in text_lower for kw in urgent_keywords):
            category = "urgent"
            summary = snippet
            action_required = True
            suggested_reply = f"Здравствуйте, {sender}! Сообщение получено, отвечу в ближайшее время."
        elif any(kw in text_lower for kw in gov_keywords):
            category = "gov"
            summary = f"Гос. уведомление: {snippet}"
            action_required = True
            suggested_reply = None
        elif any(kw in text_lower for kw in news_keywords):
            category = "news"
            summary = snippet
            action_required = False
            suggested_reply = None
        elif any(kw in text_lower for kw in media_keywords):
            category = "media"
            summary = snippet
            action_required = False
            suggested_reply = None
        else:
            category = "important" if len(text) > 30 else "general"
            summary = snippet
            action_required = False
            suggested_reply = None
            
        return AnalysisResult(
            msg_uid="mock_uid",
            category=category,
            summary=summary,
            action_required=action_required,
            suggested_reply=suggested_reply
        )

    async def ask_ai_question(self, user_text: str) -> str:
        """Answers a direct question from the user using Gemini."""
        if not self.client:
            return "К сожалению, API-ключ ИИ не настроен, я не могу ответить на ваш вопрос."
            
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            return f"Извините, сейчас включена пауза API (лимит). Попробуйте через {wait_time} сек."

        prompt = (
            "Ты — умный ИИ-помощник (AI Message Aggregator). "
            "Пользователь задает тебе вопрос или пишет сообщение напрямую в чат. "
            "Отвечай максимально подробно и полезно. "
            "У тебя есть доступ к поиску в интернете (Google Search) — используй его для поиска актуальной информации и новостей.\n\n"
            f"Сообщение пользователя:\n{user_text}"
        )
        
        active_models = self._get_active_models()
        if not active_models:
            wait_time = self._get_cooldown_wait_time()
            return f"К сожалению, все модели ИИ временно на паузе лимита. Пожалуйста, подождите {wait_time} сек."
            
        from google.genai import types
        
        for model_name in active_models:
            try:
                self._track_request()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model_name,
                        contents=prompt
                    ),
                    timeout=30.0
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                err_str = str(e)
                if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                    self.unsupported_models.add(model_name)
                    continue
                if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if "day" in err_str.lower() or "daily" in err_str.lower():
                        self.exhausted_models.add(model_name)
                        continue
                    else:
                        logger.warning(f"AI model {model_name} hit minute limit. Cooling down.")
                        self.model_cooldowns[model_name] = time.time() + 60.0
                        continue
                continue
                
        return "Произошла ошибка при обращении к ИИ. Попробуйте позже."
