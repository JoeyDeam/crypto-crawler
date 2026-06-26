#!/usr/bin/env python3
"""
早报 — 每日 5:00 推送
- 加密币全球 Top 10 热点新闻
- 亚马逊 Top 10 爆款产品
"""

import io
import json
import os
import sys
import time
import re
from datetime import datetime, timedelta

import feedparser
import requests
from bs4 import BeautifulSoup

# ═══════════════════════════════════════════
#  Windows 编码修复
# ═══════════════════════════════════════════

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════
#  1. 加密币全球热点新闻 (RSS 多源聚合)
# ═══════════════════════════════════════════

NEWS_SOURCES = [
    ("Google全球",  "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("BBC中文",     "https://www.bbc.com/zhongwen/simp/index.xml"),
    ("Google综合",  "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
]

def fetch_news(limit=10):
    """聚合中文全球热点新闻 RSS，返回 Top N"""
    all_news = []
    seen = set()

    for source_name, url in NEWS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                # 去重
                key = title[:40]
                if key in seen:
                    continue
                seen.add(key)
                # 清理 Google News 标题中的来源后缀
                title = title.split(" - ")[0].strip()
                # 发布时间
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = time.strftime("%m-%d %H:%M", entry.published_parsed)
                    except Exception:
                        pass
                all_news.append({
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                })
                if len(all_news) >= limit * 3:
                    break
        except Exception as e:
            print(f"  [{source_name}] 失败: {e}")
            continue

    return all_news[:limit]


# ═══════════════════════════════════════════
#  2. 亚马逊 Top 10 爆款产品
# ═══════════════════════════════════════════

AMAZON_URL = "https://www.amazon.com/Best-Sellers/zgbs/"
AMAZON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch_amazon_bestsellers(limit=10):
    """抓取 Amazon Best Sellers 页面 Top N 产品"""
    products = []
    try:
        resp = requests.get(AMAZON_URL, headers=AMAZON_HEADERS, timeout=15, proxies={"http": None, "https": None})
        if resp.status_code != 200:
            print(f"  Amazon 返回 {resp.status_code}")
            return products

        soup = BeautifulSoup(resp.text, "lxml")

        for card in soup.select(".p13n-sc-uncoverable-faceout"):
            if len(products) >= limit:
                break

            # 标题
            title_el = card.select_one(".p13n-sc-truncate-desktop-type2, .p13n-sc-truncated")
            title = title_el.text.strip() if title_el else "N/A"

            # 跳过非实体产品
            skip_words = ["plan with", "subscription", "gift card", "reload", "auto-renewal"]
            if any(w in title.lower() for w in skip_words):
                continue

            # 价格
            price_el = card.select_one("span.a-price span.a-offscreen")
            price = price_el.text.strip() if price_el else "N/A"

            # 评分
            stars_el = card.select_one(".a-icon-alt")
            stars = stars_el.text.strip()[:25] if stars_el else ""

            # 链接
            link_el = card.select_one("a.a-link-normal")
            link = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                link = "https://www.amazon.com" + href if href.startswith("/") else href
                # 去掉 ref 参数
                link = re.sub(r"/ref=.*", "", link)

            products.append({
                "title": title,
                "price": price,
                "stars": stars,
                "link": link,
            })

    except Exception as e:
        print(f"  Amazon 抓取失败: {e}")

    return products[:limit]


# ═══════════════════════════════════════════
#  3. 格式化早报
# ═══════════════════════════════════════════

def format_report(news, products):
    """格式化早报文本"""
    now = datetime.now()
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    date_str = now.strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append("🌅 每日早报")
    lines.append(f"{date_str}")
    lines.append("=" * 35)
    lines.append("")

    # ── 新闻 ──
    lines.append("📰 全球热点新闻 Top 10")
    lines.append("-" * 35)
    for i, n in enumerate(news, 1):
        title = n["title"][:80]
        pub = f" {n['published']}" if n.get("published") else ""
        lines.append(f"{i:2d}. {title}")
        lines.append(f"    {n['link']}")
        lines.append("")
    lines.append("")

    # ── 亚马逊 ──
    lines.append("🛒 亚马逊 Best Sellers Top 10")
    lines.append("-" * 35)
    for i, p in enumerate(products, 1):
        title = p["title"][:70]
        price = p.get("price", "N/A")
        stars = p.get("stars", "")
        lines.append(f"{i:2d}. {title}")
        lines.append(f"    💰 {price}  {stars}")
        if p.get("link"):
            lines.append(f"    📎 {p['link']}")
        lines.append("")

    lines.append("=" * 35)
    lines.append("📲 新闻源: Google News & BBC 中文")
    lines.append("📲 商品源: Amazon Best Sellers")
    lines.append("🐢 梦宝早报 · 每日 5:00")

    return "\n".join(lines)


# ═══════════════════════════════════════════
#  4. PushPlus 推送
# ═══════════════════════════════════════════

def send_pushplus(token, title, content):
    """推送到微信"""
    try:
        resp = requests.post(
            "http://www.pushplus.plus/send",
            json={"token": token, "title": title, "content": content, "template": "txt"},
            timeout=15,
            proxies={"http": None, "https": None},  # 跳过系统代理
        )
        result = resp.json()
        if result.get("code") == 200:
            print("[PushPlus] OK")
            return True
        else:
            print(f"[PushPlus] Fail: {result.get('msg')}")
            return False
    except Exception as e:
        print(f"[PushPlus] Error: {e}")
        return False


# ═══════════════════════════════════════════
#  5. 主任务
# ═══════════════════════════════════════════

def run():
    print("=" * 40)
    print(f" 早报任务 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 40)

    config = load_config()
    token = os.environ.get("PUSHPLUS_TOKEN") or config.get("pushplus_token", "")

    # Step 1: 新闻
    print("\n[1/2] 抓取全球加密热点新闻...")
    news = fetch_news(10)
    print(f"  -> 获取 {len(news)} 条")

    # Step 2: 亚马逊
    print("\n[2/2] 抓取 Amazon Best Sellers...")
    products = fetch_amazon_bestsellers(10)
    print(f"  -> 获取 {len(products)} 件产品")

    # 格式化
    report = format_report(news, products)
    print("\n" + report[:500] + "...\n")

    # 推送
    if not token or "你的PushPlus" in token:
        print("[警告] PushPlus token 未配置")
    else:
        send_pushplus(token, "早报 | 加密新闻+亚马逊爆款", report)

    print("\nDone.")


if __name__ == "__main__":
    run()
