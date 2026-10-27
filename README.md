<div align="center">

# 🥇 黄金价格监测 · 多目标双向版

**跑在 GitHub Actions 上的个人金价哨兵：定时取价、穿越目标位就弹微信，关机也不停**

[English](#english-version) · 简体中文

</div>

![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)
![Schedule](https://img.shields.io/badge/cron-*/15（目标，实测受限）-orange)
![Push](https://img.shields.io/badge/push-WxPusher-success)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 关于本项目（About）

### 用途

一个**单文件 Python 监测脚本 + 定时任务**，不是 App、不是交易工具。它只做三件事：

1. **取价** —— 抓国际现货黄金（伦敦金 XAU/USD）与在岸美元人民币汇率，换算成 **人民币/克**；
2. **比价** —— 把实时价和你设的目标价位逐一比较，做**穿越检测**（价格从目标位一侧穿到另一侧）；
3. **推送** —— 到价时给微信发一条 ⚠️ 提醒，平时发一条 📊 播报。

解决的痛点：不想 24 小时盯盘、不想装来路不明的行情 App、不想为了一个定时脚本买服务器、不想让自己电脑常开。适合**个人在固定价位分批买入/卖出**的场景（例如"跌破 880 提醒我加仓""涨到 1000 提醒我出货"）。

### 主要功能特性

| 特性 | 说明 |
|---|---|
| 🌙 **24h 不断价** | 基准取国际现货（伦敦金），覆盖上金所闭市时段，避免闭市后基准冻结失真 |
| 🇨🇳 **国内口径对照** | 同时展示国内 Au99.99 参考价（招行公开行情接口），方便核对国际/国内价差 |
| 🔁 **买卖双价** | 基准 ± `cmb_spread`（默认 2.5）→ 买入价（银行卖你）/ 卖出价（银行买你回收），贴合招行黄金账户实际报价 |
| 🎯 **双向多目标** | 【买入组】用买入价，跌破即提醒（默认 880/900）；【卖出组】用卖出价，涨到即提醒（如 1000）。两组独立穿越检测、互不干扰 |
| 🧠 **两层采样** | 距任一目标 ≤1% 进高频层（600s），否则平时层（7200s）。`--loop` 常驻模式下生效 |
| 🔔 **多渠道推送** | WxPusher（个人微信）/ 企业微信机器人 / PushPlus / 控制台，可同时启用 |
| 🔐 **凭证零入库** | 全部走 GitHub Secrets / 环境变量注入；本地 `config.json` 已被 `.gitignore` 排除 |
| 🧪 **自带自检** | `--test` 不依赖网络，直接校验穿越检测与分层算法 |
| ☁️ **三种载体** | GitHub Actions（主）/ 本地常驻 / 腾讯云 SCF 云函数（备选，见 `index.py`） |

### 运行方式

| 方式 | 命令 / 触发 | 适用场景 | 说明 |
|---|---|---|---|
| **GitHub Actions**（主） | `cron: */15` + 手动 `Run workflow` | 长期无人值守 | 免费、关机照跑；频率受 GitHub 调度限制（见「已知限制」） |
| 本地常驻 | `python3 gold_monitor.py --loop` | 想按 10 分钟/2 小时真正采样 | 进程活着才有效，`quiet_normal` 在此模式生效 |
| 本地单次 | `python3 gold_monitor.py --once` | 手动看一眼 / 调试推送样式 | 每次新进程，依赖 `state.json` 做跨运行穿越检测 |
| 算法自检 | `python3 gold_monitor.py --test` | 改代码后验证逻辑 | 不联网，输出 PASS/FAIL |
| 腾讯云 SCF | `index.py` 的 `main_handler` + 定时触发器 | 想脱离 GitHub 限流 | 状态落 `/tmp/gold_state.json`，依赖 warm 实例复用 |

### 使用说明

**① 拿 WxPusher 凭证**
到 [wxpusher.zjiecode.com](https://wxpusher.zjiecode.com) 注册 → 创建应用 → 得到 `appToken`（`AT_xxx`）→ 扫码关注应用拿到 `UID`（`UID_xxx`）。

**② 把代码推到自己的仓库**

```bash
git init && git add . && git commit -m "init gold monitor"
git remote add origin git@github.com:<你的用户名>/<仓库名>.git
git branch -M main && git push -u origin main
```

**③ 配置 Secrets 与 Variables**（仓库 Settings → Secrets and variables → Actions）

Secrets（敏感）：

| Name | Value |
|---|---|
| `WXPUSHER_APP_TOKEN` | `AT_你的appToken` |
| `WXPUSHER_UIDS` | `UID_你的UID`（多个用逗号分隔） |

Variables（普通配置，可留空用默认值）：

| Name | 默认 | 作用 |
|---|---|---|
| `CMB_TARGET_PRICES` | `880,900` | 【买入组】目标，用**买入价**触发跌破提醒；不配则沿用 `TARGET_PRICES` |
| `CMB_TARGET_PRICES_SELL` | 空 | 【卖出组】目标，用**卖出价**触发涨到提醒，如 `1000`；空 = 不监测卖出 |
| `TARGET_PRICES` | `880,900` | 兜底目标，仅当 `CMB_TARGET_PRICES` 未配时生效 |
| `CMB_SPREAD` | `2.5` | 点差偏移（元/克）：基准 ± 此值 = 买卖双价。实测点差约 5 元/克，取半 |
| `CMB_GOLD_LABEL` | `招行黄金` | 买入/卖出价前缀，换银行改这里 |
| `CMB_ACCOUNT_LABEL` | `黄金账户` | 基准行账户名，如 `积存金` / `账户贵金属` |

**④ 启用 workflow**：仓库 Actions 页 → 「黄金价格监测」→ Enable workflow。

**⑤ 手动跑一次验证**：Actions → Run workflow。控制台/微信收到 📊 播报即成功。

之后到价自动弹 ⚠️。想改目标价，直接在 Variables 里改，下次运行即生效，不用改代码。

### 已知限制（Important）

1. **GitHub 的 cron 不是准点闹钟。** 本仓库设为 `*/15`，但实测近 100 次运行的中位间隔是 **283 分钟**（约 4.7 小时），最短 122 分钟、最长近 10 小时。免费 public 仓库的 schedule 会被大幅降级排队，**不要指望分钟级到价提醒**；要真正的分钟级，用本地 `--loop`、SCF 定时触发器或自建服务器。
2. **仓库连续 60 天没有提交，GitHub 会自动禁用定时 workflow**（状态 `disabled_inactivity`）。本项目靠每次运行提交 `state.json` 维持活跃度，并在超过 45 天无提交时自动补一个 keepalive 空提交——即便如此，也建议偶尔看一眼 Actions 页确认还活着。
3. **`state.json` 必须跨运行保留。** 穿越检测依赖它记录"上次价格在目标位的哪一侧"。它已被移出 `.gitignore`，由 workflow 提交回仓库；若换成 `actions/cache`/COS 也行，但绝不能每次全新 checkout。
4. **数据源是公开免费接口**（新浪 `hq.sinajs.cn`、招行 `m.cmbchina.com`），无 SLA、无备用源，字段或反爬策略随时可能变。
5. **`akshare` 不再是默认依赖**（已从 `requirements.txt` 移除）。它只服务于未启用的 SGE 分支（`get_sge_price`），主链路只用 `requests`。若要启用 `source="sge"`，自行 `pip install "akshare>=1.18"`。
6. **`--once` 每次运行都会推一条播报**，`quiet_normal` 只对 `--loop` 生效；cron 真按 15 分钟跑时就是 96 条/天，介意就调大 cron 间隔。

---

## 🎯 修改目标金价

**推荐：GitHub 网页直接改（免 push）** —— Settings → Secrets and variables → Actions → Variables：

- `CMB_TARGET_PRICES` —— 【买入组】目标（买入价跌破提醒），如 `850,920,950`
- `CMB_TARGET_PRICES_SELL` —— 【卖出组】目标（卖出价涨到提醒），如 `1000`；留空 = 不监测卖出
- `TARGET_PRICES` —— 兜底目标（仅当 `CMB_TARGET_PRICES` 未配置时生效）

保存后下一次 cron 触发即生效。`CMB_SPREAD` / `CMB_GOLD_LABEL` / `CMB_ACCOUNT_LABEL` 的含义见上表。

---

## 🔔 推送渠道

| 渠道 | 适用场景 | 配置位置 | 字段 |
|---|---|---|---|
| **WxPusher** ⭐ | 个人微信 | Secrets | `WXPUSHER_APP_TOKEN` + `WXPUSHER_UIDS` |
| 企业微信机器人 | 群内自动发 | Secrets | `WECHAT_WEBHOOK` |
| PushPlus | 微信服务号 | Secrets | `PUSHPLUS_TOKEN` |

> 程序自动检测：字段非空即启用，多个渠道可同时生效。控制台输出始终打印，便于本地调试。

---

## 🧠 核心机制

### 两层采样

| 层级 | 触发条件 | 间隔 | 用途 |
|---|---|---|---|
| **平时层** | 距任一目标 > 1%（`threshold_pct`） | 7200s | 静默期低频播报 |
| **高频层** | 距任一目标 ≤ 1% | 600s | 临近目标及时跟踪 |

> 该机制只在 `--loop` 下真正生效。Actions / `--once` 是定频触发，代码里的 interval 不会被执行，因此这两种模式下**推送正文不再显示"采样层/下次间隔"那一行**，避免让人误以为"下次是 2 小时后"。

### 多目标穿越检测

对每个 (资产, 目标组, 目标价) 独立记录"上次方位"（`above` / `below`），存 `state.json`：

- 之前 `below` + 现在 `above` → **上穿**
- 之前 `above` + 现在 `below` → **下穿**
- 首次运行（无历史状态）不触发提醒，只记录方位

**穿越方向会决定文案，不是只报"穿越了"**。买入组的目标价在价格上方（等跌下来买），所以两种方向的含义完全不同：

| 组 | 穿越方向 | 含义 | 推送 |
|---|---|---|---|
| 买入组 | 下穿（below→above 的反向） | 跌到目标，买入机会出现 | ⚠️ `买入价已跌破目标位 X，可考虑买入` |
| 买入组 | 上穿（below→above） | 价格反弹走开，买入窗口关闭 | ℹ️ `买入价已上穿目标位 X（价格回升，买入窗口关闭）` |
| 卖出组 | 上穿（below→above） | 涨到目标，卖出机会出现 | ⚠️ `卖出价已突破目标位 X，可考虑卖出` |
| 卖出组 | 下穿（above→below） | 价格回落，卖出窗口关闭 | ℹ️ `卖出价已跌破目标位 X（价格回落，卖出窗口关闭）` |

标题前缀跟着严重级别走：出现上面 ⚠️ 那两种（真有操作机会）才用 `⚠️`，只是窗口关闭的用 `ℹ️`。`--test` 里对这四种组合都有断言。

### 到价标注（一眼看方向）

价格到目标位时，在正文对应行追加彩色标注（WxPusher 的 Markdown 支持 `<font color>`）：

| 场景 | 末尾标注 | 文案 | 含义 |
|---|---|---|---|
| 跌破买入目标（用买入价） | `<font color="green">buy</font>` | `**已到价(可买入)**` | 可考虑买入 |
| 涨到卖出目标（用卖出价） | `<font color="red">sale</font>` | `**已到价(可卖出)**` | 可考虑卖出 |
| 远未到价 | 无 | 距离百分比 | 静默参考 |

> 示例：`距 880.00：-1.97% **已到价(可买入)** <font color="green">buy</font>`

**注意"已到价"不等于"刚触发提醒"。** 它只是静态判断「当前价是否已在目标位的可操作一侧」，所以只要价格一直在目标下方，每次播报都会带着 `已到价(可买入)`。真正的提醒只在**跨过目标位的那一次**发（见上面的穿越方向矩阵）。

**所以目标价必须设在还没到达的一侧才有哨兵意义**：当前价 860 时把买入组设成 880/900，等于目标已经在身后——它会永久显示"已到价"并且永远不会发 ⚠️。想被提醒"再跌下来"，目标要设在当前价**下方**（如 840/820）。

**播报含"较上次"**：`- 较上次（10-27 14:58）：+4.66 元（+0.54%）`。Actions 每次是全新进程，上一次的基准价存在 `state.json` 的 `__meta__.last_base` 里，所以跨运行也能算出涨跌；首次运行没有历史值，这一行不显示。

### 数据源与价格口径

**唯一资产：招行纸黄金（黄金账户）**，基准 = 国际现货黄金。

- **主基准**：新浪 `hf_XAU`（伦敦金 XAU/USD）× `fx_susdcny`（在岸 USDCNY）÷ 31.1035（1 金衡盎司克数）= 人民币/克，**直接采用，不叠升贴水**。24h 连续交易。
- **国内参考**：招行 `api/rate/gold` 的 `Au99.99` 报价（无报价时回退 `Au(T+D)` / `Au100g`），仅作对照行，不参与计算。
- **买卖双价**：`买入价 = 基准 + cmb_spread`、`卖出价 = 基准 − cmb_spread`。招行黄金账户无独立公开实时行情，点差约 5 元/克，故默认取 2.5。
- **校准**：若你 App 显示的买卖价与 `基准 ± 2.5` 差得多，直接调 `CMB_SPREAD`。
- **推送首行**：`- **黄金账户** 基准（国际现货）：860.16 元/克（12:54:00）`

---

## 📂 文件结构

```
gold-monitor/
├── gold_monitor.py           # 主程序（取数 + 穿越检测 + 分层 + 推送）
├── index.py                  # 腾讯云 SCF 入口（备选部署）
├── config.example.json       # 配置模板
├── config.json               # 本地真实配置（.gitignore 忽略，需自建）
├── requirements.txt          # Python 依赖（只需 requests）
├── .github/workflows/
│   └── gold-monitor.yml      # GitHub Actions 定时任务
├── state.json                # 穿越检测状态（入库，由 workflow 自动提交）
├── deploy.sh                 # GitHub 一键部署脚本（需 PAT）
├── deploy_guide.md           # 腾讯云 SCF 部署说明
├── DOCUMENTATION.md          # 完整项目文档（架构/机制/排障/配置）
├── LICENSE                   # MIT
└── README.md                 # 本文件
```

---

## 🛠 本地开发

```bash
# 仅需 requests 即可跑主链路；akshare 只服务于未启用的 SGE 分支
pip install requests

# 算法自检（不联网）
python3 gold_monitor.py --test

# 单次运行（读同目录 config.json，无则用默认配置）
python3 gold_monitor.py --once

# 常驻循环（按两层采样真实变频）
python3 gold_monitor.py --loop
```

调试推送样式时，把目标价临时改到实时价附近即可触发穿越提醒：

```bash
CMB_TARGET_PRICES=865 python3 gold_monitor.py --once
```

配置优先级：`DEFAULT_CONFIG`（代码内默认） < `config.json` < 环境变量。环境变量清单见 [DOCUMENTATION.md 附录 B](DOCUMENTATION.md)。

---

## 📈 频率与免费额度

| 仓库类型 | Actions 额度 | 建议 cron | 实测表现 |
|---|---|---|---|
| **Public** | 无限免费 | `*/15` 或更疏 | 名义 15 分钟，实际中位约 4~5 小时一次 |
| **Private** | ~2000 分钟/月 | `*/30` | 同样受调度降级影响，且更易超额度 |

> 单次运行约 30 秒（含安装依赖）。改 `.github/workflows/gold-monitor.yml` 的 `cron:` 后 push 生效。
> 想要分钟级精度：本地 `--loop`（最可靠）、腾讯云 SCF 定时触发器，或任意一台常开机器 + systemd/cron。

---

## 📋 完整文档

架构图、设计取舍、故障排查表、配置字段全表、安全 posture：

👉 [DOCUMENTATION.md](DOCUMENTATION.md)

---

## ⚠️ 免责声明

本项目仅作**技术学习与个人价格监测**用途。

- 数据源为免费公开接口，分钟级延迟，实盘以银行/券商终端为准
- 价格换算存在国际/国内口径差与点差估算误差，**不可作为成交依据**
- 推送内容**不构成任何投资建议**
- public 仓库会公开你的目标价位，介意请转 private（并注意额度）
- 作者不对任何投资盈亏负责

---

## 📜 License

[MIT](LICENSE)

---

<a id="english-version"></a>

## English

A single-file Python price watcher that runs as a scheduled GitHub Actions job. It fetches
spot gold (XAU/USD) and the onshore USD/CNY rate from Sina, converts the price into CNY per gram,
compares it against user-defined target levels, and pushes WeChat notifications via WxPusher
(plus WeCom bot / PushPlus / console as optional channels) whenever the price crosses a level.

Key points: 24h international benchmark instead of a closing-time-frozen domestic quote; dual-sided
buy/sell price derived from `benchmark ± spread`; independent target groups for "buy the dip" and
"sell the top"; crossing state persisted in `state.json` so a level is alerted only once.

**Usage:** fork/push the repo → set `WXPUSHER_APP_TOKEN` / `WXPUSHER_UIDS` as Secrets →
optionally set `CMB_TARGET_PRICES` / `CMB_TARGET_PRICES_SELL` as Variables → enable the workflow.
Local: `python3 gold_monitor.py --once|--loop|--test`.

**Caveat:** GitHub's schedule is best-effort. With `*/15` configured, observed median gap is
~4.7 hours. For minute-level accuracy, run `--loop` on a always-on host.

Full design docs: [DOCUMENTATION.md](DOCUMENTATION.md)
