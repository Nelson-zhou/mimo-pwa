# Xiaomi MiMo PWA 📱

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-0%20(Pure%20Python)-success.svg)](#)
[![PWA Ready](https://img.shields.io/badge/PWA-Standalone%20App-5A0FC8.svg?logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Network-Tailscale%20%2F%20LAN-black.svg?logo=tailscale&logoColor=white)](https://tailscale.com/)

> **Lightweight mobile PWA gateway for Xiaomi MiMo Desktop.**  
> Operate the MiMo agent on your computer from your phone — assign tasks, inspect artifacts, switch models, and monitor quota. Single-file pure Python, zero third-party dependencies.

[中文文档 (Chinese Documentation)](./README.md)

---

## 🛠️ The Problem We Solve

Xiaomi MiMo officially ships only a desktop client. Once you leave your machine, you cannot track agent progress or dispatch urgent work.

This project reverse-engineers the client's local runtime surface and exposes a **non-invasive local gateway** that enables:
1. **Full mobile control** — send requirements, browse code/file artifacts, dispatch long-running tasks.
2. **Hands-free remote execution** — tool calls and shell commands run silently on the desktop without clicking approval dialogs.
3. **True desktop state sync** — the phone inherits the currently focused session and working directory in real time.
4. **Native app experience** — installable standalone PWA, voice input, image upload.
5. **Full model matrix** — dynamic catalog aggregation, mobile bottom-sheet picker, alias normalization, preference write-back.

---

## 🏗️ Architecture: 6 Desktop Integration Points

No binary patching. The gateway transparently proxies six local data sources:

```
┌────────────────────────────────────────────────────────┐
│               Mobile PWA (iOS Safari / Android Chrome) │
│     (Tailscale HTTPS / LAN Wi-Fi direct access)        │
└───────────────────────────┬────────────────────────────┘
                            │  SSE stream / REST API
                            ▼
┌────────────────────────────────────────────────────────┐
│             mimo-pwa gateway (server.py)               │
│        (listens on 0.0.0.0:8080, pure Python)          │
└───────────┬───────────────────────────────┬────────────┘
            │                               │
            ▼ Desktop API                   ▼ Local state read/write
┌───────────────────────────┐   ┌────────────────────────────────┐
│  Xiaomi MiMo Desktop core │   │   Local configs & databases    │
│  (port in desktop-api.json)│   │                                │
│                           │   │ 1. desktop-api.json (creds)    │
│ • POST /v1/sessions/turns │   │ 2. mimocode.db (SQLite)        │
│ • GET  /v1/sessions/events│   │ 3. composer-input.json (focus) │
│ • POST /v1/sessions/abort │   │ 4. preferences.json (models)   │
│ • GET  /v1/tools          │   │ 5. Electron LevelDB (avatar)   │
│                           │   │ 6. Cookies.db (SSO quota)      │
└───────────────────────────┘   └────────────────────────────────┘
```

| Integration point | Local path / protocol | Purpose |
| :--- | :--- | :--- |
| **1. Dynamic credentials** | macOS: `~/Library/Application Support/Xiaomi MiMo/desktop-api.json`<br>Linux: `~/.config/XiaomiMiMoDesktop/desktop-api.json` | Auto-extract random port + Bearer token for password-less reverse proxy. |
| **2. Session store** | `~/.local/share/mimocode/mimocode.db` | Create sessions in SQLite, inherit cwd, auto-rename from first message. |
| **3. Desktop focus** | `composer-input.json` | Track the active desktop session; phone opens on the same task. |
| **4. Model write-back** | `preferences.json` | Mobile model switch persists globally and per session. |
| **5. Real avatar** | `Local Storage/leveldb` | Parse `mimo.set.avatar` and show the signed-in user avatar. |
| **6. Weekly quota** | `Partitions/xiaomi-account/Cookies` | Extract Xiaomi SSO `passToken`, query remaining quota & reset countdown. |

---

## ⚡ Core Capabilities

### 1. Native 1M Context & Live Token HUD
- **1,000,000-token context** aligned with MiMo's internal `limit.context = 1e6`.
- Ring HUD shows total tokens used, remaining %, and prompt-cache hit rate.

### 2. Dynamic Multi-Source Model Engine
Models are **not hard-coded**. The catalog is assembled at runtime from:

| Source | Role |
| :--- | :--- |
| `model-catalog.json` | Official quota, cost multipliers, context windows |
| `models.dev` cache / extended config | Claude, DeepSeek, other extended models |
| `preferences.json` + session DB | Defaults, recents, per-session model |

**Canonical ID mapping** normalizes historical aliases:

| Alias / legacy | Canonical ID |
| :--- | :--- |
| `mimo-pro` / `mimo-x-pro-preview` | `mimo-v2.6-pro` |
| `mimo-flash` / `mimo-x-flash-preview` | `mimo-v2.6-flash` |
| `mimo-auto` | `mimo-auto` |

**Mobile bottom-sheet selector** supports category filters, capability badges, context size and cost multiplier. Selections write back to desktop preferences and session maps.

Typical catalog (live, may grow):
- **MiMo Auto** — free adaptive router
- **MiMo-V2.6-Pro / UltraSpeed / Flash** — current flagship line
- **MiMo-V2.5 / V2.5-Pro / UltraSpeed** — previous flagship
- **MiMo-V2-Pro / V2-Flash / V2-Omni** — multimodal & lite
- **Claude Sonnet 4.5 / 4.6, DeepSeek V4 Pro** — extended compute

### 3. Dual-Channel Streaming (SSE + Polling Watchdog)
- Millisecond SSE typewriter stream via `/v1/sessions/{id}/events` with Thinking + tool cards.
- 1.5s polling watchdog recovers missed fragments after mobile backgrounding / lock screen.
- Persistent "working" motion, elapsed timer, and live badges so running tasks never look stuck.

### 4. Remote Execution Without Prompt Walls
Mobile turns default to `perm: "完全访问权限"` so shell and tools execute without desktop-side approval clicks.

### 5. Artifacts / Plugins / Quota Panel
- Auto-classified artifact browser (code, docs, images) with preview and download.
- Toggle Desktop-installed skills/plugins (arxiv, deep-research, …).
- Weekly remaining compute % and reset countdown.

### 6. Zero External Dependencies
Single-file stdlib Python (`http.server`, `sqlite3`, `urllib`, `zlib`, …). Optional local vendor JS (`marked`, `prism`) keeps Markdown offline-capable. No `pip install` required.

---

## 🚀 Quick Start

### 1. Start the gateway
Keep **Xiaomi MiMo Desktop** running, then:

```bash
git clone https://github.com/Nelson-zhou/mimo-pwa.git
cd mimo-pwa

# A) Quick start (auto-increments port if occupied)
./start.sh

# B) Systemd user service (recommended on Linux)
./install-service.sh
PORT=8081 ./install-service.sh   # optional custom port

# C) Direct launch (default 0.0.0.0:8080)
python3 server.py
```

If 8080 is taken (e.g. by qBittorrent), the gateway picks the next free port, or set one:

```bash
PORT=8081 ./start.sh
python3 server.py --port 8081
```

#### Systemd management
- Status: `systemctl --user status mimo-pwa`
- Logs: `journalctl --user -u mimo-pwa -f`
- Restart: `systemctl --user restart mimo-pwa`
- Stop: `systemctl --user stop mimo-pwa`
- Uninstall: `./uninstall-service.sh`

### 2. Remote network access

#### Option A: Tailscale HTTPS (recommended)
```bash
# Map once; replace 8080 with your actual gateway port
tailscale serve --https=8443 --bg 8080
```
The gateway only surfaces an install link when `tailscale serve` forwards HTTPS to the live gateway port.

#### Option B: LAN Wi-Fi
Open the LAN IP printed in the terminal (e.g. `http://192.168.x.x:8080`) on your phone.

### 3. Install to home screen
- **iOS Safari**: Share → **Add to Home Screen**
- **Android Chrome**: Menu → **Install app** / **Add to Home screen**

---

## 🧪 Tests & Regression Guards

```bash
# 1) Model mapping / session-model unit tests
python3 -m unittest tests.test_model_mapping -v

# 2) Embedded PWA JS syntax & safety guards (includes node --check)
python3 -m unittest tests.test_pwa_syntax -v

# 3) Live E2E (gateway must be running; includes headless Chrome render)
python3 -m unittest tests.test_pwa_live_e2e -v

# Everything
python3 -m unittest discover -s tests -v
```

| Suite | Covers |
| :--- | :--- |
| `tests/test_model_mapping.py` | Canonical ID normalization, extended models, context limits, session model resolution |
| `tests/test_pwa_syntax.py` | Inline JS syntax, async `initApp`, global error boundary, safetyTimer anti-stall |
| `tests/test_pwa_live_e2e.py` | HTTP root reachability, clean script evaluation, headless Chrome render |

---

## ⚙️ CLI Flags

```text
Usage: python3 server.py [options]

  --port PORT     Listen port (default: 8080; auto-increments if busy)
  --host HOST     Bind address (default: 0.0.0.0)
  --workdir DIR   Default working directory for new sessions (default: ~)
```

---

## 🛡️ Security & Privacy Guardrails

See [**SECURITY_GUARD.md**](./SECURITY_GUARD.md) for the full policy (UID, cookies, Tailnet hostnames, local paths, etc.).

```bash
# Install pre-commit interceptor
./scripts/install-hooks.sh

# Manual compliance scan (run before every commit)
./scripts/security-check.sh
```

---

## 📄 License

Released under the [MIT License](./LICENSE).
