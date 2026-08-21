#!/usr/bin/env python3
"""
Terminal helper to obtain VK User Access Token directly from Linux VPS console
without needing any Web GUI or browser on the server.
"""

import sys
import json
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

def main():
    print("==================================================")
    print("🔑 VK Token Helper for Headless Linux VPS Console")
    print("==================================================")
    
    login = input("Введите логин VK (телефон или email): ").strip()
    password = input("Введите пароль VK: ").strip()
    
    if not login or not password:
        print("❌ Логин и пароль обязательны!")
        sys.exit(1)
        
    # App ID 2685278 (Kate Mobile)
    client_id = "2685278"
    client_secret = "b352b20f04c63f114c"
    
    params = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": login,
        "password": password,
        "scope": "messages,offline,friends,photos",
        "v": "5.131"
    }
    
    url = f"https://oauth.vk.com/token?{urllib.parse.urlencode(params)}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'KateMobileAndroid/56 lite-ru'})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            token = data.get("access_token")
            user_id = data.get("user_id")
            
            if token:
                print(f"✅ Успешно получении токен для пользователя VK ID {user_id}!")
                update_env_file("VK_TOKEN", token)
                print("🎉 Токен автоматически сохранен в .env файле сервера!")
                return
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            err_data = json.loads(body)
            if err_data.get("error") == "need_2fa":
                print("🔐 Включена двухфакторная аутентификация (2FA)!")
                code = input("Введите 2FA код из СМС / привязаного приложения: ").strip()
                params["code"] = code
                url_2fa = f"https://oauth.vk.com/token?{urllib.parse.urlencode(params)}"
                req_2fa = urllib.request.Request(url_2fa, headers={'User-Agent': 'KateMobileAndroid/56 lite-ru'})
                with urllib.request.urlopen(req_2fa) as resp_2fa:
                    data_2fa = json.loads(resp_2fa.read().decode('utf-8'))
                    token_2fa = data_2fa.get("access_token")
                    if token_2fa:
                        print("✅ Успешно получении токен с 2FA!")
                        update_env_file("VK_TOKEN", token_2fa)
                        print("🎉 Токен автоматически сохранен в .env файле сервера!")
                        return
        except Exception:
            pass
        print(f"❌ Ошибка входа VK: {body}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

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
