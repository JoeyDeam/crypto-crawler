#!/usr/bin/env python3
"""广播日报给所有 Telegram 订阅者 — GitHub Actions 调用"""

import json
import os
import sys
import requests
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBERS_FILE = os.path.join(SCRIPT_DIR, "subscribers.json")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def fetch_prices():
    results = {}
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd", "ids": "bitcoin,ethereum,dogecoin",
            "order": "market_cap_desc", "per_page": 5, "page": 1,
            "sparkline": "false", "price_change_percentage": "24h",
        }
        resp = requests.get(url, params=params, timeout=12)
        for coin in resp.json():
            results[coin["id"]] = {
                "name": coin["name"], "symbol": coin["symbol"].upper(),
                "price": coin.get("current_price"),
                "change_24h": coin.get("price_change_percentage_24h"),
            }
    except Exception:
        pass
    try:
        url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        for p in resp.json()[0]["spreadProfilePrices"]:
            if p["spreadProfile"] == "premium":
                results["gold"] = {"price": p["bid"]}
                break
    except Exception:
        pass
    return results


def fmt_broadcast(prices):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    emoji = {"bitcoin": "₿", "ethereum": "Ξ", "dogecoin": "🐕"}
    lines = ["📊 每日行情播报", now, "─" * 20]
    for cid in ["bitcoin", "ethereum", "dogecoin"]:
        if cid in prices:
            c = prices[cid]
            a = "🟢" if (c["change_24h"] or 0) >= 0 else "🔴"
            ps = f"${c['price']:,.2f}" if c["price"] >= 1 else f"${c['price']:.6f}"
            lines.append(f"{emoji.get(cid,'')} {c['name']}: {ps}  {a} {c['change_24h']:+.2f}%")
    if "gold" in prices:
        lines.append(f"🥇 黄金: ${prices['gold']['price']:,.2f}")
    return "\n".join(lines)


def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    subs = []
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, "r") as f:
            subs = json.load(f)

    if not subs:
        print("No subscribers yet.")
        return

    prices = fetch_prices()
    msg = fmt_broadcast(prices)
    sent = 0
    for chat_id in subs:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": msg},
                timeout=10,
            )
            if resp.json().get("ok"):
                sent += 1
            else:
                print(f"Failed for {chat_id}: {resp.json().get('description')}")
        except Exception as e:
            print(f"Error for {chat_id}: {e}")

    print(f"Sent to {sent}/{len(subs)} subscribers.")


if __name__ == "__main__":
    main()
