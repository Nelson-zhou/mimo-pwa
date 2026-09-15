#!/usr/bin/env bash
# ==============================================================================
# Xiaomi MiMo PWA - Install Git Pre-Commit Security Hook
# ==============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_FILE="${ROOT_DIR}/.git/hooks/pre-commit"

if [ ! -d "${ROOT_DIR}/.git" ]; then
    echo "❌ 错误: 当前目录不是 Git 仓库根目录。"
    exit 1
fi

mkdir -p "${ROOT_DIR}/.git/hooks"

cat > "$HOOK_FILE" <<'EOF'
#!/usr/bin/env bash
# Automatically trigger security-check before commit
ROOT_DIR="$(git rev-parse --show-toplevel)"
"${ROOT_DIR}/scripts/security-check.sh"
EOF

chmod +x "$HOOK_FILE"
chmod +x "${ROOT_DIR}/scripts/security-check.sh"

echo "✅ Git Pre-Commit 安全守卫已成功安装！"
echo "   后续每次执行 git commit 时，都将自动扫描隐私泄漏与合规问题并进行拦截。"
