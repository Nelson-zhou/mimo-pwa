# Xiaomi MiMo PWA 📱✨

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PWA](https://img.shields.io/badge/PWA-Installable-orange.svg)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Tailscale-Ready-black.svg)](https://tailscale.com/)
[![Dependencies](https://img.shields.io/badge/dependencies-0-success.svg)](#)

> **Xiaomi MiMo 官方桌面端极简原质手机 PWA 网关** —— 让您随时随地通过手机（Android / iOS）操作电脑上运行的 Xiaomi MiMo AI 核心引擎，支持真正无浏览器地址栏的原生应用安装、毫秒级聚焦同步与大模型真实切换。

[English Documentation](./README_EN.md)

---

## 🌟 核心特性

- 🎨 **1:1 官方原质视觉**：深度继承 Xiaomi MiMo Desktop 标志性的极简白灰色调（`#FFFFFF` / `#F8F9FA`）、Xiaomi 官方品牌 Logo 与小米橙圆角曲面（Squircle）自适应图标。
- 📲 **真正独立 PWA 原生应用**：
  - 完整实现 Web App Manifest（`display: standalone`）与 Service Worker 离线缓存。
  - 支持 Android Chrome 原生 WebAPK 安装与 iOS 沉浸全屏，**彻底消除浏览器地址栏与导航条**，拥有独立任务后台。
- 🖥️ **桌面活跃状态毫秒级同步**：
  - 实时联动电脑端当前选中的会话，手机端打开**秒级自动锁定电脑屏幕上正在查看的任务**。
  - 手机端新建任务或发送消息，电脑端界面即刻同步呈现。
- 🔄 **真实大模型双向切换**：
  - 真实打通底层模型配置持久化，可在 `MiMo Auto`（智能调度）、`MiMo Pro`（旗舰代码与系统设计）与 `MiMo Flash`（低延迟极速响应）之间无缝切换。
- 🛡️ **自动化系统级权限放行**：
  - 任务调用强制携带完全访问权限（`FullAccess`），命令执行与文件读写自动执行，出门在外无需返回电脑端手动点击授权弹窗。
- ⚡ **OpenCode 原生流式事件对齐**：
  - 深度兼容 OpenCode 底层 SSE 事件生命周期（`message.part.delta` 打字机流、`message.updated` 状态更新、`session.idle` 空闲恢复）。
- 🚀 **零外部依赖 (Pure Python)**：
  - 100% 基于 Python 3 标准库（`http.server`、`sqlite3`、`ssl`、`urllib`），无需 `pip install` 任何第三方包，开箱即用。

---

## 🏗️ 架构与底层联动原理

本项目通过精准挖掘并利用了 Xiaomi MiMo Desktop 运行时的 **6 大本地机制**，实现安全无侵入的透明代理：

```
┌────────────────────────────────────────────────────────┐
│               手机端 PWA (Android / iOS)                │
│    (HTTPS 安全通道: https://<device>.ts.net:8443)      │
└───────────────────────────┬────────────────────────────┘
                            │  WebSocket / SSE / REST
                            ▼
┌────────────────────────────────────────────────────────┐
│             mimo-pwa 本地网关 (server.py)               │
│          (监听 0.0.0.0:8080，零依赖 Pure Python)        │
└───────────┬───────────────────────────────┬────────────┘
            │                               │
            ▼ 本地 API 调用                  ▼ 本地持久化与状态读取
┌───────────────────────────┐   ┌────────────────────────┐
│  Xiaomi MiMo Desktop 核心  │   │     本地配置文件与数据库 │
│  (内部端口: desktop-api.json)│   │                        │
│                           │   │ • mimocode.db (SQLite) │
│ • POST /v1/sessions/turns │   │ • composer-input.json  │
│ • GET  /v1/sessions/events│   │ • preferences.json     │
│ • POST /v1/sessions/abort │   │ • xiaomi-confirmed.json│
└───────────────────────────┘   └────────────────────────┘
```

1. **`desktop-api.json` (动态凭据桥梁)**：桌面端启动时在本地随机端口拉起服务，并将监听端口与 Bearer Token 写入 `~/Library/Application Support/Xiaomi MiMo/desktop-api.json`，网关自动免密接入。
2. **OpenCode 基因与流式事件**：MiMo 底层事件结构对齐 OpenCode 规范，网关直通消费 `/v1/sessions/{id}/events` 流式增量。
3. **`mimocode.db` (SQLite 数据层)**：通过 `~/.local/share/mimocode/mimocode.db` 保持多会话双向一致性与首句自动命名。
4. **`composer-input.json` (桌面聚焦同步)**：实时读取电脑当前正在操作的会话 ID，使手机端无缝接管电脑端工作流。
5. **`preferences.json` (模型持久化)**：手机端切换模型后直接回写配置，确保后续所有任务模型真实生效。
6. **`xiaomi-last-confirmed.json` (身份继承)**：读取已登录的小米账号昵称与 UID，手机端免扫码直接展现个人身份。

---

## 🚀 快速开始

### 1. 前置准备
- **操作系统**：macOS（已安装并启动 [Xiaomi MiMo Desktop](https://mimo.xiaomi.com/) 客户端）。
- **Python 版本**：Python 3.9+。

### 2. 获取代码与启动
```bash
# 克隆仓库
git clone https://github.com/your-username/mimo-pwa.git
cd mimo-pwa

# 一键启动（支持通过 PORT 环境变量指定端口，默认 8080）
./start.sh

# 或者直接用 Python 启动
python3 server.py --port 8080
```

---

## 📱 手机端访问与真正 PWA 安装（推荐 Tailscale）

Android Chrome 规范要求：**必须在 HTTPS 安全上下文中才允许安装无地址栏的原生独立 PWA**。

### 推荐方案：Tailscale 官方受信任 HTTPS 通道（零配置）

1. 在电脑上配置 Tailscale Serve（将 Tailscale 专属安全域名映射至网关）：
   ```bash
   # 为 8443 端口启用 Tailscale 自动 HTTPS 代理
   tailscale serve --https=8443 --bg 8080
   ```
2. 启动 `server.py`，终端会动态输出您的专属 HTTPS 地址，例如：
   ```
   👉【真正原生 PWA 安装通道（HTTPS 安全证书，无浏览器框）】:
      https://your-mac.tail9f7768.ts.net:8443
   ```
3. 用手机（红米/小米/其它 Android 设备）的 Chrome 打开该 HTTPS 地址：
   - 网页顶部会出现横幅：**「📲 点击安装 Xiaomi MiMo 到手机桌面」**，直接点击即可；
   - 或点击 Chrome 右上角 **「⋮」** 菜单，点击 **「安装应用」**。
4. 在手机桌面上点击 **Xiaomi MiMo** 启动 —— **彻底脱离浏览器，全屏无地址栏，体验与官方 App 完全一致**！

> 💡 **iOS 用户**：在 Safari 中打开页面，点击底部的【分享】按钮，选择【添加到主屏幕】即可。

---

## ⚙️ 命令行参数

```bash
python3 server.py --help

选项:
  --port PORT        指定网关监听端口 (默认: 8080)
  --host HOST        指定监听地址 (默认: 0.0.0.0)
  --workdir DIR      指定新建任务的默认工作目录 (默认: 当前用户家目录 ~)
```

---

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request！
- 代码遵循 PEP 8 规范。
- 坚持“零第三方依赖”的设计理念，保持极简与高效。

---

## 📄 开源许可证

本项目采用 [MIT License](./LICENSE) 开源许可。
