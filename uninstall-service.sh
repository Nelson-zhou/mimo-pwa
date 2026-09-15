#!/usr/bin/env bash
# ==============================================================================
# Xiaomi MiMo Desktop PWA Gateway - Uninstall Systemd User Service
# ==============================================================================
set -e

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="mimo-pwa.service"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

echo "🗑️ 正在停止并卸载 Xiaomi MiMo PWA 守护服务..."

if systemctl --user is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl --user stop "$SERVICE_NAME"
    echo "⏹️ 服务已停止。"
fi

if systemctl --user is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl --user disable "$SERVICE_NAME"
    echo "🚫 开机自启已禁用。"
fi

if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    echo "🧹 服务配置文件已移除。"
fi

systemctl --user daemon-reload

echo "✅ Xiaomi MiMo PWA 系统服务已卸载完毕。"
