# -*- coding: utf-8 -*-
"""
Course Companion · 看课小帮手（一键运行版入口）
================================================
由 PyInstaller 打包成单文件可执行后，运行本入口即可：
  1) 自动检查/下载 Playwright 浏览器内核（首次约 1-2 分钟）
  2) 首次运行弹窗录入账号/密码（之后保存免登录）
  3) 全程自动：看课、课中应答、考核交卷、进度核对

源码模式：python course_companion_gui.py
打包产物：course_companion(.exe) 双击运行
"""
import os
import sys


def _browser_cache_dir():
    """Playwright 浏览器内核的缓存目录（跨平台）。
    打包环境强制使用程序所在目录下的 ms-playwright/，
    避免受用户已有全局缓存干扰，实现「绿包即拿即用」。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                            "ms-playwright")
    import platform
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    if os.name == "nt":
        return os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "ms-playwright")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches",
                            "ms-playwright")
    return os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright")


def _chromium_installed():
    cache = _browser_cache_dir()
    if not os.path.isdir(cache):
        return False
    return any(n.startswith("chromium") for n in os.listdir(cache)
               if os.path.isdir(os.path.join(cache, n)))


def ensure_browser():
    """确保 Chromium 内核已安装；缺失时调用 `playwright install chromium` 下载。"""
    if _chromium_installed():
        print("检测到已安装的 Chromium 内核，跳过下载")
        return
    print("=" * 52)
    print("首次运行：正在下载 Chromium 内核（约 1-2 分钟，请稍候）…")
    print("=" * 52)
    import subprocess
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": _browser_cache_dir()}
    # 打包环境：复用当前可执行文件（内置了 python 运行时 + playwright 包）
    exe = sys.argv[0] if getattr(sys, "frozen", False) else sys.executable
    ret = subprocess.call(
        [exe, "-m", "playwright", "install", "chromium"], env=env)
    if ret != 0 or not _chromium_installed():
        print("\n!! 内核下载失败。可设置环境变量 PLAYWRIGHT_BROWSERS_PATH 指定"
              "镜像源后重试，例如（国内加速）：")
        print("   set PLAYWRIGHT_BROWSERS_PATH=C:\\pw-mirror")
        print("   并把镜像好的 ms-playwright\\chromium-* 拷入程序目录")
        if os.name == "nt":
            input("按回车退出…")
        sys.exit(1)
    print("Chromium 内核下载完成 ✓")


def main():
    print("Course Companion · 看课小帮手（一键运行版）")
    print("正在初始化…")
    ensure_browser()

    # 让主脚本从当前可执行文件所在目录读取配置
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    os.chdir(base)
    print("工作目录：" + base)
    print("-" * 52)

    import course_companion
    course_companion.main()


if __name__ == "__main__":
    main()
