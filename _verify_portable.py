# -*- coding: utf-8 -*-
"""便携包(zip)解压即用验证：把 zip 解到全新临时目录，跑真 exe，断言
  ① 免下载秒启动（内核随包内置 → 跳过下载）
  ② 走到启动浏览器、无内核路径崩溃
  ③ GUI 登录窗弹出
跑完杀进程树。用法: python _verify_portable.py   退出码 0 = 通过。
"""
import os
import subprocess
import sys
import tempfile
import time

ZIP = os.path.join("dist", "course_companion_portable_v1.0.0.zip")
RUN_LOG = "run.log"
checks = []


def ck(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(("  OK   " if cond else "  FAIL ") + name
          + (("  <- " + str(detail)) if (detail and not cond) else ""))


assert os.path.exists(ZIP), "缺 " + ZIP + ", 先打便携包"
print("zip: %.1f MB" % (os.path.getsize(ZIP) / 1024 / 1024))

# ① 解压到全新临时目录
tmp = tempfile.mkdtemp(prefix="cc_portable_")
print("解压到:", tmp)
t0 = time.time()
subprocess.check_call(
    ["tar", "-xf", os.path.abspath(ZIP), "-C", tmp])
print("解压耗时 %.1fs" % (time.time() - t0))
app_dir = os.path.join(tmp, "course_companion")
exe = os.path.join(app_dir, "course_companion.exe")

ck("解压出 course_companion.exe", os.path.exists(exe))
ck("内核随包存在(chrome.exe)",
   os.path.exists(os.path.join(app_dir, "ms-playwright",
                               "chromium-1234", "chrome-win64", "chrome.exe")))
ck("答案表随包存在", os.path.exists(os.path.join(app_dir, "answers.json")))
ck("使用说明 README.txt 随包存在",
   os.path.exists(os.path.join(app_dir, "README.txt")))
ck("无隐私文件泄漏(凭据/auth)联检",
   not os.path.exists(os.path.join(app_dir, "auth.json"))
   and not os.path.exists(os.path.join(app_dir, "credentials.local.json")))

# ② 跑真 exe
p = subprocess.Popen([exe], cwd=app_dir)
run_log = os.path.join(app_dir, RUN_LOG)
deadline = time.time() + 120
blob = ""
while time.time() < deadline:
    try:
        with open(run_log, encoding="utf-8", errors="replace") as f:
            blob = f.read()
    except OSError:
        time.sleep(0.3)
        continue
    if any(k in blob for k in ("内核就绪", "内核未就绪", "浏览器线程异常")):
        if "启动浏览器" in blob or "内核未就绪" in blob:
            break
    time.sleep(0.3)

alive = p.poll() is None
ck("免下载秒启动(跳过下载)", "跳过下载" in blob, blob[:300])
ck("内核就绪", "内核就绪" in blob)
ck("走到启动浏览器", "启动浏览器" in blob, blob[:300])
ck("无内核路径崩溃(Executable doesn't exist)",
   "Executable doesn't exist" not in blob)
ck("exe 存活(未崩溃)", alive)

# ③ GUI 登录窗
def _find_gui_window():
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


gui = None
end = time.time() + 15
while time.time() < end:
    gui = _find_gui_window()
    if gui:
        break
    time.sleep(0.5)
ck("GUI 登录窗已弹出", gui, "15s 内未找到")
if gui:
    print("  INFO 窗口标题:", gui)

# ④ 收尾：杀进程树 + 清临时目录
if sys.platform == "win32":
    subprocess.call(["taskkill", "/T", "/F", "/PID", str(p.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
else:
    p.kill()
try:
    p.wait(timeout=15)
except Exception:
    pass
import shutil
for _ in range(5):
    try:
        shutil.rmtree(tmp, ignore_errors=False)
        break
    except OSError:
        time.sleep(1)

fails = [n for n, ok in checks if not ok]
print("\n== 便携包验证: %d/%d 通过 ==" % (len(checks) - len(fails), len(checks)))
if fails:
    print("失败项:", fails)
    sys.exit(1)
print("portable OK")
