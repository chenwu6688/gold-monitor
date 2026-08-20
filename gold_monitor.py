#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金价格监测 · 多目标版（支持云函数）
====================================
设计要点：
  1. 后端定时任务 + 可插拔推送，不做完整 App。
  2. 支持【多个目标金价】，分别做穿越检测与到价提醒。
  3. 两层采样：任一目标 ±阈值 内 → 高频(默认10min)，否则平时(默认2h)。
  4. 穿越检测：价格上穿/下穿某目标只提醒一次；状态持久化，云函数无状态也可工作。
  5. 口径：国内金价 = 上海金交所 Au99.99 实时报价（元/克），数据源 akshare.spot_quotations_sge()。
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
    "target_prices": [880.0, 900.0],  # 多目标金价（元/克）；为空时回退单目标 target_price
    "target_price": 950.0,            # 单目标兼容（多目标优先）
    "threshold_pct": 0.01,            # 距任一目标 1% 内 → 进入高频采样层
    "hit_pct": 0.001,                 # 视为"到达"的容差带（0.1%）
    "normal_interval": 7200,          # 平时采样间隔（秒）= 2 小时
    "high_freq_interval": 600,        # 接近目标时高频间隔（秒）= 10 分钟
    "wecom_webhook": "",              # 企业微信机器人 webhook（留空=不启用）
    "pushplus_token": "",             # 微信推送 PushPlus token（可选）
    "wxpusher_app_token": "",         # WxPusher 应用 token（个人微信推送）
    "wxpusher_uids": [],              # WxPusher 接收用户 UID 列表
    "quiet_normal": False,            # True 时平时层不播报，仅到价提醒
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
    if os.environ.get("TARGET_PRICES"):
        cfg["target_prices"] = [float(x.strip()) for x in os.environ["TARGET_PRICES"].split(",") if x.strip()]
    if os.environ.get("TARGET_PRICE"):
        cfg["target_price"] = float(os.environ["TARGET_PRICE"])
    if os.environ.get("WECHAT_WEBHOOK"):
        cfg["wecom_webhook"] = os.environ["WECHAT_WEBHOOK"]
    if os.environ.get("PUSHPLUS_TOKEN"):
        cfg["pushplus_token"] = os.environ["PUSHPLUS_TOKEN"]
    if not cfg.get("target_prices"):
        cfg["target_prices"] = [cfg["target_price"]]
    cfg["target_prices"] = [float(t) for t in cfg["target_prices"]]
    return cfg


def get_targets(cfg):
    return [float(t) for t in (cfg.get("target_prices") or [cfg.get("target_price")])]


# ----------------------------------------------------------------------------
# 数据源：上海金交所 Au99.99 实时报价（元/克）
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


# ----------------------------------------------------------------------------
# 状态：每个目标价位的上一次"方位"(above/below)，用于穿越检测。
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
# 核心分析：多目标穿越检测 + 两层采样
# ----------------------------------------------------------------------------
def analyze(price, prev_price, cfg):
    targets = get_targets(cfg)
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
        prev = analyze_prev_sides.get(t)
        hit = prev is not None and prev != side   # 穿越目标位（上穿或下穿）
        if hit:
            hits.append(t)
        analyze_prev_sides[t] = side

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


def build_content(price, date, a):
    lines = [f"- 国内金价（SGE Au99.99）：**{price:.2f}** 元/克（{date}）"]
    if a["change"] is not None:
        lines.append(f"- 较上次：{a['change']:+.2f} 元（{a['change_pct']:+.2f}%）")
    for t in a["targets"]:
        lines.append(f"- 距目标 {t:.2f}：{a['dists'][t]:+.2f}%")
    lines.append(f"- 采样层：{a['layer']}（下次间隔 {a['interval']}s）")
    return "\n".join(lines)


def _hit_suffix(a):
    hit_list = "、".join(f"{t:.2f}" for t in a["hits"])
    return f"\n\n> ⚠️ 价格已穿越目标位 **{hit_list}** 元/克，请关注操作。"


# ----------------------------------------------------------------------------
# 主循环（本地常驻）
# ----------------------------------------------------------------------------
def run_loop(cfg):
    targets = get_targets(cfg)
    print(f"启动黄金监测 | 目标 {targets} 元/克 | "
          f"平时 {cfg['normal_interval']}s / 高频 {cfg['high_freq_interval']}s")
    prev_price = None
    while True:
        try:
            price, date = get_sge_price()
        except Exception as e:
            print(f"[warn] 取数失败，10s 后重试：{e}")
            time.sleep(10)
            continue

        a = analyze(price, prev_price, cfg)

        if a["hits"]:
            content = build_content(price, date, a) + _hit_suffix(a)
            push(cfg, "⚠️ 金价到达目标位", content)
        elif not cfg.get("quiet_normal", False):
            push(cfg, "📊 黄金价格播报", build_content(price, date, a))

        prev_price = price
        save_state()
        time.sleep(a["interval"])


# ----------------------------------------------------------------------------
# 单次运行（云函数每次触发调用一次）
# ----------------------------------------------------------------------------
def run_once(cfg, save=True):
    price, date = get_sge_price()
    a = analyze(price, None, cfg)
    if a["hits"]:
        content = build_content(price, date, a) + _hit_suffix(a)
        push(cfg, "⚠️ 金价到达目标位（单次）", content)
    else:
        push(cfg, "📊 黄金价格播报（单次）", build_content(price, date, a))
    if save:
        save_state()


# ----------------------------------------------------------------------------
# 算法自测（不依赖网络）
# ----------------------------------------------------------------------------
def run_test():
    cfg = dict(DEFAULT_CONFIG)
    cfg["target_prices"] = [950.0]
    reset_state()
    seq = [940.0, 948.0, 951.0, 955.0, 944.0, 953.0]
    hits, layers = [], []
    for p in seq:
        a = analyze(p, None, cfg)
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
