import re

fpath = 'c:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/ai_engine.py'
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern for the ask_ai_question function
pattern = r'    async def ask_ai_question\(self, user_text: str\) -> str:\n(?:.|\n)*?    async def summarize_news\('

match = re.search(pattern, content)
if match:
    # Build new function
    new_func = """    async def ask_ai_question(self, user_text: str) -> str:
        \"\"\"Answers a direct question from the user using Gemini.\"\"\"
        if not self.client:
            return "❌ Ошибка, API-ключ не настроен, ИИ недоступен."
            
        now = time.time()
        if now < self.rate_limit_until:
            wait_time = int(self.rate_limit_until - now)
            return f"⏳ Лимит запросов API (429). Подождите {wait_time} сек."

        prompt = (
            "Ты полезный ИИ-помощник (AI Message Aggregator). "
            "Отвечай на вопросы пользователя максимально полно и развернуто. "
            "Если требуется поиск информации, используй доступ к сети. "
            "Используй форматирование Telegram, где уместно.\n\n"
            f"Вопрос пользователя:\n{user_text}"
        )
        
        active_models = [m for m in self.priority_models if m not in self.exhausted_models and m not in self.unsupported_models]
        if not active_models:
            return "❌ Ошибка, нет доступных моделей ИИ на сегодня."
            
        from google.genai import types
        
        for model_name in active_models:
            try:
                self._track_request()
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            tools=[{"google_search": {}}]
                        )
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
                    if "day" in err_str.lower() or "daily" in err_str.lower() or "quota" in err_str.lower():
                        self.exhausted_models.add(model_name)
                        continue
                    else:
                        self.rate_limit_until = time.time() + 60.0
                        return f"⏳ Лимит минутный (429). Подождите минуту."
                continue
        return "❌ Не удалось получить ответ от ИИ."

    async def summarize_news("""
    
    new_content = content.replace(match.group(0), new_func)
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Replaced ask_ai_question!")
else:
    print("Could not match.")
