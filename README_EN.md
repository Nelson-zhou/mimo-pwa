# Xiaomi MiMo PWA 📱✨

[![Python](https://img.shields.io/badge/python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8.svg?logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Tailscale-HTTPS%20Ready-black.svg?logo=tailscale&logoColor=white)](https://tailscale.com/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-0%20(Pure%20Python)-success.svg)](#)

> **Official Pixel-Perfect Mobile PWA Gateway for Xiaomi MiMo Desktop** — Seamlessly monitor and control your Xiaomi MiMo AI agent on your desktop from any mobile device (iOS / Android / tablets) anytime, anywhere. Features genuine address-bar-free standalone PWA installation, desktop focus synchronization, 1M official context HUD, and desktop avatar & weekly quota linkage.

[中文文档 (Chinese Documentation)](./README.md)

---

## 🌟 Key Features

### 🎨 1. 1:1 Official MiMo Aesthetics & Brand Mark
- **Authentic MiMo Geometric Mark**: Extracted from desktop client source Figma assets (`Figma 1929:695 / 2046:263`), showcasing deep black canvas (`#000000`) and cream-white (`#FFF9EE`) 4-quadrant geometric symbols (`M` `I` `M` `O`).
- **Complete Retina Icon Matrix**: Includes `apple-touch-icon.png` (180×180 full-bleed squircle clipping for iOS), `icon-192.png`, `icon-512.png`, and vector SVGs with strict cache-busting headers to guarantee instant visual updates.
- **Minimalist Light Interface**: 1:1 reproduction of desktop styling (`#FFFFFF` / `#F8F9FA`), floating dock input bar, syntax-highlighted code blocks, and collapsible reasoning accordions.

### 🤖 2. Official Model Matrix with Real-Time Persistence
Full bidirectional synchronization with desktop `preferences.json`, supporting all official MiMo models:
| Model Name | Positioning | Compute Multiplier | Recommended Use Case |
| :--- | :--- | :---: | :--- |
| **MiMo Auto** | Recommended default scheduler | 1.0x | General coding, intent analysis, everyday tasks |
| **MiMo-X-Pro-Preview** | Flagship reasoning & coding | 1.0x | Complex system architectures, large refactors, full-stack debug |
| **MiMo-X-Flash-Preview**| Ultra-low latency | 0.4x | Quick Q&A, lightweight scripts, conversational flow |

### 📊 3. 1M Context Window & Dynamic SVG HUD
- **1,000,000 (1M) Native Token Capacity**: Decoded from client's internal asar configuration (`limit: { context: 1e6 }`). Proprietary MiMo models leverage full 1M context limits, while 3rd party models adapt to 200k.
- **Dynamic Circular Progress HUD**: Header HUD displays current token count, percentage, remaining capacity, and prompt cache hit rate in real time.

### 👤 4. Desktop Avatar & 7-Day Usage + Weekly Quota
- **Direct LevelDB Avatar Linkage**: Automatically extracts and circular-crops user avatar from Electron LevelDB (`mimo.set.avatar`) alongside Xiaomi SSO profile credentials.
- **Interactive 7-Day Histogram**: Tap the avatar to open an interactive modal displaying daily token consumption for the past week, today's usage, and week total.
- **Subscription Quota Indicator**: Displays remaining weekly subscription quota percentage and reset schedule (e.g. *Remaining 68.5% · Resets Monday 00:00*), identical to desktop app.

### ⚡ 5. Dual-Channel High Reliability (SSE + Polling Guard)
- **Millisecond Typewriter Streaming**: Direct pass-through of `/v1/sessions/{id}/events` SSE stream with structured tool invocation cards (Bash, Edit, Grep, Read).
- **Mobile Sleep & Background Protection**: Built-in 1.5s intelligent polling fallback ensures zero lost messages when switching apps or locking the screen.
- **Workspace Directory & Auto Title**: Inherits desktop working directory (`~`) for new tasks, and automatically extracts conversation titles from the opening prompt.

### 🛠️ 6. Multimodal Input & System Permissions
- **Speech-to-Text Voice Input**: Integrated Web Speech API for instantaneous, hands-free voice dictation.
- **Multimodal File & Image Uploads**: Drag and drop or upload images and documents with live thumbnails injected into the prompt.
- **System-Level Permission Bypass**: Quick toggles for "Full Access", "Ask for Approval", or "Default", allowing autonomous remote script execution without returning to your desktop.
- **Plugins & Artifacts**: Inspect installed MCP skills and preview generated artifacts and code directly on your phone.

### 🚀 7. Zero External Dependencies (Pure Python)
- **100% Python 3 Standard Library** (`http.server`, `sqlite3`, `urllib`, `struct`, `zlib`, etc.).
- **Zero `pip install` required**, zero node_modules, instant deployment.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│             Mobile PWA (iOS Safari / Android Chrome)   │
│    (Tailscale HTTPS: https://<device>.ts.net:8443)     │
└───────────────────────────┬────────────────────────────┘
                            │  SSE Stream / REST API
                            ▼
┌────────────────────────────────────────────────────────┐
│             mimo-pwa Local Gateway (server.py)         │
│          (Listening on 0.0.0.0:8080, Pure Python)      │
└───────────┬───────────────────────────────┬────────────┘
            │                               │
            ▼ Local REST Bridge             ▼ Local Storage & Persistence
┌───────────────────────────┐   ┌────────────────────────────────┐
│  Xiaomi MiMo Desktop Core │   │     Local Config & Databases   │
│  (Internal dynamic port)  │   │                                │
│ • POST /v1/sessions/turns │   │ • mimocode.db (SQLite session) │
│ • GET  /v1/sessions/events│   │ • composer-input.json (focus)  │
│ • POST /v1/sessions/abort │   │ • preferences.json (models)    │
│ • GET  /v1/tools          │   │ • Cookies.db (SSO quota query) │
│                           │   │ • LevelDB (desktop app avatar) │
└───────────────────────────┘   └────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **OS**: macOS running [Xiaomi MiMo Desktop](https://mimo.xiaomi.com/).
- **Python**: Python 3.9+.

### 2. Run the Gateway
```bash
# Clone repository
git clone https://github.com/Nelson-zhou/mimo-pwa.git
cd mimo-pwa

# One-click start (default port: 8080)
./start.sh

# Or start directly with Python
python3 server.py --port 8080
```

---

## 📱 Mobile Installation & PWA Experience

To eliminate browser address bars and get a native full-screen app experience, use **Tailscale HTTPS**:

### Recommended: Tailscale Automatic HTTPS

1. **Enable Tailscale Port Serving on your Mac**:
   ```bash
   tailscale serve --https=8443 --bg 8080
   ```
2. **Launch the Gateway**: The terminal will print your private HTTPS address:
   ```text
   👉 [True Native PWA Installation Channel (HTTPS Valid Certificate)]:
      https://macbook-pro.tail9f7768.ts.net:8443
   ```
3. **Install on Phone**:
   - **iOS (Safari)**: Open the link ➔ Tap **Share** ➔ Tap **Add to Home Screen**.
   - **Android (Chrome)**: Open the link ➔ Tap **Add to Home screen** / **Install App**.
4. **Result**: A pristine standalone **Xiaomi MiMo** application icon appears on your home screen with no browser chrome.

---

## ⚙️ Command Line Options

```bash
python3 server.py --help

Options:
  --port PORT        Gateway listening port (default: 8080)
  --host HOST        Listening interface (default: 0.0.0.0)
  --workdir DIR      Default working directory for new sessions (default: ~)
```

---

## 📄 License

Distributed under the [MIT License](./LICENSE). Built to empower developers and AI agent enthusiasts with desktop-grade workflows on mobile.
