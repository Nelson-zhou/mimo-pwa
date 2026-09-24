#!/usr/bin/env bash
# ==============================================================================
# Xiaomi MiMo PWA - Pre-Commit Security & Privacy Guard Check
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo -e "${BLUE}🔍 [Security Guard] 正在执行 Git 提交前安全与隐私合规审查...${NC}"

FAILURES=0

# 检查 1: 是否有敏感私钥、数据库或凭证文件被加入暂存区/版本控制
FORBIDDEN_PATTERNS=(
    "mimocode\.db"
    "desktop-api\.json"
    "xiaomi-last-confirmed\.json"
    "\.pem$"
    "\.key$"
    "id_rsa"
    "id_ed25519"
    "Cookies\.db"
    "Local Storage/leveldb"
)

# 获取要检查的文件列表（优先检查暂存区，若无暂存区则检查所有受版本控制的文件）
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM || true)
    if [ -z "$STAGED_FILES" ]; then
        FILES_TO_CHECK=$(git ls-files || true)
    else
        FILES_TO_CHECK="$STAGED_FILES"
    fi
else
    FILES_TO_CHECK=$(find . -type f ! -path "./.git/*")
fi

# 1. 检查文件名
for file in $FILES_TO_CHECK; do
    for pat in "${FORBIDDEN_PATTERNS[@]}"; do
        if echo "$file" | grep -Eq "$pat"; then
            echo -e "${RED}❌ [拦截] 发现高危敏感文件被纳入版本控制: ${file}${NC}"
            FAILURES=$((FAILURES + 1))
        fi
    done
done

# 2. 检查内容中是否包含敏感隐私特征
# 定义检查规则数组: "描述|正则表达式|排除文件正则"
RULES=(
    "硬编码的小米 UID|1225308396"
    "硬编码的 Tailscale 专属 MagicDNS 域名|tail[0-9a-f]{6}\.ts\.net"
    "硬编码的开发者主目录绝对路径|/home/[a-zA-Z0-9._-]+/mimo"
    "内部 scratch 临时工具路径|\.gemini/antigravity"
    "硬编码真实 Bearer 令牌或长秘钥|[0-9a-f]{64}"
)

for file in $FILES_TO_CHECK; do
    # 忽略二进制文件与安全审查脚本自身、说明文档
    if [ ! -f "$file" ] || git check-attr -a "$file" 2>/dev/null | grep -q "binary: set"; then
        continue
    fi
    base_file=$(basename "$file")
    if [ "$base_file" = "security-check.sh" ] || [ "$base_file" = "SECURITY_GUARD.md" ] || [ "$base_file" = "install-hooks.sh" ]; then
        continue
    fi

    for rule in "${RULES[@]}"; do
        DESC=$(echo "$rule" | cut -d'|' -f1)
        REGEX=$(echo "$rule" | cut -d'|' -f2)

        # 在文件中检索命中行
        MATCHES=$(grep -EIn "$REGEX" "$file" 2>/dev/null || true)
        if [ -n "$MATCHES" ]; then
            echo -e "${RED}❌ [拦截] 在文件 ${file} 中检测到敏感内容【${DESC}】:${NC}"
            echo "$MATCHES" | head -n 5 | while read -r line; do
                echo -e "   ${YELLOW}${line}${NC}"
            done
            FAILURES=$((FAILURES + 1))
        fi
    done
done

# 3. 自动化测试套件自检 (语法/防白屏/模型映射)
echo -e "${BLUE}🧪 [PWA Syntax Guard] 运行前端 JavaScript 语法与防白屏自动化自检...${NC}"
if python3 -m unittest tests/test_pwa_syntax.py >/dev/null 2>&1; then
    echo -e "${GREEN}   ✓ 前端 JavaScript 语法与初始化机制 100% 校验通过${NC}"
else
    echo -e "${RED}❌ [拦截] 前端 JavaScript 存在语法错误或防卡死机制失效！${NC}"
    python3 -m unittest tests/test_pwa_syntax.py
    FAILURES=$((FAILURES + 1))
fi

echo -e "${BLUE}🧪 [Model Mapping Guard] 运行模型映射与会话感知自动化自检...${NC}"
if python3 -m unittest tests/test_model_mapping.py >/dev/null 2>&1; then
    echo -e "${GREEN}   ✓ 模型注册表与别名映射机制 100% 校验通过${NC}"
else
    echo -e "${RED}❌ [拦截] 模型映射逻辑或单元测试未通过！${NC}"
    python3 -m unittest tests/test_model_mapping.py
    FAILURES=$((FAILURES + 1))
fi

echo -e "${BLUE}🧪 [PWA Live E2E Guard] 运行本地电脑 PWA 真实访问与渲染回归测试...${NC}"
if python3 -m unittest tests/test_pwa_live_e2e.py >/dev/null 2>&1; then
    echo -e "${GREEN}   ✓ 本地浏览器访问与首屏无头渲染回归测试 100% 校验通过${NC}"
else
    echo -e "${RED}❌ [拦截] 本地 PWA 访问异常或界面渲染报错！${NC}"
    python3 -m unittest tests/test_pwa_live_e2e.py
    FAILURES=$((FAILURES + 1))
fi

# 4. 审查结果判定
echo "----------------------------------------------------------------"
if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}🛑 安全审查未通过！共发现 ${FAILURES} 处潜在隐私或安全问题。${NC}"
    echo -e "${YELLOW}请参阅 SECURITY_GUARD.md 进行脱敏修正后再执行提交。${NC}"
    exit 1
else
    echo -e "${GREEN}✅ 安全与合规审查全部通过！无个人隐私泄露，无违规信息。${NC}"
    exit 0
fi
