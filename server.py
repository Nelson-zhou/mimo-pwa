#!/usr/bin/env python3
"""
================================================================================
Xiaomi MiMo Desktop 官方极简原质 PWA 网关 (v6.0.0)
================================================================================
深度继承与还原 Xiaomi MiMo Desktop 官方界面色调与品牌特征：
- 1:1 官方明亮色调 (#FFFFFF / #F8F9FA) 与极简设计语言
- 继承官方 Logo: [Xiaomi MIMO Beta]
- 动态继承客户端当前登录的小米账号昵称与用户 ID
- 继承官方浮岛输入框样式与 [完全访问] / [MiMo Auto] / [免责声明]
- 继承官方代码块样式 (带行号与复制按钮)
- 支持新建任务会话、自动重命名、大模型选择面板与高频状态轮询守护
================================================================================
"""

import json
import os
import re
import socket
import sqlite3
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
import zlib

DEFAULT_GATEWAY_PORT = 8080
DESKTOP_API_JSON_PATH = os.path.expanduser("~/Library/Application Support/Xiaomi MiMo/desktop-api.json")
MIMO_DB_PATH = os.path.expanduser("~/.local/share/mimocode/mimocode.db")
COMPOSER_INPUT_PATH = os.path.expanduser("~/Library/Application Support/Xiaomi MiMo/composer-input.json")
XIAOMI_CONFIRMED_PATH = os.path.expanduser("~/Library/Application Support/Xiaomi MiMo/xiaomi-last-confirmed.json")
PREFERENCES_PATH = os.path.expanduser("~/Library/Application Support/Xiaomi MiMo/preferences.json")
AVATAR_PNG_PATH = os.path.join(os.path.dirname(__file__), "assets", "avatar.png")
AVATAR_SVG_PATH = os.path.join(os.path.dirname(__file__), "assets", "avatar.svg")


def load_desktop_api_credentials() -> Tuple[Optional[int], Optional[str]]:
    """读取 Xiaomi MiMo Desktop 运行时动态生成的端口与鉴权 Token"""
    if not os.path.exists(DESKTOP_API_JSON_PATH):
        return None, None
    try:
        with open(DESKTOP_API_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("port"), data.get("token")
    except Exception:
        return None, None


def get_current_model() -> str:
    """真实读取当前在 preferences.json 中保存的模型配置"""
    if os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
                m = p.get("model", "mimo/mimo-auto")
                if "/" in m:
                    return m.split("/", 1)[1]
                return m
        except Exception:
            pass
    return "mimo-auto"


def set_current_model(model_id: str) -> bool:
    """修改 preferences.json 中的模型并持久化到本地桌面应用配置中"""
    if not model_id:
        return False
    if os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["model"] = f"mimo/{model_id}" if not model_id.startswith("mimo/") else model_id
            with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
                json.dump(p, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print("Error updating preferences.json model:", e)
            return False
    return False


def get_user_profile() -> Dict[str, Any]:
    """读取客户端当前登录的小米账号昵称与用户 ID"""
    name = "MiMo User"
    uid = ""
    if os.path.exists(XIAOMI_CONFIRMED_PATH):
        try:
            with open(XIAOMI_CONFIRMED_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                name = data.get("displayName") or name
                uid = data.get("userId") or uid
        except Exception:
            pass
    return {
        "displayName": name,
        "userId": uid,
        "avatarUrl": "/icons/avatar.png" if os.path.exists(AVATAR_PNG_PATH) else "",
    }


def get_desktop_current_session_id() -> Optional[str]:
    """读取用户当前在电脑端窗口中聚焦打开的活跃会话 ID"""
    if os.path.exists(COMPOSER_INPUT_PATH):
        try:
            with open(COMPOSER_INPUT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 桌面端当前打开的会话记录在 convoMeta 的键中
                meta = data.get("convoMeta")
                if meta and isinstance(meta, dict):
                    keys = [k for k in meta.keys() if k.startswith("ses_")]
                    if keys:
                        return keys[-1]
                cur = data.get("currentKey")
                if cur and cur.startswith("ses_"):
                    return cur
        except Exception:
            pass

    if os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
            c = conn.cursor()
            c.execute(
                """
                SELECT id FROM session 
                WHERE title NOT LIKE 'checkpoint-writer%' 
                  AND title NOT IN ('Auto Dream', 'Auto Distill', 'Title request', '新任务会话', '测试会话REST')
                ORDER BY time_updated DESC LIMIT 1
                """
            )
            row = c.fetchone()
            conn.close()
            if row and row[0]:
                return row[0]
        except Exception:
            pass

    return None


def create_new_mimo_session_in_db(title: str = "新任务会话", directory: Optional[str] = None) -> Dict[str, Any]:
    if not directory:
        directory = os.path.expanduser("~")
    """在电脑本地数据库中创建一个全新的真实 MiMo 会话"""
    import uuid

    new_id = "ses_" + uuid.uuid4().hex[:22]
    now = int(time.time() * 1000)
    if os.path.exists(MIMO_DB_PATH):
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=5)
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, time_created, time_updated)
            VALUES (?, "global", NULL, "new-session", ?, ?, "2.1.159", ?, ?)
        """,
            (new_id, directory, title, now, now),
        )
        conn.commit()
        conn.close()

    if os.path.exists(COMPOSER_INPUT_PATH):
        try:
            with open(COMPOSER_INPUT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["currentKey"] = new_id
            with open(COMPOSER_INPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    return {
        "id": new_id,
        "title": title,
        "directory": directory,
        "time": {"created": now, "updated": now},
    }


def call_mimo_v1(
    endpoint: str, method: str = "GET", body: Optional[Dict[str, Any]] = None, timeout: float = 12.0
) -> Tuple[int, Any]:
    """向 Xiaomi MiMo Desktop 官方 v1 接口通信"""
    port, token = load_desktop_api_credentials()
    if not port or not token:
        return 503, {"error": "电脑上的 Xiaomi MiMo Desktop 尚未运行"}

    url = f"http://127.0.0.1:{port}/v1/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Xiaomi-MiMo-PWA-Client",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw}
    except Exception as e:
        return 502, {"error": str(e)}


def get_tailscale_info() -> Tuple[Optional[str], Optional[str]]:
    """动态检测当前机器的 Tailscale MagicDNS 域名与 IPv4 地址"""
    dns_name = None
    ip = None
    try:
        res = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=2, check=False)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            self_node = data.get("Self", {})
            dns = self_node.get("DNSName", "").rstrip(".")
            if dns:
                dns_name = dns
            ips = self_node.get("TailscaleIPs", [])
            for candidate in ips:
                if "." in candidate:
                    ip = candidate
                    break
    except Exception:
        pass
    if not ip:
        try:
            res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2, check=False)
            if res.returncode == 0:
                out = res.stdout.strip().split("\n")[0]
                if out and len(out.split(".")) == 4 and not out.startswith("Failed"):
                    ip = out
        except Exception:
            pass
    return dns_name, ip


def get_local_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    return "127.0.0.1"


def generate_mimo_orange_icon(size: int = 192) -> bytes:
    """动态生成 Xiaomi 标志性橙色圆角曲面 (Squircle) App 图标"""
    raw = bytearray()
    center = size / 2.0
    sq_radius = size * 0.44

    for y in range(size):
        raw.append(0)
        for x in range(size):
            dx = abs(x - center)
            dy = abs(y - center)
            norm_x = dx / sq_radius
            norm_y = dy / sq_radius
            super_d = norm_x**3.6 + norm_y**3.6

            if super_d <= 1.0:
                cx = abs(x - center)
                cy = abs(y - center)
                is_white = False
                scale = size / 192.0
                # 绘制白色的简洁 Mi 造型
                if 28 * scale <= cx <= 40 * scale and cy <= 36 * scale:
                    is_white = True
                elif cx <= 8 * scale and cy <= 36 * scale:
                    is_white = True
                elif 8 * scale <= cx <= 40 * scale and 24 * scale <= cy <= 36 * scale and (y < center):
                    is_white = True

                if is_white:
                    raw.extend([255, 255, 255, 255])
                else:
                    raw.extend([255, 105, 0, 255])  # 小米橙 #FF6900
            else:
                raw.extend([0, 0, 0, 0])

    compressed = zlib.compress(bytes(raw))
    png = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png += struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    png += struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", zlib.crc32(b"IDAT" + compressed))
    png += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    return png


ICON_192_PNG = generate_mimo_orange_icon(192)
ICON_512_PNG = generate_mimo_orange_icon(512)

# 读取裁剪好的真实客户端用户头像
if os.path.exists(AVATAR_PNG_PATH):
    with open(AVATAR_PNG_PATH, "rb") as f:
        USER_AVATAR_PNG = f.read()
else:
    USER_AVATAR_PNG = ICON_192_PNG

ICON_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
  <rect width="192" height="192" rx="42" fill="#FF6900"/>
  <g fill="#FFFFFF">
    <rect x="52" y="64" width="16" height="64" rx="4"/>
    <rect x="124" y="64" width="16" height="64" rx="4"/>
    <path d="M80 64h32c8.8 0 16 7.2 16 16v48h-16V84c0-2.2-1.8-4-4-4H80v48H64V64h16z"/>
  </g>
</svg>"""

PWA_MANIFEST_JSON = json.dumps(
    {
        "name": "Xiaomi MiMo",
        "short_name": "MiMo",
        "description": "Xiaomi MiMo Desktop AI Agent Mobile Workspace",
        "start_url": "/",
        "id": "/",
        "scope": "/",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "background_color": "#FFFFFF",
        "theme_color": "#FFFFFF",
        "orientation": "portrait",
        "lang": "zh-CN",
        "categories": ["developer", "productivity", "utilities"],
        "icons": [
            {
                "src": "/icons/icon-192.svg",
                "sizes": "192x192",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            },
            {
                "src": "/icons/icon-512.svg",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            },
            {
                "src": "/icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    },
    ensure_ascii=False,
    indent=2,
)

PWA_SERVICE_WORKER_JS = """
const CACHE_NAME = 'mimo-pwa-v9';
const PRECACHE = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-192.svg',
  '/icons/icon-512.svg',
  '/icons/avatar.png',
  '/icons/apple-touch-icon.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
      .catch(() => {})
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Stale-while-revalidate for HTML, cache-first for static assets, bypass for API
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/')) return;

  const url = new URL(e.request.url);
  const isHTML = e.request.headers.get('accept')?.includes('text/html');
  const isStatic = /\\.(js|css|svg|png|ico|json)$/.test(url.pathname);

  if (isStatic) {
    e.respondWith(
      caches.match(e.request).then((cached) => {
        if (cached) return cached;
        return fetch(e.request).then((response) => {
          if (response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
          }
          return response;
        });
      })
    );
  } else if (isHTML) {
    e.respondWith(
      fetch(e.request).then((response) => {
        if (response.status === 200) {
          caches.open(CACHE_NAME).then((c) => c.put(e.request, response.clone()));
        }
        return response;
      }).catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(
      fetch(e.request).then((response) => {
        if (response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
        }
        return response;
      }).catch(() => caches.match(e.request))
    );
  }
});
"""

# ==============================================================================
# 1:1 官方小米视觉 HTML / CSS / JS 前端
# ==============================================================================
XIAOMI_MIMO_PWA_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>Xiaomi MIMO</title>
  
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#FFFFFF">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="MiMo">
  <meta name="application-name" content="Xiaomi MiMo">
  <meta name="format-detection" content="telephone=no">
  <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png">
  <link rel="apple-touch-icon" sizes="192x192" href="/icons/icon-192.png">
  <link rel="apple-touch-icon" sizes="512x512" href="/icons/icon-512.png">
  <link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png">
  <link rel="shortcut icon" href="/icons/icon-192.png">

  <style>
    :root {
      --bg-main: #FFFFFF;
      --bg-sidebar: #F8F9FA;
      --bg-hover: #F1F3F5;
      --bg-active: #E5E7EB;
      --bg-card: #FFFFFF;
      --bg-code: #F3F4F6;
      --border-subtle: #E5E7EB;
      --border-light: #F0F2F5;
      --text-main: #111827;
      --text-body: #1F2937;
      --text-muted: #6B7280;
      --text-dim: #9CA3AF;
      --mimo-orange: #FF6900;
      --mimo-cyan-bg: #E0F2FE;
      --mimo-cyan-txt: #0284C7;
      --mimo-amber: #EA580C;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      background-color: var(--bg-main);
      color: var(--text-body);
      font-family: var(--font-family);
      font-size: 14px;
      line-height: 1.5;
      display: flex;
      flex-direction: column;
      height: 100dvh;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* 顶部导航条 */
    header {
      height: 52px;
      background: var(--bg-main);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 14px;
      position: sticky;
      top: 0;
      z-index: 50;
      user-select: none;
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      flex: 1;
    }

    .btn-icon {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      flex-shrink: 0;
    }
    .btn-icon:active {
      background: var(--bg-hover);
      color: var(--text-main);
    }

    .mimo-brand-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-right: 4px;
    }
    .mimo-brand-title {
      font-size: 16px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.2px;
      white-space: nowrap;
    }
    .mimo-beta-tag {
      background: var(--mimo-cyan-bg);
      color: var(--mimo-cyan-txt);
      font-size: 10px;
      font-weight: 600;
      padding: 1.5px 5px;
      border-radius: 4px;
      line-height: 1.2;
    }

    .session-title-header {
      font-size: 13.5px;
      font-weight: 500;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-left: 2px;
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }

    .btn-new-task-top {
      display: flex;
      align-items: center;
      gap: 4px;
      background: #F3F4F6;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 5px 10px;
      font-size: 12.5px;
      font-weight: 500;
      color: var(--text-main);
      cursor: pointer;
    }
    .btn-new-task-top:active {
      background: #E5E7EB;
    }

    /* 抽屉式侧边栏 */
    .drawer-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(3px);
      z-index: 100;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.22s ease;
    }
    .drawer-overlay.open {
      opacity: 1;
      pointer-events: auto;
    }

    .drawer {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: 275px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-subtle);
      z-index: 101;
      display: flex;
      flex-direction: column;
      transform: translateX(-100%);
      transition: transform 0.24s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 4px 0 24px rgba(0,0,0,0.06);
    }
    .drawer.open {
      transform: translateX(0);
    }

    .drawer-top-brand {
      padding: 16px 14px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .sidebar-nav-actions {
      padding: 6px 10px;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .sidebar-action-btn {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13.5px;
      color: var(--text-body);
      font-weight: 500;
      cursor: pointer;
    }
    .sidebar-action-btn:hover, .sidebar-action-btn:active {
      background: var(--bg-hover);
    }
    .sidebar-action-btn.primary {
      color: var(--text-main);
      font-weight: 600;
    }

    .sidebar-section-hdr {
      padding: 14px 14px 6px;
      font-size: 11.5px;
      font-weight: 600;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .sessions-list-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 0 8px 14px;
    }

    .session-item-row {
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13.5px;
      color: var(--text-body);
      cursor: pointer;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 2px;
    }
    .session-item-row:hover {
      background: var(--bg-hover);
    }
    .session-item-row.active {
      background: var(--bg-active);
      color: var(--text-main);
      font-weight: 500;
    }

    /* 侧边栏底部继承的客户端用户信息 */
    .sidebar-footer-user {
      border-top: 1px solid var(--border-subtle);
      padding: 12px 14px;
      display: flex;
      align-items: center;
      gap: 10px;
      background: var(--bg-sidebar);
    }
    .sidebar-user-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      object-fit: cover;
      background: #FFFFFF;
      border: 1px solid var(--border-subtle);
    }
    .sidebar-user-name {
      font-size: 13.5px;
      font-weight: 500;
      color: var(--text-main);
    }

    /* 消息视窗 */
    #chat-viewport {
      flex: 1;
      overflow-y: auto;
      padding: 18px 16px 140px;
      max-width: 820px;
      margin: 0 auto;
      width: 100%;
      -webkit-overflow-scrolling: touch;
    }

    .msg-user-container {
      display: flex;
      justify-content: flex-end;
      margin-bottom: 18px;
    }
    .user-bubble {
      background: #F3F4F6;
      color: var(--text-main);
      padding: 10px 14px;
      border-radius: 16px 16px 4px 16px;
      font-size: 14px;
      line-height: 1.55;
      border: 1px solid var(--border-subtle);
      max-width: 86%;
      word-break: break-word;
    }

    .msg-assistant-container {
      margin-bottom: 24px;
    }
    .assistant-prose-card {
      font-size: 14.5px;
      line-height: 1.7;
      color: var(--text-body);
      word-break: break-word;
    }

    /* 1:1 MiMo 官方代码卡片样式 */
    .mimo-code-card {
      background: var(--bg-code);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      margin: 12px 0;
      overflow: hidden;
    }
    .code-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 12px;
      background: #ECEFF2;
      border-bottom: 1px solid var(--border-subtle);
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }
    .btn-copy-code {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      color: var(--text-muted);
      cursor: pointer;
      background: none;
      border: none;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .btn-copy-code:hover {
      background: rgba(0,0,0,0.06);
      color: var(--text-main);
    }
    .code-card-body {
      padding: 10px 12px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 12.5px;
      line-height: 1.6;
      color: #1E293B;
      display: flex;
    }
    .code-line-nums {
      user-select: none;
      color: var(--text-dim);
      padding-right: 12px;
      text-align: right;
      border-right: 1px solid #E2E8F0;
      margin-right: 12px;
    }

    /* 思考折叠条 */
    .thinking-box {
      margin: 10px 0;
      border-radius: 8px;
      background: #F8FAFC;
      border: 1px solid #E2E8F0;
      overflow: hidden;
    }
    .thinking-toggle {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 12px;
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
    }
    .thinking-content {
      display: none;
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.6;
      color: #475569;
      background: #F1F5F9;
      white-space: pre-wrap;
    }
    .thinking-box.open .thinking-content {
      display: block;
    }

    /* 终端工具执行卡片 */
    .mimo-tool-card {
      background: #F8FAFC;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      margin: 10px 0;
      overflow: hidden;
    }
    .tool-header-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 12px;
    }
    .tool-badge {
      background: #E2E8F0;
      color: #334155;
      font-weight: 600;
      font-size: 10.5px;
      padding: 2px 6px;
      border-radius: 4px;
      font-family: var(--font-mono);
      margin-right: 8px;
    }
    .tool-cmd-preview {
      font-family: var(--font-mono);
      color: var(--text-body);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 180px;
    }
    .tool-status {
      font-size: 11px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .tool-status.running { color: #0284C7; }
    .tool-status.completed { color: #16A34A; }
    .tool-console-box {
      background: #0F172A;
      color: #F8FAFC;
      font-family: var(--font-mono);
      font-size: 11.5px;
      padding: 10px 12px;
      max-height: 200px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* 助手消息底部的真实操作栏 */
    .assistant-feedback-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
    }
    .btn-feedback-action {
      background: #F3F4F6;
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      cursor: pointer;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11.5px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: all 0.15s;
    }
    .btn-feedback-action:hover, .btn-feedback-action:active {
      background: #E5E7EB;
      color: var(--text-main);
    }

    /* 1:1 官方悬浮输入卡片 (Floating Dock) */
    footer {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      padding: 0 14px 14px;
      display: flex;
      flex-direction: column;
      align-items: center;
      pointer-events: none;
      z-index: 40;
    }

    .floating-mimo-island {
      width: 100%;
      max-width: 780px;
      background: #FFFFFF;
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      box-shadow: 0 6px 26px rgba(0, 0, 0, 0.08);
      padding: 10px 14px 10px;
      pointer-events: auto;
    }

    #dock-input {
      width: 100%;
      border: none;
      outline: none;
      background: transparent;
      font-size: 14.5px;
      color: var(--text-main);
      font-family: inherit;
      resize: none;
      max-height: 140px;
      min-height: 24px;
      line-height: 1.5;
      padding: 2px 0 8px;
    }
    #dock-input::placeholder {
      color: var(--text-dim);
    }

    .dock-controls-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 4px;
    }

    .dock-left-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn-dock-icon {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
    }
    .btn-dock-icon:active {
      background: var(--bg-hover);
      color: var(--text-main);
    }

    .dock-perm-badge {
      display: flex;
      align-items: center;
      gap: 4px;
      color: #EA580C;
      font-size: 12.5px;
      font-weight: 500;
      padding: 3px 6px;
      border-radius: 6px;
      cursor: pointer;
      user-select: none;
      transition: background 0.15s;
    }
    .dock-perm-badge:hover {
      background: #FFF7ED;
    }

    .dock-right-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .dock-model-selector {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 12.5px;
      font-weight: 500;
      color: var(--text-body);
      background: transparent;
      border: none;
      padding: 4px 6px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .dock-model-selector:hover {
      background: var(--bg-hover);
      color: var(--text-main);
    }

    .btn-dock-send {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: var(--text-main);
      color: #FFFFFF;
      border: none;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-dock-send.abort {
      background: #EF4444 !important;
      color: #FFFFFF !important;
    }

    .dock-disclaimer {
      font-size: 11px;
      color: var(--text-dim);
      text-align: center;
      margin-top: 6px;
      pointer-events: auto;
      user-select: none;
    }

    /* 模型弹窗 */
    .modal-sheet {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.4);
      z-index: 120;
      display: none;
      align-items: flex-end;
    }
    .modal-sheet.open {
      display: flex;
    }
    .modal-box {
      width: 100%;
      background: #FFFFFF;
      border-radius: 20px 20px 0 0;
      padding: 20px 18px 30px;
      box-shadow: 0 -8px 32px rgba(0,0,0,0.12);
    }
    .modal-title {
      font-size: 15px;
      font-weight: 600;
      color: var(--text-main);
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .model-item {
      padding: 12px 14px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      border: 1px solid transparent;
      margin-bottom: 6px;
    }
    .model-item:hover, .model-item.selected {
      background: #F8FAFC;
      border-color: #E2E8F0;
    }
    .model-item-name {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-main);
    }
    .model-item-desc {
      font-size: 11.5px;
      color: var(--text-muted);
      margin-top: 2px;
    }

    /* PWA 原生安装与 HTTPS 提示条 */
    .install-banner {
      display: none;
      background: linear-gradient(135deg, #FF6900 0%, #FF8A3D 100%);
      color: #FFFFFF;
      padding: 11px 16px;
      font-size: 13.5px;
      font-weight: 600;
      text-align: center;
      cursor: pointer;
      align-items: center;
      justify-content: center;
      gap: 8px;
      box-shadow: 0 3px 12px rgba(255, 105, 0, 0.28);
      z-index: 100;
      position: sticky;
      top: 0;
      animation: bannerSlideDown 0.3s ease;
    }
    .install-banner.show {
      display: flex;
    }
    .http-tip-banner {
      display: none;
      background: #FFF7ED;
      color: #C2410C;
      border-bottom: 1px solid #FFEDD5;
      padding: 9px 14px;
      font-size: 12.5px;
      font-weight: 500;
      text-align: center;
      cursor: pointer;
      align-items: center;
      justify-content: center;
      gap: 6px;
      z-index: 99;
      position: sticky;
      top: 0;
    }
    @keyframes bannerSlideDown {
      from { transform: translateY(-100%); }
      to { transform: translateY(0); }
    }
  </style>
</head>
<body>

  <!-- PWA 原生安装顶部指引 -->
  <div class="install-banner" id="installBanner" onclick="installApp()">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    <span>📲 点击安装 Xiaomi MiMo 到手机桌面 (真 PWA 原生应用，无地址栏)</span>
  </div>

  <div class="http-tip-banner" id="httpTipBanner" style="display:none;" onclick="location.href='__TS_PWA_URL__'">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
    <span>当前处于 HTTP 模式。点击一键进入 HTTPS 安全通道即可免浏览器框安装 PWA</span>
  </div>

  <!-- 顶部导航条 -->
  <header>
    <div class="header-left">
      <button class="btn-icon" onclick="toggleDrawer(true)">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <div class="mimo-brand-badge">
        <span class="mimo-brand-title">Xiaomi MIMO</span>
        <span class="mimo-beta-tag">Beta</span>
      </div>
      <div class="session-title-header" id="top-session-title">正在载入...</div>
    </div>
    <div class="header-right">
      <button class="btn-new-task-top" onclick="triggerNewSession()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        <span>新建</span>
      </button>
    </div>
  </header>

  <!-- 侧边栏抽屉 (1:1 官方结构) -->
  <div class="drawer-overlay" id="drawer-overlay" onclick="toggleDrawer(false)"></div>
  <div class="drawer" id="drawer">
    <div class="drawer-top-brand">
      <div class="mimo-brand-badge">
        <span class="mimo-brand-title">Xiaomi MIMO</span>
        <span class="mimo-beta-tag">Beta</span>
      </div>
      <button class="btn-icon" onclick="toggleDrawer(false)">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>

    <div class="sidebar-nav-actions">
      <div class="sidebar-action-btn primary" onclick="triggerNewSession()">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        <span>新建任务</span>
      </div>
      <div class="sidebar-action-btn" id="pwaInstallSidebarBtn" style="display:none; color:var(--mimo-orange); font-weight:600;" onclick="installApp()">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        <span>安装为独立应用</span>
      </div>
      <div class="sidebar-action-btn" onclick="alert('插件已由 Xiaomi MiMo 核心引擎统一托管')">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg>
        <span>插件</span>
      </div>
      <div class="sidebar-action-btn" onclick="alert('产物保存在当前项目目录中')">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
        <span>产物中心</span>
      </div>
    </div>

    <div class="sidebar-section-hdr">
      <span>最近 ▾</span>
    </div>

    <div class="sessions-list-scroll" id="sessions-container">
      <!-- 动态填充近期会话 -->
    </div>

    <!-- 侧边栏底部：继承电脑客户端真实用户头像与昵称 -->
    <div class="sidebar-footer-user">
      <img src="/icons/avatar.png" class="sidebar-user-avatar" id="user-avatar-img" alt="Avatar">
      <span class="sidebar-user-name" id="user-name-label">MiMo User</span>
    </div>
  </div>

  <!-- 消息流视窗 -->
  <div id="chat-viewport">
    <div class="msg-assistant-container" id="init-loader">
      <div class="assistant-prose-card">⏳ 正在同步电脑端当前会话...</div>
    </div>
  </div>

  <!-- 1:1 官方浮岛式输入框 (带 完全访问 / MiMo Auto / AI免责声明) -->
  <footer>
    <div class="floating-mimo-island">
      <textarea id="dock-input" rows="1" placeholder="描述任务，输入/调用技能" oninput="autoGrow(this)"></textarea>
      
      <div class="dock-controls-bar">
        <div class="dock-left-group">
          <button class="btn-dock-icon" title="添加附件/技能" onclick="triggerNewSession()">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          
          <div class="dock-perm-badge" title="最高权限自动执行" onclick="alert('已启用「完全访问」权限，MiMo 将自动执行代码工具，无需人工审批')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span>完全访问 ▾</span>
          </div>
        </div>

        <div class="dock-right-group">
          <div class="dock-model-selector" onclick="toggleModelSheet(true)" id="dock-model-btn" title="当前模型: MiMo Auto (官方默认)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="8"/></svg>
            <span id="model-name-label">MiMo Auto</span>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          </div>

          <button class="btn-dock-icon" title="语音输入 (按住)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
          </button>

          <button class="btn-dock-send" id="btn-dock-send" onclick="sendPrompt()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
          </button>
        </div>
      </div>
    </div>
    
    <div class="dock-disclaimer">内容由 AI 生成，请注意核实</div>
  </footer>

  <!-- 真实模型选择弹层 (对接电脑端 preferences.json 真实配置) -->
  <div class="modal-sheet" id="model-sheet" onclick="toggleModelSheet(false)">
    <div class="modal-box" onclick="event.stopPropagation()">
      <div class="modal-title">
        <span>选择模型</span>
        <button class="btn-icon" onclick="toggleModelSheet(false)">✕</button>
      </div>

      <div id="model-sheet-list" style="display:flex; flex-direction:column; gap:8px;">
        <div style="padding:16px; text-align:center; color:var(--text-muted); font-size:13px;">正在同步模型列表...</div>
      </div>
    </div>
  </div>

  <script>
    let currentSessionId = "";
    let selectedModelId = "mimo-auto";
    let selectedModelName = "MiMo Auto";
    let isBusy = false;
    let activeSseSource = null;
    let activeToolsMap = {};
    let activeAssistantBox = null;
    let activeProseCard = null;
    let busyPollTimer = null;

    // 1. PWA Service Worker 注册与 Android / Chrome 原生安装事件捕获
    let deferredPrompt = null;
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js", { scope: "/" })
          .then((reg) => {
            reg.update();
          })
          .catch(() => {});
      });
    }

    // 检查如果当前处于 HTTP，提示切换到 HTTPS 才能以真 PWA 原生安装
    if (!isStandalone && location.protocol === 'http:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      window.addEventListener("DOMContentLoaded", () => {
        const tip = document.getElementById("httpTipBanner");
        if (tip) tip.style.display = "flex";
      });
    }

    // 捕获 Android / Chrome 官方原生 PWA 安装事件
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      if (!isStandalone) {
        const banner = document.getElementById("installBanner");
        if (banner) banner.classList.add("show");
        const sideBtn = document.getElementById("pwaInstallSidebarBtn");
        if (sideBtn) sideBtn.style.display = "flex";
      }
    });

    function installApp() {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choiceResult) => {
          if (choiceResult.outcome === 'accepted') {
            console.log('MiMo PWA 安装成功');
          }
          deferredPrompt = null;
          const banner = document.getElementById("installBanner");
          if (banner) banner.classList.remove("show");
          const sideBtn = document.getElementById("pwaInstallSidebarBtn");
          if (sideBtn) sideBtn.style.display = "none";
        });
      } else {
        if (!isStandalone && location.protocol === 'http:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
          location.href = "__TS_PWA_URL__";
        } else {
          alert("如需将 MiMo 安装为原生桌面应用：\\n1. 请使用手机 Chrome 访问 __TS_PWA_URL__\\n2. 点击右上角菜单【⋮】并选择【安装应用】或【添加到主屏幕】。");
        }
      }
    }

    window.addEventListener("appinstalled", () => {
      const banner = document.getElementById("installBanner");
      if (banner) banner.classList.remove("show");
      const sideBtn = document.getElementById("pwaInstallSidebarBtn");
      if (sideBtn) sideBtn.style.display = "none";
    });

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent.toLowerCase());
    if (isIOS && !isStandalone) {
      window.addEventListener("DOMContentLoaded", () => {
        const sideBtn = document.getElementById("pwaInstallSidebarBtn");
        if (sideBtn) {
          sideBtn.style.display = "flex";
          sideBtn.onclick = () => {
            alert("在 iOS Safari 中：请点击底部【分享】图标，选择【添加到主屏幕】即可作为独立应用运行。");
          };
        }
      });
    }

    if (("standalone" in window.navigator) && window.navigator.standalone) {
      document.addEventListener("click", function(e) {
        let el = e.target;
        while (el && el.nodeName !== "A") el = el.parentNode;
        if (el && el.getAttribute("href") && el.getAttribute("target") !== "_blank") {
          e.preventDefault();
          window.location.href = el.getAttribute("href");
        }
      }, false);
    }

    // 2. 全兼容剪贴板复制 (彻底解决 HTTP / Tailscale 下 navigator.clipboard 报错失效)
    function copyText(str, btn) {
      if (!str) return;
      const orig = btn ? btn.innerHTML : "";
      function onOk() {
        if (btn) {
          btn.innerHTML = "✓ 已复制";
          btn.style.color = "#16A34A";
          setTimeout(() => { 
            btn.innerHTML = orig; 
            btn.style.color = "";
          }, 1600);
        }
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(str).then(onOk).catch(() => execCopy(str, onOk));
      } else {
        execCopy(str, onOk);
      }
    }

    function execCopy(str, cb) {
      const ta = document.createElement("textarea");
      ta.value = str;
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      ta.style.left = "-9999px";
      ta.setAttribute("readonly", "");
      document.body.appendChild(ta);
      ta.select();
      ta.setSelectionRange(0, 99999);
      try {
        const ok = document.execCommand("copy");
        if (ok && cb) cb();
      } catch (e) {
        console.error("execCopy failed:", e);
      }
      document.body.removeChild(ta);
    }

    function copyAssistantMessage(btn) {
      const container = btn.closest(".msg-assistant-container");
      if (!container) return;
      const prose = container.querySelector(".assistant-prose-card");
      const text = prose ? prose.innerText : "";
      copyText(text, btn);
    }

    function copyCodeBlock(btn) {
      const card = btn.closest(".mimo-code-card");
      if (!card) return;
      const pre = card.querySelector("pre");
      const text = pre ? pre.innerText : "";
      copyText(text, btn);
    }

    function toggleDrawer(open) {
      document.getElementById("drawer").classList.toggle("open", open);
      document.getElementById("drawer-overlay").classList.toggle("open", open);
      if (open) loadSessionsList();
    }

    function toggleModelSheet(open) {
      document.getElementById("model-sheet").classList.toggle("open", open);
      if (open) loadModelConfig();
    }

    // 3. 真实模型配置加载与切换 (实时读取并持久化写入 preferences.json)
    async function loadModelConfig() {
      try {
        const r = await fetch("/api/model");
        const data = await r.json();
        if (data && data.models) {
          selectedModelId = data.current || "mimo-auto";
          renderModelList(data.models, selectedModelId);
        }
      } catch (e) {
        console.warn("加载模型配置失败:", e);
      }
    }

    function renderModelList(models, curId) {
      const container = document.getElementById("model-sheet-list");
      if (!container) return;
      container.innerHTML = "";
      models.forEach(m => {
        const isSel = (m.id === curId);
        if (isSel) {
          selectedModelName = m.name;
          const lbl = document.getElementById("model-name-label");
          if (lbl) lbl.textContent = m.name;
        }
        const item = document.createElement("div");
        item.className = "model-item " + (isSel ? "selected" : "");
        item.onclick = () => selectRealModel(m.id, m.name);
        item.innerHTML = `
          <div>
            <div class="model-item-name" style="display:flex;align-items:center;">
              <span>${m.name}</span>
              <span style="font-size:11px;font-weight:normal;padding:1px 6px;border-radius:4px;background:#F1F3F5;margin-left:6px;color:#4B5563;">${m.badge || "官方"}</span>
            </div>
            <div class="model-item-desc">${m.desc}</div>
          </div>
          <div style="color: #FF6900; font-weight: 700; font-size: 15px;">${isSel ? '✓' : ''}</div>
        `;
        container.appendChild(item);
      });
    }

    async function selectRealModel(modelId, modelName) {
      selectedModelId = modelId;
      selectedModelName = modelName;
      const lbl = document.getElementById("model-name-label");
      if (lbl) lbl.textContent = modelName;
      toggleModelSheet(false);

      try {
        const r = await fetch("/api/model", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: modelId })
        });
        const res = await r.json();
        if (res.ok) {
          loadModelConfig();
        }
      } catch (e) {
        console.error("更新模型失败:", e);
      }
    }

    function autoGrow(textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
    }

    function stripSystemReminders(str) {
      if (!str) return "";
      return str.replace(/<system-reminder>[\\s\\S]*?<\\/system-reminder>/gi, "").trim();
    }

    function formatCodeBlocks(str) {
      if (!str) return "";
      let safe = str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      
      // 替换三反引号为小米官方代码块
      safe = safe.replace(/```(\\w*)?\\n([\\s\\S]*?)```/g, function(match, lang, code) {
        lang = lang || "code";
        const lines = code.trim().split("\\n");
        const lineNums = lines.map((_, i) => i + 1).join("\\n");
        const cleanCode = lines.join("\\n");
        return `
          <div class="mimo-code-card">
            <div class="code-card-header">
              <span>${lang}</span>
              <button class="btn-copy-code" onclick="copyCodeBlock(this)">
                📋 复制
              </button>
            </div>
            <div class="code-card-body">
              <div class="code-line-nums">${lineNums}</div>
              <pre><code>${cleanCode}</code></pre>
            </div>
          </div>
        `;
      });

      safe = safe.replace(/`([^`]+)`/g, "<code style='background:#F1F3F5;padding:2px 5px;border-radius:4px;font-family:var(--font-mono);font-size:12.5px;'>$1</code>");
      safe = safe.replace(/\\*\\*([^\\*]+)\\*\\*/g, "<strong>$1</strong>");
      safe = safe.replace(/\\n/g, "<br>");
      return safe;
    }

    async function loadUserProfile() {
      try {
        const r = await fetch("/api/user");
        const u = await r.json();
        if (u && u.displayName) {
          document.getElementById("user-name-label").textContent = u.displayName;
        }
      } catch(e) {}
    }

    async function loadSessionsList() {
      try {
        const r = await fetch("/api/sessions");
        const list = await r.json();
        const container = document.getElementById("sessions-container");
        container.innerHTML = "";

        if (Array.isArray(list)) {
          list.forEach(s => {
            const item = document.createElement("div");
            item.className = "session-item-row " + (s.id === currentSessionId ? "active" : "");
            item.textContent = s.title || "未命名任务";
            item.onclick = () => selectSession(s.id, s.title);
            container.appendChild(item);
          });
        }
      } catch(e) {}
    }

    async function selectSession(sid, title) {
      currentSessionId = sid;
      document.getElementById("top-session-title").textContent = title || "当前任务";
      toggleDrawer(false);
      await loadHistoricalMessages(sid, true);
      connectSessionSSE(sid);
    }

    async function triggerNewSession() {
      try {
        const r = await fetch("/api/sessions/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "新任务会话" })
        });
        const res = await r.json();
        if (res && res.id) {
          currentSessionId = res.id;
          document.getElementById("top-session-title").textContent = "新任务会话";

          const vp = document.getElementById("chat-viewport");
          vp.innerHTML = `
            <div class="msg-assistant-container">
              <div class="assistant-prose-card">
                👋 你好！我是 Xiaomi MiMo，请在下方描述你想要执行的编码或系统任务...
              </div>
            </div>
          `;
          connectSessionSSE(res.id);
          await loadSessionsList();
          toggleDrawer(false);

          const inp = document.getElementById("dock-input");
          if (inp) {
            inp.value = "";
            inp.focus();
          }
        }
      } catch(e) {
        alert("创建新任务失败: " + e.message);
      }
    }

    async function loadHistoricalMessages(sid, showLoader = false) {
      const vp = document.getElementById("chat-viewport");
      if (showLoader) {
        vp.innerHTML = `<div class="msg-assistant-container"><div class="assistant-prose-card">⏳ 正在同步会话记录...</div></div>`;
      }
      activeToolsMap = {};

      try {
        const r = await fetch("/api/messages?session_id=" + sid);
        const msgs = await r.json();

        if (Array.isArray(msgs) && msgs.length > 0) {
          vp.innerHTML = "";
          let renderedCount = 0;
          msgs.forEach(m => {
            const role = m.info?.role || "assistant";
            if (role === "user") {
              const textParts = (m.parts || []).filter(p => p.type === "text").map(p => p.text).join("\\n");
              const clean = stripSystemReminders(textParts);
              if (clean) {
                appendUserBubble(clean);
                renderedCount++;
              }
            } else {
              const wrap = appendAssistantBox();
              (m.parts || []).forEach(p => {
                if (p.type === "reasoning" && p.text) {
                  addThinking(wrap, p.text);
                } else if (p.type === "tool") {
                  const out = p.state?.output || p.state?.metadata?.output || "";
                  addToolCard(wrap, p.callID, p.tool, p.state?.status, p.state?.input, out);
                } else if (p.type === "text" && p.text) {
                  addProseText(wrap, p.text);
                }
              });
              appendFeedbackRow(wrap);
              renderedCount++;
            }
          });

          if (renderedCount === 0) {
            vp.innerHTML = `
              <div class="msg-assistant-container">
                <div class="assistant-prose-card">👋 该任务会话暂无消息，请在下方输入开始交流。</div>
              </div>
            `;
          }
        } else {
          vp.innerHTML = `
            <div class="msg-assistant-container">
              <div class="assistant-prose-card">👋 该任务会话暂无消息，请在下方输入开始交流。</div>
            </div>
          `;
        }
        vp.scrollTop = vp.scrollHeight;
      } catch(e) {
        vp.innerHTML = `<div class="msg-assistant-container"><div class="assistant-prose-card">❌ 加载会话记录失败: ${e.message}</div></div>`;
      }
    }

    function appendUserBubble(text) {
      const vp = document.getElementById("chat-viewport");
      const row = document.createElement("div");
      row.className = "msg-user-container";
      row.innerHTML = `<div class="user-bubble">${formatCodeBlocks(text)}</div>`;
      vp.appendChild(row);
      vp.scrollTop = vp.scrollHeight;
    }

    function appendAssistantBox() {
      const vp = document.getElementById("chat-viewport");
      const wrap = document.createElement("div");
      wrap.className = "msg-assistant-container";
      vp.appendChild(wrap);
      vp.scrollTop = vp.scrollHeight;
      return wrap;
    }

    function addProseText(wrap, text) {
      let c = wrap.querySelector(".assistant-prose-card");
      if (!c) {
        c = document.createElement("div");
        c.className = "assistant-prose-card";
        wrap.appendChild(c);
      }
      c.innerHTML = formatCodeBlocks(text);
      const vp = document.getElementById("chat-viewport");
      vp.scrollTop = vp.scrollHeight;
      return c;
    }

    function addThinking(wrap, text) {
      let box = wrap.querySelector(".thinking-box");
      if (!box) {
        box = document.createElement("div");
        box.className = "thinking-box";
        box.innerHTML = `
          <div class="thinking-toggle" onclick="this.parentElement.classList.toggle('open')">
            <span>💭 思考过程 (Thinking)</span>
            <span>▾</span>
          </div>
          <div class="thinking-content"></div>
        `;
        wrap.appendChild(box);
      }
      box.querySelector(".thinking-content").textContent = text;
    }

    function addToolCard(wrap, callId, tool, status, inputData, outputData) {
      let card = activeToolsMap[callId];
      if (!card) {
        card = document.createElement("div");
        card.className = "mimo-tool-card";
        const desc = inputData?.command || inputData?.path || inputData?.description || JSON.stringify(inputData || {});
        card.innerHTML = `
          <div class="tool-header-row" onclick="const b=this.parentElement.querySelector('.tool-console-box');if(b)b.style.display=b.style.display==='none'?'block':'none'">
            <div style="display:flex;align-items:center;min-width:0;">
              <span class="tool-badge">${(tool || "TOOL").toUpperCase()}</span>
              <span class="tool-cmd-preview">${desc}</span>
            </div>
            <div class="tool-status ${status || 'running'}">
              <span>●</span> <span class="st-text">${status || 'running'}</span>
            </div>
          </div>
          <div class="tool-console-box" style="display:${outputData ? 'block' : 'none'};"></div>
        `;
        wrap.appendChild(card);
        activeToolsMap[callId] = card;
      }

      const stEl = card.querySelector(".tool-status");
      stEl.className = "tool-status " + (status || "running");
      card.querySelector(".st-text").textContent = status || "running";

      if (outputData) {
        const consoleBox = card.querySelector(".tool-console-box");
        consoleBox.textContent = outputData;
        consoleBox.style.display = "block";
      }
      const vp = document.getElementById("chat-viewport");
      vp.scrollTop = vp.scrollHeight;
    }

    function appendFeedbackRow(wrap) {
      if (wrap.querySelector(".assistant-feedback-row")) return;
      const row = document.createElement("div");
      row.className = "assistant-feedback-row";
      row.innerHTML = `
        <button class="btn-feedback-action" title="复制此回答" onclick="copyAssistantMessage(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>复制全文</span>
        </button>
      `;
      wrap.appendChild(row);
    }

    function startBusyPolling(sid) {
      if (busyPollTimer) clearInterval(busyPollTimer);
      busyPollTimer = setInterval(async () => {
        if (!isBusy) {
          clearInterval(busyPollTimer);
          busyPollTimer = null;
          return;
        }
        try {
          const r = await fetch("/api/messages?session_id=" + sid);
          const msgs = await r.json();
          if (Array.isArray(msgs) && msgs.length > 0) {
            const last = msgs[msgs.length - 1];
            if (last.info?.role === "assistant") {
              const parts = last.parts || [];
              if (!activeAssistantBox) activeAssistantBox = appendAssistantBox();

              parts.forEach(p => {
                if (p.type === "reasoning" && p.text) {
                  addThinking(activeAssistantBox, p.text);
                } else if (p.type === "tool") {
                  const out = p.state?.output || p.state?.metadata?.output || "";
                  addToolCard(activeAssistantBox, p.callID, p.tool, p.state?.status, p.state?.input, out);
                } else if (p.type === "text" && p.text) {
                  activeProseCard = addProseText(activeAssistantBox, p.text);
                }
              });

              const isCompleted = !!last.info?.time?.completed;
              const hasRunningTool = parts.some(p => p.type === "tool" && p.state?.status === "running");
              if (isCompleted || (!hasRunningTool && parts.some(p => p.type === "text" && p.text))) {
                setBusy(false);
                appendFeedbackRow(activeAssistantBox);
                if (busyPollTimer) {
                  clearInterval(busyPollTimer);
                  busyPollTimer = null;
                }
                await loadSessionsList();
              }
            }
          }
        } catch (e) {}
      }, 1000);
    }

    async function sendPrompt() {
      const input = document.getElementById("dock-input");
      const text = input.value.trim();
      if (!text || isBusy) return;

      if (navigator.vibrate) navigator.vibrate(12);

      const topTitle = document.getElementById("top-session-title");
      if (topTitle && (topTitle.textContent === "新任务会话" || topTitle.textContent === "当前任务")) {
        topTitle.textContent = text.slice(0, 24);
      }

      appendUserBubble(text);
      input.value = "";
      input.style.height = "auto";
      setBusy(true);

      activeAssistantBox = appendAssistantBox();
      activeProseCard = addProseText(activeAssistantBox, "正在调度执行...");

      startBusyPolling(currentSessionId);

      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, session_id: currentSessionId, model: selectedModelId })
        });
        const res = await r.json();
        if (!r.ok) {
          activeProseCard.innerHTML = "❌ 调度出错: " + (res.error || "未知错误");
          setBusy(false);
        }
      } catch (e) {
        activeProseCard.innerHTML = "❌ 请求失败: " + e.message;
        setBusy(false);
      }
    }

    function setBusy(busy) {
      isBusy = busy;
      const btn = document.getElementById("btn-dock-send");
      if (busy) {
        btn.classList.add("abort");
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
        btn.onclick = abortTask;
      } else {
        btn.classList.remove("abort");
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>';
        btn.onclick = sendPrompt;
      }
    }

    async function abortTask() {
      try {
        await fetch("/api/abort", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: currentSessionId })
        });
        if (activeProseCard) activeProseCard.innerHTML += "<br><em>[已发送 Abort 中止信号]</em>";
      } catch (e) {}
      setBusy(false);
    }

    function connectSessionSSE(sid) {
      if (activeSseSource) activeSseSource.close();
      activeSseSource = new EventSource("/api/events?session_id=" + sid);

      const handleEvt = function(e) {
        try {
          const ev = JSON.parse(e.data);
          const type = ev.type || e.type;

          if (type === "text-partial" && ev.text) {
            if (!activeAssistantBox) activeAssistantBox = appendAssistantBox();
            activeProseCard = addProseText(activeAssistantBox, ev.text);
          } else if (type === "ui" && ev.ui) {
            if (!activeAssistantBox) activeAssistantBox = appendAssistantBox();
            if (ev.ui.kind === "text" && ev.ui.text) {
              activeProseCard = addProseText(activeAssistantBox, ev.ui.text);
            }
          } else if (type === "idle" || type === "closed" || type === "session.idle") {
            setBusy(false);
            loadHistoricalMessages(sid, false);
            loadSessionsList();
          }
        } catch(err) {}
      };

      activeSseSource.onmessage = handleEvt;
      activeSseSource.addEventListener("text-partial", handleEvt);
      activeSseSource.addEventListener("ui", handleEvt);
      activeSseSource.addEventListener("idle", handleEvt);
      activeSseSource.addEventListener("closed", handleEvt);
    }

    async function initApp() {
      // 1. 并行同步用户资料、模型配置与会话列表
      loadUserProfile();
      loadModelConfig();
      loadSessionsList();

      // 2. 安全超时兜底：若 3.5 秒内未同步成功，自动解除加载状态，防止卡死
      const safetyTimer = setTimeout(() => {
        const loader = document.getElementById("init-loader");
        if (loader) {
          loader.innerHTML = '<div class="assistant-prose-card">👋 已连接电脑端 MiMo，请在下方输入描述任务，或点击左上角查看历史会话。</div>';
        }
      }, 3500);

      // 3. 同步电脑端当前活跃任务与历史记录
      try {
        const r = await fetch("/api/active_session");
        const act = await r.json();
        clearTimeout(safetyTimer);
        if (act && act.id) {
          currentSessionId = act.id;
          document.getElementById("top-session-title").textContent = act.title || "当前任务";
          await loadHistoricalMessages(act.id, false);
          connectSessionSSE(act.id);
        } else {
          const vp = document.getElementById("chat-viewport");
          if (vp) {
            vp.innerHTML = '<div class="msg-assistant-container"><div class="assistant-prose-card">👋 你好！我是 Xiaomi MiMo，请在下方描述你想要执行的编码或系统任务...</div></div>';
          }
        }
      } catch (e) {
        clearTimeout(safetyTimer);
        const vp = document.getElementById("chat-viewport");
        if (vp) {
          vp.innerHTML = `<div class="msg-assistant-container"><div class="assistant-prose-card">❌ 连接电脑端服务异常: ${e.message}</div></div>`;
        }
      }
    }

    // 兼容所有浏览器环境，即使 DOMContentLoaded 早已触发也能即时启动
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initApp);
    } else {
      initApp();
    }
  </script>
</body>
</html>
"""


class XiaomiMiMoPwaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, code: int, data: Any):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. 前端页面
        if path in ("/", "/index.html"):
            ts_dns, _ = get_tailscale_info()
            host_header = self.headers.get("Host", "127.0.0.1").split(":")[0]
            target_host = ts_dns if ts_dns else host_header
            ts_pwa_url = f"https://{target_host}:8443/"
            body = XIAOMI_MIMO_PWA_HTML.replace("__TS_PWA_URL__", ts_pwa_url).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 2. PWA Manifest
        elif path in ("/manifest.json", "/site.webmanifest"):
            body = PWA_MANIFEST_JSON.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 3. PWA Service Worker
        elif path == "/sw.js":
            body = PWA_SERVICE_WORKER_JS.strip().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Service-Worker-Allowed", "/")
            self.end_headers()
            self.wfile.write(body)
            return

        # 4. 图标 (多尺寸 SVG / PNG PWA & Apple-Touch-Icon 兼容)
        elif path in ("/icons/icon-192.svg", "/icons/icon-512.svg"):
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(ICON_SVG)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(ICON_SVG)
            return

        elif path in ("/icons/icon-192.png", "/icons/apple-touch-icon.png", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png", "/favicon.ico"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(ICON_192_PNG)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(ICON_192_PNG)
            return

        elif path == "/icons/icon-512.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(ICON_512_PNG)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(ICON_512_PNG)
            return

        # 5. 客户端真实用户头像
        elif path == "/icons/avatar.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(USER_AVATAR_PNG)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(USER_AVATAR_PNG)
            return

        # 6. 用户信息 API
        elif path == "/api/user":
            self.send_json(200, get_user_profile())
            return

        # 7. 真实模型配置 API (读取 preferences.json 真实生效配置)
        elif path == "/api/model":
            cur = get_current_model()
            models_info = [
                {
                    "id": "mimo-auto",
                    "name": "MiMo Auto",
                    "badge": "官方默认",
                    "desc": "官方智能调度 · 依据任务难易度自动在 Flash 与 Pro 间动态路由",
                },
                {
                    "id": "mimo-pro",
                    "name": "MiMo Pro",
                    "badge": "自研旗舰",
                    "desc": "自研旗舰架构 (MiMo-X-Pro) · 深度编程、复杂架构与工具调度",
                },
                {
                    "id": "mimo-flash",
                    "name": "MiMo Flash",
                    "badge": "轻量极速",
                    "desc": "轻量极速架构 (MiMo-X-Flash) · 毫秒级低延迟交互响应",
                },
            ]
            self.send_json(200, {"current": cur, "models": models_info})
            return

        # 7. 获取电脑当前正在焦点的最新会话
        elif path == "/api/active_session":
            act_id = get_desktop_current_session_id()
            title = "最新会话"
            if act_id and os.path.exists(MIMO_DB_PATH):
                try:
                    conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
                    c = conn.cursor()
                    c.execute("SELECT title, directory FROM session WHERE id = ?", (act_id,))
                    row = c.fetchone()
                    conn.close()
                    if row:
                        title = row[0] or title
                except Exception:
                    pass
            self.send_json(200, {"id": act_id, "title": title})
            return

        # 8. 会话列表 (按更新时间倒序排序，过滤掉内部中间态会话)
        elif path == "/api/sessions":
            if os.path.exists(MIMO_DB_PATH):
                try:
                    conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
                    c = conn.cursor()
                    c.execute(
                        """
                        SELECT id, title, directory, time_created, time_updated 
                        FROM session 
                        WHERE title NOT LIKE 'checkpoint-writer%' 
                          AND title NOT IN ('Auto Dream', 'Auto Distill', 'Title request')
                        ORDER BY time_updated DESC LIMIT 80
                        """
                    )
                    rows = c.fetchall()
                    conn.close()
                    list_data = [
                        {
                            "id": r[0],
                            "title": r[1] or "未命名任务",
                            "directory": r[2] or os.path.expanduser("~"),
                            "time": {"created": r[3], "updated": r[4]},
                        }
                        for r in rows
                    ]
                    self.send_json(200, list_data)
                    return
                except Exception:
                    pass

            code, data = call_mimo_v1("sessions?limit=100")
            self.send_json(code, data)
            return

        # 9. 历史消息列表
        elif path == "/api/messages":
            sid = query.get("session_id", [None])[0]
            if not sid:
                self.send_json(400, {"error": "缺少 session_id 参数"})
                return
            code, data = call_mimo_v1(f"sessions/{sid}/messages")
            self.send_json(code, data)
            return

        # 10. SSE 事件透传
        elif path == "/api/events":
            sid = query.get("session_id", [None])[0]
            if not sid:
                self.send_json(400, {"error": "缺少 session_id 参数"})
                return

            port, token = load_desktop_api_credentials()
            if not port or not token:
                self.send_json(503, {"error": "MiMo 引擎未运行"})
                return

            url = f"http://127.0.0.1:{port}/v1/sessions/{sid}/events"
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}", "User-Agent": "Xiaomi-MiMo-PWA-Client"},
            )
            try:
                upstream = urllib.request.urlopen(req, timeout=3600)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                for raw_line in upstream:
                    self.wfile.write(raw_line)
                    self.wfile.flush()
            except Exception:
                pass
            return

        self.send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            payload = {}

        # 1. 新建会话
        if path in ("/api/sessions/create", "/api/sessions"):
            title = payload.get("title", "新任务会话")
            sess = create_new_mimo_session_in_db(title=title)
            self.send_json(200, sess)
            return

        # 2. 发送任务消息 (携带真实 model 参数 & 完全访问权限自动批准 & 工作目录)
        elif path == "/api/chat":
            msg = payload.get("message", "").strip()
            sid = payload.get("session_id")
            model = payload.get("model") or get_current_model()
            if model not in ("mimo-auto", "mimo-pro", "mimo-flash"):
                model = "mimo-auto"

            if not msg or not sid:
                self.send_json(400, {"error": "缺少 message 或 session_id"})
                return

            # 如果该会话标题是默认名，自动用第一句提示词命名
            if os.path.exists(MIMO_DB_PATH):
                try:
                    conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
                    c = conn.cursor()
                    c.execute("SELECT title FROM session WHERE id = ?", (sid,))
                    row = c.fetchone()
                    if row and (not row[0] or row[0] in ("新任务会话", "新建任务会话", "未命名任务")):
                        new_title = msg.replace("\n", " ")[:32].strip()
                        c.execute("UPDATE session SET title = ? WHERE id = ?", (new_title, sid))
                        conn.commit()
                    conn.close()
                except Exception:
                    pass

            code, res = call_mimo_v1(
                f"sessions/{sid}/turns",
                method="POST",
                body={
                    "message": msg,
                    "model": model,
                    "perm": "完全访问权限",
                    "dir": os.path.expanduser("~"),
                },
            )
            self.send_json(code, res)
            return

        # 3. 真实模型切换与 preferences.json 同步持久化
        elif path == "/api/model":
            target = payload.get("model", "mimo-auto").strip()
            if target in ("mimo-auto", "mimo-pro", "mimo-flash"):
                ok = set_current_model(target)
                self.send_json(200, {"ok": ok, "current": target})
            else:
                self.send_json(400, {"error": "不支持的模型 ID"})
            return

        # 4. 中止当前任务
        elif path == "/api/abort":
            sid = payload.get("session_id")
            code, res = call_mimo_v1(f"sessions/{sid}/abort", method="POST", body={})
            self.send_json(code, res)
            return

        self.send_json(404, {"error": "Not Found"})


def start_pwa_server(port: int = DEFAULT_GATEWAY_PORT):
    desktop_port, _ = load_desktop_api_credentials()
    tailscale_dns, tailscale_ip = get_tailscale_info()
    lan_ip = get_local_lan_ip()
    active_sid = get_desktop_current_session_id()
    user = get_user_profile()

    print("================================================================")
    print("🚀 Xiaomi MiMo Desktop 官方极简原质 PWA 网关 (v6.1.0)")
    print("================================================================")
    if desktop_port:
        print(f"✅ 成功连接电脑端 Xiaomi MiMo 核心引擎 (端口: {desktop_port})")
        print(f"   已继承当前登录小米账号: {user.get('displayName')} (ID: {user.get('userId')})")
        print(f"   已自动锁定电脑当前操作会话: {active_sid}")
    else:
        print("⚠️ 警告: 未检测到 Xiaomi MiMo Desktop 运行凭据，请确保已打开电脑端 Xiaomi MiMo")

    print("\n----------------------------------------------------------------")
    print("📱 手机端访问与真 PWA 安装专属地址：")
    if tailscale_dns:
        print("   👉【真正原生 PWA 安装通道（HTTPS 安全证书，无浏览器框）】:")
        print(f"      https://{tailscale_dns}:8443")
    if tailscale_ip:
        print(f"\n   👉【Tailscale 远程直连（HTTP 备用通道）】:\n      http://{tailscale_ip}:{port}")
    print(f"\n   👉【同一 Wi-Fi 局域网访问】:\n      http://{lan_ip}:{port}")
    print(f"\n   👉【电脑本机测试】:\n      http://127.0.0.1:{port}")
    print("----------------------------------------------------------------\n")
    print(f"📡 网关监听中 0.0.0.0:{port} ... 按 Ctrl+C 退出。\n")

    server = ThreadingHTTPServer(("0.0.0.0", port), XiaomiMiMoPwaHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 网关正在安全停止...")
        server.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Xiaomi MiMo Desktop PWA Gateway")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help="Gateway listen port")
    args = parser.parse_args()
    start_pwa_server(args.port)
