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

# VK Admin Standalone App ID: 6287487
VK_ADMIN_AUTH_URL = "https://oauth.vk.com/authorize?client_id=6287487&scope=1073737727&redirect_uri=https://oauth.vk.com/blank.html&response_type=token&revoke=1"

def main():
    print("==================================================")
    print("🔑 VK Token Helper (VK Admin / ID: 6287487)")
    print("==================================================")
    print("ВКонтакте (VK ID) блокирует прямой ввод паролей для сторонних приложений.")
    print("Выберите удобный способ получения токена:\n")
    print("1. 🔗 Вставить токен/ссылку из браузера (100% надежно для любого VK аккаунта)")
    print("2. 🔑 Ввести логин и пароль VK прямо в консоли")
    
    choice = input("\nВыберите вариант [1-2] (по умолчанию 1): ").strip() or "1"
    
    if choice == "1":
        print("\n--------------------------------------------------")
        print("1. Откройте эту ссылку в любом браузере (на ПК или телефоне):")
        print(f"\n👉 {VK_ADMIN_AUTH_URL}\n")
        print("2. Нажмите 'Разрешить'. Вас перенаправит на белую страницу.")
        print("3. Скопируйте целиком адрес этой страницы из браузера (или сам токен после access_token=).\n")
        
        token_input = input("Вставьте сюда скопированную ссылку или токен: ").strip()
        if not token_input:
            print("❌ Ничего не введено!")
            sys.exit(1)
            
        token = extract_token(token_input)
        if token:
            update_env_file("VK_TOKEN", token)
            print("\n✅ УСПЕХ! Токен VK Admin (6287487) успешно записан в .env!")
            return
        else:
            print("❌ Не удалось извлечь access_token из введенного текста.")
            sys.exit(1)
            
    else:
        login = input("\nВведите логин VK (телефон без + или email): ").strip()
        password = input("Введите пароль VK: ").strip()
        
        if not login or not password:
            print("❌ Логин и пароль обязательны!")
            sys.exit(1)
            
        clients = [
            ("6287487", "c14b8e04c14b8e04c14b8e0466c12b9180cc14bc14b8e0413f41154564ee133e9d80d29", "VK Admin (6287487)"),
            ("2685278", "b352b20f04c63f114c", "Kate Mobile (2685278)"),
            ("2274003", "hHbZxrA2u6jMFiM0bJ00", "VK Android (2274003)")
        ]
        
        for client_id, client_secret, app_name in clients:
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
                print(f"⚠️ Ошибка: {e}")

def extract_token(text: str) -> str:
    text = text.strip()
    if "access_token=" in text:
        token_part = text.split("access_token=")[1]
        token = token_part.split("&")[0]
        return token
    elif text.startswith("vk1.a."):
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

if __name__ == "__main__":
    main()
