# -*- coding: utf-8 -*-
"""
打包脚本：把 Course Companion 构建为「下载即用」的单一可执行文件。
=============================================================
产物特性：
  - Windows：dist/course_companion.exe，双击即用（自动弹浏览器、
    首次弹窗录入账号/密码、全程自动看课/考核/交卷）
  - macOS / Linux：dist/course_companion，直接运行（同特性）
  - 首次运行时自动检测并下载 Playwright Chromium 内核（联网，约 1-2 分钟）
  - 用户无需预装 Python / Playwright

用法（在对应平台的构建机上执行；产物平台 = 构建机平台）：
      python build_exe.py                  # 生成 dist/course_companion[.exe]
      python build_exe.py --name 看课小帮手  # 自定义产物名

构建机依赖：
      pip install pyinstaller playwright
"""
import os
import sys
import subprocess

APP = "course_companion"
SOURCE = "course_companion_gui.py"   # 一键入口（内核自检 + 调 main）


def _pip_install_missing():
    """缺 pyinstaller 时自动安装（国内镜像加速）。"""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未检测到 PyInstaller，正在安装…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller",
             "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])


def main():
    _pip_install_missing()
    from PyInstaller.__main__ import run

    name = APP
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--name" and i + 1 < len(argv):
            name = argv[i + 1]
            i += 2
            continue
        i += 1

    args = [
        SOURCE,
        "--name", name,
        "--onefile",              # 单一可执行文件
        "--clean",
        "--noconfirm",
        "--hidden-import", "playwright.sync_api",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.simpledialog",
        "--collect-all", "playwright",   # playwright 运行时 + node 驱动
    ]
    if sys.platform != "win32":
        args.insert(1, "--console")      # macOS/Linux 保留终端便于排错
    else:
        args.insert(1, "--noconsole")    # Windows 不弹黑框

    print("构建参数：", " ".join(args))
    run(args)

    out = os.path.join(os.getcwd(), "dist",
                      name + (".exe" if sys.platform == "win32" else ""))
    print("\n=== 构建完成 ===")
    if os.path.exists(out):
        print("产物路径：" + out)
        print("体积：%.1f MB" % (os.path.getsize(out) / 1024 / 1024))
    else:
        print("!! 未找到产物，请检查上方日志")
    print("\n分发提示：")
    print("  · Windows 双击运行；macOS/Linux：chmod +x 后 ./<name>")
    print("  · 首次运行自动下载浏览器内核（约 1-2 分钟），之后免下载")
    print("  · 首次运行弹窗录入账号/密码，保存在程序所在目录，之后免登录")
    print("  · 程序同目录放置 answers.json 才会自动答考核")


if __name__ == "__main__":
    main()
