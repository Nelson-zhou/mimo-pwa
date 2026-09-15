# 🛡️ 工作区统一 Git 安全与个人隐私合规守卫文档 (Universal Security Guardian)

> **核心原则**：本工作区项目根目录及所有关联子项目（`modest-fermi`、`mimo-pwa`、`protected-doc-pdf-exporter`、`mimo-linux-port`）以及所有 AI 对话管家，**强制共用本单一守卫体系**。在执行任何 `git commit` 或 `git push` 前，必须通过本守卫的自动化与人工双重审查，彻底杜绝个人隐私泄露、凭证外流及违规敏感内容。

---

## 📌 1. 守卫体系架构（全对话共用）

所有 AI 对话与终端 Git 操作均受以下单一守卫链路保护：

```mermaid
graph TD
    UserOrAI[用户或 AI 对话发起代码提交] --> Step1[第一道防线: AI 行为准则自检]
    Step1 --> Check1{暂存区是否含有敏感隐私/密钥/违规?}
    Check1 -- 命中风险 --> Stop1[AI 强制拒绝并本地脱敏]
    Check1 -- 合规通过 --> Step2[执行 git commit]
    Step2 --> Step3[第二道防线: 全局 Git Pre-commit 物理拦截]
    Step3 --> ScanScript[统一守卫核心: scripts/git_guard.py]
    ScanScript --> Check2{正则与文件类型审查}
    Check2 -- 命中高危特征 --> Stop2[强制阻断 Exit 1 并标红告警]
    Check2 -- 全部合规 --> Success[提交成功落盘 ✅]
```

* **唯一守卫核心脚本**：[`scripts/git_guard.py`](file:///home/nelson/Documents/antigravity/modest-fermi/scripts/git_guard.py)
* **唯一全局 Git 拦截钩子**：`~/.githooks/pre-commit`（通过 `core.hooksPath` 全局托管，全机所有仓库自动生效）
* **唯一 AI 审查规范**：[`.agents/rules/git-security-guard.md`](file:///home/nelson/Documents/antigravity/modest-fermi/.agents/rules/git-security-guard.md) 与全局 `~/.gemini/config/rules/git-security-guard.md`

---

## 🚨 2. 三大绝对禁止红线 (Zero-Tolerance Redlines)

### 🔴 红线一：个人隐私与身份环境（严禁泄露真实信息）
* **联系方式与公民身份 (PII)**：
  * 严禁提交真实 11 位大陆手机号码、18 位居民身份证号、个人非公开私密邮箱；
  * 测试样例与示例代码必须使用脱敏虚拟占位（如 `13800000000`、`user@example.com`）。
* **账号与平台专有身份**：
  * 严禁硬编码开发者个人的真实小米数字 UID（如 `1225308396` 等）；
  * 严禁硬编码企业微信员工真实姓名、工号或内部通讯录标识。
* **本地物理绝对路径**：
  * 严禁在任何源码、脚本中硬编码个人宿主机系统绝对路径（如 `/home/nelson/...`、`/Users/nelson/...`、`C:\Users\nelson\...`）；
  * 必须使用跨平台相对路径或环境变量动态解析：`$HOME`、`os.path.expanduser('~')`、`Path.home()`。
* **网络拓扑与私有节点**：
  * 严禁泄露个人专属 Tailscale MagicDNS 域名（`tail*.ts.net`）或家庭宽带固定公网 IP。

### 🔴 红线二：密钥凭证与会话鉴权（严禁硬编码机密）
* **API Key 与云凭据**：
  * GitHub 个人访问令牌 (`ghp_`, `gho_`, `github_pat_`)；
  * OpenAI / Claude / Gemini API 密钥 (`sk-`, `sk-ant-`, `AIza...`)；
  * AWS 访问凭证 (`AKIA...`) 及各大云厂商 SecretKey。
* **私钥与证书**：
  * RSA / EC / SSH 私钥文件（`id_rsa`, `id_ed25519`, `*.pem`, `*.key`, `*.pfx`）；
  * 代码中严禁出现 `-----BEGIN PRIVATE KEY-----`。
* **平台会话与 Cookie**：
  * 真实在线文档平台（微盘、腾讯文档、飞书等）提取的真实登录鉴权 Cookie（`skey`, `uin`, `pt_key`, `ptcz`, `session` 等）；
  * 小米鉴权 Token（`passToken`, `serviceToken`）及 64 位十六进制 Bearer 字符串。
* **明文密码与连接串**：
  * 包含密码的数据库连接 URL（如 `postgres://user:password@host...`）；
  * 硬编码密码变量（`password = "..."`）。

### 🔴 红线三：法律法规、违规载荷与敏感制品
* **国家安全与法律底线**：
  * 严格遵守中华人民共和国网络安全法；严禁提交涉及国家秘密、商业机密、颠覆破坏国家统一的内容；
  * 严禁包含涉黄涉赌、网络钓鱼、诈骗或政治有害信息。
* **恶意反渗透与攻击载荷**：
  * 工具仅作为合法授权下的离线阅读与多平台辅助工具，严禁包含木马后门、反弹 Shell、免杀注入载荷或未授权扫描越权代码。
* **敏感产物与数据库隔离**：
  * 严禁提交包含用户真实对话、代码历史与文件路径的本地 SQLite 数据库（如 `mimocode.db`、`Cookies.db`）；
  * 严禁提交包含用户本地运行时凭证的 `desktop-api.json`、`xiaomi-last-confirmed.json`；
  * 严禁提交包含防泄密水印的文档切片（`output/`, `slices/`, `temp/`, `mimo-uploads/`）与真实目标业务 `.pdf` 文件。

---

## 🛠️ 3. 统一守卫工具命令速查

本项目根目录内置了全能扫描引擎 [`scripts/git_guard.py`](file:///home/nelson/Documents/antigravity/modest-fermi/scripts/git_guard.py)：

```bash
# 1. 扫描当前暂存区变更 (与 pre-commit 钩子完全一致)
python3 scripts/git_guard.py

# 2. 全量扫描当前仓库所有源码文件
python3 scripts/git_guard.py --all

# 3. 指定扫描某个特定子项目目录
python3 scripts/git_guard.py --all mimo-pwa
python3 scripts/git_guard.py --all protected-doc-pdf-exporter
python3 scripts/git_guard.py --all mimo-linux-port

# 4. 重新初始化/刷新全局 Git 预提交拦截钩子
python3 scripts/git_guard.py --install-hook
```

---

## 💡 4. 误报豁免与特殊处理规范

1. **环境配置安全分离**：
   * 必须在项目根目录仅维护 `.env.example`（只保留变量声明键名，不包含任何真实密钥值）；真实 `.env` 必须加入 `.gitignore`。
2. **测试数据中包含看似手机号/长数字的误报豁免**：
   * 若确属安全的测试模拟代码且必须包含该数字，可在**该代码行末尾**追加明确标记跳过行扫描：
   ```python
   mock_phone = "13912345678"  # git-guard: ignore
   ```

---

## 🚑 5. 紧急事件与泄密回滚指南 (Incident Response)

如果发现不慎将包含敏感隐私或凭证的代码已执行 Commit：

### 场景 1：已本地 Commit，但尚未 push 到 GitHub
```bash
# 软回滚最近一次提交，文件退回暂存区，修正后再提交
git reset --soft HEAD~1
```

### 场景 2：已 push 到远程公开仓库
1. **立即吊销凭证**：第一时间前往服务商控制台（GitHub / OpenAI / 腾讯等）吊销该 Token 或 Cookie，使其立即失效！
2. **彻底清理历史记录**：
   ```bash
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch <泄密文件路径>' \
     --prune-empty --tag-name-filter cat -- --all
   git push origin --force --all
   ```
