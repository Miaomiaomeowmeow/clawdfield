# 贴进 AI 说明文件的那一段 · Snippet for your AI's instruction file

安装向导（AI-SETUP.md）第 ⑧ 题会让 AI 把下面这段贴进它自己会读的说明文件（`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`……）。也可以自己手动贴：把 `<安装路径>` 换成工作台装在哪的绝对路径。

今日小克终未地 · 原创 Miaomiao（GitHub: Miaomiaomeowmeow）· CC BY-NC-SA 4.0

---

复制下面这段 ↓

```markdown
## 今日小克终未地（把进度写进工作台）

工作台装在 `<安装路径>`。下面的命令都在**当前项目文件夹**里跑，它会自己认出是哪只小克：`python "<安装路径>/clawd.py" …`

- 每次对话开始：先跑 `clawd.py hello`，照它说的做。它会告诉你这个文件夹是哪只小克、还挂着什么；没登记的话，它会告诉你怎么问用户
- 开始做一大块活之前：`clawd.py wait ai "正在做什么"`（工作台上显示「AI 在做」）
- 做完一个里程碑（定了方向、做完一页、上线）：`clawd.py note "做成了什么"`，再 `clawd.py latest "最新进展一句话"`
- 有要用户马上做的事：`clawd.py todo add "做什么" --where "去哪做" --prompt "能直接复制的原文"`
- 用户说做完了，或你看到已经做完了：`clawd.py todo done "关键词"`
- 这一轮最后在等用户：`clawd.py wait test "等用户试什么"`（还有 `reply` 回话 / `feedback` 反馈 / `decide` 决定）；用户回了：`clawd.py wait clear`
- 项目的大框架搭好了：`clawd.py framework-done`
- 有桌宠的话（可选）：干完一块 `clawd.py pet cheer "做好啦"`；卡住要用户来 `clawd.py pet urgent "要你决定"`
- 写进去的话用户会在工作台上看到：写清楚、一句话、用用户的语言
```
