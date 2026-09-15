#!/usr/bin/env bash
# ==============================================================================
# Xiaomi MiMo Desktop PWA Gateway - Install Systemd User Service
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8081}"
PYTHON_BIN="$(which python3 || echo "/usr/bin/python3")"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="mimo-pwa.service"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

echo "📦 正在配置 Xiaomi MiMo PWA 网关为 systemd 用户级常驻守护服务..."

mkdir -p "$SYSTEMD_USER_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Xiaomi MiMo Desktop PWA Gateway
After=network.target

[Service]
Type=simple
WorkingDirectory=${DIR}
ExecStart=${PYTHON_BIN} -u ${DIR}/server.py --port ${PORT}
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

echo "✅ 服务配置文件已生成: $SERVICE_FILE"

# 重载 systemd 并启用启动
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"

# 尝试启用 linger，确保用户终端退出或锁屏后服务仍然常驻
if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$USER" 2>/dev/null || true
fi

echo ""
echo "🎉 安装完成！Xiaomi MiMo PWA 网关已作为系统级守护服务运行。"
echo "   开机自动启动，进程异常时自动重启。"
echo "----------------------------------------------------------------"
echo "🔍 查看服务状态: systemctl --user status mimo-pwa"
echo "📋 查看实时日志: journalctl --user -u mimo-pwa -f"
echo "🔄 重启服务:     systemctl --user restart mimo-pwa"
echo "⏹️ 停止服务:     systemctl --user stop mimo-pwa"
echo "🗑️ 卸载服务:     ./uninstall-service.sh"
echo "----------------------------------------------------------------"
