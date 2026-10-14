# -*- coding: utf-8 -*-
"""GUI 登录回填专项验证（方式二核心要求）：
模拟平台登录页(本地 HTTP)，跑真实的 _run_gui_login_loop ——
    页面预填(空) → 験证码图推 GUI → 用户点「登录」→ 回填 账号/密码/验证码 → 点击登录按钮
用法: python _verify_login_fill.py   退出码 0 = 通过。

线程模型（与生产 _browser_flow 一致，Playwright 对象严禁跨线程）：
    worker 线程：创建 Playwright + page，调用 _run_gui_login_loop（阻塞）
    主线程：只通过线程安全队列收验证码图 / 发登录提交 / 收登录结果
"""
import base64
import json
import os
import queue
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PASS, FAIL = [], []


def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (("  <- " + str(detail)) if (detail and not cond) else ""))


# ---- 本地模拟登录页（与平台同结构: #userName/#password/#captcha/验证码img/登录按钮） ----
# 服务端强校验：只有 账号=u123 密码=p456 非空验证码 才放行到 /home
LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Login</title></head>
<body>
<img id="cap" alt="验证码图片" src="/captcha.png" width="120" height="40">
<input id="userName" type="text"><input id="password" type="password">
<input id="captcha" type="text"><button id="btn">登录</button>
<script>
document.getElementById('btn').onclick = function () {
  var u = document.getElementById('userName').value;
  var p = document.getElementById('password').value;
  var c = document.getElementById('captcha').value;
  if (u === 'u123' && p === 'p456' && c.length > 0) { location.href = '/home'; }
};
</script></body></html>"""

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4"
    "z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/login"):
            body = LOGIN_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif self.path.startswith("/captcha"):
            body = PNG_1PX
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
        else:
            body = b"<html><body>home-ok</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = HTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
home_url = "http://127.0.0.1:%d/login" % port

# 切到临时目录跑（绝不覆盖项目里真实的 credentials.local.json / auth.json）
tmp = tempfile.mkdtemp(prefix="cc_loginfill_")
os.chdir(tmp)

import course_companion as cc          # noqa: E402
import course_companion_login as L      # noqa: E402

cred = {"account": "", "password": "", "home_url": home_url,
        "store_url": home_url}  # 模拟首次运行：本地无凭据

result = {}
started = threading.Event()


def worker():
    """所有 Playwright 操作都在本线程（与生产 _browser_flow 同构）。"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 900, "height": 700})
            page = ctx.new_page()
            page.goto(home_url, wait_until="domcontentloaded")
            started.set()
            # 阻塞跑登录循环：预填(空) → 推验证码 → 等 _SUBMIT → 回填+点击
            L._run_gui_login_loop(page, ctx, cred, threading.Event())
            # 登录成功返回后记录页面终态（仍在本线程，安全）
            result["url"] = page.url
            result["left_login"] = "login" not in page.url
            try:
                result["body"] = page.inner_text("body", timeout=3000)
            except Exception:
                result["body"] = ""
            browser.close()
            result["loop_done"] = True
    except Exception as e:
        result["err"] = str(e)[:200]
        started.set()


t = threading.Thread(target=worker, daemon=True)
t.start()
started.wait(30)

# ① 验证码图应被推到 GUI（模拟 GUI 接收；push 发生在预填之后）
try:
    b64 = L._CAPTCHA_B64.get(timeout=30)
    ck("验证码图推送到 GUI", bool(b64) and not b64.startswith("__ERR__"),
       b64[:60] if b64 else "超时")
    ck("验证码图可解码为 PNG",
       bool(b64) and not b64.startswith("__")
       and base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n")
except queue.Empty:
    ck("验证码图推送到 GUI", False, "30s 超时")

# ② 静态断言：提交时必须回填 账号/密码/验证码 三项（首登 prefill 为空）
src = open(
    r"D:\广州城建职业学院\人培方案\course-companion\course_companion_login.py",
    encoding="utf-8").read()
seg = src[src.find("account, password, code = submitted"):]
seg = seg[:seg.find("def _push_captcha_to_gui")] if "def _push_captcha_to_gui" in seg else seg
ck("提交登录时回填 #userName", 'page.fill("#userName", account)' in seg)
ck("提交登录时回填 #password", 'page.fill("#password", password)' in seg)
ck("提交登录时回填 #captcha", 'page.fill("#captcha", code)' in seg)

# ③ 模拟用户在 GUI 输入完点「登录」（只发队列，不碰 page）
L._SUBMIT.put(("u123", "p456", "8391"))

# ④ 等登录结果（服务端强校验：三项全对才放行）
try:
    ok = L._LOGIN_RESULT.get(timeout=60)
except queue.Empty:
    ok = None
ck("一次点击登录成功(_LOGIN_RESULT=True)", ok is True, "got=%r" % (ok,))
t.join(timeout=20)
ck("页面已离开登录页", result.get("left_login") is True, result.get("url", result.get("err", "")))
ck("工作线程正常收尾", result.get("loop_done") is True, result.get("err", ""))
ck("凭据 dict 已回填", cred["account"] == "u123" and cred["password"] == "p456")
try:
    with open(cc.CRED_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    ck("credentials.local.json 已保存",
       saved.get("account") == base64.b64encode(b"u123").decode())
except Exception as e:
    ck("credentials.local.json 已保存", False, e)
ck("auth.json 会话已保存", os.path.exists(cc.AUTH_STATE))

srv.shutdown()
os.chdir(r"D:\广州城建职业学院\人培方案\course-companion")
print("\n== 登录回填验证: %d/%d 通过 ==" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项:", FAIL)
    sys.exit(1)
print("login-fill OK")
