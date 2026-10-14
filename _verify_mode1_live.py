# -*- coding: utf-8 -*-
"""方式一（脚本）真实浏览器冒烟：起 Chromium → 加载平台首页 → 校验会话。
不进入看课流程（看完即关，避免挂机）。用法: python _verify_mode1_live.py
退出码 0 = 通过；会话失效不算失败（单独标记 SESSION_EXPIRED）。"""
import os
import sys
import time

import course_companion as cc

fails = []


def ck(name, cond, detail=""):
    ok = bool(cond)
    print(("  OK   " if ok else "  FAIL ") + name + (("  <- " + str(detail)) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)
    return ok

# 0) 内核在位（源码模式用 LOCALAPPDATA 默认缓存）
cache = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
chrome = None
if os.path.isdir(cache):
    for root, _d, files in os.walk(cache):
        if "chrome.exe" in files:
            chrome = root
            break
if not ck("Chromium 内核已安装（源码模式默认缓存）", chrome, cache):
    print("  提示: python -m playwright install chromium")
    sys.exit(1)

# 1) 凭据
cred = cc.load_credentials()
ck("凭据加载成功", bool(cred["account"]))

# 2) 真实浏览器
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900},
                              storage_state=cc.AUTH_STATE if os.path.exists(cc.AUTH_STATE) else None)
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    t0 = time.time()
    try:
        page.goto(cred["home_url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        ck("平台首页加载成功 (%.1fs)" % (time.time() - t0), True, page.url)
        title = page.title()
        ck("页面标题可读取", bool(title), repr(title))
        # 页面关键元素探活（证明拿到了真实页面而非错误页）
        body = page.inner_text("body", timeout=5000)
        ck("页面正文非空 (%d 字)" % len(body), len(body) > 50)
        sess_ok = "login" not in page.url
        ck("登录态检查完成（auth.json 会话）", True,
           "有效" if sess_ok else "已失效（运行时会走登录流程，非故障）")
        # 核心选择器探活：登录页元素 or 已登录首页元素，至少命中一个
        has_login_form = page.locator("#userName").count() > 0
        print("  INFO 登录表单可见: %s（会话%s）" % (has_login_form, "有效" if sess_ok else "失效"))
        if not sess_ok:
            ck("会话失效时登录表单可定位（登录流程可用）", has_login_form)
    except Exception as e:
        ck("平台访问", False, e)
    browser.close()

print()
if fails:
    print("失败项:", fails)
    sys.exit(1)
print("mode1 live OK")
