# 小克桌宠：透明、置顶、能拖动的像素小克。
# 画法照 工作台/workbench.html 里的 clawdSVG 搬过来（改那边的画法，这里也要跟着改）。
# 左键点一下 = 打开 Claude 桌面应用（右键「点一下打开」可改回工作台网页）；左键拖 = 挪位置；右键 = 菜单。
# 双击 = 叫出「克讲机」（小克外挂箱 / 克讲机Clawkie 做的能拖的小聊天窗）；长按 = 按住说话。
# 状态从同目录 status.json 读（每秒看一次有没有改），菜单里改状态 / 造型也写回这个文件。
# 窗口位置、大小这些只跟这台电脑有关的，存在 settings.json，别的程序不用管。

import ctypes
import json
import os
import random
import subprocess
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(HERE, "status.json")
SETTINGS = os.path.join(HERE, "settings.json")
WORKBENCH = "https://claude.ai/artifact/4XLcT3GusN2sP3PVuBGY3X"
STARTUP_BAT = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\小克桌宠.bat")

KEY = "#ff00fe"  # 这个颜色会变成透明，画小克时别用它
INK, PAPER, YELLOW = "#151513", "#ffffff", "#ffe14a"
TONES = ("#6d6164", "#652062", "#7920e5", "#96b5e5", "#96b500")  # 描边备用色，和工作台里的一样
FONT = ("Microsoft YaHei UI", 10)

STATES = ["urgent", "busy", "relaxed", "cheer", "sleep"]
STATE_ZH = {"urgent": "着急", "busy": "忙碌", "relaxed": "悠闲", "cheer": "欢呼", "sleep": "睡觉"}
LINES = {"urgent": "急急急！", "busy": "在忙在忙～", "relaxed": "猫猫赛高", "cheer": "做完啦！", "sleep": "zzZ…"}
PRESETS = {
    "原版小克": {"ears": "none", "tail": "none", "color": "#d97757", "hold": "none"},
    "狐狸小克": {"ears": "fox", "tail": "fox", "color": "#d97757", "hold": "cat"},
    "紫色猫猫": {"ears": "cat", "tail": "cat", "color": "#9b7bff", "hold": "cat", "face": "blush"},
    "水青兔兔": {"ears": "bunny", "tail": "bunny", "color": "#3fc7c7", "hold": "tea"},
    "粉粉小熊": {"ears": "bear", "tail": "none", "color": "#ff8fc2", "hold": "fish", "body": "bowtie"},
    "终末地工程师": {"ears": "fox", "tail": "fox", "color": "#d97757", "hold": "none", "hat": "hard", "body": "overalls", "scarf": "#ffe14a"},
    "小魔女": {"ears": "cat", "tail": "cat", "color": "#5a4a7a", "hold": "cat", "hat": "witch", "body": "cape"},
}
SIZES = {"小": 3, "中": 4, "大": 6}
DEFAULT_STATUS = {"state": "busy", "say": "", "look": PRESETS["狐狸小克"], "url": WORKBENCH, "parts": [], "presets": []}
CLICK = {"workbench": "今日小克终未地（网页）", "claude": "Claude 应用"}
# 克讲机的程序（属于「克讲机Clawkie」项目；那个文件夹改名时这里要跟着改）
TALKIE = next((p for p in (r"D:\不克思议Clawsmos\小克外挂箱Clawckbox\克讲机Clawkie\talkie\clawkie_talkie.py",
                           r"D:\不克思议Clawsmos\小克外挂箱Clawckbox\小克助手\talkie\clawkie_talkie.py") if os.path.exists(p)),
              r"D:\不克思议Clawsmos\小克外挂箱Clawckbox\克讲机Clawkie\talkie\clawkie_talkie.py")
BRIDGE = os.path.join(os.path.expanduser("~"), ".claude", "clawkie-bridge")
NOTICE = os.path.join(BRIDGE, "notice.json")      # 克讲机给小克的提醒（新回答、生图请求……）
POSE = os.path.join(BRIDGE, "pet-pose.json")      # 克讲机现在在干嘛 → 小克手里的对讲机摆什么动作
FOCUS = os.path.join(BRIDGE, "focus.json")        # 你刚在哪个对话发了消息（插件写）→ 小克看它还欠着哪些备忘
TALKIE_STATE = os.path.join(BRIDGE, "talkie.json")
# Claude 应用给每个对话存一个记录，里面 lastFocusedAt = 你最后点进它的时间 → 点进哪个对话就提醒哪个（不用等发消息、不用插件）
APP_SESSIONS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Claude_pzs8sxrjxfjjc", "LocalCache", "Roaming", "Claude", "claude-code-sessions"),
    os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code-sessions"),
]

# 小克手里的迷你对讲机：四个动作的位置（格子坐标同 clawd()：身子 x 4～18、y 2～14，右手在 x 18～21）
POSES = {
    "idle":   {"at": (18.5, 8.5)},                 # 别在右边腰上
    "listen": {"at": (18.5, -2.5), "waves": (23.5, -1)},  # 举到耳边听，天线红灯闪
    "talk":   {"at": (15.5, 6.5), "waves": (21, 7.5)},  # 凑到嘴边说，往外冒声波
    "paint":  {"at": (8.5, 9), "paint": True},     # 捧在胸前看屏幕，屏上冒小色块
}
ROTATE = {0: "不换", 30: "每 30 分钟", 60: "每 1 小时", 180: "每 3 小时", 1440: "每天"}  # 随机换小克：工作台 ⚙ 里选「桌宠随机换」再粘贴


# ---------- 读写文件 ----------

def read_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------- 画小克（照 clawdSVG） ----------

def norm_look(l):
    l = l or {}
    n = {"ears": "fox", "tail": "fox", "color": "#d97757", "hold": "cat", "hat": "none", "face": "none", "body": "none", "scarf": "none"}
    n.update(l)
    if l.get("fox") is False and "ears" not in l: n["ears"] = "none"
    if l.get("fox") is False and "tail" not in l: n["tail"] = "none"
    if l.get("cat") is False and "hold" not in l: n["hold"] = "none"
    return n


def shade(hex_, k):
    n = int(hex_[1:7], 16)
    c = [n >> 16, n >> 8 & 255, n & 255]
    c = [round(v + (255 - v) * k if k > 0 else v * (1 + k)) for v in c]
    return "#" + "".join(f"{max(0, min(255, v)):02x}" for v in c)


def clawd(look, st, parts):
    """返回要画的格子：("r", x, y, w, h, 颜色) 实心；("o", x, y, w, h, 颜色) 只描边。坐标同 SVG viewBox -8 -12 40 34。"""
    L = norm_look(look)
    B = L["color"]
    HI, DK, CR, TIP, CAT, PK = shade(B, .28), INK, "#fff3e0", shade(B, -.45), "#2a2438", "#ffb6d5"
    g = []
    P = lambda x, y, w, h, c: g.append(("r", x, y, w, h, c))
    dy = 3 if st == "relaxed" else 4 if st == "sleep" else 0

    def custom(pid, oy):
        p = next((q for q in parts if "u:" + str(q.get("id")) == pid), None)
        if not p: return
        for item in str(p.get("px", "")).split(";"):
            try:
                x, y, c = item.split(",")
                P(float(x), float(y) + oy, 1, 1, "#" + c)
            except ValueError:
                pass

    if L["tail"] == "fox":
        P(-4, 7+dy, 4, 6, B); P(-6, 5+dy, 4, 4, B); P(-7, 3+dy, 3, 3, CR); P(-6, 2+dy, 2, 1, CR); P(-1, 11+dy, 2, 3, B)
    if L["tail"] == "cat":
        P(-1, 11+dy, 2, 2, B); P(-3, 9+dy, 2, 2, B); P(-4, 6+dy, 2, 3, B); P(-3, 5+dy, 2, 1, B)
    if L["tail"] == "bunny":
        P(-2, 11+dy, 3, 3, "#fff"); P(-1, 10+dy, 1, 1, "#fff")
    if L["body"] == "cape":
        P(2, 3+dy, 18, 12, "#e2412b"); P(1, 13+dy, 20, 2, "#c23421")
    if st == "relaxed": P(3, 16, 5, 2, B); P(14, 16, 5, 2, B)
    elif st == "sleep": P(5, 16, 12, 2, B)
    else:
        for x in (5, 8, 12, 15): P(x, 14, 2, 5, B)
    P(4, 2+dy, 14, 10 if st == "sleep" else 12, B); P(4, 2+dy, 14, 2, HI)
    ear = {"fox": [(5, -3, 1, 1, TIP), (4, -2, 3, 1, B), (4, -1, 4, 1, B), (4, 0, 5, 2, B), (5, -1, 1, 1, CR), (5, 0, 2, 1, CR)],
           "cat": [(5, -2, 1, 1, B), (4, -1, 3, 1, B), (4, 0, 4, 2, B), (5, 0, 2, 1, PK)],
           "bunny": [(5, -7, 3, 9, B), (6, -6, 1, 6, PK)], "bear": [(3, -1, 4, 3, B), (4, 0, 2, 1, TIP)]}.get(L["ears"], [])
    for x, y, w, h, c in ear:
        P(x, y+dy, w, h, c); P(22-x-w, y+dy, w, h, c)
    ey = 5 + dy
    if st == "sleep": P(6, ey+3, 3, 1, DK); P(13, ey+3, 3, 1, DK)
    elif st in ("relaxed", "cheer"):
        for bx in (6, 13): P(bx, ey+2, 1, 1, DK); P(bx+1, ey+1, 1, 1, DK); P(bx+2, ey+2, 1, 1, DK)
    elif st == "urgent": P(7, ey-1, 2, 5, DK); P(13, ey-1, 2, 5, DK)
    else: P(7, ey, 2, 4, DK); P(13, ey, 2, 4, DK)

    f = L["face"]
    if f == "glasses":
        g.append(("o", 6, ey-.5, 4, 5, DK)); g.append(("o", 12, ey-.5, 4, 5, DK)); P(10, ey+1, 2, .7, DK)
    if f == "shades":
        P(6, ey, 4, 3, DK); P(12, ey, 4, 3, DK); P(10, ey+1, 2, 1, DK); P(7, ey, 1, 1, "#6d6d68"); P(13, ey, 1, 1, "#6d6d68")
    if f == "blush": P(4, ey+4, 2, 1, "#ff8fc2"); P(16, ey+4, 2, 1, "#ff8fc2")
    if f == "band": P(14, ey-3, 4, 1, "#f2c49b"); P(15, ey-3, 1, 1, "#d9a37a")
    if f.startswith("u:"): custom(f, dy)
    bd = L["body"]
    if bd == "overalls":
        P(4, 10+dy, 14, 4, "#4f7fd9"); P(6, 6+dy, 2, 4, "#4f7fd9"); P(14, 6+dy, 2, 4, "#4f7fd9"); P(6, 10+dy, 1, 1, "#ffe14a"); P(15, 10+dy, 1, 1, "#ffe14a")
    if bd == "apron": P(6, 8+dy, 10, 6, "#fff"); P(6, 8+dy, 10, 1, PK); P(10, 11+dy, 2, 2, PK)
    if bd == "cape": P(5, 8+dy, 12, 1, "#ffe14a")
    if bd == "bowtie": P(7, 9+dy, 3, 2, "#e2412b"); P(12, 9+dy, 3, 2, "#e2412b"); P(10, 9+dy, 2, 2, "#a82a1b")
    if bd.startswith("u:"): custom(bd, dy)
    if L["scarf"] and L["scarf"] != "none": P(4, 9+dy, 14, 2, L["scarf"]); P(15, 11+dy, 3, 3, L["scarf"])

    hold = L["hold"]

    def item_at(x, y, mood):
        if hold == "cat":
            P(x, y, 6, 4, CAT); P(x, y-1, 1, 1, CAT); P(x+5, y-1, 1, 1, CAT); P(x, y+4, 6, 2, CAT); P(x+6, y+4, 2, 1, CAT)
            if mood == "sleep": P(x+1, y+2, 1, 1, "#ff8fc2"); P(x+4, y+2, 1, 1, "#ff8fc2")
            else: P(x+1, y+1, 1, 1, "#ff8fc2"); P(x+4, y+1, 1, 1, "#ff8fc2"); P(x+2, y+2, 2, 1, "#4a3f5c")
            if mood == "urgent": P(x-1, y-1, 1, 2, CAT); P(x+6, y-1, 1, 2, CAT); P(x+2, y-2, 2, 1, CAT)
        elif hold == "fish":
            P(x-1, y+1, 7, 3, "#9fb3c8"); P(x+6, y, 2, 5, "#9fb3c8"); P(x, y+2, 1, 1, DK); P(x+2, y+1, 3, 1, "#c3d2e0")
        elif hold == "tea":
            P(x+1, y, 4, 6, "#f4e3c3"); P(x+1, y, 4, 1, "#fff"); P(x+3, y-3, 1, 4, "#ff8fc2"); P(x+1, y+4, 4, 1, "#5b3a29"); P(x+2, y+5, 1, 1, "#5b3a29")
        elif hold.startswith("u:"):
            custom(hold, y - 10)

    holding = hold != "none"
    if st == "cheer":
        P(1, -2, 3, 5, B); P(18, -2, 3, 5, B); item_at(8, -8, "cheer"); P(3, -6, 4, 3, B); P(15, -6, 4, 3, B)
        P(-3, -9, 1, 3, "#f5c400"); P(-4, -8, 3, 1, "#f5c400"); P(25, -6, 1, 3, "#f5c400"); P(24, -5, 3, 1, "#f5c400")
    elif st == "urgent":
        item_at(8, 10, "urgent")
        if holding: P(4, 11, 3, 3, B)
        else: P(1, 7, 3, 4, B)
        P(18, 3, 3, 5, B); P(21, -2, 1, 8, DK); P(17, -11, 9, 8, "#e2412b"); P(21, -10, 1, 4, "#fff"); P(21, -5, 1, 1, "#fff"); P(19, 1, 3, 3, B)
        P(1, 0, 1, 2, "#7fd8e8"); P(0, 2, 1, 1, "#7fd8e8")
    else:
        item_at(8, 10 + dy - (1 if st == "sleep" else 0), st)
        if holding: P(4, 11+dy, 3, 3, B); P(15, 11+dy, 3, 3, B)
        else: P(1, 7+dy, 3, 4, B); P(18, 7+dy, 3, 4, B)

    h = L["hat"]
    Y = lambda n: n + dy
    if h == "hard": P(6, Y(-1), 10, 3, "#ffe14a"); P(5, Y(1), 12, 1, DK); P(10, Y(-2), 2, 1, "#ffe14a")
    if h == "beret": P(7, Y(-1), 8, 2, "#ff8fc2"); P(6, Y(0), 10, 2, "#ff8fc2"); P(10, Y(-2), 2, 1, "#7b5cff")
    if h == "crown": P(7, Y(-1), 8, 2, "#f5c400"); P(7, Y(-3), 2, 2, "#f5c400"); P(10, Y(-4), 2, 3, "#f5c400"); P(13, Y(-3), 2, 2, "#f5c400"); P(10, Y(0), 2, 1, "#e2412b")
    if h == "chef": P(7, Y(-5), 8, 4, "#fff"); P(6, Y(-6), 4, 2, "#fff"); P(12, Y(-6), 4, 2, "#fff"); P(6, Y(-1), 10, 2, "#fff"); P(6, Y(0), 10, 1, "#d8d8d0")
    if h == "witch": P(10, Y(-8), 2, 2, "#6b4bd6"); P(9, Y(-6), 4, 2, "#6b4bd6"); P(8, Y(-4), 6, 2, "#6b4bd6"); P(7, Y(-2), 8, 2, "#6b4bd6"); P(4, Y(0), 14, 1, "#4a32a8"); P(10, Y(-4), 2, 1, "#ffe14a")
    if h == "straw": P(6, Y(-2), 10, 3, "#f2d58a"); P(6, Y(0), 10, 1, "#e2412b"); P(2, Y(1), 18, 1, "#e3c06b")
    if h == "santa": P(7, Y(-2), 8, 3, "#e2412b"); P(12, Y(-4), 3, 2, "#e2412b"); P(15, Y(-5), 2, 2, "#fff"); P(6, Y(0), 10, 2, "#fff")
    if h == "bow": P(7, Y(-1), 3, 3, "#ff6fae"); P(12, Y(-1), 3, 3, "#ff6fae"); P(10, Y(0), 2, 1, "#d94a8c")
    if h == "phones": P(4, Y(-1), 14, 1, DK); P(4, Y(-1), 1, 4, DK); P(17, Y(-1), 1, 4, DK); P(2, Y(3), 3, 4, "#3fc7c7"); P(17, Y(3), 3, 4, "#3fc7c7")
    if h == "flower": P(14, Y(-1), 3, 3, "#ff8fc2"); P(13, Y(0), 1, 1, "#ff8fc2"); P(17, Y(0), 1, 1, "#ff8fc2"); P(15, Y(0), 1, 1, "#ffe14a")
    if h.startswith("u:"): custom(h, dy)
    if st == "relaxed" and hold != "tea":
        P(20, 15, 4, 3, "#fff"); P(24, 16, 1, 1, "#fff"); P(21, 12, 1, 2, "#bdbeb8"); P(23, 11, 1, 2, "#bdbeb8")
    if st == "sleep":  # 网页里是文字 Z，这里用像素画，透明窗口里文字边缘会发花
        V = "#7b5cff"
        P(20, -3, 5, 1, V); P(23, -2, 1, 1, V); P(22, -1, 1, 1, V); P(21, 0, 1, 1, V); P(20, 1, 5, 1, V)
        P(26, -8, 3, 1, V); P(27, -7, 1, 1, V); P(26, -6, 3, 1, V)
    return g


# ---------- 窗口 ----------

class Pet:
    def __init__(self):
        self.status = {**DEFAULT_STATUS, **read_json(STATUS, {})}
        if not os.path.exists(STATUS):
            write_json(STATUS, self.status)
        self.mtime = self._mtime()
        self.settings = {"size": "中", "x": None, "y": None, "topmost": True, "bubble": True, "click": "claude", "rotate": 0, "rotAt": 0, **read_json(SETTINGS, {})}
        self.bob = 0
        self.drag = None
        self.click_job = None   # 单击要等一下，看是不是双击
        self.double = False
        self.long_job = None    # 长按 = 按住说话（克讲机）
        self.long = False
        self.notice_id = (read_json(NOTICE, {}) or {}).get("id")
        self.pose_info = read_json(POSE, {}) or {}
        self.todo = None        # 脚下那条：现在点着的对话还欠着的备忘 {"key", "items"}
        self.strip_note = ("", 0)  # 脚下那条临时放克讲机的通知（新回答、生图请求……）：(话, 到几点)
        self.say_tmp = ("", 0)     # 上面气泡临时说一句（换好啦、在听～），几秒后变回工作台定的话
        self.memo_cache = (0, [])  # talkie.json 的改动时间, 备忘
        self.app_seen = {}      # 应用的对话记录文件 → (改动时间, 对话编号, 最后点进的时间)
        self.app_top = None     # 现在点着的是哪个对话
        self.app_scan_at = 0
        self.remind_until = 0

        self.root = tk.Tk()
        self.root.title("小克桌宠")
        self.root.overrideredirect(True)
        self.root.config(bg=KEY)
        self.root.wm_attributes("-transparentcolor", KEY)
        self.root.wm_attributes("-topmost", self.settings["topmost"])
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double)
        self.canvas.bind("<Button-3>", self.on_menu)

        self.layout()
        x, y = self.settings["x"], self.settings["y"]
        if x is None or y is None:
            x = self.root.winfo_screenwidth() - self.w - 40
            y = self.root.winfo_screenheight() - self.h - 80
        elif not self.settings.get("strip"):  # 2026-10-15 脚下多了一条：窗口往下长了，往上挪一次，免得那条被任务栏挡住
            y -= self.th
            self.settings["strip"] = 1
            write_json(SETTINGS, {**self.settings, "y": y})
            self.settings["y"] = y
        self.root.geometry(f"+{int(x)}+{int(y)}")
        self.draw()
        self.root.after(1000, self.poll)
        self.root.after(600, self.tick)
        self.root.after(60000, self.rotate_tick)

    # 尺寸
    def layout(self):
        self.s = SIZES.get(self.settings["size"], 4)
        self.font = tkfont.Font(family=FONT[0], size=FONT[1])
        self.bh = self.font.metrics("linespace") * 2 + 26  # 气泡区固定放两行，说的话变长也不会把小克挤动
        self.w = max(40 * self.s, 240)
        self.feet = self.bh + 34 * self.s + 6
        self.th = self.font.metrics("linespace") + 16      # 脚下那条：克讲机的待办 / 通知（没有就是空的、透明）
        self.h = self.feet + self.th
        self.canvas.config(width=self.w, height=self.h)
        self.root.geometry(f"{self.w}x{self.h}")

    # 状态会过期（2026-10-12：之前停在「去登录小红书」一整天没变）：
    # 欢呼只开心 15 分钟；着急 / 忙碌超过 STALE_H 小时没人更新，就当没事了变悠闲；半夜不着急就睡觉
    STALE_H = 3

    def stale(self):
        age = time.time() - (self.mtime or 0)
        st = self.status.get("state", "busy")
        return (st == "cheer" and age > 15 * 60) or (st in ("urgent", "busy") and age > self.STALE_H * 3600)

    def state(self):
        st = self.status.get("state", "busy")
        st = st if st in STATES else "busy"
        if self.stale():
            st = "relaxed"
        if st != "urgent" and 1 <= time.localtime().tm_hour < 7:
            st = "sleep"
        return st

    def draw(self):
        c, s = self.canvas, self.s
        c.delete("all")
        st = self.state()
        ox = (self.w - 40 * s) / 2 + 8 * s  # viewBox 从 -8 开始
        oy = self.bh + 12 * s + 6 - self.bob * s
        for kind, x, y, w, h, col in clawd(self.status.get("look"), st, self.status.get("parts") or []):
            x0, y0 = ox + x * s, oy + y * s
            if kind == "r":
                c.create_rectangle(x0, y0, x0 + w * s, y0 + h * s, fill=col, width=0)
            else:
                c.create_rectangle(x0, y0, x0 + w * s, y0 + h * s, outline=col, width=max(1, round(.7 * s)))
        if self.settings.get("walkie", True):  # 手里的迷你克讲机（只画在桌宠上，工作台的小克不变）
            box = [1e9, 1e9, -1e9, -1e9]
            for x, y, w, h, col in self.walkie_cells():
                x0, y0 = ox + x * s, oy + y * s
                c.create_rectangle(x0, y0, x0 + w * s, y0 + h * s, fill=col, width=0)
                box = [min(box[0], x0), min(box[1], y0), max(box[2], x0 + w * s), max(box[3], y0 + h * s)]
            self.walkie_box = (box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3)  # 宽一点好点中
        else:
            self.walkie_box = None
        if self.settings["bubble"]:
            # 上面气泡 = 小克自己说的，跟工作台（今日小克终未地）定的一样；临时一句（换好啦）几秒后变回来
            say = self.status.get("say") if st == self.status.get("state") and not self.stale() else ""
            if time.time() < self.say_tmp[1]:
                say = self.say_tmp[0]
            self.draw_bubble(say or LINES[st], st)
        self.draw_strip()

    def draw_strip(self):
        """脚下那条（用户 2026-10-15：小克说的话分两个——上面是它自己说的，下面写待办）：
        现在点着的对话还欠着的备忘；克讲机有通知时临时先放通知。点一下 = 打开克讲机"""
        c = self.canvas
        self.strip_top = 1e9
        note = self.strip_note[0] if time.time() < self.strip_note[1] else ""
        if note:
            text, tail, led, bg = note, " ▸", YELLOW, PAPER
        elif self.todo:
            items = self.todo["items"]
            text, tail, led, bg = items[0], (f"  共{len(items)}件 ▸" if len(items) > 1 else " ▸"), "#e2412b", YELLOW
        else:
            return
        top = self.feet + 2
        text = " ".join(str(text).split())
        t = c.create_text(0, 0, text=text + tail, font=self.font, fill=INK, anchor="nw")
        cut = text
        while cut and c.bbox(t)[2] - c.bbox(t)[0] > self.w - 44:  # 一行放不下就截前面的话，件数留着
            cut = cut[:-1]
            c.itemconfig(t, text=cut + "…" + tail)
        x0, y0, x1, y1 = c.bbox(t)
        bw, bh = x1 - x0 + 30, self.th - 4
        left = (self.w - bw) / 2
        k = 5  # 切角，跟上面气泡一样
        c.create_polygon([left + k, top, left + bw, top, left + bw, top + bh - k, left + bw - k, top + bh, left, top + bh, left, top + k],
                         fill=bg, outline=INK, width=2)
        c.create_rectangle(left + 8, top + bh / 2 - 3, left + 14, top + bh / 2 + 3, fill=led, outline=INK, width=1)  # 小灯：红 = 待办
        c.coords(t, left + 20, top + (bh - (y1 - y0)) / 2)
        c.tag_raise(t)
        self.strip_top = top

    def pose(self):
        """克讲机在干嘛：听回答 / 你在说话 / 在画图；提醒备忘时举到耳边"""
        if time.time() < self.remind_until:
            return "listen"
        p = self.pose_info.get("pose") or "idle"
        if p != "idle" and time.time() > (self.pose_info.get("until") or 0):
            return "idle"
        return p if p in POSES else "idle"

    def walkie_cells(self):
        """迷你对讲机的格子：描边、机身、屏、喇叭、侧键、天线。
        颜色默认跟着小克自己的颜色配（用户 2026-10-15：“颜色跟这个小人不太符合……根据不同的小克变成适配的颜色”）：
        机身 = 小克的颜色压深，屏 = 奶油色，按键 = 小克的颜色提亮；菜单里也能换回「跟克讲机机身」"""
        if self.settings.get("walkieColor", "pet") == "pet":
            B = norm_look(self.status.get("look"))["color"]
            body, screen, accent = shade(B, -0.42), "#fff3e0", shade(B, 0.35)
        else:
            cols = self.pose_info.get("colors") or {}
            body, screen, accent = cols.get("body") or "#2f4fd8", cols.get("screen") or "#f2d04a", cols.get("accent") or "#e2412b"
        pose = self.pose()
        P = POSES[pose]
        x, y = P["at"]
        blink = self.bob == 1
        hand = shade(norm_look(self.status.get("look"))["color"], -0.18)
        g = [(x + 2.6, y - 3, 0.9, 3.2, INK),                                   # 天线
             (x + 2.4, y - 3.6, 1.3, 1.1, accent if (pose == "listen" and blink) else INK),
             (x - 0.5, y - 0.5, 5, 8, INK), (x, y, 4, 7, body),                # 描边 + 机身
             (x + 0.6, y + 0.7, 2.8, 2, screen),                               # 屏
             (x + 0.8, y + 3.4, 2.4, 0.45, INK), (x + 0.8, y + 4.3, 2.4, 0.45, INK),  # 喇叭孔
             (x + 1.5, y + 5.4, 1, 0.8, accent),                               # 按键
             (x - 1, y + 2.2, 0.6, 1.8, accent)]                               # 侧面通话键
        # 手：抬起来的胳膊 / 捏着对讲机的小爪子（比身子深一点，看得出来）
        if pose == "listen":
            g += [(18, 2, 2, 5, norm_look(self.status.get("look"))["color"]), (x - 0.6, y + 3, 1.6, 2, hand)]
        elif pose == "talk":
            g += [(x - 0.6, y + 3.5, 1.4, 2, hand)]
        elif pose == "paint":
            g += [(x - 0.8, y + 4, 1.4, 1.8, hand), (x + 3.4, y + 4, 1.4, 1.8, hand)]
        if P.get("paint"):  # 屏上冒小色块，一闪一闪
            for i, col in enumerate(("#e2412b", "#f5c400", "#2f4fd8")):
                if blink or i != 1:
                    g.append((x + 0.9 + i * 0.8, y + 1.1 + (i % 2) * 0.6, 0.7, 0.7, col))
        wv = P.get("waves")
        if wv:  # 声波：一闪一闪的两道
            wx, wy = wv
            k = 1 if blink else 0
            if pose == "listen":
                g += [(wx, wy + 1, 0.6, 2, accent), (wx + 1.2 + k * 0.3, wy, 0.6, 4, accent)]
            else:  # 说话：三道横的，一伸一缩
                g += [(wx, wy, 1.5 + k, 0.6, accent), (wx, wy + 1.5, 2.5 + k, 0.6, accent), (wx, wy + 3, 1.5 + k, 0.6, accent)]
        return g

    def check_talkie(self):
        """读克讲机的动作；你刚在哪个对话发了消息，就看那个对话还欠着哪些备忘"""
        info = read_json(POSE, None)
        if isinstance(info, dict):
            self.pose_info = info
        # 你点着哪个对话（读应用的记录，每秒一次，只重读改过的文件，一次几毫秒）
        top = self.app_focus()
        if top:
            ids = top[0]
        else:  # 读不到应用记录：退回看插件写的“你刚在哪个对话发了消息”
            f = read_json(FOCUS, None)
            ids = (f["sid"],) if isinstance(f, dict) and f.get("sid") else ()
        switched = bool(ids) and self.app_top is not None and ids[0] != self.app_top  # 桌宠刚开时不算“点进”
        if ids:
            self.app_top = ids[0]
        self.remind_for(ids, switched)

    def app_focus(self):
        """最后点进的那个对话：(它的所有对话编号, 点进的时间 ms)"""
        import glob
        best = None
        for root in APP_SESSIONS:
            files = glob.glob(os.path.join(root, "*", "*", "local_*.json"))
            if not files:
                continue
            for f in files:
                try:
                    mt = os.path.getmtime(f)
                except OSError:
                    continue
                old = self.app_seen.get(f)
                if not old or old[0] != mt:
                    d = read_json(f, None)
                    if not isinstance(d, dict):
                        continue
                    ids = tuple(i for i in [d.get("cliSessionId")] + list(d.get("priorCliSessionIds") or []) if i)  # 重开过的对话编号会换，旧的也认
                    old = self.app_seen[f] = (mt, ids, d.get("lastFocusedAt") or 0)
                if old[1] and (not best or old[2] > best[1]):
                    best = (old[1], old[2])
            break
        return best

    def all_memos(self):
        try:
            mt = os.path.getmtime(TALKIE_STATE)
        except OSError:
            return []
        if mt != self.memo_cache[0]:
            st = read_json(TALKIE_STATE, None)
            if isinstance(st, dict):
                self.memo_cache = (mt, st.get("memos") or [])
        return self.memo_cache[1]

    def remind_for(self, ids, switched=False):
        """脚下那条一直跟着现在点着的对话（备忘改了、做完了，一秒内跟着变）；
        刚点进一个欠着备忘的对话，小克还把对讲机举到耳边几秒"""
        memos = [m for m in self.all_memos() if not m.get("done") and (m.get("link") or {}).get("sid") in ids]
        memos.sort(key=lambda m: -(m.get("at") or 0))
        todo = {"key": ids[0], "items": [m.get("text", "") for m in memos]} if memos else None
        if todo != self.todo:
            self.todo = todo
            self.draw()
        if todo and switched:
            self.remind_until = time.time() + 8

    def draw_bubble(self, text, st):
        c = self.canvas
        full = text = " ".join(str(text).split())
        t = c.create_text(0, 0, text=text, font=self.font, fill=INK, width=self.w - 28, anchor="nw")
        while text and c.bbox(t)[3] - c.bbox(t)[1] > self.font.metrics("linespace") * 2 + 2:  # 超过两行就截掉
            text = text[:-1]
            c.itemconfig(t, text=text + "…")
        if text != full and not text:
            c.itemconfig(t, text="…")
        x0, y0, x1, y1 = c.bbox(t)
        bw, bh = x1 - x0 + 20, y1 - y0 + 10
        left = (self.w - bw) / 2
        top = self.bh - 10 - bh
        k = 6  # 切角，跟工作台的工业风一样
        pts = [left + k, top, left + bw, top, left + bw, top + bh - k, left + bw - k, top + bh,
               self.w / 2 + 5, top + bh, self.w / 2, top + bh + 7, self.w / 2 - 5, top + bh,
               left, top + bh, left, top + k]
        c.create_polygon(pts, fill=PAPER, outline=INK, width=2)
        c.create_rectangle(left + 3, top + 3, left + 9, top + 5, fill="#e2412b" if st == "urgent" else YELLOW, width=0)
        c.coords(t, left + 10, top + 5)
        c.tag_raise(t)

    # 轻轻上下晃：忙 / 急快一点，睡觉慢一点
    def tick(self):
        st = self.state()
        self.bob = 0 if self.bob or st == "sleep" else 1
        self.draw()
        self.root.after({"urgent": 250, "cheer": 300, "busy": 600, "relaxed": 900, "sleep": 1500}[st], self.tick)

    # 每秒看一下 status.json 改了没
    def _mtime(self):
        try:
            return os.path.getmtime(STATUS)
        except OSError:
            return 0

    def poll(self):
        m = self._mtime()
        if m != self.mtime:
            self.mtime = m
            data = read_json(STATUS, None)
            if isinstance(data, dict):  # 写到一半读不出来就先不管，下次再读
                self.status = {**DEFAULT_STATUS, **data}
                self.draw()
        self.check_talkie()
        # 克讲机收起时有新回答 / 新生图请求：头顶冒个泡
        n = read_json(NOTICE, None)
        if isinstance(n, dict) and n.get("id") and n.get("id") != self.notice_id:
            self.notice_id = n["id"]
            if time.time() - (n.get("at") or 0) < 60:
                self.strip_note = (str(n.get("text") or ""), time.time() + 30)
                self.draw()
        self.root.after(1000, self.poll)

    def set_status(self, **kv):
        data = read_json(STATUS, None)
        data = data if isinstance(data, dict) else dict(self.status)
        data.update(kv)
        write_json(STATUS, data)
        self.status = {**DEFAULT_STATUS, **data}
        self.mtime = self._mtime()
        self.draw()

    def save_settings(self):
        self.settings["x"], self.settings["y"] = self.root.winfo_x(), self.root.winfo_y()
        write_json(SETTINGS, self.settings)

    # 点一下 / 拖动
    def on_press(self, e):
        self.drag = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y(), False)
        self.long = False
        self.long_job = self.root.after(450, self.on_long)

    def on_drag(self, e):
        if not self.drag:
            return
        sx, sy, wx, wy, moved = self.drag
        dx, dy = e.x_root - sx, e.y_root - sy
        if moved or abs(dx) + abs(dy) > 4:
            self.drag = (sx, sy, wx, wy, True)
            self.root.geometry(f"+{wx + dx}+{wy + dy}")
            if self.long_job:  # 拖起来了就不算长按
                self.root.after_cancel(self.long_job)
                self.long_job = None

    def on_long(self):
        """长按小克 = 按住说话：叫出对讲机并开始语音，松手停"""
        self.long_job = None
        if self.drag and not self.drag[4]:
            self.long = True
            self.say_once("在听～说吧")
            self.open_talkie("start")

    def on_release(self, e):
        if self.long_job:
            self.root.after_cancel(self.long_job)
            self.long_job = None
        if self.long:
            self.long = False
            self.drag = None
            self.open_talkie("stop")
            return
        on_strip = (self.drag and not self.drag[4] and e.y >= getattr(self, "strip_top", 1e9)
                    and (self.todo or time.time() < self.strip_note[1]))
        if on_strip:  # 点脚下那条：打开克讲机（待办 → 记档）
            note = time.time() < self.strip_note[1]
            self.strip_note = ("", 0)
            self.open_talkie(mode=None if note else "memo")
            self.drag = None
            self.draw()
            return
        wb = getattr(self, "walkie_box", None)
        if self.drag and not self.drag[4] and wb and wb[0] <= e.x <= wb[2] and wb[1] <= e.y <= wb[3] and not self.double:
            # 单击手里的迷你对讲机 = 打开克讲机（单击小克身上别处还是原来的：打开 Claude / 工作台）
            self.drag = None
            self.open_talkie()
            return
        if self.double:  # 双击的第二下松手，不算单击
            self.double = False
        elif self.drag and self.drag[4]:
            self.save_settings()
        elif self.drag:
            self.click_job = self.root.after(280, self.on_click)
        self.drag = None

    def on_click(self):
        self.click_job = None
        self.open_claude() if self.settings["click"] == "claude" else self.open_workbench()

    def on_double(self, e):
        if self.click_job:
            self.root.after_cancel(self.click_job)
            self.click_job = None
        self.double = True
        self.open_talkie()

    # 克讲机：已经开着它自己会挪到小克旁边，没开就开一个
    def open_talkie(self, talk=None, mode=None):
        if not os.path.exists(TALKIE):
            self.say_once("找不到克讲机～")
            return
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        r = self.root
        near = [str(v) for v in (r.winfo_x(), r.winfo_y(), r.winfo_width(), r.winfo_height())]
        subprocess.Popen([exe if os.path.exists(exe) else "pythonw", TALKIE, "--near", *near] + (["--talk", talk] if talk else []) + (["--mode", mode] if mode else []))

    # 工作台用单独的窗口打开（浏览器的「应用」模式：没有标签页和地址栏，任务栏上单独一个图标；用户 2026-10-15 要的）
    # 先用 Edge（这台电脑默认的浏览器，之前就是在它里面打开工作台的），没有再用 Chrome，都没有才退回普通打开
    def open_workbench(self):
        url = self.status.get("url") or WORKBENCH
        for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
            if os.path.exists(exe):
                try:
                    subprocess.Popen([exe, "--app=" + url, "--window-size=1280,880"])
                    return
                except Exception:
                    pass
        webbrowser.open(url)

    def open_claude(self):
        os.startfile("claude://")  # Claude 桌面版自己登记的链接，会把它叫到前面

    # 工作台衣柜里点「复制给桌宠」，再到这里粘贴：造型 + 自己画的部件 + 存的整体造型
    def paste_look(self):
        try:
            data = json.loads(self.root.clipboard_get())
        except (tk.TclError, ValueError):
            data = None
        if not isinstance(data, dict) or not data.get("clawdPet"):
            self.say_once("剪贴板里没有造型～先去工作台衣柜点「复制给桌宠」")
            return
        pool = [q for q in data.get("pool") or [] if isinstance(q, dict) and q.get("look")][:12]
        if pool:  # 一群小克轮流来
            self.set_status(pool=pool, parts=data.get("parts") or [], say="")
            self.rotate_now()
            if not self.settings.get("rotate"):
                self.set_setting("rotate", 60)
            return
        self.set_status(look=data.get("look") or self.status["look"], parts=data.get("parts") or [], presets=data.get("presets") or [], pool=[], say="")
        self.say_once("换好啦！")

    # 随机换小克：从工作台粘贴来的那一群里换一只（不耗 token，只是本地换造型）
    def rotate_now(self):
        pool = [q for q in self.status.get("pool") or [] if isinstance(q, dict) and q.get("look")]
        if not pool:
            self.say_once("还没有一群小克～先去工作台 ⚙ 选「桌宠随机换」再粘贴")
            return
        cur = self.status.get("petName")
        pick = random.choice([q for q in pool if q.get("name") != cur] or pool)
        self.set_status(look=pick["look"], petName=pick.get("name") or "", say="")
        self.settings["rotAt"] = time.time()
        self.save_settings()
        self.say_once(f"换我来啦～我是{pick.get('name') or '小克'}")

    def rotate_tick(self):
        mins = self.settings.get("rotate") or 0
        if mins and self.status.get("pool") and time.time() - (self.settings.get("rotAt") or 0) >= mins * 60:
            self.rotate_now()
        self.root.after(60000, self.rotate_tick)

    def say_once(self, text):
        """上面气泡临时说一句，6 秒后变回工作台定的话（以前会一直盖着工作台的话）"""
        self.say_tmp = (text, time.time() + 6)
        self.draw()

    # 右键菜单
    def on_menu(self, e):
        m = tk.Menu(self.root, tearoff=0, font=FONT)
        m.add_command(label="打开 今日小克终未地（单独窗口）", command=self.open_workbench)
        m.add_command(label="打开 Claude", command=self.open_claude)
        m.add_command(label="克讲机（双击小克也行，长按 = 按住说话）", command=self.open_talkie)
        m.add_command(label=("✓ " if self.settings.get("walkie", True) else "　 ") + "手里拿着迷你对讲机",
                      command=lambda: (self.set_setting("walkie", not self.settings.get("walkie", True)), self.draw()))
        pet_col = self.settings.get("walkieColor", "pet") == "pet"
        m.add_command(label="　 迷你对讲机颜色：" + ("跟小克（点一下换成跟克讲机机身）" if pet_col else "跟克讲机机身（点一下换成跟小克）"),
                      command=lambda: (self.set_setting("walkieColor", "talkie" if pet_col else "pet"), self.draw()))
        m.add_separator()

        sm = tk.Menu(m, tearoff=0, font=FONT)
        cur = tk.StringVar(value=self.state())
        for k in STATES:
            sm.add_radiobutton(label=STATE_ZH[k], variable=cur, value=k, command=lambda k=k: self.set_status(state=k, say=""))
        m.add_cascade(label="状态", menu=sm)

        lm = tk.Menu(m, tearoff=0, font=FONT)
        for name, look in PRESETS.items():
            lm.add_command(label=name, command=lambda look=look: self.set_status(look=dict(look)))
        mine = [q for q in self.status.get("presets") or [] if isinstance(q, dict) and q.get("look")]
        if mine:
            lm.add_separator()
            for q in mine:
                lm.add_command(label="✎ " + str(q.get("name") or "?"), command=lambda look=q["look"]: self.set_status(look=dict(look)))
        lm.add_separator()
        lm.add_command(label="粘贴工作台的造型", command=self.paste_look)
        m.add_cascade(label="造型", menu=lm)

        rm = tk.Menu(m, tearoff=0, font=FONT)
        rot = tk.IntVar(value=self.settings.get("rotate") or 0)
        for k, v in ROTATE.items():
            rm.add_radiobutton(label=v, variable=rot, value=k, command=lambda k=k: self.set_setting("rotate", k))
        rm.add_separator()
        rm.add_command(label="现在换一只", command=self.rotate_now)
        m.add_cascade(label="随机换小克", menu=rm)

        zm = tk.Menu(m, tearoff=0, font=FONT)
        size = tk.StringVar(value=self.settings["size"])
        for k in SIZES:
            zm.add_radiobutton(label=k, variable=size, value=k, command=lambda k=k: self.set_size(k))
        m.add_cascade(label="大小", menu=zm)

        cm = tk.Menu(m, tearoff=0, font=FONT)
        click = tk.StringVar(value=self.settings["click"])
        for k, v in CLICK.items():
            cm.add_radiobutton(label=v, variable=click, value=k, command=lambda k=k: self.set_setting("click", k))
        m.add_cascade(label="点一下打开", menu=cm)

        bub = tk.BooleanVar(value=self.settings["bubble"])
        m.add_checkbutton(label="显示说话气泡", variable=bub, command=lambda: self.toggle("bubble"))
        top = tk.BooleanVar(value=self.settings["topmost"])
        m.add_checkbutton(label="一直在最上面", variable=top, command=lambda: self.toggle("topmost"))
        auto = tk.BooleanVar(value=os.path.exists(STARTUP_BAT))
        m.add_checkbutton(label="开机自动出现", variable=auto, command=self.toggle_startup)
        m.add_separator()
        m.add_command(label="打开状态文件", command=lambda: subprocess.Popen(["notepad.exe", STATUS]))
        m.add_command(label="退出", command=self.quit)
        m.tk_popup(e.x_root, e.y_root)

    def set_size(self, k):
        bottom = self.root.winfo_y() + self.h
        center = self.root.winfo_x() + self.w / 2
        self.settings["size"] = k
        self.layout()
        self.root.geometry(f"+{int(center - self.w / 2)}+{int(bottom - self.h)}")  # 脚的位置不变
        self.draw()
        self.root.after(50, self.save_settings)

    def set_setting(self, key, v):
        self.settings[key] = v
        self.save_settings()

    def toggle(self, key):
        self.settings[key] = not self.settings[key]
        if key == "topmost":
            self.root.wm_attributes("-topmost", self.settings["topmost"])
        self.draw()
        self.save_settings()

    def toggle_startup(self):
        if os.path.exists(STARTUP_BAT):
            os.remove(STARTUP_BAT)
        else:
            pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pyw):
                pyw = sys.executable
            with open(STARTUP_BAT, "w", encoding="mbcs") as f:
                f.write(f'@start "" "{pyw}" "{os.path.abspath(__file__)}"\r\n')

    def quit(self):
        self.save_settings()
        self.root.destroy()


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 高分屏上像素不糊
    except (AttributeError, OSError):
        pass
    Pet().root.mainloop()
