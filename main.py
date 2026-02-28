import random
import threading
import requests
import flet as ft
import os

from dbase import DataBase

# ─── Папка данных: %APPDATA%\SharkAccountSystem ───────────────────────────
APP_DATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'SharkAccountSystem')
os.makedirs(APP_DATA_DIR, exist_ok=True)

ACCS_FILE   = os.path.join(APP_DATA_DIR, 'accs.txt')
MAFS_DIR    = os.path.join(APP_DATA_DIR, 'mafs')
AVATARS_DIR = os.path.join(APP_DATA_DIR, 'avatars')
DB_FILE     = os.path.join(APP_DATA_DIR, 'data.db')
JS_DIR      = os.path.dirname(os.path.abspath(__file__))

os.makedirs(MAFS_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)
if not os.path.exists(ACCS_FILE):
    open(ACCS_FILE, 'w').close()

import asyncio
import sys

# Подавляем безвредный ConnectionResetError при закрытии на Windows
_orig_exc_handler = None
def _suppress_connection_reset(loop, context):
    exc = context.get("exception")
    if isinstance(exc, ConnectionResetError):
        return
    if _orig_exc_handler:
        _orig_exc_handler(loop, context)
    else:
        loop.default_exception_handler(context)

def _install_exception_handler():
    global _orig_exc_handler
    loop = asyncio.get_event_loop()
    _orig_exc_handler = loop.get_exception_handler()
    loop.set_exception_handler(_suppress_connection_reset)

baza = DataBase(DB_FILE)
baza.create_tables()
baza.migrate()
baza.reset_remote_avatars()

import funcs


def main(page: ft.Page):
    try:
        _install_exception_handler()
    except Exception:
        pass
    page.title = "Shark Account System"
    page.scroll = None
    page.horizontal_alignment = ft.CrossAxisAlignment.START
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
    page.bgcolor = "#0d2626"
    page.padding = 0

    page.window.width = 1600
    page.window.height = 900
    page.window.min_width = 1200
    page.window.min_height = 700
    page.window.resizable = True

    BG_IMAGE = os.path.join(JS_DIR, "bg.jpg")

    # ─── Тема ────────────────────────────────────────────────────────────────
    is_dark = [True]

    def toggle_theme(e):
        is_dark[0] = not is_dark[0]
        if is_dark[0]:
            page.theme_mode = ft.ThemeMode.DARK
            page.bgcolor = "#0d2626"
            left_panel.bgcolor  = ft.Colors.with_opacity(0.45, "#062020")
            right_panel.bgcolor = ft.Colors.with_opacity(0.45, "#062020")
            left_panel.border  = ft.Border(right=ft.BorderSide(1, ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300)))
            right_panel.border = ft.Border(left=ft.BorderSide(1,  ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300)))
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
            page.bgcolor = "#e0f7f4"
            left_panel.bgcolor  = ft.Colors.with_opacity(0.93, "#f0fffe")
            right_panel.bgcolor = ft.Colors.with_opacity(0.93, "#f0fffe")
            left_panel.border  = ft.Border(right=ft.BorderSide(1, ft.Colors.with_opacity(0.25, ft.Colors.TEAL_400)))
            right_panel.border = ft.Border(left=ft.BorderSide(1,  ft.Colors.with_opacity(0.25, ft.Colors.TEAL_400)))
        theme_btn.icon = ft.Icons.LIGHT_MODE if is_dark[0] else ft.Icons.DARK_MODE
        theme_btn.icon_color = ft.Colors.CYAN_300 if is_dark[0] else ft.Colors.TEAL_700
        page.update()

    # ─── Snackbar ─────────────────────────────────────────────────────────────
    def show_snackbar(message, color=ft.Colors.GREY_900):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def on_copy_click(e, name, func):
        func(e, name)
        show_snackbar("Copied!")

    # ─── Счётчик ──────────────────────────────────────────────────────────────
    total_text = ft.Text("", size=13, color=ft.Colors.WHITE70)
    auth_text  = ft.Text("", size=13, color=ft.Colors.GREEN_300)

    def refresh_counter():
        total  = baza.all_count()
        authed = baza.auth_count()
        total_text.value = f"Всего: {total}"
        auth_text.value  = f"Авторизовано: {authed}"
        page.title = f"Shark Account System | {total} аккаунтов"
        page.update()

    # ═══════════════════════════════════════════════════════════════════════════
    # ПРАВАЯ ПАНЕЛЬ — ИНВЕНТАРЬ
    # ═══════════════════════════════════════════════════════════════════════════
    inv_login_text = ft.Text("Выберите аккаунт", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE70)
    inv_count_text = ft.Text("", size=12, color=ft.Colors.BLUE_300)
    inv_game_tabs  = ft.Ref[ft.Row]()

    # Сетка иконок предметов
    inv_grid = ft.GridView(
        expand=True,
        runs_count=5,
        max_extent=88,
        child_aspect_ratio=1.0,
        spacing=6,
        run_spacing=6,
    )

    inv_status = ft.Text("← Нажмите на строку аккаунта", size=13,
                         color=ft.Colors.WHITE38, italic=True)

    # appid -> название игры
    GAMES = {
        "730":  "CS2",
        "440":  "TF2",
        "570":  "Dota 2",
        "252490": "Rust",
        "271590": "GTA V",
    }

    selected_login = [None]
    selected_appid = ["730"]

    def load_inventory(login, appid="730"):
        selected_login[0] = login
        selected_appid[0] = appid

        inv_login_text.value = f"🎮  {login}"
        inv_count_text.value = "Загрузка..."
        inv_grid.controls.clear()
        inv_status.value = ""

        # Показываем спиннер
        inv_grid.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.ProgressRing(width=32, height=32, stroke_width=3, color=ft.Colors.BLUE_300),
                    ft.Text("Загрузка инвентаря...", color=ft.Colors.WHITE38, size=12),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                alignment=ft.alignment.Alignment(0, 0),
                expand=True,
            )
        )
        page.update()

        def _fetch():
            try:
                account, _ = baza.get_acc(login)
                steamid32 = account.get("steamid32", 0)
                steamid64 = funcs.convert_id32_id64(steamid32) if steamid32 else 0

                url = f"https://steamcommunity.com/inventory/{steamid64}/{appid}/2?l=english&count=200"
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(url, timeout=10, headers=headers)

                inv_grid.controls.clear()

                if resp.status_code == 200:
                    data  = resp.json()
                    total = data.get("total_inventory_count", 0)
                    assets = data.get("assets", [])
                    descs  = {d["classid"]: d for d in data.get("descriptions", [])}

                    inv_count_text.value = f"{total} предметов"

                    # Цвета редкости CS2
                    RARITY_COLORS = {
                        "b0c3d9": "#b0c3d9",  # Common
                        "5e98d9": "#5e98d9",  # Uncommon
                        "4b69ff": "#4b69ff",  # Rare
                        "8847ff": "#8847ff",  # Mythical
                        "d32ce6": "#d32ce6",  # Legendary
                        "eb4b4b": "#eb4b4b",  # Ancient
                        "e4ae39": "#e4ae39",  # Immortal/Contraband
                        "caab05": "#caab05",  # Rare Special
                    }

                    for asset in assets:
                        desc = descs.get(asset.get("classid", ""), {})
                        name = desc.get("market_hash_name", desc.get("name", "?"))
                        icon_hash = desc.get("icon_url", "")
                        icon_url  = f"https://community.akamai.steamstatic.com/economy/image/{icon_hash}/88x88" if icon_hash else ""

                        # Цвет рамки по редкости
                        border_color = "#3a3a4a"
                        for tag in desc.get("tags", []):
                            if tag.get("category") == "Rarity":
                                tc = tag.get("color", "")
                                if tc in RARITY_COLORS:
                                    border_color = RARITY_COLORS[tc]

                        # Карточка предмета
                        if icon_url:
                            item_img = ft.Image(src=icon_url, width=72, height=72, fit="contain",
                                                error_content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED,
                                                                       color=ft.Colors.WHITE24, size=28))
                        else:
                            item_img = ft.Icon(ft.Icons.INVENTORY_2, color=ft.Colors.WHITE38, size=32)

                        card = ft.Container(
                            content=ft.Stack([
                                ft.Container(
                                    content=item_img,
                                    alignment=ft.alignment.Alignment(0, 0),
                                    width=84, height=84,
                                ),
                            ]),
                            width=84, height=84,
                            bgcolor="#1e1e2e",
                            border_radius=6,
                            border=ft.Border.all(1, border_color),
                            tooltip=name,
                            ink=True,
                        )
                        inv_grid.controls.append(card)

                    if not assets:
                        inv_status.value = "Инвентарь пуст"

                elif resp.status_code == 403:
                    inv_count_text.value = "Инвентарь закрыт"
                    inv_status.value = "Профиль приватный — откройте инвентарь в настройках Steam"
                else:
                    inv_count_text.value = f"Ошибка {resp.status_code}"
                    inv_status.value = "Не удалось загрузить инвентарь"

            except Exception as ex:
                inv_count_text.value = "Ошибка"
                inv_status.value = str(ex)

            page.update()

        threading.Thread(target=_fetch, daemon=True).start()

    def switch_game(appid):
        selected_appid[0] = appid
        for btn in game_btns:
            is_active = btn.data == appid
            btn.style = ft.ButtonStyle(
                color=ft.Colors.WHITE if is_active else ft.Colors.WHITE38,
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.BLUE) if is_active
                        else ft.Colors.TRANSPARENT,
            )
            if isinstance(btn.content, ft.Text):
                btn.content.color = ft.Colors.WHITE if is_active else ft.Colors.WHITE38
        if selected_login[0]:
            load_inventory(selected_login[0], appid)
        page.update()

    game_btns = []
    for aid, gname in GAMES.items():
        btn = ft.TextButton(
            content=ft.Text(gname, size=13),
            data=aid,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE if aid == "730" else ft.Colors.WHITE38,
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.BLUE) if aid == "730"
                        else ft.Colors.TRANSPARENT,
            ),
            on_click=lambda e: switch_game(e.control.data),
        )
        game_btns.append(btn)

    # ═══════════════════════════════════════════════════════════════════════════
    # ПРАВАЯ ПАНЕЛЬ — ВКЛАДКА «ОФОРМЛЕНИЕ»
    # ═══════════════════════════════════════════════════════════════════════════

    profile_login = [None]

    # --- Поля профиля ---
    profile_avatar_preview = ft.Container(
        width=80, height=80,
        border_radius=40,
        bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
        border=ft.Border.all(2, ft.Colors.TEAL_300),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=60, color=ft.Colors.TEAL_300),
    )

    profile_login_label = ft.Text("Выберите аккаунт", size=13, color=ft.Colors.WHITE70, weight=ft.FontWeight.BOLD)

    def refresh_profile_view(login):
        profile_login[0] = login
        profile_login_label.value = f"👤  {login}"
        account, _ = baza.get_acc(login)
        avatar_url = account.get("avatar_url") if account else None
        if avatar_url and os.path.exists(avatar_url):
            profile_avatar_preview.content = ft.Image(src=avatar_url, width=80, height=80, fit="cover")
        else:
            profile_avatar_preview.content = ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=60, color=ft.Colors.TEAL_300)
        page.update()

    def on_profile_pick_avatar(e):
        login = profile_login[0]
        if not login:
            show_snackbar("Сначала выберите аккаунт", color=ft.Colors.ORANGE_800)
            return
        import shutil
        from tkinter import Tk, filedialog
        def _run():
            root = Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            src = filedialog.askopenfilename(
                title=f"Аватарка для {login}",
                filetypes=[("Изображения", "*.jpg *.jpeg *.png *.webp *.gif")])
            root.destroy()
            if not src:
                return
            os.makedirs(AVATARS_DIR, exist_ok=True)
            ext = os.path.splitext(src)[1].lower() or ".jpg"
            dst = os.path.join(AVATARS_DIR, f"{login}{ext}")
            try:
                shutil.copy2(src, dst)
                baza.update_avatar(login, dst)
                update_table()
                refresh_profile_view(login)
                show_snackbar(f"[{login}] Аватарка выбрана ✓", color=ft.Colors.GREEN_800)
            except Exception as ex:
                show_snackbar(f"Ошибка: {ex}", color=ft.Colors.RED_800)
        threading.Thread(target=_run, daemon=True).start()

    def on_profile_upload_avatar(e):
        login = profile_login[0]
        if not login:
            show_snackbar("Сначала выберите аккаунт", color=ft.Colors.ORANGE_800)
            return
        import glob as _glob
        found = None
        for ext in ("jpg", "jpeg", "png", "webp", "gif"):
            candidates = _glob.glob(os.path.join(AVATARS_DIR, f"{login}.{ext}"))
            if candidates:
                found = candidates[0]
                break
        if not found:
            show_snackbar(f"[{login}] avatars/{login}.* не найден — сначала выберите файл", color=ft.Colors.ORANGE_800)
            return
        def _run():
            show_snackbar(f"[{login}] Загружаем аватарку...", color=ft.Colors.BLUE_800)
            err = funcs.set_steam_avatar(login, found)
            if err:
                show_snackbar(f"[{login}] Ошибка: {err}", color=ft.Colors.RED_800)
            else:
                show_snackbar(f"[{login}] Аватарка в Steam ✓", color=ft.Colors.GREEN_800)
                update_table()
                refresh_profile_view(login)
        threading.Thread(target=_run, daemon=True).start()

    # ─── JS через session_bridge.js ─────────────────────────────────────────
    import subprocess, json as _json

    BRIDGE  = os.path.join(JS_DIR, "session_bridge.js")

    # ─── Резолвер node.exe: сначала ищем portable, потом PATH ────────────────
    def _resolve_node():
        """Возвращает путь к node.exe — portable или системный."""
        portable = os.path.join(JS_DIR, "node", "node.exe")
        if os.path.exists(portable):
            return portable
        return "node"  # fallback: системный node из PATH

    NODE_EXE = _resolve_node()

    # Режим охвата: "one" = только выбранный, "all" = все авторизованные
    _cosm_scope  = ["one"]
    _info_scope  = ["one"]
    _badge_scope = ["one"]

    def _get_target_accounts(scope):
        """Возвращает список логинов для обработки."""
        if scope == "all":
            rows = baza.get_all()
            return [r["login"] for r in rows if r["cookies"]]
        else:
            login = profile_login[0]
            return [login] if login else []

    def _run_bridge_for(login, task, extra_cfg, log_col):
        """Выполняет bridge для одного аккаунта. Возвращает True при успехе."""
        import re as _re
        if not os.path.exists(BRIDGE):
            log_col.controls.append(ft.Text("❌ session_bridge.js не найден рядом с main.py", color=ft.Colors.RED_300, size=11))
            page.update()
            return False
        account, cookies_list = baza.get_acc(login)
        if not account or not cookies_list:
            log_col.controls.append(ft.Text(f"⚠ [{login}] нет куков — пропуск", color=ft.Colors.ORANGE_300, size=11))
            page.update()
            return False
        steamid32 = account.get("steamid32", 0)
        steamid64 = str(funcs.convert_id32_id64(steamid32)) if steamid32 else ""
        if not steamid64:
            log_col.controls.append(ft.Text(f"⚠ [{login}] нет steamid64 — пропуск", color=ft.Colors.ORANGE_300, size=11))
            page.update()
            return False
        args_json = _json.dumps({"login": login, "steamid64": steamid64,
                                  "cookies": cookies_list, "config": extra_cfg}, ensure_ascii=False)
        try:
            proc = subprocess.Popen(
                [NODE_EXE, BRIDGE, task, args_json],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", cwd=JS_DIR,
            )
            for raw in proc.stdout:
                ln = _re.sub(r'\x1b\[[0-9;]*m', '', raw).rstrip()
                if not ln:
                    continue
                color = (ft.Colors.GREEN_300  if "| OK " in ln else
                         ft.Colors.RED_300    if "ERROR" in ln or "FATAL" in ln else
                         ft.Colors.YELLOW_300 if "WARN" in ln or "TIMEOUT" in ln else
                         ft.Colors.CYAN_300   if "START" in ln else ft.Colors.WHITE70)
                log_col.controls.append(ft.Text(ln, color=color, size=11, selectable=True))
                if len(log_col.controls) > 500:
                    log_col.controls.pop(0)
                page.update()
            proc.wait()
            return proc.returncode == 0
        except FileNotFoundError:
            log_col.controls.append(ft.Text("❌ Node.js не найден в PATH", color=ft.Colors.RED_300, size=11))
            page.update()
            return False
        except Exception as ex:
            log_col.controls.append(ft.Text(f"❌ {ex}", color=ft.Colors.RED_300, size=11))
            page.update()
            return False

    def _run_bridge_multi(task, extra_cfg, log_col, scope):
        accounts = _get_target_accounts(scope)
        if not accounts:
            log_col.controls.append(ft.Text(
                "❌ Нет аккаунта — выберите аккаунт или переключитесь на режим «Все»" if scope == "one"
                else "❌ Нет авторизованных аккаунтов", color=ft.Colors.RED_300, size=11))
            page.update()
            return
        total = len(accounts)
        log_col.controls.append(ft.Text(
            f"▶ Запуск [{task}] — {total} аккаунт(ов)...", color=ft.Colors.CYAN_300, size=11))
        page.update()
        ok_cnt = 0
        for i, login in enumerate(accounts, 1):
            log_col.controls.append(ft.Text(
                f"── [{i}/{total}] {login}", color=ft.Colors.WHITE54, size=11))
            page.update()
            if _run_bridge_for(login, task, extra_cfg, log_col):
                ok_cnt += 1
        log_col.controls.append(ft.Text(
            f"✅ Готово: {ok_cnt}/{total}", color=ft.Colors.TEAL_300, size=11))
        page.update()

    js_log_col = ft.Column(spacing=1, scroll=ft.ScrollMode.ADAPTIVE, expand=True)
    js_log_box  = ft.Container(
        content=js_log_col,
        bgcolor=ft.Colors.with_opacity(0.12, "#003333"),
        border_radius=6, border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300)),
        padding=6, expand=True,
    )

    # ─── Хелпер: компактная кнопка-переключатель охвата ──────────────────────
    def _make_scope_toggle(scope_ref, btn_ref_list):
        def toggle(e):
            scope_ref[0] = "all" if scope_ref[0] == "one" else "one"
            btn = btn_ref_list[0]
            is_all = scope_ref[0] == "all"
            btn.content = ft.Row([
                ft.Icon(ft.Icons.GROUP if is_all else ft.Icons.PERSON, size=13,
                        color=ft.Colors.TEAL_200 if is_all else ft.Colors.WHITE54),
                ft.Text("Все" if is_all else "Один", size=12,
                        color=ft.Colors.TEAL_200 if is_all else ft.Colors.WHITE54),
            ], spacing=3, tight=True)
            btn.style = ft.ButtonStyle(
                color=ft.Colors.TEAL_200 if is_all else ft.Colors.WHITE54,
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.TEAL) if is_all else ft.Colors.TRANSPARENT,
            )
            page.update()
        return toggle

    def _scope_btn(scope_ref):
        btn = ft.TextButton(
            content=ft.Row([
                ft.Icon(ft.Icons.PERSON, size=13, color=ft.Colors.WHITE54),
                ft.Text("Один", size=12, color=ft.Colors.WHITE54),
            ], spacing=3, tight=True),
            style=ft.ButtonStyle(color=ft.Colors.WHITE54, bgcolor=ft.Colors.TRANSPARENT),
            tooltip="Переключить: текущий аккаунт / все авторизованные",
        )
        ref = [btn]
        btn.on_click = _make_scope_toggle(scope_ref, ref)
        return btn

    cosm_scope_btn  = _scope_btn(_cosm_scope)
    info_scope_btn  = _scope_btn(_info_scope)
    badge_scope_btn = _scope_btn(_badge_scope)

    # ══════════════════════════════════════════════════════════════════════════
    # СЕКЦИИ: Косметика / Инфо / Значок  — компактные
    # ══════════════════════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════════════════════
    # СЕКЦИЯ: Косметика
    # ══════════════════════════════════════════════════════════════════════════
    cosm_avatar_cb  = ft.Checkbox(label="Аватар",    value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    cosm_frame_cb   = ft.Checkbox(label="Рамка",     value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    cosm_bg_cb      = ft.Checkbox(label="Фон",       value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    cosm_mini_cb    = ft.Checkbox(label="Мини-фон",  value=False, active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    cosm_theme_cb   = ft.Checkbox(label="Тема",      value=False, active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))

    # IDs предметов (0 = случайный)
    cosm_avatar_ids_f = ft.TextField(label="ID аватаров",   hint_text="0 = случайный", value="0", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="ID аватаров через запятую. 0 = случайный из библиотеки Steam")
    cosm_frame_ids_f  = ft.TextField(label="ID рамок",      hint_text="0 = случайный", value="0", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="ID рамок профиля. 0 = случайный")
    cosm_bg_ids_f     = ft.TextField(label="ID фонов",      hint_text="0 = случайный", value="0", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="ID фонов профиля. 0 = случайный")
    cosm_mini_ids_f   = ft.TextField(label="ID мини-фонов", hint_text="0 = случайный", value="0", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="ID мини-фонов (маленькое изображение под аватаркой). 0 = случайный")
    cosm_themes_f     = ft.TextField(label="Темы оформления (через запятую)", hint_text="Summer, Midnight, Steel...", value="Summer, Midnight, Steel, Cosmic, Dark Mode", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Названия тем Steam Point Shop через запятую. Будет выбрана случайная")
    cosm_threads_f    = ft.TextField(label="Потоков", value="1", text_size=11, height=34, width=65, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Параллельных потоков")
    cosm_delay_f      = ft.TextField(label="Задержка (с)", value="1", text_size=11, height=34, width=90, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Пауза между аккаунтами в секундах")

    def _parse_ids(s):
        parts = [x.strip() for x in s.split(",") if x.strip()]
        try:    return [int(p) for p in parts] if parts else [0]
        except: return [0]

    def on_run_cosmetics(e):
        themes = [t.strip() for t in cosm_themes_f.value.split(",") if t.strip()]
        cfg = {
            "threads":      int(cosm_threads_f.value or 1),
            "accountDelay": int(cosm_delay_f.value or 1),
            "enabled": {
                "avatar":         cosm_avatar_cb.value,
                "frame":          cosm_frame_cb.value,
                "background":     cosm_bg_cb.value,
                "miniBackground": cosm_mini_cb.value,
                "theme":          cosm_theme_cb.value,
            },
            "items": {
                "avatar":         {"ids": _parse_ids(cosm_avatar_ids_f.value)},
                "frame":          {"ids": _parse_ids(cosm_frame_ids_f.value)},
                "background":     {"ids": _parse_ids(cosm_bg_ids_f.value)},
                "miniBackground": {"ids": _parse_ids(cosm_mini_ids_f.value)},
                "theme":          {"list": themes},
            },
        }
        js_log_col.controls.clear()
        threading.Thread(target=_run_bridge_multi,
                         args=("cosmetics", cfg, js_log_col, _cosm_scope[0]), daemon=True).start()

    cosm_ids_row = ft.Row([cosm_avatar_ids_f, cosm_frame_ids_f, cosm_bg_ids_f, cosm_mini_ids_f], spacing=6)
    cosm_section = ft.Container(
        content=ft.Column([
            # ── Заголовок + кнопка запуска ────────────────────────────────────
            ft.Row([
                ft.Icon(ft.Icons.AUTO_AWESOME, color=ft.Colors.AMBER_300, size=15),
                ft.Text("Косметика", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_200),
                ft.Container(expand=True),
                cosm_scope_btn,
                ft.Button(
                    "▶  Запустить",
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor={"": ft.Colors.with_opacity(0.28, ft.Colors.AMBER_700)},
                        color={"": ft.Colors.AMBER_200},
                        side={"": ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.AMBER_400))},
                        shape={"": ft.RoundedRectangleBorder(radius=8)},
                    ),
                    on_click=on_run_cosmetics,
                ),
            ], spacing=8),
            # ── Чекбоксы что применять ───────────────────────────────────────
            ft.Row([cosm_avatar_cb, cosm_frame_cb, cosm_bg_cb, cosm_mini_cb, cosm_theme_cb], spacing=4, wrap=True),
            # ── Потоки + задержка ────────────────────────────────────────────
            ft.Row([
                ft.Text("Потоков:", size=11, color=ft.Colors.WHITE54),
                cosm_threads_f,
                ft.Container(width=12),
                ft.Text("Задержка (с):", size=11, color=ft.Colors.WHITE54),
                cosm_delay_f,
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            # ── ID предметов ──────────────────────────────────────────────────
            cosm_ids_row,
            cosm_themes_f,
        ], spacing=6),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.AMBER),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.AMBER_400)),
        border_radius=10, padding=12,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # СЕКЦИЯ: Инфо профиля
    # ══════════════════════════════════════════════════════════════════════════
    info_nick_cb    = ft.Checkbox(label="Никнейм",     value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    info_real_cb    = ft.Checkbox(label="Реальное имя",value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    info_country_cb = ft.Checkbox(label="Страна",      value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    info_url_cb     = ft.Checkbox(label="Custom URL",  value=True,  active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))

    info_realmode_dd = ft.Dropdown(
        label="Режим имени", value="same",
        options=[ft.dropdown.Option("same", "same (= никнейму)"), ft.dropdown.Option("random", "random (из файла)")],
        text_size=12, height=38, content_padding=ft.Padding.symmetric(horizontal=8, vertical=2), width=180,
    )
    info_nickfile_f    = ft.TextField(label="Файл никнеймов",  value="./resources/overwatch_nicknames.txt", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    info_namefile_f    = ft.TextField(label="Файл имён",       value="./resources/overwatch_nicknames.txt", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    info_countryfile_f = ft.TextField(label="Файл стран",      value="./resources/country_ids_converted.txt", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    info_countries_f   = ft.TextField(label="Разрешённые страны (пусто = все)",  hint_text="US, RU, DE, FR...", value="US, UA, RU, DE, FR, GB", text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))

    info_min_digits_f  = ft.TextField(label="Цифр мин",  value="1", text_size=11, height=34, width=80, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Минимум цифр в Custom URL")
    info_max_digits_f  = ft.TextField(label="Цифр макс", value="2", text_size=11, height=34, width=80, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Максимум цифр в Custom URL")
    info_min_spec_f    = ft.TextField(label="Спец мин",  value="0", text_size=11, height=34, width=80, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Минимум спецсимволов в Custom URL")
    info_max_spec_f    = ft.TextField(label="Спец макс", value="1", text_size=11, height=34, width=80, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Максимум спецсимволов в Custom URL")
    info_specials_f    = ft.TextField(label="Спецсимволы", value="_, -", text_size=11, height=34, width=120, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Допустимые спецсимволы для Custom URL (через запятую)")
    info_delay_f       = ft.TextField(label="Задержка (с)", value="5", text_size=11, height=34, width=90, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Пауза между аккаунтами в секундах")
    info_threads_f     = ft.TextField(label="Потоков", value="1", text_size=11, height=34, width=65, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), tooltip="Кол-во параллельных потоков")

    def on_run_info(e):
        countries = [c.strip().upper() for c in info_countries_f.value.split(",") if c.strip()]
        specials  = [s.strip() for s in info_specials_f.value.split(",") if s.strip()]
        cfg = {
            "threads":      int(info_threads_f.value or 1),
            "accountDelay": int(info_delay_f.value or 5),
            "profile": {
                "nickname":     info_nick_cb.value,
                "realName":     info_real_cb.value,
                "country":      info_country_cb.value,
                "customURL":    info_url_cb.value,
                "realNameMode": info_realmode_dd.value,
                "nickNames":    info_nickfile_f.value.strip(),
                "realNames":    info_namefile_f.value.strip(),
                "countries":    info_countryfile_f.value.strip(),
                "allowedCountries": countries,
                "customURLSettings": {
                    "minDigits":      int(info_min_digits_f.value or 1),
                    "maxDigits":      int(info_max_digits_f.value or 2),
                    "minSpecials":    int(info_min_spec_f.value or 0),
                    "maxSpecials":    int(info_max_spec_f.value or 1),
                    "allowedSpecials": specials,
                },
            },
        }
        js_log_col.controls.clear()
        threading.Thread(target=_run_bridge_multi,
                         args=("info", cfg, js_log_col, _info_scope[0]), daemon=True).start()

    info_section = ft.Container(
        content=ft.Column([
            # ── Заголовок + кнопка ────────────────────────────────────────────
            ft.Row([
                ft.Icon(ft.Icons.PERSON_ROUNDED, color=ft.Colors.CYAN_300, size=15),
                ft.Text("Инфо профиля", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_200),
                ft.Container(expand=True),
                info_scope_btn,
                ft.Button(
                    "▶  Запустить",
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor={"": ft.Colors.with_opacity(0.28, ft.Colors.CYAN_700)},
                        color={"": ft.Colors.CYAN_200},
                        side={"": ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.CYAN_400))},
                        shape={"": ft.RoundedRectangleBorder(radius=8)},
                    ),
                    on_click=on_run_info,
                ),
            ], spacing=8),
            # ── Что менять ────────────────────────────────────────────────────
            ft.Row([info_nick_cb, info_real_cb, info_country_cb, info_url_cb], spacing=4, wrap=True),
            # ── Режим имени + потоки + задержка ──────────────────────────────
            ft.Row([
                info_realmode_dd,
                ft.Container(expand=True),
                ft.Text("Потоков:", size=11, color=ft.Colors.WHITE54),
                info_threads_f,
                ft.Text("Задержка (с):", size=11, color=ft.Colors.WHITE54),
                info_delay_f,
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            # ── Файлы источников ─────────────────────────────────────────────
            ft.Row([info_nickfile_f, info_namefile_f], spacing=6),
            ft.Row([info_countryfile_f, info_countries_f], spacing=6),
            # ── Custom URL настройки ──────────────────────────────────────────
            ft.Container(
                content=ft.Column([
                    ft.Text("Генерация Custom URL", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE60),
                    ft.Row([info_min_digits_f, info_max_digits_f, info_min_spec_f, info_max_spec_f, info_specials_f], spacing=6),
                ], spacing=4),
                bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                border_radius=6,
                padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            ),
        ], spacing=6),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.CYAN),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.CYAN_400)),
        border_radius=10, padding=12,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # СЕКЦИЯ: Значок
    # ══════════════════════════════════════════════════════════════════════════
    badge_random_cb  = ft.Checkbox(label="Случайный значок", value=True, active_color=ft.Colors.TEAL_300, label_style=ft.TextStyle(size=12))
    badge_ids_f      = ft.TextField(label="ID значков (если не случайный)", hint_text="1, 13, 45",
                                    text_size=11, height=34, expand=True, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    badge_threads_f  = ft.TextField(label="Потоков", value="1", text_size=11, height=34, width=65, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    badge_delay_f    = ft.TextField(label="Задержка (с)", value="2", text_size=11, height=34, width=90, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))

    def on_run_badge(e):
        ids = []
        if not badge_random_cb.value and badge_ids_f.value.strip():
            try: ids = [int(x.strip()) for x in badge_ids_f.value.split(",") if x.strip()]
            except: pass
        cfg = {
            "threads":      int(badge_threads_f.value or 1),
            "accountDelay": int(badge_delay_f.value or 2),
            "badge": {"random": badge_random_cb.value, "ids": ids},
        }
        js_log_col.controls.clear()
        threading.Thread(target=_run_bridge_multi,
                         args=("badge", cfg, js_log_col, _badge_scope[0]), daemon=True).start()

    badge_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.MILITARY_TECH_ROUNDED, color=ft.Colors.PURPLE_300, size=15),
                ft.Text("Значок профиля", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_200),
                ft.Container(expand=True),
                badge_scope_btn,
                ft.Button(
                    "▶  Запустить",
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor={"": ft.Colors.with_opacity(0.28, ft.Colors.PURPLE_700)},
                        color={"": ft.Colors.PURPLE_200},
                        side={"": ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.PURPLE_400))},
                        shape={"": ft.RoundedRectangleBorder(radius=8)},
                    ),
                    on_click=on_run_badge,
                ),
            ], spacing=8),
            ft.Row([badge_random_cb, badge_ids_f], spacing=8),
            ft.Row([
                ft.Text("Потоков:", size=11, color=ft.Colors.WHITE54),
                badge_threads_f,
                ft.Container(width=12),
                ft.Text("Задержка (с):", size=11, color=ft.Colors.WHITE54),
                badge_delay_f,
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=6),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PURPLE),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, ft.Colors.PURPLE_400)),
        border_radius=10, padding=12,
    )


    # ══════════════════════════════════════════════════════════════════════════
    # ВКЛАДКА «ОФОРМЛЕНИЕ» — компактная компоновка
    # ══════════════════════════════════════════════════════════════════════════
    profile_tab_content = ft.Column([
        # ── Шапка: аватарка + логин — компактная строка ──────────────────────
        ft.Row([
            profile_avatar_preview,
            ft.Container(width=8),
            ft.Column([
                profile_login_label,
                ft.Row([
                    ft.TextButton(
                        content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=12), ft.Text("Выбрать файл", size=11)], spacing=2, tight=True),
                        style=ft.ButtonStyle(color=ft.Colors.TEAL_200,
                                             bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.TEAL),
                                             padding=ft.Padding.symmetric(horizontal=8, vertical=3)),
                        on_click=on_profile_pick_avatar,
                        tooltip="Выбрать изображение аватарки с диска",
                    ),
                    ft.TextButton(
                        content=ft.Row([ft.Icon(ft.Icons.CLOUD_UPLOAD, size=12), ft.Text("Загрузить в Steam", size=11)], spacing=2, tight=True),
                        style=ft.ButtonStyle(color=ft.Colors.BLUE_200,
                                             bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.BLUE),
                                             padding=ft.Padding.symmetric(horizontal=8, vertical=3)),
                        on_click=on_profile_upload_avatar,
                        tooltip="Загрузить выбранную аватарку на Steam-аккаунт",
                    ),
                ], spacing=6),
            ], spacing=4, expand=True),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),

        ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),

        cosm_section,
        info_section,
        badge_section,

        ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),

        ft.Row([
            ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.WHITE38, size=13),
            ft.Text("Лог", size=11, color=ft.Colors.WHITE54),
            ft.Container(expand=True),
            ft.TextButton(
                content=ft.Text("Очистить", size=11, color=ft.Colors.WHITE38),
                on_click=lambda e: (js_log_col.controls.clear(), page.update()),
                style=ft.ButtonStyle(padding=ft.Padding.all(0)),
            ),
        ], spacing=4),
        js_log_box,

    ], spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)

    # ═══════════════════════════════════════════════════════════════════════════
    # ВКЛАДКА «Subs/Items» — запуск скрипта, редактор Sub/Item IDs, логи
    # ═══════════════════════════════════════════════════════════════════════════

    ADDIDS_DIR = JS_DIR
    ADDIDS_CONFIG = os.path.join(ADDIDS_DIR, "config.json")

    def _load_addids_config():
        try:
            if os.path.exists(ADDIDS_CONFIG):
                import json as _json2
                with open(ADDIDS_CONFIG, "r", encoding="utf-8") as f:
                    return _json2.load(f)
        except Exception:
            pass
        return {"subs": [], "items": [], "enableSubs": True, "enableItems": True}

    def _save_addids_config(cfg):
        try:
            import json as _json2
            with open(ADDIDS_CONFIG, "w", encoding="utf-8") as f:
                _json2.dump(cfg, f, indent=2, ensure_ascii=False)
            return True
        except Exception as ex:
            show_snackbar(f"Ошибка сохранения config.json: {ex}", color=ft.Colors.RED_800)
            return False

    # ── Поля редактора IDs ────────────────────────────────────────────────────
    _acfg = _load_addids_config()

    addids_subs_f = ft.TextField(
        label="Sub IDs (через запятую)",
        value=", ".join(str(x) for x in _acfg.get("subs", [])),
        text_size=11, multiline=False, expand=True,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        hint_text="222994, 232574, 59373...",
    )
    addids_items_f = ft.TextField(
        label="Item IDs (через запятую)",
        value=", ".join(str(x) for x in _acfg.get("items", [])),
        text_size=11, multiline=False, expand=True,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        hint_text="241812, 241811...",
    )
    addids_enable_subs_cb  = ft.Checkbox(label="Subs",  value=_acfg.get("enableSubs",  True),  active_color=ft.Colors.GREEN_400,  label_style=ft.TextStyle(size=12))
    addids_enable_items_cb = ft.Checkbox(label="Items", value=_acfg.get("enableItems", True), active_color=ft.Colors.BLUE_400, label_style=ft.TextStyle(size=12))
    addids_ignore_bl_cb    = ft.Checkbox(label="Ignore blacklist", value=_acfg.get("ignoreBlacklist", True), active_color=ft.Colors.ORANGE_400, label_style=ft.TextStyle(size=12))

    addids_delay_subs_f  = ft.TextField(label="Задержка Subs (мс)",  value=str(_acfg.get("delaySubs",  500)), text_size=11, height=36, width=140, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    addids_delay_items_f = ft.TextField(label="Задержка Items (мс)", value=str(_acfg.get("delayItems", 500)), text_size=11, height=36, width=140, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    addids_delay_btw_f   = ft.TextField(label="Между аккаунтами (мс)", value=str(_acfg.get("delayBetween", 1000)), text_size=11, height=36, width=160, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))
    addids_threads_f     = ft.TextField(label="Потоков/прокси", value=str(_acfg.get("threadsPerProxy", 1)), text_size=11, height=36, width=120, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2))

    addids_status_text = ft.Text("", size=11, color=ft.Colors.WHITE54)

    # ── Лог AddIDs ────────────────────────────────────────────────────────────
    addids_log_col = ft.Column(spacing=1, scroll=ft.ScrollMode.ADAPTIVE, expand=True)
    addids_log_box = ft.Container(
        content=addids_log_col,
        bgcolor=ft.Colors.with_opacity(0.12, "#003333"),
        border_radius=6, border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300)),
        padding=6, expand=True, height=260,
    )

    _addids_proc = [None]
    _addids_running = [False]

    def _addids_log(text, color=ft.Colors.WHITE70):
        import re as _re2
        text = _re2.sub(r'\x1b\[[0-9;]*m', '', text).rstrip()
        if not text:
            return
        c = (ft.Colors.GREEN_300  if "| OK"   in text or "✅" in text or "Готово" in text else
             ft.Colors.RED_300    if "ERROR"  in text or "ОШИБКА" in text or "❌" in text else
             ft.Colors.YELLOW_300 if "WARN"   in text or "уже есть" in text or "⚠" in text else
             ft.Colors.CYAN_300   if "START"  in text or "Steam Free Collector" in text or "===" in text else
             ft.Colors.WHITE70)
        addids_log_col.controls.append(ft.Text(text, color=c, size=11, selectable=True))
        if len(addids_log_col.controls) > 1000:
            addids_log_col.controls.pop(0)
        page.update()

    def _on_save_addids_config(e):
        import json as _json2
        cfg = _load_addids_config()
        try:
            cfg["subs"]  = [int(x.strip()) for x in addids_subs_f.value.split(",")  if x.strip()]
            cfg["items"] = [int(x.strip()) for x in addids_items_f.value.split(",") if x.strip()]
        except ValueError as ex:
            show_snackbar(f"Ошибка в IDs: {ex}", color=ft.Colors.RED_800)
            return
        cfg["enableSubs"]      = addids_enable_subs_cb.value
        cfg["enableItems"]     = addids_enable_items_cb.value
        cfg["ignoreBlacklist"] = addids_ignore_bl_cb.value
        cfg["delaySubs"]       = int(addids_delay_subs_f.value  or 500)
        cfg["delayItems"]      = int(addids_delay_items_f.value or 500)
        cfg["delayBetween"]    = int(addids_delay_btw_f.value   or 1000)
        cfg["threadsPerProxy"] = int(addids_threads_f.value     or 1)
        if _save_addids_config(cfg):
            show_snackbar("config.json сохранён ✓", color=ft.Colors.GREEN_800)
            addids_status_text.value = "Конфиг сохранён ✓"
            page.update()

    def _on_run_addids(e):
        if _addids_running[0]:
            show_snackbar("Subs/Items уже запущен", color=ft.Colors.ORANGE_800)
            return
        addids_node = os.path.join(ADDIDS_DIR, "subsitems.js")
        if not os.path.exists(addids_node):
            show_snackbar("subsitems.js не найден рядом с main.py", color=ft.Colors.RED_800)
            return
        _on_save_addids_config(None)
        addids_log_col.controls.clear()
        _addids_running[0] = True
        addids_run_btn.disabled = True
        addids_stop_btn.disabled = False
        addids_status_text.value = "⏳ Запущен..."
        page.update()

        def _run():
            try:
                proc = subprocess.Popen(
                    [NODE_EXE, addids_node],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", cwd=ADDIDS_DIR,
                )
                _addids_proc[0] = proc
                for line in proc.stdout:
                    _addids_log(line)
                proc.wait()
                addids_status_text.value = f"✅ Завершён (код {proc.returncode})"
            except FileNotFoundError:
                _addids_log("❌ Node.js не найден в PATH", ft.Colors.RED_300)
                addids_status_text.value = "❌ Node.js не найден"
            except Exception as ex:
                _addids_log(f"❌ {ex}", ft.Colors.RED_300)
                addids_status_text.value = f"❌ {ex}"
            finally:
                _addids_running[0] = False
                _addids_proc[0] = None
                addids_run_btn.disabled = False
                addids_stop_btn.disabled = True
                page.update()

        threading.Thread(target=_run, daemon=True).start()

    def _on_stop_addids(e):
        proc = _addids_proc[0]
        if proc:
            try:
                proc.terminate()
                _addids_log("⛔ Остановлен пользователем", ft.Colors.ORANGE_300)
                addids_status_text.value = "⛔ Остановлен"
            except Exception as ex:
                _addids_log(f"Ошибка остановки: {ex}", ft.Colors.RED_300)
        addids_stop_btn.disabled = True
        page.update()

    addids_run_btn = ft.Button(
        "▶ Запустить",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(0.22, ft.Colors.GREEN),
            color=ft.Colors.GREEN_300,
            padding=ft.Padding.symmetric(horizontal=14, vertical=0),
        ),
        on_click=_on_run_addids,
    )
    addids_stop_btn = ft.Button(
        "■ Стоп",
        icon=ft.Icons.STOP_ROUNDED,
        disabled=True,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(0.22, ft.Colors.RED),
            color=ft.Colors.RED_300,
            padding=ft.Padding.symmetric(horizontal=14, vertical=0),
        ),
        on_click=_on_stop_addids,
    )
    addids_save_btn = ft.TextButton(
        content=ft.Row([ft.Icon(ft.Icons.SAVE_ROUNDED, size=13), ft.Text("Сохранить конфиг", size=12)], spacing=3, tight=True),
        style=ft.ButtonStyle(color=ft.Colors.TEAL_200, bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.TEAL)),
        on_click=_on_save_addids_config,
    )

    # ── Счётчик sub/item IDs в полях ──────────────────────────────────────────
    addids_subs_count  = ft.Text("", size=10, color=ft.Colors.WHITE38)
    addids_items_count = ft.Text("", size=10, color=ft.Colors.WHITE38)

    def _update_ids_count(e=None):
        sc = len([x for x in addids_subs_f.value.split(",")  if x.strip()])
        ic = len([x for x in addids_items_f.value.split(",") if x.strip()])
        addids_subs_count.value  = f"{sc} шт"
        addids_items_count.value = f"{ic} шт"
        page.update()

    addids_subs_f.on_change  = _update_ids_count
    addids_items_f.on_change = _update_ids_count
    _update_ids_count()

    addids_tab_content = ft.Column([
        # ── Заголовок ──────────────────────────────────────────────────────────
        ft.Row([
            ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED, color=ft.Colors.GREEN_300, size=16),
            ft.Text("Subs / Items — Steam Free Collector", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_200),
            ft.Container(expand=True),
            addids_run_btn,
            addids_stop_btn,
        ], spacing=6),

        ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),

        # ── Sub IDs ────────────────────────────────────────────────────────────
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SUBSCRIPTIONS_ROUNDED, color=ft.Colors.GREEN_400, size=13),
                    ft.Text("Подписки (Sub IDs)", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_200),
                    ft.Container(expand=True),
                    addids_enable_subs_cb,
                    addids_subs_count,
                ], spacing=6),
                addids_subs_f,
            ], spacing=4),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.GREEN),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.GREEN)),
            border_radius=8, padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        ),

        # ── Item IDs ───────────────────────────────────────────────────────────
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.CARD_GIFTCARD_ROUNDED, color=ft.Colors.BLUE_400, size=13),
                    ft.Text("Предметы (Item IDs)", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
                    ft.Container(expand=True),
                    addids_enable_items_cb,
                    addids_items_count,
                ], spacing=6),
                addids_items_f,
            ], spacing=4),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.BLUE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.BLUE)),
            border_radius=8, padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        ),

        # ── Настройки задержек ────────────────────────────────────────────────
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.TUNE_ROUNDED, color=ft.Colors.AMBER_400, size=13),
                    ft.Text("Параметры", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_200),
                    ft.Container(expand=True),
                    addids_ignore_bl_cb,
                ], spacing=6),
                ft.Row([addids_delay_subs_f, addids_delay_items_f, addids_delay_btw_f, addids_threads_f], spacing=6),
            ], spacing=4),
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.AMBER),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.AMBER)),
            border_radius=8, padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        ),

        # ── Кнопка сохранить + статус ─────────────────────────────────────────
        ft.Row([addids_save_btn, ft.Container(expand=True), addids_status_text], spacing=6),

        ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),

        # ── Лог ───────────────────────────────────────────────────────────────
        ft.Row([
            ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.WHITE38, size=13),
            ft.Text("Лог", size=11, color=ft.Colors.WHITE54),
            ft.Container(expand=True),
            ft.TextButton(
                content=ft.Text("Очистить", size=11, color=ft.Colors.WHITE38),
                on_click=lambda e: (addids_log_col.controls.clear(), page.update()),
                style=ft.ButtonStyle(padding=ft.Padding.all(0)),
            ),
        ], spacing=4),
        addids_log_box,

    ], spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE, visible=False)

    # ─── Ручной переключатель вкладок ────────────────────────────────────────
    _active_tab = [0]  # 0 = Инвентарь, 1 = Оформление, 2 = AddIDs

    inv_tab_content = ft.Column([
        ft.Row([
            inv_login_text,
            ft.Container(expand=True),
            inv_count_text,
        ]),
        ft.Row(game_btns, spacing=4),
        ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),
        inv_grid,
        inv_status,
    ], spacing=8, expand=True, visible=True)

    profile_tab_content.visible = False

    tab_btn_inv = ft.TextButton(
        content=ft.Row([
            ft.Icon(ft.Icons.INVENTORY_2, size=14),
            ft.Text("Инвентарь", size=13),
        ], spacing=4, tight=True),
        style=ft.ButtonStyle(
            color=ft.Colors.TEAL_200,
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.TEAL),
        ),
    )
    tab_btn_profile = ft.TextButton(
        content=ft.Row([
            ft.Icon(ft.Icons.BRUSH_ROUNDED, size=14),
            ft.Text("Оформление", size=13),
        ], spacing=4, tight=True),
        style=ft.ButtonStyle(
            color=ft.Colors.WHITE38,
            bgcolor=ft.Colors.TRANSPARENT,
        ),
    )
    tab_btn_addids = ft.TextButton(
        content=ft.Row([
            ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED, size=14),
            ft.Text("Subs/Items", size=13),
        ], spacing=4, tight=True),
        style=ft.ButtonStyle(
            color=ft.Colors.WHITE38,
            bgcolor=ft.Colors.TRANSPARENT,
        ),
    )

    tab_indicator_inv     = ft.Container(height=2, bgcolor=ft.Colors.TEAL_300,    border_radius=1)
    tab_indicator_profile = ft.Container(height=2, bgcolor=ft.Colors.TRANSPARENT, border_radius=1)
    tab_indicator_addids  = ft.Container(height=2, bgcolor=ft.Colors.TRANSPARENT, border_radius=1)

    _ALL_TABS = [
        (tab_btn_inv,     tab_indicator_inv,     inv_tab_content),
        (tab_btn_profile, tab_indicator_profile, profile_tab_content),
        (tab_btn_addids,  tab_indicator_addids,  addids_tab_content),
    ]

    def switch_tab(idx):
        _active_tab[0] = idx
        for i, (btn, ind, content) in enumerate(_ALL_TABS):
            active = (i == idx)
            content.visible = active
            btn.style = ft.ButtonStyle(
                color=ft.Colors.TEAL_200 if active else ft.Colors.WHITE38,
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.TEAL) if active else ft.Colors.TRANSPARENT,
            )
            ind.bgcolor = ft.Colors.TEAL_300 if active else ft.Colors.TRANSPARENT
        page.update()

    tab_btn_inv.on_click     = lambda e: switch_tab(0)
    tab_btn_profile.on_click = lambda e: switch_tab(1)
    tab_btn_addids.on_click  = lambda e: switch_tab(2)

    tab_bar = ft.Row([
        ft.Column([tab_btn_inv,     tab_indicator_inv],     spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Column([tab_btn_profile, tab_indicator_profile], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Column([tab_btn_addids,  tab_indicator_addids],  spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(expand=True),
    ], spacing=4)

    right_panel = ft.Container(
        width=None,
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.45, "#062020"),
        border_radius=ft.BorderRadius(0, 16, 0, 16),
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300))
        ),
        padding=16,
        content=ft.Column([
            tab_bar,
            ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),
            inv_tab_content,
            profile_tab_content,
            addids_tab_content,
        ], spacing=6, expand=True),
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # ЛЕВАЯ ПАНЕЛЬ — ТАБЛИЦА АККАУНТОВ
    # ═══════════════════════════════════════════════════════════════════════════

    # ─── Удаление с подтверждением ────────────────────────────────────────────
    def confirm_delete(login):
        def do_delete(e):
            dlg.open = False
            page.update()
            baza.delete_account(login)
            refresh_counter()
            update_table()
            show_snackbar(f"[{login}] удалён", color=ft.Colors.RED_800)

        def cancel(e):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Удалить аккаунт?"),
            content=ft.Text(f"«{login}» будет удалён из базы. Это нельзя отменить."),
            actions=[
                ft.TextButton("Отмена", on_click=cancel),
                ft.TextButton("Удалить", on_click=do_delete,
                              style=ft.ButtonStyle(color=ft.Colors.RED)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # ─── Импорт ───────────────────────────────────────────────────────────────
    def on_import_click(e):
        import_btn.disabled = True
        import_btn.content = ft.Row([ft.ProgressRing(width=12, height=12, stroke_width=2),
                                      ft.Text("...", color=ft.Colors.BLUE)], tight=True, spacing=4)
        page.update()

        def _run():
            try:
                added, skipped, errors = funcs.import_accounts_verbose()
                scan_avatars_folder()
                refresh_counter()
                update_table()
                show_snackbar(f"Импорт: +{added}, пропущено {skipped}, ошибок {errors}",
                              color=ft.Colors.GREEN_800 if errors == 0 else ft.Colors.ORANGE_800)
            except Exception as ex:
                show_snackbar(f"Ошибка: {ex}", color=ft.Colors.RED_800)
            finally:
                import_btn.disabled = False
                import_btn.content = ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.BLUE, size=14),
                                              ft.Text("Импорт", color=ft.Colors.BLUE, size=13)], tight=True, spacing=4)
                page.update()

        threading.Thread(target=_run, daemon=True).start()

    # ─── Auth одного аккаунта ─────────────────────────────────────────────────
    def on_auth_click(e, login):
        show_snackbar(f"[{login}] Авторизация...", color=ft.Colors.BLUE_800)

        def _run():
            try:
                funcs.auth_account(login)
                show_snackbar(f"[{login}] Авторизован ✓", color=ft.Colors.GREEN_800)
            except Exception as ex:
                baza.add_auth_history(login, "error", str(ex))
                show_snackbar(f"[{login}] Ошибка: {ex}", color=ft.Colors.RED_800)
            finally:
                refresh_counter()
                update_table()

        threading.Thread(target=_run, daemon=True).start()

    # ─── Auth всех ────────────────────────────────────────────────────────────
    def on_auth_all_click(e):
        auth_all_btn.disabled = True
        page.update()

        def _run():
            rows = baza.get_all()
            ok, fail = 0, 0
            for row in rows:
                try:
                    funcs.auth_account(row['login'])
                    ok += 1
                except Exception as ex:
                    baza.add_auth_history(row['login'], "error", str(ex))
                    fail += 1
            show_snackbar(f"Auth: {ok} ок, {fail} ошибок",
                          color=ft.Colors.GREEN_800 if fail == 0 else ft.Colors.ORANGE_800)
            auth_all_btn.disabled = False
            refresh_counter()
            update_table()

        threading.Thread(target=_run, daemon=True).start()

    # ─── Массовое подтверждение трейдов ───────────────────────────────────────
    def on_confirm_all_accounts(e):
        async def _run():
            rows = baza.get_all()
            ok, fail = 0, 0
            for row in rows:
                try:
                    await funcs.confirm_all(row['login'])
                    ok += 1
                except Exception as ex:
                    fail += 1
            show_snackbar(f"Трейды: {ok} ок, {fail} ошибок",
                          color=ft.Colors.GREEN_800 if fail == 0 else ft.Colors.ORANGE_800)
        page.run_task(_run)

    # ─── История авторизаций ───────────────────────────────────────────────────
    history_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True, spacing=4)

    def open_history_panel(login=None):
        history_list.controls.clear()
        records = baza.get_auth_history(login, limit=200)
        if not records:
            history_list.controls.append(
                ft.Text("История пуста", color=ft.Colors.WHITE38, italic=True))
        else:
            for rec in records:
                ok = rec["status"] == "success"
                history_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.ERROR,
                                    color=ft.Colors.GREEN_300 if ok else ft.Colors.RED_300, size=14),
                            ft.Text(rec["auth_time"], size=11, color=ft.Colors.WHITE54, width=130),
                            ft.Text(rec["login"],     size=11, color=ft.Colors.WHITE,   width=150),
                            ft.Text(rec["note"] or "", size=11, color=ft.Colors.WHITE38, expand=True),
                        ], spacing=6),
                        padding=ft.Padding.symmetric(vertical=3, horizontal=6),
                        border_radius=4,
                        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                    )
                )
        history_bs.open = True
        page.update()

    history_bs = ft.BottomSheet(
        content=ft.Container(
            bgcolor="#1a1a2e", height=380, padding=16,
            content=ft.Column([
                ft.Row([
                    ft.Text("История авторизаций", size=15, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE, expand=True),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_color=ft.Colors.WHITE54,
                                  on_click=lambda e: (setattr(history_bs, 'open', False), page.update())),
                ]),
                ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300)),
                history_list,
            ], spacing=6, expand=True),
        ), open=False,
    )
    page.overlay.append(history_bs)

    # ─── Загрузка аватарки через tkinter ──────────────────────────────────────
    def pick_avatar(login):
        import shutil
        from tkinter import Tk, filedialog

        def _run():
            root = Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            src = filedialog.askopenfilename(
                title=f"Аватарка для {login}",
                filetypes=[("Изображения", "*.jpg *.jpeg *.png *.webp *.gif")])
            root.destroy()
            if not src:
                return
            os.makedirs(AVATARS_DIR, exist_ok=True)
            ext = os.path.splitext(src)[1].lower() or ".jpg"
            dst = os.path.join(AVATARS_DIR, f"{login}{ext}")
            try:
                shutil.copy2(src, dst)
                baza.update_avatar(login, dst)
                update_table()
                if profile_login[0] == login:
                    refresh_profile_view(login)
                show_snackbar(f"[{login}] Аватарка установлена ✓", color=ft.Colors.GREEN_800)
            except Exception as ex:
                show_snackbar(f"Ошибка: {ex}", color=ft.Colors.RED_800)

        threading.Thread(target=_run, daemon=True).start()

    # ─── Установить аватарку в Steam ──────────────────────────────────────────
    def upload_steam_avatar(login):
        import glob as _glob
        found = None
        for ext in ("jpg", "jpeg", "png", "webp", "gif"):
            candidates = _glob.glob(os.path.join(AVATARS_DIR, f"{login}.{ext}"))
            if candidates:
                found = candidates[0]
                break
        if not found:
            show_snackbar(f"[{login}] Файл avatars/{login}.jpg не найден", color=ft.Colors.ORANGE_800)
            return

        def _run():
            show_snackbar(f"[{login}] Загружаем аватарку в Steam...", color=ft.Colors.BLUE_800)
            err = funcs.set_steam_avatar(login, found)
            if err:
                show_snackbar(f"[{login}] Ошибка: {err}", color=ft.Colors.RED_800)
            else:
                show_snackbar(f"[{login}] Аватарка установлена в Steam ✓", color=ft.Colors.GREEN_800)
                update_table()

        threading.Thread(target=_run, daemon=True).start()

    # ─── Автосканирование папки avatars/ ──────────────────────────────────────
    def scan_avatars_folder():
        import glob as _glob
        if not os.path.exists(AVATARS_DIR):
            return
        rows = baza.get_all()
        logins = {row['login'].lower(): row['login'] for row in rows}
        matched = 0
        for ext in ("jpg", "jpeg", "png", "webp", "gif"):
            for fpath in _glob.glob(os.path.join(AVATARS_DIR, f"*.{ext}")):
                basename = os.path.splitext(os.path.basename(fpath))[0].lower()
                if basename in logins:
                    real_login = logins[basename]
                    acc, _ = baza.get_acc(real_login)
                    if acc and acc.get('avatar_url') != fpath:
                        baza.update_avatar(real_login, fpath)
                        matched += 1
        if matched:
            print(f"[avatars] Привязано аватарок: {matched}")

    # ─── Таблица ──────────────────────────────────────────────────────────────
    table = ft.DataTable(
        column_spacing=6,
        columns=[
            ft.DataColumn(ft.Text("#",     color=ft.Colors.WHITE54, size=12)),
            ft.DataColumn(ft.Text("",      color=ft.Colors.WHITE54)),          # Avatar
            ft.DataColumn(ft.Text("Login", color=ft.Colors.WHITE54, size=12)),
            ft.DataColumn(ft.Text("Pass",  color=ft.Colors.WHITE54, size=12)),
            ft.DataColumn(ft.Text("",      color=ft.Colors.WHITE54)),          # Actions
        ],
        rows=[],
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
        border_radius=8,
        horizontal_lines=ft.BorderSide(1, ft.Colors.with_opacity(0.04, ft.Colors.WHITE)),

    )

    def on_row_click(login):
        """Клик по строке — загружает инвентарь справа и обновляет вкладку оформления."""
        load_inventory(login, selected_appid[0])
        refresh_profile_view(login)

    def update_table(filter_text=""):
        rows = baza.find_acc(filter_text)
        table.rows.clear()
        for index, row in enumerate(rows):
            name        = row['login']
            has_cookies = bool(row['cookies'])
            avatar_url  = row['avatar_url'] if row['avatar_url'] else None

            row_color = (ft.Colors.with_opacity(0.07, ft.Colors.GREEN)
                         if has_cookies
                         else ft.Colors.with_opacity(0.07, ft.Colors.RED))

            # Аватарка
            if avatar_url and os.path.exists(avatar_url):
                avatar_inner = ft.Container(
                    content=ft.Image(src=avatar_url, width=34, height=34, border_radius=17),
                    width=34, height=34, border_radius=17,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                )
            else:
                avatar_inner = ft.Container(
                    content=ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=34,
                                    color=ft.Colors.GREEN_300 if has_cookies else ft.Colors.RED_300),
                    width=34, height=34,
                )

            avatar_widget = ft.TextButton(
                content=avatar_inner,
                tooltip="Выбрать аватарку",
                on_click=lambda e, n=name: pick_avatar(n),
                style=ft.ButtonStyle(padding=ft.Padding.all(0)),
            )

            auth_color = ft.Colors.GREEN_300 if has_cookies else ft.Colors.ORANGE_300

            table.rows.append(ft.DataRow(
                color=row_color,
                cells=[
                    ft.DataCell(ft.Text(str(index + 1), color=ft.Colors.WHITE38, size=12)),
                    ft.DataCell(avatar_widget),
                    ft.DataCell(
                        ft.TextButton(
                            content=ft.Text(name, color=ft.Colors.WHITE, size=13),
                            tooltip="Копировать логин / Клик ПКМ: показать инвентарь",
                            on_click=lambda e, n=name: (on_copy_click(e, n, funcs.copy_acc_login), on_row_click(n)),
                            style=ft.ButtonStyle(padding=ft.Padding.all(0)),
                        )
                    ),
                    ft.DataCell(
                        ft.TextButton(
                            content=ft.Text("••••••••••", color=ft.Colors.WHITE38, size=13),
                            tooltip="Копировать пароль",
                            on_click=lambda e, n=name: on_copy_click(e, n, funcs.copy_acc_pass),
                            style=ft.ButtonStyle(padding=ft.Padding.all(0)),
                        )
                    ),
                    ft.DataCell(
                        ft.Row([
                            ft.IconButton(icon=ft.Icons.OPEN_IN_BROWSER,        icon_color=ft.Colors.CYAN_300,   tooltip="Открыть инвентарь",    icon_size=18, on_click=lambda e, n=name: on_row_click(n)),
                            ft.IconButton(icon=ft.Icons.LANGUAGE,              icon_color=ft.Colors.TEAL_300,   tooltip="Браузер",              icon_size=18, on_click=lambda e, n=name: funcs.browser(e, n)),
                            ft.IconButton(icon=ft.Icons.LOCK_ROUNDED,          icon_color=ft.Colors.GREEN_300,  tooltip="Guard-код",            icon_size=18, on_click=lambda e, n=name: on_copy_click(e, n, funcs.copy_acc_guard)),
                            ft.IconButton(icon=ft.Icons.LOGIN,                 icon_color=auth_color,           tooltip="Авторизовать",         icon_size=18, on_click=lambda e, n=name: on_auth_click(e, n)),
                            ft.IconButton(icon=ft.Icons.ACCOUNT_BOX_OUTLINED,  icon_color=ft.Colors.PURPLE_200, tooltip="Аватарка в Steam",     icon_size=18, on_click=lambda e, n=name: upload_steam_avatar(n)),
                            ft.IconButton(icon=ft.Icons.CHECK_ROUNDED,         icon_color=ft.Colors.GREEN,      tooltip="Подтвердить трейды",   icon_size=18, on_click=lambda e, n=name: page.run_task(funcs.confirm_all, n)),
                            ft.IconButton(icon=ft.Icons.CLOSE_ROUNDED,         icon_color=ft.Colors.ORANGE,     tooltip="Отклонить трейды",     icon_size=18, on_click=lambda e, n=name: page.run_task(funcs.deny_all, n)),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE_ROUNDED, icon_color=ft.Colors.RED_400,   tooltip="Удалить",              icon_size=18, on_click=lambda e, n=name: confirm_delete(n)),
                        ], spacing=0, tight=True)
                    ),
                ]
            ))
        page.update()

    # ─── Верхняя панель ───────────────────────────────────────────────────────
    search_field = ft.TextField(
        label="Search by login", expand=True,
        border_color=ft.Colors.BLUE_400,
        focused_border_color=ft.Colors.BLUE,
        text_size=13, height=40,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        on_change=lambda e: update_table(e.control.value),
    )

    theme_btn = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE, icon_color=ft.Colors.YELLOW_300,
        tooltip="Переключить тему", on_click=toggle_theme,
    )

    import_btn = ft.Button(
        content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, color=ft.Colors.BLUE, size=14),
                        ft.Text("Импорт", color=ft.Colors.BLUE, size=13)], tight=True, spacing=4),
        on_click=on_import_click, tooltip="Читает accs.txt + maFiles",
    )
    auth_all_btn = ft.Button(
        content=ft.Row([ft.Icon(ft.Icons.LOGIN, color=ft.Colors.ORANGE, size=14),
                        ft.Text("Auth All", color=ft.Colors.ORANGE, size=13)], tight=True, spacing=4),
        on_click=on_auth_all_click,
    )
    confirm_all_btn = ft.Button(
        content=ft.Row([ft.Icon(ft.Icons.DONE_ALL, color=ft.Colors.GREEN, size=14),
                        ft.Text("Подтвердить всё", color=ft.Colors.GREEN, size=13)], tight=True, spacing=4),
        on_click=on_confirm_all_accounts,
    )
    history_btn = ft.Button(
        content=ft.Row([ft.Icon(ft.Icons.HISTORY, color=ft.Colors.PURPLE_200, size=14),
                        ft.Text("История", color=ft.Colors.PURPLE_200, size=13)], tight=True, spacing=4),
        on_click=lambda e: open_history_panel(),
    )

    top_bar = ft.Row([
        ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.WHITE54, size=14),
        total_text,
        ft.VerticalDivider(width=14, color=ft.Colors.WHITE24),
        ft.Icon(ft.Icons.VERIFIED_USER, color=ft.Colors.GREEN_300, size=14),
        auth_text,
        ft.Container(expand=True),
        theme_btn,
    ], alignment=ft.MainAxisAlignment.START)

    controls_row = ft.Row(
        [search_field, import_btn, auth_all_btn, confirm_all_btn, history_btn],
        spacing=6,
    )

    scrollable_table = ft.Column([table], scroll=ft.ScrollMode.ADAPTIVE, expand=True)

    left_panel = ft.Container(
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.45, "#062020"),
        border_radius=ft.BorderRadius(16, 0, 16, 0),
        border=ft.Border(
            right=ft.BorderSide(1, ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300))
        ),
        padding=16,
        content=ft.Column([
            top_bar,
            controls_row,
            ft.Divider(color=ft.Colors.with_opacity(0.15, ft.Colors.TEAL_300), height=1),
            scrollable_table,
        ], spacing=10, expand=True),
    )

    # ─── Главный layout: левая + правая ───────────────────────────────────────
    main_row = ft.Row([left_panel, right_panel], spacing=0, expand=True)

    def build_layout():
        page.controls.clear()
        if os.path.exists(BG_IMAGE):
            page.add(ft.Stack([
                ft.Image(src=BG_IMAGE, fit="cover", opacity=0.30,
                         width=page.window.width, height=page.window.height),
                ft.Container(content=main_row, expand=True,
                             margin=ft.Margin(16, 16, 16, 16)),
            ], expand=True))
        else:
            page.add(ft.Container(content=main_row, expand=True,
                                   margin=ft.Margin(16, 16, 16, 16)))
        page.update()

    # ─── Загрузочный экран (аквамариновая тема) ─────────────────────────────
    # Аквамариновая палитра
    AQ_DEEP   = "#0d2626"   # фон — глубокий тёмный океан
    AQ_MID    = "#0a3d3d"   # средний
    AQ_BRIGHT = "#00b4b4"   # яркий аквамарин
    AQ_LIGHT  = "#7fffd4"   # светлый (aquamarine)
    AQ_GLOW   = "#00ffcc"   # неоновый акцент

    splash_progress = ft.ProgressBar(
        width=420,
        color=AQ_BRIGHT,
        bgcolor=ft.Colors.with_opacity(0.10, AQ_MID),
        bar_height=5,
        value=0,
    )
    splash_pct = ft.Text("0%", color=AQ_LIGHT, size=12,
                          style=ft.TextStyle(letter_spacing=1))
    splash_status = ft.Text(
        "Инициализация...",
        color=ft.Colors.with_opacity(0.55, AQ_LIGHT),
        size=12, italic=True,
    )

    # Логотип — три кольца + иконка, с анимацией opacity
    logo_outer = ft.Container(
        width=160, height=160,
        border_radius=80,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.20, AQ_BRIGHT)),
        animate_opacity=ft.Animation(900, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
    )
    logo_mid = ft.Container(
        width=122, height=122,
        border_radius=61,
        bgcolor=ft.Colors.with_opacity(0.07, AQ_BRIGHT),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.30, AQ_BRIGHT)),
        margin=ft.Margin(19, 19, 19, 19),
        animate_opacity=ft.Animation(900, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
    )
    logo_inner = ft.Container(
        width=88, height=88,
        border_radius=44,
        bgcolor=ft.Colors.with_opacity(0.18, AQ_BRIGHT),
        margin=ft.Margin(36, 36, 36, 36),
        animate_opacity=ft.Animation(900, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
    )
    logo_icon_col = ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.MANAGE_ACCOUNTS_ROUNDED, size=66, color=AQ_LIGHT)
        ], alignment=ft.MainAxisAlignment.CENTER)
    ], alignment=ft.MainAxisAlignment.CENTER, expand=True,
       animate_opacity=ft.Animation(700, ft.AnimationCurve.EASE_IN_OUT),
       opacity=0,
    )

    logo = ft.Container(
        width=160, height=160,
        animate_opacity=ft.Animation(600, ft.AnimationCurve.EASE_IN),
        opacity=0,
        content=ft.Stack([logo_outer, logo_mid, logo_inner, logo_icon_col]),
    )

    splash_title = ft.Text(
        "SHARK",
        size=70,
        weight=ft.FontWeight.W_900,
        color=AQ_LIGHT,
        style=ft.TextStyle(letter_spacing=18),
        animate_opacity=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0,
    )
    splash_subtitle_row = ft.Row([
        ft.Container(width=70, height=1,
                     bgcolor=ft.Colors.with_opacity(0.30, AQ_BRIGHT)),
        ft.Text(
            "ACCOUNT  SYSTEM",
            size=11,
            color=AQ_BRIGHT,
            weight=ft.FontWeight.W_600,
            style=ft.TextStyle(letter_spacing=7),
        ),
        ft.Container(width=70, height=1,
                     bgcolor=ft.Colors.with_opacity(0.30, AQ_BRIGHT)),
    ], alignment=ft.MainAxisAlignment.CENTER, spacing=16,
       animate_opacity=ft.Animation(800, ft.AnimationCurve.EASE_IN_OUT),
       opacity=0,
    )

    splash = ft.Container(
        expand=True,
        bgcolor=AQ_DEEP,
        content=ft.Column([
            ft.Container(height=20),

            logo,

            ft.Container(height=30),

            # ── SHARK ────────────────────────────────────────────────────────
            splash_title,

            ft.Container(height=6),

            # ── ACCOUNT SYSTEM ───────────────────────────────────────────────
            splash_subtitle_row,

            ft.Container(height=16),

            # ── Декоративная полоса ──────────────────────────────────────────
            ft.Container(
                width=260, height=1,
                bgcolor=ft.Colors.with_opacity(0.12, AQ_GLOW),
            ),

            ft.Container(height=44),

            # ── Прогресс ─────────────────────────────────────────────────────
            ft.Container(
                width=420,
                content=ft.Column([
                    ft.Row([
                        ft.Container(expand=True),
                        splash_pct,
                    ], width=420),
                    ft.Container(height=4),
                    splash_progress,
                ], spacing=0),
            ),

            ft.Container(height=14),
            splash_status,

            ft.Container(height=40),

            # ── Версия ───────────────────────────────────────────────────────
            ft.Row([
                ft.Container(width=24, height=1,
                             bgcolor=ft.Colors.with_opacity(0.15, AQ_BRIGHT)),
                ft.Text(
                    "v2.0  ·  Steam Account Tool",
                    size=10,
                    color=ft.Colors.with_opacity(0.25, AQ_LIGHT),
                    style=ft.TextStyle(letter_spacing=2),
                ),
                ft.Container(width=24, height=1,
                             bgcolor=ft.Colors.with_opacity(0.15, AQ_BRIGHT)),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),

            ft.Container(height=20),

        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           alignment=ft.MainAxisAlignment.CENTER,
           spacing=0, expand=True),
    )

    page.add(splash)
    page.update()

    def _load():
        import time

        # ── Фаза 1: Плавное появление логотипа ──────────────────────────────
        # Кольца появляются последовательно
        logo.opacity = 1.0
        page.update()
        time.sleep(0.05)

        logo_outer.opacity = 1.0
        page.update()
        time.sleep(0.18)

        logo_mid.opacity = 1.0
        page.update()
        time.sleep(0.18)

        logo_inner.opacity = 1.0
        page.update()
        time.sleep(0.18)

        logo_icon_col.opacity = 1.0
        page.update()
        time.sleep(0.25)

        # Заголовок SHARK
        splash_title.opacity = 1.0
        page.update()
        time.sleep(0.20)

        # Подзаголовок ACCOUNT SYSTEM
        splash_subtitle_row.opacity = 1.0
        page.update()
        time.sleep(0.40)

        # ── Фаза 2: Плавный прогресс-бар ────────────────────────────────────
        steps = [
            (0.15, "Подключение к базе данных..."),
            (0.35, "Загрузка аккаунтов..."),
            (0.60, "Сканирование аватарок..."),
            (0.80, "Инициализация интерфейса..."),
            (0.95, "Финальная настройка..."),
        ]

        current = 0.0
        for target, status in steps:
            splash_status.value = status
            # Плавно нарастаем от current до target мелкими шагами
            steps_count = max(1, int((target - current) * 60))
            for i in range(steps_count):
                val = current + (target - current) * (i + 1) / steps_count
                splash_progress.value = val
                splash_pct.value = f"{int(val * 100)}%"
                page.update()
                time.sleep(0.012)
            current = target

        build_layout()
        refresh_counter()
        scan_avatars_folder()
        update_table()

        # Финальный плавный добег до 100%
        for i in range(20):
            val = current + (1.0 - current) * (i + 1) / 20
            splash_progress.value = val
            splash_pct.value = f"{int(val * 100)}%"
            page.update()
            time.sleep(0.018)

        splash_status.value = "Система готова ✓"
        splash_pct.value = "100%"
        splash_progress.value = 1.0
        page.update()
        time.sleep(0.4)

    threading.Thread(target=_load, daemon=True).start()


ft.run(main)
