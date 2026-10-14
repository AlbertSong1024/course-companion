# -*- coding: utf-8 -*-
"""
Course Companion · 看课小帮手（一键运行版入口）
===============================================
双击即可运行的单一可执行文件（PyInstaller onefile 打包）：
  1) 自动检查/下载 Playwright 浏览器内核（首次约 1-2 分钟）
  2) 弹出登录界面：账号 / 密码 / 验证码图片直接显示在窗口里，
     输入后点「登录」按钮
  3) 自动执行后续全流程：看课、课中应答、考核交卷、进度核对

源码模式：python course_companion_gui.py
打包产物：course_companion(.exe) 双击运行

线程模型（防止进程/内存叠加的关键）：
  · 整个进程生命周期内 有且只有一个 Playwright 实例、一个浏览器
  · GUI 主线程先起：tkinter 窗口（表单 + 验证码图 + 日志）
  · 工作线程：内核自检/下载（进度逐行进 GUI 日志）→ 持有 Playwright
    跑「登录 → 学习 → 考核」全流程
  · 内核下载直接调内置 node 驱动（绝不 spawn 自身，杜绝自我重启爆炸）
  · 工作线程结束后才关闭 Playwright；窗口关闭则中止；绝不自我重启
  · --noconsole 无 cmd 黑窗：日志 = GUI 运行日志区 + 程序目录 run.log
"""
import os
import sys
import threading
import subprocess


def _harden_console():
    """中文 Windows 控制台默认 GBK 编码：print 遇到 ✓ 之类字符会
    UnicodeEncodeError 直接把程序打崩（双击运行实测踩过坑）。
    把 stdout/stderr 设为「遇未知字符降级为 ?」，任何字符都不会再崩；
    只改 errors 不改 encoding，中文显示不受影响。"""
    for name in ("stdout", "stderr"):
        try:
            st = getattr(sys, name, None)
            if st is not None and hasattr(st, "reconfigure"):
                st.reconfigure(errors="replace")
        except Exception:
            pass


_harden_console()


# ==================== 浏览器内核自检 ====================

def _browser_cache_dir():
    """Playwright 内核缓存目录（跨平台）。
    打包环境强制放在程序目录旁（ms-playwright/），避免受全局缓存干扰。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                            "ms-playwright")
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    import platform
    if os.name == "nt":
        return os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "ms-playwright")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches",
                            "ms-playwright")
    return os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")


def _chromium_installed():
    """内核是否真的可用：目录存在 **且** chrome.exe 真实存在。
    （只判断目录名会让下载中断的残留误判为"已安装"，启动时才找不到
    chrome.exe 而崩溃——上次实测教训。）"""
    cache = _browser_cache_dir()
    if not os.path.isdir(cache):
        return False
    try:
        for name in os.listdir(cache):
            if not name.startswith("chromium"):
                continue
            sub = os.path.join(cache, name)
            if not os.path.isdir(sub):
                continue
            base_depth = sub.count(os.sep)
            for root, dirs, files in os.walk(sub):
                if "chrome.exe" in files:
                    return True
                # 限制深度：chromium-xxxx/chrome-win64/chrome.exe 即可
                if root.count(os.sep) - base_depth >= 2:
                    dirs[:] = []
        return False
    except OSError:
        return False


def _find_driver_node_cli():
    """定位随包内置的 node 可执行文件与 cli.js（Playwright 驱动）。"""
    from playwright._impl._driver import compute_driver_executable
    return compute_driver_executable()


# npmmirror 国内镜像(已实测验证 builds/cft/... 二进制齐全,同步官方):
#   cdn.npmmirror.com/binaries/playwright/builds/cft/151.0.7922.34/win64/chrome-win64.zip
_CN_MIRROR = "https://cdn.npmmirror.com/binaries/playwright"


def _say(msg):
    """统一日志出口：进 GUI 日志窗 + stdout + run.log（cmd 已隐藏）。"""
    import course_companion_login as L
    L.log(msg)


def _download_chromium_builtin():
    """直接调用随包内置的 node 驱动执行 `playwright install chromium`。
    不会 spawn 自身，杜绝 onefile 自我重启爆炸。
    · 默认走 npmmirror 国内镜像加速（境外 CDN 国内裸连常卡死）；
      用户显式设置过 PLAYWRIGHT_DOWNLOAD_HOST 则尊重其配置。
    · 子进程输出逐行捕获转发到 GUI 日志窗（cmd 隐藏后进度在这里看）。
    返回 True 表示成功。"""
    import re as _re
    node_exe, cli_js = _find_driver_node_cli()
    if not (os.path.exists(node_exe) and os.path.exists(cli_js)):
        _say("未找到内置 node 驱动（%s / %s）" % (node_exe, cli_js))
        return False
    env = {**os.environ,
           "PLAYWRIGHT_BROWSERS_PATH": _browser_cache_dir(),
           "PW_LANG_NAME": "python"}
    # 国内加速：用户没显式配置过下载地址时，默认 npmmirror 镜像
    if not (env.get("PLAYWRIGHT_DOWNLOAD_HOST")
            or env.get("PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST")):
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = _CN_MIRROR
    # 单次连接超时放宽到 120s（默认 30s，弱网下容易误判失败）
    env.setdefault("PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT", "120000")
    _say("下载源：" + env.get("PLAYWRIGHT_DOWNLOAD_HOST", _CN_MIRROR))
    _say("保存到：" + env["PLAYWRIGHT_BROWSERS_PATH"])
    proc = subprocess.Popen(
        [node_exe, cli_js, "install", "chromium"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        raw = proc.stdout.readline()
        if not raw:
            if proc.poll() is not None:
                break
            continue
        try:
            line = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        # node 进度条用 \r 分段、ANSI 控制码混杂 → 拆干净再逐段进 GUI
        line = _re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
        for seg in line.replace("\r", "\n").split("\n"):
            seg = seg.strip()
            if seg:
                _say(seg)
    proc.wait()
    return proc.returncode == 0


def _clear_stale_dirlock():
    """清理上次下载中断残留的 __dirlock 目录锁。
    （实测：下载到 10% 被 ECONNRESET 掐断后残留 dirlock，
     下次安装会一直等锁超时——重试前必须先清掉。）"""
    lock = os.path.join(_browser_cache_dir(), "__dirlock")
    if os.path.isdir(lock):
        import shutil
        try:
            shutil.rmtree(lock, ignore_errors=True)
            _say("已清理上次中断残留的下载锁")
        except Exception:
            pass


def ensure_browser():
    """确保 Chromium 内核已安装；缺失时下载（失败自动重试，弱网友好）。
    返回 True/False —— 失败不再 sys.exit（cmd 已隐藏，退出=窗口直接消失，
    用户看不到原因；改为返回 False 让主流程保留窗口并显示错误日志）。"""
    if _chromium_installed():
        _say("检测到已安装的 Chromium 内核，跳过下载")
        return True
    _say("=" * 52)
    _say("首次运行：正在通过国内镜像下载 Chromium 内核")
    _say("（约 1-2 分钟，进度实时显示在下方）…")
    _say("=" * 52)
    ok = False
    for attempt in range(1, 4):  # 弱网 ECONNRESET 自动重试，最多 3 次
        if attempt > 1:
            _say("第 %d/3 次重试（上次下载被网络中断，续跑）…" % attempt)
        _clear_stale_dirlock()
        if _download_chromium_builtin() and _chromium_installed():
            ok = True
            break
        if _chromium_installed():  # 进度返回码非 0 但文件已齐：以实况为准
            ok = True
            break
    if not ok:
        _say("!! 内核下载失败（已自动重试 3 次）。可依次尝试：")
        _say("   1) 关闭后重跑一次（镜像偶发中断，续跑即可）")
        _say("   2) 删除本程序旁的 ms-playwright 文件夹再跑（清残留）")
        _say("   3) 换官方源后重试：set PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev")
        return False
    _say("Chromium 内核下载完成 √")
    return True


# ==================== 凭据（静默读取，不弹窗） ====================

def _load_cred_silent():
    """静默读取凭据：文件在则解码，不在则返回空表单（由 GUI 录入）。"""
    import base64, json
    import course_companion as cc
    account = ""
    password = ""
    if os.path.exists(cc.CRED_FILE):
        try:
            with open(cc.CRED_FILE, encoding="utf-8") as f:
                raw = json.load(f)
            account = base64.b64decode(raw["account"]).decode("utf-8")
            password = base64.b64decode(raw["password"]).decode("utf-8")
        except Exception:
            pass
    return {
        "account": account,
        "password": password,
        "home_url": base64.b64decode(cc._EP_HOME).decode("utf-8"),
        "store_url": base64.b64decode(cc._EP_LIST).decode("utf-8"),
    }


# ==================== 浏览器线程 ====================

def _browser_flow(stop_event):
    """浏览器线程主体：在此线程内创建并持有 Playwright（线程安全的关键），
    跑「登录 → 学习 → 考核」全流程。结束后 才 关闭 Playwright。"""
    import course_companion as cc
    import course_companion_login as L
    L.log("启动浏览器…")

    # 关键修复：PyInstaller 冻结环境下，Playwright 驱动默认去 _MEI 临时
    # 目录的 .local-browsers 找内核（上次实测崩溃点）。必须在启动前把
    # PLAYWRIGHT_BROWSERS_PATH 钉到 ensure_browser 检测/下载的同一目录，
    # 保证「下载的地方」「启动找的地方」永远一致。
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browser_cache_dir()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        if os.path.exists(cc.AUTH_STATE):
            ctx = browser.new_context(
                viewport={"width": 1400, "height": 900},
                storage_state=cc.AUTH_STATE)
            L.log("已加载保存的登录态 " + cc.AUTH_STATE)
        else:
            ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())

        cred = _load_cred_silent()
        if not cred["account"]:
            L.log("未检测到账号配置，请在窗口内输入账号/密码")

        # 登录 → 学习 → 考核（整个进程只跑一次，无自我重启）
        try:
            L.browser_thread(page, ctx, cred, stop_event)
        except Exception as e:
            L.log("浏览器线程异常：" + str(e)[:120])
        finally:
            try:
                ctx.storage_state(path=cc.AUTH_STATE)
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
    L.log("浏览器已关闭")


# ==================== 主流程 ====================

def run_main():
    """核心流程（--noconsole 无 cmd 窗口版）：
      1) 立即弹 GUI（日志/表单就绪）
      2) 后台线程：内核自检/下载（进度逐行进 GUI 日志窗）
      3) 内核就绪 → 同一线程接着跑浏览器「登录 → 学习 → 考核」
    整个进程只启动一次浏览器；窗口关闭或学习完成后才退出。
    下载失败不退出进程：GUI 保留，错误原因显示在日志窗，用户可关窗重跑。"""
    import course_companion_login as L

    # 1) 工作目录（打包产物：exe 所在目录；源码：当前目录）
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    os.chdir(base)
    # 清掉上一次的日志（run.log 每次运行从零开始）
    try:
        if os.path.exists("run.log"):
            os.remove("run.log")
    except Exception:
        pass
    L.log("工作目录：" + base)

    stop_event = threading.Event()

    # 2) 后台工作线程：内核下载 → 浏览器全流程（顺序执行，单线程持有 Playwright）
    def _worker():
        # 工作线程兜底：noconsole 下未捕获异常没人看得见，全部转成 GUI 日志
        try:
            if not ensure_browser():
                L.log("内核未就绪，已停止（可关闭窗口后重跑）")
                return
            L.log("内核就绪")
            _browser_flow(stop_event)
        except Exception as e:
            L.log("工作线程异常（请查看 run.log）：" + str(e)[:200])

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    # 3) GUI 主线程：登录表单 + 验证码图 + 日志（先于下载出现，进度可见）
    cred = _load_cred_silent()
    app = L.LoginApp(cred, on_close=stop_event.set)
    app.run()

    # 窗口关闭 → 等工作线程收尾
    stop_event.set()
    t.join(timeout=15)
    L.log("程序退出")


if __name__ == "__main__":
    try:
        run_main()
    except KeyboardInterrupt:
        print("\n用户中断")  # noconsole 下 stdout 可能为 None，别再抛
