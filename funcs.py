import os
from dbase import DataBase
import pyperclip
import glob
import json
import threading
from steamguard import SteamMobile, LoginConfirmType
from steampy.guard import generate_one_time_code
from playwright.sync_api import sync_playwright
from aiosteampy import SteamClient
from aiosteampy.utils import update_session_cookies, get_jsonable_cookies
import asyncio
import traceback
import requests

baza = DataBase("data.db")

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"


def copy_acc_guard(_, login):
    account, _ = baza.get_acc(login)
    pyperclip.copy(generate_one_time_code(account['shared_secret']))


def copy_acc_pass(_, login):
    account, _ = baza.get_acc(login)
    pyperclip.copy(account["password"])


def copy_acc_login(_, login):
    pyperclip.copy(login)


def convert_id64_id32(steam_id):
    steamid64ident = 76561197960265728
    return int(steam_id) - steamid64ident


def convert_id32_id64(steam_id):
    steamid64ident = 76561197960265728
    return int(steam_id) + steamid64ident


def search_maf(login):
    search_patterns = [
        './mafs/*.maFile',
        './*.maFile',
        './**/*.maFile',
    ]
    for pattern in search_patterns:
        for maf in glob.glob(pattern, recursive=True):
            try:
                with open(maf, 'r', encoding='utf-8') as f:
                    info = json.loads(f.read())
                    if login.lower() == info.get('account_name', '').lower():
                        print(f"Найден maFile для {login}: {maf}")
                        return maf, info['Session']['SteamID'], info['shared_secret'], info.get('identity_secret')
            except Exception as ex:
                print(f"Ошибка чтения {maf}: {ex}")
    print(f"maFile для '{login}' не найден.")
    return None, None, None, None


def import_accounts():
    import_accounts_verbose()


def import_accounts_verbose():
    added, skipped, errors = 0, 0, 0
    with open('accs.txt', 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    for account in lines:
        parts = account.split(':')
        if len(parts) < 2:
            print(f"Неверный формат строки: {account}")
            errors += 1
            continue
        login = parts[0]
        password = parts[1]
        maf_path, steam_id_64, shared_secret, identity_secret = search_maf(login)
        if not maf_path:
            print(f"Не удалось найти мафайл для аккаунта {login}")
            errors += 1
            continue
        existed = baza.get_acc(login)[0]
        baza.add_account(login, password, shared_secret, identity_secret,
                         convert_id64_id32(steam_id_64))
        if existed:
            skipped += 1
        else:
            added += 1

    return added, skipped, errors


def auth_account(login: str):
    account, _ = baza.get_acc(login)
    if not account:
        raise ValueError(f"Аккаунт {login} не найден в базе")
    cookies = cookie(account['login'], account['password'], account['shared_secret'])
    baza.update_cookies(login, cookies)
    if account.get('steamid32'):
        avatar_path = fetch_steam_avatar(account['steamid32'])
        if avatar_path:
            baza.update_avatar(login, avatar_path)
    print(f"[{login}] Куки сохранены")


def cookie(log, pas, shared):
    mobile = SteamMobile(log, pas)
    mobile.get_steampowered()
    mobile.get_steamcommunity()
    code_type = mobile.login()
    guard = generate_one_time_code(shared)

    if code_type == LoginConfirmType.none:
        mobile.confirm_login()
    elif code_type == LoginConfirmType.email:
        email_code = input('Enter Steam Guard Code Email > ')
        mobile.confirm_login(email_code)
    elif code_type == LoginConfirmType.mobile:
        mobile_code = mobile.generate_steam_guard_code() or guard
        mobile.confirm_login(mobile_code)

    data = mobile.export()["cookies"]
    for i in range(len(data)):
        if type(data[i]["expires"]) != int:
            data[i]["expires"] = 1897035906

    return data


def _cookies_to_dict(cookies_list: list) -> dict:
    """Конвертирует список куки [{name, value, ...}] в простой dict."""
    return {c["name"]: c["value"] for c in cookies_list if "name" in c and "value" in c}


def set_steam_avatar(login: str, image_path: str) -> str:
    """
    Устанавливает аватарку профиля Steam через авторизованную HTTP-сессию.
    Возвращает пустую строку при успехе или строку с описанием ошибки.
    """
    account, cookies_list = baza.get_acc(login)
    if not account:
        return f"Аккаунт {login} не найден в базе"
    if not cookies_list:
        return "Аккаунт не авторизован. Сначала нажмите Auth."
    if not os.path.exists(image_path):
        return f"Файл не найден: {image_path}"

    steamid32 = account.get("steamid32")
    if not steamid32:
        return "steamid32 не задан для аккаунта"

    steamid64 = convert_id32_id64(steamid32)
    cookies = _cookies_to_dict(cookies_list)

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})

    # Устанавливаем куки в сессию
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".steamcommunity.com")

    # Получаем актуальный sessionid
    sessionid = cookies.get("sessionid", "")
    if not sessionid:
        try:
            session.get("https://steamcommunity.com/", timeout=10)
            sessionid = session.cookies.get("sessionid", "")
        except Exception as ex:
            return f"Не удалось получить sessionid: {ex}"

    if not sessionid:
        return "sessionid не найден. Переавторизуйтесь."

    # Определяем MIME-тип
    ext = os.path.splitext(image_path)[1].lower().strip(".")
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",  "webp": "image/webp",
        "gif": "image/gif",
    }
    mime = mime_map.get(ext, "image/jpeg")

    try:
        with open(image_path, "rb") as f:
            img_data = f.read()

        url = "https://steamcommunity.com/actions/FileUploader/"
        files = {
            "avatar": (os.path.basename(image_path), img_data, mime),
        }
        data = {
            "type":      "player_avatar_image",
            "sId":       str(steamid64),
            "sessionid": sessionid,
            "doSub":     "1",
            "json":      "1",
        }

        resp = session.post(url, files=files, data=data, timeout=20)
        print(f"[{login}] Steam avatar upload: HTTP {resp.status_code}")
        print(f"[{login}] Response: {resp.text[:300]}")

        if resp.status_code == 200:
            # Пытаемся распарсить JSON
            try:
                j = resp.json()
                success = j.get("success") or j.get("result") == "ok"
            except Exception:
                success = "success" in resp.text.lower()

            if success:
                baza.update_avatar(login, image_path)
                return ""
            else:
                try:
                    j = resp.json()
                    msg = j.get("message") or j.get("error") or str(j)
                except Exception:
                    msg = resp.text[:200]
                return f"Steam вернул ошибку: {msg}"
        else:
            return f"HTTP {resp.status_code}: {resp.text[:150]}"

    except Exception as ex:
        return f"Ошибка: {ex}"


def fetch_steam_avatar(steamid32: int) -> str | None:
    import re
    os.makedirs("avatars", exist_ok=True)
    local_path = f"avatars/{steamid32}.jpg"

    if os.path.exists(local_path):
        return local_path

    try:
        steamid64 = convert_id32_id64(steamid32)
        xml_url = f"https://steamcommunity.com/profiles/{steamid64}/?xml=1"
        headers = {"User-Agent": user_agent}
        resp = requests.get(xml_url, timeout=10, headers=headers)

        if resp.status_code != 200:
            return None

        match = re.search(r'<avatarFull>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</avatarFull>', resp.text)
        if not match:
            return None

        avatar_url = match.group(1).strip()
        img_resp = requests.get(avatar_url, timeout=10, headers=headers)
        if img_resp.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(img_resp.content)
            return local_path
    except Exception as e:
        print(f"[avatar] Ошибка: {e}")
    return None


async def setup_client_session(login: str) -> SteamClient:
    account, cookies = baza.get_acc(login)
    if not account:
        raise ValueError(f"Аккаунт {login} не найден в базе")

    client = SteamClient(
        account["steamid32"],
        account['login'],
        account['password'],
        account['shared_secret'],
        account['identity_secret'],
        user_agent=user_agent
    )

    if cookies:
        try:
            update_session_cookies(client.session, cookies)
            await client.prepare()
            print(f"Сессия восстановлена для {login} через куки")
            return client
        except Exception as e:
            print(f"Не удалось восстановить сессию: {e}")

    try:
        await client.login()
        await client.prepare()
        new_cookies = get_jsonable_cookies(client.session)
        baza.update_cookies(login, new_cookies)
        print(f"Сессия обновлена для {login} через логин")
        return client
    except Exception as e:
        await client.session.close()
        raise RuntimeError(f"Не удалось залогиниться на {login}: {e}")


def browser(_, login):
    def _run():
        try:
            account, _ = baza.get_acc(login)
            with sync_playwright() as p:
                br = p.chromium.launch(headless=False)
                context = br.new_context()
                page = context.new_page()
                page.goto("https://store.steampowered.com")
                cookies = cookie(account['login'], account['password'], account['shared_secret'])
                context.add_cookies(cookies)
                page.goto("https://steamcommunity.com/")
                page.wait_for_event("close", timeout=0)
        except Exception as e:
            print(f"[{login}] Ошибка: {type(e)}")
            traceback.print_exc()

    threading.Thread(target=_run, daemon=True).start()


async def confirm_all(login):
    client = await setup_client_session(login)
    try:
        active_listings, to_confirm, buy_orders, total_count = await client.get_my_listings()
        for listing in to_confirm:
            try:
                await client.confirm_sell_listing(listing)
                print(f"[{login}] Confirmed: {listing.item.description.market_name}")
            except Exception as e:
                print(f"[{login}] ITEM SKIPPED: {e}")
    finally:
        await client.session.close()


async def deny_all(login):
    client = await setup_client_session(login)
    try:
        active_listings, to_confirm, buy_orders, total_count = await client.get_my_listings()
        for listing in to_confirm:
            await client.cancel_sell_listing(listing)
            print(f"[{login}] Отклонено: {listing.item.description.market_name}")
    finally:
        await client.session.close()


def delete_account(login: str):
    return baza.delete_account(login)


def copy_all_acc_data(_, login: str):
    account, _ = baza.get_acc(login)
    guard = generate_one_time_code(account['shared_secret']) if account.get('shared_secret') else ""
    text = f"Login: {account['login']}\nPassword: {account['password']}\nGuard: {guard}"
    pyperclip.copy(text)


def add_account_manual(login: str, password: str, shared_secret: str = "",
                       identity_secret: str = "", steamid32: int = 0):
    baza.add_account(login, password, shared_secret, identity_secret, steamid32)
