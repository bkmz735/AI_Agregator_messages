#!/usr/bin/env python3
"""
Terminal helper to obtain VK User Access Token directly from Linux VPS console
without needing any Web GUI or browser on the server.
"""

import sys
import json
import urllib.parse
import urllib.request
from pathlibPath = Path
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# Supported Standalone App IDs:
# 6287487 = VK Admin (vk.com official client)
# 2685278 = Kate Mobile
# 6126148 = VK Me
APP_CLIENTS = {
    "1": ("6287487", None, "VK Admin / vk.com (ID: 6287487)"),
    "2": ("2685278", "b352b20f04c63f114c", "Kate Mobile (ID: 2685278)"),
    "3": ("6126148", "q14b8e04q14b8e04q14b8e04", "VK Me (ID: 6126148)")
}

def main():
    print("==================================================")
    print("🔑 VK Token Helper for Headless Linux VPS Console")
    print("==================================================")
    
    print("Выберите клиент VK для токена:")
    print("1. VK Admin / vk.com (ID: 6287487) [По умолчанию]")
    print("2. Kate Mobile (ID: 2685278)")
    print("3. VK Me (ID: 6126148)")
    choice = input("Введите номер [1-3] (по умолчанию 1): ").strip() or "1"
    
    client_id, client_secret, app_name = APP_CLIENTS.get(choice, APP_CLIENTS["1"])
    print(f"\nИспользуем клиент: {app_name}")
    
    login = input("Введите логин VK (телефон или email): ").strip()
    password = input("Введите пароль VK: ").strip()
    
    if not login or not password:
        print("❌ Логин и пароль обязательны!")
        sys.exit(1)
        
    params = {
        "grant_type": "password",
        "client_id": client_id,
        "username": login,
        "password": password,
        "scope": "messages,offline,friends,photos,wall,groups",
        "v": "5.131"
    }
    if client_secret:
        params["client_secret"] = client_secret
    
    url = f"https://oauth.vk.com/token?{urllib.parse.urlencode(params)}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'VKAdmin/1.0 (Android; 10; ARM64; ru)'})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            token = data.get("access_token")
            user_id = data.get("user_id")
            
            if token:
                print(f"\n✅ Успешно получен токен {app_name} для пользователя VK ID {user_id}!")
                update_env_file("VK_TOKEN", token)
                print("🎉 Токен автоматически сохранен в .env файле сервера!")
                return
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            err_data = json.loads(body)
            if err_data.get("error") == "need_2fa":
                print("\n🔐 Включена двухфакторная аутентификация (2FA)!")
                code = input("Введите 2FA код из СМС / приложения: ").strip()
                params["code"] = code
                url_2fa = f"https://oauth.vk.com/token?{urllib.parse.urlencode(params)}"
                req_2fa = urllib.request.Request(url_2fa, headers={'User-Agent': 'VKAdmin/1.0'})
                with urllib.request.urlopen(req_2fa) as resp_2fa:
                    data_2fa = json.loads(resp_2fa.read().decode('utf-8'))
                    token_2fa = data_2fa.get("access_token")
                    if token_2fa:
                        print(f"\n✅ Успешно получен токен {app_name} с 2FA!")
                        update_env_file("VK_TOKEN", token_2fa)
                        print("🎉 Токен автоматически сохранен в .env файле сервера!")
                        return
        except Exception:
            pass
        print(f"\n❌ Ошибка входа VK ({app_name}): {body}")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

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
