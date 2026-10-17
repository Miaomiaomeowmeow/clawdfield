#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clawd —— 让任何 AI 助手（Codex、Claude Code、Cursor、WorkBuddy……）把进度写进「今日小克终未地」。
clawd: lets any AI assistant write progress into the Clawdfield workbench.

原创 / Original work: Miaomiao (GitHub: Miaomiaomeowmeow) · CC BY-NC-SA 4.0

只用 Python 自带的功能。工作台开着就通过它写（网页马上刷新），没开就直接写 data/ 里的文件。
常用（在项目文件夹里运行，会自己认出是哪只小克）：
  python clawd.py hello                       对话开始时跑：这是哪只小克 / 没登记怎么办 / 有什么等着
  python clawd.py todo add "要用户做的事" [--where 去哪做] [--note 说明] [--prompt 能复制的原文] [--urgent] [--due 2026-10-30]
  python clawd.py todo done <编号或关键词>      用户做完了
  python clawd.py todo list
  python clawd.py wait test "等用户试什么"       这一轮最后在等用户（reply 回话 / test 试 / feedback 反馈 / decide 决定）
  python clawd.py wait ai "正在做什么"           开工前：工作台显示「AI 在做」
  python clawd.py wait clear                    用户回了
  python clawd.py note "做成了什么"              项目进程记一条里程碑
  python clawd.py latest "最新进展一句话"
  python clawd.py framework-done                大框架搭好了
  python clawd.py pet cheer "做好啦"            桌宠变状态（urgent / busy / relaxed / cheer / sleep）
设置（安装时用）：
  python clawd.py register <文件夹> <小克名字> [--parent 上级小克]   登记：这个文件夹算哪只小克
  python clawd.py register <文件夹> --no                             这个文件夹不加入工作台
  python clawd.py feature list | on <名字>… | off <名字>…             电闸开关（例：off phone、off co.office）
  python clawd.py phone auto | manual                                手机消息自动冒 / 只在点刷新时冒
  python clawd.py ai codex | claude | none                           网页里的 AI 用哪个（用 Key 去网页 /setup 填）
  python clawd.py status                                             看现在的设置
通用参数：--project 小克名字（不按文件夹认）  --chat 对话名字（wait 用，默认是文件夹名）  --folder 文件夹
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("CLAWDFIELD_DATA", os.path.join(ROOT, "data"))
DB = os.path.join(DATA, "db")
FOLDERS = os.path.join(DATA, "folders.json")
PET_STATUS = os.path.join(ROOT, "pet", "status.json")
ID_OK = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")
COLORS = ["#ffb347", "#7bd389", "#6ec6ff", "#ff8fc2", "#b39ddb", "#ffd54f", "#4db6ac", "#f48fb1"]

FEATURES = {  # 电闸：组 → 格子（和网页里的一样）
    "map": ("地图", {"egg": "彩蛋", "pile": "堆堆乐", "say": "头上的话", "fresh": "新东西提醒"}),
    "phone": ("手机", {"gossip": "八卦群", "life": "今日小事", "asks": "小克的请求"}),
    "co": ("公司", {"event": "公司事件", "fame": "名人堂", "office": "办公室"}),
    "live": ("自己会活", {"age": "长大", "mood": "自动换心情", "idle": "没人管会变样", "visit": "敲门串门"}),
}


def today():
    return datetime.date.today().isoformat()


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def rid():
    return secrets.token_hex(5)


def slug(name):
    s = re.sub(r"[^A-Za-z0-9_\-]+", "-", name).strip("-")
    return s if s and s == name.replace(" ", "-") else hashlib.md5(name.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------- 读写（工作台开着走它，没开写文件）

def server_port():
    try:
        with open(os.path.join(DATA, "server.json"), encoding="utf-8") as f:
            port = int(json.load(f)["port"])
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=1) as r:
            return port if json.loads(r.read().decode("utf-8")).get("app") == "clawdfield" else None
    except Exception:
        return None


PORT = None


def http(method, path, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Clawdfield": "1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8") or "null")


def read_coll(coll):
    if PORT:
        return {d["id"]: d["data"] for d in http("GET", "/api/db/" + coll)["docs"]}
    try:
        with open(os.path.join(DB, coll + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_doc(coll, did, doc, merge=False):
    assert ID_OK.match(did), did
    if PORT:
        http("PATCH" if merge else "PUT", "/api/db/%s/%s" % (coll, did), doc)
        return
    os.makedirs(DB, exist_ok=True)
    d = read_coll(coll)
    d[did] = {**(d.get(did) or {}), **doc} if merge else doc
    p = os.path.join(DB, coll + ".json")
    tmp = p + "." + rid() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# ---------------------------------------------------------------- 文件夹 → 小克

def norm(p):
    return os.path.normcase(os.path.abspath(os.path.expanduser(p))).rstrip("\\/")


def folder_entry(folder):
    reg = load_json(FOLDERS, {"folders": {}})
    c, best = norm(folder), None
    for k, v in reg.get("folders", {}).items():
        nk = norm(k)
        if c == nk or c.startswith(nk + os.sep):
            if best is None or len(nk) > len(norm(best[0])):
                best = (k, v)
    return best


def projects():
    return read_coll("projects")


def find_project(name):
    for pid, p in projects().items():
        if p.get("name") == name or name in (p.get("aliases") or []):
            return pid, p
    return None, None


def ensure_project(name, parent=None):
    pid, p = find_project(name)
    if not pid:
        pid = "p" + rid()
        p = {"name": name, "bornAt": today(), "color": COLORS[len(projects()) % len(COLORS)],
             "frameworkDone": False, "timeline": [], "history": [{"id": rid(), "k": "born", "d": today(), "t": "来到工作台"}]}
        write_doc("projects", pid, p)
    if parent and parent != name:
        ppid, pp = find_project(parent)
        if not ppid:
            ppid = ensure_project(parent)
            _, pp = find_project(parent)
        write_doc("projects", pid, {"linkOf": {**(p.get("linkOf") or {}), parent: "sup"}}, merge=True)
        write_doc("projects", ppid, {"linkOf": {**(pp.get("linkOf") or {}), name: "sub"}}, merge=True)
    return pid


def who(a):
    if a.project:
        return a.project
    e = folder_entry(a.folder or os.getcwd())
    if e and e[1].get("project"):
        return e[1]["project"]
    sys.exit("这个文件夹还没登记是哪只小克。先跑：python clawd.py hello（它会告诉你怎么问用户），或者加 --project 名字")


# ---------------------------------------------------------------- 命令

def cmd_hello(a):
    folder = os.path.abspath(a.folder or os.getcwd())
    e = folder_entry(folder)
    reg = load_json(FOLDERS, {"folders": {}})
    if e and e[1].get("no"):
        print("这个文件夹不加入工作台（用户以前说过不要）。这次对话不用往工作台写东西。")
        return
    if not e:
        names = sorted({p.get("name") for p in projects().values() if p.get("name")})
        print("【今日小克终未地】这个文件夹还没登记：%s" % folder)
        print("请在第一次回复里用一个问题问用户（给 4 个选项，附你的推荐）：")
        print("  1. 就是已有的某只小克（合并）：" + ("、".join(names) if names else "（现在还没有小克）"))
        print("  2. 当某只小克的下属（子项目），起个新名字")
        print("  3. 单独加一只新小克，起个名字")
        print("  4. 不加入工作台")
        print("用户答了再运行其中一条：")
        print('  python "%s" register "%s" "<小克名字>" [--parent "<上级>"]' % (os.path.join(ROOT, "clawd.py"), folder))
        print('  python "%s" register "%s" --no' % (os.path.join(ROOT, "clawd.py"), folder))
        return
    name = e[1]["project"]
    pid, p = find_project(name)
    todos = [t for t in read_coll("todo").values() if t.get("project") == name and not t.get("done")]
    waits = [t for t in todos if t.get("wait")]
    ideas = [t for t in todos if t.get("by") == "me" and t.get("rough")]
    print("【今日小克终未地】这个文件夹是小克「%s」%s。往工作台写东西都用这个名字。" % (name, "（上级：%s）" % e[1]["parent"] if e[1].get("parent") else ""))
    if p and (p.get("meta") or {}).get("latest"):
        print("最新进展：" + p["meta"]["latest"])
    if waits:
        print("还挂着「等你」：" + "；".join("%s（%s）" % (t.get("title"), t.get("wait")) for t in waits[:3]) + " —— 用户回了就 wait clear")
    if ideas:
        print("用户自己写的想法（先跟用户讨论清楚再做）：" + "；".join(t.get("title", "") for t in ideas[:5]))
    rest = [t for t in todos if not t.get("wait") and t not in ideas]
    if rest:
        print("没勾掉的待办 %d 条（看到做完了就 todo done）：%s" % (len(rest), "；".join(t.get("title", "") for t in rest[:5])))
    if p and not p.get("frameworkDone"):
        print("大框架还没标好：搭好了就跑 framework-done")
    print("规矩：开工前 wait ai「在做什么」；做完一个里程碑 note；有要用户做的事 todo add；这一轮最后在等用户就 wait test/reply/feedback/decide。")


def cmd_register(a):
    folder = os.path.abspath(a.folder_arg)
    reg = load_json(FOLDERS, {"folders": {}})
    reg.setdefault("folders", {})
    if a.no:
        reg["folders"][folder] = {"no": True}
        save_json(FOLDERS, reg)
        print("记好了：%s 不加入工作台" % folder)
        return
    if not a.name:
        sys.exit("要写小克名字，或者加 --no")
    entry = {"project": a.name}
    if a.parent:
        entry["parent"] = a.parent
    reg["folders"][folder] = entry
    save_json(FOLDERS, reg)
    ensure_project(a.name, a.parent)
    print("记好了：%s → 小克「%s」%s" % (folder, a.name, "，上级「%s」" % a.parent if a.parent else ""))


def cmd_todo(a):
    if a.op == "list":
        name = who(a)
        rows = [(k, t) for k, t in read_coll("todo").items() if t.get("project") == name and not t.get("done")]
        for k, t in rows:
            print("%s  %s%s" % (k, t.get("title"), "  [等你:%s]" % t["wait"] if t.get("wait") else ""))
        print("（%d 条没做完）" % len(rows))
        return
    if a.op == "add":
        name = who(a)
        ensure_project(name)
        doc = {"title": a.text, "project": name, "done": False, "createdAt": now()}
        for k in ("where", "note", "prompt", "due"):
            if getattr(a, k):
                doc[k] = getattr(a, k)
        if a.urgent:
            doc["urgent"] = True
        tid = "t" + rid()
        write_doc("todo", tid, doc)
        print("加好了：%s（编号 %s）" % (a.text, tid))
        return
    if a.op == "done":
        todo = read_coll("todo")
        if a.text in todo:
            hits = [a.text]
        else:
            name = who(a)
            hits = [k for k, t in todo.items() if t.get("project") == name and not t.get("done") and a.text in (t.get("title") or "")]
        if len(hits) != 1:
            sys.exit("找到 %d 条，写得再准一点（或用编号，todo list 能看）" % len(hits))
        write_doc("todo", hits[0], {"done": True, "doneAt": today()}, merge=True)
        print("勾掉了：" + (todo[hits[0]].get("title") or hits[0]))


def cmd_wait(a):
    name = who(a)
    chat = a.chat or os.path.basename(os.path.abspath(a.folder or os.getcwd()))
    did = "wait-%s-%s" % (slug(name), slug(chat))
    if a.kind == "clear":
        if did in read_coll("todo"):
            write_doc("todo", did, {"done": True, "doneAt": today()}, merge=True)
        print("好，不再显示等你")
        return
    if not a.text:
        sys.exit("写一句话：要用户做什么 / AI 在做什么")
    ensure_project(name)
    write_doc("todo", did, {"title": a.text, "project": name, "wait": a.kind, "chat": chat, "done": False, "createdAt": now()})
    print("工作台上会显示：%s：%s" % ({"ai": "AI 在做", "reply": "等你回话", "test": "等你试", "feedback": "等你反馈", "decide": "等你决定"}[a.kind], a.text))


def cmd_note(a):
    name = who(a)
    pid = ensure_project(name)
    p = projects()[pid]
    tl = list(p.get("timeline") or []) + [{"id": rid(), "d": today(), "t": a.text, "by": "chat"}]
    write_doc("projects", pid, {"timeline": tl}, merge=True)
    print("记进「%s」的项目进程了" % name)


def cmd_latest(a):
    name = who(a)
    pid = ensure_project(name)
    meta = {**(projects()[pid].get("meta") or {}), "latest": a.text, "updated": today()}
    write_doc("projects", pid, {"meta": meta}, merge=True)
    print("更新了最新进展")


def cmd_framework(a):
    pid = ensure_project(who(a))
    write_doc("projects", pid, {"frameworkDone": True}, merge=True)
    print("标好了：大框架做好了")


def cmd_pet(a):
    if a.state not in ("urgent", "busy", "relaxed", "cheer", "sleep"):
        sys.exit("状态只能是 urgent / busy / relaxed / cheer / sleep")
    d = load_json(PET_STATUS, {})
    d["state"], d["say"] = a.state, (a.say or "")[:30]
    save_json(PET_STATUS, d)
    print("桌宠：%s %s" % (a.state, a.say or ""))


def general():
    return read_coll("settings").get("general") or {}


def cmd_feature(a):
    g = general()
    feat, phone = dict(g.get("feat") or {}), dict(g.get("phone") or {})
    cats = dict(phone.get("cats") or {})

    def get(k):
        grp, _, cell = k.partition(".")
        if not cell:
            return phone.get("on", True) is not False if grp == "phone" else feat.get(grp, True) is not False
        if grp == "phone" or k == "co.event":
            return (cats.get(cell) or {}).get("on", True) is not False
        return feat.get(k, True) is not False

    def put(k, on):
        grp, _, cell = k.partition(".")
        if grp not in FEATURES or (cell and cell not in FEATURES[grp][1]):
            sys.exit("没有这个开关：%s（feature list 看全部）" % k)
        if not cell:
            if grp == "phone":
                phone["on"] = on
            else:
                feat[grp] = on
        elif grp == "phone" or k == "co.event":
            cats[cell] = {**(cats.get(cell) or {}), "on": on}
        else:
            feat[k] = on

    if a.op == "list":
        for grp, (zh, cells) in FEATURES.items():
            print("%-6s %s %s" % (grp, "●" if get(grp) else "○", zh))
            for c, czh in cells.items():
                print("   %-14s %s %s" % (grp + "." + c, "●" if get(grp + "." + c) else "○", czh))
        print("● 开着 ○ 关着。网页右上角 ⚡ 电闸里也能拉。")
        return
    for k in a.names:
        put(k, a.op == "on")
    if cats:
        phone["cats"] = cats
    write_doc("settings", "general", {"feat": feat, "phone": phone}, merge=True)
    print(("打开了：" if a.op == "on" else "关掉了：") + "、".join(a.names))


def cmd_phone(a):
    g = general()
    phone = dict(g.get("phone") or {})
    phone["freq"] = "manual" if a.mode == "manual" else "daily"
    cats = {c: {**v, "freq": phone["freq"]} for c, v in (phone.get("cats") or {}).items()}
    if cats:
        phone["cats"] = cats
    write_doc("settings", "general", {"phone": phone}, merge=True)
    print("手机消息：" + ("只在点「刷新」时冒" if a.mode == "manual" else "每天自己冒一次"))


def cmd_ai(a):
    p = os.path.join(DATA, "config.json")
    c = load_json(p, {})
    if a.tool == "none":
        c["source"] = "none"
    else:
        c["source"] = "cli"
        c["cli"] = {**(c.get("cli") or {}), "tool": a.tool}
    save_json(p, c)
    print("网页里的 AI：" + {"none": "先不用", "codex": "借 Codex", "claude": "借 Claude Code"}[a.tool] + "（要用 Key 就打开工作台网址 /setup 填）")


def cmd_status(a):
    c = load_json(os.path.join(DATA, "config.json"), {})
    reg = load_json(FOLDERS, {"folders": {}})
    print("工作台：%s" % ("开着（端口 %d）" % PORT if PORT else "没开（双击 start.bat 打开）"))
    print("数据在：%s" % DATA)
    print("网页里的 AI：%s" % {"cli": "借 " + ((c.get("cli") or {}).get("tool") or "codex"), "api": "自己的 Key"}.get(c.get("source"), "先不用"))
    print("登记的文件夹：")
    for k, v in reg.get("folders", {}).items():
        print("  %s → %s" % (k, "不加入" if v.get("no") else v.get("project") + ("（上级 %s）" % v["parent"] if v.get("parent") else "")))
    print("小克：" + "、".join(sorted(p.get("name", "?") for p in projects().values())))


def main():
    global PORT
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="clawd", description="让 AI 助手把进度写进今日小克终未地")
    ap.add_argument("--project")
    ap.add_argument("--folder")
    ap.add_argument("--chat")
    common = argparse.ArgumentParser(add_help=False)  # 让 --project 这些写在命令后面也认
    for k in ("--project", "--folder", "--chat"):
        common.add_argument(k, default=argparse.SUPPRESS)
    sp = ap.add_subparsers(dest="cmd", required=True)
    _add = sp.add_parser
    sp.add_parser = lambda *x, **y: _add(*x, parents=[common], **y)
    sp.add_parser("hello")
    r = sp.add_parser("register"); r.add_argument("folder_arg"); r.add_argument("name", nargs="?"); r.add_argument("--parent"); r.add_argument("--no", action="store_true")
    t = sp.add_parser("todo"); t.add_argument("op", choices=["add", "done", "list"]); t.add_argument("text", nargs="?", default="")
    for k in ("where", "note", "prompt", "due"):
        t.add_argument("--" + k)
    t.add_argument("--urgent", action="store_true")
    w = sp.add_parser("wait"); w.add_argument("kind", choices=["ai", "reply", "test", "feedback", "decide", "clear"]); w.add_argument("text", nargs="?")
    n = sp.add_parser("note"); n.add_argument("text")
    l = sp.add_parser("latest"); l.add_argument("text")
    sp.add_parser("framework-done")
    pe = sp.add_parser("pet"); pe.add_argument("state"); pe.add_argument("say", nargs="?")
    f = sp.add_parser("feature"); f.add_argument("op", choices=["list", "on", "off"]); f.add_argument("names", nargs="*")
    ph = sp.add_parser("phone"); ph.add_argument("mode", choices=["auto", "manual"])
    ai = sp.add_parser("ai"); ai.add_argument("tool", choices=["codex", "claude", "none"])
    sp.add_parser("status")
    a = ap.parse_args()
    PORT = server_port()
    {"hello": cmd_hello, "register": cmd_register, "todo": cmd_todo, "wait": cmd_wait, "note": cmd_note,
     "latest": cmd_latest, "framework-done": cmd_framework, "pet": cmd_pet, "feature": cmd_feature,
     "phone": cmd_phone, "ai": cmd_ai, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
