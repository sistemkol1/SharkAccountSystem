# 🦈 SharkAccountSystem

> Steam account management tool with GUI — mass authorization, cosmetics, profile info, badges, free licenses and items collector.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Node.js](https://img.shields.io/badge/Node.js-18+-green?logo=node.js)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![Version](https://img.shields.io/badge/Version-2.0-teal)

---

## Features

- **Account Manager** — import accounts from `accs.txt` + maFiles, mass authorization via Playwright
- **Inventory Viewer** — browse CS2, TF2, Dota 2, Rust, GTA V inventories with rarity colors
- **Cosmetics** — set animated avatar, frame, background, mini-background, theme (single or all accounts)
- **Profile Info** — randomize nickname, real name, country, custom URL
- **Badge** — set favorite badge (random or by ID)
- **Subs / Items** — free licenses and items collector with blacklist support
- **Avatar Upload** — upload custom avatar images directly to Steam
- **Trade Manager** — confirm or deny all pending trades
- **Auth History** — log of all authorization attempts

---

## Requirements

- Windows 10/11
- [Node.js 18+](https://nodejs.org/)
- Python 3.10+

---

## Installation

### Option 1 — Installer (recommended)

Download `SharkAccountSystem_v2.0_Setup.exe` from [Releases](../../releases/latest) and run it.

### Option 2 — From source

```bash
git clone https://github.com/sistemkol1/SharkAccountSystem.git
cd SharkAccountSystem

pip install -r requirements.txt
playwright install chromium

npm install
```

Run:
```bash
python main.py
```

---

## Setup

1. Copy `accs.example.txt` → `accs.txt` and fill in your accounts:
   ```
   login:password
   login2:password2:shared_secret
   ```

2. Copy `config.example.json` → `config.json` and configure Sub/Item IDs

3. Place maFiles in `%APPDATA%\SharkAccountSystem\mafs\`

4. Place avatar images in `%APPDATA%\SharkAccountSystem\avatars\` (filename = login)

---

## Project Structure

```
SharkAccountSystem/
├── main.py                  # GUI (Flet)
├── funcs.py                 # Steam auth, avatar upload
├── dbase.py                 # SQLite database
├── session_bridge.js        # Node.js bridge: cosmetics / info / badge
├── subsitems.js             # Free licenses & items collector
├── resources/
│   ├── overwatch_nicknames.txt
│   └── country_ids_converted.txt
├── accs.example.txt
└── config.example.json
```

---

## License

MIT
