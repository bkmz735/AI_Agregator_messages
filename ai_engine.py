import json
import asyncio
import logging
import socket
import time
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from config import config

logger = logging.getLogger(__name__)

# Xbox DNS Servers configuration
XBOX_DNS_SERVERS = ["111.88.96.50", "111.88.96.51"]

# Enable Custom Xbox DNS Resolver for Google / AI domains
try:
    import dns.resolver
    _original_getaddrinfo = socket.getaddrinfo

    def _xbox_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and ("googleapis.com" in host or "google" in host):
            try:
                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = XBOX_DNS_SERVERS
                resolver.timeout = 2.5
                resolver.lifetime = 2.5
                answers = resolver.resolve(host, "A")
                for rdata in answers:
                    ip = rdata.address
                    return _original_getaddrinfo(ip, port, family, type, proto, flags)
            except Exception as e:
                logger.debug(f"Xbox DNS fallback for {host}: {e}")
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _xbox_getaddrinfo
    logger.info(f"Xbox DNS Resolver enabled for AI domains ({', '.join(XBOX_DNS_SERVERS)}).")
except Exception as e:
    logger.warning(f"Could not initialize Xbox DNS Resolver: {e}")

class AnalysisResult(BaseModel):
    msg_uid: str
    category: str  # "spam", "urgent", "important", "general"
    summary: str
    action_required: bool
    suggested_reply: Optional[str] = None

class AnalysisBatchResponse(BaseModel):
    results: List[AnalysisResult]

class AudioAnalysisResult(BaseModel):
    transcription: str
    category: str
    summary: str
    action_required: bool
    suggested_reply: Optional[str] = None

class AIEngine:
    # Exact AI Free Tier Limits for your specific API key/project
    MAX_RPM = 15      # Requests per minute limit (global for the key)

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.AI_API_KEY
        self.client = None
        
        # Quota and Rate Limit trackers
        self.requests_today = 0
        self.last_reset_date = date.today()
        self.minute_request_timestamps: List[float] = []
        self.rate_limit_until: float = 0.0
        self.last_error_reason: Optional[str] = None

        # Dynamically test models in priority order. If one is exhausted (429 daily) or unsupported (404),
        # we skip it and try the next one.
        # Added high-limit Lite models (500 RPD each) as excellent fallbacks.
        self.priority_models = [
            'gemini-3.5-flash-lite', 
            'gemini-3.7-flash', 
            'gemini-3.6-flash', 
            'gemini-3.5-flash', 
            'gemini-3.1-flash-lite',
            'gemini-3-flash'
        ]
        self.exhausted_models = set()  # Daily exhausted models (reset daily)
        self.unsupported_models = set()  # Deprecated/invalid models (permanent during session)

        if self.api_key:
            try:
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

    def get_quota_stats(self) -> Dict[str, Any]:
        """Returns current AI API rate limit and usage statistics."""
        now = time.time()
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if now - t <= 60]
        
        is_paused = now < self.rate_limit_until
        pause_seconds_left = int(self.rate_limit_until - now) if is_paused else 0

        return {
            "requests_today": self.requests_today,
            "requests_this_minute": len(self.minute_request_timestamps),
            "max_rpm": self.MAX_RPM,
            "is_paused": is_paused,
            "pause_seconds_left": pause_seconds_left,
            "status_text": f"🔴 Пауза лимита ({pause_seconds_left}с)" if is_paused else "🟢 API Активен"
        }

    async def generate_content_with_retry(self, contents: Any, config: Any) -> Any:
        """Executes a AI API request with the priority models fallback and rate limit protections."""
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            raise RuntimeError(f"AI API rate limit active. Resuming in {wait_time}s.")
            
        rpm_count = len([t for t in self.minute_request_timestamps if time.time() - t <= 60])
        if rpm_count >= self.MAX_RPM:
            self.rate_limit_until = time.time() + 60.0
            raise RuntimeError(f"AI API RPM limit reached ({rpm_count}/{self.MAX_RPM}). Pausing API calls for 60s.")
            
        if not self.client:
            raise RuntimeError("AI client not initialized.")
            
        active_models = [m for m in self.priority_models if m not in self.exhausted_models and m not in self.unsupported_models]
        if not active_models:
            raise RuntimeError("No active AI models available (all exhausted or unsupported for today).")
            
        last_error = None
        for model_name in active_models:
            try:
                self._track_request()
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=model_name,
                        contents=contents,
                        config=config
                    ),
                    timeout=20.0
                )
                return response
            except Exception as e:
                err_str = str(e)
                last_error = e
                # Handle 404
                if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                    logger.warning(f"AI model {model_name} is unsupported (404).")
                    self.unsupported_models.add(model_name)
                    continue
                # Handle 429
                if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if "day" in err_str.lower() or "daily" in err_str.lower() or "quota" in err_str.lower():
                        logger.error(f"AI model {model_name} hit daily quota.")
                        self.exhausted_models.add(model_name)
                        continue
                    else:
                        self.rate_limit_until = time.time() + 60.0
                        raise RuntimeError(f"AI API 429 Minute Limit hit! Pausing API calls for 60s. Error: {e}")
                logger.warning(f"Model {model_name} failed: {e}")
                continue
                
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
                "Расшифруй это голосовое сообщение дословно на русском языке. "
                "Затем определи его категорию (spam, urgent, important, general), "
                "составь краткое резюме (summary), проверь требуется ли ответ (action_required), "
                "и предложи готовый черновик ответа (suggested_reply).\n"
                "Ответ верни строго в формате JSON с ключами: transcription, category, summary, action_required, suggested_reply."
            )
            active_models = [m for m in self.priority_models if m not in self.exhausted_models and m not in self.unsupported_models]
            if not active_models:
                logger.warning("No active AI models available (all exhausted or unsupported for today).")
            
            for model_name in active_models:
                try:
                    self._track_request()
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=model_name,
                            contents=[part, prompt],
                            config={'response_mime_type': 'application/json'}
                        ),
                        timeout=15.0
                    )
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
                        logger.warning(f"AI model {model_name} is unsupported (404). Adding to unsupported list permanently.")
                        self.unsupported_models.add(model_name)
                        continue
                    
                    # Handle 429 (quota exhausted)
                    if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if "day" in err_str.lower() or "daily" in err_str.lower() or "quota" in err_str.lower():
                            logger.error(f"AI model {model_name} hit daily quota limit. Adding to exhausted list.")
                            self.exhausted_models.add(model_name)
                            # Try next model in loop immediately
                            continue
                        else:
                            # RPM limit (minute block) - pause the engine briefly
                            self.rate_limit_until = time.time() + 60.0
                            logger.error(f"AI API 429 Minute Limit hit! Pausing API calls for 60s. Error: {e}")
                            break
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
        If batch size exceeds 5 messages, automatically splits into chunks of 5 for optimal AI accuracy.
        """
        if not messages_batch:
            return []

        # Chunking: split large batches into sub-batches of max 5 items
        CHUNK_SIZE = 5
        if len(messages_batch) > CHUNK_SIZE:
            chunks = [messages_batch[i:i + CHUNK_SIZE] for i in range(0, len(messages_batch), CHUNK_SIZE)]
            logger.info(f"Splitting batch of {len(messages_batch)} messages into {len(chunks)} sub-chunks (max {CHUNK_SIZE} msgs each)...")
            all_results = []
            for idx, chunk in enumerate(chunks, 1):
                logger.info(f"Processing chunk {idx}/{len(chunks)} ({len(chunk)} messages)...")
                while True:
                    try:
                        chunk_results = await self._analyze_single_batch_chunk(chunk, custom_prompt_suffix)
                        all_results.extend(chunk_results)
                        break
                    except RuntimeError as e:
                        if "rate limit" in str(e).lower() or "rpm limit" in str(e).lower() or "minute limit" in str(e).lower() or "429" in str(e):
                            logger.warning(f"Rate limit hit during chunking: {e}. Sleeping 60s...")
                            import asyncio
                            await asyncio.sleep(60)
                        else:
                            raise e
            return all_results
        else:
            while True:
                try:
                    return await self._analyze_single_batch_chunk(messages_batch, custom_prompt_suffix)
                except RuntimeError as e:
                    if "rate limit" in str(e).lower() or "rpm limit" in str(e).lower() or "minute limit" in str(e).lower() or "429" in str(e):
                        logger.warning(f"Rate limit hit during chunking: {e}. Sleeping 60s...")
                        import asyncio
                        await asyncio.sleep(60)
                    else:
                        raise e

    async def _analyze_single_batch_chunk(self, messages_batch: List[Dict[str, str]], custom_prompt_suffix: str = "") -> List[AnalysisResult]:
        """Analyzes a single chunk (up to 5 messages) in ONE AI API call."""
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            raise RuntimeError(f"AI API minute rate limit active. Resuming in {wait_time}s.")

        if self.client:
            # Pre-check: don't waste an API call if we already know we're over limit
            rpm_count = len([t for t in self.minute_request_timestamps if time.time() - t <= 60])
            if rpm_count >= self.MAX_RPM:
                self.rate_limit_until = time.time() + 60.0
                raise RuntimeError(f"AI API RPM limit reached ({rpm_count}/{self.MAX_RPM}). Pausing API calls for 60s.")
            else:
                batch_json_input = json.dumps(messages_batch, ensure_ascii=False)
                prompt = (
                    f"{config.AI_FILTER_PROMPT}\n"
                    f"{custom_prompt_suffix}\n\n"
                    f"Проанализируй список входящих сообщений ниже и верни массив JSON ответов для каждого сообщения:\n"
                    f"{batch_json_input}"
                )
                active_models = [m for m in self.priority_models if m not in self.exhausted_models and m not in self.unsupported_models]
                if not active_models:
                    logger.warning("No active AI models available (all exhausted or unsupported for today).")
                
                for model_name in active_models:
                    try:
                        self._track_request()
                        response = await asyncio.wait_for(
                            asyncio.to_thread(
                                self.client.models.generate_content,
                                model=model_name,
                                contents=prompt,
                                config={'response_mime_type': 'application/json'}
                            ),
                            timeout=10.0
                        )
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
                                    # Fallback if AI forgot to include msg_uid
                                    if "msg_uid" not in item and i < len(messages_batch):
                                        item["msg_uid"] = messages_batch[i]["msg_uid"]
                                    elif "msg_uid" not in item:
                                        item["msg_uid"] = f"fallback_{time.time()}_{i}"
                                    results.append(AnalysisResult(**item))
                                logger.info(f"Successfully analyzed CHUNK of {len(results)} messages via AI API ({model_name}).")
                                return results
                    except Exception as e:
                        err_str = str(e)
                        # Handle 404 (model deprecated / unsupported)
                        if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                            logger.warning(f"AI model {model_name} is unsupported (404). Adding to unsupported list permanently.")
                            self.unsupported_models.add(model_name)
                            continue
                        
                        # Handle 429 (quota exhausted)
                        if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            if "day" in err_str.lower() or "daily" in err_str.lower() or "quota" in err_str.lower():
                                logger.error(f"AI model {model_name} hit daily quota limit. Adding to exhausted list.")
                                self.exhausted_models.add(model_name)
                                # Try next model in loop immediately
                                continue
                            else:
                                # RPM limit (minute block) - pause the engine briefly
                                self.rate_limit_until = time.time() + 60.0
                                logger.error(f"AI API 429 Minute Limit hit! Pausing API calls for 60s. Error: {e}")
                                raise RuntimeError(f"AI API minute limit hit (429): {e}")
                        logger.warning(f"Batch analysis model {model_name} failed: {e}")
                        continue

        # Fallback / Mock analysis engine for batch
        results = []
        for msg in messages_batch:
            mock = self._mock_analyze(msg.get("channel", ""), msg.get("sender", ""), msg.get("text", ""))
            results.append(AnalysisResult(
                msg_uid=msg.get("msg_uid", ""),
                category=mock.category,
                summary=mock.summary,
                action_required=mock.action_required,
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
        
        clean_text = text.strip()[:60].replace('\n', ' ')
        snippet = f": {clean_text}..." if clean_text else ""
        
        if any(kw in text_lower for kw in spam_keywords):
            category = "spam"
            summary = "Обнаружены признаки рекламы или мошенничества."
            action_required = False
            suggested_reply = None
        elif any(kw in text_lower for kw in urgent_keywords):
            category = "urgent"
            summary = f"Вопрос по сделке/заказу от {sender}{snippet}"
            action_required = True
            suggested_reply = f"Здравствуйте, {sender}! Сообщение получено, отвечу в ближайшее время."
        elif any(kw in text_lower for kw in gov_keywords):
            category = "gov"
            summary = f"Официальное уведомление от {sender}{snippet}"
            action_required = True
            suggested_reply = None
        elif any(kw in text_lower for kw in news_keywords):
            category = "news"
            summary = f"Новость от {sender}{snippet}"
            action_required = False
            suggested_reply = None
        elif any(kw in text_lower for kw in media_keywords):
            category = "media"
            summary = f"Медиа/видео от {sender}{snippet}"
            action_required = False
            suggested_reply = None
        else:
            category = "important" if len(text) > 30 else "general"
            summary = f"Сообщение от {sender}{snippet}"
            action_required = False
            suggested_reply = None
            
        return AnalysisResult(
            msg_uid="mock_uid",
            category=category,
            summary=summary,
            action_required=action_required,
            suggested_reply=suggested_reply
        )
