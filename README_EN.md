# Xiaomi MiMo PWA 📱

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-0%20(Pure%20Python)-success.svg)](#)
[![PWA Ready](https://img.shields.io/badge/PWA-Standalone%20App-5A0FC8.svg?logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Network-Tailscale%20%2F%20LAN-black.svg?logo=tailscale&logoColor=white)](https://tailscale.com/)

> **Lightweight Mobile PWA Gateway for Xiaomi MiMo Desktop**.  
> Solves the mobile accessibility limitation of the official desktop AI agent. Control your MiMo tasks remotely from your phone (iOS / Android) with zero external dependencies in pure Python.

[中文文档 (Chinese Documentation)](./README.md)

---

## 🛠️ Problems Solved

Xiaomi MiMo only provides a desktop client (macOS). Once developers leave their workstation, they cannot check task progress or dispatch urgent tasks.

By reverse-engineering the desktop application's internal runtime mechanics, this gateway provides an uninvasive local bridge that enables:
1. **Full Mobile Control**: Assign tasks, inspect code changes, and review live agent outputs from any smartphone.
2. **Autonomous Execution Without Pop-ups**: Automatically authorizes execution permissions, allowing CLI tools and terminal scripts to run autonomously without requiring desktop confirmation.
3. **Bidirectional State Sync**: Automatically inherits active session focus, working directory, and conversation history directly from your Mac.
4. **Standalone App Experience**: Installs as an address-bar-free native PWA with speech-to-text dictation and image attachment uploads.

---

## 🏗️ Technical Architecture: 6 Local Integration Touchpoints

The gateway does not patch binaries. Instead, it hooks into 6 key local runtime artifacts maintained by the desktop app:

```
┌────────────────────────────────────────────────────────┐
│             Mobile PWA (iOS Safari / Android Chrome)   │
│    (Tailscale HTTPS / Local Wi-Fi Network)             │
└───────────────────────────┬────────────────────────────┘
                            │  SSE Stream / REST API
                            ▼
┌────────────────────────────────────────────────────────┐
│             mimo-pwa Gateway (server.py)               │
│         (Listening 0.0.0.0:8080, Pure Python Standard) │
└───────────┬───────────────────────────────┬────────────┘
            │                               │
            ▼ Local API Calls               ▼ Direct File & DB Read/Write
┌───────────────────────────┐   ┌────────────────────────────────┐
│  Xiaomi MiMo Desktop Core │   │     Local Runtime Storage      │
│  (Internal dynamic port)  │   │                                │
│                           │   │ 1. desktop-api.json (Port/Auth)│
│ • POST /v1/sessions/turns │   │ 2. mimocode.db (SQLite)        │
│ • GET  /v1/sessions/events│   │ 3. composer-input.json (Focus) │
│ • POST /v1/sessions/abort │   │ 4. preferences.json (Models)   │
│ • GET  /v1/tools          │   │ 5. Electron LevelDB (Settings) │
│                           │   │ 6. Cookies.db (SSO Quota API)  │
└───────────────────────────┘   └────────────────────────────────┘
```

| Integration Touchpoint | Local Path / Protocol | Mechanism & Practical Utility |
| :--- | :--- | :--- |
| **1. Dynamic Credentials** | macOS: `~/Library/Application Support/Xiaomi MiMo/desktop-api.json`<br>Linux: `~/.config/XiaomiMiMoDesktop/desktop-api.json` | The desktop core starts on an ephemeral port. The gateway extracts the dynamic `port` and Bearer `token` automatically. |
| **2. Session & History DB**| `~/.local/share/mimocode/mimocode.db` (SQLite) | Direct SQLite integration: auto-inherits the workspace directory (`~`) and titles sessions based on first prompt. |
| **3. Active Focus Linkage**| `composer-input.json` under the data dir above | Reads user's active session on desktop (`activeSessionId`), automatically opening the current desktop task on mobile. |
| **4. Model Persistence**   | `preferences.json` under the data dir above | Directly updates persistent configuration when toggling models from mobile. |
| **5. Desktop Avatar Sync** | `Local Storage/leveldb` under the data dir above | Decodes `mimo.set.avatar` from LevelDB to render custom user avatars in the mobile drawer. |
| **6. Weekly Quota Tracking**| `Partitions/xiaomi-account/Cookies` under the data dir above | Reads Xiaomi SSO `passToken` to query remaining weekly quota percentage and reset schedules. |

> On startup the gateway auto-detects the data directory by preferring the path that contains `desktop-api.json`, so both macOS and Linux layouts work out of the box.

---

## ⚡ Core Engineering Capabilities

### 1. 1,000,000 Token Native Context & Live Token HUD
- **1M Context Limit**: Decoded from client's internal configuration (`limit: { context: 1e6 }`). Full 1M token support for proprietary MiMo models.
- **Dynamic Circular Progress HUD**: Header HUD displays token count, remaining percentage, and Prompt Cache Hit Rate in real time.

### 2. Full Official Model Matrix
| Model ID | Backend Identifier | Compute Multiplier | Recommended Use Case |
| :--- | :--- | :---: | :--- |
| **MiMo Auto** | `mimo-auto` | 1.0x | Default intelligent routing according to task complexity |
| **MiMo-X-Pro-Preview** | `mimo-x-pro-preview` | 1.0x | Flagship reasoning for system architecture and large-scale refactors |
| **MiMo-X-Flash-Preview**| `mimo-x-flash-preview` | 0.4x | Lightweight, low-latency interactions and quick edits |

### 3. Dual-Channel High Availability (SSE + Polling Watchdog)
- **Millisecond Typewriter Streaming**: Direct pass-through of `/v1/sessions/{id}/events` SSE stream with structured tool invocation cards (Bash, Edit, Grep, Read).
- **Mobile Sleep & Lock Protection**: Integrated 1.5s polling fallback prevents hung connections or dropped messages when switching apps.

### 4. Autonomous Execution Authorization
- Tasks sent from mobile default to `perm: "完全访问权限"`, allowing CLI execution without requiring desktop confirmation.

### 5. Zero Dependencies (Pure Python)
- Single-file architecture implemented exclusively with Python standard libraries (`http.server`, `sqlite3`, `urllib`, `struct`, `zlib`, etc.).
- No `pip install`, no node build steps, instant deployment.

---

## 🚀 Quick Start

### 1. Run the Gateway
Ensure **Xiaomi MiMo Desktop** is running, then start the gateway:

```bash
git clone https://github.com/Nelson-zhou/mimo-pwa.git
cd mimo-pwa

# Option A: one-click script (auto-picks a free port)
./start.sh

# Option B: direct start (listens on 0.0.0.0:8080 by default)
python3 server.py
```

If port 8080 is already taken (e.g. by qBittorrent), the gateway automatically tries the next free port, or you can pin one:

```bash
PORT=8081 ./start.sh
# or
python3 server.py --port 8081
```

### 2. Network Access

#### Option A: Tailscale Serve (Recommended for Remote Access)
Exposes an official HTTPS certificate required for standalone PWA installation:

```bash
# Enable HTTPS forwarding on port 8443 (use your actual gateway port)
tailscale serve --https=8443 --bg 8080
```

The gateway auto-detects your Tailscale MagicDNS hostname and only advertises an HTTPS install URL when `tailscale serve status` actually forwards to the current gateway port. If none exists yet, run `tailscale serve` first (use your real gateway port, e.g. 8081).

#### Option B: Local Wi-Fi
Connect phone and computer to the same Wi-Fi, and open `http://<LAN_IP>:8080` (or the auto-selected port).

### 3. Add to Home Screen
- **iOS (Safari)**: Tap Share ➔ Tap **Add to Home Screen**.
- **Android (Chrome)**: Tap menu ➔ Tap **Install App** / **Add to Home Screen**.

---

## ⚙️ Command Line Options

```text
Usage: python3 server.py [options]

Options:
  --port PORT       Gateway listen port (default: 8080; auto-increments if occupied)
  --host HOST       Interface IP to bind (default: 0.0.0.0)
  --workdir DIR     Default workspace directory for new sessions (default: ~)
```

---

## 📄 License

Distributed under the [MIT License](./LICENSE).
