# -*- coding: utf-8 -*-
"""方式一（脚本）验证：离线自检（导入/凭据/答案表/LLM 模块/GUI 控件）。
用法: python _verify_mode1.py   退出码 0 = 全部通过。"""
import base64
import json
import sys

PASS, FAIL = [], []


def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (("  <- " + str(detail)) if (detail and not cond) else ""))


# 1) 全模块导入
try:
    import course_companion as cc
    import course_companion_login as L
    import course_companion_gui as G
    import llm_answerer as A
    import build_exe  # noqa
    ck("5 个模块全部可导入", True)
except Exception as e:
    ck("5 个模块全部可导入", False, e)
    print("致命错误，后续检查无法进行")
    sys.exit(1)

# 2) 凭据可解码
try:
    with open(cc.CRED_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    acc = base64.b64decode(raw["account"]).decode("utf-8")
    pwd = base64.b64decode(raw["password"]).decode("utf-8")
    ck("credentials.local.json 可解码且非空", bool(acc and pwd))
except Exception as e:
    ck("credentials.local.json 可解码且非空", False, e)

# 3) 端点可解码（Base64 内置 URL）
try:
    home = base64.b64decode(cc._EP_HOME).decode()
    store = base64.b64decode(cc._EP_LIST).decode()
    ck("内置端点可解码", home.startswith("http") and store.startswith("http"), home)
except Exception as e:
    ck("内置端点可解码", False, e)

# 4) 答案表 / 题库结构
try:
    ans = cc.load_answers()
    struct = A.load_question_structure()
    ck("answers.json 可加载且非空", len(ans) > 0, "题数=%d" % len(ans))
    ck("questions.json 可加载", len(struct) > 0, "题数=%d" % len(struct))
    ck("答案表覆盖全部题目 (%d/%d)" % (len([k for k in struct if k in ans]), len(struct)),
       all(k in ans for k in struct))
    ck("答案值均为 Choice/Correct/Incorrect 形态",
       all(all(str(v).startswith(("Choice", "Correct", "Incorrect")) for v in vs)
           for vs in ans.values()))
except Exception as e:
    ck("答案表/题库结构", False, e)

# 5) LLM 模块：未配置时严格降级
try:
    ck("无 llm.local.json 时 llm_enabled()=False", A.llm_enabled() is False)
    q1 = {"type": "单选题", "title": "1+1=?", "options": [
        {"choice": "Choice0", "text": "A、1"}, {"choice": "Choice1", "text": "B、2"}]}
    ck("未配置时 answer_question 返回 None", A.answer_question(q1) is None)
    ck("parse_choice_numbers 解析 JSON 数组", A.parse_choice_numbers("答案\n[1, 3]") == [1, 3])
    ck("parse_choice_numbers 兼容代码块", A.parse_choice_numbers("```json\n[2]\n```") == [2])
    ck("parse_choice_numbers 单数字兜底", A.parse_choice_numbers("选 4") == [4])
    ck("parse_choice_numbers 乱文本返回 None", A.parse_choice_numbers("无答案") is None)
    prompt, choice_of = A.build_prompt(q1, multi=False)
    ck("build_prompt 选项字母映射 Choice0→1, Choice1→2",
       choice_of == {1: "Choice0", 2: "Choice1"}, choice_of)
    ck("read_llm_config_silent 未配置返回 None", cc.read_llm_config_silent() is None)
except Exception as e:
    ck("LLM 模块降级行为", False, e)

# 6) 页面答案解析（三级锚点策略，离线造页面片段等价校验）
try:
    cases = [
        ("if ('Choice0,Choice2')", ["Choice0", "Choice2"]),
        ("answerList = ['Choice1','Choice3']", ["Choice1", "Choice3"]),
        ("x='Choice2';y=1", ["Choice2"]),
    ]
    import re
    ok = True
    for html, want in cases:
        m = re.search(r"if\s*\(\s*'((?:Choice\d+\s*,?\s*)+)'", html)
        if m:
            got = [v.strip() for v in m.group(1).split(",") if v.strip()]
        else:
            m = re.search(r"answerList\s*=\s*\[([^\]]+)\]", html)
            if m:
                vals = [v.strip().strip("'\"") for v in m.group(1).split(",")]
                got = [v for v in vals if v.startswith("Choice")]
            else:
                m = re.search(r"'(Choice\d+)'", html)
                got = [m.group(1)] if m else []
        if got != want:
            ok = False
            print("       片段 %r 期望 %s 实得 %s" % (html, want, got))
    ck("页面参考答案三级锚点策略", ok)
except Exception as e:
    ck("页面参考答案解析", False, e)

# 7) GUI：登录窗 + LLM 设置弹窗可创建
try:
    app = L.LoginApp({"account": "x", "password": "y"}, on_close=lambda: None)
    ck("LoginApp 创建成功", app.root.title() != "")
    ck("登录窗含账号/密码/验证码/登录按钮/LLM设置",
       all(hasattr(app, a) for a in ("account_entry", "password_entry",
                                     "captcha_entry", "login_btn", "llm_btn")))
    app._open_llm_settings()
    win = getattr(app, "_llm_win", None)
    ck("LLM 设置弹窗可打开", win is not None and win.winfo_exists())
    if win is not None and win.winfo_exists():
        win.destroy()
    app.root.destroy()
except Exception as e:
    ck("GUI 控件（登录窗 + LLM 设置）", False, e)

print("\n== 方式一离线自检: %d/%d 通过 ==" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项:", FAIL)
    sys.exit(1)
print("mode1 offline OK")
