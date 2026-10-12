# -*- coding: utf-8 -*-
"""
Course Companion · 看课小帮手（Playwright 版）
=============================================
面向在线视频课程平台的自动学习助手：保持视频播放、自动应答课中问题、
自动推进课时，把重复性的点击工作交给程序。

功能：
  1) 自动登录（首次弹窗配置账号密码，之后会话自动续期免登录）
  2) 验证码截图自动弹出，人工看图输入，脚本自动填入提交（输错自动重试）
  3) 持续监控：视频播放状态 / 课中问题 / 观看进度 / 掉线 / 视频加载出错
  4) 课中问题：自动读取页面内置的参考答案，并以真实鼠标事件点击作答
  5) 观看达标自动进入下一课时，循环推进直到全部完成
  6) 到达需要本人完成的考核/测验环节自动停下
  7) 视频加载出错自动刷新恢复；观看进度保存在服务端，刷新不丢失

快速开始：
  1) 安装 Python 3.9+，然后安装依赖（国内镜像加速）：
     pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple
     python -m playwright install chromium
  2) 运行：python course_companion.py
     首次运行按弹窗提示完成一次性配置（账号 / 密码 / 平台首页地址 /
     课程列表页地址），配置保存在 credentials.local.json

说明：
  - 敏感信息保存在 credentials.local.json（Base64 编码存储），
    该文件已被 .gitignore 排除，不会提交到仓库；换电脑重新配置即可
  - 学习期间请保持浏览器窗口处于前台（可缩小、勿最小化），
    部分平台会暂停后台标签页的计时
  - 同一账号多窗口/多设备同时观看时，多数平台只记录其一，请勿多开
  - 本项目仅供学习交流，请遵守所在平台的服务条款，账号安全自负
"""

import re
import time
import os
import sys
import json
import base64
from playwright.sync_api import sync_playwright

# ================== 配置区 ==================
POLL_SECONDS = 20           # 监控间隔（秒）
AUTH_STATE = "auth.json"    # 登录态保存文件（自动生成，免重复登录）
CRED_FILE = "credentials.local.json"  # 本地凭据配置（已被 .gitignore 排除）
# ============================================


def ask_input(prompt):
    """弹窗收集输入（支持后台运行，不依赖终端）。"""
    import tkinter as tk
    from tkinter import simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # 弹窗置顶，确保用户看得到
    val = simpledialog.askstring("Course Companion · 看课小帮手", prompt, parent=root)
    root.destroy()
    return val


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + str(msg), flush=True)


def load_credentials():
    """加载本地配置 credentials.local.json（Base64 编码的账号 / 密码 /
    平台首页地址 / 课程列表页地址）。文件不存在时弹窗逐项录入并保存。
    脚本与仓库中不保留任何明文凭据；换电脑时删除该文件重新配置即可。"""
    if os.path.exists(CRED_FILE):
        with open(CRED_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        missing = [k for k in ("account", "password", "home_url", "store_url")
                   if k not in raw]
        if missing:
            log("配置缺少字段 " + ",".join(missing) +
                "，请删除 " + CRED_FILE + " 重新配置")
            sys.exit(1)
        return {k: base64.b64decode(raw[k]).decode("utf-8") for k in raw}

    log("未检测到配置文件，开始首次配置（共 4 项，仅此一次）…")
    account = (ask_input("首次配置 1/4：请输入登录账号") or "").strip()
    password = (ask_input("首次配置 2/4：请输入登录密码") or "").strip()
    home_url = (ask_input("首次配置 3/4：请输入平台首页地址（含 https://）") or "").strip()
    store_url = (ask_input("首次配置 4/4：请输入课程列表页地址（含 https://）") or "").strip()
    if not all([account, password, home_url, store_url]):
        log("存在空项，退出。重新运行可再次配置")
        sys.exit(1)
    raw = {k: base64.b64encode(v.encode("utf-8")).decode("ascii")
           for k, v in (("account", account), ("password", password),
                        ("home_url", home_url), ("store_url", store_url))}
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
    log("配置已保存到 " + CRED_FILE + "（已被 .gitignore 排除，不会入库）")
    return {k: base64.b64decode(v).decode("utf-8") for k, v in raw.items()}


def read_answer_from_page(page):
    """从页面内嵌脚本提取参考答案（Choice 值列表）。
    注意：部分页面脚本文本中的字母 s 会被特殊字符替换（includes 会断裂），
    所以用多级策略，不依赖 includes 字样：
      策略1: 锚点 "if ('Choice..." 截取引号内容（单/多选都适用，逗号分隔）
      策略2: answerList = ['Choice0','Choice2'] 数组形式
      策略3: 页面里第一处 'ChoiceX'（兜底）
    """
    html = page.content()
    m = re.search(r"if\s*\(\s*'((?:Choice\d+\s*,?\s*)+)'", html)
    if m:
        return [v.strip() for v in m.group(1).split(",") if v.strip()]
    m = re.search(r"answerList\s*=\s*\[([^\]]+)\]", html)
    if m:
        vals = [v.strip().strip("'\"") for v in m.group(1).split(",")]
        vals = [v for v in vals if v.startswith("Choice")]
        if vals:
            return vals
    m = re.search(r"'(Choice\d+)'", html)
    if m:
        return [m.group(1)]
    return None


def handle_completed_popup(page):
    """检测「您已完成这个活动」提示弹窗（页面自定义弹窗，非原生 dialog）：
    点「确定」→ 点「下一个活动」→ 由外层重新识别新活动。
    返回 True 表示处理过弹窗。"""
    try:
        if page.locator("text=您已完成这个活动").count() == 0:
            return False
        log("检测到「已完成」提示弹窗")
        btn = page.locator("button:has-text('确定'), a:has-text('确定')").first
        if btn.count() > 0:
            btn.click(timeout=3000)
        page.wait_for_timeout(1000)
        nxt = page.locator("a", has_text="下一个活动")
        if nxt.count() > 0:
            nxt.first.click(timeout=3000)
            log("已跳到下一课时")
            page.wait_for_timeout(4000)
        return True
    except Exception as e:
        log("处理已完成弹窗异常：" + str(e)[:80])
        return False


def handle_quiz(page):
    """检测并作答课中问题。弹窗不存在时直接返回 True。"""
    quiz = page.locator("input[name=response]")
    if quiz.count() == 0:
        return True
    try:
        if not quiz.first.is_visible():
            return True
    except Exception:
        return True

    title = ""
    try:
        h = page.locator("h3").filter(has_text="题").first
        title = h.inner_text(timeout=1000).strip().replace("\n", " ")
    except Exception:
        pass
    log("检测到课中问题：" + title[:70])

    answer = read_answer_from_page(page)
    if not answer:
        log("!! 未能从页面脚本读取到参考答案，请在浏览器窗口人工作答，脚本每10秒检查一次…")
        for _ in range(60):  # 最长等 10 分钟（平台通常 15 分钟超时）
            page.wait_for_timeout(10000)
            if page.locator("input[name=response]").count() == 0:
                log("人工作答完成，继续学习")
                return True
        return False

    log("页面参考答案 = " + ",".join(answer))
    try:
        for v in answer:
            # 点击包住该选项的 label（真实鼠标点击，radio 自动联动选中）
            page.locator(
                f"label:has(input[name=response][value={v}])"
            ).first.click(timeout=5000)
        page.wait_for_timeout(300)
        page.get_by_role("button", name="提交").click(timeout=5000)
        page.wait_for_timeout(1500)
    except Exception as e:
        log("作答点击异常：" + str(e)[:100])
        return False

    # 验证：弹窗消失 = 通过（页面自动关窗并恢复播放）；仍在 = 需重试
    if page.locator("input[name=response]").count() == 0:
        log("课中问题作答通过，视频已恢复播放")
        return True
    log("答案未生效，下轮监控自动重试…")
    return False


def read_progress(page):
    """读取「要求观看视频X分钟 / 您已观看X分钟」。返回 (要求, 已观看) 或 None。"""
    try:
        body = page.inner_text("body", timeout=3000)
    except Exception:
        return None
    m1 = re.search(r"要求观看视频\s*(\d+)\s*分钟", body)
    m2 = re.search(r"您已观看\s*(\d+)\s*分钟", body)
    if m1 and m2:
        return int(m1.group(1)), int(m2.group(1))
    return None


def current_activity(page):
    """读取「当前活动：《XXX》」的标题。"""
    try:
        body = page.inner_text("body", timeout=3000)
        m = re.search(r"当前活动：《(.+?)》", body)
        return m.group(1) if m else ""
    except Exception:
        return ""


def ensure_playing(page):
    """确保视频处于播放状态（真实点击 + 空格键双保险）。"""
    try:
        v = page.locator("video").first
        if v.count() == 0:
            return
        if v.evaluate("el => el.paused"):
            try:
                v.click(timeout=3000)  # 真实鼠标点击视频区域
            except Exception:
                pass
            page.wait_for_timeout(800)
            if v.evaluate("el => el.paused"):
                page.keyboard.press("Space")  # 兜底：空格键
            page.wait_for_timeout(800)
    except Exception:
        pass


def fix_video_error(page):
    """检测「加载出错」，刷新页面恢复（观看计时保存在服务端，刷新不丢进度）。"""
    try:
        body = page.inner_text("body", timeout=2000)
        if "加载出错" in body:
            log("检测到视频加载出错，刷新页面恢复…")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
    except Exception:
        pass


def goto_course(page, cred):
    """进入课程学习页：平台首页 → 点击课程入口（完成单点登录）
    → 课程列表页 → 开始学习 → 通过「学习进度」页直达第一个未完成课时。
    直接访问列表页地址可能因单点登录未完成而失败，必须先走入口跳转。"""
    # 1. 打开平台首页
    page.goto(cred["home_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if "login" in page.url:
        return False
    # 2. 点击导航菜单里的课程入口（触发 SSO 跳转到课程列表页）
    try:
        page.locator("a", has_text="公需课").first.click(timeout=6000)
        page.wait_for_timeout(5000)
    except Exception as e:
        log("点击课程入口异常：" + str(e)[:80])
    # 3. 若未到达课程列表页，再尝试直接访问（此时 SSO 可能已完成）
    if "courseRegister" not in page.url:
        page.goto(cred["store_url"], wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    # 4. 等待「开始学习」出现（最多 10 秒）
    try:
        page.locator("a", has_text="开始学习").first.wait_for(timeout=10000)
    except Exception:
        log("课程列表页未出现「开始学习」，当前页面: " + page.url[:90])
        return False
    page.locator("a", has_text="开始学习").first.click()
    page.wait_for_timeout(4000)
    # 5. 通过「学习进度」页直接定位第一个未完成课时（免逐节跳过）
    try:
        page.locator("a", has_text="学习进度").first.click(timeout=5000)
        page.wait_for_timeout(3000)
        row = page.locator("tr", has_text="未完成").first
        if row.count() > 0:
            title_link = row.locator("a").first
            name = title_link.inner_text(timeout=2000).strip()
            title_link.click(timeout=5000)
            page.wait_for_timeout(4000)
            log("已从学习进度页直达第一个未完成课时：" + name)
        else:
            log("学习进度页未发现「未完成」课时（可能已全部完成），留在默认页")
    except Exception as e:
        # 定位失败不致命：留在默认课时页，主循环的弹窗跳过逻辑可兜底
        log("学习进度定位失败（走默认课时页兜底）：" + str(e)[:80])
    return True


def ensure_login(page, context, cred):
    """确保已登录；掉线时自动补登录。
    登录流程：账号密码自动填 → 验证码截图自动打开 + 弹窗置顶 →
    看一眼图输数字 → 脚本自动填入并点击登录。输错自动重试（最多 3 次）。
    登录成功后把 Cookie 存到 auth.json，下次启动直接免登录。"""
    page.goto(cred["home_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if "login" not in page.url:
        log("登录态有效（auth.json 已保存的会话仍可用），无需登录")
        return True

    log("登录态已失效，走登录流程…")
    for attempt in range(1, 4):  # 最多 3 次（验证码看错自动重试）
        page.fill("#userName", cred["account"])
        page.fill("#password", cred["password"])
        # 验证码：截图保存并自动打开，人工识别后在弹窗输入
        try:
            cap_img = page.locator(
                "img[alt*='验证码'], img[src*='captcha'], img[src*='code']"
            ).first
            cap_img.screenshot(path="captcha.png")
        except Exception:
            page.screenshot(path="captcha.png",
                            clip={"x": 0, "y": 0, "width": 900, "height": 600})
        try:
            os.startfile("captcha.png")  # Windows 自动打开图片
        except Exception:
            pass
        code = ask_input(
            "第 %d/3 次尝试\n请输入 captcha.png 图片中的验证码\n（看不清留空点确定，自动换一张）：" % attempt
        )
        code = (code or "").strip()
        if not code:
            # 换一张验证码再试
            try:
                page.locator(
                    "img[alt*='验证码'], img[src*='captcha'], img[src*='code']"
                ).first.click()
                page.wait_for_timeout(1200)
            except Exception:
                pass
            continue
        page.fill("#captcha", code)
        page.locator("button", has_text="登录").first.click()
        page.wait_for_timeout(3000)
        if "login" not in page.url:
            # 登录成功：保存 Cookie 到 auth.json，之后启动免登录
            try:
                context.storage_state(path=AUTH_STATE)
                log("登录成功，会话已保存到 " + AUTH_STATE + "（下次启动免登录）")
            except Exception as e:
                log("登录成功，但保存会话失败：" + str(e)[:80])
            return True
        log("本次未登录成功（密码或验证码错误），自动重试…")
    log("连续 3 次未登录成功，请检查配置后重新运行")
    return False


def main():
    cred = load_credentials()
    with sync_playwright() as p:
        # 有头模式：真实浏览器窗口，平台计时/焦点检测全部正常
        browser = p.chromium.launch(headless=False)
        # 启动时加载已保存的登录态（auth.json），有就免登录
        if os.path.exists(AUTH_STATE):
            ctx = browser.new_context(
                viewport={"width": 1400, "height": 900},
                storage_state=AUTH_STATE,
            )
            log("已加载保存的登录态 " + AUTH_STATE)
        else:
            ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())  # 自动关闭「答案错误」等弹窗

        if not ensure_login(page, ctx, cred):
            browser.close()
            return
        if not goto_course(page, cred):
            log("进入课程失败，请重新运行")
            browser.close()
            return

        done_sections = 0
        while True:  # ---- 外层循环：一节一节推进 ----
            activity = current_activity(page)
            log("当前课时：《%s》" % activity)

            # 考核/测验环节：页面没有视频也没有进度条 → 停下（需本人完成）
            if "考核" in activity or (
                read_progress(page) is None
                and page.locator("video").count() == 0
            ):
                log("已进入考核/测验环节，助手停止，请本人完成！")
                break

            none_rounds = 0  # 连续读不到进度条的轮数
            while True:  # ---- 内层循环：单节监控 ----
                # 掉线检测
                if "login" in page.url:
                    log("会话失效，自动重新登录…")
                    if not ensure_login(page, ctx, cred) or not goto_course(page, cred):
                        browser.close()
                        return
                    break  # 回外层重新识别当前课时

                fix_video_error(page)   # 视频「加载出错」自动刷新
                handle_quiz(page)       # 有课中问题自动作答
                ensure_playing(page)    # 视频暂停自动恢复播放

                # 「您已完成这个活动」弹窗：确定 → 下一课时 → 重新识别
                if handle_completed_popup(page):
                    none_rounds = 0
                    break

                prog = read_progress(page)
                if prog:
                    none_rounds = 0
                    req, done = prog
                    if done >= req:
                        log("本节达标（%d/%d 分钟），进入下一课时" % (done, req))
                        page.locator("a", has_text="下一个活动").first.click()
                        page.wait_for_timeout(4000)
                        done_sections += 1
                        log("本次运行累计推进 %d 节" % done_sections)
                        # 会话自动续期：每完成一节刷新一次 Cookie 存档，
                        # 只要助手持续运行，会话保持新鲜，几乎不会掉线
                        try:
                            ctx.storage_state(path=AUTH_STATE)
                        except Exception:
                            pass
                        break  # 回外层开始新一节
                    log("观看中：%d / %d 分钟" % (done, req))
                else:
                    # 读不到进度条：可能是已完成节（页面无进度文案）或页面加载慢
                    none_rounds += 1
                    log("未读到进度条（第 %d 次）" % none_rounds)
                    if none_rounds >= 3:
                        nxt = page.locator("a", has_text="下一个活动")
                        if nxt.count() > 0:
                            log("判定本节无需观看（已完成或非视频课时），跳到下一节")
                            nxt.first.click()
                            page.wait_for_timeout(4000)
                        none_rounds = 0
                        break  # 回外层重新识别新课时
                page.wait_for_timeout(POLL_SECONDS * 1000)

        browser.close()
        log("本次学习结束")


if __name__ == "__main__":
    main()
