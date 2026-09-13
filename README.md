# Xiaomi MiMo PWA 📱

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-0%20(Pure%20Python)-success.svg)](#)
[![PWA Ready](https://img.shields.io/badge/PWA-Standalone%20App-5A0FC8.svg?logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![Tailscale](https://img.shields.io/badge/Network-Tailscale%20%2F%20LAN-black.svg?logo=tailscale&logoColor=white)](https://tailscale.com/)

> **Xiaomi MiMo 官方桌面端轻量手机 PWA 网关**。  
> 解决桌面端 AI Agent 无法在移动端操作的痛点，出门在外通过手机随时接管电脑上的 MiMo 工作流。单文件纯 Python 编写，零第三方依赖。

[English Documentation (英文文档)](./README_EN.md)

---

## 🛠️ 解决的实际痛点

Xiaomi MiMo 官方仅提供 macOS / 桌面客户端，开发者离开电脑后无法获知任务进度，也无法临时派发紧急任务。

本项目通过反编译与分析桌面客户端本地运行机制，提供免侵入的本地网关，实现：
1. **手机端全功能操作**：手机随时向电脑端 MiMo 提需求、查阅执行中的代码/文件产物、派发长期任务。
2. **免确认远程自主执行**：自动放行执行权限，工具链与终端命令在电脑端静默执行，无需回到电脑前点击授权弹窗。
3. **真实桌面状态双向同步**：手机端直接继承电脑端当前选中的会话与工作目录，两端状态实时保持一致。
4. **原生 App 级使用体验**：支持安装为无浏览器边框的独立 PWA 应用，支持语音输入、图片上传。

---

## 🏗️ 深入原理：客户端 6 大本地集成点

网关无需破解或修改客户端二进制文件，通过精准监听与联动客户端本地落地的 6 个核心数据源实现透明代理：

```
┌────────────────────────────────────────────────────────┐
│               手机端 PWA (iOS Safari / Android Chrome) │
│    (Tailscale HTTPS 域名直连 / 本地局域网 Wi-Fi)        │
└───────────────────────────┬────────────────────────────┘
                            │  SSE 增量流 / REST API
                            ▼
┌────────────────────────────────────────────────────────┐
│             mimo-pwa 代理网关 (server.py)               │
│         (监听 0.0.0.0:8080，单文件 100% 纯 Python)      │
└───────────┬───────────────────────────────┬────────────┘
            │                               │
            ▼ 本地 API 调用                  ▼ 本地状态与持久化读取/回写
┌───────────────────────────┐   ┌────────────────────────────────┐
│  Xiaomi MiMo Desktop 核心 │   │     本地核心配置与数据库       │
│  (内部端口: desktop-api.json)│   │                                │
│                           │   │ 1. desktop-api.json (动态凭据) │
│ • POST /v1/sessions/turns │   │ 2. mimocode.db (SQLite 会话库) │
│ • GET  /v1/sessions/events│   │ 3. composer-input.json (焦点)  │
│ • POST /v1/sessions/abort │   │ 4. preferences.json (默认模型) │
│ • GET  /v1/tools          │   │ 5. Electron LevelDB (用户设置) │
│                           │   │ 6. Cookies.db (SSO 配额接口)   │
└───────────────────────────┘   └────────────────────────────────┘
```

| 集成点 | 本地路径 / 协议 | 作用与实现原理 |
| :--- | :--- | :--- |
| **1. 动态服务凭据** | macOS: `~/Library/Application Support/Xiaomi MiMo/desktop-api.json`<br>Linux: `~/.config/XiaomiMiMoDesktop/desktop-api.json` | 客户端启动时监听随机端口，网关自动提取其 `port` 与 Bearer `token`，完成免密反代。 |
| **2. 会话与历史库** | `~/.local/share/mimocode/mimocode.db` (SQLite) | 手机端新建会话直接写入 SQLite，自动继承当前工作目录；首条消息自动提炼并重命名标题。 |
| **3. 桌面焦点联动** | 与数据目录同级的 `composer-input.json` | 实时读取电脑上用户最后活跃的 `activeSessionId`，手机打开自动定位到该任务。 |
| **4. 模型切换回写** | 与数据目录同级的 `preferences.json` | 手机端切换模型后直接回写配置，使后续所有任务的模型选择永久生效。 |
| **5. 真实用户头像** | 与数据目录同级的 `Local Storage/leveldb` | 解析 LevelDB 中存储的 `mimo.set.avatar` 键值，动态提取并在移动端展示真实用户头像。 |
| **6. 订阅配额监控** | 与数据目录同级的 `Partitions/xiaomi-account/Cookies` | 提取小米 SSO `passToken`，实时查询本周剩余配额百分比与周重置倒计时。 |

> 网关启动时会自动探测数据目录：优先查找含有 `desktop-api.json` 的路径，兼容 macOS 与 Linux 安装布局。

---

## ⚡ 核心能力与硬核设计

### 1. 官方原生 1M 超长上下文 & 实时 Token HUD
- **1,000,000 Token 上下文支持**：对齐 MiMo 内部配置（`limit: { context: 1e6 }`），自有模型完全解锁 1M 上下文。
- **实时环形进度 HUD**：顶栏动态计算并显示当前会话消耗的 Token 总量、剩余百分比、Prompt 缓存命中率（Cache Hit Rate）。

### 2. 官方大模型全矩阵支持
| 模型标识 | 对应后端参数 | 算力消耗 | 定位与特性 |
| :--- | :--- | :---: | :--- |
| **MiMo Auto** | `mimo-auto` | 1.0x | 官方推荐，自动根据任务复杂度路由调度 |
| **MiMo-X-Pro-Preview** | `mimo-x-pro-preview` | 1.0x | 旗舰级推理，针对大型架构、深度算法与复杂代码重构 |
| **MiMo-X-Flash-Preview**| `mimo-x-flash-preview` | 0.4x | 极速响应，针对日常轻量编辑与即时问答 |

### 3. 双通道通信高可用架构 (SSE + 轮询看门狗)
- **毫秒级 SSE 打字机流**：直通底层 `/v1/sessions/{id}/events`，结构化输出思考过程（Thinking）与工具调用卡片（Bash、Edit、Grep、Read）。
- **锁屏/切后台防丢失保障**：移动端切后台容易导致 TCP 连接挂起，网关集成 1.5s 智能轮询看门狗，亮屏瞬间秒级补全错过的消息片段。

### 4. 远程执行免授权
- 手机端发起的任务默认携带 `perm: "完全访问权限"`，终端命令自动放行，无需电脑前二次点击弹窗确认。

### 5. 零外部依赖 (Pure Python)
- 单文件架构，完全使用 Python 3 标准库（`http.server`、`sqlite3`、`urllib`、`struct`、`zlib` 等）。
- 无需执行 `pip install`，无外部轮子与 node 构建环境，拷走即跑。

---

## 🚀 极速部署指引

### 1. 启动网关
确保电脑上的 **Xiaomi MiMo** 客户端正在运行，然后执行：

```bash
# 克隆项目
git clone https://github.com/Nelson-zhou/mimo-pwa.git
cd mimo-pwa

# 方式 A：一键启动（端口被占用时会自动切换）
./start.sh

# 方式 B：直接启动 (默认监听 0.0.0.0:8080)
python3 server.py
```

若 8080 被其他程序占用（例如 qBittorrent），网关会自动尝试下一个可用端口，或手动指定：

```bash
PORT=8081 ./start.sh
# 或
python3 server.py --port 8081
```

### 2. 远程网络访问配置

#### 方案 A：Tailscale 远程直连（强烈推荐，外网随时用）
通过 Tailscale 官方内置的 HTTPS 反向代理，可获得经过 CA 认证的合法 HTTPS 证书（满足 PWA 原生安装条件）：

```bash
# 开启后台映射（仅需执行一次；8080 改成你实际监听的端口）
tailscale serve --https=8443 --bg 8080
```

网关启动时会自动读取本机 MagicDNS 域名，并检查 `tailscale serve status`：**仅当存在转发到当前网关端口的 HTTPS 配置时**，才会在终端与页面中展示可点击的安装链接。若尚未配置，请先执行上面的 `tailscale serve` 命令（端口改成实际监听端口，例如 8081）。

#### 方案 B：同一局域网 Wi-Fi 直连
手机与电脑连接同一 Wi-Fi，手机浏览器直接访问终端输出的局域网 IP（如 `http://192.168.x.x:8080`）。

### 3. 安装到手机桌面
- **iOS (Safari)**：点击底部【分享】按钮 ➔ 选择【添加到主屏幕】。
- **Android (Chrome)**：点击地址栏右侧菜单 ➔ 选择【安装应用】或【添加到主屏幕】。

添加后即可作为完全独立的 App 运行，无任何浏览器网址栏与外框干扰。

---

## ⚙️ 命令行参数

```text
用法: python3 server.py [选项]

选项:
  --port PORT       指定服务监听端口 (默认: 8080；被占用时自动递增)
  --host HOST       指定监听网卡 IP (默认: 0.0.0.0)
  --workdir DIR     指定新建会话的默认物理工作目录 (默认: 当前用户 ~)
```

---

## 📄 许可证

基于 [MIT License](./LICENSE) 开源发布。
