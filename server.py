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
    "configs": [],              # 存起来的几套（服务商 + 地址 + Key + 模型），换服务商一点就换
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
        if not isinstance(out.get("configs"), list):
            out["configs"] = []
        return out

    def save(self, c):
        with self.lock:
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(c, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.file)

    def public(self):
        """给网页看的版本：Key 只露最后 4 位（存的几套配置也一样）。"""
        c = self.load()
        for a in [c["api"]] + c["configs"]:
            k = a.get("key") or ""
            a["key"] = ""
            a["hasKey"] = bool(k)
            a["keyTail"] = k[-4:] if len(k) >= 8 else ""
        u = self.usage()
        c["usedToday"], c["tokensToday"] = u["n"], u["tin"] + u["tout"]
        return c

    def usage(self):
        try:
            with open(self.usage_file, encoding="utf-8") as f:
                u = json.load(f)
        except (OSError, ValueError):
            u = {}
        if u.get("date") != str(datetime.date.today()):
            u = {}
        return {"date": str(datetime.date.today()), "n": u.get("n", 0), "tin": u.get("tin", 0), "tout": u.get("tout", 0)}

    def used_today(self):
        return self.usage()["n"]

    def _bump(self, n=0, tin=0, tout=0):
        with self.lock:
            u = self.usage()
            u["n"] += n
            u["tin"] += int(tin or 0)
            u["tout"] += int(tout or 0)
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(u, f)
            return u

    def count_one(self):
        return self._bump(n=1)["n"]

    def add_tokens(self, tin, tout):
        self._bump(tin=tin, tout=tout)


class AIError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


# 出错说人话（照技能 ai-connect 第六节）
SAY = {
    "not_granted": "还没接上 AI：去设置里选一种",
    "auth": "Key 不对，或者已经失效了：重新粘贴一次",
    "money": "这个 Key 的余额用完了（或者还没开通付费），去服务商那边充值后再试",
    "perm": "这个模型现在用不了（没权限，或者你所在的地区不能用）：换一个模型试试",
    "model": "找不到这个模型：点「拉取模型列表」重新选一个",
    "rate": "说得太快了，服务商让歇一会儿，过一分钟再试",
    "timeout": "等太久没回音：再试一次，或者换个快一点的模型",
    "server": "服务商那边出错了，等一下再试",
    "network": "连不上服务商：看看网络，或者地址填得对不对",
    "bad": "请求被拒绝了（多半是模型名不对，或者这个模型不支持某个设置）",
    "refused": "AI 这次不肯回答，换个说法试试",
    "bad_json": "AI 没按格式回答，再点一次试试",
    "limit": "今天的 AI 次数用完了，可以在设置里改",
}


def say(code, detail="", status=None, model=""):
    tail = []
    if status:
        tail.append("错误代码 %s" % status)
    if detail:
        tail.append(str(detail)[:140])
    if model:
        tail.append("模型：%s" % model)
    return SAY.get(code, "出错了") + ("（%s）" % "；".join(tail) if tail else "")


def human_http(status, txt, model=""):
    low = (txt or "").lower()
    try:
        j = json.loads(txt)
        msg = ((j.get("error") or {}) if isinstance(j.get("error"), dict) else {}).get("message") or j.get("message") or str(j.get("error") or "")
    except (ValueError, AttributeError):
        msg = txt
    if status == 401:
        code = "auth"
    elif status == 402 or re.search(r"insufficient|quota|balance|credit|billing|余额", low):
        code = "money"
    elif status == 403:
        code = "perm"
    elif status == 404:
        code = "model"
    elif status == 429:
        code = "rate"
    elif status in (408, 504):
        code = "timeout"
    elif status >= 500:
        code = "server"
    else:
        code = "bad"
    return AIError(code, say(code, msg, status, model))


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
                raise AIError("not_granted", "电脑上没找到 %s 命令：装好并登录后再试，或者换一种" % tool)
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
            err = (r.stderr or "").strip()[-200:]
            if re.search(r"log ?in|login|auth|登录", err, re.I):
                raise AIError("auth", "%s 好像没登录：先在它自己那边登录一次（%s）" % (tool, err[-80:]))
            raise AIError("server", "%s 出错了（%s）" % (tool, err or "没有说原因"))
        return out


def http_json(method, url, body=None, headers=None, model="", timeout=JSON_TIMEOUT):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise human_http(e.code, e.read().decode("utf-8", "replace")[:600], model)
    except urllib.error.URLError as e:
        if "timed out" in str(e.reason):
            raise AIError("timeout", say("timeout", "", None, model))
        raise AIError("network", say("network", e.reason))
    except TimeoutError:
        raise AIError("timeout", say("timeout", "", None, model))
    except ValueError:
        raise AIError("bad", say("bad", "服务商回的不是 JSON，地址可能填错了"))


def api_parts(a):
    kind = a.get("kind") or "anthropic"
    base0, m0, s0 = API_PRESETS.get(kind, ("", "", ""))
    return kind, (a.get("base") or base0).rstrip("/"), a.get("key") or "", m0, s0


def list_models(a):
    """填好地址和 Key 后，拉出这个服务商有哪些模型"""
    kind, base, key, _, _ = api_parts(a)
    if not key and kind != "openai":
        raise AIError("not_granted", "先填 Key 再拉取")
    if kind == "anthropic":
        j = http_json("GET", base + "/v1/models?limit=1000", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=20)
        return sorted(m.get("id") for m in j.get("data", []) if m.get("id"))
    if kind == "gemini":
        j = http_json("GET", base + "/models?pageSize=1000", headers={"x-goog-api-key": key}, timeout=20)
        return sorted(m["name"].split("/", 1)[-1] for m in j.get("models", [])
                      if m.get("name") and "generateContent" in (m.get("supportedGenerationMethods") or ["generateContent"]))
    j = http_json("GET", base + "/models", headers={"Authorization": "Bearer " + key} if key else {}, timeout=20)
    return sorted(m.get("id") for m in (j.get("data") or j.get("models") or []) if isinstance(m, dict) and m.get("id"))


def ask_api(cfg, prompt, tier, config=None):
    a = cfg["api"]
    kind, base, key, m0, s0 = api_parts(a)
    model = (a.get("smartModel") if tier == "complex" else a.get("model")) or a.get("model") or (s0 if tier == "complex" else m0)
    if not key and kind != "openai":
        raise AIError("not_granted", "还没填 Key")
    if not model:
        raise AIError("not_granted", "还没选模型：点「拉取模型列表」选一个")
    tin = tout = 0
    if kind == "anthropic":
        body = {"model": model, "max_tokens": 16000,
                "messages": [{"role": "user", "content": prompt}]}
        if re.match(r"claude-(opus|sonnet|haiku|fable)-5", model):
            body["output_config"] = {"effort": "medium" if tier == "complex" else "low"}
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        if re.match(r"claude-(opus-5|fable-5-1|sonnet-5-5)", model):
            # 被安全检查误拦时，自动换一个合适的模型再试
            body["fallbacks"] = "default"
            headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
        j = http_json("POST", base + "/v1/messages", body, headers, model)
        u = j.get("usage") or {}
        tin, tout = u.get("input_tokens", 0), u.get("output_tokens", 0)
        if j.get("stop_reason") == "refusal":
            raise AIError("refused", say("refused", "", None, model))
        text = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
    elif kind == "gemini":
        j = http_json("POST", "%s/models/%s:generateContent" % (base, urllib.parse.quote(model)),
                      {"contents": [{"parts": [{"text": prompt}]}]}, {"x-goog-api-key": key}, model)
        u = j.get("usageMetadata") or {}
        tin, tout = u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)
        parts = ((j.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
    else:
        # 其余都按 OpenAI 的格式（OpenAI、DeepSeek、Kimi、通义、豆包、OpenRouter、本机 Ollama……）
        headers = {"Authorization": "Bearer " + key} if key else {}
        j = http_json("POST", base + "/chat/completions", {"model": model, "messages": [{"role": "user", "content": prompt}]}, headers, model)
        u = j.get("usage") or {}
        tin, tout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        text = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if config:
        config.add_tokens(tin, tout)
    return text


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
        raise AIError("limit", say("limit", "每天 %d 次" % limit))
    config.count_one()
    full = prompt + (JSON_TAIL if kind == "json" else "")
    text = ask_cli(cfg, full) if src == "cli" else ask_api(cfg, full, tier, config)
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
            return self.file(os.path.join("assets", "clawd.ico"), "image/x-icon")
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
        if parts == ["api", "ai", "models"]:
            a = cfg.load()["api"]
            q = {k: v for k, v in b.items() if k in ("kind", "base", "key") and isinstance(v, str)}
            if not q.get("key") and q.get("kind", a.get("kind")) == a.get("kind"):
                q["key"] = a.get("key") or ""  # 没重新填 Key 就用存着的那把
            try:
                return self.send(200, {"ok": True, "models": list_models({**a, **q})})
            except AIError as e:
                return self.send(200, {"ok": False, "code": e.code, "message": e.message})
        if parts == ["api", "ai", "configs"]:
            c = cfg.load()
            op, sets = b.get("op"), c["configs"]
            if op == "save":
                name = str(b.get("name") or "").strip()[:20]
                if not name:
                    n = len(sets) + 1
                    while any(x.get("name") == "配置 %d" % n for x in sets):
                        n += 1
                    name = "配置 %d" % n
                old = next((x for x in sets if x.get("name") == name), None)
                item = {"id": old["id"] if old else secrets.token_hex(4), "name": name, **{k: c["api"].get(k, "") for k in DEFAULT_CONFIG["api"]}}
                sets = [item if x is old else x for x in sets] if old else sets + [item]
                c["configs"], c["cfg"] = sets, item["id"]
            elif op == "use":
                item = next((x for x in sets if x.get("id") == b.get("id")), None)
                if not item:
                    return self.fail(404, "not_found", "这套配置找不到了")
                c["api"] = {k: item.get(k, "") for k in DEFAULT_CONFIG["api"]}
                c["source"], c["cfg"] = "api", item["id"]
            elif op == "delete":
                c["configs"] = [x for x in sets if x.get("id") != b.get("id")]
                if c.get("cfg") == b.get("id"):
                    c["cfg"] = ""
            else:
                return self.fail(400, "bad_op")
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


def seed_sample(data_dir):
    """第一次打开（data/db 里还没有任何东西、也没人清空过）：把 sample/db 里的 11 只示例小克复制进去。
    First start: copy the sample Clawds from sample/db so the page is not empty. Returns True if it did."""
    db = os.path.join(data_dir, "db")
    src = os.path.join(ROOT, "sample", "db")
    if os.path.exists(os.path.join(data_dir, "fresh")):  # 用户跑过 clawd.py fresh：要空白的
        return False
    if glob.glob(os.path.join(db, "*.json")) or not os.path.isdir(src):
        return False
    os.makedirs(db, exist_ok=True)
    for f in glob.glob(os.path.join(src, "*.json")):
        shutil.copy(f, os.path.join(db, os.path.basename(f)))
    return True


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
    if seed_sample(a.data):
        print("第一次打开：先放了 11 只示例小克进去看看效果（想清空：python clawd.py fresh）")
        print("First start: loaded 11 sample Clawds so you can see how it works (python clawd.py fresh to start clean)")
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
    try:  # 名片：告诉小克桌宠（clawd-pet）工作台装在哪、网址是什么，单击桌宠就能打开 / 帮忙开起来
        cards = os.environ.get("CLAWD_CARDS") or os.path.join(os.path.expanduser("~"), ".clawd")
        os.makedirs(cards, exist_ok=True)
        with open(os.path.join(cards, "workbench.json"), "w", encoding="utf-8") as f:
            json.dump({"app": APP, "version": VERSION, "dir": ROOT, "url": url, "at": int(time.time())}, f, ensure_ascii=False)
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
