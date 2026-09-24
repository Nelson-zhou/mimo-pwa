#!/usr/bin/env python3
"""
================================================================================
Xiaomi MiMo Desktop 官方极简原质 PWA 网关 (v6.0.0)
================================================================================
深度继承与还原 Xiaomi MiMo Desktop 官方界面色调与品牌特征：
- 1:1 官方明亮色调 (#FFFFFF / #F8F9FA) 与极简设计语言
- 继承官方 Logo: [Xiaomi MIMO Beta]
- 动态继承客户端登录用户头像与昵称
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
import traceback
import base64
import tempfile
import shutil
import uuid
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
import zlib

DEFAULT_GATEWAY_PORT = 8080


def _resolve_mimo_data_dir() -> str:
    """按平台定位 Xiaomi MiMo Desktop 用户数据目录。"""
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Library", "Application Support", "Xiaomi MiMo"),
        os.path.join(home, ".config", "XiaomiMiMoDesktop"),
        os.path.join(home, ".config", "Xiaomi MiMo"),
        os.path.join(home, ".config", "Electron"),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "desktop-api.json")):
            return path
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[0]


MIMO_DATA_DIR = _resolve_mimo_data_dir()
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP_API_JSON_PATH = os.path.join(MIMO_DATA_DIR, "desktop-api.json")
MIMO_DB_PATH = os.path.expanduser("~/.local/share/mimocode/mimocode.db")
COMPOSER_INPUT_PATH = os.path.join(MIMO_DATA_DIR, "composer-input.json")
XIAOMI_CONFIRMED_PATH = os.path.join(MIMO_DATA_DIR, "xiaomi-last-confirmed.json")
PREFERENCES_PATH = os.path.join(MIMO_DATA_DIR, "preferences.json")
AVATAR_PNG_PATH = os.path.join(_SCRIPT_DIR, "assets", "avatar_default.png")
_AVATAR_DIR_CANDIDATES = [
    os.path.join(_SCRIPT_DIR, "assets", "avatars"),
    os.path.join(_SCRIPT_DIR, "mimo-pwa", "assets", "avatars"),
]
AVATAR_ASSETS_DIR = next((p for p in _AVATAR_DIR_CANDIDATES if os.path.isdir(p)), _AVATAR_DIR_CANDIDATES[0])
LEVELDB_DIR = os.path.join(MIMO_DATA_DIR, "Local Storage", "leveldb")
HOME_DIR = os.path.expanduser("~")
DEFAULT_WORKDIR = HOME_DIR
DEFAULT_TAILSCALE_HTTPS_PORT = 8443
GATEWAY_LISTEN_PORT: Optional[int] = None
def delete_mimo_session(sid: str) -> bool:
    """从本地 SQLite 数据库及 MiMo Desktop 中删除指定会话。"""
    success = False
    if os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=5)
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")
            c.execute("DELETE FROM session WHERE id = ?", (sid,))
            conn.commit()
            conn.close()
            success = True
        except Exception:
            pass
    try:
        port, token = load_desktop_api_credentials()
        if port and token:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/sessions/{sid}",
                headers={"Authorization": f"Bearer {token}"},
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=3)
            success = True
    except Exception:
        pass
    return success


# avatar-id → filename mapping (from app.asar decompile)
AVATAR_FILE_MAP = {
    "avatar-1": "avatar-1-B6KwUrRj.png",
    "avatar-2": "avatar-2-w0iv7mdV.png",
    "avatar-3": "avatar-3-DV2ldWBE.png",
    "avatar-4": "avatar-4-i1E2Uex3.png",
    "avatar-5": "avatar-5-DZ-nyoXt.png",
}


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


# ── 模型注册表与规范映射体系 (Model Mapping Registry) ──────────────────────────

MODEL_CATALOG_PATH = os.path.join(MIMO_DATA_DIR, "model-catalog.json")
MODELS_WITH_CLAUDE_PATH = os.path.join(MIMO_DATA_DIR, "models-with-claude.json")

# 官方与拓展基础模型注册字典
DEFAULT_MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "mimo-auto": {
        "id": "mimo-auto",
        "canonicalId": "mimo-auto",
        "provider": "mimo",
        "providerName": "小米自研",
        "category": "official",
        "name": "MiMo Auto",
        "shortName": "Auto",
        "badge": "官方默认 · 免费",
        "badgeClass": "badge-blue",
        "contextWindow": "1,000,000 (1M)",
        "ratio": "免费调度",
        "desc": "官方智能调度引擎 · 根据任务复杂度在 Flash 与 Pro 之间自适应无缝路由",
        "capabilities": ["自适应路由", "1M 上下文", "工具调用", "多模态"],
        "icon": "🤖",
        "color": "#FF6900",
    },
    "mimo-v2.6-pro": {
        "id": "mimo-v2.6-pro",
        "canonicalId": "mimo-v2.6-pro",
        "provider": "xiaomi",
        "providerName": "小米自研",
        "category": "official",
        "name": "MiMo V2.6 Pro",
        "shortName": "Pro",
        "badge": "自研旗舰 · 1.0x",
        "badgeClass": "badge-orange",
        "contextWindow": "1,000,000 (1M)",
        "ratio": "1.0x 算力",
        "desc": "自研旗舰高精度模型 · 专为深度代码重构、复杂工程架构设计与全能工具调用打造",
        "capabilities": ["深度代码重构", "复杂系统架构", "高精度推理", "全能工具链"],
        "icon": "💎",
        "color": "#FF6900",
    },
    "mimo-v2.6-flash": {
        "id": "mimo-v2.6-flash",
        "canonicalId": "mimo-v2.6-flash",
        "provider": "xiaomi",
        "providerName": "小米自研",
        "category": "official",
        "name": "MiMo V2.6 Flash",
        "shortName": "Flash",
        "badge": "轻量极速 · 0.4x",
        "badgeClass": "badge-cyan",
        "contextWindow": "1,000,000 (1M)",
        "ratio": "0.4x 算力",
        "desc": "自研轻量高吞吐模型 · 毫秒级首字极速响应，适合敏捷修改、代码阅读与快速指令",
        "capabilities": ["毫秒级响应", "0.4x 低消耗", "敏捷交互", "轻量代码编写"],
        "icon": "⚡",
        "color": "#0284C7",
    },
    "claude-sonnet-4-6": {
        "id": "claude-sonnet-4-6",
        "canonicalId": "claude-sonnet-4-6",
        "provider": "anthropic",
        "providerName": "Anthropic",
        "category": "extended",
        "name": "Claude Sonnet 4.6",
        "shortName": "Sonnet",
        "badge": "编码主力 · 1M",
        "badgeClass": "badge-purple",
        "contextWindow": "1,000,000 (1M)",
        "ratio": "高端算力",
        "desc": "业界标杆级代码与严密逻辑分析模型 · 超长上下文连续自主决策 Agent 工作流",
        "capabilities": ["标杆级代码能力", "自主 Agent 循环", "超长上下文", "精密设计"],
        "icon": "🧠",
        "color": "#7C3AED",
    },
    "deepseek-v4-pro": {
        "id": "deepseek-v4-pro",
        "canonicalId": "deepseek-v4-pro",
        "provider": "anthropic",
        "providerName": "DeepSeek",
        "category": "extended",
        "name": "DeepSeek V4 Pro",
        "shortName": "DeepSeek",
        "badge": "开源旗舰 · 推理",
        "badgeClass": "badge-blue",
        "contextWindow": "1,000,000 (1M)",
        "ratio": "深度思考",
        "desc": "超大 MoE 架构深度推理模型 · 具备强悍的数学推导、长程算法推演与代码生成力",
        "capabilities": ["深度思考推理", "算法推演", "MoE 架构", "全链路工具调用"],
        "icon": "🐋",
        "color": "#2563EB",
    },
}

# 别名映射字典（无论客户端或数据库传入何种历史名称，统一映射归一）
MODEL_ALIAS_MAP: Dict[str, str] = {
    # Pro 系列
    "mimo-pro": "mimo-v2.6-pro",
    "mimo-x-pro-preview": "mimo-v2.6-pro",
    "mimo-x-pro": "mimo-v2.6-pro",
    "xiaomi/mimo-v2.6-pro": "mimo-v2.6-pro",
    "xiaomi/mimo-x-pro-preview": "mimo-v2.6-pro",
    "mimo/mimo-v2.6-pro": "mimo-v2.6-pro",
    "mimo/mimo-x-pro-preview": "mimo-v2.6-pro",
    "mimo-v2.5-pro-ultraspeed": "mimo-v2.6-pro",
    "mimo-v2.6-pro-ultraspeed": "mimo-v2.6-pro",
    # Flash 系列
    "mimo-flash": "mimo-v2.6-flash",
    "mimo-x-flash-preview": "mimo-v2.6-flash",
    "mimo-x-flash": "mimo-v2.6-flash",
    "xiaomi/mimo-v2.6-flash": "mimo-v2.6-flash",
    "xiaomi/mimo-x-flash-preview": "mimo-v2.6-flash",
    "mimo/mimo-v2.6-flash": "mimo-v2.6-flash",
    "mimo/mimo-x-flash-preview": "mimo-v2.6-flash",
    # Auto 系列
    "mimo-auto": "mimo-auto",
    "mimo/mimo-auto": "mimo-auto",
    "xiaomi/mimo-auto": "mimo-auto",
    # Claude 系列
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet": "claude-sonnet-4-6",
    "sonnet-4-6": "claude-sonnet-4-6",
    # DeepSeek 系列
    "deepseek-v4-pro": "deepseek-v4-pro",
    "anthropic/deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek": "deepseek-v4-pro",
}


def resolve_canonical_model(raw_id: Optional[str]) -> str:
    """将任意来源的模型 ID（包括前缀、后缀、历史缩写）归一化为标准的注册表 ID"""
    if not raw_id:
        return "mimo-auto"
    clean_id = str(raw_id).strip()
    if clean_id in MODEL_ALIAS_MAP:
        return MODEL_ALIAS_MAP[clean_id]

    # 尝试去除 provider 前缀再次匹配
    if "/" in clean_id:
        short = clean_id.split("/", 1)[1]
        if short in MODEL_ALIAS_MAP:
            return MODEL_ALIAS_MAP[short]
        if short in DEFAULT_MODEL_REGISTRY:
            return short

    if clean_id in DEFAULT_MODEL_REGISTRY:
        return clean_id

    # 模糊兜底映射
    lower = clean_id.lower()
    if "pro" in lower and ("mimo" in lower or "xiaomi" in lower):
        return "mimo-v2.6-pro"
    if "flash" in lower and ("mimo" in lower or "xiaomi" in lower):
        return "mimo-v2.6-flash"
    if "claude" in lower or "sonnet" in lower:
        return "claude-sonnet-4-6"
    if "deepseek" in lower:
        return "deepseek-v4-pro"
    if "auto" in lower:
        return "mimo-auto"

    return clean_id


def get_model_info(model_id: str) -> Dict[str, Any]:
    """获取指定模型 ID 的完整展示与配置元数据（带映射解析）"""
    canonical_id = resolve_canonical_model(model_id)
    if canonical_id in DEFAULT_MODEL_REGISTRY:
        return dict(DEFAULT_MODEL_REGISTRY[canonical_id])

    # 未知/自定义扩展模型动态构造
    return {
        "id": canonical_id,
        "canonicalId": canonical_id,
        "provider": "custom",
        "providerName": "自定义拓展",
        "category": "extended",
        "name": canonical_id,
        "shortName": canonical_id.split("/")[-1][:10],
        "badge": "拓展模型",
        "badgeClass": "badge-gray",
        "contextWindow": "自适应",
        "ratio": "自定义",
        "desc": f"已配置拓展模型: {canonical_id}",
        "capabilities": ["模型推理能力", "上下文支持"],
        "icon": "🧩",
        "color": "#6B7280",
    }


def get_available_models() -> List[Dict[str, Any]]:
    """动态获取当前系统所有可用模型（聚合注册表、model-catalog.json 与本地会话历史）"""
    models_dict = dict(DEFAULT_MODEL_REGISTRY)

    # 1. 动态探测 model-catalog.json
    if os.path.exists(MODEL_CATALOG_PATH):
        try:
            with open(MODEL_CATALOG_PATH, "r", encoding="utf-8") as f:
                cat = json.load(f)
            for m in cat.get("models", []):
                mid = m.get("id")
                mtype = m.get("modelType")
                if mtype and mtype != "TEXT":
                    continue
                if mid:
                    canon = resolve_canonical_model(mid)
                    if canon not in models_dict:
                        models_dict[canon] = {
                            "id": canon,
                            "canonicalId": canon,
                            "provider": "xiaomi",
                            "providerName": "小米自研",
                            "category": "official",
                            "name": m.get("name") or canon,
                            "shortName": (m.get("name") or canon).replace("MiMo ", "").strip(),
                            "badge": f"自研 · {m.get('displayRatio', 1.0)}x",
                            "badgeClass": "badge-orange",
                            "contextWindow": "1,000,000 (1M)",
                            "ratio": f"{m.get('displayRatio', 1.0)}x 算力",
                            "desc": f"小米官方云端服务目录模型 ({canon})",
                            "capabilities": ["官方模型服务", "1M 上下文", "工具调用"],
                            "icon": "🤖",
                            "color": "#FF6900",
                        }
        except Exception:
            pass

    # 2. 动态探测历史使用模型（从 mimocode.db 最近消息提取）
    if os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
            c = conn.cursor()
            c.execute("SELECT data FROM message WHERE data LIKE '%modelID%' ORDER BY time_created DESC LIMIT 150;")
            for (data_str,) in c.fetchall():
                try:
                    d = json.loads(data_str)
                    mid = d.get("modelID")
                    if mid:
                        canon = resolve_canonical_model(mid)
                        if canon not in models_dict:
                            models_dict[canon] = get_model_info(canon)
                except Exception:
                    pass
            conn.close()
        except Exception:
            pass

    # 排序：官方自研在前（Auto -> Pro -> Flash），拓展模型在后
    order_weights = {
        "mimo-auto": 0,
        "mimo-v2.6-pro": 1,
        "mimo-v2.6-flash": 2,
        "claude-sonnet-4-6": 10,
        "deepseek-v4-pro": 11,
    }
    result = list(models_dict.values())
    result.sort(key=lambda m: (order_weights.get(m["canonicalId"], 99), m["canonicalId"]))
    return result


def get_session_model(session_id: Optional[str] = None) -> Dict[str, Any]:
    """读取指定会话当前生效的模型配置（优先会话内消息绑定的模型，其次 fallback 到全局默认模型）"""
    if session_id and os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
            c = conn.cursor()
            c.execute("""
                SELECT data FROM message 
                WHERE session_id = ? 
                ORDER BY time_created DESC 
                LIMIT 20;
            """, (session_id,))
            rows = c.fetchall()
            conn.close()
            for (data_raw,) in rows:
                try:
                    d = json.loads(data_raw)
                    # 1. 助手消息 modelID
                    if d.get("modelID"):
                        return get_model_info(d.get("modelID"))
                    # 2. 用户消息 model dict
                    if isinstance(d.get("model"), dict) and d.get("model").get("modelID"):
                        return get_model_info(d.get("model").get("modelID"))
                    # 3. 用户消息字符串 model
                    if isinstance(d.get("model"), str) and d.get("model"):
                        return get_model_info(d.get("model"))
                except Exception:
                    pass
        except Exception:
            pass

    # 无会话消息或新会话，读取 preferences.json 全局默认
    global_model = get_current_model()
    return get_model_info(global_model)


def get_current_model() -> str:
    """真实读取当前在 preferences.json 中保存的全局默认模型并返回规范 ID"""
    if os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
                m = p.get("model", "mimo/mimo-auto")
                return resolve_canonical_model(m)
        except Exception:
            pass
    return "mimo-auto"


def set_current_model(model_id: str, session_id: Optional[str] = None, set_global: bool = True) -> bool:
    """更新模型配置：支持持久化至 preferences.json 全局配置，并记录会话模型映射"""
    canonical_id = resolve_canonical_model(model_id)
    if not canonical_id:
        return False

    success = True
    if set_global and os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
            # 保持对官方 preferences.json 格式的兼容（部分版本带 mimo/ 前缀，部分无前缀）
            if canonical_id.startswith("mimo-"):
                p["model"] = f"mimo/{canonical_id}"
            else:
                p["model"] = canonical_id
            with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
                json.dump(p, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Error updating preferences.json model:", e)
            success = False

    return success



UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "mimo-uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR, exist_ok=True)

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def get_current_perm() -> str:
    """读取当前在 preferences.json 中保存的权限配置"""
    if os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
                return p.get("perm", "完全访问权限")
        except Exception:
            pass
    return "完全访问权限"


def set_current_perm(perm_value: str, session_id: Optional[str] = None) -> bool:
    """修改 preferences.json 中的权限并持久化到本地桌面应用配置中，同时直接同步至 mimocode.db 的 session.permission 规则"""
    if perm_value not in ("完全访问权限", "帮我审批", "默认权限"):
        return False

    # 1. 持久化到 preferences.json
    if os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["perm"] = perm_value
            if session_id:
                if "permByConvo" not in p or not isinstance(p["permByConvo"], dict):
                    p["permByConvo"] = {}
                p["permByConvo"][session_id] = perm_value
            with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
                json.dump(p, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Error updating preferences.json perm:", e)

    # 2. 同步更新 SQLite mimocode.db 的 session.permission 规则
    if os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=5)
            c = conn.cursor()
            rules = None
            if perm_value == "完全访问权限":
                rules = json.dumps([{"permission": "*", "pattern": "*", "action": "allow"}])
            elif perm_value == "帮我审批":
                rules = json.dumps([{"permission": "edit", "pattern": "*", "action": "allow"}])
            if session_id:
                c.execute("UPDATE session SET permission = ? WHERE id = ?", (rules, session_id))
            else:
                c.execute("UPDATE session SET permission = ?", (rules,))
            conn.commit()
            conn.close()
        except Exception as e:
            print("Error updating mimocode.db session permission:", e)
    return True



def categorize_artifact(ext: str) -> Tuple[str, str]:
    """根据后缀返回分类 (doc, app, other) 与徽章名称"""
    if ext in (".docx", ".doc"):
        return "doc", "Word"
    elif ext in (".pptx", ".ppt"):
        return "doc", "PPT"
    elif ext in (".xlsx", ".xls", ".csv"):
        return "doc", "Excel"
    elif ext == ".pdf":
        return "doc", "PDF"
    elif ext in (".txt", ".md", ".markdown"):
        return "doc", "文本"
    elif ext in (".html", ".htm"):
        return "app", "落地页"
    elif ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".json"):
        return "app", "代码应用"
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
        return "other", "图片"
    else:
        return "other", "文件"


def get_all_artifacts() -> list:
    """汇总检索 Xiaomi MiMo 在本地产生的所有产物 (SQLite present_files + XiaomiMiMoProjects)"""
    results = []
    seen_paths = set()

    # 1. 从 mimocode.db 的 present_files 工具调用中提取
    if os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=3)
            c = conn.cursor()
            c.execute(
                """
                SELECT p.session_id, s.title, p.time_created, p.data 
                FROM part p 
                LEFT JOIN session s ON p.session_id = s.id 
                WHERE p.data LIKE ? 
                ORDER BY p.time_created DESC LIMIT 100
                """,
                ("%\"tool\":\"present_files\"%",),
            )
            for sid, stitle, tcreate, data_str in c.fetchall():
                try:
                    data = json.loads(data_str)
                    inp = data.get("state", {}).get("input", {})
                    files = inp.get("files", [])
                    exp = inp.get("explanation", "")
                    for fp in files:
                        if not fp or fp in seen_paths:
                            continue
                        seen_paths.add(fp)
                        fname = os.path.basename(fp)
                        ext = os.path.splitext(fname)[1].lower()
                        cat, badge = categorize_artifact(ext)
                        exists = os.path.exists(fp)
                        size = os.path.getsize(fp) if exists else 0
                        results.append({
                            "path": fp,
                            "name": fname,
                            "title": exp or fname,
                            "ext": ext,
                            "category": cat,
                            "badge": badge,
                            "sessionId": sid or "",
                            "sessionTitle": stitle or "对话任务",
                            "timeCreated": tcreate,
                            "size": size,
                            "exists": exists,
                        })
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            print("Error query artifacts DB:", e)

    # 2. 扫描用户 XiaomiMiMoProjects 目录
    proj_dir = os.path.expanduser("~/XiaomiMiMoProjects")
    if os.path.exists(proj_dir):
        try:
            for root, _, files in os.walk(proj_dir):
                for f in files:
                    if f.startswith(".") or f.endswith((".DS_Store", ".tmp", ".log")):
                        continue
                    fp = os.path.join(root, f)
                    if fp not in seen_paths:
                        seen_paths.add(fp)
                        ext = os.path.splitext(f)[1].lower()
                        cat, badge = categorize_artifact(ext)
                        stat = os.stat(fp)
                        results.append({
                            "path": fp,
                            "name": f,
                            "title": f,
                            "ext": ext,
                            "category": cat,
                            "badge": badge,
                            "sessionId": "",
                            "sessionTitle": "本地产物项目",
                            "timeCreated": int(stat.st_mtime * 1000),
                            "size": stat.st_size,
                            "exists": True,
                        })
        except Exception as e:
            print("Error scan XiaomiMiMoProjects:", e)

    results.sort(key=lambda x: x.get("timeCreated", 0), reverse=True)
    return results


def format_token_lx(val: int) -> str:
    """1:1 还原客户端 Lx 缩写算法 (K / M 换算)"""
    if val >= 1_000_000:
        s = f"{val / 1_000_000:.1f}M"
        return s.replace(".0M", "M")
    elif val >= 1_000:
        s = f"{val / 1_000:.1f}K"
        return s.replace(".0K", "K")
    return str(val)


def get_model_context_limit(model_id: str) -> int:
    """获取指定模型的上下文窗口上限（单位：tokens）"""
    canon = resolve_canonical_model(model_id)
    if "claude" in canon:
        return 1_000_000 if "4-6" in canon else 200_000
    if "deepseek" in canon:
        return 1_000_000
    if "gemini" in canon:
        return 1_000_000
    return 1_000_000


def get_context_usage(session_id: Optional[str] = None) -> Dict[str, Any]:
    """1:1 深度对齐 Xiaomi MiMo 客户端 A0e / TD / b0e 算法读取真实 Token 消耗"""
    _default_limit = get_model_context_limit("mimo-auto")  # 1M
    if not os.path.exists(MIMO_DB_PATH):
        return {
            "ok": True,
            "total": 0,
            "total_fmt": "0",
            "limit": _default_limit,
            "limit_fmt": format_token_lx(_default_limit),
            "pct": 0,
            "remaining_pct": 100,
            "cache_hit": 0,
            "model": "mimo-auto",
        }
    try:
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
        cur = conn.cursor()
        # 若未显式传入 session_id，则无缝对齐电脑端当前激活的高亮会话
        target_sid = session_id or get_desktop_current_session_id()
        if target_sid:
            cur.execute(
                "SELECT data FROM message WHERE session_id = ? ORDER BY time_created DESC",
                (target_sid,)
            )
        else:
            cur.execute(
                "SELECT data FROM message ORDER BY time_created DESC LIMIT 60"
            )
        rows = cur.fetchall()
        conn.close()

        # 严格对齐客户端 A0e 回溯遍历过滤算法：
        # 倒序查找第一个有效结算（TD(r) > 0）的 assistant 轮次，自动跳过尚在流式或 0 token 的中间态消息
        found_tokens = None
        found_data = None
        for r in rows:
            try:
                d = json.loads(r[0])
                if d.get("role") != "assistant":
                    continue
                tok = d.get("tokens")
                if not tok or not isinstance(tok, dict):
                    continue
                inp = tok.get("input", 0) or 0
                outp = tok.get("output", 0) or 0
                cache = tok.get("cache", {}) or {}
                cache_read = cache.get("read", 0) or 0
                cache_write = cache.get("write", 0) or 0

                # 官方 TD 公式: (input||0) + (cacheRead||0) + (cacheWrite||0) + (output||0)
                calc_total = inp + cache_read + cache_write + outp
                if calc_total <= 0:
                    continue  # 忽略未结算或进行中的 0 token 消息，与官方 A0e 保持完全一致

                found_tokens = {
                    "total": calc_total,
                    "input": inp,
                    "output": outp,
                    "cache_read": cache_read,
                    "cache_write": cache_write,
                }
                found_data = d
                break
            except Exception:
                continue

        if not found_tokens:
            return {
                "ok": True,
                "total": 0,
                "total_fmt": "0",
                "limit": _default_limit,
                "limit_fmt": format_token_lx(_default_limit),
                "pct": 0,
                "remaining_pct": 100,
                "cache_hit": 0,
                "model": "mimo-auto",
            }

        total = found_tokens["total"]
        inp = found_tokens["input"]
        outp = found_tokens["output"]
        cache_read = found_tokens["cache_read"]
        cache_write = found_tokens["cache_write"]
        raw_mid = (found_data or {}).get("modelID") or (get_session_model(target_sid)["canonicalId"] if target_sid else get_current_model())
        model_id = resolve_canonical_model(raw_mid)
        model_info = get_model_info(model_id)

        limit = get_model_context_limit(model_id)

        # 官方 jD / x0e 百分比算法
        pct = round((total / limit) * 100, 1) if limit > 0 else 0
        remaining_pct = round(max(0.0, 100.0 - pct), 1)

        # 官方 b0e 缓存命中率算法：cacheRead / (cacheRead + cacheWrite + input)
        denom = cache_read + cache_write + inp
        cache_hit = round((cache_read / denom) * 100) if denom > 0 else 0

        return {
            "ok": True,
            "total": total,
            "total_fmt": format_token_lx(total),
            "model": model_info.get("name", model_id),
            "model_id": model_id,
            "model_info": model_info,
            "input": inp,
            "output": outp,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "limit": limit,
            "limit_fmt": format_token_lx(limit),
            "pct": pct,
            "remaining_pct": remaining_pct,
            "cache_hit": cache_hit,
            "model": model_id,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "total": 0,
            "total_fmt": "0",
            "limit": get_model_context_limit("mimo-auto"),
            "limit_fmt": format_token_lx(get_model_context_limit("mimo-auto")),
            "pct": 0,
            "remaining_pct": 100,
            "cache_hit": 0,
        }


def get_all_plugins() -> List[Dict[str, Any]]:
    """读取 Xiaomi MiMo 原生内置技能与插件及其启用状态"""
    skills_base = os.path.expanduser("~/.local/share/mimocode/builtin_skills")
    target_dir = None
    if os.path.exists(skills_base):
        for sub in sorted(os.listdir(skills_base), reverse=True):
            p = os.path.join(skills_base, sub, "skills")
            if os.path.isdir(p):
                target_dir = p
                break
    if not target_dir:
        target_dir = os.path.expanduser("~/.local/share/mimocode/builtin_skills/desktop-1d6a9fe/skills")

    ext_file = os.path.join(MIMO_DATA_DIR, "extensions.json")
    enabled_map = {}
    if os.path.exists(ext_file):
        try:
            with open(ext_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for ext in data.get("extensions", []):
                    enabled_map[ext.get("id")] = ext.get("enabled", True)
        except Exception:
            pass

    pref_file = PREFERENCES_PATH
    if os.path.exists(pref_file):
        try:
            with open(pref_file, "r", encoding="utf-8") as f:
                pref = json.load(f)
                if "computerUseEnabled" in pref:
                    enabled_map["computer-use"] = pref["computerUseEnabled"]
                if "browserUseEnabled" in pref:
                    enabled_map["mimo-browser-use"] = pref["browserUseEnabled"]
        except Exception:
            pass

    results = []
    if os.path.exists(target_dir):
        for name in sorted(os.listdir(target_dir)):
            skill_path = os.path.join(target_dir, name)
            if not os.path.isdir(skill_path):
                continue
            skill_md = os.path.join(skill_path, "SKILL.md")
            title = name
            desc = ""
            if os.path.exists(skill_md):
                try:
                    with open(skill_md, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        m = re.search(r"^---\s*(.*?)\s*---", content, re.DOTALL)
                        if m:
                            for line in m.group(1).splitlines():
                                if line.startswith("name:"):
                                    title = line.split("name:", 1)[1].strip().strip("\"'")
                                elif line.startswith("description:"):
                                    desc = line.split("description:", 1)[1].strip().strip("\"'")
                except Exception:
                    pass

            cat = "engineering"
            icon = "⚡"
            badge = "代码工程"
            if name in ("docx-official", "pptx-official", "xlsx-official", "pdf-official"):
                cat = "office"
                badge = "Office 办公"
                if "docx" in name: icon = "📄"
                elif "pptx" in name: icon = "📊"
                elif "xlsx" in name: icon = "📈"
                elif "pdf" in name: icon = "📑"
            elif "browser" in name or "computer" in name or "playwright" in name:
                cat = "automation"
                icon = "🤖"
                badge = "系统自动化"
            elif "research" in name or "paper" in name or "arxiv" in name or "data" in name:
                cat = "research"
                icon = "🔬"
                badge = "科研分析"
            elif "design" in name or "frontend" in name:
                cat = "design"
                icon = "🎨"
                badge = "交互设计"
            elif "code" in name or "python" in name or "evolve" in name or "loop" in name or "mate" in name:
                cat = "engineering"
                icon = "💻"
                badge = "代码工程"

            results.append({
                "id": name,
                "name": title,
                "desc": desc or f"Xiaomi MiMo 官方原生 {title} 专属技能扩展",
                "category": cat,
                "badge": badge,
                "icon": icon,
                "enabled": enabled_map.get(name, True)
            })
    return results


def set_plugin_enabled(plugin_id: str, enabled: bool) -> bool:
    """切换插件/技能的启用状态并同步持久化至 extensions.json 与 preferences.json"""
    ext_file = os.path.join(MIMO_DATA_DIR, "extensions.json")
    pref_file = PREFERENCES_PATH
    try:
        if os.path.exists(pref_file):
            try:
                with open(pref_file, "r", encoding="utf-8") as f:
                    pref = json.load(f)
                if plugin_id in ("computer-use", "MiMo-Computer-Use"):
                    pref["computerUseEnabled"] = bool(enabled)
                elif plugin_id in ("mimo-browser-use", "browser-replay", "MiMo-Browser-Use"):
                    pref["browserUseEnabled"] = bool(enabled)
                with open(pref_file, "w", encoding="utf-8") as f:
                    json.dump(pref, f, ensure_ascii=False, indent=2)
            except Exception as pe:
                print("Error updating preferences for plugin:", pe)

        data = {"schema": 1, "generation": 1, "extensions": []}
        if os.path.exists(ext_file):
            try:
                with open(ext_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        exts = data.get("extensions", [])
        found = False
        for e in exts:
            if e.get("id") == plugin_id:
                e["enabled"] = bool(enabled)
                found = True
                break
        if not found:
            exts.append({
                "id": plugin_id,
                "kind": "skill",
                "origin": "bundled",
                "enabled": bool(enabled),
                "authKeys": [],
                "placements": {
                    "skillDirs": [plugin_id],
                    "mcpKeys": [],
                    "secretKeys": [],
                    "stateKeys": [f"plugin:{plugin_id}", f"skill:{plugin_id}"],
                    "engineSkillNames": [plugin_id]
                },
                "installedAt": int(time.time() * 1000)
            })
        data["extensions"] = exts
        data["generation"] = data.get("generation", 1) + 1
        with open(ext_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("Error saving plugin state:", e)
        return False



def get_desktop_avatar_png() -> bytes:
    """从 LevelDB 读取 mimo.set.avatar 设置，返回对应官方头像 PNG 字节
    联动逻辑：与 app 端完全一致 —— 读 Local Storage leveldb 的 mimo.set.avatar key
    """
    avatar_id = "avatar-2"  # 默认值
    try:
        if os.path.exists(LEVELDB_DIR):
            for fname in os.listdir(LEVELDB_DIR):
                if not fname.endswith(".log") and not fname.endswith(".ldb"):
                    continue
                fpath = os.path.join(LEVELDB_DIR, fname)
                try:
                    with open(fpath, "rb") as f:
                        raw = f.read()
                    # 搜索 mimo.set.avatar 键值
                    marker = b"mimo.set.avatar"
                    idx = raw.rfind(marker)  # rfind 取最新写入的值
                    if idx != -1:
                        chunk = raw[idx: idx + 80]
                        import re as _re
                        m = _re.search(rb"avatar-([1-5])", chunk)
                        if m:
                            avatar_id = f"avatar-{m.group(1).decode()}"
                            break
                except Exception:
                    continue
    except Exception:
        pass

    fname = AVATAR_FILE_MAP.get(avatar_id, AVATAR_FILE_MAP["avatar-2"])
    fpath = os.path.join(AVATAR_ASSETS_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, "rb") as f:
            return f.read()

    # fallback: 旧的 avatar_circle.png
    if os.path.exists(AVATAR_PNG_PATH):
        with open(AVATAR_PNG_PATH, "rb") as f:
            return f.read()
    return b""


def get_weekly_usage() -> Dict[str, Any]:
    """统计最近7天每日 token 消耗（从 mimocode.db message 表）"""
    import datetime as _dt
    from collections import defaultdict as _dd

    now = time.time()
    week_ago_ms = int((now - 7 * 86400) * 1000)
    today_str = _dt.datetime.now().strftime("%m-%d")

    day_tokens: Dict[str, int] = _dd(int)
    day_turns: Dict[str, int] = _dd(int)
    total_week = 0
    total_today = 0
    today_ms = int(_dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

    if not os.path.exists(MIMO_DB_PATH):
        return {"ok": False, "days": [], "total_week": 0, "total_today": 0}

    try:
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=3)
        c = conn.cursor()
        c.execute("SELECT data FROM message WHERE time_created > ?", (week_ago_ms,))
        rows = c.fetchall()
        conn.close()

        for r in rows:
            try:
                d = json.loads(r[0])
                if d.get("role") != "assistant":
                    continue
                tok = d.get("tokens", {}) or {}
                inp = tok.get("input", 0) or 0
                outp = tok.get("output", 0) or 0
                cache = tok.get("cache", {}) or {}
                t = inp + outp + (cache.get("read", 0) or 0) + (cache.get("write", 0) or 0)
                if t <= 0:
                    continue
                tc = (d.get("time") or {}).get("created", 0) or 0
                dk = _dt.datetime.fromtimestamp(tc / 1000).strftime("%m-%d")
                day_tokens[dk] += t
                day_turns[dk] += 1
                total_week += t
                if tc >= today_ms:
                    total_today += t
            except Exception:
                continue

        # 构造最近7天的列表（包含无数据的天）
        days = []
        for i in range(6, -1, -1):
            d_str = (_dt.datetime.now() - _dt.timedelta(days=i)).strftime("%m-%d")
            days.append({
                "date": d_str,
                "tokens": day_tokens.get(d_str, 0),
                "turns": day_turns.get(d_str, 0),
                "is_today": d_str == today_str,
            })

        max_tok = max((d["tokens"] for d in days), default=1) or 1
        for d in days:
            d["pct"] = round(d["tokens"] / max_tok * 100)

        return {
            "ok": True,
            "days": days,
            "total_week": total_week,
            "total_today": total_today,
            "total_week_fmt": format_token_lx(total_week),
            "total_today_fmt": format_token_lx(total_today),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "days": [], "total_week": 0, "total_today": 0}


def get_user_quota() -> Dict[str, Any]:
    """通过 Xiaomi SSO passToken 调用外部 API 获取订阅配额剩余量
    等同于 app 端「剩余用量」面板：显示 percent + resetDate（1周周期）
    API: GET {baseUrl}/user/usage  → {code:0, data:{percent, resetDate}}
    """
    import shutil, tempfile, urllib.request, urllib.error

    # 1. 从 Electron Cookies DB 读取 SSO credentials
    cookie_path = os.path.join(MIMO_DATA_DIR, "Partitions", "xiaomi-account", "Cookies")
    pass_token = None
    user_id = None
    try:
        tmp = tempfile.mktemp(suffix=".db")
        shutil.copy2(cookie_path, tmp)
        conn = sqlite3.connect(tmp, timeout=3)
        c = conn.cursor()
        c.execute("SELECT name, value FROM cookies WHERE name IN ('passToken','userId','cUserId')")
        for name, val in c.fetchall():
            if name == "passToken":
                pass_token = val
            elif name == "userId":
                user_id = val
        conn.close()
        os.unlink(tmp)
    except Exception:
        pass

    if not pass_token or not user_id:
        return {"ok": False, "reason": "no-sso", "percent": None, "resetDate": None}

    # 2. 尝试用 SSO cookie 直接调用 xiaomimimo.com 的用量 API
    # (app 内部用 authFetch，使用登录时换取的 JWT；我们用 SSO cookie 尝试)
    candidate_urls = [
        "https://api.xiaomimimo.com/user/usage",
        "https://api.xiaomimimo.com/v1/user/usage",
    ]
    cookie_str = f"passToken={pass_token}; userId={user_id}"

    for url in candidate_urls:
        try:
            req = urllib.request.Request(url, headers={
                "Cookie": cookie_str,
                "User-Agent": "MiMo Desktop/1.0 (macOS)",
                "Accept": "application/json",
            })
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read().decode())
            if isinstance(data, dict) and data.get("code") == 0:
                d = data.get("data", {})
                return {
                    "ok": True,
                    "percent": d.get("percent"),
                    "resetDate": d.get("resetDate"),
                    "period": "1 周",
                }
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"ok": False, "reason": "auth-expired", "percent": None, "resetDate": None}
        except Exception:
            continue

    return {"ok": False, "reason": "failed", "percent": None, "resetDate": None}


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


def _session_title_in_db(session_id: str) -> Optional[str]:
    if not session_id or not os.path.exists(MIMO_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
        c = conn.cursor()
        c.execute(
            """
            SELECT title FROM session
            WHERE id = ?
              AND title NOT LIKE 'checkpoint-writer%'
              AND title NOT IN ('Auto Dream', 'Auto Distill', 'Title request', '测试会话REST')
            """,
            (session_id,),
        )
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _latest_session_id_in_db() -> Optional[str]:
    """数据库中最近更新的用户会话。"""
    if not os.path.exists(MIMO_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
        c = conn.cursor()
        c.execute(
            """
            SELECT id FROM session
            WHERE title NOT LIKE 'checkpoint-writer%'
              AND title NOT IN ('Auto Dream', 'Auto Distill', 'Title request', '测试会话REST')
            ORDER BY time_updated DESC LIMIT 1
            """
        )
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _session_updated_ts(session_id: Optional[str]) -> int:
    if not session_id or not os.path.exists(MIMO_DB_PATH):
        return -1
    try:
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
        c = conn.cursor()
        c.execute("SELECT time_updated FROM session WHERE id = ?", (session_id,))
        row = c.fetchone()
        conn.close()
        return int(row[0] or 0) if row else -1
    except Exception:
        return -1


def get_desktop_current_session_id() -> Optional[str]:
    """打开 PWA 时应落点的会话：桌面焦点优先，若焦点已过期则回退到最近更新会话。"""
    focus_id: Optional[str] = None
    if os.path.exists(COMPOSER_INPUT_PATH):
        try:
            with open(COMPOSER_INPUT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cur = data.get("currentKey")
            if isinstance(cur, str) and cur.startswith("ses_"):
                focus_id = cur
        except Exception:
            pass

    latest_id = _latest_session_id_in_db()

    # 桌面焦点存在且仍是有效用户会话 → 优先同步桌面当前打开的任务
    if focus_id and _session_title_in_db(focus_id) is not None:
        focus_ts = _session_updated_ts(focus_id)
        latest_ts = _session_updated_ts(latest_id)
        # 焦点明显落后（例如 PWA 测试会话残留），改落最近会话
        if latest_id and latest_ts > focus_ts:
            return latest_id
        return focus_id

    return latest_id


def set_desktop_focus_session(session_id: str, directory: Optional[str] = None) -> None:
    """把桌面 composer 焦点会话同步为 session_id，保证双端落点一致。"""
    if not session_id or not os.path.exists(COMPOSER_INPUT_PATH):
        return
    try:
        with open(COMPOSER_INPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["currentKey"] = session_id
        meta = data.get("convoMeta")
        if not isinstance(meta, dict):
            meta = {}
        meta[session_id] = {
            "project": os.path.basename(directory) if directory else os.path.basename(HOME_DIR) or "workspace",
            "directory": directory or DEFAULT_WORKDIR,
        }
        data["convoMeta"] = meta
        with open(COMPOSER_INPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def touch_session_updated(session_id: str) -> None:
    if not session_id or not os.path.exists(MIMO_DB_PATH):
        return
    try:
        now = int(time.time() * 1000)
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
        c = conn.cursor()
        c.execute("UPDATE session SET time_updated = ? WHERE id = ?", (now, session_id))
        conn.commit()
        conn.close()
    except Exception:
        pass




def get_session_context_data(sid: str) -> Dict[str, Any]:
    """获取指定会话的任务清单 (Task Checklist 5/8) 与代码变更统计 (Git Diffs)"""
    res = {
        "tasks": {"total": 0, "done": 0, "in_progress": 0, "open": 0, "items": []},
        "git": None,
    }
    if not sid or not os.path.exists(MIMO_DB_PATH):
        return res
    try:
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
        c = conn.cursor()
        # 1. 任务清单 (来自 SQLite task 表)
        try:
            c.execute(
                "SELECT id, status, summary, created_at, ended_at FROM task WHERE session_id = ? ORDER BY created_at ASC",
                (sid,),
            )
            tasks = c.fetchall()
            items = [{"id": r[0], "status": r[1], "summary": r[2]} for r in tasks]
            done_cnt = sum(1 for t in items if t["status"] == "done")
            in_prog_cnt = sum(1 for t in items if t["status"] == "in_progress")
            open_cnt = sum(1 for t in items if t["status"] == "open")
            res["tasks"] = {
                "total": len(items),
                "done": done_cnt,
                "in_progress": in_prog_cnt,
                "open": open_cnt,
                "items": items,
            }
        except Exception:
            pass

        # 2. 会话工作目录
        c.execute("SELECT directory FROM session WHERE id = ?", (sid,))
        row = c.fetchone()
        conn.close()
        directory = row[0] if row and row[0] else None

        # 3. 代码变更统计 (深入探测工作区 git diff)
        if directory and os.path.exists(directory):
            dirs_to_check = [directory]
            for root, dirs, _ in os.walk(directory):
                if ".git" in dirs:
                    dirs_to_check.append(root)
                if len(dirs_to_check) > 3:
                    break
            for d in reversed(dirs_to_check):
                if os.path.exists(os.path.join(d, ".git")):
                    try:
                        p = subprocess.run(
                            ["git", "diff", "--shortstat"],
                            cwd=d,
                            capture_output=True,
                            text=True,
                            timeout=2,
                            check=False,
                        )
                        st = p.stdout.strip()
                        if st:
                            files, adds, dels = 0, 0, 0
                            for part in st.split(","):
                                part = part.strip()
                                if "file" in part:
                                    files = int(part.split()[0])
                                elif "insertion" in part:
                                    adds = int(part.split()[0])
                                elif "deletion" in part:
                                    dels = int(part.split()[0])
                            p_files = subprocess.run(
                                ["git", "diff", "--name-status"],
                                cwd=d,
                                capture_output=True,
                                text=True,
                                timeout=2,
                                check=False,
                            )
                            f_list = []
                            for line in p_files.stdout.splitlines()[:20]:
                                if line.strip():
                                    sp = line.split(None, 1)
                                    if len(sp) == 2:
                                        f_list.append({"status": sp[0], "file": sp[1]})
                            res["git"] = {
                                "files": files,
                                "additions": adds,
                                "deletions": dels,
                                "file_list": f_list,
                                "dir": os.path.basename(d),
                            }
                            break
                    except Exception:
                        pass
    except Exception:
        pass
    return res


def get_session_turn_status(sid: str) -> Dict[str, Any]:
    """
    精确检查指定会话当前的真实工作状态与当前任务轮次（Turn）的真实开始时间戳。
    如果在运行中，返回 {"is_busy": True, "turn_start_time": int(ms)}
    如果空闲，返回 {"is_busy": False, "turn_start_time": 0}
    """
    if not sid:
        return {"is_busy": False, "turn_start_time": 0}

    # 1. 优先从本地 SQLite 毫秒级极速查询
    if os.path.exists(MIMO_DB_PATH):
        try:
            conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
            c = conn.cursor()
            c.execute(
                "SELECT id, time_created, time_updated, data FROM message WHERE session_id = ? ORDER BY time_created DESC LIMIT 1",
                (sid,),
            )
            row = c.fetchone()
            if not row:
                conn.close()
                return {"is_busy": False, "turn_start_time": 0}

            last_id, last_time, _, last_raw = row
            data = json.loads(last_raw)
            role = data.get("role", "assistant")
            finish = data.get("finish")
            has_error = bool(data.get("error"))
            parent_id = data.get("parentID")

            # 检查是否有未结束的工具执行
            c.execute("SELECT data FROM part WHERE message_id = ?", (last_id,))
            parts = [json.loads(p[0]) for p in c.fetchall() if p[0]]
            has_running_tool = any(
                p.get("type") == "tool" and p.get("state", {}).get("status") == "running" for p in parts
            )

            if role == "user":
                conn.close()
                return {"is_busy": True, "turn_start_time": int(last_time or 0)}

            is_done = (finish == "stop" or bool(data.get("time", {}).get("completed"))) and not has_running_tool
            if has_error:
                is_done = True

            if not is_done:
                turn_start_time = 0
                if parent_id:
                    c.execute("SELECT time_created FROM message WHERE id = ?", (parent_id,))
                    p_row = c.fetchone()
                    if p_row and p_row[0]:
                        turn_start_time = int(p_row[0])
                if not turn_start_time:
                    created_val = data.get("time", {}).get("created")
                    turn_start_time = int(created_val or last_time or 0)
                conn.close()
                return {"is_busy": True, "turn_start_time": turn_start_time}

            conn.close()
            return {"is_busy": False, "turn_start_time": 0}
        except Exception:
            pass

    # 2. 备选兜底：向官方 Desktop HTTP API 查询消息列表判定
    try:
        code, msgs = call_mimo_v1(f"sessions/{sid}/messages")
        if code == 200 and isinstance(msgs, list) and msgs:
            last = msgs[-1]
            info = last.get("info", {})
            role = info.get("role", "assistant")
            finish = info.get("finish")
            has_error = bool(info.get("error"))
            parts = last.get("parts", [])
            has_running_tool = any(
                p.get("type") == "tool" and p.get("state", {}).get("status") == "running" for p in parts
            )

            if role == "user":
                return {"is_busy": True, "turn_start_time": int(info.get("time", {}).get("created", 0))}

            is_done = (finish == "stop" or bool(info.get("time", {}).get("completed"))) and not has_running_tool
            if has_error:
                is_done = True

            if not is_done:
                parent_id = info.get("parentID")
                turn_start_time = 0
                if parent_id:
                    for m in msgs:
                        m_info = m.get("info", {})
                        if m_info.get("id") == parent_id or m.get("id") == parent_id:
                            turn_start_time = int(m_info.get("time", {}).get("created", 0))
                            break
                if not turn_start_time:
                    turn_start_time = int(info.get("time", {}).get("created", 0))
                return {"is_busy": True, "turn_start_time": turn_start_time}
    except Exception:
        pass

    return {"is_busy": False, "turn_start_time": 0}


def create_new_mimo_session_in_db(title: str = "新任务会话", directory: Optional[str] = None) -> Dict[str, Any]:
    """在电脑本地数据库中创建一个全新的真实 MiMo 会话"""
    import uuid

    if not directory:
        directory = DEFAULT_WORKDIR

    new_id = "ses_" + uuid.uuid4().hex[:22]
    now = int(time.time() * 1000)
    if os.path.exists(MIMO_DB_PATH):
        conn = sqlite3.connect(MIMO_DB_PATH, timeout=5)
        c = conn.cursor()
        cur_p = get_current_perm()
        perm_rules = None
        if cur_p == "完全访问权限":
            perm_rules = json.dumps([{"permission": "*", "pattern": "*", "action": "allow"}])
        elif cur_p == "帮我审批":
            perm_rules = json.dumps([{"permission": "edit", "pattern": "*", "action": "allow"}])
        c.execute(
            """
            INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, permission, time_created, time_updated)
            VALUES (?, "global", NULL, "new-session", ?, ?, "2.1.159", ?, ?, ?)
        """,
            (new_id, directory, title, perm_rules, now, now),
        )
        conn.commit()
        conn.close()

    if os.path.exists(COMPOSER_INPUT_PATH):
        try:
            with open(COMPOSER_INPUT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["currentKey"] = new_id
            if "convoMeta" not in data or not isinstance(data["convoMeta"], dict):
                data["convoMeta"] = {}
            data["convoMeta"][new_id] = {
                "project": os.path.basename(directory) or os.path.basename(HOME_DIR) or "workspace",
                "directory": directory,
            }
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


def get_tailscale_ip() -> Optional[str]:
    try:
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2, check=False)
        ip = (res.stdout or "").strip().split("\n")[0]
        if ip and ip.count(".") == 3 and ip.replace(".", "").isdigit():
            return ip
    except Exception:
        pass
    return None


def get_local_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def get_tailscale_magicdns_host() -> Optional[str]:
    try:
        res = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if res.returncode != 0 or not res.stdout:
            return None
        status = json.loads(res.stdout)
        dns = ((status.get("Self") or {}).get("DNSName") or "").strip().rstrip(".")
        if dns and dns.endswith(".ts.net"):
            return dns
    except Exception:
        pass
    return None


def _parse_serve_https_ports(serve_json: Dict[str, Any]) -> List[Tuple[int, Optional[int]]]:
    """从 tailscale serve status --json 提取 (https_listen_port, target_local_port)。"""
    found: List[Tuple[int, Optional[int]]] = []
    seen: set = set()

    def walk_handlers(handlers: Any) -> Optional[int]:
        if not isinstance(handlers, dict):
            return None
        for cfg in handlers.values():
            if not isinstance(cfg, dict):
                continue
            proxy = cfg.get("Proxy") or cfg.get("proxy")
            if isinstance(proxy, str) and proxy.startswith("http://127.0.0.1:"):
                try:
                    return int(proxy.rsplit(":", 1)[-1])
                except ValueError:
                    return None
            path = cfg.get("Path") or cfg.get("path")
            if isinstance(path, str):
                try:
                    return int(path)
                except ValueError:
                    return None
        return None

    def extract_from_tcp_web(tcp: Any, web: Any) -> None:
        if not isinstance(tcp, dict):
            return
        for port_s, tcp_cfg in tcp.items():
            try:
                listen_port = int(port_s)
            except (TypeError, ValueError):
                continue
            if not isinstance(tcp_cfg, dict) or not (tcp_cfg.get("HTTPS") or tcp_cfg.get("https")):
                continue
            target = None
            if isinstance(web, dict):
                for _host, web_cfg in web.items():
                    if isinstance(web_cfg, dict):
                        handlers = web_cfg.get("Handlers") if "Handlers" in web_cfg else web_cfg
                        target = walk_handlers(handlers)
                        if target is not None:
                            break
            key = (listen_port, target)
            if key not in seen:
                seen.add(key)
                found.append(key)

    # 根节点直接含 TCP/Web（background serve）
    extract_from_tcp_web(serve_json.get("TCP"), serve_json.get("Web"))

    # Foreground / Background 分组
    for section_key in ("Foreground", "Background"):
        section = serve_json.get(section_key)
        if not isinstance(section, dict):
            continue
        if "TCP" in section or "Web" in section:
            extract_from_tcp_web(section.get("TCP"), section.get("Web"))
            continue
        for entry in section.values():
            if isinstance(entry, dict):
                extract_from_tcp_web(entry.get("TCP"), entry.get("Web"))
                # 兼容嵌套 Web 里带 Handlers 的写法
                web = entry.get("Web")
                if isinstance(web, dict):
                    for _host, web_cfg in web.items():
                        if isinstance(web_cfg, dict) and "Handlers" in web_cfg:
                            extract_from_tcp_web(entry.get("TCP"), {_host: web_cfg})

    return found


def get_tailscale_https_url(gateway_port: Optional[int] = None) -> Optional[str]:
    """仅当存在转发到本网关的 tailscale serve HTTPS 时才返回可用安装地址。"""
    host = get_tailscale_magicdns_host()
    if not host:
        return None
    try:
        res = subprocess.run(
            ["tailscale", "serve", "status", "--json"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if res.returncode != 0 or not res.stdout:
            return None
        serve_json = json.loads(res.stdout or "{}")
    except Exception:
        return None

    pairs = _parse_serve_https_ports(serve_json)
    if not pairs:
        return None

    port = gateway_port or GATEWAY_LISTEN_PORT
    matched = [lp for lp, target in pairs if target == port]
    if not matched and port is not None:
        return None
    listen_port = matched[0] if matched else pairs[0][0]
    if listen_port == 443:
        return f"https://{host}"
    return f"https://{host}:{listen_port}"


_PWA_HTTPS_CACHE: Dict[str, Any] = {"ts": 0.0, "url": None}


def get_pwa_https_url_cached(ttl: float = 15.0) -> Optional[str]:
    now = time.time()
    if now - float(_PWA_HTTPS_CACHE["ts"]) < ttl:
        return _PWA_HTTPS_CACHE["url"]
    url = get_tailscale_https_url()
    _PWA_HTTPS_CACHE["ts"] = now
    _PWA_HTTPS_CACHE["url"] = url
    return url


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        try:
            return s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0
        except OSError:
            return False


def pick_available_port(host: str, port: int, max_tries: int = 20) -> int:
    for candidate in range(port, port + max_tries):
        if not port_in_use(host, candidate):
            return candidate
    return port


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# 官方 Xiaomi MiMo 纯正黑底四格几何矢量图标（来自客户端 Figma 1929:695 / 2046:263）
OFFICIAL_MIMO_SVG = b"""<svg width="1024" height="1024" viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="1024" height="1024" fill="#000000"/>
  <g transform="translate(0.19 -8.28)" fill="#FFF9EE">
    <path d="M469.881 867.33C469.881 875.261 463.451 881.691 455.52 881.691H147.017C139.086 881.691 132.656 875.261 132.656 867.33V598.213C132.656 585.635 147.679 579.134 156.848 587.744L291.438 714.127C296.964 719.317 305.573 719.317 311.099 714.127L445.689 587.744C454.858 579.134 469.881 585.635 469.881 598.213V867.33Z"/>
    <path d="M469.881 445.599C469.881 453.531 463.451 459.961 455.52 459.961H147.017C139.086 459.961 132.656 453.531 132.656 445.599V176.483C132.656 163.905 147.679 157.404 156.848 166.014L291.438 292.397C296.964 297.586 305.573 297.586 311.099 292.397L445.689 166.014C454.858 157.404 469.881 163.905 469.881 176.483V445.599Z"/>
    <rect x="649.387" y="158.855" width="181.909" height="301.586" rx="14.3612"/>
    <circle cx="740.273" cy="730.976" r="150.726"/>
  </g>
</svg>"""

ICON_SVG = OFFICIAL_MIMO_SVG

# 内置官方 MiMo 高清图标 Base64，确保即使无外部资源文件也绝不降级为错误的小米橙标
FALLBACK_180_PNG_B64 = """iVBORw0KGgoAAAANSUhEUgAAALQAAAC0CAYAAAA9zQYyAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAARGVYSWZNTQAqAAAACAABh2kABAAAAAEAAAAaAAAAAAADoAEAAwAAAAEAAQAAoAIABAAAAAEAAAC0oAMABAAAAAEAAAC0AAAAAFbVlnkAAAGfaVRYdFhNTDpjb20uYWRvYmUueG1wAAAAAAA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJYTVAgQ29yZSA2LjAuMCI+CiAgIDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+CiAgICAgIDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiCiAgICAgICAgICAgIHhtbG5zOmV4aWY9Imh0dHA6Ly9ucy5hZG9iZS5jb20vZXhpZi8xLjAvIj4KICAgICAgICAgPGV4aWY6UGl4ZWxYRGltZW5zaW9uPjEwMjQ8L2V4aWY6UGl4ZWxYRGltZW5zaW9uPgogICAgICAgICA8ZXhpZjpQaXhlbFlEaW1lbnNpb24+MTAyNDwvZXhpZjpQaXhlbFlEaW1lbnNpb24+CiAgICAgIDwvcmRmOkRlc2NyaXB0aW9uPgogICA8L3JkZjpSREY+CjwveDp4bXBtZXRhPgpVgmNYAAAUmElEQVR4Ae2dCXhU1dnH/8lMkgkESAKybxEXorgUJQoECEsBC0X2SIEi8NnIFrBBAaksFtmFKCFA2ATZQghbInxUXIpUaVGhflLcxWqVRRMIZJtJcr/33CQ0jglcMnfnPc8zZGY495z3/b+/ufds91w/ABK9OLECtlDA3xZesBOsQJkCDDSjYCsFGGhbhZOdYaCZAVspwEDbKpzsDAPNDNhKAQbaVuFkZxhoZsBWCjDQtgonO8NAMwO2UoCBtlU42RkGmhmwlQIMtK3Cyc4w0MyArRRgoG0VTnaGgWYGbKUAA22rcLIzDDQzYCsFGGhbhZOdYaCZAVspwEDbKpzsDAPNDNhKAQbaVuFkZxhoZsBWCjDQtgonO+NkCeyjQL264Yi8KxIBDn/Nt8PyI9k8xcX416nT+Ckr2zQiag70rREtMGF8HOrWq4vUHWk4eOiwaZz3xZDbWkVgwoQ4hIaGYvu2HfjL4bd9Kc7nYztFt8fmTWvRsmVz2txNp93d/Pzw1ZdnMGLkWLz39+M++6BWAcJ7TV50xpBOf3RMkqQiehVKRYUXpfiJcZrUpZUPlZUb1a6tdOarU+STR/bLXZAl9ezR1TC/HA6HdPStg7ItUmEWSa3ji+L65l/2S/7+/ob5XzFGmrahO3Z4CK3vuQ9w59ArF3QlxEsvLcXM6QlkgzVTTOdoZOxLQ4uIluTTZdmvgKCa+N1jgw1zKDjYhaZNGgMlhfrbIBWiedMmCAoK1L/uSmrUFOgaNWpQleKHW5ZKSkj0Ysxb8DwWzpsNP7pkWSn1eaQn9uzejvoNGxDIFeEpQXBwsKGulEikrUHJyLq9XdYUaLoGetdHQJPwHjemzZyOFYmL4HQ6fpnHhN/EDhmA1NTNCA0Lle33NrFSX70z8WfNFdAU6CqtF6B7CjAhPh7r1qyAKyioyqxm+I+xj4+gDtc61KxJV5wijxlMYhuqUMAYoIUxAmp3HkaNGYMtm1MQElKzChON/XrypDisSUlCYCANCBUVGWsM135dBYwDutw0gnrQ0Fik7diE8LCw8m9N8Vd0XhMTl8Ihmvo05srJ/AoYD7TQiKDu3acv9u7ehkaiw2VwEp3VhS/MljuvohMrt/sNtomrV6aAOYAWthLUnWK60pDYTrRs0UyZ9RrkcjqdSEpcjGnPTi/t/IlOLCfLKGAeoIVkBPUDUVE4kJmO1nferruILlcQ1qeswPj4SXKnVbcZN909tW+F5gJa6OzOR2SbNjLUv7r/Xt2UrxUSgq00dfz70aPlHxbDrJv0qlZkPqCFe+4CRNzWCpn70yBmG7VO4eFhcqd04NChpTBrXSGXr5kC5gRauEszcY2bNcG+vamgdRKaCSA6ofvSt6NXnz4Ms2Yq61eweYEWGrjd8iq9XWlbMeBRAk7l1LJFc7oK7ER0TBeGWWVtjSrO3EALVTwe1KpN7dutr2Dk8FjxjSopkjqdBzJ3oW27KII5X5UyuRDjFTA/0EIjmqELdgViw/pVGBc3xmfV2lJn87XM3XLnk2H2WU5TFWANoIVkNFPndDiwcmUinkmgYbVqpmjqZGZm7KJO5610Zi6oZil8mFkVsA7QQkGatfOjZZKLlizA87Nn3LCmvXp0w17qZDYSa4d/tvzzhoviA0yqgLWAFiKKmTta8fbcnOewfOl80J0SiqQd2L8v0tK2yJ1MsXyVkz0VUEaD2XyXl58WYkrCU1iTvJxWwl37bonfU2dy65aNcudSdDI52VcBawIt4iFDnY//iYvDpg2rUKNG5XeMjI8bi/UbVsNFnUpe/mlfkMs9sy7QMtT0D63/eGz4cKRu3YjQOrXL/ZL/Tps6GUkrl8PpT+s/efnnz7Sx6wfNtzHQRTiCum//R3EgIxyLl76Ei5cu4Xexg/EEnZ15+acuETBNJfYAWshJkyPtO3XAHnrJZ2NHAE3K0I2somnC6aZRwD5Ai5DRVPnVxE2Mq1LcTG+s3Ya+mSLFvipSgIFWJBNnsooCDLRVIsV2KlKAgVYkE2eyigIMtFUixXYqUoCBViQTZ7KKAgy0VSLFdipSgIFWJBNnsooCDLRVIsV2KlKAgVYkE2eyigIMtFUixXYqUoCBViQTZ7KKAgy0VSLFdipSgIFWJBNnsooCDLRVIsV2KlKAgVYkE2eyigIMtFUixXYqUoCBViQTZ7KKAgy0VSLFdipSgIFWJBNnsooCDLRVIsV2KlKAgVYkE2eyigIMtFUixXYqUkBToMUDLG+W5C+2GzMwGam1kXV7S64p0D/++FNpfbYH24nzF3701la3z27aYCcvjx6r4e/Qrc6rFfk5kJubR5u6muM56JrunHT03WPI2LMPvx0wiPy36xNZ/fHdmS+wOmXj1Rjr/cbt9iBp1VokJ78MBIboqLU/pOJCJCWvpY1dzQG0uE5quvlbsMuF3/Z9BM3oEW1SiaZV6c0R/KiZcflKLg4dOoxv/v2t7vV7V9jr190QHd1BfnSHxmEF6KrrKSrGkSPv4PAbf/U2xbDPmgNtmGdc8U2pgKZt6JtSUXbaUAUYaEPl58rVVoCBVltRLs9QBRhoQ+XnytVWgIFWW1Euz1AFGGhD5efK1VaAgVZbUS7PUAUYaEPl58rVVoCBVltRLs9QBRhoQ+XnytVWgIFWW1Euz1AFGGhD5efK1VaAgVZbUS7PUAUYaEPl58rVVoCBVltRLs9QBRhoQ+XnytVWgIFWW1Euz1AFGGhD5efK1VaAgVZbUS7PUAU0veu7omcOhz+Ki+1357e/vz9KSqzjV0hICJo1bYwWLZqjceOGqBcejuBglxwqsRXCj1lZ+P77H3Dmm2/x3Xf/kbcoqBhHK7wXt2Jr9uretbP0xuuZ0ofv/02aNnWyRABoVpeWfniXTXdYS2+9eUD64Pg7UsKUCZLD4TCtX63vvEOaNDFO2rNrq/TVZyelgstnJanksiRJ+fQqoFdh2Uu8p+/o//JzfpC++OSEtCt1szT+ybHSHbe3Mq1/XrHRDuaIli2krHNfk0hCqCv0KpTWJCdKAQEBVhGnUjtHDBsi5V05T/4IIIRfbmnUyGGV5vUSW7c8NWoES8NiB0mHDuyWci/9QDaKGORJUnEOmZtNoci69kvkEXnLoL+S/R8pc/9OafCgRyWXK0g3P6qhn3ZADyHnZUHKxRMikbBbN6+VagQHm1mUKm178onRkruAYCi69F8gyKdt5FM1xFf9GHGyGD1quPTPE++S1rn0Iog9F/9ra3ksbvSvKEOURT/gD44fkYbTj9qkVyXtgBZnCFkEb/EIgH27t0l1atdWPaBaQjX1qYlSiYfOWhVhFr7RWSx16wbDfenwcDvpyFsHr4J33bOwd1yUfpavSrnS64f2Sw+2vd9wvyvGXNNRDlKW6qokufPQb8BApKe9inr16laSwXxfzZ01HUteXAg/saVZcfEvDKzS11/kVP8Lp9OBP82YisOvZ6JTTBfAXUAvt/oVlZcoynYXokfPHqB+BBKemkgbKRm7WWW5aZoCXV5JpX8J6u49e2H/nh1o0qRRpVnM8KUYxXhx8TzMmjsLKPLQFn3mGtGoWzccO7dtwp/nz0OwK6gUZr2Eox9OSEhNLF22BNSMRJ06tfWqucp6jANamERQt4+Oxmv7d6HVrRFVGmnUfwQGBGB10jL88ekEwFNIY0FVXHEMMrB5s6Y4kLELA4YMkbU05McmrlbufAwbMVI+OTVq2MAgNUqrNRZoYQOJcV/btjiQuQtt7m5tqBgVK6dOK15Zn4wnxj1JMNMl3GQwN2vaBBl7UxHVvj1pmFvRdGPekw2du3bD3t3b0aBBfWNsoFqNB1q4TlDfERmJ1zLS0e7BXxkmRnnF1FnF9q0bMGzkSLItz3Qwh4eFIm3HJtxLJwKhnWkSaRXVvgN2bFmPWrXEtr76J3MALfym9ljziJbIoOZHTOeO+itRVuMt1ElNT9tCndYBpTAbZknlFdNQGVavXI6HOnYyF8zl5hLUMT16YsXyRYZ0FM0DtBCEes4NGtbHHrps/ab3r8sl0u1v0yaN5XZg9549TQmzEOKp+HEYMuwxss8EzYyqIuPJxaixo/HkE49XlUOz780FtHDT40FoWBh2pr6KoYP7a+a4d8G3tYpA5v40PEydVLmZ4Z3BBJ/vv+8ezJn9LA0bajgkp4afou9c7MH8F+ag9Z23q1Gi4jLMB7QwnYbHaobUwKub12HMqOGKnaluxjZ3R1KnNJ06p9R+N1ObtIJDoqmxZMFc1KwTVuk4eIWs5nhLox+h9epj4QuzdW16mBNoERJ6ZkdgYABS1q7E5IlxmgUp6kEaYaHO6O2t7ySYaTTDpKl/vz7o0ZuaQh4TdQKvpxWNDvV7tB/EozL0SuYFWihAv3IHTUAlvrQUM6fTWLDKKaZzNHVC09AsojnBTOPMJk1iPHza1HiyjsQw11D4tRWjoU4/pxPTn54CcYXRI5kbaKGAmJkrKca8Bc9jwbxZql2++jzSU+581hcTAVpOE6sQxe7duqDdQw+VTu6oUJ6uRdCEVKcunRDdgezXIZkfaCGCgNrjxvSZM7AicRGc9Kv3JcUOHoDUHZup8xkql+tLWXocO+bxEYDDN5/1sLPSOugs7R/gAq0ArPS/1f7SGkALr8VMHbXJJsTHY92al+EKonUL1UhjCY5N1NkUnU55bUY1ytDzkCaNG6EHnaFNP7JxLVFKCtG7Z3fUo3UnWifrAC2UEFDTwP2oMWOwZXOKvDDmRgQSncs1KUkICqSznUkeFHk9+7vQJFNofWoWiTUTVk30PMMGTZuiow7NDmsBXR5QgnrQ0Fh5+jecxqyVJNGpFJ1L0cm0Ehx0CxsZbM0w/Swufk50ixG+aJusqxRB3btPX1oMsw3XWuEl1umKsVDRqRSdS0NWpFUzhqKv8EDb++nKZI7HDlfTjbLDiuV1Olqvm7Yu0EImgrpTTAwy9u1ES7qL2TsJIJISF2Pas9NLO38mW8vsba/35/q31EPz5s3oimIDoMmHWyNaQiys0jJZG2ihDM3sPRAVJa8LvktMjpSlYFr+uT5lBcbHT5I7k2Zb/llu57X+NqYOYWgoLZoXfQerJzqZhIeHoWED6g9omCw6FuSlCEEdec/dOHxoH9Zt2ITs7Iugu5PRoTO12egsbtXUkNYV+wXSaI7Jx8kV6Us/ygCXC/Xr18Op04qOqFYmewAtXKeZvkZ0K9dzc2aXCUGXaRNPZSuJVmhoHcqmzwybEnt8zkNj6XXqCJ+0S/YBWmgkhraKrXtG9g5zdcfavcsxz2c/BAUFamqO9dvQmspjbOFG3kmuledadwcYaK0ip0K5ubTXHPUIVSjJLEWUID9f+KRdYqC109bnkrOysolnC88QVlRA7NtBs7NZ2eSThomB1lBcX4v+4exZFIkzmkk2cfHJH/IhPzcP585d8KmY6x3MQF9PIQP///vvz+Knn+iMRpvdWD6RD+cvXMDZc+c0dcUGSmmqj6GFi8vzF19+Zd2loxXV83fi08++wJUr2t7cy0BXFN1k78Uox7F/vE9W2WEs2h/vHfuH5goz0JpL7FsFh994mxZUeXwrxOijqf0sFRXgjTePaG4JA625xL5V8O6x4/j2669Bt+n4VpCRR9MM4eeffoYPPjypuRUMtOYS+1ZBTk4O9mYcoI6htjNsvll5naPJ9vQ9GcjTeAxaWMFAXycWZvjvjZu20Rqry9YcvqPRjbycLGzeskMXKRloXWT2rZITJz/Ca5kHQcvVfCvIiKOdLqSn78Unn36uS+0MtC4y+17JgiXLUZh3ha6p4h4yiyT57JyNxS++rJvBDLRuUvtW0fH3T2AjrfWGk+5Wt0pyBiM5OQUfa7kA2ksLBtpLEDN/nP3nRfj689PU9LBAB5FuTPjk/05i/qLlukrKQOsqt2+VnT9/gfYlmYoiN41Lm3k6nGwryMvDuIl/RPbFi745fYNHM9A3KJjR2Q/+72HMmTOPmh50a5YZFy0Jm5yBmDF9Ft4+8jfd5WKgdZfc9woXLF6GtavWUNMj2PfC1CxBwEw2Jb6YiMQVq9QsWXFZDLRiqcyTsaREwsQpT2PLK68AgdRJNMOZugzmlORVmDrtOcPEYqANk963it3Ujh77h0lYlbSSzorU/DCyTS22yqWO6rIlS2nbiAS6tdO4mxIYaN+4MvRoNz2+Y/ykBDyTMA2FbrrLPdCA0Q8azcijW8UmTZiChGf+RDCXGKoJA22o/OpUvmTZCvym70B8/NHHBHVNfc7W4qxMzZ0T73+IXr37Iyl5rTrO+FgKA+2jgGY5/M23jqBzl95YOH8+ci7TjKJoW2vRDCkDOTv7EubOnouYbo/g6LvHzCKDtouTSjfms9BUrQ9h8TfBlLQY850xcy7ad+yOtavX4OKlnFKwRVPEl46jOFaUQT+SLLolbOWKJDzcoSvmPL+g9Mfjg25qH6rpItszZ/5dujhd/KpFR8FubIsdBmRQAvHZ51+qHZtql/ev05/iD+MmY9GSRMTGDsSg/v1wL22V5gwWT3cVRlN7W7R1q9q8UpzZHeLiLfDwo5V+OThJU+/pu/dhZ9oenPmG4mrSJBDTbOMHfxJGbGU7KX4CXC76hWu9y4jeIpN6EnHxzpGjiB0+GmfPntfbAkX1BdDNAW3a3IXOnTqg/cNRiGx9BxrTs2Vq166FQPEkBLlpQhgQ5IW0j55Ygy1u0D1FPwxx29SRo+/hFK3HMHL0QpGjlElToMuNuCuyNT3Q/BYNfzrlNen8l9QTPfyT//wIhYUmfxhmBWnENsNio/i6dcNQu1YtOtmULkvNLyggmC/TneZZtOFlNooMHH6rYO4NvdUF6BuyiDOzAj4oIBpKnFgB2yjAQNsmlOyIUICBZg5spQADbatwsjMMNDNgKwUYaFuFk51hoJkBWynAQNsqnOwMA80M2EoBBtpW4WRnGGhmwFYKMNC2Cic7w0AzA7ZSgIG2VTjZGQaaGbCVAgy0rcLJzjDQzICtFGCgbRVOdoaBZgZspQADbatwsjMMNDNgKwUYaFuFk51hoJkBWynAQNsqnOwMA80M2EqB/wd+Mfxqqvrc1AAAAABJRU5ErkJggg=="""
FALLBACK_192_PNG_B64 = """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"""
FALLBACK_512_PNG_B64 = """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w6atfEvykau3u+naub0MHnS1nK+fA8WKFRVPfubtzly4XYaKJR87Ku/r6f6NG7fK8uVr5MjRoy6UsLPLJAC5xCVMs9fY2Bi9HKhUHP9z0eLlggqk67dMkwRQ7BIwB/8SxYtJdDSTA/MTGTOeDx44KPv//FPS0jiTmh87J95LAuCEMnUggAACCCBgmQB3AVgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCagwACCCCAgBMCJABOKFMHAggggAAClgmQAFgWEJqDAAIIIICAEwIkAE4oUwcCCCCAAAKWCZAAWBYQmoMAAggggIATAiQATihTBwIIIIAAApYJkABYFhCa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"""


VENDOR_ASSETS_DIR = os.path.join(_SCRIPT_DIR, "assets", "vendor")
FALLBACK_MARKED_JS_B64 = "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"
FALLBACK_PRISM_JS_B64 = "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"


def load_vendor_asset(filename: str, fallback_compressed_b64: str) -> bytes:
    p = os.path.join(VENDOR_ASSETS_DIR, filename)
    if os.path.isfile(p):
        try:
            with open(p, "rb") as f:
                data = f.read()
                if len(data) > 100:
                    return data
        except Exception:
            pass
    if fallback_compressed_b64:
        try:
            return zlib.decompress(base64.b64decode(fallback_compressed_b64))
        except Exception:
            pass
    return b""

OFFICIAL_MIMO_ICONS_DIR = os.path.join(os.path.dirname(__file__), "mimo-pwa", "assets")

def load_official_icon(filename: str, fallback_b64: str) -> bytes:
    p = os.path.join(OFFICIAL_MIMO_ICONS_DIR, filename)
    if os.path.exists(p):
        try:
            with open(p, "rb") as f:
                data = f.read()
                if len(data) > 100:
                    return data
        except Exception:
            pass
    return base64.b64decode(fallback_b64)

ICON_192_PNG = load_official_icon("icon-192.png", FALLBACK_192_PNG_B64)
ICON_512_PNG = load_official_icon("icon-512.png", FALLBACK_512_PNG_B64)
APPLE_TOUCH_ICON_PNG = load_official_icon("apple_touch_icon.png", FALLBACK_180_PNG_B64)

# 读取裁剪好的真实客户端用户头像
if os.path.exists(AVATAR_PNG_PATH):
    with open(AVATAR_PNG_PATH, "rb") as f:
        USER_AVATAR_PNG = f.read()
else:
    USER_AVATAR_PNG = ICON_192_PNG

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
        "background_color": "#000000",
        "theme_color": "#000000",
        "orientation": "portrait",
        "lang": "zh-CN",
        "categories": ["developer", "productivity", "utilities"],
        "icons": [
            {
                "src": "/icons/icon-192.png?v=mimo-2026",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/icons/icon-512.png?v=mimo-2026",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": "/icons/icon-192.png?v=mimo-2026",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable"
            },
            {
                "src": "/icons/icon-512.png?v=mimo-2026",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable"
            },
            {
                "src": "/icons/apple-touch-icon.png?v=mimo-2026",
                "sizes": "180x180",
                "type": "image/png"
            }
        ]
    },
    ensure_ascii=False,
    indent=2,
)

PWA_SERVICE_WORKER_JS = """
const CACHE_NAME = 'mimo-pwa-v19';
const PRECACHE = [
  '/',
  '/index.html',
  '/manifest.json?v=mimo-2026',
  '/icons/icon-192.png?v=mimo-2026',
  '/icons/icon-512.png?v=mimo-2026',
  '/icons/apple-touch-icon.png?v=mimo-2026',
  '/icons/avatar.png'
];

self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
});

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

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.status === 200 && fresh.type !== 'opaque') {
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const shell = await cache.match('/index.html') || await cache.match('/');
    if (shell) return shell;
    throw err;
  }
}

async function cacheFirst(request, { revalidate = true } = {}) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) {
    if (revalidate) {
      fetch(request).then((res) => {
        if (res && res.status === 200) cache.put(request, res.clone());
      }).catch(() => {});
    }
    return cached;
  }
  const res = await fetch(request);
  if (res && res.status === 200) cache.put(request, res.clone());
  return res;
}

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  const isHTML = (e.request.headers.get('accept') || '').includes('text/html')
    || url.pathname === '/'
    || url.pathname === '/index.html';
  const isStatic = /[.](js|css|svg|png|ico|json|woff2?)$/.test(url.pathname);

  if (isHTML) {
    e.respondWith(networkFirst(e.request));
  } else if (isStatic || url.pathname.startsWith('/icons/') || url.pathname.startsWith('/vendor/')) {
    e.respondWith(cacheFirst(e.request, { revalidate: true }));
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover, interactive-widget=resizes-content">
  <script src="/vendor/marked.min.js"></script>
  <script src="/vendor/prism.min.js"></script>
  <script>
    // 全局启动与防卡死兜底守卫
    window.addEventListener('error', function(e) {
      console.error('[PWA Boot Guard]', e);
      var topTitle = document.getElementById('top-session-title');
      if (topTitle && topTitle.textContent === '正在载入...') {
        topTitle.textContent = '运行异常';
      }
      var loader = document.getElementById('init-loader');
      if (loader) {
        loader.innerHTML = '<div style="background:#FFF1F2;border:1px solid #FECDD3;border-radius:12px;padding:16px;margin:20px 12px;color:#9F1239;font-size:13px;line-height:1.6;">' +
          '<div style="font-weight:700;display:flex;align-items:center;gap:6px;margin-bottom:6px;font-size:14px;">⚠️ 界面加载遇到异常</div>' +
          '<div style="color:#BE123C;margin-bottom:12px;word-break:break-all;">' + (e.message || '未知脚本错误') + '</div>' +
          '<button onclick="location.reload()" style="background:#E11D48;color:#FFF;border:none;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;">刷新页面重试</button>' +
        '</div>';
      }
    });
  </script>
  <title>Xiaomi MIMO</title>
  
  <link rel="manifest" href="/manifest.json?v=mimo-2026">
  <meta name="theme-color" content="#FFFFFF">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="MiMo">
  <meta name="application-name" content="Xiaomi MiMo">
  <meta name="format-detection" content="telephone=no">
  <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png?v=mimo-2026">
  <link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png?v=mimo-2026">
  <link rel="apple-touch-icon" sizes="192x192" href="/icons/icon-192.png?v=mimo-2026">
  <link rel="apple-touch-icon" sizes="512x512" href="/icons/icon-512.png?v=mimo-2026">
  <link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png?v=mimo-2026">
  <link rel="icon" type="image/png" sizes="512x512" href="/icons/icon-512.png?v=mimo-2026">
  <link rel="shortcut icon" href="/icons/icon-192.png?v=mimo-2026">

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

    /* 头像点击区域 */
    .sidebar-user-avatar {
      cursor: pointer;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .sidebar-user-avatar:hover {
      transform: scale(1.08);
      box-shadow: 0 0 0 2px var(--accent);
    }
    /* 周用量弹窗 */
    #weekly-usage-popover {
      position: fixed;
      left: 12px;
      bottom: 72px;
      width: 252px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.18);
      padding: 14px 16px 16px;
      z-index: 9999;
      display: none;
    }
    #weekly-usage-popover.open { display: block; }
    .weekly-pop-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-dim);
      letter-spacing: 0.04em;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .weekly-pop-close {
      cursor: pointer;
      color: var(--text-dim);
      font-size: 14px;
      line-height: 1;
      padding: 2px 4px;
    }
    .weekly-chart {
      display: flex;
      align-items: flex-end;
      gap: 5px;
      height: 60px;
      margin-bottom: 10px;
    }
    .weekly-bar-wrap {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      height: 100%;
      justify-content: flex-end;
    }
    .weekly-bar {
      width: 100%;
      border-radius: 4px 4px 0 0;
      background: var(--border-subtle);
      min-height: 3px;
      transition: height 0.3s ease;
    }
    .weekly-bar.today { background: var(--accent); }
    .weekly-bar.has-data { background: #6B9BF4; }
    .weekly-bar-label {
      font-size: 9.5px;
      color: var(--text-dim);
      white-space: nowrap;
    }
    .weekly-bar-label.today { color: var(--accent); font-weight: 600; }
    .weekly-stats {
      display: flex;
      justify-content: space-between;
      padding-top: 8px;
      border-top: 1px solid var(--border-subtle);
    }
    .weekly-stat-item { text-align: center; }
    .weekly-stat-val {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-main);
    }
    .weekly-stat-lbl {
      font-size: 10px;
      color: var(--text-dim);
      margin-top: 1px;
    }

    /* 订阅配额剩余区块 */
    .quota-section {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--border-subtle);
    }
    .quota-label {
      font-size: 10px;
      font-weight: 600;
      color: var(--text-dim);
      letter-spacing: 0.04em;
      margin-bottom: 8px;
    }
    .quota-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .quota-meta {
      display: flex;
      gap: 10px;
      align-items: center;
    }
    .quota-chip {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-main);
      background: var(--bg-input);
      border-radius: 6px;
      padding: 2px 7px;
    }
    .quota-expire {
      font-size: 10px;
      color: var(--text-dim);
    }
    .quota-bar-bg {
      flex: 1;
      height: 4px;
      border-radius: 2px;
      background: var(--border-subtle);
      overflow: hidden;
    }
    .quota-bar-fill {
      height: 100%;
      border-radius: 2px;
      background: var(--accent);
      transition: width 0.4s ease;
    }
    .quota-bar-fill.low { background: #ef4444; }
    .quota-bar-fill.mid { background: #f59e0b; }
    .quota-loading {
      font-size: 10px;
      color: var(--text-dim);
      text-align: center;
      padding: 4px 0;
    }

    /* Prism 语法着色与 Xiaomi MiMo 官方高颜值代码卡片 */
    code[class*="language-"], pre[class*="language-"] {
      color: #1E293B;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.6;
      text-align: left;
      white-space: pre;
      word-spacing: normal;
      word-break: normal;
      word-wrap: normal;
      tab-size: 2;
      hyphens: none;
    }
    .token.comment, .token.prolog, .token.doctype, .token.cdata { color: #94A3B8; font-style: italic; }
    .token.punctuation { color: #64748B; }
    .token.property, .token.tag, .token.boolean, .token.number, .token.constant, .token.symbol, .token.deleted { color: #D97706; }
    .token.selector, .token.attr-name, .token.string, .token.char, .token.builtin, .token.inserted { color: #16A34A; }
    .token.operator, .token.entity, .token.url, .language-css .token.string, .style .token.string { color: #0284C7; }
    .token.atrule, .token.attr-value, .token.keyword { color: #7C3AED; font-weight: 600; }
    .token.function, .token.class-name { color: #2563EB; font-weight: 500; }
    .token.regex, .token.important, .token.variable { color: #E11D48; }
    .token.inserted-sign { background-color: rgba(34, 197, 94, 0.15); color: #15803D; display: block; }
    .token.deleted-sign { background-color: rgba(239, 68, 68, 0.15); color: #B91C1C; display: block; }

    .mimo-code-card {
      background: var(--bg-code);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      margin: 12px 0;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .code-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 14px;
      background: #ECEFF2;
      border-bottom: 1px solid var(--border-subtle);
      font-size: 11.5px;
      color: var(--text-muted);
      font-family: var(--font-mono);
      font-weight: 600;
      letter-spacing: 0.5px;
    }
    .btn-copy-code {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      color: var(--text-muted);
      cursor: pointer;
      background: rgba(255,255,255,0.7);
      border: 1px solid var(--border-subtle);
      padding: 3px 8px;
      border-radius: 5px;
      transition: all 0.15s ease;
    }
    .btn-copy-code:hover, .btn-copy-code:active {
      background: #FFFFFF;
      color: var(--primary);
      border-color: var(--primary);
    }
    .btn-copy-code.copied {
      color: #16A34A;
      border-color: #16A34A;
      background: rgba(22, 163, 74, 0.08);
    }
    .code-card-body {
      padding: 12px 14px;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.6;
    }
    .code-card-body pre {
      margin: 0;
      padding: 0;
      background: transparent;
      border: none;
    }

    /* 消息视窗 */
    #chat-viewport {
      flex: 1;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 18px 16px max(140px, calc(env(safe-area-inset-bottom) + 120px));
      max-width: 840px;
      margin: 0 auto;
      width: 100%;
      -webkit-overflow-scrolling: touch;
      scroll-behavior: auto;
    }

    .msg-user-container {
      display: flex;
      justify-content: flex-end;
      margin-bottom: 20px;
    }
    .user-bubble {
      background: #F3F4F6;
      color: var(--text-main);
      padding: 11px 15px;
      border-radius: 18px 18px 4px 18px;
      font-size: 14.5px;
      line-height: 1.55;
      border: 1px solid var(--border-subtle);
      max-width: 86%;
      word-break: break-word;
      position: relative;
    }
    .user-bubble-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 6px;
      padding-top: 5px;
      border-top: 1px dashed rgba(0,0,0,0.08);
      font-size: 11px;
      color: var(--text-muted);
    }
    .btn-bubble-action {
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 2px 4px;
      border-radius: 4px;
      font-size: 11px;
    }
    .btn-bubble-action:hover {
      color: var(--primary);
      background: rgba(0,0,0,0.04);
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
    .assistant-prose-card > *:first-child { margin-top: 0; }
    .assistant-prose-card > *:last-child { margin-bottom: 0; }
    .assistant-prose-card h1,
    .assistant-prose-card h2,
    .assistant-prose-card h3,
    .assistant-prose-card h4 {
      color: var(--text-main);
      margin: 16px 0 8px;
      font-weight: 600;
      line-height: 1.35;
    }
    .assistant-prose-card h1 { font-size: 19px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 5px; }
    .assistant-prose-card h2 { font-size: 16.5px; }
    .assistant-prose-card h3 { font-size: 15px; }
    .assistant-prose-card h4 { font-size: 14px; }
    .assistant-prose-card p { margin: 8px 0; }
    .assistant-prose-card ul,
    .assistant-prose-card ol {
      margin: 8px 0 8px 1.4em;
      padding: 0;
    }
    .assistant-prose-card li { margin: 4px 0; line-height: 1.6; }
    .assistant-prose-card blockquote {
      border-left: 3.5px solid var(--primary);
      margin: 10px 0;
      padding: 6px 14px;
      background: rgba(37, 99, 235, 0.04);
      color: #475569;
      border-radius: 0 6px 6px 0;
      font-size: 13.5px;
    }
    .assistant-prose-card a {
      color: var(--mimo-cyan-txt);
      text-decoration: underline;
      text-underline-offset: 2.5px;
    }
    .assistant-prose-card hr {
      border: none;
      border-top: 1px solid var(--border-subtle);
      margin: 16px 0;
    }
    .assistant-prose-card code:not([class*="language-"]) {
      background: #F1F3F5;
      color: #9D174D;
      padding: 2px 5px;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 12.5px;
    }
    .table-responsive {
      width: 100%;
      overflow-x: auto;
      margin: 12px 0;
      -webkit-overflow-scrolling: touch;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
    }
    .table-responsive table, .mimo-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      line-height: 1.5;
    }
    .table-responsive th, .table-responsive td, .mimo-table th, .mimo-table td {
      padding: 8px 12px;
      border-bottom: 1px solid var(--border-subtle);
      text-align: left;
    }
    .table-responsive th, .mimo-table th {
      background: #F8FAFC;
      font-weight: 600;
      color: var(--text-main);
    }
    .table-responsive tr:last-child td, .mimo-table tr:last-child td {
      border-bottom: none;
    }

    /* 思考折叠条 (Thinking Process) */
    .thinking-box {
      margin: 10px 0;
      border-radius: 9px;
      background: #F8FAFC;
      border: 1px solid #E2E8F0;
      overflow: hidden;
      transition: all 0.2s ease;
    }
    .thinking-box.live {
      border-color: #BFDBFE;
      background: rgba(239, 246, 255, 0.6);
      box-shadow: 0 2px 8px rgba(37, 99, 235, 0.06);
    }
    .thinking-toggle {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
    }
    .thinking-toggle-left {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .thinking-toggle-badge {
      font-size: 10px;
      color: var(--primary);
      background: rgba(37, 99, 235, 0.08);
      padding: 1px 6px;
      border-radius: 10px;
      font-weight: 500;
    }
    .thinking-toggle-arrow {
      font-size: 10px;
      color: var(--text-dim);
      transition: transform 0.2s ease;
    }
    .thinking-box.open .thinking-toggle-arrow {
      transform: rotate(180deg);
    }
    .thinking-content {
      display: none;
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.6;
      color: #475569;
      background: #F1F5F9;
      white-space: pre-wrap;
      font-family: var(--font-mono);
      border-top: 1px solid #E2E8F0;
      max-height: 280px;
      overflow-y: auto;
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
      transition: border-color 0.15s ease;
    }
    .mimo-tool-card.running {
      border-color: #BAE6FD;
      box-shadow: 0 2px 8px rgba(2, 132, 199, 0.06);
    }
    .tool-header-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 12px;
      user-select: none;
    }
    .tool-header-left {
      display: flex;
      align-items: center;
      min-width: 0;
      flex: 1;
      margin-right: 8px;
    }
    .tool-icon-badge {
      font-size: 13px;
      margin-right: 6px;
      display: inline-flex;
      align-items: center;
    }
    .tool-badge {
      background: #E2E8F0;
      color: #334155;
      font-weight: 600;
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 4px;
      font-family: var(--font-mono);
      margin-right: 8px;
      flex-shrink: 0;
    }
    .tool-cmd-preview {
      font-family: var(--font-mono);
      color: var(--text-body);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 240px;
      font-size: 11.5px;
    }
    .tool-header-right {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }
    .tool-status {
      font-size: 11px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 2px 8px;
      border-radius: 12px;
      font-weight: 500;
      flex-shrink: 0;
    }
    .tool-status.running {
      color: #0284C7;
      background: rgba(2, 132, 199, 0.08);
    }
    .tool-status.running .tool-status-icon {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #0284C7;
      box-shadow: 0 0 0 0 rgba(2, 132, 199, 0.6);
      animation: toolPulseDot 1.4s infinite cubic-bezier(0.66, 0, 0, 1);
      display: inline-block;
    }
    @keyframes toolPulseDot {
      to { box-shadow: 0 0 0 7px rgba(2, 132, 199, 0); }
    }
    .tool-status.completed {
      color: #16A34A;
      background: rgba(22, 163, 74, 0.08);
    }
    .tool-status.completed .tool-status-icon {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #16A34A;
      display: inline-block;
    }
    .tool-status.error, .tool-status.failed {
      color: #DC2626;
      background: rgba(220, 38, 38, 0.08);
    }
    .tool-chevron {
      font-size: 10px;
      color: var(--text-dim);
      transition: transform 0.2s ease;
    }
    .mimo-tool-card.open .tool-chevron {
      transform: rotate(180deg);
    }
    .tool-console-box {
      display: none;
      background: #0F172A;
      color: #E2E8F0;
      border-top: 1px solid var(--border-subtle);
      font-family: var(--font-mono);
      font-size: 11.5px;
      line-height: 1.6;
      max-height: 260px;
      overflow-y: auto;
      word-break: break-all;
    }
    .mimo-tool-card.open .tool-console-box {
      display: block;
    }
    .tool-console-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 12px;
      background: #1E293B;
      color: #94A3B8;
      font-size: 10.5px;
      border-bottom: 1px solid #334155;
    }
    .btn-copy-tool {
      background: transparent;
      border: 1px solid #475569;
      color: #CBD5E1;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      cursor: pointer;
    }
    .btn-copy-tool:hover { background: #334155; }
    .tool-output-pre {
      margin: 0;
      padding: 10px 12px;
      white-space: pre-wrap;
      font-family: inherit;
    }

    /* 极简思考状态提示 */
    .mimo-thinking-text {
      font-size: 14px;
      color: var(--text-muted, #86868B);
      padding: 6px 4px;
      margin: 2px 0 6px 0;
      display: inline-flex;
      align-items: center;
      line-height: 1.5;
      user-select: none;
      animation: fadeInThinking 0.25s ease-out;
    }
    @keyframes fadeInThinking {
      from { opacity: 0; transform: translateY(2px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .dot-pulse {
      display: inline-block;
      letter-spacing: 2px;
      animation: dotPulse 1.4s infinite ease-in-out;
    }
    @keyframes dotPulse {
      0%, 20% { opacity: 0.25; }
      50% { opacity: 1; }
      100% { opacity: 0.25; }
    }

    /* 任务进行中：顶部常驻动效 */
    .task-live-top {
      display: none;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      font-weight: 600;
      color: #1D4ED8;
      user-select: none;
      pointer-events: none;
      z-index: 45;
      position: fixed;
      top: 52px;
      left: 0;
      right: 0;
      height: 36px;
      padding: 0 16px;
      justify-content: center;
      background: linear-gradient(90deg, #EFF6FF 0%, #EDE9FE 45%, #EFF6FF 100%);
      background-size: 200% 100%;
      border-bottom: 1px solid #DBEAFE;
    }
    .task-live-top.show {
      display: flex;
      animation: taskLiveIn 0.22s ease-out, taskShimmer 1.8s linear infinite;
    }
    @keyframes taskLiveIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes taskShimmer {
      0% { background-position: 0% 50%; }
      100% { background-position: 200% 50%; }
    }
    .task-live-orb {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #3B82F6;
      box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.45);
      animation: taskOrbPulse 1.4s infinite ease-out;
      flex-shrink: 0;
    }
    @keyframes taskOrbPulse {
      0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.45); transform: scale(1); }
      70% { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); transform: scale(1.05); }
      100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); transform: scale(1); }
    }
    .task-live-label { overflow: hidden; text-overflow: ellipsis; }
    .task-live-elapsed {
      color: #3B82F6;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
    }
    .task-live-shimmer {
      width: 42px;
      height: 4px;
      border-radius: 999px;
      background: linear-gradient(90deg, #DBEAFE, #93C5FD, #DBEAFE);
      background-size: 200% 100%;
      animation: taskShimmer 1.2s linear infinite;
      flex-shrink: 0;
    }

    /* 会话抽屉搜索与操作 */
    .drawer-search-wrap {
      padding: 8px 12px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .drawer-search-input {
      width: 100%;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
      background: #FFFFFF;
      font-size: 12.5px;
      outline: none;
      color: var(--text-main);
      box-sizing: border-box;
    }
    .drawer-search-input:focus { border-color: var(--primary); }
    .session-item-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 12px;
      cursor: pointer;
      border-bottom: 1px solid var(--border-light);
      transition: background 0.12s ease;
    }
    .session-item-row:hover { background: var(--bg-hover); }
    .session-item-row.active {
      background: #EFF6FF;
      border-left: 3px solid var(--primary);
    }
    .session-item-main {
      flex: 1;
      min-width: 0;
      margin-right: 8px;
    }
    .session-item-title {
      font-size: 13px;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .session-item-live-badge {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      font-size: 10px;
      color: #ff8c00;
      background: rgba(255, 140, 0, 0.12);
      padding: 1px 6px;
      border-radius: 999px;
      font-weight: 600;
      flex-shrink: 0;
    }
    @media (prefers-color-scheme: dark) {
      .session-item-live-badge {
        color: #ffa94d;
        background: rgba(255, 169, 77, 0.18);
      }
    }
    .session-item-time {
      font-size: 11px;
      color: var(--text-dim);
      margin-top: 2px;
    }
    .session-item-del {
      background: none;
      border: none;
      color: var(--text-dim);
      font-size: 13px;
      padding: 4px 6px;
      border-radius: 4px;
      cursor: pointer;
      line-height: 1;
    }
    .session-item-del:hover {
      color: #DC2626;
      background: rgba(220, 38, 38, 0.08);
    }

    /* 滚动到底悬浮气泡 */
    .scroll-bottom-btn {
      display: none;
      position: fixed;
      left: 50%;
      transform: translateX(-50%);
      bottom: 120px;
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: #FFFFFF;
      border: 1px solid var(--border-subtle);
      box-shadow: 0 4px 16px rgba(0,0,0,0.12);
      color: var(--text-main);
      cursor: pointer;
      z-index: 35;
      align-items: center;
      justify-content: center;
      transition: transform 0.18s ease, opacity 0.18s ease;
    }
    .scroll-bottom-btn.show { display: flex; }
    .scroll-bottom-btn-dot {
      position: absolute;
      top: -2px;
      right: -2px;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #2563EB;
      border: 2px solid #FFFFFF;
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
      flex-wrap: nowrap;
      min-width: 0;
      width: 100%;
      padding-top: 4px;
    }

    .dock-left-group {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 1;
      min-width: 0;
      flex-wrap: nowrap;
    }
    .btn-dock-icon {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      flex-shrink: 0;
    }
    .btn-dock-icon:active {
      background: var(--bg-hover);
      color: var(--text-main);
    }

    .dock-perm-badge {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      color: #EA580C;
      font-size: 12px;
      font-weight: 500;
      padding: 3px 6px;
      border-radius: 6px;
      cursor: pointer;
      user-select: none;
      transition: background 0.15s;
      flex-shrink: 1;
      min-width: 0;
      white-space: nowrap;
    }
    .dock-perm-badge:hover {
      background: #FFF7ED;
    }
    #perm-name-label {
      display: inline-block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 82px;
      line-height: 1.2;
    }

    .dock-right-group {
      display: flex;
      align-items: center;
      gap: 4px;
      flex-shrink: 0;
      min-width: 0;
      flex-wrap: nowrap;
    }

    .dock-model-wrap {
      position: relative;
      display: inline-flex;
      align-items: center;
    }

    .dock-model-selector {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-body);
      background: transparent;
      border: none;
      padding: 3px 6px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
      flex-shrink: 1;
      min-width: 0;
    }
    .dock-model-selector:hover {
      background: var(--bg-hover);
      color: var(--text-main);
    }
    #model-name-label {
      display: inline-block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 135px;
      line-height: 1.2;
    }

    /* 气泡式悬浮模型选择菜单 (紧贴模型按钮，防超出屏幕智能贴靠) */
    .model-popover-menu {
      position: absolute;
      bottom: calc(100% + 8px);
      right: 0;
      width: 260px;
      max-width: calc(100vw - 20px);
      background: #FFFFFF;
      border: 1px solid var(--border-subtle);
      box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.18), 0 4px 12px rgba(0, 0, 0, 0.08);
      border-radius: 14px;
      padding: 10px 8px;
      z-index: 250;
      box-sizing: border-box;
      animation: fadeIn 0.15s ease;
    }
    .model-popover-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 2px 8px 8px;
      border-bottom: 1px solid var(--border-light);
      margin-bottom: 6px;
    }
    .model-popover-title {
      font-size: 12.5px;
      font-weight: 600;
      color: var(--text-main);
    }
    .model-popover-close {
      cursor: pointer;
      color: var(--text-dim);
      font-size: 11px;
      padding: 2px 5px;
      border-radius: 4px;
    }
    .model-popover-close:hover {
      background: rgba(0,0,0,0.05);
      color: var(--text-main);
    }
    .model-popover-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-height: 280px;
      overflow-y: auto;
    }
    .model-popover-item {
      padding: 8px 10px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.12s ease;
    }
    .model-popover-item:hover {
      background: #F8FAFC;
    }
    .model-popover-item.selected {
      background: #FFF7ED;
      border-color: #FED7AA;
    }
    .model-popover-item-title {
      font-size: 12.5px;
      font-weight: 600;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .model-popover-item-desc {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 2px;
      line-height: 1.3;
    }
    .model-popover-item-badge {
      font-size: 10px;
      font-weight: normal;
      padding: 1px 5px;
      border-radius: 4px;
      background: #F1F3F5;
      color: #4B5563;
    }

    .btn-dock-send {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--text-main);
      color: #FFFFFF;
      border: none;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.15s;
      flex-shrink: 0;
    }
    .btn-dock-send.abort {
      background: #EF4444 !important;
      color: #FFFFFF !important;
    }

    /* 移动端与窄屏单行自适应弹性适配 (不换行，放不下自动省略号) */
    @media (max-width: 440px) {
      .floating-mimo-island {
        padding: 8px 10px 8px;
      }
      footer {
        padding: 0 10px 10px;
      }
      .dock-left-group {
        gap: 4px;
      }
      .dock-right-group {
        gap: 3px;
      }
      .dock-perm-badge {
        font-size: 11px;
        padding: 2px 5px;
        gap: 2px;
      }
      #perm-name-label {
        max-width: 66px;
      }
      .dock-model-selector {
        font-size: 11px;
        padding: 2px 5px;
        gap: 2px;
      }
      #model-name-label {
        max-width: 70px;
      }
      .btn-dock-icon {
        width: 24px;
        height: 24px;
      }
      .btn-dock-send {
        width: 26px;
        height: 26px;
      }
    }

    @media (max-width: 360px) {
      .floating-mimo-island {
        padding: 6px 8px 6px;
      }
      footer {
        padding: 0 6px 6px;
      }
      .dock-left-group {
        gap: 2px;
      }
      .dock-right-group {
        gap: 2px;
      }
      .dock-perm-badge {
        font-size: 10.5px;
        padding: 2px 4px;
      }
      #perm-name-label {
        max-width: 50px;
      }
      .dock-model-selector {
        font-size: 10.5px;
        padding: 2px 4px;
      }
      #model-name-label {
        max-width: 54px;
      }
      .btn-dock-icon {
        width: 22px;
        height: 22px;
      }
      .btn-dock-send {
        width: 24px;
        height: 24px;
      }
    }

    .dock-disclaimer {
      font-size: 11px;
      color: var(--text-dim);
      text-align: center;
      margin-top: 6px;
      pointer-events: auto;
      user-select: none;
    }

    /* 上下文用量指示器 HUD 样式 */
    .ctx-hud-btn {
      background: none;
      border: none;
      padding: 3px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--text-dim);
      border-radius: 50%;
      transition: color 0.15s, background 0.15s;
    }
    .ctx-hud-btn:hover {
      color: var(--text-main);
      background: rgba(0, 0, 0, 0.05);
    }
    .ctx-hud-ring {
      display: block;
    }
    .ctx-hud-popover {
      position: absolute;
      bottom: calc(100% + 10px);
      right: 0;
      width: 230px;
      background: #FFFFFF;
      border: 1px solid #E5E7EB;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
      border-radius: 14px;
      padding: 12px 14px;
      z-index: 200;
      box-sizing: border-box;
      font-size: 12px;
      animation: fadeIn 0.15s ease;
    }
    .ctx-hud-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .ctx-hud-title {
      font-weight: 600;
      color: var(--text-main);
      font-size: 12.5px;
    }
    .ctx-hud-close {
      cursor: pointer;
      color: var(--text-dim);
      font-size: 11px;
      padding: 2px 5px;
      border-radius: 4px;
    }
    .ctx-hud-close:hover {
      background: rgba(0,0,0,0.05);
      color: var(--text-main);
    }
    .ctx-hud-pct-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 6px;
    }
    .ctx-hud-pct-val {
      font-size: 18px;
      font-weight: 700;
      color: var(--text-main);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .ctx-hud-pct-rem {
      font-size: 11.5px;
      color: var(--text-muted);
    }
    .ctx-hud-bar-bg {
      height: 5px;
      background: #E5E7EB;
      border-radius: 3px;
      overflow: hidden;
      margin-bottom: 8px;
    }
    .ctx-hud-bar-fill {
      height: 100%;
      border-radius: 3px;
      background: var(--primary);
      transition: width 0.3s ease;
    }
    .ctx-hud-tokens {
      font-size: 11.5px;
      color: var(--text-muted);
      margin-bottom: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .ctx-hud-cache {
      font-size: 11px;
      color: #059669;
      font-weight: 500;
      background: rgba(16, 185, 129, 0.1);
      padding: 2px 6px;
      border-radius: 4px;
      display: inline-block;
      margin-top: 4px;
    }
    .ctx-hud-model {
      font-size: 11px;
      color: var(--text-dim);
      margin-top: 6px;
    }

    /* 语音录音脉冲动画与提示 */
    .btn-dock-icon.recording {
      color: #FF6900 !important;
      background: rgba(255, 105, 0, 0.12) !important;
      animation: micPulse 1.2s infinite ease-in-out;
    }
    @keyframes micPulse {
      0% { box-shadow: 0 0 0 0 rgba(255, 105, 0, 0.4); }
      70% { box-shadow: 0 0 0 8px rgba(255, 105, 0, 0); }
      100% { box-shadow: 0 0 0 0 rgba(255, 105, 0, 0); }
    }
    .voice-cues-drawer {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      background: rgba(255, 105, 0, 0.08);
      border-radius: 8px;
      margin: 4px 10px 6px;
      font-size: 11.5px;
      color: #EA580C;
      font-weight: 500;
      animation: fadeIn 0.2s ease;
    }
    .voice-cue-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #EA580C;
      display: inline-block;
      animation: micPulse 1s infinite;
    }

    /* 插件中心样式 */
    .plugins-box {
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      border-radius: 20px 20px 0 0;
      padding: 20px 18px 24px;
    }
    .plugin-tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }
    .plugin-tab {
      padding: 5px 14px;
      border-radius: 20px;
      border: 1px solid #E5E7EB;
      background: #F9FAFB;
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
      white-space: nowrap;
    }
    .plugin-tab.active {
      background: #111827;
      color: #FFFFFF;
      border-color: #111827;
      font-weight: 600;
    }
    .plugins-scroll-list {
      overflow-y: auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding-bottom: 12px;
    }
    .plugin-card {
      background: #FFFFFF;
      border: 1px solid #E5E7EB;
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: border-color 0.15s;
    }
    .plugin-card:hover {
      border-color: #D1D5DB;
      box-shadow: 0 2px 8px rgba(0,0,0,0.03);
    }
    .plugin-card-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .plugin-info {
      flex: 1;
      min-width: 0;
    }
    .plugin-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;
    }
    .plugin-icon {
      font-size: 16px;
    }
    .plugin-name {
      font-size: 13.5px;
      font-weight: 600;
      color: var(--text-main);
    }
    .plugin-desc {
      font-size: 12px;
      color: var(--text-dim);
      line-height: 1.45;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .switch-toggle {
      position: relative;
      display: inline-block;
      width: 40px;
      height: 22px;
      flex-shrink: 0;
    }
    .switch-toggle input {
      opacity: 0;
      width: 0;
      height: 0;
    }
    .slider {
      position: absolute;
      cursor: pointer;
      inset: 0;
      background-color: #E5E7EB;
      transition: .2s;
      border-radius: 22px;
    }
    .slider:before {
      position: absolute;
      content: "";
      height: 18px;
      width: 18px;
      left: 2px;
      bottom: 2px;
      background-color: white;
      transition: .2s;
      border-radius: 50%;
      box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    .switch-toggle input:checked + .slider {
      background-color: #10B981;
    }
    .switch-toggle input:checked + .slider:before {
      transform: translateX(18px);
    }


    
    /* 附件预览行 */
    .attached-files-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 12px 2px;
      max-height: 120px;
      overflow-y: auto;
    }
    .attached-file-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #F3F4F6;
      border: 1px solid #E5E7EB;
      border-radius: 8px;
      padding: 3px 8px;
      font-size: 11.5px;
      color: var(--text-main);
      max-width: 220px;
    }
    .attached-file-chip span {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .attached-file-thumb {
      width: 24px;
      height: 24px;
      border-radius: 4px;
      object-fit: cover;
    }
    .attached-file-del {
      cursor: pointer;
      color: var(--text-muted);
      font-size: 12px;
      margin-left: 2px;
      font-weight: bold;
    }
    .attached-file-del:hover {
      color: #EF4444;
    }

    /* 权限徽章色彩状态 */
    .dock-perm-badge.amber {
      color: #D97706 !important;
      background: rgba(217, 119, 6, 0.08) !important;
    }
    .dock-perm-badge.blue {
      color: #2563EB !important;
      background: rgba(37, 99, 235, 0.08) !important;
    }
    .dock-perm-badge.gray {
      color: #4B5563 !important;
      background: rgba(107, 114, 128, 0.08) !important;
    }

    /* 产物中心模态窗样式 */
    .artifacts-box {
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      border-radius: 20px 20px 0 0;
      padding: 20px 18px 24px;
    }
    .artifact-tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
      overflow-x: auto;
    }
    .artifact-tab {
      padding: 5px 14px;
      border-radius: 20px;
      border: 1px solid #E5E7EB;
      background: #F9FAFB;
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
      white-space: nowrap;
    }
    .artifact-tab.active {
      background: #111827;
      color: #FFFFFF;
      border-color: #111827;
      font-weight: 600;
    }
    .artifact-search-box {
      margin-bottom: 12px;
    }
    .artifact-search-box input {
      width: 100%;
      box-sizing: border-box;
      padding: 8px 12px;
      border-radius: 10px;
      border: 1px solid #E5E7EB;
      background: #F9FAFB;
      font-size: 12.5px;
      outline: none;
    }
    .artifacts-scroll-list {
      overflow-y: auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding-bottom: 12px;
    }
    .artifact-card {
      background: #FFFFFF;
      border: 1px solid #E5E7EB;
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .artifact-card:hover {
      border-color: #D1D5DB;
      box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .artifact-card-top {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
    }
    .artifact-card-title {
      font-size: 13.5px;
      font-weight: 600;
      color: var(--text-main);
      line-height: 1.35;
    }
    .artifact-badge {
      padding: 2px 7px;
      border-radius: 6px;
      font-size: 10.5px;
      font-weight: 600;
      flex-shrink: 0;
    }
    .badge-doc { background: #EFF6FF; color: #2563EB; }
    .badge-app { background: #FFF7ED; color: #EA580C; }
    .badge-other { background: #F3F4F6; color: #4B5563; }
    .artifact-card-meta {
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .artifact-card-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-top: 6px;
      border-top: 1px solid #F3F4F6;
    }
    .btn-artifact-action {
      padding: 4px 10px;
      border-radius: 7px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      border: 1px solid #E5E7EB;
      background: #FFFFFF;
      color: var(--text-main);
      display: inline-flex;
      align-items: center;
      gap: 3px;
      text-decoration: none;
    }
    .btn-artifact-action.primary {
      background: var(--mimo-orange);
      color: #FFFFFF;
      border-color: var(--mimo-orange);
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
      max-width: 600px;
      margin: 0 auto;
      box-sizing: border-box;
      background: #FFFFFF;
      border-radius: 20px 20px 0 0;
      padding: 20px 18px 30px;
      box-shadow: 0 -8px 32px rgba(0,0,0,0.12);
      max-height: 85vh;
      overflow-y: auto;
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

    /* ── 手机端原生全能模型抽屉 (Mobile Native Model Sheet) ── */
    .model-sheet-box {
      width: 100%;
      max-width: 600px;
      margin: 0 auto;
      box-sizing: border-box;
      background: #FFFFFF;
      border-radius: 24px 24px 0 0;
      padding: 12px 18px 28px;
      box-shadow: 0 -10px 40px rgba(0,0,0,0.18);
      max-height: 82vh;
      display: flex;
      flex-direction: column;
      animation: sheetSlideUp 0.24s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes sheetSlideUp {
      from { transform: translateY(100%); }
      to { transform: translateY(0); }
    }
    .sheet-drag-handle {
      width: 36px;
      height: 4px;
      background: #CBD5E1;
      border-radius: 2px;
      margin: 2px auto 12px;
      flex-shrink: 0;
    }
    .model-active-tag {
      font-size: 11px;
      font-weight: 600;
      color: var(--primary);
      background: #FFF7ED;
      border: 1px solid #FFEDD5;
      padding: 2px 8px;
      border-radius: 999px;
    }
    .model-sheet-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 12px;
      line-height: 1.4;
    }
    .model-category-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--border-light);
      padding-bottom: 8px;
      flex-shrink: 0;
    }
    .model-cat-tab {
      padding: 5px 12px;
      border-radius: 16px;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid var(--border-subtle);
      background: #F8F9FA;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .model-cat-tab.active {
      background: var(--text-main);
      color: #FFFFFF;
      border-color: var(--text-main);
    }
    .model-sheet-cards-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow-y: auto;
      flex: 1;
      padding-right: 2px;
      -webkit-overflow-scrolling: touch;
    }
    .model-card-item {
      padding: 12px 14px;
      border-radius: 14px;
      background: #FFFFFF;
      border: 1.5px solid #F1F3F5;
      cursor: pointer;
      display: flex;
      align-items: stretch;
      transition: all 0.15s ease;
      position: relative;
    }
    .model-card-item:hover {
      background: #FAFAFA;
      border-color: #E2E8F0;
    }
    .model-card-item.selected {
      background: #FFF9F5;
      border-color: #FF6900;
      box-shadow: 0 3px 12px rgba(255, 105, 0, 0.12);
    }
    .model-card-stripe {
      width: 4px;
      border-radius: 4px;
      background: #E2E8F0;
      margin-right: 12px;
      flex-shrink: 0;
      transition: background 0.15s ease;
    }
    .model-card-item.selected .model-card-stripe {
      background: #FF6900;
    }
    .model-card-body {
      flex: 1;
      min-width: 0;
    }
    .model-card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      margin-bottom: 4px;
    }
    .model-card-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .model-card-badges {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 6px;
    }
    .model-badge-chip {
      font-size: 10px;
      font-weight: 600;
      padding: 1.5px 6px;
      border-radius: 4px;
    }
    .badge-orange { background: #FFEDD5; color: #C2410C; }
    .badge-cyan { background: #E0F2FE; color: #0369A1; }
    .badge-blue { background: #EFF6FF; color: #1D4ED8; }
    .badge-purple { background: #F3E8FF; color: #7E22CE; }
    .badge-gray { background: #F1F3F5; color: #4B5563; }
    .model-card-desc {
      font-size: 11.5px;
      color: var(--text-muted);
      line-height: 1.4;
      margin-bottom: 6px;
    }
    .model-card-caps {
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .model-cap-pill {
      font-size: 10px;
      color: var(--text-muted);
      background: #F3F4F6;
      padding: 1px 6px;
      border-radius: 4px;
    }
    .model-check-circle {
      width: 22px;
      height: 22px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 700;
      flex-shrink: 0;
      margin-left: 10px;
      align-self: center;
      border: 1.5px solid #CBD5E1;
      color: transparent;
      transition: all 0.15s ease;
    }
    .model-card-item.selected .model-check-circle {
      background: #FF6900;
      border-color: #FF6900;
      color: #FFFFFF;
      box-shadow: 0 2px 6px rgba(255, 105, 0, 0.35);
    }
    .model-sheet-footer {
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--border-light);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    .model-default-toggle-label {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--text-muted);
      cursor: pointer;
    }
    .session-model-pill {
      display: inline-flex;
      align-items: center;
      font-size: 10px;
      font-weight: 600;
      padding: 1px 5px;
      border-radius: 4px;
      background: #F1F5F9;
      color: #475569;
      margin-left: 6px;
      border: 1px solid #E2E8F0;
      vertical-align: middle;
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

    /* ── Desktop / 原生双栏体验 ───────────────────────────── */
    .desktop-only { display: none; }
    .btn-icon:focus-visible,
    .btn-dock-send:focus-visible,
    .btn-dock-icon:focus-visible,
    .btn-new-task-top:focus-visible,
    .sidebar-action-btn:focus-visible,
    .session-item-row:focus-visible,
    .btn-feedback-action:focus-visible,
    .dock-model-selector:focus-visible,
    .dock-perm-badge:focus-visible {
      outline: 2px solid var(--mimo-orange);
      outline-offset: 2px;
    }
    @media (hover: hover) {
      .btn-icon:hover { background: var(--bg-hover); color: var(--text-main); }
      .btn-new-task-top:hover { background: #E5E7EB; }
      .btn-dock-icon:hover { background: var(--bg-hover); color: var(--text-main); }
      .btn-dock-send:hover { transform: scale(1.06); }
      .session-item-row:hover { background: var(--bg-hover); }
    }

    /* 会话分组 */
    .session-group-label {
      padding: 12px 12px 4px;
      font-size: 11px;
      font-weight: 600;
      color: var(--text-dim);
      letter-spacing: 0.02em;
      user-select: none;
    }

    /* 欢迎态 + 建议任务 */
    .welcome-block {
      padding: 28px 4px 8px;
    }
    .welcome-title {
      font-size: 22px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.3px;
      margin-bottom: 8px;
    }
    .welcome-sub {
      font-size: 13.5px;
      color: var(--text-muted);
      line-height: 1.6;
      margin-bottom: 18px;
      max-width: 520px;
    }
    .suggest-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 10px;
    }
    .suggest-chip {
      text-align: left;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 12px 14px;
      cursor: pointer;
      transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
    }
    .suggest-chip:hover {
      border-color: #FED7AA;
      box-shadow: 0 4px 14px rgba(255, 105, 0, 0.08);
    }
    .suggest-chip:active { transform: scale(0.98); }
    .suggest-chip-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-main);
      margin-bottom: 4px;
    }
    .suggest-chip-desc {
      font-size: 11.5px;
      color: var(--text-muted);
      line-height: 1.45;
    }

    /* Markdown 增强（列表 / 标题 / 链接） */
    .assistant-prose-card h1,
    .assistant-prose-card h2,
    .assistant-prose-card h3 {
      color: var(--text-main);
      margin: 14px 0 8px;
      line-height: 1.3;
    }
    .assistant-prose-card h1 { font-size: 18px; }
    .assistant-prose-card h2 { font-size: 16px; }
    .assistant-prose-card h3 { font-size: 14.5px; }
    .assistant-prose-card ul,
    .assistant-prose-card ol {
      margin: 8px 0 8px 1.2em;
      padding: 0;
    }
    .assistant-prose-card li { margin: 4px 0; line-height: 1.6; }
    .assistant-prose-card a {
      color: var(--mimo-cyan-txt);
      text-decoration: underline;
      text-underline-offset: 2px;
    }
    .assistant-prose-card hr {
      border: none;
      border-top: 1px solid var(--border-subtle);
      margin: 14px 0;
    }

    /* 连接状态点 */
    .conn-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #16A34A;
      box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.15);
    }
    .conn-dot.warn { background: #F59E0B; box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.15); }
    .conn-dot.err { background: #EF4444; box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.15); }

    /* 滚动到底提示 */
    .scroll-bottom-btn {
      display: none;
      position: absolute;
      left: 50%;
      transform: translateX(-50%);
      bottom: 118px;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: #FFFFFF;
      border: 1px solid var(--border-subtle);
      box-shadow: 0 4px 14px rgba(0,0,0,0.1);
      color: var(--text-muted);
      cursor: pointer;
      z-index: 35;
      align-items: center;
      justify-content: center;
    }
    .scroll-bottom-btn.show { display: flex; }

    @media (min-width: 920px) {
      .desktop-only { display: inline-flex; }
      .drawer {
        transform: none;
        box-shadow: none;
        z-index: 20;
        width: 280px;
      }
      .drawer-overlay { display: none !important; }
      body.sidebar-collapsed .drawer {
        transform: translateX(-100%);
      }
      #chat-viewport {
        margin-left: 280px;
        max-width: calc(820px + 280px);
        padding: 24px 32px 150px;
      }
      body.sidebar-collapsed #chat-viewport {
        margin-left: 0;
        max-width: 820px;
      }
      footer {
        left: 280px;
        right: 0;
        padding-bottom: 18px;
      }
      body.sidebar-collapsed footer {
        left: 0;
      }
      header {
        padding-left: 294px;
      }
      body.sidebar-collapsed header {
        padding-left: 14px;
      }
      .user-bubble { max-width: 78%; }
      .welcome-title { font-size: 28px; }
      .suggest-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 640px; }
      .tool-cmd-preview { max-width: 420px; }
      .floating-mimo-island {
        max-width: 780px;
        border-radius: 22px;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
    }
  
    /* ── 移动端专属上下文看板 (任务清单 5/8 + 代码变更) ──────────────── */
    .mimo-context-ribbon {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-light);
      overflow-x: auto;
      white-space: nowrap;
      scrollbar-width: none;
      -webkit-overflow-scrolling: touch;
      z-index: 10;
    }
    .mimo-context-ribbon::-webkit-scrollbar { display: none; }
    
    .context-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      border: 1px solid var(--border-light);
      background: var(--bg-hover);
      color: var(--text-main);
      transition: all 0.15s ease;
      user-select: none;
      flex-shrink: 0;
    }
    .context-pill:active { transform: scale(0.97); }
    .context-pill-task {
      border-color: rgba(16, 185, 129, 0.3);
      background: rgba(16, 185, 129, 0.08);
      color: #059669;
    }
    .context-pill-task .pill-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10B981;
      display: inline-block;
    }
    .context-pill-task .pill-dot.pulse {
      animation: pulse-ring 1.8s infinite;
    }
    .context-pill-git {
      border-color: rgba(59, 130, 246, 0.3);
      background: rgba(59, 130, 246, 0.08);
      color: #2563EB;
    }
    .diff-tag-add { color: #16A34A; font-weight: 600; margin-left: 2px; }
    .diff-tag-del { color: #DC2626; font-weight: 600; margin-left: 2px; }
    .pill-arrow { font-size: 13px; opacity: 0.6; margin-left: 2px; }

    /* ── 底部抽屉模态框 (Bottom Sheet) ────────────────────────── */
    .mimo-sheet-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(4px);
      z-index: 1000;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.25s ease;
    }
    .mimo-sheet-overlay.open {
      opacity: 1;
      pointer-events: auto;
    }
    .mimo-bottom-sheet {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      max-height: 78vh;
      background: var(--bg-surface);
      border-top-left-radius: 20px;
      border-top-right-radius: 20px;
      box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.2);
      z-index: 1001;
      transform: translateY(100%);
      transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border-top: 1px solid var(--border-light);
    }
    .mimo-bottom-sheet.open {
      transform: translateY(0);
    }
    .mimo-sheet-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 18px 12px;
      border-bottom: 1px solid var(--border-light);
      flex-shrink: 0;
    }
    .mimo-sheet-title-row {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .mimo-sheet-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-main);
    }
    .mimo-sheet-badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.12);
      color: #059669;
    }
    .mimo-sheet-badge.diff-summary {
      background: rgba(59, 130, 246, 0.12);
      color: #2563EB;
    }
    .mimo-sheet-close {
      background: none;
      border: none;
      font-size: 18px;
      color: var(--text-dim);
      padding: 4px 8px;
      cursor: pointer;
      border-radius: 6px;
    }
    .mimo-sheet-body {
      padding: 12px 16px 28px;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    
    /* 任务项样式 */
    .task-item-card {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 10px;
      background: var(--bg-hover);
      border: 1px solid var(--border-light);
      font-size: 13px;
      line-height: 1.45;
    }
    .task-item-card.done {
      opacity: 0.72;
    }
    .task-item-card.done .task-item-text {
      text-decoration: line-through;
      color: var(--text-dim);
    }
    .task-item-card.in_progress {
      border-color: #f59e0b;
      background: rgba(245, 158, 11, 0.08);
      font-weight: 600;
    }
    .task-item-icon {
      font-size: 14px;
      flex-shrink: 0;
      margin-top: 1px;
    }
    .task-item-text {
      flex: 1;
      color: var(--text-main);
      word-break: break-word;
    }

    /* 代码变更项样式 */
    .diff-file-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 12px;
      border-radius: 8px;
      background: var(--bg-hover);
      border: 1px solid var(--border-light);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }
    .diff-file-left {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      flex: 1;
    }
    .diff-file-badge {
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 10px;
      background: #3B82F6;
      color: #fff;
    }
    .diff-file-name {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: var(--text-main);
    }

    /* ── 工具卡片极致收敛重构 (单行胶囊 + 纯内嵌展开) ─────────────── */
    .mimo-tool-card {
      border: 1px solid var(--border-light);
      border-radius: 9px;
      margin: 4px 0;
      background: var(--bg-surface);
      overflow: hidden;
      transition: all 0.15s ease;
    }
    .mimo-tool-card:hover {
      border-color: rgba(0, 0, 0, 0.15);
    }
    .tool-header-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 11px;
      cursor: pointer;
      user-select: none;
      background: var(--bg-surface);
      transition: background 0.12s ease;
    }
    .tool-header-row:active {
      background: var(--bg-hover);
    }
    .tool-header-left {
      display: flex;
      align-items: center;
      gap: 7px;
      min-width: 0;
      flex: 1;
      margin-right: 8px;
    }
    .tool-icon-badge {
      font-size: 12.5px;
      flex-shrink: 0;
    }
    .tool-cmd-preview {
      font-size: 12.5px;
      font-weight: 500;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tool-header-right {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }
    .tool-chevron {
      font-size: 12px;
      color: var(--text-dim);
      transition: transform 0.2s ease;
    }
    .mimo-tool-card.open .tool-chevron {
      transform: rotate(180deg);
    }
    
    /* 控制台日志默认彻底折叠，严禁强制铺屏 */
    .tool-console-box {
      display: none;
      background: #141417;
      border-top: 1px solid #27272a;
    }
    .mimo-tool-card.open .tool-console-box {
      display: block;
    }
    .tool-console-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 12px;
      background: #1c1c21;
      font-size: 11px;
      color: #9ca3af;
      border-bottom: 1px solid #27272a;
    }
    .tool-output-pre {
      margin: 0;
      padding: 10px 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 11.5px;
      line-height: 1.45;
      color: #e4e4e7;
      white-space: pre;
      word-break: normal;
      overflow-x: auto;
      max-height: 260px;
      -webkit-overflow-scrolling: touch;
    }
    .tool-output-pre code {
      background: none;
      padding: 0;
      color: inherit;
    }

    /* ── 移动端极致响应式适配大解放 ──────────────────────────── */
    @media (max-width: 600px) {
      .mimo-brand-badge {
        display: none !important;
      }
      .header-left {
        gap: 8px;
        flex: 1;
        min-width: 0;
      }
      .session-title-header {
        flex: 1;
        min-width: 0;
        max-width: none !important;
        font-size: 15px;
        font-weight: 600;
        text-align: left;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .btn-new-task-top span {
        display: none;
      }
      .btn-new-task-top {
        padding: 6px;
        width: 32px;
        height: 32px;
        justify-content: center;
        border-radius: 50%;
      }
      .dock-disclaimer {
        display: none !important;
      }
      .floating-mimo-island {
        padding: 8px 12px 6px;
      }
      #dock-input {
        font-size: 14.5px;
        padding: 4px 0 6px;
      }
      .msg-assistant-container {
        padding: 2px 0;
      }
      .thinking-box {
        margin: 4px 0;
        padding: 3px 6px;
      }
    }

</style>
</head>
<body>

  <!-- PWA 原生安装顶部指引 -->
  <div class="install-banner" id="installBanner" onclick="installApp()">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    <span>📲 点击安装 Xiaomi MiMo 到手机桌面 (真 PWA 原生应用，无地址栏)</span>
  </div>

  <div class="http-tip-banner" id="httpTipBanner" style="display:none;" onclick="openHttpsChannel()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
    <span id="httpTipBannerText">当前处于 HTTP 模式。点击一键进入 HTTPS 安全通道即可免浏览器框安装 PWA</span>
  </div>

  <!-- 顶部导航条 -->
  <header>
    <div class="header-left">
      <button class="btn-icon" id="btn-sidebar-toggle" title="切换侧栏 (Ctrl+B)" onclick="toggleSidebar()">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
      <div class="mimo-brand-badge">
        <span class="mimo-brand-title">Xiaomi MIMO</span>
        <span class="mimo-beta-tag">Beta</span>
      </div>
      <div class="session-title-header" id="top-session-title">正在载入...</div>
    </div>
    <div class="header-right">
      <span class="conn-dot desktop-only" id="conn-dot" title="与电脑端连接状态"></span>
      <button class="btn-new-task-top" title="新建任务 (Ctrl+N)" onclick="triggerNewSession()">
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
      <div class="sidebar-action-btn" onclick="openPluginsModal()">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg>
        <span>插件与技能</span>
      </div>
      <div class="sidebar-action-btn" onclick="openArtifactsModal()">
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
      <img src="/icons/avatar.png" class="sidebar-user-avatar" id="user-avatar-img" alt="Avatar"
           onclick="toggleWeeklyUsage(event)" title="点击查看本周用量">
      <span class="sidebar-user-name" id="user-name-label">MiMo</span>
    </div>
  </div>

  <!-- 周用量弹出面板 -->
  <div id="weekly-usage-popover" onclick="event.stopPropagation()">
    <div class="weekly-pop-title">
      <span>📊 近7天 Token 用量</span>
      <span class="weekly-pop-close" onclick="closeWeeklyUsage()">✕</span>
    </div>
    <div class="weekly-chart" id="weekly-chart-bars">
      <!-- JS 动态渲染 -->
    </div>
    <div class="weekly-stats">
      <div class="weekly-stat-item">
        <div class="weekly-stat-val" id="weekly-today-val">—</div>
        <div class="weekly-stat-lbl">今日</div>
      </div>
      <div class="weekly-stat-item">
        <div class="weekly-stat-val" id="weekly-week-val">—</div>
        <div class="weekly-stat-lbl">本周合计</div>
      </div>
    </div>
    <!-- 订阅配额剩余量 -->
    <div class="quota-section">
      <div class="quota-label">剩余用量</div>
      <div id="quota-content" class="quota-loading">加载中…</div>
    </div>
  </div>

  <!-- 消息流视窗 -->
  
  <!-- 顶部上下文看板胶囊条 (任务清单 5/8 + 代码变更) -->
  <div class="mimo-context-ribbon" id="mimo-context-ribbon" style="display:none;">
    <div class="context-pill context-pill-task" id="pill-tasks-btn" onclick="openTaskDrawer()">
      <span class="pill-dot" id="pill-tasks-dot"></span>
      <span class="pill-title">任务清单</span>
      <span class="pill-badge" id="pill-tasks-badge">0/0</span>
      <span class="pill-arrow">›</span>
    </div>
    <div class="context-pill context-pill-git" id="pill-git-btn" onclick="openDiffDrawer()" style="display:none;">
      <span class="pill-icon">📄</span>
      <span class="pill-title" id="pill-git-files">0 文件已更改</span>
      <span class="diff-tag-add" id="pill-git-add">+0</span>
      <span class="diff-tag-del" id="pill-git-del">-0</span>
      <span class="pill-arrow">›</span>
    </div>
  </div>

  <div id="chat-viewport">
    <div id="init-loader" class="welcome-block">
      <div class="welcome-title">👋 你好，我是 MiMo</div>
      <div class="welcome-sub">正在同步电脑端会话。你也可以直接描述想执行的编码或系统任务，我会在电脑上为你完成。</div>
      <div class="suggest-grid" id="suggest-grid">
        <button class="suggest-chip" onclick="useSuggestion('帮我梳理一下当前目录的项目结构，并写成 README')">
          <div class="suggest-chip-title">📁 梳理项目结构</div>
          <div class="suggest-chip-desc">扫描当前目录，输出清晰的结构说明</div>
        </button>
        <button class="suggest-chip" onclick="useSuggestion('检查系统里最近的错误日志，并总结可能原因')">
          <div class="suggest-chip-title">🔍 检查系统日志</div>
          <div class="suggest-chip-desc">定位异常并给出可执行的修复建议</div>
        </button>
        <button class="suggest-chip" onclick="useSuggestion('把这份需求整理成可执行的开发任务清单')">
          <div class="suggest-chip-title">📋 拆解开发任务</div>
          <div class="suggest-chip-desc">从需求到步骤，生成可跟进的任务列表</div>
        </button>
        <button class="suggest-chip" onclick="useSuggestion('帮我写一个 Python 脚本自动化处理重复工作')">
          <div class="suggest-chip-title">⚙️ 自动化脚本</div>
          <div class="suggest-chip-desc">把重复操作变成一键可跑的工具</div>
        </button>
      </div>
    </div>
  </div>
  <button class="scroll-bottom-btn" id="scroll-bottom-btn" title="回到底部" onclick="scrollToBottom(true)">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="6 9 12 15 18 9"/></svg>
    <span class="scroll-bottom-btn-dot" id="scroll-unread-dot" style="display:none;"></span>
  </button>

  <!-- 任务进行中：顶部动效条 -->
  <div class="task-live-top" id="task-live-top" aria-live="polite">
    <span class="task-live-orb"></span>
    <span class="task-live-label">MiMo 正在工作</span>
    <span class="task-live-elapsed" id="task-live-top-elapsed">0s</span>
    <span class="task-live-shimmer"></span>
  </div>

  <!-- 1:1 官方浮岛式输入框 (带 完全访问 / MiMo Auto / 动态上下文指示器 / 真实语音输入) -->
  <footer>
    <div class="floating-mimo-island">
      <div class="attached-files-row" id="attached-files-row" style="display:none;"></div>
      <div class="voice-cues-drawer" id="voice-cues-drawer" style="display:none;">
        <span class="voice-cue-dot"></span>
        <span id="voice-cue-text">🎙️ 正在聆听中... 请说话 (再次点击麦克风结束)</span>
      </div>
      <textarea id="dock-input" rows="1" placeholder="描述任务，输入/调用技能..." oninput="autoGrow(this)"></textarea>
      <input type="file" id="dock-file-input" multiple accept="image/*,.pdf,.txt,.md,.py,.js,.html,.json,.docx,.xlsx,.pptx" style="display:none;" onchange="handleFileInputChange(event)">
      
      <div class="dock-controls-bar">
        <div class="dock-left-group">
          <button class="btn-dock-icon" title="添加图片或文件" onclick="document.getElementById('dock-file-input').click()">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          
          <div class="dock-perm-badge amber" id="dock-perm-btn" title="切换审批权限" onclick="togglePermSheet(true)">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span id="perm-name-label">完全访问 ▾</span>
          </div>
        </div>

        <div class="dock-right-group">
          <!-- 上下文用量指示器 (动态环形进度条 + 详情浮层，对接 mimocode.db 真实 token 用量) -->
          <div class="ctx-hud-container" style="position:relative; display:inline-flex; align-items:center;">
            <button class="ctx-hud-btn" id="ctx-hud-btn" title="查看上下文用量" onclick="toggleContextHud(event)">
              <svg class="ctx-hud-ring" viewBox="0 0 16 16" width="18" height="18">
                <circle class="ctx-hud-ring-bg" cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="2.2" opacity="0.25"></circle>
                <circle class="ctx-hud-ring-fg" id="ctx-hud-fg" cx="8" cy="8" r="6" fill="none" stroke="var(--primary)" stroke-width="2.2" stroke-linecap="round" pathLength="100" stroke-dasharray="0 100" transform="rotate(-90 8 8)"></circle>
              </svg>
            </button>
            <div class="ctx-hud-popover" id="ctx-hud-popover" style="display:none;" onclick="event.stopPropagation()">
              <div class="ctx-hud-head">
                <span class="ctx-hud-title">📊 上下文用量</span>
                <span class="ctx-hud-close" onclick="closeContextHud()">✕</span>
              </div>
              <div class="ctx-hud-pct-row">
                <span class="ctx-hud-pct-val" id="ctx-hud-pct-val">0.0%</span>
                <span class="ctx-hud-pct-rem" id="ctx-hud-pct-rem">剩余 100.0%</span>
              </div>
              <div class="ctx-hud-bar-bg">
                <div class="ctx-hud-bar-fill" id="ctx-hud-bar-fill" style="width:0%;"></div>
              </div>
              <div class="ctx-hud-tokens" id="ctx-hud-tokens">已用 0 · 共 200,000</div>
              <div class="ctx-hud-cache" id="ctx-hud-cache" style="display:none;">⚡ 缓存命中率 0%</div>
              <div class="ctx-hud-model" id="ctx-hud-model">模型：MiMo Auto</div>
            </div>
          </div>

          <div class="dock-model-wrap" id="dock-model-wrap">
            <div class="dock-model-selector" onclick="toggleModelMenu(event)" id="dock-model-btn" title="当前模型: MiMo Auto (官方默认)">
              <span id="model-name-label">MiMo Auto</span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
            </div>

            <!-- 紧贴模型按钮的气泡式弹出菜单 (智能屏幕边缘贴靠防溢出) -->
            <div class="model-popover-menu" id="model-popover-menu" style="display:none;" onclick="event.stopPropagation()">
              <div class="model-popover-head">
                <span class="model-popover-title">切换模型</span>
                <span class="model-popover-close" onclick="closeModelMenu(event)">✕</span>
              </div>
              <div class="model-popover-list" id="model-popover-list">
                <div style="padding:12px 8px; text-align:center; color:var(--text-muted); font-size:11.5px;">正在同步模型列表...</div>
              </div>
            </div>
          </div>

          <button class="btn-dock-icon" id="btn-dock-voice" title="语音输入" onclick="toggleVoiceRecording(event)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
          </button>

          <button class="btn-dock-send" id="btn-dock-send" onclick="sendPrompt()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
          </button>
        </div>
      </div>
    </div>
    
    <div class="dock-disclaimer">内容由 AI 生成，请注意核实<span class="desktop-only" style="margin-left:10px;opacity:.7;">Ctrl+N 新建 · Ctrl+B 侧栏 · Ctrl+K 输入 · Esc 关闭</span></div>
  </footer>

  
  <!-- 权限选择弹层 (对接 preferences.json 真实权限模式) -->
  <div class="modal-sheet" id="perm-sheet" onclick="togglePermSheet(false)">
    <div class="modal-box" onclick="event.stopPropagation()">
      <div class="modal-title">
        <span>切换审批权限</span>
        <button class="btn-icon" onclick="togglePermSheet(false)">✕</button>
      </div>
      <div id="perm-sheet-list" style="display:flex; flex-direction:column; gap:8px;">
        <div style="padding:16px; text-align:center; color:var(--text-muted); font-size:13px;">正在同步权限列表...</div>
      </div>
    </div>
  </div>

  <!-- 插件与技能中心模态窗 (官方27项内置技能与系统级扩展) -->
  <div class="modal-sheet" id="plugins-sheet" onclick="togglePluginsSheet(false)">
    <div class="modal-box plugins-box" onclick="event.stopPropagation()">
      <div class="modal-title">
        <div>
          <span style="font-size:16px; font-weight:700;">🧩 插件与技能中心</span>
          <div style="font-size:11.5px; color:var(--text-muted); margin-top:2px; font-weight:normal;">
            Xiaomi MiMo 原生托管的 27+ 项专业技能与自动化扩展
          </div>
        </div>
        <button class="btn-icon" onclick="togglePluginsSheet(false)">✕</button>
      </div>
      <div class="plugin-tabs">
        <button class="plugin-tab active" data-cat="all" onclick="filterPlugins('all', this)">全部</button>
        <button class="plugin-tab" data-cat="office" onclick="filterPlugins('office', this)">Office 办公</button>
        <button class="plugin-tab" data-cat="automation" onclick="filterPlugins('automation', this)">系统自动化</button>
        <button class="plugin-tab" data-cat="research" onclick="filterPlugins('research', this)">科研分析</button>
        <button class="plugin-tab" data-cat="design" onclick="filterPlugins('design', this)">交互设计</button>
        <button class="plugin-tab" data-cat="engineering" onclick="filterPlugins('engineering', this)">代码工程</button>
      </div>
      <div class="artifact-search-box">
        <input type="text" id="plugin-search-input" placeholder="搜索技能、工具或插件，如 docx, browser, python..." oninput="onSearchPlugins(this.value)">
      </div>
      <div class="plugins-scroll-list" id="plugins-scroll-list">
        <div style="padding:24px; text-align:center; color:var(--text-muted); font-size:13px;">正在加载插件列表...</div>
      </div>
    </div>
  </div>

  <!-- 产物中心模态窗 (完整汇总预览下载) -->
  <div class="modal-sheet" id="artifacts-sheet" onclick="toggleArtifactsSheet(false)">
    <div class="modal-box artifacts-box" onclick="event.stopPropagation()">
      <div class="modal-title">
        <div>
          <span style="font-size:16px; font-weight:700;">产物中心</span>
          <div style="font-size:11.5px; color:var(--text-muted); margin-top:2px; font-weight:normal;">
            这里汇总了你在 Xiaomi MiMo 里生成过的全部产物，可预览、下载或回到对话继续
          </div>
        </div>
        <button class="btn-icon" onclick="toggleArtifactsSheet(false)">✕</button>
      </div>
      <div class="artifact-tabs">
        <button class="artifact-tab active" data-cat="all" onclick="filterArtifacts('all', this)">全部</button>
        <button class="artifact-tab" data-cat="doc" onclick="filterArtifacts('doc', this)">文档</button>
        <button class="artifact-tab" data-cat="app" onclick="filterArtifacts('app', this)">应用</button>
        <button class="artifact-tab" data-cat="other" onclick="filterArtifacts('other', this)">其他</button>
      </div>
      <div class="artifact-search-box">
        <input type="text" id="artifact-search-input" placeholder="搜索产物名称或标题..." oninput="onSearchArtifacts(this.value)">
      </div>
      <div class="artifacts-scroll-list" id="artifacts-scroll-list">
        <div style="padding:24px; text-align:center; color:var(--text-muted); font-size:13px;">正在加载产物列表...</div>
      </div>
    </div>
  </div>

  <!-- 手机端原生全能模型抽屉 (Mobile Native Model Sheet) -->
  <div class="modal-sheet" id="model-sheet" onclick="toggleModelSheet(false)">
    <div class="modal-box model-sheet-box" onclick="event.stopPropagation()">
      <div class="sheet-drag-handle"></div>
      <div class="modal-title" style="margin-bottom:4px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px; font-weight:700;">选择 AI 模型</span>
          <span class="model-active-tag" id="sheet-active-model-tag">当前任务生效</span>
        </div>
        <button class="btn-icon" onclick="toggleModelSheet(false)" aria-label="关闭">✕</button>
      </div>
      <div class="model-sheet-subtitle" id="model-sheet-subtitle">
        为当前任务指派专属 AI 模型，或同步设为新建任务的全局默认引擎
      </div>

      <!-- 分类标签过滤器 -->
      <div class="model-category-tabs">
        <button class="model-cat-tab active" data-cat="all" onclick="switchModelCategory('all', this)">全部模型</button>
        <button class="model-cat-tab" data-cat="official" onclick="switchModelCategory('official', this)">官方自研</button>
        <button class="model-cat-tab" data-cat="extended" onclick="switchModelCategory('extended', this)">拓展旗舰</button>
      </div>

      <!-- 动态模型卡片列表 -->
      <div id="model-sheet-list" class="model-sheet-cards-list">
        <div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;">正在同步模型映射列表...</div>
      </div>

      <!-- 底部默认配置开关 -->
      <div class="model-sheet-footer">
        <label class="model-default-toggle-label">
          <input type="checkbox" id="chk-set-default-model" checked>
          <span>同步设为新建任务的默认模型</span>
        </label>
      </div>
    </div>
  </div>

  <script>
    // ── 通用 HTML 转义工具 (彻底避免 escapeHtml is not defined 错误) ──
    function escapeHtml(str) {
      if (!str) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    // ── 滚动与布局（桌面原生体验） ───────────────────────────
    function isNearBottom(vp, threshold = 120) {
      if (!vp) return true;
      return vp.scrollHeight - vp.scrollTop - vp.clientHeight < threshold;
    }

    function scrollToBottom(force = false) {
      const vp = document.getElementById("chat-viewport");
      if (!vp) return;
      const stick = force || isNearBottom(vp);
      if (stick) vp.scrollTop = vp.scrollHeight;
      const btn = document.getElementById("scroll-bottom-btn");
      if (btn) btn.classList.toggle("show", !isNearBottom(vp, 80));
    }

    function setConnState(state) {
      const el = document.getElementById("conn-dot");
      if (!el) return;
      el.className = "conn-dot desktop-only" + (state === "warn" ? " warn" : state === "err" ? " err" : "");
    }

    function isDesktopLayout() {
      return window.matchMedia("(min-width: 920px)").matches;
    }

    function toggleSidebar() {
      if (isDesktopLayout()) {
        document.body.classList.toggle("sidebar-collapsed");
        localStorage.setItem("mimo.sidebarCollapsed", document.body.classList.contains("sidebar-collapsed") ? "1" : "0");
      } else {
        toggleDrawer(true);
      }
    }

    function useSuggestion(text) {
      const inp = document.getElementById("dock-input");
      if (!inp) return;
      inp.value = text;
      autoGrow(inp);
      inp.focus();
      sendPrompt();
    }

    function closeAllSheets() {
      togglePermSheet(false);
      togglePluginsSheet(false);
      toggleArtifactsSheet(false);
      toggleModelSheet(false);
      closeModelMenu();
      closeContextHud();
      closeWeeklyUsage();
      if (!isDesktopLayout()) toggleDrawer(false);
    }

    function focusComposer() {
      const inp = document.getElementById("dock-input");
      if (inp) {
        inp.focus();
        inp.setSelectionRange(inp.value.length, inp.value.length);
      }
    }

    // ── 快捷键（对齐 Desktop） ───────────────────────────────
    document.addEventListener("keydown", function(e) {
      const meta = e.metaKey || e.ctrlKey;
      const key = (e.key || "").toLowerCase();
      if (meta && key === "n") {
        e.preventDefault();
        triggerNewSession();
        return;
      }
      if (meta && key === "b") {
        e.preventDefault();
        toggleSidebar();
        return;
      }
      if (meta && key === "k") {
        e.preventDefault();
        focusComposer();
        return;
      }
      if (e.key === "Escape") {
        closeAllSheets();
        return;
      }
    });

    // Enter 发送 / Shift+Enter 换行（支持中文输入法组合态）
    (function bindComposerKeys() {
      const input = document.getElementById("dock-input");
      if (!input) return;
      input.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
          e.preventDefault();
          sendPrompt();
        }
      });
      input.addEventListener("input", function() {
        try {
          localStorage.setItem("mimo.draft." + (currentSessionId || "default"), input.value);
        } catch (_) {}
      });
      document.getElementById("chat-viewport")?.addEventListener("scroll", function() {
        const btn = document.getElementById("scroll-bottom-btn");
        if (btn) btn.classList.toggle("show", !isNearBottom(this, 80));
      });
    })();

    function restoreDraft() {
      const inp = document.getElementById("dock-input");
      if (!inp) return;
      try {
        const d = localStorage.getItem("mimo.draft." + (currentSessionId || "default"));
        if (d) {
          inp.value = d;
          autoGrow(inp);
        }
      } catch (_) {}
    }

    let currentSessionId = "";
    let selectedModelId = "mimo-auto";
    let selectedModelName = "MiMo Auto";
    let selectedPerm = "完全访问权限";
    let selectedPermName = "完全访问";
    let attachedFiles = [];
    let allArtifacts = [];
    let currentArtifactTab = "all";
    let allPlugins = [];
    let currentPluginTab = "all";
    let isBusy = false;
    let activeSseSource = null;
    let activeToolsMap = {};
    let activeAssistantBox = null;
    let activeProseCard = null;
    let busyPollTimer = null;
    let isContextHudOpen = false;
    let voiceRecognition = null;
    let isVoiceRecording = false;

    // ── 上下文用量 HUD (动态扇区环形进度条 + 浮层明细) ──
    // ── 周用量弹窗 ────────────────────────────────────────────────
    function closeWeeklyUsage() {
      document.getElementById("weekly-usage-popover").classList.remove("open");
    }

    async function toggleWeeklyUsage(e) {
      if (e) e.stopPropagation();
      const pop = document.getElementById("weekly-usage-popover");
      if (pop.classList.contains("open")) {
        pop.classList.remove("open");
        return;
      }
      // 关闭其他弹窗
      closeModelMenu();
      const ctxPop = document.getElementById("ctx-hud-popover");
      if (ctxPop) ctxPop.style.display = "none";

      pop.classList.add("open");
      // 重置配额区块为加载中
      const qEl = document.getElementById("quota-content");
      if (qEl) qEl.innerHTML = '<span class="quota-loading">加载中…</span>';

      // 并行加载 token 用量 + 订阅配额
      Promise.all([
        fetch("/api/weekly-usage").then(r => r.json()).catch(() => null),
        fetch("/api/user-quota").then(r => r.json()).catch(() => null),
      ]).then(([weekData, quotaData]) => {
        if (weekData?.ok) renderWeeklyChart(weekData);
        renderQuota(quotaData);
      });
    }

    function renderWeeklyChart(data) {
      const bars = document.getElementById("weekly-chart-bars");
      if (!bars) return;
      bars.innerHTML = data.days.map(d => {
        const h = Math.max(3, Math.round(d.pct * 0.57));  // max 57px
        const cls = d.is_today ? "today" : (d.tokens > 0 ? "has-data" : "");
        const lblCls = d.is_today ? "today" : "";
        const tip = d.tokens > 0 ? formatTokLocal(d.tokens) : "0";
        return `<div class="weekly-bar-wrap" title="${d.date}: ${tip}">
          <div class="weekly-bar ${cls}" style="height:${h}px"></div>
          <div class="weekly-bar-label ${lblCls}">${d.date.replace(/^0/,"")}</div>
        </div>`;
      }).join("");

      document.getElementById("weekly-today-val").textContent = formatTokLocal(data.total_today);
      document.getElementById("weekly-week-val").textContent = formatTokLocal(data.total_week);
    }

    function formatTokLocal(n) {
      if (!n) return "0";
      if (n >= 1000000) return (n/1000000).toFixed(1) + "M";
      if (n >= 1000) return (n/1000).toFixed(1) + "K";
      return String(n);
    }

    function renderQuota(data) {
      const el = document.getElementById("quota-content");
      if (!el) return;

      if (!data || !data.ok) {
        const reason = data?.reason;
        if (reason === "auth-expired") {
          el.innerHTML = '<span class="quota-loading">登录已过期，请在 app 中重新登录</span>';
        } else if (reason === "no-sso") {
          el.innerHTML = '<span class="quota-loading">请先在 app 中登录小米账号</span>';
        } else {
          el.innerHTML = '<span class="quota-loading">无法获取，请在 app 中查看</span>';
        }
        return;
      }

      const pct = typeof data.percent === "number" ? Math.round(data.percent) : null;
      const resetDate = data.resetDate || "—";
      const period = data.period || "1 周";

      // 进度条颜色
      const fillCls = pct !== null ? (pct <= 15 ? "low" : pct <= 40 ? "mid" : "") : "";
      const pctText = pct !== null ? pct + "%" : "—";

      el.innerHTML = `
        <div class="quota-row">
          <div class="quota-meta">
            <span class="quota-chip">${period}</span>
            <span class="quota-chip">${pctText}</span>
            <span class="quota-expire">${resetDate}</span>
          </div>
        </div>
        <div style="margin-top:6px;display:flex;align-items:center;gap:8px;">
          <div class="quota-bar-bg">
            <div class="quota-bar-fill ${fillCls}" style="width:${pct ?? 0}%"></div>
          </div>
          <span style="font-size:10px;color:var(--text-dim);white-space:nowrap;">剩余 ${pctText}</span>
        </div>
      `;
    }

    // 点击页面其他区域关闭弹窗
    document.addEventListener("click", function(e) {
      const pop = document.getElementById("weekly-usage-popover");
      if (pop && pop.classList.contains("open") && !pop.contains(e.target)) {
        pop.classList.remove("open");
      }
    });

    function toggleContextHud(e) {
      if (e) e.stopPropagation();
      const popover = document.getElementById("ctx-hud-popover");
      if (!popover) return;
      isContextHudOpen = !isContextHudOpen;
      if (isContextHudOpen) {
        closeModelMenu();
        popover.style.display = "block";
        updateContextUsage(currentSessionId);
        // 动态边界自适应贴靠：测量当前弹窗视口位置，防止超出屏幕边缘
        requestAnimationFrame(() => {
          popover.style.transform = "none";
          const rect = popover.getBoundingClientRect();
          const winWidth = window.innerWidth;
          if (rect.right > winWidth - 8) {
            const shift = rect.right - (winWidth - 8);
            popover.style.transform = `translateX(-${shift}px)`;
          } else if (rect.left < 8) {
            const shift = 8 - rect.left;
            popover.style.transform = `translateX(${shift}px)`;
          }
        });
      } else {
        popover.style.display = "none";
      }
    }

    function closeContextHud() {
      const popover = document.getElementById("ctx-hud-popover");
      if (popover) popover.style.display = "none";
      isContextHudOpen = false;
    }

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ctx-hud-container")) {
        closeContextHud();
      }
      if (!e.target.closest(".dock-model-wrap")) {
        closeModelMenu();
      }
    });

    async function updateContextUsage(sessionId) {
      try {
        const url = "/api/context-usage" + (sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : "");
        const r = await fetch(url);
        const d = await r.json();
        if (!d || !d.ok) return;

        const pct = Math.min(100, Math.max(0, d.pct || 0));
        const rem = Math.max(0, (100 - pct).toFixed(1));
        const total = d.total || 0;
        const limit = d.limit || 200000;
        const cacheHit = d.cache_hit || 0;
        const model = d.model || selectedModelName || "mimo-x-pro";

        const fg = document.getElementById("ctx-hud-fg");
        if (fg) {
          fg.setAttribute("stroke-dasharray", `${pct} 100`);
          if (pct >= 85) {
            fg.setAttribute("stroke", "#EF4444");
          } else if (pct >= 60) {
            fg.setAttribute("stroke", "#F59E0B");
          } else {
            fg.setAttribute("stroke", "var(--primary)");
          }
        }

        const pctVal = document.getElementById("ctx-hud-pct-val");
        const pctRem = document.getElementById("ctx-hud-pct-rem");
        const barFill = document.getElementById("ctx-hud-bar-fill");
        const tokensEl = document.getElementById("ctx-hud-tokens");
        const cacheEl = document.getElementById("ctx-hud-cache");
        const modelEl = document.getElementById("ctx-hud-model");

        const totalFmt = d.total_fmt || (total >= 1000 ? (total / 1000).toFixed(1) + "K" : total);
        const limitFmt = d.limit_fmt || (limit >= 1000 ? (limit / 1000).toFixed(0) + "K" : limit);

        if (pctVal) pctVal.textContent = pct.toFixed(1) + "%";
        if (pctRem) pctRem.textContent = `(剩余 ${rem}%)`;
        if (barFill) {
          barFill.style.width = pct + "%";
          barFill.style.background = pct >= 85 ? "#EF4444" : (pct >= 60 ? "#F59E0B" : "var(--primary)");
        }
        if (tokensEl) tokensEl.textContent = `已用 ${totalFmt}，共 ${limitFmt} (${Number(total).toLocaleString()} tokens)`;
        if (cacheEl) {
          if (cacheHit > 0) {
            cacheEl.style.display = "block";
            cacheEl.textContent = `⚡ 缓存命中率 ${cacheHit}%`;
          } else {
            cacheEl.style.display = "none";
          }
        }
        const modelDisplayMap = {
          "mimo-auto": "MiMo Auto",
          "mimo-pro": "MiMo-X-Pro-Preview",
          "mimo-x-pro-preview": "MiMo-X-Pro-Preview",
          "mimo-flash": "MiMo-X-Flash-Preview",
          "mimo-x-flash-preview": "MiMo-X-Flash-Preview",
        };
        const displayModel = modelDisplayMap[model] || model;
        if (modelEl) modelEl.textContent = `模型：${displayModel}`;
      } catch (e) {
        console.warn("Update context usage failed:", e);
      }
    }

    // ── 真实语音输入 (Web Speech API 流式识别) ──
    function toggleVoiceRecording(e) {
      if (e) e.stopPropagation();
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        alert("当前环境不支持或未开启 Web 语音识别。推荐使用 iOS Safari、Android Chrome 或桌面 Chrome/Edge 体验原生语音输入。");
        return;
      }

      const voiceBtn = document.getElementById("btn-dock-voice");
      const cuesDrawer = document.getElementById("voice-cues-drawer");
      const cuesText = document.getElementById("voice-cue-text");
      const inputEl = document.getElementById("dock-input");

      if (isVoiceRecording) {
        if (voiceRecognition) {
          try { voiceRecognition.stop(); } catch(err) {}
        }
        isVoiceRecording = false;
        if (voiceBtn) voiceBtn.classList.remove("recording");
        if (cuesDrawer) cuesDrawer.style.display = "none";
        return;
      }

      try {
        voiceRecognition = new SpeechRecognition();
        voiceRecognition.lang = "zh-CN";
        voiceRecognition.continuous = true;
        voiceRecognition.interimResults = true;

        let baseText = inputEl ? inputEl.value : "";
        if (baseText && !baseText.endsWith(" ")) baseText += " ";

        voiceRecognition.onstart = () => {
          isVoiceRecording = true;
          if (voiceBtn) voiceBtn.classList.add("recording");
          if (cuesDrawer) cuesDrawer.style.display = "flex";
          if (cuesText) cuesText.textContent = "🎙️ 正在聆听中... 请说话 (再次点击麦克风结束)";
        };

        voiceRecognition.onresult = (event) => {
          let interimTranscript = "";
          let finalTranscript = "";
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              finalTranscript += event.results[i][0].transcript;
            } else {
              interimTranscript += event.results[i][0].transcript;
            }
          }
          if (inputEl) {
            inputEl.value = baseText + finalTranscript + interimTranscript;
            autoGrow(inputEl);
            inputEl.focus();
          }
        };

        voiceRecognition.onerror = (event) => {
          console.warn("Speech recognition error:", event.error);
          if (event.error === "not-allowed") {
            alert("请在系统或浏览器设置中允许麦克风权限以使用语音输入。");
          }
          isVoiceRecording = false;
          if (voiceBtn) voiceBtn.classList.remove("recording");
          if (cuesDrawer) cuesDrawer.style.display = "none";
        };

        voiceRecognition.onend = () => {
          isVoiceRecording = false;
          if (voiceBtn) voiceBtn.classList.remove("recording");
          if (cuesDrawer) cuesDrawer.style.display = "none";
        };

        voiceRecognition.start();
      } catch (err) {
        console.error("Failed to start speech recognition:", err);
        alert("启动语音输入失败：" + err.message);
      }
    }

    // ── 插件与技能中心逻辑 ──
    function openPluginsModal() {
      togglePluginsSheet(true);
    }

    function togglePluginsSheet(open) {
      const sheet = document.getElementById("plugins-sheet");
      if (sheet) {
        if (open) {
          loadPluginsList();
          sheet.classList.add("open");
        } else {
          sheet.classList.remove("open");
        }
      }
    }

    async function loadPluginsList() {
      const list = document.getElementById("plugins-scroll-list");
      if (list) list.innerHTML = `<div style="padding:24px; text-align:center; color:var(--text-muted); font-size:13px;">正在加载官方技能与插件列表...</div>`;
      try {
        const r = await fetch("/api/plugins");
        const data = await r.json();
        allPlugins = data.plugins || [];
        applyPluginFilters();
      } catch (e) {
        if (list) list.innerHTML = `<div style="padding:24px; text-align:center; color:#EF4444; font-size:13px;">插件列表加载失败: ${escapeHtml(e.message)}</div>`;
      }
    }

    function filterPlugins(cat, btn) {
      currentPluginTab = cat;
      const tabs = document.querySelectorAll(".plugin-tab");
      tabs.forEach(t => t.classList.remove("active"));
      if (btn) btn.classList.add("active");
      applyPluginFilters();
    }

    function onSearchPlugins(val) {
      applyPluginFilters();
    }

    function applyPluginFilters() {
      const kw = (document.getElementById("plugin-search-input")?.value || "").toLowerCase().trim();
      let filtered = allPlugins;
      if (currentPluginTab !== "all") {
        filtered = filtered.filter(p => p.category === currentPluginTab);
      }
      if (kw) {
        filtered = filtered.filter(p =>
          (p.name && p.name.toLowerCase().includes(kw)) ||
          (p.desc && p.desc.toLowerCase().includes(kw)) ||
          (p.id && p.id.toLowerCase().includes(kw))
        );
      }
      renderPlugins(filtered);
    }

    function renderPlugins(items) {
      const container = document.getElementById("plugins-scroll-list");
      if (!container) return;
      if (!items || !items.length) {
        container.innerHTML = `
          <div style="padding:48px 16px; text-align:center; color:var(--text-muted);">
            <div style="font-size:32px; margin-bottom:8px;">🧩</div>
            <div style="font-size:13px; font-weight:500;">未找到匹配的插件或技能</div>
            <div style="font-size:11.5px; color:var(--text-dim); margin-top:4px;">换个关键词或选择其他分类试试</div>
          </div>
        `;
        return;
      }
      container.innerHTML = items.map(p => `
        <div class="plugin-card">
          <div class="plugin-card-top">
            <div class="plugin-info">
              <div class="plugin-title-row">
                <span class="plugin-icon">${p.icon || "🧩"}</span>
                <span class="plugin-name">${escapeHtml(p.name)}</span>
                <span class="artifact-badge badge-doc">${escapeHtml(p.badge)}</span>
              </div>
              <div class="plugin-desc">${escapeHtml(p.desc)}</div>
            </div>
            <label class="switch-toggle" title="切换启用状态">
              <input type="checkbox" ${p.enabled ? "checked" : ""} onchange="togglePluginState('${p.id}', this.checked)">
              <span class="slider"></span>
            </label>
          </div>
        </div>
      `).join("");
    }

    async function togglePluginState(pluginId, enabled) {
      try {
        const r = await fetch("/api/plugins/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: pluginId, enabled: enabled })
        });
        const res = await r.json();
        if (res && res.ok) {
          const target = allPlugins.find(p => p.id === pluginId);
          if (target) target.enabled = enabled;
        } else {
          alert("更新插件状态失败: " + (res.error || "未知错误"));
        }
      } catch (e) {
        alert("更新插件状态异常: " + e.message);
      }
    }


    
    // ── 审批权限切换逻辑 ──
    async function loadPermConfig() {
      try {
        const r = await fetch("/api/perm");
        const data = await r.json();
        if (data && data.options) {
          selectedPerm = data.current || "完全访问权限";
          renderPermList(data.options);
          updatePermBadge(selectedPerm, data.options);
        }
      } catch (e) {}
    }

    function updatePermBadge(permId, options) {
      const opt = (options || []).find(o => o.id === permId);
      selectedPermName = opt ? opt.name : (permId === "完全访问权限" ? "完全访问" : permId);
      const label = document.getElementById("perm-name-label");
      const btn = document.getElementById("dock-perm-btn");
      if (label) label.textContent = selectedPermName + " ▾";
      if (btn) {
        btn.classList.remove("amber", "blue", "gray");
        if (permId === "完全访问权限") btn.classList.add("amber");
        else if (permId === "帮我审批") btn.classList.add("blue");
        else btn.classList.add("gray");
      }
    }

    function renderPermList(options) {
      const container = document.getElementById("perm-sheet-list");
      if (!container) return;
      container.innerHTML = options.map(opt => `
        <div class="model-item ${opt.id === selectedPerm ? "selected" : ""}" onclick="selectPerm('${opt.id}', '${opt.name}')">
          <div>
            <div class="model-item-name" style="display:flex; align-items:center; gap:8px;">
              <span>${opt.name}</span>
              <span class="artifact-badge ${opt.badgeClass || "badge-other"}">${opt.badge}</span>
            </div>
            <div class="model-item-desc">${opt.desc}</div>
          </div>
          ${opt.id === selectedPerm ? "<span style='color:#16A34A; font-weight:700;'>✓</span>" : ""}
        </div>
      `).join("");
    }

    function togglePermSheet(open) {
      const sheet = document.getElementById("perm-sheet");
      if (sheet) {
        if (open) {
          loadPermConfig();
          sheet.classList.add("open");
        } else {
          sheet.classList.remove("open");
        }
      }
    }

    async function selectPerm(permId, permName) {
      selectedPerm = permId;
      selectedPermName = permName;
      updatePermBadge(permId);
      togglePermSheet(false);
      try {
        await fetch("/api/perm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ perm: permId, session_id: currentSessionId })
        });
      } catch (e) {}
    }

    // ── 附件与图片上传逻辑 ──
    async function handleFileInputChange(e) {
      const files = e.target.files;
      if (!files || !files.length) return;
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        await uploadSingleFile(f);
      }
      e.target.value = "";
    }

    function uploadSingleFile(file) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = async () => {
          const b64 = reader.result.split(",")[1];
          try {
            const r = await fetch("/api/upload", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ filename: file.name, content: b64, type: file.type })
            });
            const res = await r.json();
            if (res.ok) {
              attachedFiles.push({
                name: file.name,
                path: res.path,
                type: file.type,
                size: file.size,
                dataUrl: file.type.startsWith("image/") ? reader.result : null
              });
              renderAttachedFiles();
            } else {
              alert("文件上传失败: " + (res.error || "未知错误"));
            }
          } catch (err) {
            alert("上传异常: " + err.message);
          }
          resolve();
        };
        reader.readAsDataURL(file);
      });
    }

    function renderAttachedFiles() {
      const row = document.getElementById("attached-files-row");
      if (!row) return;
      if (!attachedFiles.length) {
        row.style.display = "none";
        row.innerHTML = "";
        return;
      }
      row.style.display = "flex";
      row.innerHTML = attachedFiles.map((f, idx) => `
        <div class="attached-file-chip">
          ${f.dataUrl ? `<img src="${f.dataUrl}" class="attached-file-thumb">` : `<span style="font-size:14px;">📄</span>`}
          <span title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
          <span class="attached-file-del" onclick="removeAttachedFile(${idx})">✕</span>
        </div>
      `).join("");
    }

    function removeAttachedFile(idx) {
      attachedFiles.splice(idx, 1);
      renderAttachedFiles();
    }

    // ── 产物中心逻辑 ──
    function openArtifactsModal() {
      toggleDrawer(false);
      toggleArtifactsSheet(true);
    }

    function toggleArtifactsSheet(open) {
      const sheet = document.getElementById("artifacts-sheet");
      if (sheet) {
        if (open) {
          loadArtifactsList();
          sheet.classList.add("open");
        } else {
          sheet.classList.remove("open");
        }
      }
    }

    async function loadArtifactsList() {
      const list = document.getElementById("artifacts-scroll-list");
      if (list) list.innerHTML = `<div style="padding:24px; text-align:center; color:var(--text-muted); font-size:13px;">正在同步全部产物索引...</div>`;
      try {
        const r = await fetch("/api/artifacts");
        const data = await r.json();
        allArtifacts = data.artifacts || [];
        renderArtifacts(allArtifacts);
      } catch (e) {
        if (list) list.innerHTML = `<div style="padding:24px; text-align:center; color:#EF4444; font-size:13px;">产物加载失败: ${e.message}</div>`;
      }
    }

    function filterArtifacts(cat, btn) {
      currentArtifactTab = cat;
      const tabs = document.querySelectorAll(".artifact-tab");
      tabs.forEach(t => t.classList.remove("active"));
      if (btn) btn.classList.add("active");
      applyArtifactFilters();
    }

    function onSearchArtifacts() {
      applyArtifactFilters();
    }

    function applyArtifactFilters() {
      const keyword = (document.getElementById("artifact-search-input")?.value || "").toLowerCase().trim();
      let filtered = allArtifacts;
      if (currentArtifactTab !== "all") {
        filtered = filtered.filter(a => a.category === currentArtifactTab);
      }
      if (keyword) {
        filtered = filtered.filter(a =>
          (a.title && a.title.toLowerCase().includes(keyword)) ||
          (a.name && a.name.toLowerCase().includes(keyword)) ||
          (a.sessionTitle && a.sessionTitle.toLowerCase().includes(keyword))
        );
      }
      renderArtifacts(filtered);
    }

    function renderArtifacts(items) {
      const container = document.getElementById("artifacts-scroll-list");
      if (!container) return;
      if (!items || !items.length) {
        container.innerHTML = `
          <div style="padding:48px 16px; text-align:center; color:var(--text-muted);">
            <div style="font-size:32px; margin-bottom:8px;">📦</div>
            <div style="font-size:13px; font-weight:500;">还没有匹配的产物</div>
            <div style="font-size:11.5px; color:var(--text-dim); margin-top:4px;">在对话中让 MiMo 生成页面、文档或代码后将在这里汇总</div>
          </div>
        `;
        return;
      }
      container.innerHTML = items.map(item => {
        const sizeStr = item.size > 1024 * 1024 ? (item.size / (1024 * 1024)).toFixed(1) + " MB" : Math.round(item.size / 1024) + " KB";
        const dateStr = item.timeCreated ? new Date(item.timeCreated).toLocaleDateString() + " " + new Date(item.timeCreated).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : "";
        const badgeCls = item.category === "doc" ? "badge-doc" : (item.category === "app" ? "badge-app" : "badge-other");
        const isHtml = item.ext === ".html" || item.ext === ".htm";
        const isImage = [".png", ".jpg", ".jpeg", ".webp", ".svg"].includes(item.ext);
        const canPreview = isHtml || isImage || item.ext === ".pdf" || item.ext === ".txt";

        return `
          <div class="artifact-card">
            <div class="artifact-card-top">
              <div>
                <div class="artifact-card-title">${escapeHtml(item.title || item.name)}</div>
                <div style="font-size:12px; color:var(--text-dim); margin-top:2px;">${escapeHtml(item.name)}</div>
              </div>
              <span class="artifact-badge ${badgeCls}">${item.badge || "文件"}</span>
            </div>
            <div class="artifact-card-meta">
              <span>📅 ${dateStr}</span>
              <span>💾 ${sizeStr}</span>
              ${item.sessionTitle ? `<span>💬 ${escapeHtml(item.sessionTitle)}</span>` : ""}
            </div>
            <div class="artifact-card-actions">
              ${canPreview ? `<button class="btn-artifact-action primary" onclick="openArtifactPreview('${encodeURIComponent(item.path)}')">👁️ 打开预览</button>` : ""}
              <button class="btn-artifact-action" onclick="downloadArtifact('${encodeURIComponent(item.path)}')">📥 下载</button>
              ${item.sessionId ? `<button class="btn-artifact-action" onclick="jumpToArtifactSession('${item.sessionId}')">💬 进入对话</button>` : ""}
            </div>
          </div>
        `;
      }).join("");
    }

    function openArtifactPreview(encodedPath) {
      window.open("/api/artifacts/file?path=" + encodedPath, "_blank");
    }

    function downloadArtifact(encodedPath) {
      const a = document.createElement("a");
      a.href = "/api/artifacts/file?download=1&path=" + encodedPath;
      a.target = "_blank";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }

    function jumpToArtifactSession(sid) {
      toggleArtifactsSheet(false);
      selectSession(sid);
    }

    // 1. PWA Service Worker 注册与 Android / Chrome 原生安装事件捕获
    let deferredPrompt = null;
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" })
          .then((reg) => {
            reg.update();
            if (reg.waiting) reg.waiting.postMessage({ type: "SKIP_WAITING" });
          })
          .catch(() => {});
      });
    }

    // 检查如果当前处于 HTTP，提示切换到 HTTPS 才能以真 PWA 原生安装
    if (!isStandalone && location.protocol === 'http:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      window.addEventListener("DOMContentLoaded", () => {
        const tip = document.getElementById("httpTipBanner");
        const text = document.getElementById("httpTipBannerText");
        if (!tip) return;
        if (window.MIMO_PWA_HTTPS_URL) {
          if (text) text.textContent = "当前处于 HTTP 模式。点击一键进入 HTTPS 安全通道即可免浏览器框安装 PWA";
        } else {
          if (text) text.textContent = "尚未配置到本网关的 Tailscale HTTPS，暂无法一键跳转安装。请先在电脑执行 tailscale serve";
        }
        tip.style.display = "flex";
      });
    }

    function openHttpsChannel() {
      if (window.MIMO_PWA_HTTPS_URL) {
        location.href = window.MIMO_PWA_HTTPS_URL;
        return;
      }
      const port = location.port || "8080";
      alert("未检测到指向当前网关的 Tailscale HTTPS 配置。\\n请在电脑上执行：\\ntailscale serve --https=8443 --bg " + port + "\\n完成后刷新本页再点击横幅。");
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
          if (window.MIMO_PWA_HTTPS_URL) {
            location.href = window.MIMO_PWA_HTTPS_URL;
          } else {
            alert("当前处于 HTTP 模式。请先在电脑端执行：\\ntailscale serve --https=8443 --bg " + location.port + "\\n然后使用 HTTPS 地址访问以安装 PWA。");
          }
        } else {
          const httpsHint = window.MIMO_PWA_HTTPS_URL
            ? "1. 请使用手机 Chrome 访问 " + window.MIMO_PWA_HTTPS_URL
            : "1. 请先在电脑端开启 tailscale serve，再用 HTTPS 地址访问";
          alert("如需将 MiMo 安装为原生桌面应用：\\n" + httpsHint + "\\n2. 点击右上角菜单【⋮】并选择【安装应用】或【添加到主屏幕】。");
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

    let allModelsCache = [];
    let activeModelCategory = "all";

    function toggleModelMenu(e) {
      if (e) e.stopPropagation();
      if (window.innerWidth <= 768) {
        openModelSheet();
      } else {
        toggleModelPopover(e);
      }
    }

    function toggleModelPopover(e) {
      if (e) e.stopPropagation();
      const popover = document.getElementById("model-popover-menu");
      if (!popover) return;
      const isVisible = popover.style.display !== "none" && popover.style.display !== "";
      if (isVisible) {
        popover.style.display = "none";
      } else {
        closeContextHud();
        closeModelSheet();
        popover.style.display = "block";
        loadModelConfig(currentSessionId);
        
        requestAnimationFrame(() => {
          popover.style.transform = "none";
          const rect = popover.getBoundingClientRect();
          const winWidth = window.innerWidth;
          if (rect.right > winWidth - 8) {
            const shift = rect.right - (winWidth - 8);
            popover.style.transform = `translateX(-${shift}px)`;
          } else if (rect.left < 8) {
            const shift = 8 - rect.left;
            popover.style.transform = `translateX(${shift}px)`;
          }
        });
      }
    }

    function closeModelPopover(e) {
      if (e) e.stopPropagation();
      const popover = document.getElementById("model-popover-menu");
      if (popover) popover.style.display = "none";
    }

    function openModelSheet() {
      closeContextHud();
      closeModelPopover();
      const sheet = document.getElementById("model-sheet");
      if (!sheet) return;
      sheet.classList.add("open");
      const titleEl = document.getElementById("top-session-title");
      const sub = document.getElementById("model-sheet-subtitle");
      if (sub) {
        const curTitle = (titleEl ? titleEl.textContent : "当前任务") || "当前任务";
        sub.textContent = `为任务「${curTitle}」指派专属 AI 模型，或设为新建任务的全局默认`;
      }
      loadModelConfig(currentSessionId);
    }

    function closeModelSheet() {
      const sheet = document.getElementById("model-sheet");
      if (sheet) sheet.classList.remove("open");
    }

    function toggleModelSheet(open) {
      if (open) {
        openModelSheet();
      } else {
        closeModelSheet();
        closeModelPopover();
      }
    }

    function closeModelMenu(e) {
      if (e) e.stopPropagation();
      closeModelPopover();
      closeModelSheet();
    }

    function switchModelCategory(cat, btn) {
      activeModelCategory = cat || "all";
      document.querySelectorAll(".model-cat-tab").forEach(tab => {
        tab.classList.toggle("active", tab === btn || tab.getAttribute("data-cat") === activeModelCategory);
      });
      renderModelList(allModelsCache, selectedModelId);
    }

    // 3. 真实模型配置加载与切换 (多维映射、会话感知与 preferences.json 同步)
    async function loadModelConfig(sid) {
      try {
        const targetSid = sid || currentSessionId || "";
        const r = await fetch("/api/model?session_id=" + encodeURIComponent(targetSid));
        const data = await r.json();
        if (data && data.models) {
          allModelsCache = data.models;
          selectedModelId = data.current || "mimo-auto";
          const curObj = data.session_model || allModelsCache.find(m => isSameModel(m.canonicalId || m.id, selectedModelId));
          if (curObj) {
            selectedModelName = curObj.name;
            updateDockModelLabel(curObj);
          }
          renderModelList(allModelsCache, selectedModelId);
        }
      } catch (e) {
        console.warn("加载模型配置失败:", e);
      }
    }

    function updateDockModelLabel(m) {
      const lbl = document.getElementById("model-name-label");
      const btn = document.getElementById("dock-model-btn");
      if (lbl && m) {
        lbl.textContent = m.name || m.shortName || "MiMo Auto";
      }
      if (btn && m) {
        btn.title = `当前模型: ${m.name} (${m.badge || ""}) · 点击切换`;
      }
    }

    function isSameModel(idA, idB) {
      if (!idA || !idB) return idA === idB;
      if (idA === idB) return true;
      const clean = id => String(id)
        .replace(new RegExp("^mimo/"), "")
        .replace(new RegExp("^xiaomi/"), "")
        .replace(new RegExp("^anthropic/"), "")
        .replace(new RegExp("-preview$"), "")
        .replace(new RegExp("^mimo-x-"), "mimo-");
      const cA = clean(idA);
      const cB = clean(idB);
      if (cA === cB) return true;
      if ((cA === "mimo-pro" || cA === "mimo-v2.6-pro") && (cB === "mimo-pro" || cB === "mimo-v2.6-pro")) return true;
      if ((cA === "mimo-flash" || cA === "mimo-v2.6-flash") && (cB === "mimo-flash" || cB === "mimo-v2.6-flash")) return true;
      return false;
    }

    function renderModelList(models, curId) {
      if (!Array.isArray(models) || !models.length) return;
      const popoverList = document.getElementById("model-popover-list");
      const sheetList = document.getElementById("model-sheet-list");

      // 1. 渲染桌面紧凑气泡菜单
      if (popoverList) {
        popoverList.innerHTML = "";
        models.forEach(m => {
          const isSel = isSameModel(m.canonicalId || m.id, curId);
          const item = document.createElement("div");
          item.className = "model-popover-item " + (isSel ? "selected" : "");
          item.onclick = () => selectRealModel(m.canonicalId || m.id, m.name);
          item.innerHTML = `
            <div style="flex:1; min-width:0; margin-right:8px;">
              <div class="model-popover-item-title">
                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(m.name)}</span>
                <span class="model-popover-item-badge">${escapeHtml(m.badge || "官方")}</span>
              </div>
              <div class="model-popover-item-desc">${escapeHtml(m.desc || "")}</div>
            </div>
            <div style="color: #FF6900; font-weight: 700; font-size: 14px; flex-shrink:0;">${isSel ? '✓' : ''}</div>
          `;
          popoverList.appendChild(item);
        });
      }

      // 2. 渲染手机端原生底部抽屉卡片 (支持分类过滤、特性徽标、上下文参数)
      if (sheetList) {
        sheetList.innerHTML = "";
        const filtered = models.filter(m => {
          if (activeModelCategory === "all") return true;
          return (m.category || "official") === activeModelCategory;
        });

        if (!filtered.length) {
          sheetList.innerHTML = '<div style="padding:24px; text-align:center; color:var(--text-muted); font-size:13px;">该分类下暂无可用的已配置模型</div>';
          return;
        }

        filtered.forEach(m => {
          const mId = m.canonicalId || m.id;
          const isSel = isSameModel(mId, curId);
          const card = document.createElement("div");
          card.className = "model-card-item " + (isSel ? "selected" : "");
          card.onclick = () => selectRealModel(mId, m.name);

          const capsHtml = (m.capabilities || []).map(c => `<span class="model-cap-pill">${escapeHtml(c)}</span>`).join("");
          const stripeColor = m.color || "#FF6900";

          card.innerHTML = `
            <div class="model-card-stripe" style="${isSel ? 'background:' + stripeColor : ''}"></div>
            <div class="model-card-body">
              <div class="model-card-head">
                <div class="model-card-title">
                  <span>${m.icon || "🤖"}</span>
                  <span>${escapeHtml(m.name)}</span>
                </div>
                <div style="font-size:11px; font-weight:600; color:var(--text-muted);">${escapeHtml(m.ratio || "")}</div>
              </div>
              <div class="model-card-badges">
                <span class="model-badge-chip ${m.badgeClass || 'badge-gray'}">${escapeHtml(m.badge || "官方")}</span>
                <span class="model-badge-chip badge-gray">${escapeHtml(m.contextWindow || "1M 上下文")}</span>
                <span class="model-badge-chip badge-gray">${escapeHtml(m.providerName || "自研")}</span>
              </div>
              <div class="model-card-desc">${escapeHtml(m.desc || "")}</div>
              <div class="model-card-caps">${capsHtml}</div>
            </div>
            <div class="model-check-circle">${isSel ? '✓' : ''}</div>
          `;
          sheetList.appendChild(card);
        });
      }
    }

    async function selectRealModel(modelId, modelName) {
      if (navigator.vibrate) navigator.vibrate(10);
      selectedModelId = modelId;
      selectedModelName = modelName;

      const curObj = allModelsCache.find(m => isSameModel(m.canonicalId || m.id, modelId));
      if (curObj) {
        updateDockModelLabel(curObj);
      } else {
        const lbl = document.getElementById("model-name-label");
        if (lbl) lbl.textContent = modelName;
      }

      closeModelMenu();

      const isGlobal = document.getElementById("chk-set-default-model") ? document.getElementById("chk-set-default-model").checked : true;

      try {
        const r = await fetch("/api/model", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: modelId,
            session_id: currentSessionId,
            set_global: isGlobal
          })
        });
        const res = await r.json();
        if (res.ok && res.model) {
          updateDockModelLabel(res.model);
        }
      } catch (e) {
        console.error("更新模型失败:", e);
      }
    }

    function autoGrow(textarea) {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
    }

    // ── 高性能 Markdown 与 Prism 语法高亮引擎 (纯前端零依赖) ────────────────
    function initMarkdownEngine() {
      if (typeof marked !== "undefined") {
        const renderer = new marked.Renderer();
        renderer.link = function({ href, title, text }) {
          const t = title ? ` title="${escapeHtml(title)}"` : "";
          return `<a href="${escapeHtml(href)}"${t} target="_blank" rel="noopener noreferrer">${text}</a>`;
        };
        const origTable = renderer.table.bind(renderer);
        renderer.table = function(token) {
          return `<div class="table-responsive">${origTable(token)}</div>`;
        };
        renderer.code = function({ text, lang }) {
          lang = (lang || "").trim().toLowerCase();
          let highlighted = escapeHtml(text);
          let validLang = lang;
          if (typeof Prism !== "undefined") {
            if (Prism.languages[lang]) {
              try { highlighted = Prism.highlight(text, Prism.languages[lang], lang); } catch(_) {}
            } else if (lang === "py") {
              try { highlighted = Prism.highlight(text, Prism.languages.python, "python"); validLang = "python"; } catch(_) {}
            } else if (lang === "sh" || lang === "shell" || lang === "zsh") {
              try { highlighted = Prism.highlight(text, Prism.languages.bash, "bash"); validLang = "bash"; } catch(_) {}
            } else if (lang === "js") {
              try { highlighted = Prism.highlight(text, Prism.languages.javascript, "javascript"); validLang = "javascript"; } catch(_) {}
            } else if (lang === "json") {
              try { highlighted = Prism.highlight(text, Prism.languages.json, "json"); validLang = "json"; } catch(_) {}
            } else if (lang === "diff" || lang === "patch") {
              try { highlighted = Prism.highlight(text, Prism.languages.diff, "diff"); validLang = "diff"; } catch(_) {}
            } else if (lang === "html" || lang === "xml") {
              try { highlighted = Prism.highlight(text, Prism.languages.markup, "markup"); validLang = "html"; } catch(_) {}
            } else if (lang === "css") {
              try { highlighted = Prism.highlight(text, Prism.languages.css, "css"); validLang = "css"; } catch(_) {}
            }
          }
          const displayLang = (validLang || "code").toUpperCase();
          return `
            <div class="mimo-code-card">
              <div class="code-card-header">
                <span>${escapeHtml(displayLang)}</span>
                <button class="btn-copy-code" onclick="copyCodeBlock(this)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>复制</span>
                </button>
              </div>
              <div class="code-card-body">
                <pre class="language-${validLang || 'none'}"><code>${highlighted}</code></pre>
              </div>
            </div>
          `;
        };
        marked.setOptions({
          renderer: renderer,
          gfm: true,
          breaks: true,
          pedantic: false
        });
      }
    }

    function stripSystemReminders(str) {
      if (!str) return "";
      return str.replace(new RegExp("<system-reminder>[^]*?</system-reminder>", "gi"), "").trim();
    }

    function preprocessStreamingMarkdown(str) {
      if (!str) return "";
      const matches = str.match(/```/g);
      if (matches && matches.length % 2 !== 0) {
        return str + String.fromCharCode(10) + "```";
      }
      return str;
    }

    function formatCodeBlocksFallback(str) {
      if (!str) return "";
      let safe = str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      safe = safe.replace(/`([^`]+)`/g, "<code style='background:#F1F3F5;padding:2px 5px;border-radius:4px;font-family:var(--font-mono);font-size:12.5px;'>$1</code>");
      safe = safe.replace(/\\*\\*([^\\*]+)\\*\\*/g, "<strong>$1</strong>");
      safe = safe.replace(/\\n/g, "<br>");
      return safe;
    }

    function renderMarkdownSafe(str) {
      if (!str) return "";
      const clean = stripSystemReminders(str);
      if (typeof marked !== "undefined" && marked.parse) {
        try {
          const preprocessed = preprocessStreamingMarkdown(clean);
          return marked.parse(preprocessed);
        } catch (_) {
          return formatCodeBlocksFallback(clean);
        }
      }
      return formatCodeBlocksFallback(clean);
    }

    // ── 智能视口吸底与用户上滑阅读保护 ─────────────────────────────
    let userIsScrolledUp = false;

    function checkViewportScroll() {
      const vp = document.getElementById("chat-viewport");
      if (!vp) return;
      const threshold = 70;
      const dist = vp.scrollHeight - vp.scrollTop - vp.clientHeight;
      userIsScrolledUp = dist > threshold;
      const btn = document.getElementById("scroll-bottom-btn");
      if (btn) btn.classList.toggle("show", userIsScrolledUp);
      if (!userIsScrolledUp) {
        const dot = document.getElementById("scroll-unread-dot");
        if (dot) dot.style.display = "none";
      }
    }

    function smartScrollToBottom() {
      const vp = document.getElementById("chat-viewport");
      if (!vp) return;
      if (!userIsScrolledUp) {
        vp.scrollTop = vp.scrollHeight;
      } else {
        const dot = document.getElementById("scroll-unread-dot");
        if (dot) dot.style.display = "block";
      }
    }

    function scrollToBottom(force = true) {
      const vp = document.getElementById("chat-viewport");
      if (!vp) return;
      userIsScrolledUp = false;
      const btn = document.getElementById("scroll-bottom-btn");
      if (btn) btn.classList.remove("show");
      const dot = document.getElementById("scroll-unread-dot");
      if (dot) dot.style.display = "none";
      vp.scrollTo({ top: vp.scrollHeight, behavior: "smooth" });
    }

    // ── 复制与消息操作 ─────────────────────────────────────────
    function copyCodeBlock(btn) {
      const card = btn.closest(".mimo-code-card");
      if (!card) return;
      const code = card.querySelector("pre code");
      const text = code ? code.innerText : "";
      copyText(text, btn);
    }

    function copyToolOutput(btn) {
      const box = btn.closest(".tool-console-box");
      if (!box) return;
      const code = box.querySelector("pre code");
      const text = code ? code.innerText : (box.innerText || "");
      copyText(text, btn);
    }

    function copyAssistantMessage(btn) {
      const container = btn.closest(".msg-assistant-container");
      if (!container) return;
      const proseCards = container.querySelectorAll(".assistant-prose-card");
      let parts = [];
      proseCards.forEach(c => {
        if (c.dataset.rawText) parts.push(c.dataset.rawText);
        else parts.push(c.innerText);
      });
      const text = parts.join(String.fromCharCode(10) + String.fromCharCode(10));
      copyText(text, btn);
    }

    function copyUserBubble(btn) {
      const bubble = btn.closest(".user-bubble");
      if (!bubble) return;
      const text = bubble.dataset.rawText || bubble.innerText || "";
      copyText(text, btn);
    }

    function editUserPrompt(btn) {
      const bubble = btn.closest(".user-bubble");
      const raw = bubble?.dataset.rawText || "";
      const inp = document.getElementById("dock-input");
      if (inp && raw) {
        inp.value = raw;
        autoGrow(inp);
        inp.focus();
        inp.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }

    function regenerateLastTurn(btn) {
      if (isBusy) return;
      const allUserBubbles = document.querySelectorAll(".user-bubble");
      if (!allUserBubbles.length) return;
      const lastUser = allUserBubbles[allUserBubbles.length - 1];
      const text = lastUser.dataset.rawText || "";
      if (!text) return;
      const inp = document.getElementById("dock-input");
      if (inp) {
        inp.value = text;
        sendPrompt();
      }
    }

    // ── 历史会话管理、相对时间与快捷搜索过滤 ─────────────────────────
    let allSessionsCache = [];

    function formatTimeAgo(ts) {
      if (!ts) return "";
      const now = Date.now();
      const diff = Math.max(0, Math.floor((now - ts) / 1000));
      if (diff < 60) return "刚刚";
      if (diff < 3600) return Math.floor(diff / 60) + " 分钟前";
      if (diff < 86400) return Math.floor(diff / 3600) + " 小时前";
      if (diff < 86400 * 7) return Math.floor(diff / 86400) + " 天前";
      const d = new Date(ts);
      return (d.getMonth() + 1) + "月" + d.getDate() + "日";
    }

    function renderSessionsList(list) {
      const container = document.getElementById("sessions-container");
      if (!container) return;
      container.innerHTML = "";
      if (!list || !list.length) {
        container.innerHTML = '<div style="padding:14px; color:var(--text-dim); font-size:12px; text-align:center;">暂无匹配任务</div>';
        return;
      }
      list.forEach(s => {
        const item = document.createElement("div");
        item.className = "session-item-row " + (s.id === currentSessionId ? "active" : "");
        item.dataset.id = s.id;
        const liveTag = s.is_busy ? `<span class="session-item-live-badge"><span class="dot-pulse">●</span> 工作中</span>` : "";
        item.innerHTML = `
          <div class="session-item-main" onclick="selectSession('${s.id}', '${escapeHtml(s.title || "未命名任务")}')">
            <div class="session-item-title"><span>${escapeHtml(s.title || "未命名任务")}</span>${liveTag}</div>
            <div class="session-item-time">
              <span>${formatTimeAgo(s.time?.updated || s.time?.created)}</span>
              ${s.model ? `<span class="session-model-pill">${escapeHtml(s.model)}</span>` : ""}
            </div>
          </div>
          <button class="session-item-del" title="删除会话" onclick="deleteSession('${s.id}', event)">✕</button>
        `;
        container.appendChild(item);
      });
    }

    function filterSessionsList(query) {
      query = (query || "").trim().toLowerCase();
      if (!query) {
        renderSessionsList(allSessionsCache);
        return;
      }
      const filtered = allSessionsCache.filter(s => (s.title || "").toLowerCase().includes(query));
      renderSessionsList(filtered);
    }

    async function loadSessionsList() {
      try {
        const r = await fetch("/api/sessions");
        const list = await r.json();
        if (Array.isArray(list)) {
          allSessionsCache = list;
          const searchInput = document.getElementById("session-search-input");
          filterSessionsList(searchInput ? searchInput.value : "");
        }
      } catch(e) {}
    }

    async function deleteSession(sid, e) {
      if (e) e.stopPropagation();
      if (!confirm("确定要删除此任务会话吗？此操作不可撤销。")) return;
      try {
        const r = await fetch("/api/sessions/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: sid })
        });
        if (r.ok) {
          allSessionsCache = allSessionsCache.filter(s => s.id !== sid);
          const searchInput = document.getElementById("session-search-input");
          filterSessionsList(searchInput ? searchInput.value : "");
          if (currentSessionId === sid) {
            triggerNewSession();
          }
        }
      } catch (err) {
        alert("删除失败: " + err.message);
      }
    }

    async function selectSession(sid, title) {
      if (currentSessionId === sid) {
        toggleDrawer(false);
        return;
      }
      currentSessionId = sid;
      document.getElementById("top-session-title").textContent = title || "当前任务";
      activeAssistantBox = null;
      activeToolsMap = {};
      stopBusyWatch();
      setBusy(false);
      toggleDrawer(false);
      try {
        await fetch("/api/focus_session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid })
        });
      } catch (e) {}
      loadModelConfig(sid);
      await loadHistoricalMessages(sid, true);
      connectSessionSSE(sid);
      updateContextUsage(sid);
      loadSessionContext(sid);
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
          activeAssistantBox = null;
          activeToolsMap = {};
          stopBusyWatch();
          setBusy(false);
          connectSessionSSE(res.id);
          await loadSessionsList();
          toggleDrawer(false);
          updateContextUsage(res.id);

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

    async function loadUserProfile() {
      try {
        const r = await fetch("/api/user");
        const u = await r.json();
        if (u && u.displayName) {
          document.getElementById("user-name-label").textContent = u.displayName;
        }
      } catch(e) {}
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

          // 判定当前最新一条消息是否正处于运行状态
          const lastMsg = msgs[msgs.length - 1];
          const lastInfo = lastMsg?.info || {};
          const lastRole = lastInfo.role || "assistant";
          let isRunning = false;
          let turnStartTime = 0;

          if (lastRole === "user") {
            isRunning = true;
            turnStartTime = lastInfo.time?.created || 0;
          } else if (lastRole === "assistant") {
            const parts = lastMsg.parts || [];
            const hasRunningTool = parts.some(p => p.type === "tool" && p.state?.status === "running");
            const hasError = !!lastInfo.error;
            const isDone = (lastInfo.finish === "stop" || (lastInfo.time && lastInfo.time.completed)) && !hasRunningTool;
            if (!isDone && !hasError) {
              isRunning = true;
              const parentId = lastInfo.parentID;
              if (parentId) {
                const parentMsg = msgs.find(m => (m.info?.id === parentId || m.id === parentId));
                if (parentMsg && parentMsg.info?.time?.created) {
                  turnStartTime = parentMsg.info.time.created;
                }
              }
              if (!turnStartTime) {
                for (let i = msgs.length - 1; i >= 0; i--) {
                  if (msgs[i].info?.role === "user" && msgs[i].info?.time?.created) {
                    turnStartTime = msgs[i].info.time.created;
                    break;
                  }
                }
              }
              if (!turnStartTime) {
                turnStartTime = lastInfo.time?.created || 0;
              }
            }
          }

          let curAssistantWrap = null;

          msgs.forEach((m, idx) => {
            const role = m.info?.role || "assistant";
            const isLast = (idx === msgs.length - 1);

            if (role === "user") {
              curAssistantWrap = null;
              const textParts = (m.parts || []).filter(p => p.type === "text").map(p => p.text).join(String.fromCharCode(10));
              const clean = stripSystemReminders(textParts);
              if (clean) {
                appendUserBubble(clean);
                renderedCount++;
              }
            } else {
              // 关键聚合：同一交互轮次（Turn）内所有连续的 assistant 中间消息共享同一个气泡容器！
              if (!curAssistantWrap) {
                curAssistantWrap = appendAssistantBox();
                renderedCount++;
              }
              const wrap = curAssistantWrap;
              const isCurrentRunning = isLast && isRunning;
              if (isCurrentRunning) {
                activeAssistantBox = wrap;
              }
              let hasUnfoldedReasoning = false;
              (m.parts || []).forEach(p => {
                if (p.type === "reasoning" && p.text) {
                  const live = isCurrentRunning && !(m.parts || []).some(x => x.type === "text" && x.text);
                  addThinking(wrap, p.text, live);
                  if (live) hasUnfoldedReasoning = true;
                } else if (p.type === "tool") {
                  const out = p.state?.output || p.state?.metadata?.output || "";
                  const desc = p.state?.metadata?.description || p.state?.input?.description || p.state?.input?.summary || "";
                  addToolCard(wrap, p.callID, p.tool, p.state?.status, p.state?.input, out, desc);
                } else if (p.type === "text" && p.text) {
                  addProseText(wrap, p.text, p.id);
                }
              });

              // 判断是否到达本轮交互末尾（下一条为 user 或已是全记录最后一条）
              const nextMsg = msgs[idx + 1];
              const isTurnEnd = !nextMsg || nextMsg.info?.role === "user";

              if (isTurnEnd) {
                if (isCurrentRunning) {
                  const hasRunningTool = (m.parts || []).some(p => p.type === "tool" && p.state?.status === "running");
                  if (hasRunningTool || hasUnfoldedReasoning) {
                    showThinkingIndicator(wrap);
                  }
                } else {
                  // 只有整轮完成时，才挂载唯一的反馈操作栏，杜绝重复堆叠
                  appendFeedbackRow(wrap);
                }
              }
            }
          });

          if (isRunning && turnStartTime) {
            markTaskRunning(sid, turnStartTime);
          } else if (!isRunning && isBusy) {
            setBusy(false);
          }

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
        checkViewportScroll();
      } catch(e) {
        vp.innerHTML = `<div class="msg-assistant-container"><div class="assistant-prose-card">❌ 加载会话记录失败: ${e.message}</div></div>`;
      }
    }

    function appendUserBubble(text, files) {
      const vp = document.getElementById("chat-viewport");
      const row = document.createElement("div");
      row.className = "msg-user-container";
      let filesHtml = "";
      if (files && files.length) {
        filesHtml = '<div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px;">' + files.map(f => {
          if (f.dataUrl && f.type && f.type.startsWith("image/")) {
            return `<img src="${f.dataUrl}" style="max-width:140px; max-height:140px; border-radius:8px; object-fit:cover; display:block;">`;
          }
          return `<div style="padding:4px 8px; background:rgba(0,0,0,0.06); border-radius:6px; font-size:11.5px; display:inline-flex; align-items:center; gap:4px;">📄 ${escapeHtml(f.name)}</div>`;
        }).join("") + '</div>';
      }
      const renderedText = renderMarkdownSafe(text);
      row.innerHTML = `
        <div class="user-bubble" data-raw-text="${escapeHtml(text)}">
          ${filesHtml}
          <div class="user-bubble-text">${renderedText}</div>
          <div class="user-bubble-actions">
            <button class="btn-bubble-action" title="编辑回填" onclick="editUserPrompt(this)">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              <span>编辑</span>
            </button>
            <button class="btn-bubble-action" title="复制提问" onclick="copyUserBubble(this)">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              <span>复制</span>
            </button>
          </div>
        </div>
      `;
      vp.appendChild(row);
      scrollToBottom(true);
    }

    function appendAssistantBox() {
      const vp = document.getElementById("chat-viewport");
      const wrap = document.createElement("div");
      wrap.className = "msg-assistant-container";
      vp.appendChild(wrap);
      smartScrollToBottom();
      return wrap;
    }

    let activeTextCard = null;
    let activeTextPartId = null;
    let pendingRenderRaf = null;
    let pendingRenderCard = null;
    let pendingRenderText = "";

    function flushProseRender() {
      if (pendingRenderRaf) {
        cancelAnimationFrame(pendingRenderRaf);
        pendingRenderRaf = null;
        if (pendingRenderCard && pendingRenderText !== undefined) {
          pendingRenderCard.innerHTML = renderMarkdownSafe(pendingRenderText);
          smartScrollToBottom();
        }
      }
    }

    function appendProseCard(wrap, partId) {
      if (!wrap) wrap = appendAssistantBox();
      if (partId && partId !== "default") {
        const existing = wrap.querySelector(`.assistant-prose-card[data-part-id="${partId}"]`);
        if (existing) return existing;
      }
      const c = document.createElement("div");
      c.className = "assistant-prose-card";
      if (partId && partId !== "default") {
        c.dataset.partId = partId;
      }
      wrap.appendChild(c);
      smartScrollToBottom();
      return c;
    }

    function updateProseContent(card, fullText) {
      if (!card) return;
      card.dataset.rawText = fullText;
      card.dataset.rawLength = String(fullText.length);
      pendingRenderCard = card;
      pendingRenderText = fullText;

      if (!pendingRenderRaf) {
        pendingRenderRaf = requestAnimationFrame(() => {
          pendingRenderRaf = null;
          if (pendingRenderCard) {
            pendingRenderCard.innerHTML = renderMarkdownSafe(pendingRenderText);
            smartScrollToBottom();
          }
        });
      }
    }

    function addProseText(wrap, text, partId) {
      const c = appendProseCard(wrap, partId);
      c.innerHTML = renderMarkdownSafe(text);
      c.dataset.rawText = text;
      c.dataset.rawLength = String((text || "").length);
      smartScrollToBottom();
      return c;
    }

    // ── 深度思考展示与自动折叠 ─────────────────────────────────
    function addThinking(wrap, text, isLive = false, elapsedSec = null) {
      let box = wrap.querySelector(".thinking-box");
      if (!box) {
        box = document.createElement("div");
        box.className = "thinking-box " + (isLive ? "live open" : "");
        box.innerHTML = `
          <div class="thinking-toggle" onclick="this.parentElement.classList.toggle('open')">
            <div class="thinking-toggle-left">
              <span class="thinking-toggle-icon">💭</span>
              <span class="thinking-toggle-title">${isLive ? "正在深度思考..." : "已深度思考"}</span>
              <span class="thinking-toggle-badge">${elapsedSec ? elapsedSec + "s" : ""}</span>
            </div>
            <span class="thinking-toggle-arrow">▾</span>
          </div>
          <div class="thinking-content"></div>
        `;
        wrap.insertBefore(box, wrap.firstChild);
      }
      const content = box.querySelector(".thinking-content");
      if (content) content.textContent = text;
      if (!isLive) {
        box.classList.remove("live");
        box.querySelector(".thinking-toggle-title").textContent = "已深度思考";
        if (elapsedSec) {
          box.querySelector(".thinking-toggle-badge").textContent = elapsedSec + "s";
        }
      }
    }

    function collapseThinking(wrap) {
      if (!wrap) return;
      const box = wrap.querySelector(".thinking-box");
      if (box && box.classList.contains("live")) {
        box.classList.remove("live");
        box.classList.remove("open");
        box.querySelector(".thinking-toggle-title").textContent = "已深度思考";
      }
    }

    let busyStartTime = 0;
    let taskLiveTimer = null;

    function formatElapsed(ms) {
      const s = Math.max(0, Math.floor(ms / 1000));
      if (s < 60) return s + "s";
      const m = Math.floor(s / 60);
      const rs = s % 60;
      if (m < 60) return m + "m " + String(rs).padStart(2, "0") + "s";
      const h = Math.floor(m / 60);
      return h + "h " + String(m % 60).padStart(2, "0") + "m";
    }

    function paintTaskLiveUI() {
      const elapsed = formatElapsed(Date.now() - (busyStartTime || Date.now()));
      const topE = document.getElementById("task-live-top-elapsed");
      if (topE) topE.textContent = elapsed;
      const th = document.getElementById("active-thinking-indicator");
      if (th) th.innerHTML = '正在工作 · 已处理 ' + elapsed + '<span class="dot-pulse">...</span>';
    }

    function startTaskLiveUI() {
      const top = document.getElementById("task-live-top");
      if (top) top.classList.add("show");
      paintTaskLiveUI();
      if (taskLiveTimer) clearInterval(taskLiveTimer);
      taskLiveTimer = setInterval(paintTaskLiveUI, 1000);
    }

    function stopTaskLiveUI() {
      if (taskLiveTimer) {
        clearInterval(taskLiveTimer);
        taskLiveTimer = null;
      }
      const top = document.getElementById("task-live-top");
      if (top) top.classList.remove("show");
    }

    function showThinkingIndicator(wrap) {
      removeThinkingIndicator(wrap);
      if (!wrap) return null;
      const el = document.createElement("div");
      el.className = "mimo-thinking-text";
      el.id = "active-thinking-indicator";
      el.innerHTML = '正在工作 · 已处理 ' + formatElapsed(Date.now() - (busyStartTime || Date.now())) + '<span class="dot-pulse">...</span>';
      wrap.appendChild(el);
      smartScrollToBottom();
      return el;
    }

    function removeThinkingIndicator(wrap) {
      if (wrap) {
        const el = wrap.querySelector(".mimo-thinking-text");
        if (el) el.remove();
      }
      const el = document.getElementById("active-thinking-indicator");
      if (el) el.remove();
    }

    // ── 终端工具执行卡片 (1:1 对齐电脑端：意图优先、单行收敛、拒绝爆屏) ─
    function addToolCard(wrap, callId, tool, status, inputData, outputData, extraDesc = "") {
      let card = activeToolsMap[callId];
      const isRunning = status === "running";
      const isCompleted = status === "completed";
      const isFailed = status === "error" || status === "failed";
      const labelText = isRunning ? "执行中..." : (isCompleted ? "已完成" : (isFailed ? "执行失败" : (status || "已执行")));

      // 1. 意图描述优先提取（对齐电脑端：如“汇总单测并组装 debug APK”）
      let desc = extraDesc || inputData?.description || inputData?.summary || "";
      const tName = (tool || "TOOL").toLowerCase();

      if (!desc) {
        if (typeof inputData === "string") {
          desc = inputData;
        } else if (inputData?.command) {
          // 仅保留第一条简明命令，脱敏长路径
          const firstLine = String(inputData.command).trim().split(String.fromCharCode(10))[0];
          desc = firstLine.length > 45 ? firstLine.slice(0, 42) + "..." : firstLine;
        } else if (inputData?.path || inputData?.file_path) {
          desc = inputData.path || inputData.file_path;
        } else if (inputData?.query) {
          desc = inputData.query;
        } else {
          desc = tName.toUpperCase();
        }
      }

      let toolIcon = "💻";
      let actionPrefix = isRunning ? "正在执行命令" : "已执行命令";
      if (tName.includes("bash") || tName.includes("exec") || tName.includes("terminal")) {
        toolIcon = "💻";
        actionPrefix = isRunning ? "正在执行命令" : "已执行命令";
      } else if (tName.includes("edit") || tName.includes("write") || tName.includes("create")) {
        toolIcon = "✏️";
        actionPrefix = isRunning ? "正在编辑文件" : "已编辑文件";
      } else if (tName.includes("grep") || tName.includes("find") || tName.includes("search")) {
        toolIcon = "🔍";
        actionPrefix = isRunning ? "正在检索代码" : "已检索代码";
      } else if (tName.includes("read") || tName.includes("view") || tName.includes("cat")) {
        toolIcon = "📄";
        actionPrefix = isRunning ? "正在读取文件" : "已读取文件";
      } else if (tName.includes("task") || tName.includes("todo")) {
        toolIcon = "📋";
        actionPrefix = isRunning ? "正在更新任务" : "已更新任务";
      }

      const titleText = `${actionPrefix} ${desc}`;

      if (!card) {
        card = document.createElement("div");
        // 关键改动：默认 100% 收敛！仅在执行中才展开
        card.className = "mimo-tool-card " + (isRunning ? "open running" : "completed");
        card.innerHTML = `
          <div class="tool-header-row" onclick="this.parentElement.classList.toggle('open')">
            <div class="tool-header-left">
              <span class="tool-icon-badge">${toolIcon}</span>
              <span class="tool-cmd-preview" title="${escapeHtml(titleText)}">${escapeHtml(titleText)}</span>
            </div>
            <div class="tool-header-right">
              <div class="tool-status ${status || 'running'}">
                <span class="tool-status-icon"></span>
                <span class="st-text">${labelText}</span>
              </div>
              <span class="tool-chevron">▾</span>
            </div>
          </div>
          <div class="tool-console-box">
            <div class="tool-console-header">
              <span>控制台输出</span>
              <button class="btn-copy-tool" onclick="event.stopPropagation(); copyToolOutput(this)">复制输出</button>
            </div>
            <pre class="tool-output-pre"><code></code></pre>
          </div>
        `;
        wrap.appendChild(card);
        activeToolsMap[callId] = card;
      } else {
        const previewEl = card.querySelector(".tool-cmd-preview");
        if (previewEl && titleText) previewEl.textContent = titleText;
      }

      const stEl = card.querySelector(".tool-status");
      stEl.className = "tool-status " + (status || "running");
      card.querySelector(".st-text").textContent = labelText;

      if (isCompleted) {
        card.classList.remove("running");
        card.classList.add("completed");
        // 执行完毕自动收起，消除屏幕拥堵
        card.classList.remove("open");
      } else if (isFailed) {
        card.classList.remove("running");
        card.classList.add("error");
      }

      if (outputData) {
        const codeEl = card.querySelector(".tool-output-pre code");
        if (codeEl) {
          if (tName.includes("edit") && typeof Prism !== "undefined" && Prism.languages.diff) {
            try {
              codeEl.innerHTML = Prism.highlight(outputData, Prism.languages.diff, "diff");
            } catch (_) {
              codeEl.textContent = outputData;
            }
          } else {
            codeEl.textContent = outputData;
          }
        }
      }
      smartScrollToBottom();
    }

    function appendFeedbackRow(wrap) {
      if (wrap.querySelector(".assistant-feedback-row")) return;
      const row = document.createElement("div");
      row.className = "assistant-feedback-row";
      row.innerHTML = `
        <button class="btn-feedback-action" title="复制全文" onclick="copyAssistantMessage(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>复制全文</span>
        </button>
        <button class="btn-feedback-action" title="重新生成此条回答" onclick="regenerateLastTurn(this)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
          <span>重新生成</span>
        </button>
      `;
      wrap.appendChild(row);
    }

    function startBusyWatch(sid) {
      stopBusyWatch();
      let count = 0;
      busyPollTimer = setInterval(async () => {
        if (!isBusy) {
          stopBusyWatch();
          return;
        }
        count++;
        try {
          const r = await fetch("/api/messages?session_id=" + sid);
          const msgs = await r.json();
          if (Array.isArray(msgs) && msgs.length > 0) {
            const last = msgs[msgs.length - 1];
            const info = last.info || {};
            if (info.role === "assistant") {
              const parts = last.parts || [];
              const hasRunningTool = parts.some(p => p.type === "tool" && p.state?.status === "running");
              const isDone = (info.finish === "stop" || (info.time && info.time.completed)) && !hasRunningTool;
              if (isDone) {
                stopBusyWatch();
                removeThinkingIndicator(activeAssistantBox);
                collapseThinking(activeAssistantBox);
                flushProseRender();
                if (activeAssistantBox && activeAssistantBox.children.length > 0) {
                  if (!activeAssistantBox.dataset.feedbackDone) {
                    appendFeedbackRow(activeAssistantBox);
                    activeAssistantBox.dataset.feedbackDone = "1";
                  }
                } else {
                  loadHistoricalMessages(sid, false);
                }
                setBusy(false);
                activeAssistantBox = null;
                activeTextCard = null;
                activeTextPartId = null;
                activeToolsMap = {};
                loadSessionsList();
                updateContextUsage(sid);
              } else {
                // 运行中持续校验真实轮次开始时间，防止时间偏差
                const parentId = info.parentID;
                let tStart = 0;
                if (parentId) {
                  const parentMsg = msgs.find(m => (m.info?.id === parentId || m.id === parentId));
                  if (parentMsg && parentMsg.info?.time?.created) {
                    tStart = parentMsg.info.time.created;
                  }
                }
                if (!tStart) {
                  for (let i = msgs.length - 1; i >= 0; i--) {
                    if (msgs[i].info?.role === "user" && msgs[i].info?.time?.created) {
                      tStart = msgs[i].info.time.created;
                      break;
                    }
                  }
                }
                if (tStart && (!busyStartTime || tStart < busyStartTime)) {
                  busyStartTime = tStart;
                  paintTaskLiveUI();
                }
              }
            }
          }
        } catch(e) {}
        if (count > 1800) { // 60 分钟长任务兜底
          stopBusyWatch();
          removeThinkingIndicator(activeAssistantBox);
          collapseThinking(activeAssistantBox);
          setBusy(false);
        }
      }, 2000);
    }

    function stopBusyWatch() {
      if (busyPollTimer) {
        clearInterval(busyPollTimer);
        busyPollTimer = null;
      }
    }

    async function sendPrompt() {
      const input = document.getElementById("dock-input");
      const text = input.value.trim();
      if ((!text && !attachedFiles.length) || isBusy) return;

      if (navigator.vibrate) navigator.vibrate(12);

      const topTitle = document.getElementById("top-session-title");
      if (topTitle && (topTitle.textContent === "新任务会话" || topTitle.textContent === "当前任务")) {
        topTitle.textContent = (text || "附件任务").slice(0, 24);
      }

      const sendingFiles = attachedFiles.slice();
      appendUserBubble(text || "请查看所附文件/图片", sendingFiles);
      const filePaths = sendingFiles.map(f => f.path);
      attachedFiles = [];
      renderAttachedFiles();

      input.value = "";
      input.style.height = "auto";
      const promptNow = Date.now();
      busyStartTime = promptNow;
      setBusy(true, promptNow);

      activeAssistantBox = appendAssistantBox();
      activeTextCard = null;
      activeTextPartId = null;
      activeToolsMap = {};
      showThinkingIndicator(activeAssistantBox);

      if (!activeSseSource || activeSseSource.readyState === EventSource.CLOSED) {
        connectSessionSSE(currentSessionId);
      }

      startBusyWatch(currentSessionId);

      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text || "请查看所附文件/图片",
            session_id: currentSessionId,
            model: selectedModelId,
            perm: selectedPerm,
            files: filePaths
          })
        });
        const respText = await r.text();
        let res = {};
        try {
          res = JSON.parse(respText);
        } catch (_) {
          res = { error: respText || "服务器返回了空内容" };
        }
        if (!r.ok) {
          stopBusyWatch();
          removeThinkingIndicator(activeAssistantBox);
          collapseThinking(activeAssistantBox);
          const errMsg = res.error || res.message || res.code || `引擎响应异常 (HTTP ${r.status})`;
          addProseText(activeAssistantBox, "❌ 调度出错: " + errMsg);
          setBusy(false);
        }
      } catch (e) {
        stopBusyWatch();
        removeThinkingIndicator(activeAssistantBox);
        collapseThinking(activeAssistantBox);
        addProseText(activeAssistantBox, "❌ 请求失败: " + e.message);
        setBusy(false);
      }
    }

    function setBusy(busy, startTime) {
      isBusy = busy;
      if (busy) {
        if (startTime && startTime > 0 && startTime <= Date.now()) {
          busyStartTime = startTime;
        } else if (!busyStartTime) {
          busyStartTime = Date.now();
        }
        startTaskLiveUI();
      } else {
        busyStartTime = 0;
        stopBusyWatch();
        removeThinkingIndicator(activeAssistantBox);
        stopTaskLiveUI();
      }
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
      // 快速防抖 150ms 即可，绝不阻塞用户中断意图
      if (Date.now() - busyStartTime < 150) {
        return;
      }
      stopBusyWatch();
      removeThinkingIndicator(activeAssistantBox);
      collapseThinking(activeAssistantBox);
      flushProseRender();
      try {
        await fetch("/api/abort", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: currentSessionId })
        });
        if (activeTextCard) activeTextCard.innerHTML += "<br><em>[已发送 Abort 中止信号]</em>";
      } catch (e) {}
      setBusy(false);
      activeAssistantBox = null;
      activeTextCard = null;
      activeTextPartId = null;
      activeToolsMap = {};
    }

    function markTaskRunning(sid, actualStartTime) {
      if (actualStartTime && actualStartTime > 0 && actualStartTime <= Date.now()) {
        if (!busyStartTime || actualStartTime < busyStartTime || !isBusy) {
          busyStartTime = actualStartTime;
          paintTaskLiveUI();
        }
      } else if (!busyStartTime) {
        busyStartTime = Date.now();
      }
      if (!isBusy) {
        setBusy(true, busyStartTime);
      }
      if (sid && !busyPollTimer) {
        startBusyWatch(sid);
      }
    }

    function connectSessionSSE(sid) {
      if (activeSseSource) activeSseSource.close();
      activeSseSource = new EventSource("/api/events?session_id=" + sid);
      activeSseSource._sid = sid;

      const handleEvt = function(e) {
        if (activeSseSource._sid !== sid) return;
        let ev;
        try { ev = JSON.parse(e.data); } catch(_) { return; }
        const type = ev.type || e.type;

        // ── 1. 思考流（reasoning / reasoning-partial）
        if ((type === "reasoning-partial" || type === "reasoning") && typeof ev.text === "string") {
          markTaskRunning(sid);
          if (!activeAssistantBox) activeAssistantBox = appendAssistantBox();
          removeThinkingIndicator(activeAssistantBox);
          addThinking(activeAssistantBox, ev.text, true);

        // ── 2. 文本流（累积全文，平滑流畅渲染）
        } else if (type === "text-partial" && typeof ev.text === "string") {
          markTaskRunning(sid);
          if (!activeAssistantBox) activeAssistantBox = appendAssistantBox();
          removeThinkingIndicator(activeAssistantBox);
          collapseThinking(activeAssistantBox);
          if (!activeTextCard) {
            activeTextCard = appendProseCard(activeAssistantBox, activeTextPartId || "default");
          }
          updateProseContent(activeTextCard, ev.text);

        // ── 3. ui 事件（tool / text / title / usage / reasoning）
        } else if (type === "ui" && ev.ui) {
          const ui = ev.ui;
          if (!activeAssistantBox) activeAssistantBox = appendAssistantBox();

          if (ui.kind === "text") {
            markTaskRunning(sid);
            removeThinkingIndicator(activeAssistantBox);
            collapseThinking(activeAssistantBox);
            if (ui.partID && ui.partID !== activeTextPartId) {
              activeTextPartId = ui.partID;
              activeTextCard = appendProseCard(activeAssistantBox, ui.partID);
            } else if (!activeTextCard) {
              activeTextCard = appendProseCard(activeAssistantBox, ui.partID || "default");
            }
            if (typeof ui.text === "string") {
              const curLen = parseInt(activeTextCard.dataset.rawLength || "0", 10);
              if (ui.text.length > curLen) {
                updateProseContent(activeTextCard, ui.text);
              }
            }

          } else if (ui.kind === "reasoning" || ui.kind === "thought" || ui.kind === "thinking") {
            markTaskRunning(sid);
            removeThinkingIndicator(activeAssistantBox);
            if (typeof ui.text === "string") {
              addThinking(activeAssistantBox, ui.text, true);
            }

          } else if (ui.kind === "tool") {
            markTaskRunning(sid);
            removeThinkingIndicator(activeAssistantBox);
            flushProseRender();
            activeTextCard = null;
            activeTextPartId = null;

            const out = ui.output || "";
            const desc = ui.description || ui.metadata?.description || ui.input?.description || ui.input?.summary || "";
            addToolCard(activeAssistantBox, ui.callID, ui.tool, ui.status, ui.input, out, desc);

          } else if (ui.kind === "title") {
            const titleEl = document.getElementById("top-session-title");
            if (titleEl && ui.title) titleEl.textContent = ui.title;
          }

        // ── 4. permission 权限事件（已自动准许）
        } else if (type === "permission" || type === "permission.asked") {
          // no-op (已全局放行)

        // ── 5. busy 心跳
        } else if (type === "busy") {
          markTaskRunning(sid);

        // ── 6. idle 完成
        } else if (type === "idle" || type === "session.idle") {
          removeThinkingIndicator(activeAssistantBox);
          collapseThinking(activeAssistantBox);
          flushProseRender();
          if (activeAssistantBox && !activeAssistantBox.dataset.feedbackDone) {
            appendFeedbackRow(activeAssistantBox);
            activeAssistantBox.dataset.feedbackDone = "1";
          }
          setBusy(false);
          activeAssistantBox = null;
          activeTextCard = null;
          activeTextPartId = null;
          activeToolsMap = {};
          stopBusyWatch();
          loadSessionsList();
          updateContextUsage(sid);
          loadSessionContext(sid);
        }
      };

      activeSseSource.onmessage = handleEvt;
      activeSseSource.addEventListener("text-partial", handleEvt);
      activeSseSource.addEventListener("reasoning", handleEvt);
      activeSseSource.addEventListener("reasoning-partial", handleEvt);
      activeSseSource.addEventListener("ui", handleEvt);
      activeSseSource.addEventListener("permission", handleEvt);
      activeSseSource.addEventListener("permission.asked", handleEvt);
      activeSseSource.addEventListener("busy", handleEvt);
      activeSseSource.addEventListener("idle", handleEvt);
      activeSseSource.addEventListener("closed", handleEvt);
      activeSseSource.onerror = function() {
        // SSE 断线自动重连（浏览器内置）
      };
    }

    async 
    let cachedSessionContext = { tasks: { total: 0, items: [] }, git: null };

    async function loadSessionContext(sid) {
      if (!sid) return;
      try {
        const r = await fetch("/api/session_context?session_id=" + sid);
        const data = await r.json();
        cachedSessionContext = data;
        renderContextRibbon(data);
      } catch (_) {}
    }

    function renderContextRibbon(data) {
      const ribbon = document.getElementById("mimo-context-ribbon");
      if (!ribbon) return;

      let hasAny = false;
      // 1. 任务清单胶囊
      const taskBtn = document.getElementById("pill-tasks-btn");
      const taskBadge = document.getElementById("pill-tasks-badge");
      const taskDot = document.getElementById("pill-tasks-dot");
      if (data && data.tasks && data.tasks.total > 0) {
        taskBtn.style.display = "inline-flex";
        taskBadge.textContent = `${data.tasks.done}/${data.tasks.total}`;
        if (data.tasks.in_progress > 0) {
          taskDot.className = "pill-dot pulse";
        } else {
          taskDot.className = "pill-dot";
        }
        hasAny = true;
      } else {
        taskBtn.style.display = "none";
      }

      // 2. 代码变更胶囊
      const gitBtn = document.getElementById("pill-git-btn");
      const gitLabel = document.getElementById("pill-git-files");
      const gitAdd = document.getElementById("pill-git-add");
      const gitDel = document.getElementById("pill-git-del");
      if (data && data.git && data.git.files > 0) {
        gitBtn.style.display = "inline-flex";
        gitLabel.textContent = `${data.git.files} 个文件已更改`;
        gitAdd.textContent = `+${data.git.additions}`;
        gitDel.textContent = `-${data.git.deletions}`;
        hasAny = true;
      } else {
        gitBtn.style.display = "none";
      }

      ribbon.style.display = hasAny ? "flex" : "none";
    }

    function openTaskDrawer() {
      const modal = document.getElementById("task-bottom-sheet");
      const overlay = document.getElementById("task-sheet-overlay");
      const listEl = document.getElementById("task-sheet-list");
      const badgeEl = document.getElementById("task-sheet-badge");
      if (!modal || !overlay) return;

      const tasks = cachedSessionContext?.tasks?.items || [];
      const total = cachedSessionContext?.tasks?.total || 0;
      const done = cachedSessionContext?.tasks?.done || 0;
      badgeEl.textContent = `${done}/${total} 已完成`;

      if (tasks.length === 0) {
        listEl.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-dim); font-size:13px;">当前任务暂无分解清单</div>';
      } else {
        listEl.innerHTML = tasks.map(t => {
          let icon = "○";
          let statusCls = "open";
          if (t.status === "done") {
            icon = "✓";
            statusCls = "done";
          } else if (t.status === "in_progress") {
            icon = "⟳";
            statusCls = "in_progress";
          }
          return `
            <div class="task-item-card ${statusCls}">
              <span class="task-item-icon">${icon}</span>
              <span class="task-item-text">${escapeHtml(t.summary || "未命名子任务")}</span>
            </div>
          `;
        }).join("");
      }

      overlay.classList.add("open");
      modal.classList.add("open");
    }

    function closeTaskDrawer() {
      const modal = document.getElementById("task-bottom-sheet");
      const overlay = document.getElementById("task-sheet-overlay");
      if (modal) modal.classList.remove("open");
      if (overlay) overlay.classList.remove("open");
    }

    function openDiffDrawer() {
      const modal = document.getElementById("diff-bottom-sheet");
      const overlay = document.getElementById("diff-sheet-overlay");
      const listEl = document.getElementById("diff-sheet-list");
      const badgeEl = document.getElementById("diff-sheet-badge");
      if (!modal || !overlay) return;

      const git = cachedSessionContext?.git;
      if (!git || !git.file_list || git.file_list.length === 0) {
        listEl.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-dim); font-size:13px;">暂无修改文件</div>';
      } else {
        badgeEl.textContent = `+${git.additions} -${git.deletions}`;
        listEl.innerHTML = git.file_list.map(f => {
          return `
            <div class="diff-file-card">
              <div class="diff-file-left">
                <span class="diff-file-badge">${escapeHtml(f.status || "M")}</span>
                <span class="diff-file-name" title="${escapeHtml(f.file)}">${escapeHtml(f.file)}</span>
              </div>
            </div>
          `;
        }).join("");
      }

      overlay.classList.add("open");
      modal.classList.add("open");
    }

    function closeDiffDrawer() {
      const modal = document.getElementById("diff-bottom-sheet");
      const overlay = document.getElementById("diff-sheet-overlay");
      if (modal) modal.classList.remove("open");
      if (overlay) overlay.classList.remove("open");
    }

    async function initApp() {
      initMarkdownEngine();

      // 1. 并行同步用户资料、模型配置与会话列表
      loadUserProfile();
      loadModelConfig();
      loadPermConfig();
      loadSessionsList();
      updateContextUsage();

      // 2. 绑定视口滚动检测
      const vp = document.getElementById("chat-viewport");
      if (vp) {
        vp.addEventListener("scroll", checkViewportScroll, { passive: true });
      }

      // 3. 安全超时兜底：若 3 秒内未同步成功，自动解除加载状态，防止卡死
      const safetyTimer = setTimeout(() => {
        const topTitle = document.getElementById("top-session-title");
        if (topTitle && topTitle.textContent === "正在载入...") {
          topTitle.textContent = "当前任务";
        }
        const loader = document.getElementById("init-loader");
        if (loader) {
          loader.innerHTML = '<div class="assistant-prose-card">👋 已连接电脑端 MiMo，请在下方输入描述任务，或点击左上角查看历史会话。</div>';
        }
      }, 3000);

      // 4. 同步电脑端当前活跃任务与历史记录
      try {
        const r = await fetch("/api/active_session");
        const act = await r.json();
        clearTimeout(safetyTimer);
        if (act && act.id) {
          currentSessionId = act.id;
          document.getElementById("top-session-title").textContent = act.title || "当前任务";
          if (act.model) {
            selectedModelId = act.model.canonicalId || act.model.id || selectedModelId;
            selectedModelName = act.model.name || selectedModelName;
            updateDockModelLabel(act.model);
          }
          if (act.is_busy && act.turn_start_time) {
            busyStartTime = act.turn_start_time;
            setBusy(true, act.turn_start_time);
          }
          loadModelConfig(act.id);
          await loadHistoricalMessages(act.id, false);
          connectSessionSSE(act.id);
          updateContextUsage(act.id);
          loadSessionContext(act.id);
        } else {
          document.getElementById("top-session-title").textContent = "新任务";
          if (vp) {
            vp.innerHTML = '<div class="msg-assistant-container"><div class="assistant-prose-card">👋 你好！我是 Xiaomi MiMo，请在下方描述你想要执行的编码或系统任务...</div></div>';
          }
        }
      } catch (e) {
        clearTimeout(safetyTimer);
        document.getElementById("top-session-title").textContent = "离线/待连接";
        if (vp) {
          vp.innerHTML = `<div class="msg-assistant-container"><div class="assistant-prose-card">❌ 连接电脑端服务异常: ${e.message}</div></div>`;
        }
      }
    }

    // 手机锁屏或切换后台唤醒监听：重新切回页面时毫秒级自动对齐耗时与最新消息
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        if (isBusy) {
          paintTaskLiveUI();
        }
        if (currentSessionId) {
          fetch("/api/session_status?session_id=" + currentSessionId)
            .then(r => r.json())
            .then(st => {
              if (st && st.is_busy) {
                if (st.turn_start_time) {
                  busyStartTime = st.turn_start_time;
                  paintTaskLiveUI();
                }
                if (!isBusy) setBusy(true, st.turn_start_time);
              } else if (st && !st.is_busy && isBusy) {
                setBusy(false);
                loadHistoricalMessages(currentSessionId, false);
              }
            })
            .catch(() => {});
          loadSessionContext(currentSessionId);
        }
      }
    });

    // 兼容所有浏览器环境，即使 DOMContentLoaded 早已触发也能即时启动
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initApp);
    } else {
      initApp();
    }
  </script>

  <!-- 移动端任务清单详情抽屉 (Task Checklist Modal) -->
  <div class="mimo-sheet-overlay" id="task-sheet-overlay" onclick="closeTaskDrawer()"></div>
  <div class="mimo-bottom-sheet" id="task-bottom-sheet">
    <div class="mimo-sheet-header">
      <div class="mimo-sheet-title-row">
        <span class="mimo-sheet-title">📋 任务清单</span>
        <span class="mimo-sheet-badge" id="task-sheet-badge">0/0 已完成</span>
      </div>
      <button class="mimo-sheet-close" onclick="closeTaskDrawer()">✕</button>
    </div>
    <div class="mimo-sheet-body" id="task-sheet-list">
      <div style="padding:14px; text-align:center; color:var(--text-dim); font-size:12px;">加载中...</div>
    </div>
  </div>

  <!-- 移动端代码文件变更详情抽屉 (Git Diffs Modal) -->
  <div class="mimo-sheet-overlay" id="diff-sheet-overlay" onclick="closeDiffDrawer()"></div>
  <div class="mimo-bottom-sheet" id="diff-bottom-sheet">
    <div class="mimo-sheet-header">
      <div class="mimo-sheet-title-row">
        <span class="mimo-sheet-title">📄 文件变更</span>
        <span class="mimo-sheet-badge diff-summary" id="diff-sheet-badge">+0 -0</span>
      </div>
      <button class="mimo-sheet-close" onclick="closeDiffDrawer()">✕</button>
    </div>
    <div class="mimo-sheet-body" id="diff-sheet-list">
      <div style="padding:14px; text-align:center; color:var(--text-dim); font-size:12px;">暂无修改文件</div>
    </div>
  </div>

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

    def do_DELETE(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path in ("/api/sessions", "/api/session"):
            sid = query.get("id", [None])[0] or query.get("session_id", [None])[0]
            if not sid:
                self.send_json(400, {"error": "缺少 id 参数"})
                return
            ok = delete_mimo_session(sid)
            self.send_json(200, {"ok": ok, "id": sid})
            return
        self.send_json(404, {"error": "Not Found"})

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
            https_url = get_pwa_https_url_cached()
            runtime_cfg = f'<script>window.MIMO_PWA_HTTPS_URL={json.dumps(https_url or "")};</script>'
            html = XIAOMI_MIMO_PWA_HTML
            if "</head>" in html:
                html = html.replace("</head>", runtime_cfg + "\n</head>", 1)
            else:
                html = runtime_cfg + html
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            # 交给 SW 管缓存：HTTP 层可协商，但不禁止 SW 存档
            self.send_header("Cache-Control", "no-cache")
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

        # 3b. Vendor 依赖库 (Marked & Prism 本地离线缓存支持)
        elif path == "/vendor/marked.min.js":
            body = load_vendor_asset("marked.min.js", FALLBACK_MARKED_JS_B64)
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=604800")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        elif path == "/vendor/prism.min.js":
            body = load_vendor_asset("prism.min.js", FALLBACK_PRISM_JS_B64)
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=604800")
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

        # 4. 图标 (官方 MiMo 原版黑色基底 4 块图腾几何标 & Apple-Touch-Icon 兼容)
        elif path in ("/icons/apple-touch-icon.png", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(APPLE_TOUCH_ICON_PNG)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(APPLE_TOUCH_ICON_PNG)
            return

        elif path in ("/icons/icon-192.png", "/favicon.ico"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(ICON_192_PNG)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(ICON_192_PNG)
            return

        elif path in ("/icons/icon-512.png", "/icons/mimo_official_icon_1024.png"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(ICON_512_PNG)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(ICON_512_PNG)
            return

        elif path in ("/icons/icon-192.svg", "/icons/icon-512.svg", "/icons/icon.svg"):
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(ICON_SVG)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(ICON_SVG)
            return

        # 5. 客户端真实用户头像（动态联动 app 端 mimo.set.avatar 设置）
        elif path == "/icons/avatar.png":
            avatar_bytes = get_desktop_avatar_png()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(avatar_bytes)))
            self.send_header("Cache-Control", "no-cache")  # 动态联动，不缓存
            self.end_headers()
            self.wfile.write(avatar_bytes)
            return

        # 6. 用户信息 API
        elif path == "/api/user":
            self.send_json(200, get_user_profile())
            return

        # 7. 真实模型配置 API (多维映射、会话感知与官方/拓展模型聚合)
        elif path == "/api/model":
            sid = query.get("session_id", [None])[0]
            session_model = get_session_model(sid)
            global_model = get_model_info(get_current_model())
            all_models = get_available_models()
            self.send_json(200, {
                "current": session_model["canonicalId"],
                "session_model": session_model,
                "global": global_model["canonicalId"],
                "global_model": global_model,
                "models": all_models,
            })
            return
        # 8. 审批权限配置 API
        elif path == "/api/perm":
            current_perm = get_current_perm()
            perm_options = [
                {
                    "id": "完全访问权限",
                    "name": "完全访问",
                    "badge": "推荐远程使用",
                    "badgeClass": "badge-amber",
                    "desc": "无需批准即可编辑工作区外文件、运行联网命令，跳过所有权限确认，有安全风险，请谨慎开启",
                },
                {
                    "id": "帮我审批",
                    "name": "帮我审批",
                    "badge": "智能代审",
                    "badgeClass": "badge-blue",
                    "desc": "在本项目内创建、修改、删除文件无需确认；项目外文件访问与常规命令直接放行；危险命令由模型代审",
                },
                {
                    "id": "默认权限",
                    "name": "默认权限",
                    "badge": "手动确认",
                    "badgeClass": "badge-gray",
                    "desc": "读取工作区内文件无需确认；创建、修改文件或执行命令等操作会先弹卡片请你确认",
                },
            ]
            self.send_json(200, {"current": current_perm, "options": perm_options})
            return

        # 9. 获取上传的文件内容 (图片预览/下载)
        elif path == "/api/upload/file":
            filepath = query.get("path", [""])[0]
            if not filepath or not os.path.exists(filepath):
                self.send_json(404, {"error": "文件不存在"})
                return
            ext = os.path.splitext(filepath)[1].lower()
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            try:
                with open(filepath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        # 10. 产物中心列表 API
        elif path == "/api/artifacts":
            cat = query.get("category", ["all"])[0]
            items = get_all_artifacts()
            if cat and cat != "all":
                items = [it for it in items if it.get("category") == cat]
            self.send_json(200, {"ok": True, "artifacts": items})
            return

        # 11. 产物文件直出/预览/下载
        elif path == "/api/artifacts/file":
            filepath = query.get("path", [""])[0]
            download = query.get("download", ["0"])[0] == "1"
            if not filepath or not os.path.exists(filepath):
                self.send_json(404, {"error": "产物文件不存在"})
                return
            ext = os.path.splitext(filepath)[1].lower()
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            try:
                with open(filepath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                if download:
                    fname = os.path.basename(filepath)
                    self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(fname)}"')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        # 12. 上下文用量与 Token 消耗真实 API
        elif path == "/api/context-usage":
            sid = query.get("sessionId", [""])[0] or None
            res = get_context_usage(sid)
            self.send_json(200, res)
            return

        # 周用量统计
        elif path == "/api/weekly-usage":
            self.send_json(200, get_weekly_usage())
            return

        # 订阅配额剩余量（通过 SSO cookies 调用外部 API）
        elif path == "/api/user-quota":
            self.send_json(200, get_user_quota())
            return

        # 13. 插件与技能中心列表 API
        elif path == "/api/plugins":
            items = get_all_plugins()
            self.send_json(200, {"ok": True, "plugins": items, "total": len(items)})
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
            status = get_session_turn_status(act_id) if act_id else {"is_busy": False, "turn_start_time": 0}
            session_model = get_session_model(act_id)
            self.send_json(200, {
                "id": act_id,
                "title": title,
                "is_busy": status.get("is_busy", False),
                "turn_start_time": status.get("turn_start_time", 0),
                "model": session_model,
            })
            return

        # 7b. 查询指定会话的实时工作状态与轮次耗时
        elif path == "/api/session_status":
            sid = query.get("session_id", [None])[0] or get_desktop_current_session_id()
            status = get_session_turn_status(sid) if sid else {"is_busy": False, "turn_start_time": 0}
            self.send_json(200, status)
            return

        # 7c. 查询会话任务清单与代码变更概览 (Task Checklist & Git Diffs)
        elif path == "/api/session_context":
            sid = query.get("session_id", [None])[0] or get_desktop_current_session_id()
            ctx = get_session_context_data(sid) if sid else {}
            if sid:
                ctx["model"] = get_session_model(sid)
            self.send_json(200, ctx)
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
                    active_id = get_desktop_current_session_id()
                    list_data = []
                    for r in rows:
                        s_model = get_session_model(r[0])
                        item = {
                            "id": r[0],
                            "title": r[1] or "未命名任务",
                            "directory": r[2] or DEFAULT_WORKDIR,
                            "time": {"created": r[3], "updated": r[4]},
                            "model": s_model.get("shortName", "Auto"),
                            "modelName": s_model.get("name", "MiMo Auto"),
                            "modelBadge": s_model.get("badge", ""),
                            "modelCategory": s_model.get("category", "official"),
                        }
                        if r[0] == active_id:
                            st = get_session_turn_status(r[0])
                            item["is_busy"] = st.get("is_busy", False)
                            if item["is_busy"]:
                                item["turn_start_time"] = st.get("turn_start_time", 0)
                        list_data.append(item)
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

            # 查询此 session 的真实工作目录 directory
            directory = DEFAULT_WORKDIR
            if os.path.exists(MIMO_DB_PATH):
                try:
                    conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
                    c = conn.cursor()
                    c.execute("SELECT directory FROM session WHERE id = ?", (sid,))
                    row = c.fetchone()
                    if row and row[0]:
                        directory = row[0]
                    conn.close()
                except Exception:
                    pass

            port, token = load_desktop_api_credentials()
            if not port or not token:
                self.send_json(503, {"error": "MiMo 引擎未运行"})
                return

            dir_param = urllib.parse.quote(directory)
            url = f"http://127.0.0.1:{port}/v1/sessions/{sid}/events?dir={dir_param}"
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
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                for raw_line in upstream:
                    self.wfile.write(raw_line)
                    self.wfile.flush()
            except Exception:
                pass
            return

        self.send_json(404, {"error": "Not Found"})

    def do_POST(self):
        try:
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

            # 1c. 删除会话 (从 SQLite 及桌面端同步移除)
            elif path in ("/api/sessions/delete", "/api/session/delete"):
                sid = payload.get("id") or payload.get("session_id")
                if not sid:
                    self.send_json(400, {"error": "缺少 id 参数"})
                    return
                ok = delete_mimo_session(sid)
                self.send_json(200, {"ok": ok, "id": sid})
                return

            # 1b. 同步桌面焦点会话
            elif path == "/api/focus_session":
                sid = payload.get("session_id") or payload.get("id")
                if not sid:
                    self.send_json(400, {"error": "缺少 session_id"})
                    return
                directory = None
                if os.path.exists(MIMO_DB_PATH):
                    try:
                        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
                        c = conn.cursor()
                        c.execute("SELECT directory FROM session WHERE id = ?", (sid,))
                        row = c.fetchone()
                        conn.close()
                        if row:
                            directory = row[0]
                    except Exception:
                        pass
                set_desktop_focus_session(sid, directory=directory)
                self.send_json(200, {"ok": True, "id": sid})
                return

            # 2. 发送任务消息 (携带真实 model 参数 & 完全访问权限自动批准 & 工作目录)
            elif path == "/api/chat":
                msg = payload.get("message", "").strip()
                sid = payload.get("session_id", "").strip()
                raw_model = payload.get("model") or get_session_model(sid)["canonicalId"]
                model = resolve_canonical_model(raw_model)

                if not msg or not sid:
                    self.send_json(400, {"error": "缺少 message 或 session_id"})
                    return

                perm = payload.get("perm") or get_current_perm()
                perm_rules = None
                if perm == "完全访问权限":
                    perm_rules = json.dumps([{"permission": "*", "pattern": "*", "action": "allow"}])
                elif perm == "帮我审批":
                    perm_rules = json.dumps([{"permission": "edit", "pattern": "*", "action": "allow"}])

                # 查询此 session 的真实工作目录 directory、更新标题并预配置权限规则
                directory = DEFAULT_WORKDIR
                if os.path.exists(MIMO_DB_PATH):
                    try:
                        conn = sqlite3.connect(MIMO_DB_PATH, timeout=2)
                        c = conn.cursor()
                        c.execute("SELECT directory, title FROM session WHERE id = ?", (sid,))
                        row = c.fetchone()
                        if row:
                            if row[0]:
                                directory = row[0]
                            if not row[1] or row[1] in ("新任务会话", "新建任务会话", "未命名任务"):
                                new_title = msg.replace("\n", " ")[:32].strip()
                                c.execute(
                                    "UPDATE session SET title = ?, permission = ?, time_updated = ? WHERE id = ?",
                                    (new_title, perm_rules, int(time.time() * 1000), sid),
                                )
                            else:
                                c.execute(
                                    "UPDATE session SET permission = ?, time_updated = ? WHERE id = ?",
                                    (perm_rules, int(time.time() * 1000), sid),
                                )
                            conn.commit()
                        conn.close()
                    except Exception:
                        pass
                set_desktop_focus_session(sid, directory=directory)

                files = payload.get("files", [])
                req_body = {
                    "message": msg,
                    "model": model,
                    "perm": perm,
                    "dir": directory,
                }
                if isinstance(files, list) and files:
                    req_body["files"] = [f for f in files if isinstance(f, str) and f]

                code, res = call_mimo_v1(
                    f"sessions/{sid}/turns",
                    method="POST",
                    body=req_body,
                )
                if not isinstance(res, dict):
                    res = {"error": str(res)}
                elif "error" not in res and code >= 400:
                    if res.get("code") == "busy" or res.get("message") == "session busy":
                        res["error"] = "该任务会话正在执行中，请稍候片刻或点击左上角新建任务"
                    elif res.get("message"):
                        res["error"] = res["message"]
                    elif res.get("code"):
                        res["error"] = res["code"]
                    else:
                        res["error"] = f"MiMo 引擎返回状态码 HTTP {code}"
                self.send_json(code, res)
                return

            # 3. 真实模型切换与 preferences.json 同步持久化
            elif path == "/api/model":
                target = payload.get("model", "mimo-auto").strip()
                sid = payload.get("session_id")
                set_global = payload.get("set_global", True)
                canonical = resolve_canonical_model(target)
                ok = set_current_model(canonical, session_id=sid, set_global=set_global)
                model_info = get_model_info(canonical)
                self.send_json(200, {"ok": ok, "current": canonical, "model": model_info})
                return
            # 3. 权限切换 API
            elif path == "/api/perm":
                target = payload.get("perm", "完全访问权限").strip()
                sid = payload.get("session_id")
                if target in ("完全访问权限", "帮我审批", "默认权限"):
                    ok = set_current_perm(target, session_id=sid)
                    self.send_json(200, {"ok": ok, "current": target})
                else:
                    self.send_json(400, {"error": "不支持的权限类别"})
                return

            # 4. 文件/图片上传 API
            elif path == "/api/upload":
                filename = payload.get("filename", "file.bin")
                content_b64 = payload.get("content", "")
                if not content_b64:
                    self.send_json(400, {"error": "缺少文件内容"})
                    return
                try:
                    raw = base64.b64decode(content_b64)
                    safe_name = re.sub(r"[^a-zA-Z0-9_一-龥\.\-]", "_", os.path.basename(filename))
                    saved_id = uuid.uuid4().hex[:12]
                    saved_path = os.path.join(UPLOAD_DIR, f"{saved_id}_{safe_name}")
                    with open(saved_path, "wb") as f:
                        f.write(raw)
                    self.send_json(200, {
                        "ok": True,
                        "path": saved_path,
                        "name": filename,
                        "size": len(raw),
                        "url": f"/api/upload/file?path={urllib.parse.quote(saved_path)}"
                    })
                except Exception as e:
                    self.send_json(500, {"error": str(e)})
                return

            # 5. 插件/技能启用切换 API
            elif path == "/api/plugins/toggle":
                pid = payload.get("id", "")
                enabled = bool(payload.get("enabled", True))
                if not pid:
                    self.send_json(400, {"error": "缺少插件 ID"})
                    return
                ok = set_plugin_enabled(pid, enabled)
                self.send_json(200, {"ok": ok, "id": pid, "enabled": enabled})
                return

            # 4. 中止当前任务
            elif path == "/api/abort":

                sid = payload.get("session_id")
                code, res = call_mimo_v1(f"sessions/{sid}/abort", method="POST", body={})
                self.send_json(code, res)
                return

            self.send_json(404, {"error": "Not Found"})


        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"服务器内部错误: {str(e)}"})

def validate_pwa_assets() -> None:
    """自动化自检：确保前端 HTML 模板中的 JavaScript 语法 100% 正确，严防卡死与语法白屏"""
    scripts = re.findall(r"<script.*?>([\s\S]*?)</script>", XIAOMI_MIMO_PWA_HTML)
    if not scripts:
        return

    node_bin = shutil.which("node")
    if not node_bin:
        return

    for idx, script_src in enumerate(scripts):
        clean_src = script_src.strip()
        if not clean_src:
            continue
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=True, encoding="utf-8") as tf:
                tf.write(clean_src)
                tf.flush()
                res = subprocess.run(
                    [node_bin, "--check", tf.name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode != 0:
                    err_msg = (
                        f"❌ [PWA 语法致命错误] 前端 HTML 第 {idx} 个 <script> 存在语法错误，已被启动守卫拦截！\n"
                        f"{res.stderr}\n"
                        "服务拒绝启动以防客户端卡在'正在载入...'。请先修复语法错误！"
                    )
                    print(err_msg, file=sys.stderr)
                    sys.exit(1)
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass


def start_pwa_server(
    port: int = DEFAULT_GATEWAY_PORT,
    host: str = "0.0.0.0",
    workdir: Optional[str] = None,
):
    validate_pwa_assets()
    global DEFAULT_WORKDIR
    if workdir:
        workdir = os.path.expanduser(workdir)
        if os.path.isdir(workdir):
            DEFAULT_WORKDIR = workdir
        else:
            print(f"⚠️  忽略无效 --workdir: {workdir}，继续使用 {DEFAULT_WORKDIR}")

    desktop_port, _ = load_desktop_api_credentials()

    if port_in_use(host, port):
        next_port = pick_available_port(host, port + 1)
        if port_in_use(host, next_port) or next_port == port:
            print(f"❌ 端口 {port} 已被占用，请换端口启动，例如: python3 server.py --port {port + 1}")
            sys.exit(1)
        print(f"⚠️  端口 {port} 已被占用，自动切换到 {next_port}")
        port = next_port

    global GATEWAY_LISTEN_PORT
    GATEWAY_LISTEN_PORT = port
    _PWA_HTTPS_CACHE["ts"] = 0.0

    https_url = get_pwa_https_url_cached()
    tailscale_ip = get_tailscale_ip()
    lan_ip = get_local_lan_ip()
    active_sid = get_desktop_current_session_id()
    user = get_user_profile()

    print("================================================================")
    print("🚀 Xiaomi MiMo Desktop 官方极简原质 PWA 网关 (v6.1.0)")
    print("================================================================")
    print(f"📂 数据目录: {MIMO_DATA_DIR}")
    print(f"📂 默认工作目录: {DEFAULT_WORKDIR}")
    if desktop_port:
        print(f"✅ 成功连接电脑端 Xiaomi MiMo 核心引擎 (端口: {desktop_port})")
        print(f"   已继承当前登录小米账号: {user.get('displayName')} (ID: {user.get('userId')})")
        print(f"   已自动锁定电脑当前操作会话: {active_sid}")
    else:
        print("⚠️ 警告: 未检测到 Xiaomi MiMo Desktop 运行凭据，请确保已打开电脑端 Xiaomi MiMo")

    print("\n----------------------------------------------------------------")
    print("📱 手机端访问与真 PWA 安装专属地址：")
    if https_url:
        print("   👉【真正原生 PWA 安装通道（HTTPS 安全证书，无浏览器框）】:")
        print(f"      {https_url}")
    else:
        print("   👉【真正原生 PWA 安装通道】尚未配置指向本网关的 Tailscale HTTPS")
        print(f"      可执行: tailscale serve --https={DEFAULT_TAILSCALE_HTTPS_PORT} --bg {port}")
    if tailscale_ip:
        print(f"\n   👉【Tailscale 远程直连（HTTP 备用通道）】:\n      http://{tailscale_ip}:{port}")
    print(f"\n   👉【同一 Wi-Fi 局域网访问】:\n      http://{lan_ip}:{port}")
    print(f"\n   👉【电脑本机测试】:\n      http://127.0.0.1:{port}")
    print("----------------------------------------------------------------\n")
    print(f"📡 网关监听中 {host}:{port} ... 按 Ctrl+C 退出。\n")
    sys.stdout.flush()

    try:
        server = ReusableThreadingHTTPServer((host, port), XiaomiMiMoPwaHandler)
    except OSError as e:
        print(f"❌ 监听 {host}:{port} 失败: {e}")
        print(f"   可尝试: python3 server.py --port {port + 1} --host 0.0.0.0")
        sys.exit(1)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 网关正在安全停止...")
        server.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Xiaomi MiMo Desktop PWA Gateway")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help="Gateway listen port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Gateway bind address")
    parser.add_argument(
        "--workdir",
        type=str,
        default=None,
        help="Default physical work directory for new sessions (default: ~)",
    )
    args = parser.parse_args()
    start_pwa_server(args.port, host=args.host, workdir=args.workdir)
