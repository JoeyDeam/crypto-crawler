#!/usr/bin/env python3
"""
🐢 龟龟行情 Bot — Telegram 加密币+黄金行情助手
命令: /start  /price  /report  /help
"""

import asyncio
import io
import json
import os
import sys
from datetime import datetime

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ═══════════════════════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBERS_FILE = os.path.join(SCRIPT_DIR, "subscribers.json")

# Bot Token — 优先环境变量，fallback 到 hardcoded
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN",
    "8972351108:AAHQ-29k2grCa_b3Qbn4JZDjD1pErW22Hd0")

EMOJI = {"bitcoin": "₿", "ethereum": "Ξ", "dogecoin": "🐕"}


# ═══════════════════════════════════════════════════════════
#  数据抓取（复用日报系统逻辑）
# ═══════════════════════════════════════════════════════════

def fetch_prices():
    """抓取 BTC/ETH/DOGE/黄金 实时价格"""
    results = {}

    # 加密币 via CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "bitcoin,ethereum,dogecoin",
            "order": "market_cap_desc",
            "per_page": 5, "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        resp = requests.get(url, params=params, timeout=12)
        for coin in resp.json():
            results[coin["id"]] = {
                "name": coin["name"], "symbol": coin["symbol"].upper(),
                "price": coin.get("current_price"),
                "change_24h": coin.get("price_change_percentage_24h"),
            }
    except Exception as e:
        results["_err"] = str(e)

    # 黄金 via Swissquote
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        for p in resp.json()[0]["spreadProfilePrices"]:
            if p["spreadProfile"] == "premium":
                results["gold"] = {"price": p["bid"]}
                break
    except Exception:
        pass

    return results


# ═══════════════════════════════════════════════════════════
#  订阅者管理
# ═══════════════════════════════════════════════════════════

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_subscriber(chat_id):
    subs = set(load_subscribers())
    subs.add(chat_id)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(sorted(list(subs)), f)

def remove_subscriber(chat_id):
    subs = set(load_subscribers())
    subs.discard(chat_id)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(sorted(list(subs)), f)


# ═══════════════════════════════════════════════════════════
#  格式化
# ═══════════════════════════════════════════════════════════

def fmt_price(prices):
    """格式化价格消息"""
    now = datetime.now().strftime("%H:%M")
    lines = [f"📊 实时行情 {now}", ""]
    for coin_id in ["bitcoin", "ethereum", "dogecoin"]:
        if coin_id in prices:
            c = prices[coin_id]
            em = EMOJI.get(coin_id, "💰")
            arrow = "🟢" if (c["change_24h"] or 0) >= 0 else "🔴"
            if c["price"] >= 1000:
                ps = f"${c['price']:,.2f}"
            elif c["price"] >= 1:
                ps = f"${c['price']:,.2f}"
            else:
                ps = f"${c['price']:.6f}"
            lines.append(f"{em} {c['name']}: {ps}  {arrow} {c['change_24h']:+.2f}%")
    if "gold" in prices:
        lines.append(f"🥇 黄金 XAU: ${prices['gold']['price']:,.2f}")
    return "\n".join(lines)

def fmt_report(prices):
    """格式化日报"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["📊 加密币 & 黄金日报", now, "─" * 24]
    for coin_id in ["bitcoin", "ethereum", "dogecoin"]:
        if coin_id in prices:
            c = prices[coin_id]
            arrow = "🟢" if (c["change_24h"] or 0) >= 0 else "🔴"
            if c["price"] >= 1000:
                ps = f"${c['price']:,.2f}"
            elif c["price"] >= 1:
                ps = f"${c['price']:,.2f}"
            else:
                ps = f"${c['price']:.6f}"
            lines.append(f"{EMOJI.get(coin_id,'')} {c['name']}: {ps}  {arrow} {c['change_24h']:+.2f}%")
    if "gold" in prices:
        lines.append(f"🥇 黄金(XAU): ${prices['gold']['price']:,.2f}")
    lines.extend(["─" * 24, "🐢 龟龟守护你的财富"])
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  Bot 命令
# ═══════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    save_subscriber(chat_id)
    await update.message.reply_text(
        "🐢 龟龟行情 Bot 上线！\n\n"
        "命令：\n"
        "/price  — 实时行情\n"
        "/report — 完整日报\n"
        "/help   — 帮助\n\n"
        "每天自动推送日报到微信 📲",
    )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🐢 龟龟查询中…")
    loop = asyncio.get_event_loop()
    prices = await loop.run_in_executor(None, fetch_prices)
    await update.message.reply_text(fmt_price(prices))

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🐢 龟龟生成日报中…")
    loop = asyncio.get_event_loop()
    prices = await loop.run_in_executor(None, fetch_prices)
    await update.message.reply_text(fmt_report(prices))

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🐢 龟龟行情 Bot\n\n"
        "/price  — BTC/ETH/DOGE/黄金实时价\n"
        "/report — 完整日报\n"
        "/start  — 订阅每日推送\n\n"
        "数据源: CoinGecko + Swissquote\n"
        "完全免费 · 零广告",
    )


# ═══════════════════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════════════════

def main():
    # Fix console encoding for emoji on Windows
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("help", cmd_help))

    print("Bot online! Go to Telegram and send /start")
    app.run_polling()


if __name__ == "__main__":
    main()
