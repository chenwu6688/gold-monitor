# 黄金价格监测 · 多目标版 — 项目文档

> 版本：v1.0 ｜ 更新：2026-08-20 ｜ 状态：已上线运行
> 仓库：`chenwu6688/gold-monitor`（GitHub Actions 定时运行）
> 用途：监测上海金交所 Au99.99 实时金价，多目标价位穿越自动微信提醒。

---

## 1. 项目概述

个人黄金价格监测工具：**不依赖第三方 App、不 24 小时盯盘、关机也不停**。

- **数据源**：同时监测【国内金价 SGE Au99.99】(单一价) 与【招行纸黄金(黄金账户)】(买卖双价)。前者经 `akshare` 取数；后者经招行公开行情接口取 Au99.99 基准，± `cmb_spread`(默认 2.5) 得到买入价/卖出价双价。
- **推送**：WxPusher 个人微信主动提醒（默认渠道），同时兼容企业微信机器人 / PushPlus。
- **形态**：后端定时任务 + 条件推送，不做完整 App（避免国产 Android 后台被杀进程）。
- **运行**：GitHub Actions 服务器每 15 分钟运行一次，零服务器成本。

### 满足的核心需求

1. 每 N 分钟反馈最新国内金价（趋势感知）。
2. 可输入多个目标价位，价格穿越时主动提示（触发式决策）。
3. 关机/关电脑后持续运行。

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  GitHub Actions（GitHub 服务器，定时触发，关电脑也运行）                 │
│                                                                        │
│   ┌──────────────┐   cron */15    ┌──────────────────────────────┐    │
│   │ Scheduler    │ ──────────────▶│  monitor job (ubuntu-latest) │    │
│   │ (每 15 分钟) │                │                              │    │
│   └──────────────┘                │  1. Checkout 代码            │    │
│                                   │  2. setup-python 3.12       │    │
│                                   │  3. pip install akshare     │    │
│                                   │  4. python gold_monitor.py  │    │
│                                   │     --once                  │    │
│                                   │  5. git commit state.json   │    │
│                                   └──────────────┬───────────────┘    │
└──────────────────────────────────────────────────┼───────────────────┘
                                                    │
                 ┌──────────────────────────────────┼────────────────────────┐
                 │                                  ▼                        │
                 │                     ┌────────────────────────┐            │
                 │   HTTP 实时行情      │   gold_monitor.py      │            │
                 │   ───────────────▶  │                        │            │
                 │                     │  get_sge_price()       │            │
                 │  ┌─────────────┐    │   数据源: akshare      │            │
                 │  │ 上海金交所   │    │    spot_quotations_sge│            │
                 │  │ Au99.99 实时 │    │                        │            │
                 │  │ 报价 API    │    │  analyze()             │            │
                 │  └─────────────┘    │   多目标穿越检测        │            │
                 │                     │   两层采样             │            │
                 │                     │                        │            │
                 │                     │  push()                │            │
                 │                     │   WxPusher / 企微 /    │            │
                 │                     │   PushPlus / 控制台    │            │
                 │                     └───────────┬────────────┘            │
                 │                                 │                        │
                 │                                 ▼                        │
                 │                     ┌────────────────────────┐          │
                 │                     │  WxPusher API         │          │
                 │                     │  (个人微信推送)        │          │
                 │                     └───────────┬────────────┘          │
                 │                                 │                        │
                 │                                 ▼                        │
                 │                     ┌────────────────────────┐          │
                 │                     │  你的个人微信          │          │
                 │                     │  📊 播报 / ⚠️ 到价提醒 │          │
                 │                     └────────────────────────┘          │
                 │                                                       │
                 │  状态持久化: state.json → git commit 回仓库             │
                 │  (穿越检测状态跨 Actions 运行保留)                      │
                 └───────────────────────────────────────────────────────┘
```

**数据流一句话**：GitHub 定时器 → `gold_monitor.py --once` → akshare 取 SGE 实时金价 → 多目标穿越检测 → WxPusher → 个人微信；穿越状态 `state.json` 提交回仓库持久化。

---

## 3. 文件结构

| 文件 | 作用 | 是否含敏感信息 |
|---|---|---|
| `gold_monitor.py` | 主程序：取数 + 多目标穿越检测 + 两层采样 + 推送 | 否 |
| `index.py` | 腾讯云 SCF 云函数入口（备用部署方案） | 否 |
| `config.example.json` | 配置模板（可提交） | 否（占位符） |
| `config.json` | 本地调试配置（含真实凭证） | **是，已被 .gitignore 排除** |
| `.github/workflows/gold-monitor.yml` | GitHub Actions 定时任务定义 | 否 |
| `requirements.txt` | Python 依赖（akshare + requests） | 否 |
| `state.json` | 穿越检测状态（运行时生成，已 gitignore） | 否 |
| `README_GITHUB.md` | 部署说明（首次部署用） | 否 |
| `deploy_guide.md` | 腾讯云 SCF 部署说明（备用） | 否 |
| `deploy.sh` | 一键部署脚本（首次部署用） | 否 |

> **安全原则**：真实 WxPusher 凭证只存在于 GitHub **Secrets**（仓库设置），不进代码、不进 git 历史。本地调试用 `config.json`（已被忽略）。

---

## 4. 核心设计

### 4.1 数据源与口径

**资产 1 · 国内金价**
- **口径**：上海黄金交易所 Au99.99 **实时报价**（元/克）。
- **取数函数**：`ak.spot_quotations_sge()`，返回盘中实时价（约 2-3 分钟延迟）。
- **交易时段**：日盘 9:00-15:30、夜盘 21:00-02:30；**休市时取到最后一条值**。

**资产 2 · 招行纸黄金（黄金账户）**
- **口径**：招行纸黄金(黄金账户)无独立公开实时行情接口；程序取上金所 Au99.99 为基准，叠加点差得到**买卖双价**：买入价(银行卖你=你的买入成本) = 基准 + `cmb_spread`，卖出价(银行买你=你的卖出回收) = 基准 − `cmb_spread`。实测招行黄金账户点差约 5 元/克（App 显示 买入价 973.18 / 卖出价 968.18），故 `cmb_spread = 5 ÷ 2 = 2.5`。
- **取数函数**：`get_cmb_base_price()` 调用招行公开行情 `https://m.cmbchina.com/api/rate/gold`（无需鉴权、返回 JSON），取 Au99.99 基准报价；双价由运行时按 `± cmb_spread` 计算。
- **双向目标监测**：招行纸黄金有两组独立目标 —— 【买入组】`cmb_target_prices`(默认 880/900) 用**买入价**触发"跌破买入"提醒；【卖出组】`cmb_target_prices_sell`(默认空) 用**卖出价**触发"涨到卖出"提醒。两组各自穿越检测、互不干扰。
- **校准**：若你招行 App 显示的买卖价与 `基准 ± 2.5` 不符，调 `cmb_spread` 即可（点差 5 元/克时取半 2.5；如实测卖价比基准高 3 元，则设 3.0）。

> 两资产均为**免费 + 分钟级延迟**：精度不及付费实时行情，用于趋势感知与到价提醒足够；重大实盘操作以券商/银行终端为准。

### 4.2 多目标穿越检测

- 配置 `target_prices: [880, 900]`（元/克）。
- 对每个目标记录上一次价格"方位"（above / below）。
- **穿越** = 本次方位与上次不同（上穿或下穿）→ 触发一次提醒（防抖动刷屏，同一侧只提醒一次）。
- 状态持久化到 `state.json`，使 GitHub Actions（每次新进程）也能跨运行检测穿越。

### 4.3 两层采样

| 状态 | 触发条件 | 采样频率 | 用途 |
|---|---|---|---|
| **平时层** | 距所有目标 > 1%（`threshold_pct`） | 每 15 分钟（Actions cron） | 趋势感知，低频播报 |
| **高频层** | 距任一目标 ≤ 1% | 每 10 分钟（代码 `high_freq_interval`） | 临近目标时加密采样，避免漏报到价 |

> 说明：GitHub Actions 模式下，cron 固定每 15 分钟触发一次 `--once`；"高频层"在 Actions 模式下表现为：进入 1% 区间后每次运行都判定为高频（下次间隔提示 10 分钟），但实际触发频率仍受 cron 限制为 15 分钟。如需真正 10 分钟高频，将 cron 改为 `*/10`（见第 7 节）。

### 4.4 推送渠道

| 渠道 | 配置字段 | 启用条件 |
|---|---|---|
| **WxPusher（默认）** | `wxpusher_app_token` + `wxpusher_uids` | 两个字段都非空 |
| 企业微信机器人 | `wecom_webhook` | 字段非空 |
| PushPlus | `pushplus_token` | 字段非空 |
| 控制台 | 始终打印 | 内测友好 |

推送内容：Markdown 格式，含金价、距各目标百分比、采样层、到价提醒后缀（⚠️）。

---

## 5. 运行方式

### 5.1 生产环境（已上线）

- **GitHub Actions**：`*.github/workflows/gold-monitor.yml` 中 `schedule: cron '*/15 * * * *'`。
- 每次运行：`pip install` → `python gold_monitor.py --once` → commit `state.json`。
- 完全自动化，无需人工干预。

### 5.2 本地调试

```bash
# 克隆仓库后，复制模板建本地配置
cp config.example.json config.json
# 编辑 config.json 填入你的 WxPusher 凭证（仅本地用）

# 单次运行（取数 + 推送）
python3 gold_monitor.py --once

# 算法自测（不依赖网络）
python3 gold_monitor.py --test

# 本地常驻（需常开机器）
python3 gold_monitor.py --loop
```

### 5.3 备用部署：腾讯云 SCF

`index.py` 是云函数入口（`index.main_handler`），打包 `gold_monitor.py` + `config.json` 上传，定时触发器 `*/10 * * * *`。详见 `deploy_guide.md`。

---

## 6. 部署状态（已验收）

| 验收项 | 结果 | 证据 |
|---|---|---|
| GitHub Actions 定时运行 | ✅ | Run #5 成功，commit `344b4b5` |
| SGE 实时金价取数 | ✅ | akshare `spot_quotations_sge()` |
| 多目标 (880/900) 穿越检测 | ✅ | 算法自测 PASS + 真实推送验证 |
| WxPusher 微信推送 | ✅ | 微信已收到播报 |
| SSH 鉴权（本机 push） | ✅ | `git push` 走 `git@github.com:...` |
| 免 PAT（安全） | ✅ | 已迁移 SSH，旧 PAT 可 Revoke |
| 凭证不入库 | ✅ | `config.json` 已 gitignore |

---

## 7. 运行手册（运维人员参考）

### 7.1 修改目标金价

**方式 A（推荐，不碰代码）**：GitHub 仓库 → Settings → Secrets and variables → Actions → Variables 标签：
- 编辑 `TARGET_PRICES`（国内金价目标）→ 如 `860,880,900`
- 编辑 `CMB_TARGET_PRICES`（招行纸黄金目标，不配则沿用 `TARGET_PRICES`）
- 编辑 `CMB_SPREAD`（招行点差偏移，默认 2.5 = 实测点差 5元/克 ÷ 2）
- 编辑 `CMB_TARGET_PRICES_SELL`（招行纸黄金【卖出组】目标，如 `1000`；空 = 不监测卖出）
- 编辑 `CMB_GOLD_LABEL`（买入/卖出价前缀，默认 `招行黄金`；监测别行改 `工行黄金`/`建行黄金` 等）
- 编辑 `CMB_ACCOUNT_LABEL`（基准行账户名，默认 `黄金账户`；改 `积存金`/`账户贵金属` 等对应不同产品名）
→ Save。下次运行自动生效。

**方式 B（改代码）**：编辑 `config.json` 的 `target_prices` / `cmb_target_prices` / `cmb_target_prices_sell` / `cmb_spread` 字段，提交推送（需本机 SSH）。

### 7.2 修改采样频率

编辑 `.github/workflows/gold-monitor.yml` 第 11 行：

```yaml
- cron: '*/15 * * * *'   # 默认：每 15 分钟
# - cron: '*/10 * * * *' # 更及时（public 仓库免费额度够）
# - cron: '*/30 * * * *' # 更省（private 仓库稳在免费额度内）
```

> 频率取舍：public 仓库 Actions 免费无限分钟，可放心 `*/10`；private 仓库每月 2000 分钟免费额度，`*/15` 约略超、`*/30` 稳在额度内。

### 7.3 开启安静模式（减少打扰）

编辑 `config.json`：`"quiet_normal": true` → 平时层不播报，仅到价时提醒。提交推送生效。

### 7.4 手动触发一次运行

GitHub 仓库 → Actions → 黄金价格监测 → Run workflow → Run。用于验证改动或立即检查价格。

### 7.5 本地验证推送样式

```bash
# 临时把 target 改成接近实时价，跑几次看穿越提醒样式
TARGET_PRICES=970 python3 gold_monitor.py --once
```

---

## 8. 常见问题排查

| 症状 | 可能原因 | 解决 |
|---|---|---|
| 微信收不到播报 | Secrets 未配置或配错位置 | 确认 `WXPUSHER_APP_TOKEN` / `WXPUSHER_UIDS` 在 **Secrets** 标签（非 Variables）；`TARGET_PRICES` 在 **Variables** 标签 |
| 微信收不到播报 | 未用微信关注 WxPusher 应用 | 去 WxPusher 控制台确认 UID 在「用户」列表 |
| Actions 运行成功但无提醒 | 价格未穿越目标（正常） | 当前价距目标 > 1% 时只有普通播报，不弹 ⚠️ |
| 金价长时间不变 | 处于休市时段 | 日盘 9:00-15:30 / 夜盘 21:00-02:30 外取最后值 |
| `state.json` 冲突导致 run 标红 | 本机 push 与定时任务 state 提交冲突 | 不影响监测；可改 state 持久化到分支隔离（见 index.py COS 方案） |
| 取数失败 | akshare 接口变动 / 网络 | 看 Actions 日志 `[warn] 取数失败`；本地 `python3 gold_monitor.py --once` 复现 |
| 招行纸黄金买入/卖出价偏差大 | `cmb_spread` 与实际点差不符 | 对比你招行 App 的买卖价与 `基准 ± cmb_spread`（基准=程序推送的 Au99.99），调 `CMB_SPREAD` / `cmb_spread` |
| 招行接口偶发 404 / 空 | 招行网关波动 | 程序已内置 3 次重试 + Au99.99→Au(T+D)→Au100g 回退；持续失败看 `[warn][招行纸黄金...] 取数失败` |

---

## 9. 安全 Posture

| 资产 | 状态 | 说明 |
|---|---|---|
| GitHub PAT（`gold-monitor`） | 建议 Revoke | 已迁移 SSH，本机 push 不再需要；可删 |
| SSH 密钥 | 在用 | 绑定本机，未来 push 直接用 |
| WxPusher 凭证 | Secrets 隔离 | 仅存 GitHub Secrets，不进代码/历史 |
| 仓库可见性 | public | Actions 免费无限；目标价 880/900 公开无碍 |
| `config.json` | gitignore | 真实凭证不入库 |

**凭证管理建议**：
- WxPusher token/uid 只在 GitHub Secrets 与本地 `config.json` 出现。
- 本机 `git push` 走 SSH，无需 PAT。
- 旧 PAT 如不再使用，GitHub Settings → Personal access tokens → Delete。

---

## 10. 未来可调项清单

1. **频率**：`*/15` → `*/10`（更及时）或 `*/30`（更省）。
2. **安静模式**：`quiet_normal: true` 减少平时打扰。
3. **多目标档位**：改 `TARGET_PRICES` Secret（如 `[860, 880, 900]`）。
4. **阈值带宽**：`threshold_pct`（进入高频层的判定，默认 1%）、`hit_pct`（到达容差，默认 0.1%）。
5. **第二推送渠道**：启用企业微信 / PushPlus 冗余（填对应配置字段）。
6. **数据源升级**：付费实时行情 API（重大实盘场景）。
7. **状态持久化增强**：改用分支隔离或 COS，避免本机 push 冲突（见 `index.py`）。
8. **监控告警**：Actions 失败通知（如取数连续失败）。

---

## 附录 A：配置字段说明

| 字段 | 默认值 | 含义 |
|---|---|---|
| `target_prices` | `[880, 900]` | 多目标金价（元/克） |
| `target_price` | `950` | 单目标兼容（多目标优先） |
| `threshold_pct` | `0.01` | 距目标 1% 内进入高频层 |
| `hit_pct` | `0.001` | 视为到达的容差带（0.1%） |
| `normal_interval` | `7200` | 平时采样间隔（秒） |
| `high_freq_interval` | `600` | 高频采样间隔（秒） |
| `wecom_webhook` | `""` | 企业微信机器人 webhook |
| `pushplus_token` | `""` | PushPlus token |
| `wxpusher_app_token` | `""` | WxPusher 应用 token |
| `wxpusher_uids` | `[]` | WxPusher 接收 UID 列表 |
| `cmb_target_prices` | `[880, 900]` | 招行纸黄金 目标（元/克），缺省沿用 `target_prices` |
| `cmb_spread` | `2.5` | 招行点差偏移（元/克）：基准 Au99.99 ± 此值 = 招行买卖双价 |
| `cmb_target_prices_sell` | `[]` | 招行纸黄金【卖出组】目标（元/克）：用卖出价触发"涨到卖出"提醒；空 = 不监测卖出 |
| `cmb_gold_label` | `"招行黄金"` | 买入/卖出价前缀（可改 `工行黄金`/`建行黄金` 等，对应不同银行产品） |
| `cmb_account_label` | `"黄金账户"` | 基准行账户名（可改 `积存金`/`账户贵金属` 等，对应不同银行产品名） |
| `quiet_normal` | `false` | 平时层是否静默 |

## 附录 B：环境变量覆盖（GitHub Actions 注入）

| 环境变量 | 注入来源 | 覆盖字段 |
|---|---|---|
| `WXPUSHER_APP_TOKEN` | Secrets | `wxpusher_app_token` |
| `WXPUSHER_UIDS` | Secrets | `wxpusher_uids` |
| `TARGET_PRICES` | Variables | `target_prices`（国内金价目标） |
| `CMB_TARGET_PRICES` | Variables（可选） | `cmb_target_prices`（招行纸黄金目标） |
| `CMB_SPREAD` | Variables（可选） | `cmb_spread`（招行点差偏移） |
| `CMB_TARGET_PRICES_SELL` | Variables（可选） | `cmb_target_prices_sell`（招行卖出组目标） |
| `CMB_GOLD_LABEL` | Variables（可选） | `cmb_gold_label`（买入/卖出价前缀） |
| `CMB_ACCOUNT_LABEL` | Variables（可选） | `cmb_account_label`（基准行账户名） |
| `TARGET_PRICE` | Variables（可选） | `target_price` |
| `WECHAT_WEBHOOK` | Secrets（可选） | `wecom_webhook` |
| `PUSHPLUS_TOKEN` | Secrets（可选） | `pushplus_token` |
