# -*- coding: utf-8 -*-
"""把开源版要改的地方打进 workbench.html（照原文精确替换，找不到就报错，不会乱改）。
用法：python -I tools/build.py
- 每次同步了新主版以后再跑一遍；已经改过的地方会跳过
- 原创 / Original work: Miaomiao (GitHub: Miaomiaomeowmeow) · CC BY-NC-SA 4.0
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGE = os.path.join(ROOT, "workbench.html")
MARK = "<!-- clawdfield-local-adapter -->"

# (说明, 原文, 新文)
SWAPS = [
    ("读不到数据的提示：两边都说清楚",
     'noLogin: ["现在读不到内容：请登录 claude.ai 后从侧边栏打开这个页面。", "Can\'t load data. Sign in to claude.ai and open this page from the sidebar."]',
     'noLogin: ["现在读不到内容。在自己电脑上：先双击 start.bat 再打开；在 claude.ai 上：从侧边栏打开这个页面。", "Can\'t load data. On your computer: double-click start.bat first. On claude.ai: open this page from the sidebar."]'),
    ("AI 没接上的提示：告诉去哪接",
     'aiOff: ["这里用不了 AI 画。可以在对话里跟 Claude 说「给小克画一个 XX」。", "AI drawing isn\'t available here. Ask Claude in a chat: “draw a ___ for Clawd”."]',
     'aiOff: ["AI 还没接上。在自己电脑上：打开 localhost:8765/setup 选一种 AI；在 claude.ai 上：在对话里跟 Claude 说。", "AI isn\'t connected yet. On your computer: open localhost:8765/setup and pick one. On claude.ai: ask Claude in a chat."]'),
]


def main():
    with io.open(PAGE, encoding="utf-8") as f:
        s = f.read()
    orig = s
    # 1) 转接层：放在网页本体的 <script> 前面
    if MARK not in s:
        with io.open(os.path.join(HERE, "local-adapter.js"), encoding="utf-8") as f:
            js = f.read()
        i = s.find("<script>")
        if i < 0:
            sys.exit("找不到 <script>，网页结构变了，停下来人工看")
        s = s[:i] + MARK + "\n<script>\n" + js + "</script>\n" + s[i:]
        print("✓ 加了本机转接层")
    else:
        print("- 本机转接层已经有了")
    # 2) 文字替换
    for why, old, new in SWAPS:
        if new in s:
            print("- 已改过：" + why)
        elif s.count(old) == 1:
            s = s.replace(old, new)
            print("✓ " + why)
        else:
            sys.exit("✗ 找不到（或不止一处）：" + why + "  —— 主版可能改了这句，停下来人工看")
    if s != orig:
        bak = os.path.join(tempfile.gettempdir(), "clawdfield-workbench-before-build.html")
        shutil.copyfile(PAGE, bak)
        with io.open(PAGE, "w", encoding="utf-8", newline="") as f:
            f.write(s)
        print("改好了。改之前的备份：" + bak)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
