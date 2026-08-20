# 黄金价格监测 · GitHub Actions 部署版

> 用 GitHub Actions 定时跑监测任务，**不依赖你任何一台电脑开机**，关掉电脑也照常每 15 分钟取数、到价弹微信。
> 国内金价口径 = 上海金交所 Au99.99 实时报价（元/克），数据源 akshare。
> 多目标金价（默认 880 / 900），价格穿越目标位主动推送 ⚠️ 提醒。

## 文件说明
- `gold_monitor.py` —— 主程序（实时取数 + 多目标穿越检测 + 推送）
- `index.py` —— 腾讯云 SCF 入口（备选方案，本部署用不到）
- `config.example.json` —— 配置模板（**不要**提交真实密钥）
- `config.json` —— 本地用，含真实 WxPusher 凭证（已被 .gitignore 忽略，不会上传）
- `.github/workflows/gold-monitor.yml` —— GitHub Actions 定时任务
- `requirements.txt` —— 依赖

## 部署步骤（约 5 分钟）

### 1. 把代码推到你的 GitHub 仓库
```bash
git init
git add .
git commit -m "init gold monitor"
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```
（也可在 GitHub 网页新建仓库后，把本目录内容上传。）

### 2. 配置 Secrets / Variables（关键，避免把密钥写进代码）
在仓库 **Settings → Secrets and variables → Actions** 里：
- **Secrets** 新建 `WXPUSHER_APP_TOKEN` = 你的 `AT_xxxx`
- **Secrets** 新建 `WXPUSHER_UIDS` = 你的 `UID_xxxx`（多个用逗号分隔）
- **Variables** 新建 `TARGET_PRICES` = `880,900`（多个用逗号分隔）

> 这样 WxPusher 凭证不在代码里，仓库公开也不泄露。

### 3. 开启 Actions
仓库 **Actions** 页 → 找到 "黄金价格监测" workflow → **Enable workflow**。
GitHub 会在下一次 cron 触发（或你点 "Run workflow" 手动触发）时运行。

### 4. 验证
手动触发一次（Actions → 黄金价格监测 → Run workflow），几秒后：
- Actions 日志出现取数成功 + `[push] WxPusher -> 200`
- 你的微信收到一条金价播报

之后每 15 分钟自动跑，金价穿越 880/900 时弹 ⚠️ 到价提醒。

## 频率与免费额度
- **私有仓库**：GitHub Free 每月 Actions 额度约 2000 分钟。默认 `*/15`（约 2880 分钟/月）略超，会产生小额费用；改 `*/30`（1440 分钟/月）稳在免费内。
- **公开仓库**：Actions 免费无限，可放心用 `*/10` 最及时。**注意**：公开仓库会暴露你的监测逻辑与目标价位（非机密，但需知会）。
- 想调频率：编辑 `.github/workflows/gold-monitor.yml` 里的 cron 表达式后 push。

## 状态持久化
穿越检测状态存 `state.json`，每次运行后自动 commit 回仓库，保证跨运行不重复提醒。
（频繁 commit 仅涉及 state.json，不污染业务代码历史。）

## 注意事项
- 数据源为 akshare 免费行情，**分钟级延迟**，实盘以券商/银行终端为准。
- 实时价仅在交易时段更新（日盘 9:00–15:30，夜盘 21:00–02:30），休市时取最后值。
- 本地调试：`python3 gold_monitor.py --once`（读本地 config.json）；算法自测：`python3 gold_monitor.py --test`。
