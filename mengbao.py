#!/usr/bin/env python3
"""
梦宝 (Mengbao) — 桌面龟宠 AI 助手
乌龟形态的桌面宠物，你的第二个大脑
右键互动：查看币价 / 日报 / 换姿势 / 退出
"""

import tkinter as tk
from tkinter import Menu, Toplevel, Label, Frame
import sys
import os
import json
import threading
import random
import requests
from datetime import datetime

# ═══════════════════════════════════════════════════════════
#  乌龟 ASCII 造型（多帧动画）
#  使用基础 ASCII + 安全 Unicode，兼容 Windows 所有字体
# ═══════════════════════════════════════════════════════════

FRAMES = {
    "normal": [
        # Frame 0 — 睁眼微笑
        r"""
       ___
     /  . .  \
    |    v    |
     \  ___  /
      `-...-´
       /  \
      ~    ~
""",
        # Frame 1 — 睁眼歪头
        r"""
       ___
     /  . .  \
    |    v    |
     \  ___  /
      `-...-´
       \  /
        ~~
""",
    ],
    "blink": [
        # Frame 2 — 眨眼
        r"""
       ___
     /  - -  \
    |    v    |
     \  ___  /
      `-...-´
       /  \
      ~    ~
""",
    ],
    "happy": [
        # Frame 3 — 开心
        r"""
       ___
     /  ^ ^  \
    |    w    |
     \  ~~~  /
      `-...-´
       /  \
      ~    ~
""",
    ],
    "hide": [
        # Frame 4 — 缩壳
        r"""
       ___
     /  __  \
    |  (..)  |
     \______/
      `-...-´
        ||
        ~~
""",
    ],
    "sleep": [
        # Frame 5 — 睡觉
        r"""
       ___
     /  zZ  \
    |   zZ   |
     \  ___  /
      `-...-´
        ~~
        ~~
""",
    ],
}

# ═══════════════════════════════════════════════════════════
#  透明色键（Green-screen 技术）
#  所有 #00FF00 像素变为透明，实现无背景浮空效果
# ═══════════════════════════════════════════════════════════

KEY_COLOR = "#00FF00"    # 透明色键（纯绿）

# ═══════════════════════════════════════════════════════════
#  核心：梦宝桌面宠物类
# ═══════════════════════════════════════════════════════════

class Mengbao:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("梦宝 Mengbao")

        # 窗口属性
        self.root.overrideredirect(True)       # 无边框
        self.root.attributes("-topmost", True)  # 始终置顶
        self.root.attributes("-transparentcolor", KEY_COLOR)  # 绿色变透明
        self.root.configure(bg=KEY_COLOR)

        # 初始位置：右下角
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.win_w = 200
        self.win_h = 190
        self.x = screen_w - self.win_w - 20
        self.y = screen_h - self.win_h - 50
        self.root.geometry(f"{self.win_w}x{self.win_h}+{self.x}+{self.y}")

        # 状态
        self.current_frame = "normal"
        self.frame_idx = 0
        self.drag_x = 0
        self.drag_y = 0
        self._dragging = False

        # ── 构建 UI ──
        self._build_ui()
        self._bind_events()

        # ── 启动定时器 ──
        self._schedule_blink()
        self._schedule_wander()

        # ── 问候 ──
        self.status_label.config(text="右键互动 →")
        self._show_bubble("梦宝来啦~ 🐢", 3000)

        # 启动后定期清理状态文字
        self.root.after(10000, lambda: self.status_label.config(text=""))

    # ── UI 构建 ──────────────────────────────────────

    def _build_ui(self):
        """构建透明浮空界面"""
        # 龟龟 ASCII 主体 —— 白字浮在桌面上
        self.art_label = Label(
            self.root,
            text=self._get_art(),
            font=("Consolas", 10),
            bg=KEY_COLOR, fg="#FFFFFF",
            justify=tk.LEFT,
        )
        self.art_label.pack(pady=(5, 0))

        # 迷你状态提示
        self.status_label = Label(
            self.root, text="",
            font=("Microsoft YaHei", 8),
            bg=KEY_COLOR, fg="#66FF66",
        )
        self.status_label.pack(pady=(0, 2))

    # ── 事件绑定 ────────────────────────────────────

    def _bind_events(self):
        """绑定鼠标事件"""
        # 左键拖拽
        self.art_label.bind("<ButtonPress-1>", self._drag_start)
        self.art_label.bind("<B1-Motion>", self._drag_move)
        self.art_label.bind("<ButtonRelease-1>", self._drag_end)
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<ButtonRelease-1>", self._drag_end)

        # 右键菜单（Windows 用 Button-3）
        def show_menu(e):
            self._popup_menu(e.x_root, e.y_root)
        self.art_label.bind("<Button-3>", show_menu)
        self.root.bind("<Button-3>", show_menu)

        # 双击查看币价
        self.art_label.bind("<Double-Button-1>", lambda e: self._show_price())
        self.root.bind("<Double-Button-1>", lambda e: self._show_price())

        # 滚轮切换姿势
        self.root.bind("<MouseWheel>", lambda e: self._next_frame())

        # ESC 缩壳 / 恢复
        self.root.bind("<Escape>", lambda e: self._toggle_hide())

    # ── 拖拽（含边界锁定）────────────────────────────

    def _drag_start(self, event):
        self.drag_x = event.x
        self.drag_y = event.y
        self._dragging = True

    def _drag_move(self, event):
        dx = event.x - self.drag_x
        dy = event.y - self.drag_y
        new_x = self.root.winfo_x() + dx
        new_y = self.root.winfo_y() + dy

        # 边界锁定：保证龟龟不会跑出屏幕
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        new_x = max(-self.win_w + 40, min(new_x, screen_w - 40))
        new_y = max(-20, min(new_y, screen_h - 30))

        self.x = new_x
        self.y = new_y
        self.root.geometry(f"+{self.x}+{self.y}")

    def _drag_end(self, event):
        """拖拽结束"""
        self._dragging = False

    # ── 动画控制 ────────────────────────────────────

    def _get_art(self):
        """获取当前帧的艺术字"""
        frames = FRAMES.get(self.current_frame, FRAMES["normal"])
        return frames[self.frame_idx % len(frames)]

    def _set_frame(self, name, idx=0):
        self.current_frame = name
        self.frame_idx = idx
        self.art_label.config(text=self._get_art())

    def _next_frame(self):
        """切换到下一帧"""
        names = list(FRAMES.keys())
        curr = names.index(self.current_frame)
        next_name = names[(curr + 1) % len(names)]
        self._set_frame(next_name)
        status_map = {
            "normal": "天气不错~",
            "blink": "眨眨眼~",
            "happy": "好开心！",
            "hide": "躲起来…",
            "sleep": "zzZ 打个盹",
        }
        self.status_label.config(text=status_map.get(next_name, ""))

    def _toggle_hide(self):
        """切换缩壳状态"""
        if self.current_frame == "hide":
            self._set_frame("normal")
            self.status_label.config(text="出来啦~")
        else:
            self._set_frame("hide")
            self.status_label.config(text="缩壳中…")

    def _schedule_blink(self):
        """定时眨眼"""
        def blink():
            if self.current_frame == "normal":
                self._set_frame("blink")
                self.root.after(300, lambda: self._set_frame("normal"))
        # 每 2-6 秒随机眨眼
        interval = random.randint(2000, 6000)
        self.root.after(interval, lambda: (blink(), self._schedule_blink()))

    # ── 微动：模拟活物呼吸感 ──────────────────────────

    def _schedule_wander(self):
        """每隔一段时间微微移动，像活的一样"""
        def wander():
            if self._dragging:
                return  # 拖拽中不自动移动
            dx = random.choice([-3, -1, 0, 0, 1, 3])
            dy = random.choice([-2, -1, 0, 0, 0, 1, 2])
            if dx == 0 and dy == 0:
                return
            # 目标位置
            target_x = self.root.winfo_x() + dx
            target_y = self.root.winfo_y() + dy
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            target_x = max(-self.win_w + 40, min(target_x, screen_w - 40))
            target_y = max(-20, min(target_y, screen_h - 30))

            # 平滑移动
            self._smooth_move(target_x, target_y, steps=5, delay=40)

        interval = random.randint(15000, 45000)  # 15-45 秒一次
        self.root.after(interval, lambda: (wander(), self._schedule_wander()))

    def _smooth_move(self, to_x, to_y, steps=5, delay=30):
        """平滑移动到目标位置"""
        from_x = self.root.winfo_x()
        from_y = self.root.winfo_y()
        for i in range(1, steps + 1):
            t = i / steps
            # ease-in-out
            eased = t * t * (3 - 2 * t)
            x = int(from_x + (to_x - from_x) * eased)
            y = int(from_y + (to_y - from_y) * eased)
            self.root.after(int(i * delay), lambda px=x, py=y: self.root.geometry(f"+{px}+{py}"))

    # ── 气泡消息 ────────────────────────────────────

    def _show_bubble(self, msg, duration=2500):
        """弹出气泡消息"""
        bubble = Toplevel(self.root)
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        bubble.configure(bg="#4A3728")

        label = Label(
            bubble, text=msg,
            font=("Microsoft YaHei", 10),
            bg="#4A3728", fg="#FFF8E7",
            padx=12, pady=6,
        )
        label.pack()

        # 定位在乌龟上方
        bx = self.root.winfo_x() + self.win_w // 2
        by = self.root.winfo_y() - 10
        bubble.update_idletasks()
        bubble.geometry(f"+{bx - bubble.winfo_width()//2}+{by - bubble.winfo_height()}")

        # 自动消失
        bubble.after(duration, bubble.destroy)

    # ── 右键菜单 ────────────────────────────────────

    def _popup_menu(self, x, y):
        """弹出右键菜单"""
        menu = Menu(self.root, tearoff=0, font=("Microsoft YaHei", 10))
        menu.add_command(label="💰 查看币价", command=self._show_price)
        menu.add_command(label="📊 查看日报", command=self._show_daily)
        menu.add_command(label="🐢 换个姿势", command=self._next_frame)
        menu.add_separator()
        menu.add_command(label="📌 关于梦宝", command=self._show_about)
        menu.add_command(label="❌ 退出梦宝", command=self._quit)
        menu.post(x, y)

    # ── 功能：查看币价 ──────────────────────────────

    def _fetch_prices(self):
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
            data = resp.json()
            for coin in data:
                results[coin["id"]] = {
                    "name": coin["name"],
                    "symbol": coin["symbol"].upper(),
                    "price": coin.get("current_price"),
                    "change_24h": coin.get("price_change_percentage_24h"),
                }
        except Exception as e:
            results["_crypto_error"] = str(e)

        # 黄金 via Swissquote
        try:
            url = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            for p in data[0]["spreadProfilePrices"]:
                if p["spreadProfile"] == "premium":
                    results["gold"] = {"price": p["bid"], "change_24h": 0}
                    break
        except Exception as e:
            results["_gold_error"] = str(e)

        return results

    def _show_price(self):
        """弹窗显示币价"""
        self.status_label.config(text="抓取中…")
        self.root.update()

        def _fetch_and_show():
            prices = self._fetch_prices()

            # 在主线程更新 UI
            self.root.after(0, lambda: self._display_price_popup(prices))
            self.root.after(0, lambda: self.status_label.config(text="右键我互动哟~"))

        threading.Thread(target=_fetch_and_show, daemon=True).start()

    def _display_price_popup(self, prices):
        """显示价格弹窗"""
        popup = Toplevel(self.root)
        popup.title("实时价格")
        popup.geometry("280x280")
        popup.configure(bg="#FFF8E7")
        popup.resizable(False, False)

        # 标题
        title = Label(
            popup,
            text=f"📊 实时行情  {datetime.now().strftime('%H:%M')}",
            font=("Microsoft YaHei", 11, "bold"),
            bg="#FFF8E7", fg="#4A3728",
        )
        title.pack(pady=(10, 5))

        # 内容
        frame = Frame(popup, bg="#FFF8E7")
        frame.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)

        coin_order = ["bitcoin", "ethereum", "dogecoin"]
        emoji_map = {"bitcoin": "₿", "ethereum": "Ξ", "dogecoin": "🐕"}

        for coin_id in coin_order:
            if coin_id in prices:
                c = prices[coin_id]
                arrow = "📈" if (c["change_24h"] or 0) >= 0 else "📉"
                line = f"{emoji_map.get(coin_id,'')} {c['name']}: ${c['price']:,.2f}  {arrow} {c['change_24h']:+.2f}%"
                Label(
                    frame, text=line,
                    font=("Consolas", 10),
                    bg="#FFF8E7", fg="#4A3728",
                    anchor="w",
                ).pack(fill=tk.X, pady=2)

        # 黄金
        if "gold" in prices:
            g = prices["gold"]
            line = f"🥇 黄金 XAU: ${g['price']:,.2f}"
            Label(
                frame, text=line,
                font=("Consolas", 10),
                bg="#FFF8E7", fg="#4A3728",
                anchor="w",
            ).pack(fill=tk.X, pady=2)

        # 关闭按钮
        btn = tk.Button(
            popup, text="知道了",
            command=popup.destroy,
            bg="#8B7355", fg="white",
            font=("Microsoft YaHei", 10),
            relief="flat", padx=20, pady=4,
        )
        btn.pack(pady=(0, 12))

        # 居中于屏幕
        popup.update_idletasks()
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        pw = popup.winfo_width()
        ph = popup.winfo_height()
        popup.geometry(f"+{(sw-pw)//2}+{(sh-ph)//2}")

    # ── 功能：查看日报 ───────────────────────────────

    def _show_daily(self):
        """显示完整日报"""
        self.status_label.config(text="生成日报中…")
        self.root.update()

        def _fetch_and_show():
            prices = self._fetch_prices()
            self.root.after(0, lambda: self._display_daily_popup(prices))
            self.root.after(0, lambda: self.status_label.config(text="右键我互动哟~"))

        threading.Thread(target=_fetch_and_show, daemon=True).start()

    def _display_daily_popup(self, prices):
        """显示日报弹窗"""
        popup = Toplevel(self.root)
        popup.title("每日日报")
        popup.geometry("340x360")
        popup.configure(bg="#FFF8E7")
        popup.resizable(False, False)

        now = datetime.now()
        lines = []
        lines.append("📊 加密币 & 黄金日报")
        lines.append(f"{now.strftime('%Y-%m-%d %H:%M')}")
        lines.append("─" * 30)

        coin_order = ["bitcoin", "ethereum", "dogecoin"]
        emoji_map = {"bitcoin": "₿", "ethereum": "Ξ", "dogecoin": "🐕"}

        for coin_id in coin_order:
            if coin_id in prices:
                c = prices[coin_id]
                arrow = "📈" if (c["change_24h"] or 0) >= 0 else "📉"
                if c["price"] >= 1000:
                    ps = f"${c['price']:,.2f}"
                elif c["price"] >= 1:
                    ps = f"${c['price']:,.2f}"
                else:
                    ps = f"${c['price']:.6f}"
                lines.append(f"{emoji_map.get(coin_id,'')} {c['name']:<8} {ps:<14} {arrow} {c['change_24h']:+.2f}%")

        lines.append("─" * 30)
        if "gold" in prices:
            g = prices["gold"]
            lines.append(f"🥇 黄金(XAU)  ${g['price']:,.2f}")
        lines.append("")
        lines.append("🐢 梦宝守护你的财富")
        lines.append("📲 数据: CoinGecko & Swissquote")

        content = "\n".join(lines)

        text_frame = Frame(popup, bg="#FFF8E7")
        text_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        text_widget = tk.Text(
            text_frame,
            font=("Consolas", 10),
            bg="#FFF8E7", fg="#4A3728",
            relief="flat", borderwidth=0,
            wrap=tk.WORD,
            height=16,
        )
        text_widget.insert("1.0", content)
        text_widget.config(state="disabled")
        text_widget.pack(fill=tk.BOTH, expand=True)

        btn = tk.Button(
            popup, text="好的",
            command=popup.destroy,
            bg="#8B7355", fg="white",
            font=("Microsoft YaHei", 10),
            relief="flat", padx=20, pady=4,
        )
        btn.pack(pady=(0, 12))

        popup.update_idletasks()
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        pw = popup.winfo_width()
        ph = popup.winfo_height()
        popup.geometry(f"+{(sw-pw)//2}+{(sh-ph)//2}")

    # ── 功能：关于 ──────────────────────────────────

    def _show_about(self):
        """关于弹窗"""
        about = Toplevel(self.root)
        about.title("关于梦宝")
        about.geometry("300x220")
        about.configure(bg="#FFF8E7")
        about.resizable(False, False)

        msg = """
     🐢 梦宝 Mengbao

    你的桌面龟宠 AI 助手
    第二个大脑

    功能：
    右键  → 查看币价 & 日报
    拖拽  → 移动位置
    滚轮  → 切换姿势
    ESC   → 缩壳/出来

    永远守护你的数字财富 💰
    """
        Label(
            about, text=msg,
            font=("Microsoft YaHei", 10),
            bg="#FFF8E7", fg="#4A3728",
            justify=tk.CENTER,
        ).pack(pady=15)

        btn = tk.Button(
            about, text="🐢 知道了",
            command=about.destroy,
            bg="#8B7355", fg="white",
            font=("Microsoft YaHei", 10),
            relief="flat", padx=20, pady=4,
        )
        btn.pack(pady=(0, 12))

        about.update_idletasks()
        sw = about.winfo_screenwidth()
        sh = about.winfo_screenheight()
        pw = about.winfo_width()
        ph = about.winfo_height()
        about.geometry(f"+{(sw-pw)//2}+{(sh-ph)//2}")

    # ── 退出 ────────────────────────────────────────

    def _quit(self):
        """退出梦宝"""
        self._show_bubble("梦宝走啦~ 拜拜 🐢💨", 2000)
        self.root.after(2000, self.root.destroy)

    # ── 启动 ────────────────────────────────────────

    def run(self):
        """启动梦宝"""
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════
#  开机自启动管理
# ═══════════════════════════════════════════════════════════

def setup_autostart():
    """写入 Windows 注册表实现开机自启"""
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    script_path = os.path.abspath(__file__)
    python_exe = sys.executable
    command = f'"{python_exe}" "{script_path}"'

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "Mengbao", 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"自启动设置失败: {e}")
        return False


def remove_autostart():
    """从注册表移除开机自启"""
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, "Mengbao")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"移除自启动失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 首次运行自动设置开机自启
    if "--no-autostart" not in sys.argv and "--remove" not in sys.argv:
        setup_autostart()

    if "--remove" in sys.argv:
        remove_autostart()
        print("梦宝开机自启已移除")
        sys.exit(0)

    mengbao = Mengbao()
    mengbao.run()
