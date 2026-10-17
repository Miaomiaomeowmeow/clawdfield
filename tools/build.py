# -*- coding: utf-8 -*-
"""把开源版要改的地方打进 workbench.html（照原文精确替换，找不到就报错，不会乱改）。
用法：python -I tools/build.py
- 每次同步了新主版以后再跑一遍；已经改过的地方会跳过，转接层会换成最新的
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

# (说明, 原文, 新文, 原文应该出现几次；None = 至少一次、全部替换)
SWAPS = [
    ("读不到数据的提示：两边都说清楚",
     'noLogin: ["现在读不到内容：请登录 claude.ai 后从侧边栏打开这个页面。", "Can\'t load data. Sign in to claude.ai and open this page from the sidebar."]',
     'noLogin: ["现在读不到内容。在自己电脑上：先双击 start.bat 再打开；在 claude.ai 上：从侧边栏打开这个页面。", "Can\'t load data. On your computer: double-click start.bat first. On claude.ai: open this page from the sidebar."]',
     1),
    ("AI 没接上的提示：告诉去哪接",
     'aiOff: ["这里用不了 AI 画。可以在对话里跟 Claude 说「给小克画一个 XX」。", "AI drawing isn\'t available here. Ask Claude in a chat: “draw a ___ for Clawd”."]',
     'aiOff: ["AI 还没接上。在自己电脑上：打开 localhost:8765/setup 选一种 AI；在 claude.ai 上：在对话里跟 Claude 说。", "AI isn\'t connected yet. On your computer: open localhost:8765/setup and pick one. On claude.ai: ask Claude in a chat."]',
     1),
    ("小克的像素画里带上看不见的五个点",
     'aria-hidden="true">${g}</svg>',
     'aria-hidden="true">${g}${window.CF_SIG || ""}</svg>',
     None),
]


def main():
    with io.open(PAGE, encoding="utf-8") as f:
        s = f.read()
    orig = s
    with io.open(os.path.join(HERE, "local-adapter.js"), encoding="utf-8") as f:
        block = MARK + "\n<script>\n" + f.read() + "</script>\n"
    # 1) 转接层：放在网页本体的 <script> 前面；已经有了就换成最新的
    if MARK in s:
        a = s.index(MARK)
        b = s.index("</script>\n", a) + len("</script>\n")
        if s[a:b] != block:
            s = s[:a] + block + s[b:]
            print("✓ 转接层换成了最新的")
        else:
            print("- 转接层已经是最新的")
    else:
        i = s.find("<script>")
        if i < 0:
            sys.exit("找不到 <script>，网页结构变了，停下来人工看")
        s = s[:i] + block + s[i:]
        print("✓ 加了本机转接层")
    # 2) 文字替换
    for why, old, new, n in SWAPS:
        have = s.count(old)
        if new in s and have == 0:
            print("- 已改过：" + why)
        elif (n is None and have >= 1) or have == n:
            s = s.replace(old, new)
            print("✓ %s（%d 处）" % (why, have))
        else:
            sys.exit("✗ 找不到（或次数不对）：" + why + "  —— 主版可能改了这里，停下来人工看")
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
