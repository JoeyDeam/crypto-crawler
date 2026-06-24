#!/usr/bin/env python3
"""
币圈 + 黄金 日报推送系统
抓取 BTC / ETH / DOGE / 黄金 实时价格 → 格式化日报 → PushPlus 推送到微信

用法:
    python daily_report.py          # 立即运行一次
    python daily_report.py --test   # 测试模式，不实际推送

定时运行（推荐 Windows 任务计划程序）:
    每天 9:00 执行: python daily_report.py
"""

import requests
import json
import os
import sys
import io
from datetime import datetime

# ─── Windows 终端 UTF-8 编码修复 (支持 emoji) ──────────

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    except (AttributeError, OSError):
        pass

# ─── 配置 ────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# 币种中文名 & emoji 映射
COIN_EMOJI = {
    "bitcoin":   "₿",
    "ethereum":  "Ξ",
    "dogecoin":  "🐕",
}

def load_config():
    """加载配置文件"""
    if not os.path.exists(CONFIG_PATH):
        print(f"[错误] 配置文件不存在: {CONFIG_PATH}")
        print("请先创建 config.json（参考 config.json 模板）")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── 1. 加密币价格抓取 (CoinGecko) ─────────────────────

def fetch_crypto_prices(coin_ids, vs_currency="usd"):
    """从 CoinGecko 抓取指定币种的实时价格和 24h 涨跌幅

    Args:
        coin_ids: 币种 ID 列表, 如 ["bitcoin", "ethereum", "dogecoin"]
        vs_currency: 计价货币, 默认 usd

    Returns:
        dict: {coin_id: {name, symbol, price, change_24h, market_cap}, ...}
    """
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": vs_currency,
        "ids": ",".join(coin_ids),
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        raise Exception("CoinGecko API 请求超时")
    except requests.exceptions.RequestException as e:
        raise Exception(f"CoinGecko API 请求失败: {e}")
    except json.JSONDecodeError:
        raise Exception(f"CoinGecko API 返回非 JSON 数据: {resp.text[:200]}")

    if not isinstance(data, list):
        raise Exception(f"CoinGecko API 返回异常数据: {str(data)[:200]}")

    result = {}
    for coin in data:
        result[coin["id"]] = {
            "name": coin["name"],
            "symbol": coin["symbol"].upper(),
            "price": coin.get("current_price"),
            "market_cap": coin.get("market_cap"),
            "change_24h": coin.get("price_change_percentage_24h"),
        }
    return result


# ─── 2. 黄金价格抓取 (多数据源自动切换) ─────────────────

def fetch_gold_price():
    """抓取黄金现货价格 (XAU/USD)，多个免费数据源自动切换

    Returns:
        dict: {price, change_24h, source}

    数据源优先级:
        1. Swissquote 公开报价 (免费, 无需 Key)
        2. Yahoo Finance v8 API (免费, 无需 Key)
    """
    sources = [
        _fetch_gold_swissquote,
        _fetch_gold_yahoo_v8,
    ]

    for i, source_fn in enumerate(sources):
        try:
            result = source_fn()
            if result and result.get("price") and result["price"] > 0:
                result["source"] = i
                return result
        except Exception as e:
            print(f"  [黄金] 数据源 {source_fn.__name__} 失败: {e}")
            continue

    raise Exception("所有黄金数据源均不可用，请检查网络连接")


def _fetch_gold_swissquote():
    """通过 Swissquote 公开报价 API 获取 XAU/USD 现货价格

    返回实时买卖报价，取 premium 档位的 bid 价作为参考价
    """
    url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # 取第一个报价条目中的 premium 档位 bid 价格
    entry = data[0]
    premium_price = None
    for profile in entry.get("spreadProfilePrices", []):
        if profile["spreadProfile"] == "premium":
            premium_price = profile["bid"]
            break

    # 如果没找到 premium，取第一个档位的 bid
    if premium_price is None and entry.get("spreadProfilePrices"):
        premium_price = entry["spreadProfilePrices"][0]["bid"]

    if premium_price is None:
        raise Exception("Swissquote 响应中未找到有效价格")

    return {
        "price": premium_price,
        "change_24h": 0,  # Swissquote 公开 API 不提供 24h 涨跌幅
    }


def _fetch_gold_yahoo_v8():
    """通过 Yahoo Finance 内部 API 获取 XAU/USD 价格 (备选)"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    chart = data["chart"]["result"][0]
    meta = chart["meta"]
    price = meta["regularMarketPrice"]
    prev_close = meta.get("previousClose", price)

    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

    return {
        "price": price,
        "change_24h": round(change_pct, 2),
    }


# ─── 3. 日报格式化 ──────────────────────────────────────

def format_report(crypto_data, gold_data):
    """将价格数据格式化为简洁文本日报

    Args:
        crypto_data: fetch_crypto_prices() 返回的字典
        gold_data: fetch_gold_price() 返回的字典

    Returns:
        str: 格式化的日报文本
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append("📊 加密币 & 黄金日报")
    lines.append(f"{date_str}")
    lines.append("─" * 28)

    # 按 BTC → ETH → DOGE 顺序输出
    coin_order = ["bitcoin", "ethereum", "dogecoin"]
    for coin_id in coin_order:
        if coin_id not in crypto_data:
            continue
        coin = crypto_data[coin_id]
        emoji = COIN_EMOJI.get(coin_id, "💰")
        name = coin["name"]
        price = coin["price"]
        change = coin["change_24h"]

        # 价格格式化
        if price is not None:
            if price >= 1000:
                price_str = f"${price:,.2f}"
            elif price >= 1:
                price_str = f"${price:,.2f}"
            else:
                price_str = f"${price:.6f}"
        else:
            price_str = "N/A"

        # 涨跌箭頭
        if change is not None:
            arrow = "📈" if change >= 0 else "📉"
            change_str = f"{arrow} {change:+.2f}%"
        else:
            change_str = ""

        lines.append(f"{emoji} {name:<8} {price_str:<14} {change_str}")

    # 黄金
    lines.append("─" * 28)
    gold_price = gold_data.get("price")
    gold_change = gold_data.get("change_24h")

    if gold_price:
        gold_price_str = f"${gold_price:,.2f}"
        if gold_change is not None and gold_change != 0:
            gold_arrow = "📈" if gold_change >= 0 else "📉"
            gold_change_str = f"{gold_arrow} {gold_change:+.2f}%"
        else:
            gold_change_str = ""
    else:
        gold_price_str = "N/A"
        gold_change_str = ""
    lines.append(f"🥇 黄金(XAU)  {gold_price_str:<14} {gold_change_str}")

    lines.append("─" * 28)
    lines.append("📲 数据: CoinGecko (加密币) & Swissquote (黄金)")
    lines.append("🔔 推送: PushPlus")

    return "\n".join(lines)


# ─── 4. PushPlus 微信推送 ───────────────────────────────

def send_pushplus(token, title, content):
    """通过 PushPlus API 推送消息到微信

    Args:
        token:  PushPlus 的 token（在 pushplus.plus 注册获取）
        title:  消息标题
        content: 消息正文（纯文本）

    Returns:
        bool: 推送是否成功
    """
    url = "http://www.pushplus.plus/send"
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "txt",  # 纯文本模板
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 200:
            print(f"[PushPlus] 推送成功 ✓")
            return True
        else:
            print(f"[PushPlus] 推送失败: {result.get('msg', '未知错误')}")
            return False
    except requests.exceptions.Timeout:
        print("[PushPlus] 推送超时")
        return False
    except Exception as e:
        print(f"[PushPlus] 推送异常: {e}")
        return False


# ─── 5. 主任务 ──────────────────────────────────────────

def job(test_mode=False):
    """执行一次日报抓取与推送

    Args:
        test_mode: True 时不实际推送到微信，仅打印到控制台
    """
    print(f"\n{'='*40}")
    print(f" 日报推送任务 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*40}")

    # 加载配置
    config = load_config()
    coins = config.get("coins", ["bitcoin", "ethereum", "dogecoin"])
    # 优先读取环境变量（GitHub Actions 用），fallback 到配置文件
    token = os.environ.get("PUSHPLUS_TOKEN") or config.get("pushplus_token", "")
    vs_currency = config.get("vs_currency", "usd")

    # Step 1: 抓取加密币价格
    print("\n[1/3] 抓取加密币价格...")
    try:
        crypto_data = fetch_crypto_prices(coins, vs_currency)
        for coin_id, info in crypto_data.items():
            arrow = "📈" if (info["change_24h"] or 0) >= 0 else "📉"
            print(f"  {COIN_EMOJI.get(coin_id, '💰')} {info['name']}: "
                  f"${info['price']:,.2f} {arrow} {info['change_24h']:+.2f}%")
    except Exception as e:
        print(f"  [错误] 加密币价格抓取失败: {e}")
        return

    # Step 2: 抓取黄金价格
    print("\n[2/3] 抓取黄金价格...")
    try:
        gold_data = fetch_gold_price()
        print(f"  🥇 黄金(XAU/USD): ${gold_data['price']:,.2f}")
    except Exception as e:
        print(f"  [错误] 黄金价格抓取失败: {e}")
        gold_data = {"price": None, "change_24h": 0}

    # Step 3: 格式化 & 推送
    print("\n[3/3] 格式化日报 & 推送到微信...")
    report = format_report(crypto_data, gold_data)
    print("\n" + report + "\n")

    if test_mode:
        print("[测试模式] 跳过微信推送（加 --test 时不会实际推送）")
    elif not token or token == "你的PushPlus_token_在这里填写":
        print("[警告] 未配置 PushPlus token！")
        print("  1. 访问 https://www.pushplus.plus/ 注册")
        print("  2. 微信扫码关注公众号获取 token")
        print("  3. 将 token 填入 config.json 的 pushplus_token 字段")
    else:
        send_pushplus(token, "📊 加密币 & 黄金日报", report)

    print(f"\n{'='*40}")
    print(" 任务结束")
    print(f"{'='*40}\n")


# ─── 入口 ───────────────────────────────────────────────

if __name__ == "__main__":
    test_mode = "--test" in sys.argv or "-t" in sys.argv
    job(test_mode=test_mode)
