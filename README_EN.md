# Xiaomi MiMo PWA 📱✨

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PWA](https://img.shields.io/badge/PWA-Installable-orange.svg)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Tailscale-Ready-black.svg)](https://tailscale.com/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-success.svg)](#)

> **Official Pixel-Perfect Mobile PWA Gateway for Xiaomi MiMo Desktop** — Control and monitor your Xiaomi MiMo AI agent running on your desktop from any mobile device (Android & iOS) anytime, anywhere. Features genuine address-bar-free standalone PWA installation, desktop focus synchronization, and real model switching.

[中文文档](./README.md)

---

## 🌟 Key Features

- 🎨 **1:1 Official Xiaomi Aesthetics**: Faithfully reproduces Xiaomi MiMo Desktop's clean white/light gray palette (`#FFFFFF` / `#F8F9FA`), brand badges, and Xiaomi orange squircle adaptive icons.
- 📲 **Genuine Standalone PWA**:
  - Fully compliant Web App Manifest (`display: standalone`) and Service Worker offline caching.
  - Generates Android WebAPK / iOS standalone apps without browser address bars or navigation chrome.
- 🖥️ **Desktop Focus Synchronization**:
  - Automatically identifies and locks onto whichever session is currently focused on your desktop monitor.
  - Real-time two-way synchronization between mobile and desktop windows.
- 🔄 **Real Model Switching**:
  - Seamlessly switch between `MiMo Auto` (intelligent routing), `MiMo Pro` (advanced reasoning & coding), and `MiMo Flash` (low-latency).
  - Model preference updates are persisted directly to desktop configuration (`preferences.json`).
- 🛡️ **Automated Execution Permissions**:
  - Automatically issues `FullAccess` authorization for turn executions, enabling uninterrupted autonomous command execution on your Mac without remote pop-up hurdles.
- ⚡ **Aligned with OpenCode Event Stream Lifecycle**:
  - Direct consumption of SSE event streams (`message.part.delta`, `message.updated`, `session.idle`).
- 🚀 **Zero External Dependencies**:
  - 100% built on the Python 3 standard library (`http.server`, `sqlite3`, `ssl`, `urllib`). No `pip install` required.

---

## 🏗️ Architecture & Mechanism

The gateway transparently hooks into 6 native artifacts exposed by the running Xiaomi MiMo Desktop instance:

1. **`desktop-api.json` (Dynamic Credentials)**: Automatically retrieves the dynamically assigned localhost port and Bearer Token on startup.
2. **OpenCode Event Protocol**: Native SSE streaming via `/v1/sessions/{id}/events`.
3. **`mimocode.db` (SQLite Persistence)**: Reads and writes directly to `~/.local/share/mimocode/mimocode.db` for instant two-way session persistence.
4. **`composer-input.json` (Focus Tracking)**: Synchronizes with the user's active session on desktop.
5. **`preferences.json` (Model Persistence)**: Reads and writes the default model configuration.
6. **`xiaomi-last-confirmed.json` (Identity Inheritance)**: Reuses the authenticated Xiaomi account nickname and user ID.

---

## 🚀 Quick Start

### 1. Prerequisites
- macOS running [Xiaomi MiMo Desktop](https://mimo.xiaomi.com/).
- Python 3.9+.

### 2. Run the Gateway
```bash
# Clone the repository
git clone https://github.com/your-username/mimo-pwa.git
cd mimo-pwa

# One-click start (default port: 8080)
./start.sh

# Or start directly with Python
python3 server.py --port 8080
```

---

## 📱 Mobile PWA Installation (Recommended via Tailscale)

Android Chrome strictly requires an **HTTPS** context to allow WebAPK standalone installation.

### Tailscale HTTPS Setup (Recommended)
1. Enable Tailscale Serve on your Mac:
   ```bash
   tailscale serve --https=8443 --bg 8080
   ```
2. Open the printed HTTPS URL in Chrome on your mobile phone:
   ```
   https://<your-device>.tailnet-name.ts.net:8443
   ```
3. Tap **"Install App"** from the top banner or Chrome's three-dot menu.
4. Launch from your home screen as a pure native app!

---

## 📄 License

This project is licensed under the [MIT License](./LICENSE).
