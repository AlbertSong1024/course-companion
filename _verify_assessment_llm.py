# -*- coding: utf-8 -*-
r"""考核「必须 LLM 作答」全链路实测（本地 mock 考核页 + mock OpenAI 服务）。
三个场景：
  S1 未配置 LLM → 不作答、不交卷、日志明确提示（等待超时返回 False）
  S2 等待期间补配 LLM → 轮询检测到 → 自动接管 → 实时抓题作答 → 交卷成功
  S3 已配置 LLM   → 全程「考核页实时抓取」题面 → 逐题作答 → 交卷
用法: python _verify_assessment_llm.py   退出码 0 = 全部通过。
所有文件写在临时目录，绝不碰项目里的 answers.json / llm.local.json。
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PROJ = r"D:\广州城建职业学院\人培方案\course-companion"
sys.path.insert(0, PROJ)

PASS, FAIL = [], []


def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name
          + (("  <- " + str(detail)) if (detail and not cond) else ""))


# ---- mock 考核页（结构对齐平台：#testForm / #topicList .m-topic-item /
#      .topic-title / label>input[value] / strong.on 计数 / submitTest/finishTest）
ASSESS_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>考核</title></head>
<body>
<div class="g-study-prompt" style="display:none"></div>
<div id="testForm">
  <div id="topicList">
    <div class="m-topic-item">
      <div class="topic-title">1、 [单选题] 一加一等于几？</div>
      <label><strong>A</strong><input type="radio" name="r1" value="Choice0">一</label>
      <label><strong>B</strong><input type="radio" name="r1" value="Choice1">二</label>
      <label><strong>C</strong><input type="radio" name="r1" value="Choice2">三</label>
    </div>
    <div class="m-topic-item">
      <div class="topic-title">2、 [多选题] 下列哪些是偶数？</div>
      <label><strong>A</strong><input type="checkbox" name="r2" value="Choice0">1</label>
      <label><strong>B</strong><input type="checkbox" name="r2" value="Choice1">2</label>
      <label><strong>C</strong><input type="checkbox" name="r2" value="Choice2">4</label>
    </div>
    <div class="m-topic-item">
      <div class="topic-title">3、 [判断题] 地球是圆的。</div>
      <label><strong>A</strong><input type="radio" name="r3" value="Correct">正确</label>
      <label><strong>B</strong><input type="radio" name="r3" value="Incorrect">错误</label>
    </div>
  </div>
  <button onclick="submitTest()">提交</button>
</div>
<a href="/progress" id="toProgress">学习进度</a>
<script>
document.addEventListener('change', function (e) {
  var t = e.target;
  if (!t.matches || !t.matches('input[value]')) return;
  var lab = t.closest('label'); if (!lab) return;
  var s = lab.querySelector('strong'); if (!s) return;
  s.classList.toggle('on', !!t.checked);
});
function submitTest() {}
function finishTest() {
  var f = document.getElementById('testForm');
  if (f) f.parentNode.removeChild(f);
  var p = document.querySelector('.g-study-prompt');
  p.textContent = '您已完成'; p.style.display = 'block';
}
</script></body></html>"""

PROGRESS_HTML = ("<html><body>完成 3/3 项活动，学习进度 100%，"
                 "考核成绩： 88 分</body></html>")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/exam"):
            body, ctype = ASSESS_HTML.encode(), "text/html; charset=utf-8"
        else:
            body, ctype = PROGRESS_HTML.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode("utf-8", "replace")
        try:
            content = json.loads(raw)["messages"][1]["content"]
        except Exception:
            content = ""
        # 按题干关键词给确定答案（真实链路仍走完整 prompt 构造/解析）
        if "一加一等于几" in content:
            ans = "[2]"              # → Choice1
        elif "偶数" in content:
            ans = "[1, 2]"           # → Choice0, Choice1
        elif "地球" in content:
            ans = "[1]"              # → Correct
        else:
            ans = "[1]"
        body = json.dumps(
            {"choices": [{"message": {"content": ans}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = HTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % port

# 临时目录：answers.json / llm.local.json 全写这里
tmp = tempfile.mkdtemp(prefix="cc_assess_")
os.chdir(tmp)

import course_companion as cc   # noqa: E402

LOGS = []


def cap_log(msg):
    line = str(msg)
    LOGS.append(line)
    print("  >", line[:110])


cc.log = cap_log


def write_llm_cfg():
    with open("llm.local.json", "w", encoding="utf-8") as f:
        json.dump({"base_url": base, "api_key": "sk-test",
                   "model": "mock"}, f)


def write_llm_cfg_later(sec):
    def go():
        time.sleep(sec)
        write_llm_cfg()
    threading.Thread(target=go, daemon=True).start()


from playwright.sync_api import sync_playwright   # noqa: E402

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_context().new_page()

    # ================= S1: 未配置 LLM → 拦截不作答 =================
    print("\n--- S1 未配置 LLM ---")
    if os.path.exists("llm.local.json"):
        os.remove("llm.local.json")
    LOGS.clear()
    cc.ASSESS_WAIT_SECONDS = 6
    cc.MANUAL_POLL_SECONDS = 1
    page.goto(base + "/exam", wait_until="domcontentloaded")
    ret = cc.handle_assessment(page)
    blob = "\n".join(LOGS)
    ck("S1 返回 False(未交卷)", ret is False, ret)
    ck("S1 考核页仍在(未交卷)", page.locator("#testForm").count() > 0)
    ck("S1 日志明示不作答不交卷", "不作答、不交卷" in blob)
    ck("S1 日志指引去 LLM 设置", "LLM 设置" in blob)
    ck("S1 无任何选项被勾选",
       page.locator("#topicList input:checked").count() == 0)
    ck("S1 未写 answers.json", not os.path.exists("answers.json"))

    # ================= S2: 等待期间补配 LLM → 自动接管 =================
    print("\n--- S2 等待中补配 LLM → 自动接管 ---")
    if os.path.exists("answers.json"):
        os.remove("answers.json")
    LOGS.clear()
    cc.ASSESS_WAIT_SECONDS = 45
    cc.MANUAL_POLL_SECONDS = 1
    write_llm_cfg_later(3)  # 等待开始 3 秒后才保存 LLM 配置
    page.goto(base + "/exam", wait_until="domcontentloaded")
    ret = cc.handle_assessment(page)
    blob = "\n".join(LOGS)
    ck("S2 检测到配置后自动接管", "自动接管" in blob)
    ck("S2 题面来自考核页实时抓取", "考核页实时抓取" in blob, blob[:400])
    ck("S2 未回退本地题库", "回退本地题库" not in blob)
    ck("S2 交卷成功(返回 True)", ret is True, ret)
    ck("S2 考核页已消失(已交卷)", page.locator("#testForm").count() == 0)
    # 交卷后 #testForm 已被移除，选中状态改从作答日志断言（逐题 "已选 … OK"）
    ck("S2 第1题选中 Choice1", "第  1 题 已选 Choice1 → 1/1 OK" in blob, blob[-400:])
    ck("S2 第2题选中 Choice0+Choice1",
       "第  2 题 已选 Choice0,Choice1 → 2/2 OK" in blob)
    ck("S2 第3题选中 Correct", "第  3 题 已选 Correct → 1/1 OK" in blob)
    if os.path.exists("answers.json"):
        got = json.load(open("answers.json", encoding="utf-8"))
        ck("S2 answers.json 记录本卷 3 题",
           got == {"1": ["Choice1"], "2": ["Choice0", "Choice1"],
                   "3": ["Correct"]}, got)
    else:
        ck("S2 answers.json 记录本卷 3 题", False, "文件不存在")

    # ================= S3: 一开始就配置好 LLM =================
    print("\n--- S3 已配置 LLM 全程 ---")
    LOGS.clear()
    write_llm_cfg()
    cc.ASSESS_WAIT_SECONDS = 45
    page.goto(base + "/exam", wait_until="domcontentloaded")
    ret = cc.handle_assessment(page)
    blob = "\n".join(LOGS)
    ck("S3 交卷成功(返回 True)", ret is True, ret)
    ck("S3 全部 3 题作答完成", "全部 3 题作答完成" in blob)
    ck("S3 题面实时抓取", "考核页实时抓取" in blob)
    ck("S3 考核页已消失", page.locator("#testForm").count() == 0)
    ck("S3 逐题选中状态 OK(日志)",
       all(s in blob for s in (
           "第  1 题 已选 Choice1 → 1/1 OK",
           "第  2 题 已选 Choice0,Choice1 → 2/2 OK",
           "第  3 题 已选 Correct → 1/1 OK")),
       blob[-400:])

    browser.close()

srv.shutdown()
os.chdir(PROJ)
try:
    shutil.rmtree(tmp, ignore_errors=True)
except Exception:
    pass

print("\n== 考核必须LLM实测: %d/%d 通过 ==" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项:", FAIL)
    sys.exit(1)
print("assessment-llm OK")
