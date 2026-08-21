import json
import asyncio
import logging
from typing import Optional
from pydantic import BaseModel
from config import config

logger = logging.getLogger(__name__)

class AnalysisResult(BaseModel):
    category: str  # "spam", "urgent", "important", "general"
    summary: str
    action_required: bool
    suggested_reply: Optional[str] = None

class AIEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.client = None
        
        if self.api_key:
            try:
                from google import genai
                # Connect directly from local server (no VPN proxy for Gemini)
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Gemini API client initialized directly (no VPN proxy).")
            except Exception as e:
                logger.warning(f"Could not initialize google.genai Client: {e}. Falling back to rule-based analysis.")
        else:
            logger.info("No GEMINI_API_KEY set. Running in rule-based simulation mode.")

    async def analyze_message(self, channel: str, sender: str, text: str) -> AnalysisResult:
        """
        Analyzes an incoming message using Gemini API structured output (JSON).
        If API key is missing or fails, uses robust rule-based mock analysis.
        """
        if self.client:
            prompt = f"{config.AI_FILTER_PROMPT}\n\n[Канал]: {channel}\n[Отправитель]: {sender}\n[Текст]:\n{text}"
            
            for model_name in ['gemini-flash-latest', 'gemini-3.6-flash', 'gemini-3.5-flash']:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.client.models.generate_content,
                            model=model_name,
                            contents=prompt,
                            config={'response_mime_type': 'application/json'}
                        ),
                        timeout=6.0
                    )
                    if response and response.text:
                        result_data = json.loads(response.text)
                        logger.info(f"Successfully analyzed via Gemini API ({model_name}): {result_data.get('category')}")
                        return AnalysisResult(**result_data)
                except Exception as e:
                    logger.warning(f"Model {model_name} skipped or timed out: {e}")
                    continue

        # Fallback / Mock analysis engine
        return self._mock_analyze(channel, sender, text)

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
            category=category,
            summary=summary,
            action_required=action_required,
            suggested_reply=suggested_reply
        )
