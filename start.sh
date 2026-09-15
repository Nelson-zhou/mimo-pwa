#!/usr/bin/env bash
# ==============================================================================
# Xiaomi MiMo Desktop PWA Gateway - One-click Start Script
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export PYTHONUNBUFFERED=1

if [ "$1" = "--install-service" ] || [ "$1" = "--service" ]; then
    shift
    exec "$DIR/install-service.sh" "$@"
fi

# 1. 检查 Python 3
if ! command -v python3 &>/dev/null; then
    echo "❌ 错误: 未检测到 Python 3，请先安装 Python 3.9+。"
    exit 1
fi

# 2. 检查 Xiaomi MiMo Desktop 是否已启动（兼容 macOS / Linux 路径）
MIMO_API_CONF=""
for candidate in \
    "$HOME/Library/Application Support/Xiaomi MiMo/desktop-api.json" \
    "$HOME/.config/XiaomiMiMoDesktop/desktop-api.json" \
    "$HOME/.config/Xiaomi MiMo/desktop-api.json" \
    "$HOME/.config/Electron/desktop-api.json"; do
    if [ -f "$candidate" ]; then
        MIMO_API_CONF="$candidate"
        break
    fi
done
if [ -z "$MIMO_API_CONF" ]; then
    echo "⚠️  提示: 未检测到电脑端 Xiaomi MiMo 运行凭证。"
    echo "   请确保电脑端【Xiaomi MiMo】已打开运行，以支持双向联动。"
    echo ""
else
    echo "✅ 已检测到 MiMo Desktop 凭据: $MIMO_API_CONF"
fi

# 3. 检查 Tailscale 状态（可选推荐）
if command -v tailscale &>/dev/null; then
    TS_STATUS=$(tailscale status --peers=false 2>/dev/null || true)
    if [ -n "$TS_STATUS" ] && ! echo "$TS_STATUS" | grep -qi "Stopped"; then
        echo "✅ Tailscale 已就绪，支持手机安全远程访问与原生 PWA 安装。"
    fi
fi

PORT="${PORT:-8080}"

# 4. 端口占用时自动寻找可用端口
port_in_use() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1 && { exec 3>&- 3<&-; return 0; } || return 1
}

if port_in_use "$PORT"; then
    FOUND=""
    for cand in $(seq $((PORT + 1)) $((PORT + 30))); do
        if ! port_in_use "$cand"; then
            FOUND="$cand"
            break
        fi
    done
    if [ -n "$FOUND" ]; then
        echo "⚠️  端口 $PORT 已被占用，自动切换到 $FOUND"
        PORT="$FOUND"
    else
        echo "❌ 端口 $PORT 及附近均被占用，请设置 PORT=xxxx 后重试。"
        exit 1
    fi
fi

echo "🚀 正在启动 Xiaomi MiMo PWA 网关 (端口: $PORT)..."
echo "💡 提示: 若需开机自启且在后台长久常驻，推荐执行: ./install-service.sh"
exec python3 -u server.py --port "$PORT" "$@"
