# 让桌宠跟着 Claude 对话自动变状态（给 Claude Code 的 hook 用，用户同意后才接上）。
# 用法：python pet_hook.py busy | done | wait
#   busy = 你刚发了消息，Claude 开始干活；done = Claude 这一轮做完了；wait = Claude 在等你回复 / 点同意
# 只改 status.json 里的 state 和 say，造型（look / parts / presets）不动。
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(HERE, "status.json")
MAP = {"busy": ("busy", "在干活…"), "done": ("cheer", "做完一步啦！"), "wait": ("urgent", "等你回我一下～")}


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in MAP:
        return
    try:
        sys.stdin.read()  # hook 会把这次的信息从 stdin 传进来，这里用不上，读掉就行
    except Exception:
        pass
    try:
        with open(STATUS, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["state"], data["say"] = MAP[kind]
    tmp = STATUS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATUS)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 桌宠的事出错了也别影响对话
