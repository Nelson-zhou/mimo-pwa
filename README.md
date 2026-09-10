# Xiaomi MiMo PWA 📱✨

[![Python](https://img.shields.io/badge/python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8.svg?logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Tailscale-HTTPS%20Ready-black.svg?logo=tailscale&logoColor=white)](https://tailscale.com/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-0%20(Pure%20Python)-success.svg)](#)

> **Xiaomi MiMo 官方桌面端极简原质手机 PWA 网关** —— 让您随时随地通过手机（iOS / Android / 平板）远程无缝操作电脑上运行的 Xiaomi MiMo 核心智能体引擎。支持真正无浏览器地址栏的原生应用安装、毫秒级桌面聚焦同步、1M 官方上下文 HUD、客户端头像与周用量配额双向联动。

[English Documentation (英文文档)](./README_EN.md)

---

## 🌟 核心特性

### 🎨 1. 1:1 官方原质设计与品牌标识
- **官方正版 MiMo 品牌图腾**：提取自客户端源码 Figma 原稿（`Figma 1929:695 / 2046:263`），采用深邃黑底（`#000000`）与米白色（`#FFF9EE`）经典四宫格几何标识（`M` `I` `M` `O`），告别传统小米橙标与杂乱图标。
- **全套 Retian 图标矩阵**：涵盖 `apple-touch-icon.png` (180×180 Full-Bleed iOS 原生裁切)、`icon-192.png`、`icon-512.png` 与矢量 SVG，配备强缓存驱逐机制（Cache-Busting），确保保存到桌面即呈完美质感。
- **明亮极简交互界面**：1:1 还原桌面版色调（`#FFFFFF` / `#F8F9FA`）、浮岛输入条、代码块语法高亮与折叠式思维链（Thinking Accordion）。

### 🤖 2. 官方大模型矩阵双向无缝切换
支持与桌面端 `preferences.json` 真实持久化同步，可在三大官方大模型之间任意切换：
| 模型名称 | 官方定位 | 算力倍率 | 推荐适用场景 |
| :--- | :--- | :---: | :--- |
| **MiMo Auto** | 官方推荐·默认智能调度 | 1.0x | 综合日常开发、智能意图识别与任务拆解 |
| **MiMo-X-Pro-Preview** | 旗舰推理·顶级编程 | 1.0x | 复杂系统架构、大型代码重构、全栈 Debug |
| **MiMo-X-Flash-Preview**| 极速响应·轻量敏捷 | 0.4x | 快速问答、轻量脚本修改、极低延迟交互 |

### 📊 3. 1M 官方超长上下文 & 实时 HUD 指示器
- **1,000,000 (1M) 真实上下文极限**：对齐桌面客户端 asar 反编译配置（`limit: { context: 1e6 }`），MiMo 自有模型完整支持 100 万 Token 上下文，第三方模型自动适配 200k。
- **动态 SVG 环形进度 HUD**：顶栏实时环形进度条显示当前会话 Token 消耗、百分比、剩余容量及 Prompt 缓存命中率（Cache Hit Rate）。

### 👤 4. 客户端头像与 7 天用量 + 周配额联动
- **桌面头像与昵称秒级继承**：读取并解码 Electron LevelDB 本地设置（`mimo.set.avatar`）与账号凭据，圆形裁切并在侧栏底部实时展示用户真实头像与昵称。
- **近 7 天 Token 用量直方图**：点击头像即可展开交互式弹窗，展示近 7 天 Token 消耗柱状图、今日用量与本周合计。
- **订阅配额剩余量指示器**：弹窗底部完整还原桌面端「剩余用量」面板，通过小米 SSO 接口获取当前周期剩余配额百分比与每周重置倒计时（例如：*剩余 68.5% · 将于周一 00:00 重置*）。

### ⚡ 5. 高可用双通道流式通讯 (SSE + 轮询兜底)
- **毫秒级打字机流式输出**：直连 MiMo 核心引擎 `/v1/sessions/{id}/events` SSE 流，支持工具调用卡片（Bash、Edit、Grep、Read）实时状态与标准输出展示。
- **移动端锁屏与切后台保障**：搭载 1.5s 智能轮询守护引擎，即使移动网络丢包或连接挂起，重新亮屏即刻无缝续接对话内容。
- **工作目录与标题自动同步**：新建对话自动继承电脑端真实工作目录（`~`），首条指令自动提炼并重命名会话标题。

### 🛠️ 6. 全功能多模态与系统级权限
- **真实语音输入**：集成 Web Speech API，点击麦克风直接进行高精度普通话语音输入。
- **多模态文件/图片上传**：支持本地图片、文件拖拽或点击上传，即时生成缩略预览并自动注入 Prompt。
- **系统权限一键放行**：支持切换「完全访问权限」、「帮我审批」或「默认权限」，出门在外远程执行命令无需回电脑端手动确认。
- **插件中心与成果物预览**：支持查看与开关已安装的 MCP 扩展技能，支持 Artifacts 代码/文件直读预览。

### 🚀 7. 纯正零外部依赖 (Pure Python)
- **100% 纯 Python 3 标准库**（`http.server`、`sqlite3`、`urllib`、`struct`、`zlib` 等）。
- **零 `pip install`**，无 node_modules，无额外编译环境，克隆即可运行。

---

## 🏗️ 系统架构图

```
┌────────────────────────────────────────────────────────┐
│               手机端 PWA (iOS Safari / Android Chrome) │
│    (Tailscale HTTPS 通道: https://<device>.ts.net:8443)│
└───────────────────────────┬────────────────────────────┘
                            │  SSE 打字机增量 / REST API
                            ▼
┌────────────────────────────────────────────────────────┐
│             mimo-pwa 本地网关 (server.py)               │
│          (监听 0.0.0.0:8080，零依赖 Pure Python)        │
└───────────┬───────────────────────────────┬────────────┘
            │                               │
            ▼ 本地 REST 通信                 ▼ 本地数据持久化读取与回写
┌───────────────────────────┐   ┌────────────────────────────────┐
│  Xiaomi MiMo Desktop 引擎 │   │     本地配置文件与数据库       │
│  (内部动态端口: desktop-api.json)│   │                                │
│                           │   │ • mimocode.db (SQLite 会话库)   │
│ • POST /v1/sessions/turns │   │ • composer-input.json (桌面聚焦)│
│ • GET  /v1/sessions/events│   │ • preferences.json (模型设置)   │
│ • POST /v1/sessions/abort │   │ • Cookies.db (SSO 周配额查询)  │
│ • GET  /v1/tools          │   │ • LevelDB (桌面用户自定义头像) │
└───────────────────────────┘   └────────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 前置环境
- **操作系统**：macOS（已安装并登录运行 [Xiaomi MiMo Desktop](https://mimo.xiaomi.com/) 客户端）
- **Python 版本**：Python 3.9+

### 2. 获取代码与运行
```bash
# 克隆仓库
git clone https://github.com/Nelson-zhou/mimo-pwa.git
cd mimo-pwa

# 一键启动（默认端口 8080）
./start.sh

# 或者直接通过 Python 启动
python3 server.py --port 8080
```

---

## 📱 手机端安装与沉浸式 PWA 体验

为了让 PWA **彻底脱离浏览器地址栏与导航条**，获得与原生 App 一致的全屏体验，推荐配合 **Tailscale HTTPS** 通道使用：

### 推荐方案：Tailscale 官方自动证书（零配置内网穿透）

1. **电脑端开启 Tailscale 端口代理**：
   ```bash
   # 将 Tailscale 安全域名的 8443 端口映射至网关 8080
   tailscale serve --https=8443 --bg 8080
   ```
2. **终端将自动输出专属访问链接**，例如：
   ```text
   👉【真正原生 PWA 安装通道（HTTPS 安全证书，无浏览器框）】:
      https://macbook-pro.tail9f7768.ts.net:8443
   ```
3. **手机端添加至主屏幕**：
   - **iOS (iPhone / iPad)**：在 Safari 中打开上述链接 ➔ 点击底部的 **「分享 (Share)」** 按钮 ➔ 选择 **「添加到主屏幕 (Add to Home Screen)」**。
   - **Android (小米 / 红米 / 华为等)**：在 Chrome 浏览器中打开 ➔ 点击顶部横幅 **「添加到桌面」** 或右上角菜单 **「安装应用」**。
4. **效果**：桌面生成纯正黑底米白色的 **Xiaomi MiMo** 独立图标，点击启动后全屏无浏览器框架，直接进入 AI 工作流！

---

## ⚙️ 进阶配置与命令行参数

```bash
python3 server.py --help

选项:
  --port PORT        指定网关监听端口 (默认: 8080)
  --host HOST        指定监听地址 (默认: 0.0.0.0)
  --workdir DIR      指定新建任务的默认工作目录 (默认: 当前用户家目录 ~)
```

---

## 📂 项目结构

```text
mimo-pwa/
├── server.py              # 网关主程序（含全套 1:1 前端 UI、SSE 代理与持久化桥接，单文件纯 Python）
├── start.sh               # 一键启动与环境检查脚本
├── requirements.txt       # 空文件（100% 纯标准库，零外部包依赖）
├── LICENSE                # MIT 开源协议
├── README.md              # 中文详细指南与特性说明
├── README_EN.md           # English Guide
└── assets/                # 官方纯正 MiMo 高清图标与静态资源
    ├── apple_touch_icon.png
    ├── icon-192.png
    ├── icon-512.png
    ├── icon-192.svg
    ├── icon-512.svg
    ├── avatar.png
    └── mimo_official_icon_1024.png
```

---

## 📄 开源许可证

本项目基于 [MIT License](./LICENSE) 开源发布。代码旨在为广大 Xiaomi MiMo 开发者与智能体爱好者提供更自由的移动工作流支持。
