/* 今日小克终未地 · 本机转接层（Clawdfield local adapter）
   原创 / Original work: Miaomiao (GitHub: Miaomiaomeowmeow) · CC BY-NC-SA 4.0
   在 claude.ai 上打开：什么都不做，照旧用 claude.ai 的数据库和 AI。
   在自己电脑上打开（server.py 开的 localhost）：假装成 claude.ai 的样子，把数据存到本机 data/，AI 交给 server.py 转发。
   网页本体一行不用改：它照旧调用 window.claude.use("db") / use("sample")。 */
(function () {
  if (window.claude && window.claude.use) return;
  var h = location.hostname;
  var local = location.protocol === "http:" && (h === "localhost" || h === "127.0.0.1" || h === "[::1]" ||
    /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(h));
  if (!local) return;
  var H = { "Content-Type": "application/json", "X-Clawdfield": "1" };
  var enc = encodeURIComponent;
  var ABC = "abcdefghijklmnopqrstuvwxyz0123456789";
  function rid() { var s = ""; for (var i = 0; i < 20; i++) s += ABC[Math.floor(Math.random() * 36)]; return s; }
  function err(code, msg) { var e = new Error(msg || code); e.code = code; return e; }
  function req(method, url, body) {
    return fetch(url, { method: method, headers: H, body: body === undefined ? undefined : JSON.stringify(body) })
      .then(function (r) {
        if (r.ok) return r.json();
        return r.json().catch(function () { return {}; }).then(function (j) { throw err(j.code || ("http_" + r.status), j.message); });
      }, function () { throw err("offline", "本机小程序没开：请双击 start.bat"); });
  }
  function snapOf(docs) {
    return { docs: docs.map(function (d) { return { id: d.id, data: function () { return d.data; } }; }), size: docs.length, empty: !docs.length };
  }
  var subs = {}, es = null;
  function refresh(c) {
    var L = subs[c]; if (!L || !L.length) return;
    req("GET", "/api/db/" + enc(c)).then(function (j) {
      var s = snapOf(j.docs); L.slice().forEach(function (x) { x.ok(s); });
    }, function (e) { L.slice().forEach(function (x) { if (x.bad) x.bad(e); }); });
  }
  function ensureES() {
    if (es) return;
    es = new EventSource("/api/events");
    es.onmessage = function (e) { var m; try { m = JSON.parse(e.data); } catch (x) { return; } (m.c || []).forEach(refresh); };
    es.onopen = function () { Object.keys(subs).forEach(refresh); };  // 断线重连后补一次
  }
  function doc(c, id) {
    id = id || rid();
    var u = "/api/db/" + enc(c) + "/" + enc(id);
    return {
      id: id,
      set: function (d) { return req("PUT", u, d).then(function () {}); },
      update: function (d) { return req("PATCH", u, d).then(function () {}); },
      "delete": function () { return req("DELETE", u).then(function () {}); },
      get: function () { return req("GET", u).then(function (j) { return { id: id, exists: j.exists, data: function () { return j.data; } }; }); }
    };
  }
  function collection(c) {
    return {
      doc: function (id) { return doc(c, id); },
      get: function () { return req("GET", "/api/db/" + enc(c)).then(function (j) { return snapOf(j.docs); }); },
      onSnapshot: function (ok, bad) {
        (subs[c] = subs[c] || []).push({ ok: ok, bad: bad }); ensureES(); refresh(c);
        return function () { subs[c] = (subs[c] || []).filter(function (x) { return x.ok !== ok; }); };
      }
    };
  }
  var db = { collection: collection };
  var sample = {
    json: function (prompt, opts) {
      opts = opts || {};
      return req("POST", "/api/ai", { prompt: String(prompt), tier: opts.modelTier || "default", kind: "json" })
        .then(function (j) { return j.value; });
    }
  };
  window.claude = {
    local: true,
    use: function (name) {
      if (name === "db") return Promise.resolve(db);
      if (name === "sample") return Promise.resolve(sample);
      return Promise.reject(err("not_supported"));
    }
  };
})();
