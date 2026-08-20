<div align="center">

# 🥇 黄金价格监测 · 多目标版

**用 GitHub Actions 定时跑金价监测，关掉电脑也照常弹微信**

[English](#english-version) · 简体中文

</div>

> **国内金价口径** = 上海黄金交易所 Au99.99 实时报价（元/克），数据源 akshare
> **默认监测目标位**：880 / 900 元/克，价格穿越主动 ⚠️ 推送

![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)
![Schedule](https://img.shields.io/badge/cron-every%2015%20min-orange)
![Push](https://img.shields.io/badge/push-WxPusher-success)
![Status](https://img.shields.io/badge/status-running-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ 这是什么？

一个**轻量后端监测任务**（不是完整 App），每 15 分钟在 GitHub 服务器上跑一次：

1. 拉取 SGE Au99.99 国内实时金价
2. 对比多个目标价位（默认 880 / 900）
3. 价格穿越目标位时，通过 **WxPusher** 主动推送到你的个人微信
4. 状态自动 commit 回仓库，跨运行不重复提醒

### 核心特性

- 🆓 **完全免费** — 公开仓库 Actions 无限额度
- 🖥 **零运维** — GitHub 服务器跑，电脑关掉也不影响
- 🔐 **密钥零泄露** — WxPusher 凭证走 GitHub Secrets，不进代码
- 🎯 **多资产 + 多目标 + 双向监测** — 同时监测【国内金价 SGE Au99.99】与【招行纸黄金(买卖双价)】；招行支持**买入组(跌破买入价提醒 880/900)** 与 **卖出组(涨到卖出价提醒，如 1000)** 两组独立目标
- ⚡ **智能采样** — 任一资产接近目标时 10 分钟一次，平时 2 小时一次
- 🔌 **多渠道推送** — WxPusher / 企业微信 / PushPlus 可同时启用

---

## 🚀 快速开始（5 分钟）

### 1. 准备 WxPusher 凭证
访问 [wxpusher.zjiecode.com](https://wxpusher.zjiecode.com) 注册并创建应用，拿到：
- `appToken`（格式 `AT_xxx`）
- `UID`（格式 `UID_xxx`，扫码关注你的应用获取）

### 2. 推送代码到你的 GitHub 仓库
```bash
# 在本项目目录
git init
git add .
git commit -m "init gold monitor"
git remote add origin git@github.com:<你的用户名>/<仓库名>.git
git branch -M main
git push -u origin main
```

### 3. 在 GitHub 配置 Secrets 和 Variables
路径：**Settings → Secrets and variables → Actions**

**Secrets（敏感凭证）**

| Name | Value |
|---|---|
| `WXPUSHER_APP_TOKEN` | `AT_你的appToken` |
| `WXPUSHER_UIDS` | `UID_你的UID`（多个用逗号分隔） |

**Variables（普通配置）**

| Name | Value | 作用 |
|---|---|---|
| `TARGET_PRICES` | `880,900` | 国内金价 (SGE Au99.99) 目标，逗号分隔 |
| `CMB_TARGET_PRICES` | `880,900` | 招行纸黄金 目标，逗号分隔（不配则沿用 `TARGET_PRICES`） |
| `CMB_SPREAD` | `2.5` | 招行点差偏移（元/克）：基准 Au99.99 ± 此值 = 招行**买卖双价**（实测点差约 5 元/克，取半 2.5） |
| `CMB_TARGET_PRICES_SELL` | （空） | 招行纸黄金【卖出组】目标，逗号分隔；用于"涨到卖出价提醒"，如 `1000`（空 = 不监测卖出） |

### 4. 启用 Workflow
仓库 **Actions** 页 → 找到「黄金价格监测」→ **Enable workflow**

### 5. 手动触发一次
**Actions → 黄金价格监测 → Run workflow** → 几秒后微信收到金价播报 ✅

之后每 15 分钟自动跑，到价时弹 ⚠️ 提醒。

---

## 🎯 修改目标金价

**推荐：在 GitHub 网页直接改（免 push）**

**Settings → Secrets and variables → Actions → Variables**
- `TARGET_PRICES` —— 国内金价 (SGE Au99.99) 目标，如 `850,920,950`
- `CMB_TARGET_PRICES` —— 招行纸黄金 目标，如 `850,920,950`（不配则沿用 `TARGET_PRICES`）

保存后**下一次 cron 触发即生效**。
- `CMB_SPREAD`：调招行点差偏移（默认 2.5 = 实测点差 5元/克 ÷ 2）。
- `CMB_TARGET_PRICES_SELL`：招行纸黄金**卖出组**目标（如 `1000`），用于"涨到卖出价提醒"；**留空 = 不监测卖出**。买入组 `CMB_TARGET_PRICES`(默认 880/900) 继续负责"跌破买入提醒"，两组独立并存。

---

## 🔔 推送渠道

| 渠道 | 适用场景 | 配置位置 | 字段 |
|---|---|---|---|
| **WxPusher** ⭐ | 个人微信 | Secrets | `WXPUSHER_APP_TOKEN` + `WXPUSHER_UIDS` |
| 企业微信机器人 | 公司群自动发 | Secrets | `WECHAT_WEBHOOK` |
| PushPlus | 微信服务号 | Secrets | `PUSHPLUS_TOKEN` |

> 默认只启用 WxPusher。要同时启用其他渠道，把对应字段加到 Secrets 即可，程序会自动检测并推送。

---

## 🧠 核心机制

### 两层采样
| 层级 | 触发条件 | 间隔 | 用途 |
|---|---|---|---|
| **平时层** | 距任一目标 > 1% | 2 小时 | 静默期低频播报 |
| **高频层** | 距任一目标 ≤ 1% | 10 分钟 | 临近目标及时跟踪 |

### 多目标穿越检测
对每个目标价位独立追踪"上次方位"（above / below）：
- 之前 `below` + 现在 `above` → **上穿** → 弹 ⚠️
- 之前 `above` + 现在 `below` → **下穿** → 弹 ⚠️
- 状态存 `state.json` 并自动 commit 回仓库，跨运行不重复提醒

### 数据源
**资产 1 · 国内金价**
- **接口**：`akshare.spot_quotations_sge()`
- **品种**：Au99.99
- **延迟**：分钟级（实盘以券商/银行终端为准）
- **交易时段**：日盘 9:00–15:30，夜盘 21:00–02:30（休市时取最后值）

**资产 2 · 招行纸黄金（黄金账户）**
- **接口**：招行公开行情 `https://m.cmbchina.com/api/rate/gold`（无需鉴权，返回 JSON）
- **口径**：招行纸黄金(黄金账户)无独立公开实时接口；程序取上金所 Au99.99 为基准，叠加点差得到**买卖双价**：
  - **买入价（银行卖你 = 你的买入成本）= 基准 + cmb_spread**（默认 2.5）
  - **卖出价（银行买你 = 你的卖出回收）= 基准 − cmb_spread**
  - 实测招行黄金账户点差约 **5 元/克**（买入价 973.18 / 卖出价 968.18，App 实测），故 `cmb_spread = 5 ÷ 2 = 2.5`
- **双向目标监测**：招行纸黄金有两组独立目标 —— 【买入组】`cmb_target_prices`(默认 880/900) 用**买入价**触发"跌破买入"提醒；【卖出组】`cmb_target_prices_sell`(默认空) 用**卖出价**触发"涨到卖出"提醒。两组各自穿越检测、互不干扰。
- **推送内容**：同时展示买入价与卖出价，一眼看清两边成交价。
- **校准**：若你 App 显示的买卖价与 `基准 ± 2.5` 不符，调 `CMB_SPREAD` 即可。
- **延迟**：分钟级，交易时段实时更新

---

## 📂 文件结构

```
gold-monitor/
├── gold_monitor.py           # 主程序（取数 + 穿越检测 + 推送）
├── index.py                  # 腾讯云 SCF 入口（备选部署）
├── config.example.json       # 配置模板
├── config.json               # 本地真实配置（.gitignore 忽略）
├── requirements.txt          # Python 依赖
├── .github/
│   └── workflows/
│       └── gold-monitor.yml  # GitHub Actions 定时任务
├── state.json                # 穿越检测状态（自动 commit）
├── deploy.sh                 # 一键部署脚本
├── deploy_guide.md           # 详细部署指南
├── README.md                 # 本文件（仓库门面）
└── DOCUMENTATION.md          # 完整项目文档
```

---

## 🛠 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 算法自测（不依赖网络）
python3 gold_monitor.py --test

# 单次运行（读本地 config.json）
python3 gold_monitor.py --once

# 常驻循环（需常开机器）
python3 gold_monitor.py --loop
```

调试时复制 `config.example.json` 为 `config.json` 并填入凭证。

---

## 📈 频率与免费额度

| 仓库类型 | Actions 额度 | 推荐 cron | 到价提醒延迟 |
|---|---|---|---|
| **Public** | 无限免费 | `*/10` | ≤ 10 分钟 |
| **Private** | ~2000 分钟/月 | `*/30` | ≤ 30 分钟 |

修改 `.github/workflows/gold-monitor.yml` 的 `cron:` 字段后 push 即可。

---

## 📋 完整文档

深度设计、故障排查、安全 posture、配置字段说明、环境变量覆盖：

👉 [DOCUMENTATION.md](DOCUMENTATION.md)

---

## ⚠️ 免责声明

本项目仅作**技术学习与个人监测用途**。

- 数据源 `akshare` 为免费行情接口，**分钟级延迟**，实盘以券商/银行终端为准
- 推送内容**不构成任何投资建议**
- 公开仓库会暴露监测逻辑（目标价位等），如有隐私需求请用 Private 仓库
- 仓库作者不对任何投资盈亏负责

---

## 📜 License

[MIT](LICENSE)

---

<a id="english-version"></a>

## English

A lightweight backend job that monitors Shanghai Gold Exchange (SGE) Au99.99 price
every 15 minutes on GitHub Actions, pushes WeChat alerts via WxPusher when price
crosses user-defined target levels (default 880 / 900 CNY/g). Multi-target
crossing detection, two-layer adaptive sampling, zero server cost, zero
credential leakage (Secrets).

Full design docs: [DOCUMENTATION.md](DOCUMENTATION.md)
