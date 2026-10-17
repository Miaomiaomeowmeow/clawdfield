# 给 AI 看的安装向导 · Setup guide for the user's AI

> 使用者会跟你（他们的 AI 助手：Codex、Claude Code、Cursor、WorkBuddy、Gemini……都行）说一句“照 AI-SETUP.md 帮我设置”。你照下面一步步做。
> If the user writes in English, ask the questions in English. Keep it friendly and short; the user may not be technical.
>
> 今日小克终未地 · 原创 Miaomiao（GitHub: Miaomiaomeowmeow）· CC BY-NC-SA 4.0，不准商用

下面 `<安装路径>` = 这个文件所在的文件夹（绝对路径）。命令都写成 `python "<安装路径>/clawd.py" …`（Windows 上 `python` 不行就试 `py -3`，Mac 上用 `python3`）。

---

## 规矩（整个设置过程都照这个）

- **一次只问一个问题**，每题给选项，第一个是你的推荐。用户不懂技术：别用专业词，非用不可就用一句大白话解释
- 每题都有三种回答：**要** / **不要** / **要，但我没有某样东西**。第三种就照题目里写的「没有的话」告诉用户去哪下载、装好再继续；能自己检查的（例：电脑上有没有 Python、有没有 Codex）**先自己检查**，别问用户
- **不要的功能只是关掉**（在 ⚡ 电闸里拉下来），代码不删，以后随时能打开
- 改用户电脑上的东西（往用户的 AI 说明文件里加一段、建桌面快捷方式）之前，先说清楚要改哪里、问一句
- 每题答完就马上用命令写进去，别攒到最后

---

## 第 0 步：先自己检查（不用问用户）

1. 这台电脑是 Windows、Mac 还是 Linux
2. 有没有 Python 3.8 以上：`python --version`（或 `py -3 --version` / `python3 --version`）
   - 没有 → 告诉用户：去 https://www.python.org/downloads/ 下载安装；**Windows 安装时一定勾上「Add python.exe to PATH」**；装好告诉你，再继续
3. 电脑上有没有已经登录的 AI 助手命令：`codex --version`、`claude --version`（Windows 上 Codex 桌面版的命令也可能在 `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe`）
4. 跑 `python "<安装路径>/clawd.py" status`，确认能跑

## 第 1 步：开场白（照这个意思说，可以用自己的话）

> 我来帮你把「今日小克终未地」装好。它是一个放在你自己电脑上的工作台：每个项目是一只像素小克，要你做的事、存下来的东西、以后再做的想法都挂在它名下，我（AI）干活的进度也会写进去。我会问你几个问题，每个都能说“要 / 不要 / 要但我没有”。不要的只是先关掉，以后在网页右上角的 ⚡ 电闸里随时能打开。

## 第 2 步：一题一题问

### ① 用小克这个样子吗？
- 现在只有小克（Clawd）这一个样子；颜色、衣服、帽子、宠物都能在网页里换，也能自己画、让 AI 画
- 要 → 继续。想要完全不同的角色 → 告诉用户：目前还没有，可以先用小克，在衣柜里换颜色和装扮

### ② 你的项目都放在哪？哪些文件夹算一只小克？
- 问一个大文件夹（例：`D:\我的项目`），你去列出里面一层的文件夹，**一条条问**：算一只小克吗？叫什么？有没有上级（它是哪个项目的一部分）？
- 每个答完就登记：
  - `python "<安装路径>/clawd.py" register "<文件夹>" "<小克名字>"`
  - 是别的项目的一部分：后面加 `--parent "<上级小克名字>"`
  - 不加入：`python "<安装路径>/clawd.py" register "<文件夹>" --no`
- 小克名字可以俏皮一点，但要一看就知道是哪个项目
- 以后新开的文件夹不用现在登记：AI 在那里第一次跑 `clawd.py hello` 时会自己来问

### ③ 网页里带 ✨ 的按钮（起名字、写性格、编八卦……）用哪个 AI？
- **借电脑上的 Codex / Claude Code**（第 0 步查到有的才推荐）：不用 Key，用的是它们套餐里的额度。每次要等几秒到几十秒，**问题不大**：手机八卦这种只是偶尔跑一下，平时点按钮等一会儿就好
  - `python "<安装路径>/clawd.py" ai codex`（或 `ai claude`）
- **用自己的 Key**（Claude、OpenAI、Gemini、DeepSeek、Kimi、通义、豆包、OpenRouter，或电脑上跑的 Ollama）：最快，按次数付钱给服务商
  - 不要让用户把 Key 发给你。告诉用户：等工作台打开后，进网址 `http://localhost:8765/setup`，选「用自己的 Key」自己粘贴（Key 只存在他电脑的 `data/config.json`）
- **先不用**：`python "<安装路径>/clawd.py" ai none`。带 ✨ 的按钮会提示还没接上，别的照常用
- 没有 Codex 也没有 Key，但想用 → Codex 在 https://github.com/openai/codex ，Claude Code 在 https://claude.com/claude-code ，装好登录后再选

### ④ 要手机吗？（小克们的八卦群、今日小事、小克的请求）
- 要 → 再问一句：**每天自己冒一次**，还是**只在你点「刷新」时冒**？
  - 自己冒：`python "<安装路径>/clawd.py" phone auto`；只点刷新：`… phone manual`
  - 每次冒都会用一点 AI（借 Codex 的话等十几秒）
- 不要 → `python "<安装路径>/clawd.py" feature off phone`
- 只要其中几样 → `feature off phone.gossip`（八卦群）/ `phone.life`（今日小事）/ `phone.asks`（小克的请求）

### ⑤ 要「公司」那一套吗？（公司大楼、职位、公告栏的公司事件、名人堂、办公室）
- 要 → 什么都不用做
- 不要公司事件 / 名人堂 / 办公室 → `feature off co.event` / `co.fame` / `co.office`（可以只关几样）
- 全都不要 → `feature off co`

### ⑥ 要小克「自己会活」吗？（会长大、自己换心情、很久没人管会变样、别的小克来串门）
- 要 → 什么都不用做；不要 → `feature off live`；只关几样 → `live.age` / `live.mood` / `live.idle` / `live.visit`

### ⑦ 要桌宠吗？（桌面上一只会动的像素小克，跟着你的 AI 变状态）
- 只有 **Windows** 能用。不是 Windows → 告诉用户“桌宠暂时只有 Windows 版”，跳过
- 要 → 告诉用户双击 `<安装路径>\pet\` 里的启动文件；问要不要放桌面快捷方式、要不要开机自动出现（要的话你帮忙建）

### ⑧ 要我以后每次干活都把进度写进去吗？
- 推荐要。要 → 问用户：贴进**全局**（所有项目都这样，推荐）还是只贴进某几个项目
- 把 `<安装路径>/AI-RULES.md` 里「复制下面这段」的内容（把 `<安装路径>` 换成真的路径）贴进**你自己会读的说明文件**：
  - Codex：全局 `~/.codex/AGENTS.md`，或项目里的 `AGENTS.md`
  - Claude Code：全局 `~/.claude/CLAUDE.md`，或项目里的 `CLAUDE.md`
  - Cursor：项目里的 `AGENTS.md`（或 `.cursor/rules/` 里新建一个规则）
  - Gemini CLI：`~/.gemini/GEMINI.md` 或项目里的 `GEMINI.md`
  - 别的 AI 助手：贴进它自己的说明 / 规则文件；不知道在哪就问用户
  - 文件里已经有这段（搜「今日小克终未地」）就别重复贴

## 第 3 步：打开看看

1. 告诉用户双击 `<安装路径>` 里的 `start.bat`（Mac / Linux：`start.command`），浏览器会打开 `http://localhost:8765`
   - 那个黑色窗口别关：关掉 = 工作台关了（数据不会丢）
2. 第 ③ 题选了用 Key 的，提醒去 `http://localhost:8765/setup` 填
3. 跑 `python "<安装路径>/clawd.py" status`，把结果用大白话讲给用户听

## 第 4 步：最后跟用户说（照这个意思）

> 装好了！
> - 不懂的地方看说明书：`<安装路径>/GUIDE.md`（网页里点右上角的 **?** 也能看）
> - 以后网页里还会有一个能直接问的 AI，看不懂哪里就问它
> - 刚才关掉的功能，随时去网页**右上角的 ⚡ 电闸**拉开就有
> - 想改 AI：打开 `http://localhost:8765/setup`
