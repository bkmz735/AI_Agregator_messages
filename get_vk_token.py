#!/usr/bin/env python3
"""
Official VK ID OAuth 2.0 PKCE Helper (id.vk.ru)
Generates PKCE verifier/challenge, builds authorize URL, and exchanges authorization code for VK ID access_token & refresh_token.
"""

import os
import sys
import json
import base64
import hashlib
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def generate_pkce():
    # 32 random bytes -> base64url verifier
    code_verifier = base64url_encode(os.urandom(32))
    # SHA256(verifier) -> base64url challenge
    code_challenge = base64url_encode(hashlib.sha256(code_verifier.encode('ascii')).digest())
    state = base64url_encode(os.urandom(16))
    return code_verifier, code_challenge, state

def main():
    print("==================================================")
    print("🔑 Official VK ID OAuth 2.0 (PKCE id.vk.ru)")
    print("==================================================")
    
    # Standalone App ID (default: 6287487 or custom client_id)
    client_id = input("Введите App Client ID (по умолчанию 6287487): ").strip() or "6287487"
    redirect_uri = "https://vk.ru/blank.html"
    
    code_verifier, code_challenge, state = generate_pkce()
    
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": "vkid.personal_info messages offline",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256"
    }
    
    auth_url = f"https://id.vk.ru/authorize?{urllib.parse.urlencode(auth_params)}"
    
    print("\n--------------------------------------------------")
    print("1. Откройте эту официальную ссылку VK ID в браузере:")
    print(f"\n👉 {auth_url}\n")
    print("2. Нажмите 'Разрешить'. Вас перенаправит на ссылку с параметром 'code' и 'device_id'.")
    print("3. Скопируйте всю итоговую ссылку из адресной строки белой страницы.\n")
    
    redirect_input = input("Вставьте сюда итоговую ссылку (или парамер payload/code): ").strip()
    if not redirect_input:
        print("❌ Ошибка: пустой ввод!")
        sys.exit(1)
        
    code, device_id, input_state = parse_redirect_input(redirect_input)
    if not code:
        print("❌ Не удалось найти параметр 'code' во введенных данных!")
        sys.exit(1)
        
    print("\n🔄 Обмениваем код авторизации на Access Token через id.vk.ru/oauth2/auth...")
    
    token_data = exchange_code_for_token(
        client_id=client_id,
        code=code,
        code_verifier=code_verifier,
        device_id=device_id or "1111",
        redirect_uri=redirect_uri,
        state=input_state or state
    )
    
    if token_data and "access_token" in token_data:
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        print("\n==================================================")
        print("🎉 УСПЕХ! Токен VK ID получен!")
        print(f"Access Token: {access_token[:20]}...")
        if refresh_token:
            print(f"Refresh Token: {refresh_token[:20]}...")
        print("==================================================")
        
        update_env_file("VK_TOKEN", access_token)
        if refresh_token:
            update_env_file("VK_REFRESH_TOKEN", refresh_token)
        print("✅ Токены успешно записаны в .env файл сервера!")
    else:
        print(f"\n❌ Ошибка получения токена VK ID: {token_data}")

def parse_redirect_input(text: str):
    code, device_id, state = None, None, None
    text = text.strip()
    
    if "code=" in text:
        parsed = urllib.parse.urlparse(text)
        qs = urllib.parse.parse_qs(parsed.query or parsed.fragment)
        
        if "payload" in qs:
            try:
                payload = json.loads(qs["payload"][0])
                code = payload.get("code")
                device_id = payload.get("device_id")
                state = payload.get("state")
            except Exception:
                pass
                
        if not code and "code" in qs:
            code = qs["code"][0]
        if not device_id and "device_id" in qs:
            device_id = qs["device_id"][0]
        if not state and "state" in qs:
            state = qs["state"][0]
            
    elif len(text) > 10:
        code = text
        
    return code, device_id, state

def exchange_code_for_token(client_id, code, code_verifier, device_id, redirect_uri, state):
    url = "https://id.vk.ru/oauth2/auth"
    body_data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": code_verifier,
        "device_id": device_id,
        "redirect_uri": redirect_uri,
        "state": state
    }
    encoded_data = urllib.parse.urlencode(body_data).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=encoded_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            return json.loads(err_body)
        except Exception:
            return {"error": err_body}
    except Exception as e:
        return {"error": str(e)}

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

if __name__ == "__main__":
    main()
