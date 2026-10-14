# -*- coding: utf-8 -*-
r"""GUI 运行日志 + LLM 设置 全链路实测（在临时目录跑，绝不碰项目真实文件）。
覆盖用户反馈的两个问题：
  A) GUI「运行日志」区空白 → 驱动真实 LoginApp，断言文本框里真有日志
  B) LLM 设置没测过 → 真实打开对话框、填表、点保存/清除按钮；
     用本地 mock OpenAI 服务跑通「LLM 答题 → 答案表写回」全链路
另存窗口截图 gui_log_proof.png 作证据。
用法: python _verify_llm_gui.py   退出码 0 = 全部通过。
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


# ---- 临时工作目录（llm.local.json / answers.json 都写这里，项目目录零污染） ----
tmp = tempfile.mkdtemp(prefix="cc_llm_gui_")
shutil.copy2(os.path.join(PROJ, "questions.json"), tmp)  # 题库副本
os.chdir(tmp)

import course_companion as cc          # noqa: E402
import course_companion_login as L      # noqa: E402
import llm_answerer as A                # noqa: E402


# ---- mock OpenAI 兼容服务：POST /chat/completions → 固定 [1] ----
class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        body = json.dumps(
            {"choices": [{"message": {"content": "[1]"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = HTTPServer(("127.0.0.1", 0), Mock)
mock_port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
mock_base = "http://127.0.0.1:%d" % mock_port


# ==================== A) GUI 运行日志可见性 ====================
app = L.LoginApp({"account": "", "password": ""}, on_close=lambda: None)
cc.log = L.log  # 同浏览器线程：主流程日志也进 GUI 队列
L.log("测试日志：GUI 可见性验证 1")
L.log("测试日志：GUI 可见性验证 2")


def pump(sec):
    """驱动 tkinter 事件循环（让 after(150) 定时器真正跑起来）。"""
    end = time.time() + sec
    while time.time() < end:
        app.root.update()
        time.sleep(0.05)


pump(1.5)
txt = app.log_text.get("1.0", "end-1c")
ck("GUI 运行日志区有内容",
   "GUI 可见性验证 1" in txt and "GUI 可见性验证 2" in txt, repr(txt[:100]))
ck("日志框写完仍为只读(disabled)",
   str(app.log_text.cget("state")) == "disabled",
   app.log_text.cget("state"))
ck("日志有时间戳前缀", __import__("re").search(r"\[\d{2}:\d{2}:\d{2}\]", txt),
   repr(txt[:30]))


# ---- 小工具：遍历窗口找 Entry / Button ----
def walk(w, out, klass):
    for c in w.winfo_children():
        if c.winfo_class() == klass:
            out.append(c)
        walk(c, out, klass)


# ==================== B) LLM 设置对话框（真实点击） ====================
app._open_llm_settings()
pump(0.6)
win = app._llm_win
entries = {}
walk(win, entries_list := [], "TEntry")
for e in entries_list:                      # 按 grid 行号识别三个输入框
    try:
        entries[int(e.grid_info().get("row", -1))] = e
    except Exception:
        pass
btns = []
walk(win, btns, "TButton")
ck("LLM 弹窗含 3 个输入框(base/model/key)",
   sorted(k for k in entries if k >= 0) == [1, 2, 3], sorted(entries))

entries[1].delete(0, "end"); entries[1].insert(0, mock_base)
entries[2].delete(0, "end"); entries[2].insert(0, "mock-model")
entries[3].delete(0, "end"); entries[3].insert(0, "sk-test-123456")
save_btn = [b for b in btns
            if b.cget("text").replace(" ", "") == "保存"]
ck("找到「保 存」按钮", len(save_btn) == 1,
   [b.cget("text") for b in btns])
save_btn[0].invoke()
pump(2.0)                                   # 等 win.after(700, destroy)
ck("llm.local.json 已保存", os.path.exists("llm.local.json"))
if os.path.exists("llm.local.json"):
    cfg = json.load(open("llm.local.json", encoding="utf-8"))
    ck("配置内容正确(base/model/key)",
       cfg.get("base_url") == mock_base
       and cfg.get("model") == "mock-model"
       and cfg.get("api_key") == "sk-test-123456", cfg)
pump(2.0)                                   # 等状态栏 tick(%10==1 ≈1.65s)
status = str(app.llm_status.cget("text"))
ck("主窗状态栏显示「LLM 答题：已启用」", "已启用" in status, status)


# ==================== C) LLM 答题全链路（mock 服务） ====================
ck("llm_enabled()==True", A.llm_enabled() is True)
struct = A.load_question_structure()
ck("题库读入 30 题", len(struct) == 30, len(struct))
q = struct[1]
multi = "多选" in (q.get("type") or "")
ans = A.answer_question(q, multi=multi)
ck("LLM 答题返回有效 Choice 列表",
   bool(ans) and all(x.startswith("Choice") for x in ans), ans)

res = cc._llm_resolve_answers(None, {}, 30)
ck("_llm_resolve_answers 补答 30 题", len(res) == 30, len(res))
ck("答案表已写回 answers.json", os.path.exists("answers.json"))
if os.path.exists("answers.json"):
    raw = json.load(open("answers.json", encoding="utf-8"))
    ck("answers.json 共 30 条且值为 Choice 列表",
       len(raw) == 30 and all(str(v).startswith("[" ) for v in raw.values()),
       "%d 条" % len(raw))

# 坏端口 → 调用失败必须静默降级 None（不影响主流程）
with open("llm.local.json", "w", encoding="utf-8") as f:
    json.dump({"base_url": "http://127.0.0.1:1",
               "api_key": "sk-x", "model": "m"}, f)
ck("坏端点 answer_question 降级返回 None",
   A.answer_question(q, multi=multi) is None)


# ==================== D) 清除 LLM 配置（真实点击） ====================
app._open_llm_settings()
pump(0.6)
win2 = app._llm_win
e2 = []
walk(win2, e2, "TEntry")
b2 = []
walk(win2, b2, "TButton")
clear_btn = [b for b in b2 if "清除" in b.cget("text")]
ck("找到「清除 LLM 配置」按钮", len(clear_btn) == 1,
   [b.cget("text") for b in b2])
clear_btn[0].invoke()
pump(2.5)
ck("清除后 llm.local.json 已删除", not os.path.exists("llm.local.json"))
ck("llm_enabled() 回到 False", A.llm_enabled() is False)
status = str(app.llm_status.cget("text"))
ck("状态栏回到「未启用」", "未启用" in status, status)

# 清除动作的日志也应进 GUI
pump(1.0)
txt2 = app.log_text.get("1.0", "end-1c")
ck("GUI 日志累积更多内容(≥50 字)", len(txt2) > 50, len(txt2))


# ==================== E) 窗口截图取证 ====================
try:
    from PIL import ImageGrab
    pump(0.6)
    x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
    w, h = app.root.winfo_width(), app.root.winfo_height()
    shot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    shot_path = os.path.join(PROJ, "gui_log_proof.png")
    shot.save(shot_path)
    ck("窗口截图已保存 gui_log_proof.png", os.path.exists(shot_path),
       shot_path)
except Exception as e:
    ck("窗口截图已保存 gui_log_proof.png", False, e)

app.root.destroy()
srv.shutdown()
os.chdir(PROJ)
print("\n== GUI日志+LLM设置实测: %d/%d 通过 ==" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项:", FAIL)
    sys.exit(1)
print("llm-gui OK")
