# -*- coding: utf-8 -*-
"""
登录 GUI 模块：单一窗口完成「账号 / 密码 / 验证码」登录，之后自动进入学习。
============================================================================
窗口内容（自上而下）：
  · 登录表单：账号、密码、验证码（验证码图片内嵌显示，点"换一张"刷新）
  · 状态日志区：实时显示当前进度（内核初始化 / 登录 / 看课 / 考核）

线程模型（关键，保证不会进程/内存爆炸）：
  · 浏览器线程：持有 Playwright 实例与 page，跑「登录 → 学习 → 考核」全流程
  · GUI 主线程：tkinter 窗口，只负责表单、显示验证码图、日志
  · 二者通过 4 个线程安全队列/事件通信：
      _LOG_LINES     浏览器线程 → GUI（日志行）
      _CAPTCHA_REQ   GUI「换一张」 → 浏览器线程（请求刷新验证码）
      _CAPTCHA_B64   浏览器线程 → GUI（新验证码图）
      _LOGIN_RESULT  浏览器线程 → 主入口（登录结果）
      _SUBMIT        GUI「登录」按钮 → 浏览器线程（提交账号/密码/验证码）

  主入口 run_main() 在浏览器线程结束后 才 关闭 Playwright，
  整个进程生命周期内 有且只有一个 sync_playwright 实例、
  一个 browser、一个 ctx —— 不会无限重启、不会内存叠加。
"""
import queue
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
from io import BytesIO

# ============ 线程间通信 ============
_LOG_LINES: "queue.Queue[str]" = queue.Queue()     # 浏览器线程 → GUI
_CAPTCHA_REQ: "queue.Queue[None]" = queue.Queue()   # GUI「换一张」 → 浏览器线程
_CAPTCHA_B64: "queue.Queue[str]" = queue.Queue()    # 浏览器线程 → GUI（新图）
_LOGIN_RESULT: "queue.Queue[bool]" = queue.Queue()  # 浏览器线程 → 入口
_SUBMIT: "queue.Queue" = queue.Queue()              # GUI「登录」 → 浏览器线程


def log(msg):
    """写日志：入队给 GUI + 打印到 stdout + 落盘 run.log。
    （exe 打包为 --noconsole 无 cmd 窗口后，run.log 是唯一完整日志存档，
    出问题时可直接查看程序目录下的 run.log。）"""
    stamp = time.strftime("[%H:%M:%S] ")
    line = stamp + str(msg)
    _LOG_LINES.put(line)
    try:
        print(line, flush=True)
    except Exception:
        pass  # noconsole 下 stdout 可能为 None，落盘不受影响
    try:
        with open("run.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def drain_log_queue(q, text_widget):
    """由 GUI 主循环定时调用，把日志行刷到文本框（带长度上限防膨胀）。
    关键：log_text 建的时候是 state="disabled" 只读态，此时 insert
    **不报错也不写入**（Tcl 静默忽略），日志就永远进不了窗口——cmd 有
    日志而 GUI 空白正是这个坑。必须 写前解锁、写完锁回。"""
    while True:
        try:
            line = q.get_nowait()
        except queue.Empty:
            break
        except Exception:
            break
        try:
            text_widget.config(state="normal")
            text_widget.insert(tk.END, line + "\n")
            text_widget.see(tk.END)
            # 限制文本框行数，防止长时间运行内存无限增长
            if int(text_widget.index("end-1c").split(".")[0]) > 500:
                text_widget.delete("1.0", "50.0")
            text_widget.config(state="disabled")
        except Exception:
            # 写入异常不能把整条日志链弄断：恢复只读态后继续下一条
            try:
                text_widget.config(state="disabled")
            except Exception:
                break


class LoginApp:
    """登录 + 状态监视窗口。生命周期由 run_main() 管理。"""

    def __init__(self, cred, on_close=None):
        self.cred = cred
        self.on_close = on_close
        self.root = tk.Tk()
        self.root.title("Course Companion · 看课小帮手")
        self.root.geometry("560x610")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self._collapsed = False

        # ---- 顶部：登录表单 ----
        self.form_frame = ttk.Frame(self.root, padding=12)
        self.form_frame.pack(fill="x")

        ttk.Label(self.form_frame, text="广东省教师继续教育 · 公需课程",
                  font=("Microsoft YaHei UI", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(self.form_frame, text="账号：").grid(row=1, column=0,
                                                         sticky="e", pady=4)
        self.account_entry = ttk.Entry(self.form_frame, width=34)
        self.account_entry.grid(row=1, column=1, columnspan=2, sticky="we")
        self.account_entry.insert(0, cred.get("account", ""))

        ttk.Label(self.form_frame, text="密码：").grid(row=2, column=0,
                                                         sticky="e", pady=4)
        self.password_entry = ttk.Entry(self.form_frame, width=34, show="*")
        self.password_entry.grid(row=2, column=1, columnspan=2, sticky="we")
        self.password_entry.insert(0, cred.get("password", ""))

        # 验证码行：输入框 + 图片标签
        ttk.Label(self.form_frame, text="验证码：").grid(
            row=3, column=0, sticky="e", pady=4)
        self.captcha_var = tk.StringVar()
        self.captcha_entry = ttk.Entry(self.form_frame, textvariable=self.captcha_var,
                                       width=10)
        self.captcha_entry.grid(row=3, column=1, sticky="w")
        self.captcha_img_holder = tk.Label(self.form_frame, text="（获取中…）")
        self.captcha_img_holder.grid(row=3, column=2, sticky="w", padx=8)
        self.captcha_photo = None
        self._request_captcha()  # 初始刷新一张

        ttk.Button(self.form_frame, text="换一张验证码",
                   command=self._request_captcha).grid(
            row=4, column=1, columnspan=2, sticky="e", pady=(4, 0))

        self.login_btn = ttk.Button(self.form_frame, text="登  录",
                                    command=self._do_login)
        self.login_btn.grid(row=5, column=0, columnspan=3,
                            sticky="we", pady=(10, 0))

        # ---- LLM 设置栏（常驻：登录后表单隐藏，本栏仍可见，随时可配） ----
        self.ctrl_frame = ttk.Frame(self.root, padding=(12, 6))
        self.ctrl_frame.pack(fill="x")
        self.llm_btn = ttk.Button(self.ctrl_frame, text="⚙ LLM 设置",
                                  command=self._open_llm_settings)
        self.llm_btn.pack(side="left")
        self.llm_status = ttk.Label(self.ctrl_frame, foreground="#666666")
        self.llm_status.pack(side="left", padx=10)
        self._drain_ticks = 0

        # ---- 底部：状态日志 ----
        self.log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=8)
        self.log_frame.pack(fill="both", expand=True, pady=(8, 8), padx=12)
        self.log_text = tk.Text(self.log_frame, width=60, height=14,
                                state="disabled", wrap="word",
                                background="#1e1e1e", foreground="#c8e6c9",
                                font=("Consolas", 9))
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_scroll = ttk.Scrollbar(self.log_frame,
                                        command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        self.log_scroll.pack(side="right", fill="y")

        self.root.after(150, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

    # ---- 表单小工具（已内联到 __init__，保留账号/密码 Entry 引用） ----
    # （原 _mk_row / _account_var / _password_var 已废弃，改为直接建 Entry）

    # ---- 日志刷新（GUI 主线程） ----
    def _drain(self):
        """定时排空各队列。after() 放 finally：任何一帧、任何一环抛异常
        都不能断掉定时链（原实现 after 在最后一行，一处异常=GUI 僵死：
        日志停更、验证码不刷新、登录结果不回）。"""
        try:
            drain_log_queue(_LOG_LINES, self.log_text)
            # LLM 状态每 ~1.5 秒刷新一次（实时反映 llm.local.json 的增删改）
            self._drain_ticks += 1
            if self._drain_ticks % 10 == 1:
                try:
                    import course_companion as cc
                    cfg = cc.read_llm_config_silent()
                    if cfg:
                        self.llm_status.config(
                            text="LLM 答题：已启用（%s）" % cfg["model"],
                            foreground="#2e7d32")
                    else:
                        self.llm_status.config(text="LLM 答题：未启用",
                                               foreground="#666666")
                except Exception:
                    pass
            # 拉取新验证码图
            while True:
                try:
                    b64 = _CAPTCHA_B64.get_nowait()
                    self._show_captcha_b64(b64)
                except queue.Empty:
                    break
            # 拉取登录结果 → 反馈到按钮
            while True:
                try:
                    ok = _LOGIN_RESULT.get_nowait()
                    self._on_login_result(ok)
                except queue.Empty:
                    break
        except Exception as e:  # 定时器自身绝不能崩：记到 stderr 不断链
            try:
                print("GUI 刷新异常(不影响运行): " + str(e)[:120], file=sys.stderr)
            except Exception:
                pass  # noconsole 下 stderr 为 None，绝不能再抛
        finally:
            self.root.after(150, self._drain)

    def _show_captcha_b64(self, b64: str):
        if b64.startswith("__ERR__:"):
            self.captcha_img_holder.config(
                text="获取验证码失败（" + b64.split(":", 1)[1] + "），点'换一张'",
                image="", foreground="#c00")
            return
        try:
            from PIL import Image, ImageTk
            import base64
            img = Image.open(BytesIO(base64.b64decode(b64)))
            img.thumbnail((260, 130))
            self.captcha_photo = ImageTk.PhotoImage(img)
            self.captcha_img_holder.config(image=self.captcha_photo, text="")
        except Exception as e:
            self.captcha_img_holder.config(text="验证码加载失败：" + str(e)[:30],
                                          image="", foreground="#c00")

    def _request_captcha(self):
        _CAPTCHA_REQ.put(None)

    def _on_login_result(self, ok):
        if ok:
            if getattr(self, "_collapsed", False):
                return  # 已收起过（登录成功/会话有效都可能推送），幂等
            self._collapsed = True
            self.login_btn.config(state="disabled", text="登录成功 ✓")
            try:
                self.captcha_img_holder.destroy()
            except Exception:
                pass
            self.form_frame.pack_forget()
            # 缩小成状态条，保留 LLM 设置栏 + 日志，避免挡学习窗口
            self.root.geometry("520x320")
            self.root.attributes("-topmost", False)
            log("窗口已切换为运行状态监视模式（LLM 设置仍可用）")
        else:
            self.login_btn.config(state="normal", text="重新登录")
            self._request_captcha()  # 失败自动换一张验证码

    # ---- 登录按钮 ----
    def _do_login(self):
        account = self.account_entry.get().strip()
        password = self.password_entry.get().strip()
        captcha = self.captcha_var.get().strip()
        if not account or not password:
            messagebox.showwarning("缺少信息", "请填写账号和密码")
            return
        if self.login_btn["state"] == "disabled":
            return  # 已提交，防重复点击
        _SUBMIT.put((account, password, captcha))
        self.login_btn.config(state="disabled", text="登录中…")
        self.captcha_var.set("")  # 清空旧验证码，失败重输不残留
        log("已提交登录，等待结果…")

    # ---- LLM 设置（Toplevel，随时可开；保存后立即生效，无需重启） ----
    def _open_llm_settings(self):
        import course_companion as cc
        if getattr(self, "_llm_win", None) is not None:
            try:
                if self._llm_win.winfo_exists():
                    self._llm_win.lift()
                    return
            except Exception:
                pass
        win = tk.Toplevel(self.root)
        self._llm_win = win
        win.title("LLM 答题设置")
        win.geometry("470x250")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)

        cur = cc.read_llm_config_silent() or {}
        ttk.Label(frm, text="配置后考核环节由 LLM 校验/补答答案表；"
                            "留空点保存=保持原值。").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frm, text="base_url：").grid(row=1, column=0, sticky="e")
        e_base = ttk.Entry(frm, width=40)
        e_base.grid(row=1, column=1, sticky="we", pady=2)
        e_base.insert(0, cur.get("base_url", "https://api.deepseek.com"))
        ttk.Label(frm, text="model：").grid(row=2, column=0, sticky="e")
        e_model = ttk.Entry(frm, width=40)
        e_model.grid(row=2, column=1, sticky="we", pady=2)
        e_model.insert(0, cur.get("model", "deepseek-chat"))
        ttk.Label(frm, text="api_key：").grid(row=3, column=0, sticky="e")
        e_key = ttk.Entry(frm, width=40, show="*")
        e_key.grid(row=3, column=1, sticky="we", pady=2)
        e_key.insert(0, cur.get("api_key", ""))

        tip = ttk.Label(frm, foreground="#666666",
                        text="已启用 ✓" if cur else "当前未启用 LLM 答题")
        tip.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def do_save():
            base = (e_base.get().strip() or "https://api.deepseek.com").rstrip("/")
            model = (e_model.get().strip() or "deepseek-chat")
            key = e_key.get().strip()
            if not key:
                tip.config(text="api_key 不能为空（取消请直接关窗）",
                           foreground="#c00")
                return
            try:
                cc.save_llm_config(base, key, model)
                tip.config(text="已保存 ✓ 下一题立即生效", foreground="#080")
                win.after(700, win.destroy)
            except Exception as e:
                tip.config(text="保存失败：" + str(e)[:40], foreground="#c00")

        def do_clear():
            try:
                cc.remove_llm_config()
                tip.config(text="已清除，回到纯静态答案表模式", foreground="#666666")
                win.after(700, win.destroy)
            except Exception as e:
                tip.config(text="清除失败：" + str(e)[:40], foreground="#c00")

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="we", pady=(10, 0))
        ttk.Button(btns, text="保  存", command=do_save).pack(
            side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(btns, text="清除 LLM 配置", command=do_clear).pack(
            side="left", expand=True, fill="x", padx=4)
        ttk.Button(btns, text="关闭", command=win.destroy).pack(
            side="left", expand=True, fill="x", padx=(4, 0))
        win.transient(self.root)
        e_key.focus_set()

    def _on_window_close(self):
        if self.on_close:
            self.on_close()
        self.root.destroy()

    # ---- 主循环 ----
    def run(self):
        self.root.mainloop()


# ============ 浏览器线程侧 ============

def browser_thread(page, ctx, cred, stop_event):
    """在浏览器线程中运行「登录 → 学习 → 考核」全流程。
    由 run_main 调用，整个进程生命周期内只调用一次。"""
    import course_companion as cc
    # 让 course_companion 的日志也进 GUI
    cc.log = log

    # 1) 先检查登录态
    page.goto(cred["home_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if "login" in page.url:
        if not cred.get("account"):
            log("请在窗口内填写账号/密码后点击登录")
        else:
            log("登录态失效，请在窗口内完成登录（账号/密码已预填，只需输验证码）")
        _run_gui_login_loop(page, ctx, cred, stop_event)
        if stop_event.is_set():
            return
    else:
        log("登录态有效（auth.json 会话仍可用），直接开始学习")
        _LOGIN_RESULT.put(True)  # 无需登录，立即收起表单进入监视模式

    # 2) 进入课程 → 学习循环 → 考核
    if not cc.goto_course(page, cred):
        log("进入课程失败，请人工检查浏览器窗口")
        _LOGIN_RESULT.put(False)
        return
    cc.run_learning_flow(page, ctx, cred)
    log("学习流程结束")
    _LOGIN_RESULT.put(True)


def _run_gui_login_loop(page, ctx, cred, stop_event):
    """有 GUI 的登录循环：验证码图推到窗口，用户点「登录」后回填提交。"""
    import base64
    import course_companion as cc
    while not stop_event.is_set():
        # 每次循环前把凭据填到页面
        try:
            page.fill("#userName", cred.get("account", ""))
            page.fill("#password", cred.get("password", ""))
        except Exception:
            pass
        # 请求一张新验证码 → 推到 GUI
        _push_captcha_to_gui(page)
        # 等待用户提交（_SUBMIT）或请求换一张（_CAPTCHA_REQ）
        deadline = time.time() + 300  # 5 分钟宽限
        submitted = None
        while time.time() < deadline and not stop_event.is_set():
            try:
                submitted = _SUBMIT.get(timeout=0.3)
                break
            except queue.Empty:
                # 检查「换一张」请求：先真正刷新页面上的验证码图片
                # （点图片触发换一张），再截图推给 GUI——否则只是把
                # 同一张图重截一遍，用户看不清时点它没用
                try:
                    _CAPTCHA_REQ.get_nowait()
                    try:
                        page.locator(
                            "img[alt*='验证码'], img[src*='captcha'], img[src*='code']"
                        ).first.click(timeout=3000)
                        page.wait_for_timeout(1200)
                    except Exception:
                        pass
                    _push_captcha_to_gui(page)
                    continue
                except queue.Empty:
                    pass
        if stop_event.is_set():
            return
        if submitted is None:
            log("等待登录输入超时（5 分钟），刷新验证码…")
            continue
        account, password, code = submitted
        cred["account"] = account
        cred["password"] = password
        try:
            cc.save_credentials(account, password)
        except Exception:
            pass
        # 提交登录：账号/密码/验证码 三项都以本次 GUI 提交的值为准
        # （关键：首次运行 credentials.local.json 不存在时，循环顶部预填的
        #  是空值，必须在此回填，否则首登第一下必然提交空账号密码）
        try:
            page.fill("#userName", account)
            page.fill("#password", password)
            page.fill("#captcha", code)
            page.locator("button", has_text="登录").first.click()
            page.wait_for_timeout(3000)
            if "login" not in page.url:
                try:
                    ctx.storage_state(path=cc.AUTH_STATE)
                    log("登录成功，会话已保存到 " + cc.AUTH_STATE)
                except Exception:
                    pass
                _LOGIN_RESULT.put(True)  # 登录成功 → 立即收起表单进监视模式
                return  # 登录成功，跳出循环
            log("本次未登录成功（账号/密码/验证码有误），自动重试…")
            _LOGIN_RESULT.put(False)  # 反馈失败 → 按钮恢复可点
        except Exception as e:
            log("登录提交异常：" + str(e)[:80])
            _LOGIN_RESULT.put(False)


def _push_captcha_to_gui(page):
    """截图登录页验证码 → base64 → 推给 GUI 显示。"""
    import base64
    try:
        cap = page.locator(
            "img[alt*='验证码'], img[src*='captcha'], img[src*='code']"
        ).first
        buf = cap.screenshot()
        b64 = base64.b64encode(buf).decode("ascii")
        _CAPTCHA_B64.put(b64)
    except Exception as e:
        _CAPTCHA_B64.put("__ERR__:" + str(e)[:40])


def save_credentials(account, password):
    """把账号密码 Base64 存到程序目录的 credentials.local.json。"""
    import base64, json
    import course_companion as cc
    raw = {
        "account": base64.b64encode(account.encode("utf-8")).decode("ascii"),
        "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
    }
    with open(cc.CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
    log("账号已保存到 " + cc.CRED_FILE + "（下次运行免配置）")
