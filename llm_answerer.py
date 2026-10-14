# -*- coding: utf-8 -*-
"""
LLM 自动答题模块(方式一/方式二共用,纯 HTTP,零新增依赖)
================================================================
把「题干 + 选项」交给 DeepSeek 等 OpenAI 兼容接口的 /chat/completions,
解析出正确选项编号(1..N),映射回平台的 Choice0.. 值。

配置文件 llm.local.json(放程序目录;已被 .gitignore 排除,不入库):
    {
      "base_url": "https://api.deepseek.com",
      "api_key":  "sk-xxxx",
      "model":    "deepseek-chat"
    }

约定:
  · llm_enabled()  False 表示未配置(或配置损坏)→ 全部降级为原行为
  · answer_question()  返回 ["Choice1", "Choice3", ...] 或 None(不确定/失败)
  · 题目来源:优先用 questions.json 解析后的结构;缺失时回退到实时抓取考核页
"""
import json
import os
import re
import urllib.request

LLM_CONFIG_FILE = "llm.local.json"
_QUESTIONS_FILE = "questions.json"


# ==================== 配置 ====================

def _load_cfg():
    """读 llm.local.json;返回 dict 或 None。结果惰性记忆(含失败),
    避免反复读坏文件;运行中把文件放到程序目录后,下次进程启动才生效。
    占位符 key(含 PASTE)视为未配置,避免启动即静默 401。"""
    global _cfg, _cfg_loaded
    if _cfg_loaded:
        return _cfg
    _cfg_loaded = True
    if not os.path.exists(LLM_CONFIG_FILE):
        return None
    try:
        with open(LLM_CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        base = (cfg.get("base_url") or "").rstrip("/")
        key = (cfg.get("api_key") or "").strip()
        model = (cfg.get("model") or "").strip()
        if not (base and key and model):
            return None
        if "PASTE" in key.upper() or key in ("", "sk-..."):
            return None  # 占位符 key → 视为未配置
        return {"base_url": base, "api_key": key, "model": model}
    except Exception:
        return None


def _load_cfg():
    """读 llm.local.json;返回 dict 或 None。
    每次都实时读取(不缓存):运行中改文件或 GUI「LLM 设置」保存后,
    下一题立即生效。占位符 key(含 PASTE)视为未配置,避免静默 401。"""
    if not os.path.exists(LLM_CONFIG_FILE):
        return None
    try:
        with open(LLM_CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        base = (cfg.get("base_url") or "").rstrip("/")
        key = (cfg.get("api_key") or "").strip()
        model = (cfg.get("model") or "").strip()
        if not (base and key and model):
            return None
        if "PASTE" in key.upper() or key in ("", "sk-..."):
            return None  # 占位符 key → 视为未配置
        return {"base_url": base, "api_key": key, "model": model}
    except Exception:
        return None


def llm_enabled():
    """已配置可用 LLM 才返回 True(调用方据此决定是否提示人工)。
    实时读取配置文件,GUI/手改文件随时生效,无需重启。"""
    return _load_cfg() is not None


# ==================== 题库 ====================

def load_question_structure():
    """把 questions.json 读成 {题号: {"type","title","options":[{"choice","text"}]}}。
    文件不存在/损坏时返回空 dict(调用方回退到实时抓取)。"""
    if not os.path.exists(_QUESTIONS_FILE):
        return {}
    try:
        with open(_QUESTIONS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        out = {}
        for item in raw:
            q = {
                "type": item.get("type", ""),
                "title": item.get("title", ""),
                "options": [
                    {"choice": o.get("choice"), "text": o.get("text", "")}
                    for o in item.get("options", [])
                ],
            }
            out[int(item.get("no", 0))] = q
        return out
    except Exception:
        return {}


# ==================== 题目构造 ====================

def _option_index_map(options):
    """1-based 选项序号 → 平台 choice 值。
    平台选项文本形如「A、xxx」,字母 A/B/C/... 依次对应 Choice0/1/2/...,
    所以「第 k 个选项」的 Choice 编号 = 第 k 个选项在按选项文本出现的
    字母顺序里的位置。直接用选项文本首个字母(非数字/非中文)的序号映射。"""
    choice_of = {}
    letter_seq = []
    for o in options:
        m = re.match(r"\s*([A-Za-z])\s*[、,.．]?", str(o.get("text", "")))
        letter_seq.append(m.group(1).upper() if m else "?")
    order = sorted(
        range(len(options)),
        key=lambda i: (letter_seq[i] == "?", letter_seq[i]))
    for i, j in enumerate(order):
        choice_of[i + 1] = options[j].get("choice", "")
    return choice_of


def build_prompt(q, multi=True):
    """生成 LLM 提示词。q 形如 {"type","title","options":[{choice,text}]}。
    multi=True 多选题允许多选;False(单选/是非)强制恰选一个。
    选项按 Choice0/1/2... 的自然顺序展示为第 1/2/3 项,
    要求 LLM 末尾单独一行输出 JSON 数组(选项序号 1..N),便于解析。"""
    choice_of = _option_index_map(q.get("options", []))
    lines = [
        "你是一名答题助手。请根据题目作答,只输出 JSON,不要解释。",
        "题目类型:" + (q.get("type") or ("多选题" if multi else "单选题")),
        "题干:" + str(q.get("title", "")).strip(),
    ]
    for i, o in enumerate(q.get("options", []), start=1):
        lines.append("%d. %s" % (i, o.get("text", "")))
    if multi:
        lines.append("请选择所有正确选项(可能 1~%d 个),输出形如 [1,3]。" % len(choice_of))
    else:
        lines.append("请选择唯一正确选项,输出形如 [2]。")
    lines.append("最后一行必须单独输出 JSON 数组,如 [1, 3],不要包含其他文字。")
    return "\n".join(lines), choice_of


def parse_choice_numbers(text):
    """从 LLM 回复里解析选项编号集合(1-based);解析失败返回 None。
    策略:① 找 JSON 数组(兼容 ```json 代码块)→ ② 找 [..,..] → ③ 单数字兜底。"""
    if not text:
        return None
    nums = None
    m = re.search(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]", text)
    if m:
        nums = [int(x) for x in m.group(1).split(",") if x.strip()]
    if not nums:
        m = re.search(r"(\d+)", text)
        if m:
            nums = [int(m.group(1))]
    if not nums:
        return None
    return sorted(set(n for n in nums if 1 <= n <= 99))


def answer_question(q, multi=True):
    """让 LLM 回答一题。成功返回 ["Choice1","Choice3",...] 列表;
    未配置/调用失败/解析失败/无有效选项 → None(调用方保持原行为)。"""
    cfg = _load_cfg()
    if not cfg:
        return None
    prompt, choice_of = build_prompt(q, multi=multi)
    if not choice_of:
        return None
    try:
        data = json.dumps({
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": "你是精确答题助手,只按格式输出。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 300,
        }).encode("utf-8")
        req = urllib.request.Request(
            cfg["base_url"] + "/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + cfg["api_key"],
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
    except Exception:
        return None

    nums = parse_choice_numbers(text)
    if not nums:
        return None
    # 只保留真实存在的选项;单选/是非强制 1 个
    out = [choice_of[n] for n in nums if n in choice_of and choice_of[n]]
    if not out:
        return None
    if not multi:
        out = out[:1]
    return out
