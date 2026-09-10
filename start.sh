#!/usr/bin/env bash
# ==============================================================================
# Xiaomi MiMo Desktop PWA Gateway - One-click Start Script
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1. 检查 Python 3
if ! command -v python3 &>/dev/null; then
    echo "❌ 错误: 未检测到 Python 3，请先安装 Python 3.9+。"
    exit 1
fi

# 2. 检查 Xiaomi MiMo Desktop 是否已启动
MIMO_API_CONF="$HOME/Library/Application Support/Xiaomi MiMo/desktop-api.json"
if [ ! -f "$MIMO_API_CONF" ]; then
    echo "⚠️  提示: 未检测到电脑端 Xiaomi MiMo 运行凭证。"
    echo "   请确保电脑端【Xiaomi MiMo】已打开运行，以支持双向联动。"
    echo ""
fi

# 3. 检查 Tailscale 状态（可选推荐）
if command -v tailscale &>/dev/null; then
    TS_STATUS=$(tailscale status 2>/dev/null || true)
    if [ -n "$TS_STATUS" ]; then
        echo "✅ Tailscale 已就绪，支持手机安全远程访问与原生 PWA 安装。"
    fi
fi

PORT="${PORT:-8080}"

echo "🚀 正在启动 Xiaomi MiMo PWA 网关 (端口: $PORT)..."
chmod +x "$0"
exec python3 server.py --port "$PORT" "$@"
