#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金价格监测 · 多资产 / 多目标 / 双向版（支持云函数）
==============================================

监测资产：
  1. 国内金价 (SGE Au99.99)         —— akshare 取数（单一价，目标=到达提醒）
  2. 招行纸黄金 (黄金账户)           —— 招行公开行情接口取 Au99.99 + 点差偏移（买卖双价，双向目标）

设计要点：
  1. 后端定时任务 + 可插拔推送，不做完整 App。
  2. 每个资产支持【多组目标】，每组独立穿越检测与到价提醒：
       - 招行纸黄金有两组目标：
           * 买入组(cmb_target_prices)   —— 用「买入价」监测，价格【跌破】目标位 → 提醒可买入（默认 880/900）
           * 卖出组(cmb_target_prices_sell) —— 用「卖出价」监测，价格【突破】目标位 → 提醒可卖出（如 1000）
       - 国内金价单一组（目标=到达提醒）。
  3. 两层采样：任一目标 ±阈值 内 → 高频(默认10min)，否则平时(默认2h)。
  4. 穿越检测：价格上穿/下穿某目标只提醒一次；状态持久化，云函数无状态也可工作。
  5. 国内金价口径 = 上海金交所 Au99.99 实时报价（元/克，单一价）。
  6. 招行纸黄金口径（买卖双价）：
       - 数据源：招行公开行情接口 https://m.cmbchina.com/api/rate/gold （取 Au99.99 基准价）
       - 招行纸黄金(黄金账户)没有独立公开实时行情接口，其报价 = 上金所 Au99.99 + 招行点差。
         实测招行黄金账户点差约 5 元/克（买入价 973.18 / 卖出价 968.18，App 实测），
         故 基准价+2.5 ≈ 招行「实时买入价」(银行卖你=你的买入成本)，
             基准价-2.5 ≈ 招行「实时卖出价」(银行买你=你的卖出回收价)。
       - 买入组目标用「买入价」触发（跌破买入）；卖出组目标用「卖出价」触发（突破卖出）。
       - 推送内容**同时展示买入价与卖出价** + 两组目标距离。
       - 若 App 显示买卖价与 基准±2.5 不符，调 cmb_spread 到真实点差的一半。
推送渠道（可同时启用）：WxPusher 微信 / 企业微信机器人 / PushPlus / 控制台。
运行：python3 gold_monitor.py [--once | --test | --loop]
云函数：同目录放 index.py（见 index.py），定时触发器每 10 分钟调一次 --once。
"""
import json
import time
import os
import sys
import datetime
import warnings

warnings.filterwarnings("ignore")

try:
    import akshare as ak
except ImportError:
    ak = None

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")   # 穿越检测状态（云函数可改到 /tmp 或 COS）

DEFAULT_CONFIG = {
    "target_prices": [880.0, 900.0],     # 国内金价 (SGE Au99.99) 目标（元/克）
    "target_price": 950.0,               # 单目标兼容（多目标优先）
    "cmb_target_prices": [880.0, 900.0], # 招行纸黄金【买入组】目标（跌破买入价提醒，元/克）
    "cmb_target_prices_sell": [],        # 招行纸黄金【卖出组】目标（涨到卖出价提醒，元/克；空=不监测卖出）
    "cmb_spread": 2.5,                   # 招行黄金账户点差偏移（元/克）= 实测点差(5元)/2
    "cmb_gold_label": "招行黄金",        # 买入/卖出价前缀（可改成工行黄金/建行黄金等，对应不同银行产品）
    "cmb_account_label": "黄金账户",      # 基准行账户名（可改成积存金/账户贵金属等）
    "threshold_pct": 0.01,               # 距任一目标 1% 内 → 进入高频采样层
    "hit_pct": 0.001,                    # 视为"到达"的容差带（0.1%）
    "normal_interval": 7200,             # 平时采样间隔（秒）= 2 小时
    "high_freq_interval": 600,          # 接近目标时高频间隔（秒）= 10 分钟
    "wecom_webhook": "",                 # 企业微信机器人 webhook（留空=不启用）
    "pushplus_token": "",                # 微信推送 PushPlus token（可选）
    "wxpusher_app_token": "",           # WxPusher 应用 token（个人微信推送）
    "wxpusher_uids": [],                 # WxPusher 接收用户 UID 列表
    "quiet_normal": False,               # True 时平时层不播报，仅到价提醒
}


# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    # 环境变量覆盖（GitHub Actions 用 Secrets/Vars 注入，避免把真实凭证提交进仓库）
    if os.environ.get("WXPUSHER_APP_TOKEN"):
        cfg["wxpusher_app_token"] = os.environ["WXPUSHER_APP_TOKEN"]
    if os.environ.get("WXPUSHER_UIDS"):
        cfg["wxpusher_uids"] = [u.strip() for u in os.environ["WXPUSHER_UIDS"].split(",") if u.strip()]
    if os.environ.get("TARGET_PRICES"):                       # → 国内金价目标
        cfg["target_prices"] = [float(x.strip()) for x in os.environ["TARGET_PRICES"].split(",") if x.strip()]
    if os.environ.get("CMB_TARGET_PRICES"):                   # → 招行买入组目标
        cfg["cmb_target_prices"] = [float(x.strip()) for x in os.environ["CMB_TARGET_PRICES"].split(",") if x.strip()]
    if os.environ.get("CMB_TARGET_PRICES_SELL"):              # → 招行卖出组目标
        cfg["cmb_target_prices_sell"] = [float(x.strip()) for x in os.environ["CMB_TARGET_PRICES_SELL"].split(",") if x.strip()]
    if os.environ.get("CMB_SPREAD"):                         # → 招行点差
        cfg["cmb_spread"] = float(os.environ["CMB_SPREAD"])
    if os.environ.get("CMB_GOLD_LABEL"):                     # → 买入/卖出价前缀
        cfg["cmb_gold_label"] = os.environ["CMB_GOLD_LABEL"]
    if os.environ.get("CMB_ACCOUNT_LABEL"):                  # → 基准行账户名
        cfg["cmb_account_label"] = os.environ["CMB_ACCOUNT_LABEL"]
    if os.environ.get("TARGET_PRICE"):
        cfg["target_price"] = float(os.environ["TARGET_PRICE"])
    if os.environ.get("WECHAT_WEBHOOK"):
        cfg["wecom_webhook"] = os.environ["WECHAT_WEBHOOK"]
    if os.environ.get("PUSHPLUS_TOKEN"):
        cfg["pushplus_token"] = os.environ["PUSHPLUS_TOKEN"]
    # 兜底：招行买入组未单独配置时，沿用国内金价目标
    if not cfg.get("cmb_target_prices"):
        cfg["cmb_target_prices"] = cfg["target_prices"]
    # 类型归一
    cfg["target_prices"] = [float(t) for t in cfg["target_prices"]]
    cfg["cmb_target_prices"] = [float(t) for t in cfg["cmb_target_prices"]]
    cfg["cmb_target_prices_sell"] = [float(t) for t in cfg.get("cmb_target_prices_sell", [])]
    cfg["cmb_spread"] = float(cfg.get("cmb_spread", 0))
    if not cfg["target_prices"]:
        cfg["target_prices"] = [cfg["target_price"]]
    return cfg


def build_assets(cfg):
    """把配置展开为资产列表。

    每个资产有一组或多组目标（group），每组独立穿越检测：
      - side: "price"(单一价) / "buy"(用买入价) / "sell"(用卖出价)
      - suffix: 用于 state key 区分不同组
      - targets: 该组目标价位列表
    """
    return [
        {
            "key": "sge_au9999",
            "name": "国内金价 (SGE Au99.99)",
            "source": "sge",
            "mode": "single",
            "groups": [{"label": "目标", "side": "buy", "suffix": "", "targets": [float(t) for t in cfg["target_prices"]]}],
            "spread": 0.0,
        },
        {
            "key": "cmb_paper_gold",
            "name": "招行纸黄金 (黄金账户)",
            "source": "cmb",
            "mode": "dual",
            "groups": [
                {"label": "买入价目标(跌破买入)", "side": "buy", "suffix": "buy", "targets": [float(t) for t in cfg["cmb_target_prices"]]},
                {"label": "卖出价目标(涨到卖出)", "side": "sell", "suffix": "sell", "targets": [float(t) for t in cfg["cmb_target_prices_sell"]]},
            ],
            "spread": cfg["cmb_spread"],
            "gold_label": cfg["cmb_gold_label"],        # 买入/卖出价前缀（可改银行名）
            "account_label": cfg["cmb_account_label"],  # 基准行账户名（可改产品名）
        },
    ]


# ----------------------------------------------------------------------------
# 数据源
# ----------------------------------------------------------------------------
def get_sge_price(retry=3):
    """返回 (price:float, update_time:str)。取上金所 Au99.99 实时报价。"""
    if ak is None:
        raise RuntimeError("akshare 未安装")
    last_err = None
    for _ in range(retry):
        try:
            df = ak.spot_quotations_sge()
            sub = df[df["品种"] == "Au99.99"]
            if sub.empty:
                sub = df
            row = sub.iloc[-1]
            return float(row["现价"]), str(row["更新时间"])
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"获取金价失败: {last_err}")


def get_cmb_base_price(retry=3):
    """招行纸黄金(黄金账户)基准价 = 上金所 Au99.99 报价（元/克）。
    数据源: 招行公开行情接口 https://m.cmbchina.com/api/rate/gold （无需鉴权，返回 JSON）。
    该接口仅暴露上金所合约行情(Au99.99 / Au(T+D) / Au100g ...)，招行纸黄金本身无独立公开 API，
    故以 Au99.99 报价为基准，调用方再 ± cmb_spread 得到招行纸黄金买卖双价。
    返回 (base_price:float, update_time:str)。
    """
    if requests is None:
        raise RuntimeError("requests 未安装")
    url = "https://m.cmbchina.com/api/rate/gold"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://m.cmbchina.com/goldratedetail.html",
        "Accept": "application/json",
    }
    last_err = None
    for _ in range(retry):
        try:
            r = requests.get(url, headers=headers, timeout=10)
            data = r.json()
            items = data.get("body", {}).get("data", [])
            if not items:
                raise RuntimeError("接口返回空")
            def pick(no):
                row = next((x for x in items if x.get("goldNo") == no), None)
                if row and str(row.get("curPrice")) not in (None, "0.00", ""):
                    return float(row["curPrice"]), str(row.get("time", ""))
                return None
            # 优先 Au99.99，无报价时回退 Au(T+D) / Au100g
            res = pick("AU9999") or pick("AUTD") or pick("AU100G")
            if not res:
                raise RuntimeError("未找到有效金价")
            return res
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"获取招行金价失败: {last_err}")


SOURCE_MAP = {
    "sge": get_sge_price,
    "cmb": get_cmb_base_price,
}


# ----------------------------------------------------------------------------
# 状态：每个 (资产, 组, 目标价位) 的上一次"方位"(above/below)，用于穿越检测。
# 持久化到文件，使云函数（无状态、每次新进程）也能跨调用检测穿越。
# ----------------------------------------------------------------------------
analyze_prev_sides = {}


def reset_state():
    analyze_prev_sides.clear()


def load_state(path=STATE_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            analyze_prev_sides.update(json.load(f))
    except Exception:
        analyze_prev_sides.clear()


def save_state(path=STATE_PATH):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(analyze_prev_sides, f)
    except Exception as e:
        print(f"[warn] 状态保存失败: {e}")


# ----------------------------------------------------------------------------
# 核心分析：单组目标穿越检测 + 两层采样
# ----------------------------------------------------------------------------
def analyze(price, prev_price, targets, key, cfg):
    threshold = cfg["threshold_pct"]

    change = None
    change_pct = None
    if prev_price is not None:
        change = price - prev_price
        change_pct = change / prev_price * 100.0

    hits = []
    any_in_band = False
    for t in targets:
        dist_pct = (price - t) / t * 100.0
        in_band = abs(dist_pct) / 100.0 <= threshold
        if in_band:
            any_in_band = True
        side = "above" if price > t else "below"
        state_key = f"{key}:{t}"
        prev = analyze_prev_sides.get(state_key)
        hit = prev is not None and prev != side   # 穿越目标位（上穿或下穿）
        if hit:
            hits.append(t)
        analyze_prev_sides[state_key] = side

    interval = cfg["high_freq_interval"] if any_in_band else cfg["normal_interval"]
    layer = "高频" if any_in_band else "平时"
    return {
        "price": price,
        "targets": targets,
        "dists": {t: (price - t) / t * 100.0 for t in targets},
        "hits": hits,
        "any_in_band": any_in_band,
        "interval": interval,
        "layer": layer,
        "change": change,
        "change_pct": change_pct,
    }


# ----------------------------------------------------------------------------
# 推送（可同时启用多个渠道）
# ----------------------------------------------------------------------------
def push(cfg, title, content):
    if cfg.get("wecom_webhook") and requests is not None:
        try:
            r = requests.post(
                cfg["wecom_webhook"],
                json={"msgtype": "markdown", "markdown": {"content": f"## {title}\n{content}"}},
                timeout=10,
            )
            print(f"[push] 企业微信 -> {r.status_code}")
        except Exception as e:
            print(f"[push] 企业微信失败: {e}")

    if cfg.get("pushplus_token") and requests is not None:
        try:
            r = requests.post(
                "http://www.pushplus.plus/send",
                json={"token": cfg["pushplus_token"], "title": title,
                      "content": content, "template": "html"},
                timeout=10,
            )
            print(f"[push] PushPlus -> {r.status_code}")
        except Exception as e:
            print(f"[push] PushPlus 失败: {e}")

    if cfg.get("wxpusher_app_token") and cfg.get("wxpusher_uids") and requests is not None:
        try:
            r = requests.post(
                "https://wxpusher.zjiecode.com/api/send/message",
                json={
                    "appToken": cfg["wxpusher_app_token"],
                    "content": content,
                    "summary": title,
                    "contentType": 3,            # 3 = Markdown
                    "uids": cfg["wxpusher_uids"],
                },
                timeout=10,
            )
            print(f"[push] WxPusher -> {r.status_code} {r.text[:80]}")
        except Exception as e:
            print(f"[push] WxPusher 失败: {e}")

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] {title}\n{content}\n{'=' * 48}")


def _compute_groups(asset, raw_price):
    """返回非空目标组的 [(group, monitor_price, buy_price, sell_price)]。"""
    spread = asset.get("spread", 0.0)
    buy = raw_price + spread
    sell = raw_price - spread
    out = []
    for g in asset["groups"]:
        if not g["targets"]:
            continue
        if g["side"] == "buy":
            mp = buy
        elif g["side"] == "sell":
            mp = sell
        else:
            mp = raw_price
        out.append((g, mp, buy, sell))
    return out


def _reach_line(t, dist, reached, side="buy", indent=0):
    """目标距离行。reached=True 时在文末追加彩色字体 buy/sale 标注方向。
    side="buy"  → 价格已跌破目标(到价买入)  → 绿色 buy
    side="sell" → 价格已涨到目标(到价卖出)  → 红色 sale
    排版：未到价 = `距 t：dist%`；到价 = `距 t：dist% **已到价(可买/卖)** <color>tag`
    """
    pad = "    " * indent
    if not reached:
        return f"{pad}距 {t:.2f}：{dist:+.2f}%"
    color = "green" if side == "buy" else "red"
    tag = "buy" if side == "buy" else "sale"
    label = "已到价(可买入)" if side == "buy" else "已到价(可卖出)"
    return f"{pad}距 {t:.2f}：{dist:+.2f}% **{label}** <font color=\"{color}\">{tag}</font>"


def build_asset_content(asset, raw_price, date, results, cfg):
    """results: [(group, analyze_result, monitor_price, buy, sell), ...]"""
    if asset["mode"] == "single":
        g, a, mp, _, _ = results[0]
        lines = [f"- **{asset['name']}**：**{mp:.2f}** 元/克（{date}）"]
        if a["change"] is not None:
            lines.append(f"- 较上次：{a['change']:+.2f} 元（{a['change_pct']:+.2f}%）")
        for t in g["targets"]:
            reached = (mp <= t) if g["side"] == "buy" else (mp >= t)
            lines.append(_reach_line(t, a["dists"][t], reached, side=g["side"]))
        lines.append(f"- 采样层：{a['layer']}（下次间隔 {a['interval']}s）")
        return "\n".join(lines)

    # dual：展示买卖双价 + 每组目标距离
    _, _, _, buy, sell = results[0]
    gl = asset.get("gold_label", "")            # 买入/卖出价前缀（如「招行黄金」）
    al = asset.get("account_label", "黄金账户")  # 基准行账户名（如「黄金账户」）
    prefix = f"{gl} " if gl else ""
    lines = [
        f"- **{al}** 基准 Au99.99：**{raw_price:.2f}** 元/克（{date}）",
        f"- **{prefix}买入价（银行卖你=你买入成本）**：**{buy:.2f}** 元/克",
        f"- {prefix}卖出价（银行买你=你卖出回收）：{sell:.2f} 元/克",
    ]
    any_band = False
    for g, a, mp, _, _ in results:
        side_label = "买入价" if g["side"] == "buy" else "卖出价"
        lines.append(f"- **{g['label']}**（{side_label}监测）：")
        for t in g["targets"]:
            reached = (mp <= t) if g["side"] == "buy" else (mp >= t)
            lines.append(_reach_line(t, a["dists"][t], reached, side=g["side"], indent=1))
        any_band = any_band or a["any_in_band"]
    layer = "高频" if any_band else "平时"
    interval = min((a["interval"] for g, a, mp, _, _ in results), default=cfg["normal_interval"])
    lines.append(f"- 采样层：{layer}（下次间隔 {interval}s）")
    return "\n".join(lines)


def _hit_suffix(g, a):
    hit_list = "、".join(f"{t:.2f}" for t in a["hits"])
    if g["side"] == "buy":
        return f"\n\n> ⚠️ 招行纸黄金**买入价已跌破目标位 {hit_list}** 元/克，可考虑买入。"
    elif g["side"] == "sell":
        return f"\n\n> ⚠️ 招行纸黄金**卖出价已突破目标位 {hit_list}** 元/克，可考虑卖出。"
    return f"\n\n> ⚠️ 价格已穿越目标位 **{hit_list}** 元/克，请关注操作。"


# ----------------------------------------------------------------------------
# 主循环（本地常驻）
# ----------------------------------------------------------------------------
def run_loop(cfg):
    assets = build_assets(cfg)
    print(f"启动黄金监测 | 资产: {[a['name'] for a in assets]} | "
          f"平时 {cfg['normal_interval']}s / 高频 {cfg['high_freq_interval']}s")
    prev = {}   # key: f"{asset_key}:{suffix}" -> 上次监测价
    while True:
        intervals = []
        for asset in assets:
            try:
                raw_price, date = SOURCE_MAP[asset["source"]]()
            except Exception as e:
                print(f"[warn][{asset['name']}] 取数失败，跳过本轮: {e}")
                intervals.append(cfg["normal_interval"])
                continue
            results = []
            for g, mp, buy, sell in _compute_groups(asset, raw_price):
                gkey = f"{asset['key']}:{g['suffix']}"
                a = analyze(mp, prev.get(gkey), g["targets"], gkey, cfg)
                results.append((g, a, mp, buy, sell))
                prev[gkey] = mp
            if not results:
                intervals.append(cfg["normal_interval"])
                continue
            content = build_asset_content(asset, raw_price, date, results, cfg)
            hit_parts = [(g, a) for g, a, mp, _, _ in results if a["hits"]]
            if hit_parts:
                suffix = "".join(_hit_suffix(g, a) for g, a in hit_parts)
                push(cfg, f"⚠️ {asset['name']} 到达目标位", content + suffix)
            elif not cfg.get("quiet_normal", False):
                push(cfg, f"📊 {asset['name']} 播报", content)
            for g, a, mp, _, _ in results:
                intervals.append(a["interval"])
        save_state()
        time.sleep(min(intervals) if intervals else cfg["normal_interval"])


# ----------------------------------------------------------------------------
# 单次运行（云函数每次触发调用一次）
# ----------------------------------------------------------------------------
def run_once(cfg, save=True):
    assets = build_assets(cfg)
    for asset in assets:
        try:
            raw_price, date = SOURCE_MAP[asset["source"]]()
        except Exception as e:
            print(f"[warn][{asset['name']}] 取数失败，跳过: {e}")
            continue
        results = []
        for g, mp, buy, sell in _compute_groups(asset, raw_price):
            gkey = f"{asset['key']}:{g['suffix']}"
            a = analyze(mp, None, g["targets"], gkey, cfg)
            results.append((g, a, mp, buy, sell))
        if not results:
            continue
        content = build_asset_content(asset, raw_price, date, results, cfg)
        hit_parts = [(g, a) for g, a, mp, _, _ in results if a["hits"]]
        if hit_parts:
            suffix = "".join(_hit_suffix(g, a) for g, a in hit_parts)
            push(cfg, f"⚠️ {asset['name']} 到达目标位（单次）", content + suffix)
        else:
            push(cfg, f"📊 {asset['name']} 播报（单次）", content)
    if save:
        save_state()


# ----------------------------------------------------------------------------
# 算法自测（不依赖网络）
# ----------------------------------------------------------------------------
def run_test():
    cfg = dict(DEFAULT_CONFIG)
    reset_state()
    targets = [950.0]
    key = "test"
    seq = [940.0, 948.0, 951.0, 955.0, 944.0, 953.0]
    hits, layers = [], []
    for p in seq:
        a = analyze(p, None, targets, key, cfg)
        hits.append(bool(a["hits"]))
        layers.append(a["layer"])
    expected_hits = [False, False, True, False, True, True]
    expected_layers = ["平时", "高频", "高频", "高频", "高频", "高频"]
    ok = (hits == expected_hits) and (layers == expected_layers)
    print("序列价格      :", seq)
    print("是否触发提醒  :", hits)
    print("期望触发      :", expected_hits)
    print("采样层        :", layers)
    print("期望采样层    :", expected_layers)
    print("RESULT:", "PASS ✅" if ok else "FAIL ❌")
    return ok


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    cfg = load_config()
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if mode == "--once":
        run_once(cfg)
    elif mode == "--test":
        sys.exit(0 if run_test() else 1)
    elif mode == "--loop":
        try:
            run_loop(cfg)
        except KeyboardInterrupt:
            print("\n已停止。")
    else:
        print("用法: python3 gold_monitor.py [--once | --test | --loop]")
