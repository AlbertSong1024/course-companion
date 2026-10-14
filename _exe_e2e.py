# -*- coding: utf-8 -*-
r"""exe 端到端验证(无 cmd 版):跑真 exe,断言国内源下载/进度、GUI 弹窗、
日志落盘 run.log、浏览器启动。cmd 隐藏后 exe 无 stdout,一切断言改读
dist/run.log(exe 每次启动会重建它)。
用法: python _exe_e2e.py  (dist\ms-playwright 无 chrome.exe 时走全新下载场景)
"""
import os
import re
import subprocess
import sys
import time

EXE = os.path.join("dist", "course_companion.exe")
KERNEL_DIR = os.path.join("dist", "ms-playwright")
RUN_LOG = os.path.join("dist", "run.log")

assert os.path.exists(EXE), "缺 dist/course_companion.exe,先跑 python build_exe.py"

need_download = True
if os.path.exists(os.path.join(KERNEL_DIR, "chromium-1234")):
    for _r, _d, files in os.walk(os.path.join(KERNEL_DIR, "chromium-1234")):
        if "chrome.exe" in files:
            need_download = False
            break
print("本次场景:", "全新下载(验证国内源)" if need_download else "已有内核(验证免下载启动)")

# 上一次的 run.log 先删掉,确保本次断言读到的是新内容
try:
    if os.path.exists(RUN_LOG):
        os.remove(RUN_LOG)
except OSError:
    pass

env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
p = subprocess.Popen([os.path.abspath(EXE)],
                    cwd=os.path.dirname(os.path.abspath(EXE)),
                    env=env)

lines = []


def read_log():
    """增量读 run.log → lines,返回全部内容。"""
    try:
        with open(RUN_LOG, encoding="utf-8", errors="replace") as f:
            all_lines = [x.rstrip("\n") for x in f.readlines()]
    except OSError:
        return "\n".join(lines)
    if len(all_lines) > len(lines):
        for x in all_lines[len(lines):]:
            lines.append(x)
            if len(lines) <= 40 or any(k in x for k in
                                       ("下载源", "完成", "就绪", "异常", "失败",
                                        "启动浏览器", "登录")):
                print("  |", x[:140])
    return "\n".join(lines)


# 等待关键里程碑行(下载完成/内核就绪/启动浏览器 或 失败),run.log 每次启动重建
deadline = time.time() + (900 if need_download else 60)
blob = ""
while time.time() < deadline:
    if not os.path.exists(RUN_LOG):
        time.sleep(0.3)
        continue
    blob = read_log()
    if any(k in blob for k in ("内核就绪", "内核未就绪", "浏览器线程异常")):
        break
    time.sleep(0.3)

# 下载场景再等「启动浏览器」；失败场景立即短等后断言
if "内核就绪" in blob or "启动浏览器" in blob:
    end = time.time() + 30
    while time.time() < end:
        blob = read_log()
        if "启动浏览器" in blob:
            break
        time.sleep(0.3)

alive = p.poll() is None
blob = read_log()

checks = []
def ck(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(("  OK " if cond else "  FAIL ") + name
          + (("  <- " + str(detail)) if (detail and not cond) else ""))

if need_download:
    ck("日志回显国内镜像源(cdn.npmmirror)",
       "cdn.npmmirror.com" in blob or "下载源" in blob)
    ck("未把境外源当主源(下载源非 cdn.playwright.dev)",
       not re.search(r"下载源：https://cdn\.playwright\.dev", blob))
    ck("下载进度进日志(node 进度行被转发)",
       bool(re.search(r"\d+% of \d", blob)), blob[-200:])
    ck("内核下载完成/或已就绪",
       ("下载完成" in blob) or ("内核就绪" in blob))
    ck("chrome.exe 已落盘", os.path.exists(
        os.path.join(KERNEL_DIR, "chromium-1234", "chrome-win64", "chrome.exe")))
    ck("未报下载失败(3 次重试全败才算)", "内核下载失败" not in blob)
else:
    ck("已装内核秒过(跳过下载)", "跳过下载" in blob)
    ck("内核就绪", "内核就绪" in blob)

ck("run.log 已生成(无 cmd 时的日志存档)", os.path.exists(RUN_LOG))
ck("exe 存活(未崩溃)", alive)
ck("走到启动浏览器", "启动浏览器" in blob)
ck("无内核路径崩溃(Executable doesn't exist)",
   "Executable doesn't exist" not in blob)


# GUI 登录窗真的弹出来(枚举顶层窗口标题)
def _find_gui_window():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        n = u32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith("Course Companion") and u32.IsWindowVisible(hwnd):
                found.append(buf.value)
        return True
    u32.EnumWindows(cb, 0)
    return found[0] if found else None


gui_title = None
gui_deadline = time.time() + 15
while time.time() < gui_deadline:
    gui_title = _find_gui_window()
    if gui_title:
        break
    time.sleep(0.5)
ck("GUI 登录窗已弹出", gui_title, "15s 内未找到 Course Companion 窗口")
if gui_title:
    print("  INFO 窗口标题:", gui_title)


# 无论成败都杀整个进程树(exe→driver→chrome)，否则桌面残留浏览器/GUI 窗口
if sys.platform == "win32":
    subprocess.call(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
else:
    p.kill()
try:
    p.wait(timeout=15)
except Exception:
    pass

fails = [n for n, ok in checks if not ok]
print("\n== 结果: %d/%d 通过 ==" % (len(checks) - len(fails), len(checks)))
if fails:
    print("失败项:", fails)
    sys.exit(1)
print("e2e OK")
