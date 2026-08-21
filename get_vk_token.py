#!/usr/bin/env python3
"""
Terminal helper to obtain VK User Access Token directly from Linux VPS console.
Supports silent_token, OAuth 2.0 PKCE, access_token fragment, and direct token strings.
"""

import sys
import json
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

def extract_token(text: str) -> str:
    text = text.strip()
    
    # 1. Check if input is URL encoded or JSON payload containing silent_token
    if "payload=" in text:
        try:
            parsed = urllib.parse.urlparse(text)
            fragment_or_query = parsed.fragment or parsed.query
            qs = urllib.parse.parse_qs(fragment_or_query)
            if "payload" in qs:
                payload_str = qs["payload"][0]
                payload_json = json.loads(payload_str)
                if "token" in payload_json:
                    return payload_json["token"]
        except Exception:
            pass
            
    # 2. Check access_token=
    if "access_token=" in text:
        token_part = text.split("access_token=")[1]
        token = token_part.split("&")[0]
        return token

    # 3. Direct VK token string
    if text.startswith("vk1.a.") or len(text) > 30:
        return text

    return text

def update_env_file(key: str, value: str):
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        new_lines.append(f"{key}={value}")
        
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def main():
    print("==================================================")
    print("🔑 VK Token Helper (Auto Payload & Token Parser)")
    print("==================================================")
    
    token_input = input("Вставьте сюда скопированную ссылку с белой страницы или токен: ").strip()
    if not token_input:
        print("❌ Ничего не введено!")
        sys.exit(1)
        
    token = extract_token(token_input)
    if token:
        update_env_file("VK_TOKEN", token)
        print(f"\n✅ УСПЕХ! Извлечен и записан VK токен ({token[:20]}...) в .env!")
    else:
        print("❌ Не удалось извлечь токен.")

if __name__ == "__main__":
    main()
