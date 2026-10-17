#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clawdfield 本机小程序（今日小克终未地 · 开源版）
Clawdfield local server.

原创 / Original work: Miaomiao (GitHub: Miaomiaomeowmeow)
许可 / License: CC BY-NC-SA 4.0 — 不准商用；改了再发出去要署名、写清改了什么、用同样许可。见 LICENSE。
小克（Clawd）的原型是 Anthropic 的形象；这是粉丝作品，不是官方作品。

只用 Python 自带的功能，不用装任何东西。
- 把工作台网页开在 http://localhost:8765
- 数据存在 data/ 文件夹（每类东西一个 JSON 文件），别的程序改了文件，网页会自己刷新
- 网页里的 AI：借电脑上已登录的 Codex / Claude Code，或者用自己的 Key，或者不用
用法：python server.py [--port 8765] [--open] [--data 路径]
"""
import argparse
import datetime
import glob
import http.server
import json
import os
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = "clawdfield"
VERSION = "0.1.0"
NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,60}$")
ID_RE = re.compile(r"^(?!\.\.?$)[A-Za-z0-9_\-.~:@+]{1,200}$")
JSON_TIMEOUT = 180  # 一次 AI 最多等几秒
TONES = ("#6d6164", "#652062", "#7920e5", "#96b5e5", "#96b500")  # 描边备用色，和网页、桌宠里的一样
ORIGIN = "bWFkZSBieSDllrXllrU="  # 出处标记

# ---------------------------------------------------------------- 数据

class Store:
    """data/db/<集合>.json = {文档id: 文档}。写的时候先写临时文件再换掉，不会写坏。"""

    def __init__(self, data_dir):
        self.dir = os.path.join(data_dir, "db")
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.RLock()
        self.cache = {}   # 集合 -> (mtime_ns, dict)
        self.cond = threading.Condition()
        self.tick = 0
        self.changed = {}  # 集合 -> 第几次变的
        self.seen = {}     # 集合 -> mtime_ns（看文件有没有被别的程序改）
        for f in glob.glob(os.path.join(self.dir, "*.json")):
            self.seen[os.path.basename(f)[:-5]] = os.stat(f).st_mtime_ns

    def path(self, coll):
        return os.path.join(self.dir, coll + ".json")

    def read(self, coll):
        p = self.path(coll)
        with self.lock:
            try:
                mt = os.stat(p).st_mtime_ns
            except FileNotFoundError:
                return {}
            hit = self.cache.get(coll)
            if hit and hit[0] == mt:
                return hit[1]
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                if not isinstance(d, dict):
                    d = {}
            except (OSError, ValueError):
                d = hit[1] if hit else {}
            self.cache[coll] = (mt, d)
            return d

    def write(self, coll, d):
        p = self.path(coll)
        with self.lock:
            tmp = p + "." + secrets.token_hex(4) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
            mt = os.stat(p).st_mtime_ns
            self.cache[coll] = (mt, d)
            self.seen[coll] = mt
        self.notify(coll)

    def notify(self, coll):
        with self.cond:
            self.tick += 1
            self.changed[coll] = self.tick
            self.cond.notify_all()

    def watch(self):
        """别的程序（clawd 命令、AI 助手）直接改了 data/db 里的文件，也告诉网页。"""
        while True:
            time.sleep(1)
            try:
                now = {os.path.basename(f)[:-5]: os.stat(f).st_mtime_ns
                       for f in glob.glob(os.path.join(self.dir, "*.json"))}
            except OSError:
                continue
            for c, mt in now.items():
                if self.seen.get(c) != mt:
                    self.seen[c] = mt
                    self.notify(c)
            for c in list(self.seen):
                if c not in now:
                    del self.seen[c]
                    self.notify(c)

# ---------------------------------------------------------------- AI 设置

DEFAULT_CONFIG = {
    "source": "none",          # none 不用 / cli 借电脑上的 AI 助手 / api 用自己的 Key
    "cli": {"tool": "codex", "path": "", "command": ""},
    "api": {"kind": "anthropic", "vendor": "claude", "base": "", "key": "", "model": "", "smartModel": ""},
    "dailyLimit": 200,          # 一天最多调几次 AI（防止花太多钱 / 额度）
}

API_PRESETS = {
    # kind: (默认地址, 普通档默认模型, 聪明档默认模型)；模型都可以自己改
    "anthropic": ("https://api.anthropic.com", "claude-opus-5-5", "claude-opus-5-5"),
    "openai": ("https://api.openai.com/v1", "", ""),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta", "", ""),
}


class Config:
    def __init__(self, data_dir):
        self.file = os.path.join(data_dir, "config.json")
        self.usage_file = os.path.join(data_dir, "ai-usage.json")
        self.lock = threading.Lock()

    def load(self):
        try:
            with open(self.file, encoding="utf-8") as f:
                c = json.load(f)
        except (OSError, ValueError):
            c = {}
        out = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in c.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k].update(v)
            else:
                out[k] = v
        return out

    def save(self, c):
        with self.lock:
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(c, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.file)

    def public(self):
        """给网页看的版本：Key 只露最后 4 位。"""
        c = self.load()
        k = c["api"].get("key") or ""
        c["api"]["key"] = ""
        c["api"]["hasKey"] = bool(k)
        c["api"]["keyTail"] = k[-4:] if len(k) >= 8 else ""
        c["usedToday"] = self.used_today()
        return c

    def used_today(self):
        try:
            with open(self.usage_file, encoding="utf-8") as f:
                u = json.load(f)
            return u.get("n", 0) if u.get("date") == str(datetime.date.today()) else 0
        except (OSError, ValueError):
            return 0

    def count_one(self):
        with self.lock:
            n = self.used_today() + 1
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump({"date": str(datetime.date.today()), "n": n}, f)
            return n


class AIError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def find_cli(tool, path=""):
    if path and os.path.exists(path):
        return path
    exe = shutil.which(tool)
    if exe:
        return exe
    if tool == "codex" and os.name == "nt":
        # Codex 桌面版自带的命令行（没装 npm 版时）
        hits = sorted(glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe")),
                      key=os.path.getmtime, reverse=True)
        if hits:
            return hits[0]
    return ""


def detect_clis():
    return {t: bool(find_cli(t)) for t in ("codex", "claude")}


CLI_SLOTS = threading.Semaphore(2)  # 同时最多跑 2 个，别把电脑卡住


def ask_cli(cfg, prompt):
    cli = cfg["cli"]
    tool = cli.get("tool") or "codex"
    with CLI_SLOTS, tempfile.TemporaryDirectory(prefix="clawdfield-ai-") as work:
        if tool == "custom":
            cmd = (cli.get("command") or "").strip()
            if not cmd:
                raise AIError("not_granted", "还没填自定义命令")
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=work, shell=True, timeout=JSON_TIMEOUT)
            out = r.stdout
        else:
            exe = find_cli(tool, cli.get("path", ""))
            if not exe:
                raise AIError("not_granted", "电脑上没找到 %s 命令" % tool)
            if tool == "codex":
                last = os.path.join(work, "answer.txt")
                cmd = [exe, "exec", "--skip-git-repo-check", "-s", "read-only", "-C", work, "-o", last, "-"]
                r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", cwd=work, timeout=JSON_TIMEOUT)
                out = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else r.stdout
            elif tool == "claude":
                cmd = [exe, "-p", "--output-format", "text"]
                r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", cwd=work, timeout=JSON_TIMEOUT)
                out = r.stdout
            else:
                raise AIError("not_granted", "不认识的工具：%s" % tool)
        if r.returncode != 0 and not (out or "").strip():
            raise AIError("ai_failed", (r.stderr or "").strip()[-300:] or "命令出错了")
        return out


def post_json(url, body, headers):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=JSON_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")[:400]
        code = "bad_key" if e.code in (401, 403) else ("rate_limited" if e.code == 429 else "ai_failed")
        raise AIError(code, "HTTP %s：%s" % (e.code, txt))
    except urllib.error.URLError as e:
        raise AIError("offline", "连不上 AI：%s" % e.reason)


def ask_api(cfg, prompt, tier):
    a = cfg["api"]
    kind = a.get("kind") or "anthropic"
    base0, m0, s0 = API_PRESETS.get(kind, ("", "", ""))
    base = (a.get("base") or base0).rstrip("/")
    key = a.get("key") or ""
    model = (a.get("smartModel") if tier == "complex" else a.get("model")) or a.get("model") or (s0 if tier == "complex" else m0)
    if not key and kind != "openai":
        raise AIError("not_granted", "还没填 Key")
    if not model:
        raise AIError("not_granted", "还没填模型名字")
    if kind == "anthropic":
        body = {"model": model, "max_tokens": 16000,
                "messages": [{"role": "user", "content": prompt}],
                "output_config": {"effort": "medium" if tier == "complex" else "low"}}
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        if model.startswith(("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")):
            # 被安全检查误拦时，自动换一个合适的模型再试
            body["fallbacks"] = "default"
            headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
        j = post_json(base + "/v1/messages", body, headers)
        if j.get("stop_reason") == "refusal":
            raise AIError("refused", "AI 拒绝回答这一条")
        return "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
    if kind == "gemini":
        j = post_json("%s/models/%s:generateContent" % (base, urllib.parse.quote(model)),
                      {"contents": [{"parts": [{"text": prompt}]}]}, {"x-goog-api-key": key})
        parts = ((j.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)
    # 其余都按 OpenAI 的格式（OpenAI、DeepSeek、Kimi、通义、豆包、OpenRouter、本机 Ollama……）
    headers = {"Authorization": "Bearer " + key} if key else {}
    j = post_json(base + "/chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}]}, headers)
    return ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def pull_json(text):
    """从 AI 的回答里抠出 JSON（去掉 ```json 包装、前后的废话）。"""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if starts:
        s = min(starts)
        dec = json.JSONDecoder()
        try:
            return dec.raw_decode(t[s:])[0]
        except ValueError:
            pass
    raise AIError("bad_json", "AI 没按格式回答，再点一次试试")


JSON_TAIL = "\n\nReply with ONLY valid JSON (no explanation, no Markdown code fences)."


def ask_ai(config, prompt, tier="default", kind="json"):
    cfg = config.load()
    src = cfg.get("source")
    if src not in ("cli", "api"):
        raise AIError("not_granted", "还没接 AI")
    limit = int(cfg.get("dailyLimit") or 0)
    if limit and config.used_today() >= limit:
        raise AIError("limit", "今天的 AI 次数用完了（每天 %d 次，可以在设置里改）" % limit)
    config.count_one()
    full = prompt + (JSON_TAIL if kind == "json" else "")
    text = ask_cli(cfg, full) if src == "cli" else ask_api(cfg, full, tier)
    return pull_json(text) if kind == "json" else text

# ---------------------------------------------------------------- 网页服务

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Clawdfield/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("CLAWDFIELD_LOG"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # 只认本机来的，挡住别的网站偷偷改数据
    def host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        return host in ("localhost", "127.0.0.1", "::1") or host in self.server.extra_hosts

    def send(self, code, obj=None, ctype="application/json; charset=utf-8", raw=None, cache=False):
        body = raw if raw is not None else (b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def fail(self, code, err, msg=""):
        self.send(code, {"code": err, "message": msg or err})

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20 * 1024 * 1024:
            raise ValueError("too big")
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw.decode("utf-8")) if raw else None

    def file(self, name, ctype):
        p = os.path.join(ROOT, name)
        try:
            with open(p, "rb") as f:
                self.send(200, raw=f.read(), ctype=ctype)
        except OSError:
            self.fail(404, "not_found")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.host_ok():
            return self.fail(403, "bad_host")
        u = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(x) for x in u.path.split("/") if x]
        st = self.server.store
        if not parts or parts == ["index.html"] or parts == ["workbench.html"]:
            return self.file("workbench.html", "text/html; charset=utf-8")
        if parts == ["setup"] or parts == ["setup.html"]:
            return self.file("setup.html", "text/html; charset=utf-8")
        if parts == ["api", "ping"]:
            return self.send(200, {"app": APP, "version": VERSION})
        if parts == ["api", "events"]:
            return self.events()
        if parts[:2] == ["api", "db"] and len(parts) in (3, 4):
            coll = parts[2]
            if not NAME_RE.match(coll):
                return self.fail(400, "bad_name")
            d = st.read(coll)
            if len(parts) == 3:
                return self.send(200, {"docs": [{"id": k, "data": v} for k, v in d.items()]})
            did = parts[3]
            return self.send(200, {"exists": did in d, "data": d.get(did)})
        if parts[:2] == ["api", "ai"] and len(parts) == 3 and parts[2] == "config":
            c = self.server.config.public()
            c["found"] = detect_clis()
            return self.send(200, c)
        if parts[0] == "_blob" and len(parts) == 2 and ID_RE.match(parts[1]):
            hits = glob.glob(os.path.join(self.server.blobs, glob.escape(parts[1]) + ".*"))
            if hits:
                ext = os.path.splitext(hits[0])[1].lower()
                ct = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                      ".webp": "image/webp", ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
                with open(hits[0], "rb") as f:
                    return self.send(200, raw=f.read(), ctype=ct, cache=True)
            return self.fail(404, "not_found")
        if len(parts) == 1 and parts[0] in ("favicon.ico",):
            return self.file(os.path.join("pet", "clawd.ico"), "image/x-icon")
        return self.fail(404, "not_found")

    def events(self):
        """网页一直连着这里；数据一变就告诉它哪几类变了。"""
        st = self.server.store
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.close_connection = True
        with st.cond:
            mine = st.tick
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                with st.cond:
                    st.cond.wait_for(lambda: st.tick > mine, timeout=15)
                    new = [c for c, t in st.changed.items() if t > mine]
                    mine = st.tick
                msg = ("data: " + json.dumps({"c": new}) + "\n\n") if new else ": ping\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
        except (OSError, ValueError):
            return

    def write_ok(self):
        if not self.host_ok():
            self.fail(403, "bad_host")
            return False
        if self.headers.get("X-Clawdfield") != "1":
            self.fail(403, "bad_origin")
            return False
        return True

    def do_PUT(self):
        self.change("set")

    def do_PATCH(self):
        self.change("update")

    def do_DELETE(self):
        self.change("delete")

    def change(self, op):
        if not self.write_ok():
            return
        parts = [urllib.parse.unquote(x) for x in urllib.parse.urlsplit(self.path).path.split("/") if x]
        if parts[:2] != ["api", "db"] or len(parts) != 4 or not NAME_RE.match(parts[2]) or not ID_RE.match(parts[3]):
            return self.fail(400, "bad_path")
        coll, did = parts[2], parts[3]
        try:
            doc = self.body() if op != "delete" else None
        except ValueError:
            return self.fail(400, "bad_json")
        if op != "delete" and not isinstance(doc, dict):
            return self.fail(400, "bad_doc")
        st = self.server.store
        with st.lock:
            d = dict(st.read(coll))
            if op == "set":
                d[did] = doc
            elif op == "update":
                cur = dict(d.get(did) or {})
                cur.update(doc)
                d[did] = cur
            else:
                d.pop(did, None)
            if coll == "settings" and did == "general" and did in d and "_o" not in d[did]:
                d[did]["_o"] = ORIGIN
            st.write(coll, d)
        self.send(200, {"ok": True})

    def do_POST(self):
        if not self.write_ok():
            return
        parts = [x for x in urllib.parse.urlsplit(self.path).path.split("/") if x]
        try:
            b = self.body() or {}
        except ValueError:
            return self.fail(400, "bad_json")
        cfg = self.server.config
        if parts == ["api", "ai"]:
            try:
                val = ask_ai(cfg, str(b.get("prompt") or ""), b.get("tier") or "default", b.get("kind") or "json")
                return self.send(200, {"ok": True, "value": val})
            except AIError as e:
                return self.fail(403 if e.code in ("not_granted", "limit") else 502, e.code, e.message)
            except subprocess.TimeoutExpired:
                return self.fail(504, "timeout", "AI 太久没回答")
            except Exception as e:  # 别让一次出错把小程序弄挂
                return self.fail(500, "ai_failed", str(e)[:300])
        if parts == ["api", "ai", "config"]:
            c = cfg.load()
            for sec in ("cli", "api"):
                if isinstance(b.get(sec), dict):
                    new = {k: v for k, v in b[sec].items() if k in DEFAULT_CONFIG[sec] and isinstance(v, str)}
                    if sec == "api" and not new.get("key"):
                        new.pop("key", None)  # 没重新填 Key 就保留原来的
                    c[sec].update(new)
            if b.get("source") in ("none", "cli", "api"):
                c["source"] = b["source"]
            if isinstance(b.get("dailyLimit"), int) and 0 <= b["dailyLimit"] <= 100000:
                c["dailyLimit"] = b["dailyLimit"]
            if b.get("clearKey"):
                c["api"]["key"] = ""
            cfg.save(c)
            return self.send(200, {"ok": True})
        if parts == ["api", "ai", "test"]:
            t0 = time.time()
            try:
                v = ask_ai(cfg, 'Say hello to the user in Chinese in a few words. Return {"hi": "..."}', "default", "json")
                return self.send(200, {"ok": True, "value": v, "seconds": round(time.time() - t0, 1)})
            except AIError as e:
                return self.send(200, {"ok": False, "code": e.code, "message": e.message})
            except subprocess.TimeoutExpired:
                return self.send(200, {"ok": False, "code": "timeout", "message": "AI 太久没回答"})
            except Exception as e:
                return self.send(200, {"ok": False, "code": "ai_failed", "message": str(e)[:300]})
        return self.fail(404, "not_found")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def already_running(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Clawdfield 本机小程序")
    ap.add_argument("--port", type=int, default=int(os.environ.get("CLAWDFIELD_PORT", "8765")))
    ap.add_argument("--data", default=os.environ.get("CLAWDFIELD_DATA", os.path.join(ROOT, "data")))
    ap.add_argument("--open", action="store_true", help="开好以后打开浏览器")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if already_running(a.port):
        print("已经开着了：http://localhost:%d" % a.port)
        if a.open:
            webbrowser.open("http://localhost:%d/" % a.port)
        return

    os.makedirs(a.data, exist_ok=True)
    store = Store(a.data)
    srv = None
    for port in range(a.port, a.port + 10):
        try:
            srv = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if not srv:
        print("端口 %d～%d 都被占用了，用 --port 换一个" % (a.port, a.port + 9))
        sys.exit(1)
    srv.store = store
    srv.config = Config(a.data)
    srv.blobs = os.path.join(a.data, "blobs")
    srv.extra_hosts = set()
    os.makedirs(srv.blobs, exist_ok=True)
    threading.Thread(target=store.watch, daemon=True).start()
    url = "http://localhost:%d/" % srv.server_address[1]
    try:  # 告诉 clawd 命令现在开在哪个端口
        with open(os.path.join(a.data, "server.json"), "w", encoding="utf-8") as f:
            json.dump({"port": srv.server_address[1], "pid": os.getpid()}, f)
    except OSError:
        pass
    print("今日小克终未地 已经开好：%s" % url)
    print("数据存在：%s" % os.path.abspath(a.data))
    print("关掉这个窗口 = 关掉工作台（数据不会丢）")
    if a.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
