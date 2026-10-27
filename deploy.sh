#!/usr/bin/env bash
#
# 黄金价格监测 · GitHub Actions 一键部署脚本（Ubuntu / Linux）
# 用法：
#   ./deploy.sh [仓库名] [public|private]
# 例：
#   ./deploy.sh gold-monitor public
#
# 登录支持两种方式，优先 gh：
#   1) 已登录 gh  → 直接复用，无需再传 PAT
#   2) 未登录 gh  → 交互式提示粘贴 PAT，仅用于 gh 登录，绝不写入 git remote
#
# 仓库部署通过 GitHub Secrets 注入 WxPusher 凭证，
# 不会把微信凭证写进仓库（安全）。本地调试用的 config.json 已在包内，已 .gitignore 排除。
#
set -euo pipefail

# ---------- 颜色 ----------
G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; B='\033[0;34m'; N='\033[0m'

echo -e "${B}=== 黄金价格监测 · GitHub 一键部署 ===${N}"

# ---------- 0. 定位脚本所在目录（包根）----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo -e "${Y}工作目录: $SCRIPT_DIR${N}"

# ---------- 1. 取参数 ----------
REPO="${1:-gold-monitor}"
VIS="${2:-public}"

# ---------- 2. 依赖检查 ----------
echo -e "${Y}[1/6] 检查依赖...${N}"
for c in git gh unzip python3; do
  if ! command -v "$c" >/dev/null 2>&1; then
    echo -e "${R}缺少命令: $c${N}"; exit 1
  fi
done
echo -e "${G}  git/gh/python3 就绪${N}"

# ---------- 3. gh 登录 ----------
echo -e "${Y}[2/6] 检查 gh 登录态...${N}"
if gh auth status >/dev/null 2>&1; then
  echo -e "${G}  已登录，复用现有凭据${N}"
else
  read -rsp "请输入 GitHub PAT（github_pat_xxx 或 ghp_xxx，仅用于 gh 登录）: " PAT; echo
  if [ -z "${PAT:-}" ]; then
    echo -e "${R}未提供 PAT，退出。${N}"; exit 1
  fi
  printf '%s\n' "$PAT" | gh auth login --with-token 2>&1 | tail -3 || {
    echo -e "${R}gh 登录失败（检查 PAT 是否有效/可访问 api.github.com）${N}"; exit 1
  }
  unset PAT   # 用完立刻清掉，不留内存/环境变量
fi
OWNER="$(gh api user --jq .login)"
echo -e "${G}  已登录为: $OWNER${N}"

# ---------- 4. 创建仓库（若不存在）----------
FULL="$OWNER/$REPO"
echo -e "${Y}[3/6] 确保仓库存在: $FULL ...${N}"
if gh repo view "$FULL" >/dev/null 2>&1; then
  echo -e "${G}  仓库已存在，跳过创建${N}"
else
  VIS_FLAG="--private"; [ "$VIS" = "public" ] && VIS_FLAG="--public"
  gh repo create "$REPO" $VIS_FLAG --description "GitHub Actions 定时监测国际金价换算人民币/克，穿越目标价位推送微信提醒（WxPusher）" 2>&1 | tail -2 || {
    echo -e "${R}创建仓库失败（可能重名或网络问题）${N}"; exit 1
  }
  echo -e "${G}  仓库已创建（$VIS）${N}"
fi

# ---------- 5. git 初始化 & 推送 ----------
echo -e "${Y}[4/6] 初始化并提交...${N}"
git config user.email "bot@example.com" 2>/dev/null || true
git config user.name  "gold-monitor"    2>/dev/null || true

if [ ! -d .git ]; then git init -q; fi
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$FULL.git"
git add .
if git diff --cached --quiet; then
  echo -e "${Y}  无变化，仍继续推送${N}"
else
  git commit -q -m "init gold monitor" 2>&1 | tail -2 || true
fi
git branch -M main

echo -e "${Y}[5/6] 推送到 GitHub...${N}"
# 让 git 复用 gh 的登录态：凭据由 credential helper 提供，
# remote URL 里不带任何 token（把 PAT 塞进 URL 会写进 .git/config 明文留存，
# 一旦 PAT 过期，之后所有 push 都会报 Invalid username or token）。
gh auth setup-git
git remote set-url origin "https://github.com/$FULL.git"
git push -u origin main 2>&1 | tail -5 || {
  echo -e "${R}推送失败（检查仓库名/网络/仓库权限）${N}"; exit 1
}
echo -e "${G}  推送成功 ✅${N}"

# ---------- 6. 启用 Actions ----------
echo -e "${Y}[6/6] 启用 Actions workflow...${N}"
gh workflow enable "黄金价格监测" --repo "$FULL" 2>&1 | tail -2 || {
  echo -e "${Y}  自动启用失败，请到网页手动 Enable（不影响部署）${N}"
}

# ---------- 完成提示 ----------
echo ""
echo -e "${G}========== 部署代码完成 ✅ ==========${N}"
echo -e "${B}仓库地址: https://github.com/$FULL${N}"
echo ""
echo -e "${Y}最后一步（必须你亲自做，安全原因）：配置 WxPusher 微信凭证${N}"
echo -e "  打开: https://github.com/$FULL/settings/secrets/actions"
echo -e "  点 [New repository secret] 添加："
echo -e "    ${B}WXPUSHER_APP_TOKEN${N} = ${G}AT_你的token${N}"
echo -e "    ${B}WXPUSHER_UIDS${N}      = ${G}UID_你的uid${N}"
echo -e "  点 [Variables] 标签 → [New repository variable] 添加："
echo -e "    ${B}CMB_TARGET_PRICES${N}      = ${G}880,900${N}          ${Y}# 买入组：价格跌破即提醒${N}"
echo -e "    ${B}CMB_TARGET_PRICES_SELL${N} = ${G}1000,1200${N}        ${Y}# 卖出组：价格涨到即提醒${N}"
echo ""
echo -e "配置完到 Actions 页面手动 Run workflow 一次，微信收到金价播报即成功。"
echo -e "之后关掉电脑也照常监测。${R}注意：${N}GitHub 免费仓库的 schedule 会被大幅排队，"
echo -e "实测触发间隔中位数约 4~5 小时，不是分钟级；要分钟级请本地跑 ${B}--loop${N} 或部署到云函数。"
echo ""
echo -e "${R}安全提醒：若本次粘贴过 PAT，用完请去 GitHub → Settings → Developer settings 吊销。${N}"
