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

# Enable Custom Xbox DNS Resolver for Google / Gemini domains
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
    logger.info(f"Xbox DNS Resolver enabled for Gemini domains ({', '.join(XBOX_DNS_SERVERS)}).")
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
    # Exact Gemini Free Tier Limits for your specific API key/project
    MAX_RPM = 5      # Requests per minute limit
    MAX_RPD = 20     # Requests per day limit

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.client = None
        
        # Quota and Rate Limit trackers
        self.requests_today = 0
        self.last_reset_date = date.today()
        self.minute_request_timestamps: List[float] = []
        self.rate_limit_until: float = 0.0
        self.last_error_reason: Optional[str] = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Gemini API client initialized successfully.")
            except Exception as e:
                logger.warning(f"Could not initialize google.genai Client: {e}. Falling back to rule-based analysis.")
        else:
            logger.info("No GEMINI_API_KEY set. Running in rule-based simulation mode.")

    def _track_request(self):
        """Updates internal rate limit counters."""
        now = time.time()
        today = date.today()

        # Reset daily counter at midnight
        if today != self.last_reset_date:
            self.requests_today = 0
            self.last_reset_date = today

        self.requests_today += 1
        self.minute_request_timestamps.append(now)

        # Keep only timestamps within the last 60 seconds
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if now - t <= 60]

    def get_quota_stats(self) -> Dict[str, Any]:
        """Returns current Gemini API rate limit and usage statistics."""
        now = time.time()
        self.minute_request_timestamps = [t for t in self.minute_request_timestamps if now - t <= 60]
        
        is_paused = now < self.rate_limit_until
        pause_seconds_left = int(self.rate_limit_until - now) if is_paused else 0

        return {
            "requests_today": self.requests_today,
            "max_rpd": self.MAX_RPD,
            "remaining_today": max(0, self.MAX_RPD - self.requests_today),
            "requests_this_minute": len(self.minute_request_timestamps),
            "max_rpm": self.MAX_RPM,
            "is_paused": is_paused,
            "pause_seconds_left": pause_seconds_left,
            "status_text": f"🔴 Пауза лимита ({pause_seconds_left}с)" if is_paused else "🟢 API Активен"
        }

    async def transcribe_and_analyze_audio(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> AudioAnalysisResult:
        """Transcribes audio/voice message using Gemini multimodal capabilities and analyzes it."""
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            logger.warning(f"Gemini API rate limited. Skipping audio API call for {wait_time}s.")
            return AudioAnalysisResult(
                transcription="[Обработка приостановлена: превышен лимит Gemini API (429)]",
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
            for model_name in ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-flash-latest']:
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
                        logger.info(f"Successfully transcribed audio ({len(audio_bytes)} bytes) using Gemini {model_name}.")
                        return AudioAnalysisResult(
                            transcription=parsed.get("transcription", "Расшифровка недоступна"),
                            category=parsed.get("category", "important"),
                            summary=parsed.get("summary", "Голосовое сообщение"),
                            action_required=parsed.get("action_required", True),
                            suggested_reply=parsed.get("suggested_reply", "Спасибо за голосовое сообщение! Прослушал, отвечу в ближайшее время.")
                        )
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        self.rate_limit_until = time.time() + 60.0
                        logger.error(f"Gemini API 429 Rate Limit hit! Pausing API calls for 60s. Error: {e}")
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

    async def analyze_batch_messages(self, messages_batch: List[Dict[str, str]]) -> List[AnalysisResult]:
        """
        Analyzes a BATCH of raw incoming messages in a single Gemini API call to save tokens!
        """
        if not messages_batch:
            return []

        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            logger.warning(f"Gemini API rate limited (429). Retrying batch after {wait_time}s...")
            return [
                AnalysisResult(
                    msg_uid=msg.get("msg_uid", ""),
                    category="important",
                    summary=f"В буфере (ожидание сброса лимита ИИ {wait_time}с)",
                    action_required=True,
                    suggested_reply=None
                ) for msg in messages_batch
            ]

        if self.client:
            batch_json_input = json.dumps(messages_batch, ensure_ascii=False)
            prompt = (
                f"{config.AI_FILTER_PROMPT}\n\n"
                f"Проанализируй список входящих сообщений ниже и верни массив JSON ответов для каждого сообщения:\n"
                f"{batch_json_input}"
            )
            
            for model_name in ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-1.5-flash']:
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
                        parsed = json.loads(response.text)
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
                            logger.info(f"Successfully analyzed BATCH of {len(results)} messages via Gemini API ({model_name}).")
                            return results
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "Quota" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        self.rate_limit_until = time.time() + 60.0
                        logger.error(f"Gemini API 429 Rate Limit hit! Pausing API calls for 60s. Error: {e}")
                        break
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
        spam_keywords = ["выигрыш", "казино", "ставка", "заработок в интернете", "крипта 100%", "кредит", "подпишись на канал", "бесплатно жми"]
        urgent_keywords = ["срочно", "купить", "цена", "где забрать", "оплата", "доставка", "когда отправите"]
        
        if any(kw in text_lower for kw in spam_keywords):
            category = "spam"
            summary = "Обнаружены признаки рекламы или мошенничества."
            action_required = False
            suggested_reply = None
        elif any(kw in text_lower for kw in urgent_keywords):
            category = "urgent"
            summary = f"Вопрос по сделке/заказу от {sender} в {channel}."
            action_required = True
            suggested_reply = f"Здравствуйте, {sender}! Сообщение получено, отвечу в ближайшее время."
        else:
            category = "important" if len(text) > 30 else "general"
            summary = f"Сообщение от {sender}: {text[:60]}..."
            action_required = False
            suggested_reply = None
            
        return AnalysisResult(
            msg_uid="mock_uid",
            category=category,
            summary=summary,
            action_required=action_required,
            suggested_reply=suggested_reply
        )
