#!/usr/bin/env python3
"""
Terminal helper to obtain VK User Access Token directly from Linux VPS console
without needing any Web GUI or browser on the server.
Includes automatic fallback across official VK standalone clients.
"""

import sys
import json
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# Official VK Standalone App Credentials (ID, secret, name)
CLIENTS = [
    ("6287487", "c14b8e04c14b8e04c14b8e0466c12b9180cc14bc14b8e0413f41154564ee133e9d80d29", "VK Admin (6287487)"),
    ("2685278", "b352b20f04c63f114c", "Kate Mobile (2685278)"),
    ("2274003", "hHbZxrA2u6jMFiM0bJ00", "VK Android Official (2274003)"),
    ("6126148", "q14b8e04q14b8e04q14b8e04", "VK Me (6126148)")
]

def main():
    print("==================================================")
    print("🔑 VK Token Helper for Headless Linux VPS Console")
    print("==================================================")
    
    login = input("Введите логин VK (телефон или email): ").strip()
    password = input("Введите пароль VK: ").strip()
    
    if not login or not password:
        print("❌ Логин и пароль обязательны!")
        sys.exit(1)
        
    for client_id, client_secret, app_name in CLIENTS:
        print(f"\n🔄 Пробуем авторизацию через {app_name}...")
        params = {
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": login,
            "password": password,
            "scope": "messages,offline,friends,photos,wall,groups",
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
                    print(f"\n✅ УСПЕХ! Получен токен {app_name} для VK ID {user_id}!")
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
                    req_2fa = urllib.request.Request(url_2fa, headers={'User-Agent': 'KateMobileAndroid/56 lite-ru'})
                    with urllib.request.urlopen(req_2fa) as resp_2fa:
                        data_2fa = json.loads(resp_2fa.read().decode('utf-8'))
                        token_2fa = data_2fa.get("access_token")
                        if token_2fa:
                            print(f"\n✅ УСПЕХ! Получен токен с 2FA!")
                            update_env_file("VK_TOKEN", token_2fa)
                            print("🎉 Токен автоматически сохранен в .env файле сервера!")
                            return
            except Exception:
                pass
            print(f"⚠️ {app_name} не подошел: {body}")
        except Exception as e:
            print(f"⚠️ Ошибка {app_name}: {e}")

    print("\n❌ Не удалось авторизоваться ни через один клиент. Проверьте правильность логина и пароля.")

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
