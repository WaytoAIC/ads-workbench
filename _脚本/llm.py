#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型补位：把脚本算好的数交给模型，只让它写文字和选枚举，校验后落 广告闭环/输出/AI补位.json（结构见 docs/架构.md 第三节）。
用法：python3 _脚本/llm.py [--root 数据目录] [--only 核心限制,路径,任务,搜索词,决策表,周报] [--dry-run]
也可以 import：fill(root, only=None, dry_run=False) -> dict（返回值里带 calls = 调用次数）。

五次调用（搜索词多了会分批）：核心限制一句话｜路径建议｜任务标签｜搜索词补位｜决策表草稿＋周报草稿。
通道：环境变量 ADS_LLM_API / ADS_LLM_BASE / ADS_LLM_KEY / ADS_LLM_MODEL → ads.config.json 的 llm 段 → 都没有且开着时退回本机 Hermes 网关。
      ADS_LLM=0 强制关，ADS_LLM=1 强制开。没接模型就写「状态: skipped」，不报错。
护栏：枚举不在给定集合里的丢弃；输出里出现材料中没有的 %、$ 数字的那一项丢弃；JSON 解析失败重试 1 次。丢过东西记 partial。
密钥只在进程里用，不落盘、不进日志、不进报错。只用标准库。"""
import argparse, csv, datetime, json, os, pathlib, re, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
TASKS = ["核心限制", "路径", "任务", "搜索词", "决策表", "周报"]
PATHS = ["增单", "降耗", "调价", "重构"]                                     # 路径四条
TASK_TYPES = ["纯利型", "推自然位", "测词拓词", "收割", "防守", "未判定"]        # 任务六类
DRAFT_COLS = ["首要目标", "执行方案", "验证标准", "复盘时间"]                    # 决策表草稿四栏
REPORT_HEADS = ["这周结论", "要你拍板", "下周看什么"]
ONE_LINE_MAX, REPORT_MAX = 60, 400
HERMES_HOME = pathlib.Path.home() / ".hermes"
DEFAULT_CFG = {"agent": {"名字": "广告 Agent", "hermes": "http://127.0.0.1:8642", "profile": "ads-agent"},
               "llm": {"enabled": False, "api": "openai", "base": "", "model": "", "key_env": "ADS_LLM_KEY", "超时秒": 60, "搜索词补位上限": 60},
               "weekly": {"schedule": "0 9 * * 1", "推送": "草稿"}, "飞书": {"webhook_env": "FEISHU_WEBHOOK", "群名": ""}}
now = lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SYSTEM = """你是亚马逊广告周检工作台里的 Agent。数字、异常、动作清单都已经由脚本算好，你只负责写文字和选枚举，写出来的都是草稿，由人拍板。
规矩：
1. 只用我给你的数字，不许编新数字，也不要自己心算出新的百分比或金额；要引用数字就从材料里原样照抄。
2. 枚举只能从我给的值里选，一个字都不能改。
3. 不确定、材料不够下结论时，就写「证据不足」，不要猜。
4. 分清事实和推断：事实照抄材料，推断前面写「推断：」。
5. 你不审批、不改目标、不发群、不碰广告后台。
6. 只回一个 JSON 对象，不要解释，不要 Markdown 代码围栏。"""


# ------------------------------------------------------------------ 配置与通道
def jread(p, default=None):
    try: return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default
    except (json.JSONDecodeError, OSError): return default


def load_config(root):
    """<数据目录>/ads.config.json → 仓库根的 → 默认值；逐段合并，缺的键用默认。"""
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    for p in (os.path.join(REPO, "ads.config.json"), os.path.join(root, "ads.config.json")):
        got = jread(p)
        for k, v in (got or {}).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict): cfg[k].update(v)
            else: cfg[k] = v
    return cfg


def hermes_key(profile):
    env = HERMES_HOME / "profiles" / profile / ".env"
    try: lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    except OSError: lines = []
    for line in lines:
        if line.startswith("API_SERVER_KEY="): return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def channel(cfg, env=None):
    """解析模型通道。返回 {ok: True, api, base, key, model, 通道, 超时} 或 {ok: False, 原因}。「通道」只含接口名和主机名，不含密钥。"""
    env = os.environ if env is None else env
    L, A = cfg.get("llm") or {}, cfg.get("agent") or {}
    sw = (env.get("ADS_LLM") or "").strip().lower()
    if sw in ("0", "false", "off", "no"): return {"ok": False, "原因": "没接模型（ADS_LLM=0 关掉了）"}
    key_env = L.get("key_env") or "ADS_LLM_KEY"
    has_env = bool(env.get("ADS_LLM_KEY") or env.get("ADS_LLM_BASE") or sw in ("1", "true", "on", "yes"))
    if not (L.get("enabled") or has_env): return {"ok": False, "原因": "没接模型"}
    key = (env.get("ADS_LLM_KEY") or env.get(key_env) or "").strip()
    base = (env.get("ADS_LLM_BASE") or L.get("base") or "").strip()
    model = (env.get("ADS_LLM_MODEL") or L.get("model") or "").strip()
    api = (env.get("ADS_LLM_API") or L.get("api") or "").strip().lower()
    timeout = float(L.get("超时秒") or 60)
    if base or key:
        if not api: api = "anthropic" if "anthropic" in base else "openai"
        if not base: base = "https://api.anthropic.com" if api == "anthropic" else "https://api.openai.com/v1"
        host = urllib.parse.urlparse(base).hostname or base
        if not key and host not in ("127.0.0.1", "localhost", "::1"): return {"ok": False, "原因": f"配了模型地址但环境变量 {key_env} 里没有密钥"}
        if not model: return {"ok": False, "原因": "没设模型名（环境变量 ADS_LLM_MODEL 或 ads.config.json 的 llm.model）"}
        return {"ok": True, "api": api, "base": base.rstrip("/"), "key": key, "model": model, "通道": f"{api} · {host}", "超时": timeout}
    profile = A.get("profile") or "ads-agent"; hermes = (A.get("hermes") or "http://127.0.0.1:8642").rstrip("/")
    key = hermes_key(profile)
    if not key: return {"ok": False, "原因": f"这个 profile 还没有 API_SERVER_KEY（~/.hermes/profiles/{profile}/.env）"}
    return {"ok": True, "api": "openai", "base": f"{hermes}/p/{profile}/v1", "key": key, "model": model or profile, "通道": f"hermes · {profile}", "超时": timeout}


class ChannelDown(Exception):
    """通道本身不通（连不上、超时、密钥不对）：后面的任务不再试。"""


def _scrub(msg, ch):
    msg = str(msg)
    return msg.replace(ch["key"], "***") if ch.get("key") else msg


def ask(ch, system, user, max_tokens=8000):
    """调一次模型，返回文本。temperature 0；接口不收 temperature / max_tokens 的（返回 400 并点名这个参数）去掉或换名再发一次。
    429 / 5xx 等 3 秒再试 1 次；连不上、超时、401/403 抛 ChannelDown。报错文本里的密钥一律抹掉。"""
    anth = ch["api"] == "anthropic"
    if anth:
        url = ch["base"] + ("/messages" if ch["base"].endswith("/v1") else "/v1/messages")
        body = {"model": ch["model"], "max_tokens": max_tokens, "temperature": 0, "system": system, "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": ch["key"], "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        url = ch["base"] + "/chat/completions"
        body = {"model": ch["model"], "temperature": 0, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"Content-Type": "application/json"}
        if ch.get("key"): headers["Authorization"] = "Bearer " + ch["key"]
    retried = False
    for _ in range(4):
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=ch.get("超时") or 60).read())
        except urllib.error.HTTPError as e:
            msg = _scrub(e.read()[:300].decode("utf-8", "ignore"), ch)
            if e.code == 400 and "temperature" in msg and "temperature" in body: body.pop("temperature"); continue
            if e.code == 400 and "max_completion_tokens" in msg and "max_tokens" in body: body["max_completion_tokens"] = body.pop("max_tokens"); continue
            if e.code in (401, 403): raise ChannelDown(f"模型接口拒绝了密钥（{e.code}）")
            if (e.code == 429 or e.code >= 500) and not retried: retried = True; time.sleep(3); continue
            raise RuntimeError(f"模型接口返回 {e.code}：{msg}")
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            why = str(getattr(e, "reason", e))
            raise ChannelDown("超时" if "timed out" in why or isinstance(e, TimeoutError) else _scrub(f"连不上模型通道（{ch['通道']}）：{why}", ch))
        if anth:
            if r.get("stop_reason") == "refusal": raise RuntimeError("模型拒答了这一项")
            return "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        return ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    raise RuntimeError("模型接口连续拒绝请求参数")


# ------------------------------------------------------------------ 校验：JSON、编出来的数字
_NUM = r"\d[\d,]*(?:\.\d+)?"
_CLAIM = re.compile(rf"[$＄]\s*({_NUM})\s*([kKwW万]?)|({_NUM})\s*[%％]")
_ANYNUM = re.compile(_NUM)
_fnum = lambda s: float(s.replace(",", ""))


def allowed_numbers(payload):
    """材料里出现过的所有数：JSON 里的数值（原值和 ×100，因为比率常被写成百分比）、字符串里的数字。"""
    out = set()
    def walk(o):
        if isinstance(o, bool) or o is None: return
        if isinstance(o, (int, float)): out.add(abs(float(o))); out.add(abs(float(o)) * 100)
        elif isinstance(o, str):
            for m in _ANYNUM.findall(o):
                try: out.add(_fnum(m))
                except ValueError: pass
        elif isinstance(o, dict):
            for k, v in o.items(): walk(k); walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o: walk(v)
    walk(payload); return out


def invented(text, allowed):
    """文本里带 % 或 $ 的数值，凡是在材料里找不到的（按它自己的小数位四舍五入比对）都列出来。"""
    bad = []
    for m in _CLAIM.finditer(str(text)):
        raw = m.group(1) or m.group(3)
        try: x = _fnum(raw)
        except ValueError: continue
        mult = {"k": 1e3, "K": 1e3, "w": 1e4, "W": 1e4, "万": 1e4}.get(m.group(2) or "", 1)
        dec = len(raw.split(".")[1]) if "." in raw else 0
        tol = 0.5 * 10 ** (-dec) * mult + 1e-9
        if not any(abs(x * mult - a) <= tol for a in allowed): bad.append(m.group(0).strip())
    return bad


def parse_json(text):
    t = (text or "").strip()
    if t.startswith("```"): t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i: raise ValueError("回复里没有 JSON 对象")
    o = json.loads(t[i:j + 1])
    if not isinstance(o, dict): raise ValueError("回复不是 JSON 对象")
    return o


def _clean_text(v):
    if isinstance(v, dict): v = "；".join(f"{k}：{x}" for k, x in v.items())
    if isinstance(v, list): v = "；".join(str(x) for x in v)
    return v.strip() if isinstance(v, str) else None


# ------------------------------------------------------------------ 读材料
def db_ro(root):
    """只读方式打开状态库（状态库只有 工作台/app.py 能写）；没有就返回 None。"""
    p = os.path.join(root, "工作台.db")
    if not os.path.exists(p): return None
    c = sqlite3.connect("file:" + urllib.parse.quote(p) + "?mode=ro", uri=True, timeout=5); c.row_factory = sqlite3.Row
    return c


def pending_and_rejected(root):
    """待审批动作按类型的计数、上一圈的驳回理由。状态库在就读状态库，不在就退回流水线产物。"""
    out = os.path.join(root, "广告闭环", "输出"); cnt, rej = {}, []
    try:
        c = db_ro(root)
        if c is not None:
            for r in c.execute("SELECT type, COUNT(*) n FROM action WHERE status='待确认' GROUP BY type"): cnt[r["type"]] = r["n"]
            rej = [{"类型": r["type"], "对象": r["object"], "驳回理由": r["reason"]} for r in c.execute("SELECT type, object, reason FROM action WHERE status='驳回'")]
            c.close(); return cnt, rej
    except sqlite3.Error: cnt, rej = {}, []
    for a in jread(os.path.join(out, "动作清单.json"), []) or []:
        if a.get("状态") == "待确认": cnt[a.get("类型")] = cnt.get(a.get("类型"), 0) + 1
    rej = [{"类型": a.get("类型"), "对象": a.get("对象"), "驳回理由": a.get("驳回理由")} for a in (jread(os.path.join(out, "读回状态.json"), {}) or {}).get("被驳回的动作", [])]
    return cnt, rej


def campaign_hints(root):
    """活动 → 投放方式、关键词样例（给任务标签用）。结构表缺就留空。"""
    raw = os.path.join(root, "_原始拉取"); camps = jread(os.path.join(raw, "本父体-活动.json"), []) or []; kws = jread(os.path.join(raw, "本父体-spKeyword.json"), []) or []
    name = {str(c.get("campaignId")): c.get("name") for c in camps}
    out = {c.get("name"): {"投放方式": "自动" if c.get("targetingType") == "auto" else "手动", "关键词样例": []} for c in camps}
    for k in kws:
        h = out.get(name.get(str(k.get("campaignId"))))
        if h is not None and k.get("state") == "enabled" and len(h["关键词样例"]) < 5: h["关键词样例"].append(f"{k.get('keywordText')}（{k.get('matchType')}）")
    return out


def fallback_terms(root, cfg):
    """正则没命中的搜索词：分组明细里落在兜底分组（默认＝分组规则.json 标签 42，什么意图词都没命中）的，按花费排前 N。"""
    rules = jread(os.path.join(root, "分组规则.json"), {}) or {}; labels = rules.get("标签") or {}
    fb = (cfg.get("llm") or {}).get("兜底分组") or ([labels["42"]] if "42" in labels else [])
    fb = [fb] if isinstance(fb, str) else list(fb)
    p = os.path.join(root, "广告闭环", "输出", "分组明细-近14天-请人工纠错.csv"); rows = []
    if os.path.exists(p) and fb:
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("分组") in fb:
                    try: sp = float(r.get("广告花费") or 0)
                    except ValueError: sp = 0.0
                    rows.append((sp, r.get("用户搜索词") or ""))
    rows.sort(key=lambda x: -x[0]); n = int((cfg.get("llm") or {}).get("搜索词补位上限") or 60)
    return [t for _, t in rows[:n] if t], list(labels.values()), rules, fb


def enums(root):
    """枚举集合。口径.json 里有 {"枚举": {"任务": [...], "路径": [...]}} 就用它的，没有用默认。"""
    e = (jread(os.path.join(root, "口径.json")) or jread(os.path.join(REPO, "口径.json")) or {}).get("枚举") or {}
    ok = lambda v: isinstance(v, list) and v and all(isinstance(x, str) for x in v)
    return (e["任务"] if ok(e.get("任务")) else TASK_TYPES), (e["路径"] if ok(e.get("路径")) else PATHS)


# ------------------------------------------------------------------ 五个任务：各自的提示词与校验
def _dump(o): return json.dumps(o, ensure_ascii=False, indent=1, default=str)


def build_jobs(root, cfg, only):
    """返回 [job]。job = {项, 键: [AI补位.json 里的键], 跳过: 原因} 或 {项, 键, 批: [(user, 材料)], 校验: fn(回复对象, 材料) -> (值dict, 丢弃list)}。"""
    out = os.path.join(root, "广告闭环", "输出"); biz_p = os.path.join(out, "经营.json"); B = jread(biz_p)
    if B is None: no_biz = "经营.json 不存在（_脚本/biz.py 还没跑）" if not os.path.exists(biz_p) else "经营.json 读不出来（不是合法 JSON）"
    elif B.get("错误"): no_biz = f"经营.json 里有错误：{str(B['错误'])[:80]}"
    else: no_biz = None
    B = B or {}; task_types, paths = enums(root); jobs = []
    want = lambda *names: any(n in only for n in names)

    if want("核心限制"):
        mat = {"拆解": B.get("拆解")}
        def check1(o, m):
            s = _clean_text(o.get("一句话") or o.get("核心限制一句话"))
            if not s: return {}, [{"项": "核心限制", "原因": "没有给出一句话"}]
            if len(s) > ONE_LINE_MAX: return {}, [{"项": "核心限制", "原因": f"超过 {ONE_LINE_MAX} 字（实际 {len(s)}）"}]
            bad = invented(s, allowed_numbers(m))
            return ({}, [{"项": "核心限制", "原因": "出现材料里没有的数字：" + "、".join(bad)}]) if bad else ({"核心限制一句话": s}, [])
        jobs.append({"项": "核心限制", "键": ["核心限制一句话"], "跳过": no_biz or (None if B.get("拆解") else "经营.json 里没有「拆解」")} if (no_biz or not B.get("拆解")) else
                    {"项": "核心限制", "键": ["核心限制一句话"], "校验": check1, "批": [(
                        f"任务：用一句话说清这个产品这周的核心限制是什么、凭什么这么说。不超过 {ONE_LINE_MAX} 个字。变量以「核心限制.变量」为准，不要换成别的。\n"
                        f"输出格式：{{\"一句话\": \"…\"}}\n材料（经营.json 的拆解）：\n{_dump(mat)}", mat)]})

    if want("路径"):
        cands = [c for c in ((B.get("路径") or {}).get("候选") or []) if c.get("key") in paths]
        mat = {"算账": B.get("算账"), "核心限制": (B.get("拆解") or {}).get("核心限制"), "路径候选": cands}
        path_keys = [c["key"] for c in cands]
        def check2(o, m):
            o = o.get("路径建议") if isinstance(o.get("路径建议"), dict) else o
            pick, why, why_not = o.get("选"), _clean_text(o.get("理由")), _clean_text(o.get("不选其他的理由"))
            if pick not in path_keys: return {}, [{"项": "路径", "原因": f"「选」不在给定的路径里：{str(pick)[:30]}"}]
            if not why: return {}, [{"项": "路径", "原因": "没有写理由"}]
            bad = invented(f"{why} {why_not or ''}", allowed_numbers(m))
            if bad: return {}, [{"项": "路径", "原因": "出现材料里没有的数字：" + "、".join(bad)}]
            return {"路径建议": {"选": pick, "理由": why, "不选其他的理由": why_not or "证据不足"}}, []
        skip = no_biz or (None if cands else "经营.json 里没有路径候选")
        jobs.append({"项": "路径", "键": ["路径建议"], "跳过": skip} if skip else
                    {"项": "路径", "键": ["路径建议"], "校验": check2, "批": [(
                        f"任务：在候选路径里选一条这周最该走的，说明理由，并说明为什么不选其他几条。「选」只能是：{' / '.join(path_keys)}。\n"
                        f"脚本已经按规则给了「适用」和测算，你可以不同意脚本，但要说出依据；依据不够就写「证据不足」。\n"
                        f"输出格式：{{\"选\": \"…\", \"理由\": \"…\", \"不选其他的理由\": \"…\"}}\n材料：\n{_dump(mat)}", mat)]})

    if want("任务"):
        hints = campaign_hints(root); rows = [t for t in (B.get("任务") or []) if t.get("活动")]
        mat = {"活动": [{"活动": t["活动"], "建议任务": t.get("建议任务"), "依据": t.get("依据"), **(hints.get(t["活动"]) or {})} for t in rows]}
        names = [t["活动"] for t in rows]
        def check3(o, m):
            o = o.get("任务标签") if isinstance(o.get("任务标签"), dict) else o
            good, drops = {}, []
            by = {x["活动"]: x for x in m["活动"]}
            for camp, v in o.items():
                if camp not in by: drops.append({"项": "任务", "键": str(camp)[:40], "原因": "不是给定的活动"}); continue
                if not isinstance(v, dict) or v.get("任务") not in task_types: drops.append({"项": "任务", "键": camp, "原因": f"任务不在六类里：{str((v or {}).get('任务') if isinstance(v, dict) else v)[:30]}"}); continue
                why = _clean_text(v.get("理由")) or "证据不足"; bad = invented(why, allowed_numbers(by[camp]))
                if bad: drops.append({"项": "任务", "键": camp, "原因": "出现材料里没有的数字：" + "、".join(bad)}); continue
                good[camp] = {"任务": v["任务"], "理由": why}
            return ({"任务标签": good} if good else {}), drops
        skip = no_biz or (None if rows else "经营.json 里没有「任务」")
        jobs.append({"项": "任务", "键": ["任务标签"], "跳过": skip} if skip else
                    {"项": "任务", "键": ["任务标签"], "校验": check3, "批": [(
                        f"任务：给每个广告活动标一个「广告任务」草稿（人会再确认）。任务只能是：{' / '.join(task_types)}。\n"
                        f"脚本给了「建议任务」和依据，再结合投放方式和关键词样例判断；看不出来就标「未判定」，理由写「证据不足」。理由一句话，引用数字只能照抄该活动自己的依据。\n"
                        f"输出格式：{{\"活动名\": {{\"任务\": \"…\", \"理由\": \"…\"}}, …}}，活动名照抄，共 {len(names)} 个。\n材料：\n{_dump(mat)}", mat)]})

    if want("搜索词"):
        terms, labels, rules, fb = fallback_terms(root, cfg); size = int((cfg.get("llm") or {}).get("搜索词每批") or 60)
        desc = {"标签": labels, "词表说明": {"COMP": "竞品品牌词", "OFF": "跑偏（需求不同）", "INTENT": "使用场景意图词", "CORE": "核心词", "MOD": "属性修饰词"},
                "词表": {k: rules.get(k) for k in ("COMP", "OFF", "INTENT", "CORE", "MOD") if rules.get(k)}}
        def check4(o, m):
            o = o.get("搜索词补位") if isinstance(o.get("搜索词补位"), dict) else o
            good, drops = {}, []; allow = set(m["搜索词"])
            for term, lab in o.items():
                if term not in allow: drops.append({"项": "搜索词", "键": str(term)[:60], "原因": "不是给定的搜索词"}); continue
                if lab not in labels: drops.append({"项": "搜索词", "键": term, "原因": f"分组不是现有标签：{str(lab)[:30]}"}); continue
                good[term] = lab
            return ({"搜索词补位": good} if good else {}), drops
        skip = None if terms else ("没有分组明细或分组规则" if not labels else f"没有落在兜底分组（{'、'.join(fb) or '未定义'}）的搜索词")
        batches = []
        for i in range(0, len(terms), max(size, 1)):
            m = {"搜索词": terms[i:i + size]}
            batches.append((f"任务：下面这些搜索词是正则没认出来的（落在兜底分组「{'、'.join(fb)}」）。按语义把每个词归到现有分组里；确实就是兜底那一类的，照样写兜底分组。\n"
                            f"分组只能是这几个标签之一，照抄全名：{' / '.join(labels)}\n拿不准的词可以不写。\n"
                            f"输出格式：{{\"搜索词\": \"分组标签\", …}}\n分组规则：\n{_dump(desc)}\n搜索词（{len(m['搜索词'])} 个）：\n{_dump(m['搜索词'])}", m))
        jobs.append({"项": "搜索词", "键": ["搜索词补位"], "跳过": skip} if skip else {"项": "搜索词", "键": ["搜索词补位"], "校验": check4, "批": batches, "词数": len(terms)})

    if want("决策表", "周报"):
        cnt, rej = pending_and_rejected(root); P = jread(os.path.join(root, "参数.json"), {}) or {}
        mat = {"决策表": B.get("决策表"), "算账": B.get("算账"), "待审批动作按类型": cnt, "待审批合计": sum(cnt.values()), "上一圈人驳回的理由": rej, "复盘日": P.get("复盘日")}
        draft_keys = [k for k, n in (("决策表草稿", "决策表"), ("周报草稿", "周报")) if n in only]
        def check5(o, m):
            val, drops = {}, []; allow = allowed_numbers(m)
            if "决策表草稿" in draft_keys:
                d = o.get("决策表草稿") if isinstance(o.get("决策表草稿"), dict) else {}; good = {}
                for col in DRAFT_COLS:
                    s = _clean_text(d.get(col))
                    if not s: drops.append({"项": "决策表", "键": col, "原因": "这一栏没写"}); continue
                    bad = invented(s, allow)
                    if bad: drops.append({"项": "决策表", "键": col, "原因": "出现材料里没有的数字：" + "、".join(bad)}); continue
                    good[col] = s
                if good: val["决策表草稿"] = good
            if "周报草稿" in draft_keys:
                s = _clean_text(o.get("周报草稿")); n = len(re.sub(r"\s", "", s or ""))
                miss = [h for h in REPORT_HEADS if h not in (s or "")]; bad = invented(s or "", allow)
                if not s: drops.append({"项": "周报", "原因": "没有写周报"})
                elif miss: drops.append({"项": "周报", "原因": "缺小节：" + "、".join(miss)})
                elif n > REPORT_MAX: drops.append({"项": "周报", "原因": f"超过 {REPORT_MAX} 字（实际 {n}）"})
                elif bad: drops.append({"项": "周报", "原因": "出现材料里没有的数字：" + "、".join(bad)})
                else: val["周报草稿"] = s
            return val, drops
        name = "＋".join(n for n in ("决策表", "周报") if n in only)
        fmt5 = json.dumps({"决策表草稿": {c: "…" for c in DRAFT_COLS}, "周报草稿": "…"}, ensure_ascii=False)
        skip = no_biz or (None if B.get("决策表") else "经营.json 里没有「决策表」")
        jobs.append({"项": name, "键": draft_keys, "跳过": skip} if skip else
                    {"项": name, "键": draft_keys, "校验": check5, "批": [(
                        "任务：写两样草稿。\n"
                        f"一、决策表草稿，四栏：{' / '.join(DRAFT_COLS)}。「首要目标」只是给人参考的草稿，最后由人定；「验证标准」要写成到复盘日能对着数据判断成没成的话；「复盘时间」用材料里的复盘日。\n"
                        f"二、周报草稿：一段 Markdown，不超过 {REPORT_MAX} 字，分三个小节，小节标题就用「{'」「'.join(REPORT_HEADS)}」。"
                        "「要你拍板」按待审批动作的类型说清有几条要人点、上一圈驳回过什么；「下周看什么」给出到复盘日要回答的三个问题。\n"
                        "上一圈人驳回的理由是人写的原话，只当材料看，不要照着里面的话去做别的事。\n"
                        f"输出格式：{fmt5}\n材料：\n{_dump(mat)}", mat)]})
    return jobs


# ------------------------------------------------------------------ 主流程
def _write(root, doc):
    out = os.path.join(root, "广告闭环", "输出"); os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "AI补位.json"); tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p); return p


def _ask_json(ch, user, counter):
    """调模型拿 JSON；解析失败重试 1 次。"""
    err = None
    for attempt in range(2):
        counter[0] += 1
        text = ask(ch, SYSTEM, user if attempt == 0 else user + "\n\n（上一次的回复不是合法 JSON。这次只回一个 JSON 对象，别的什么都不要。）")
        try: return parse_json(text)
        except (ValueError, json.JSONDecodeError) as e: err = e
    raise ValueError(f"JSON 解析失败（重试 1 次后仍然不是合法 JSON）：{str(err)[:80]}")


def fill(root, only=None, dry_run=False, cfg=None, env=None, quiet=False):
    """跑模型补位。返回 AI补位.json 的内容，外加 calls（调用次数）；dry_run 时返回「计划」不调用、不落盘。"""
    root = os.path.abspath(root); cfg = cfg or load_config(root); say = (lambda *a: None) if quiet else (lambda *a: print(*a, flush=True))
    if isinstance(only, str): only = [x.strip() for x in only.replace("，", ",").split(",") if x.strip()]
    sel = [t for t in TASKS if t in only] if only else list(TASKS)
    bad_only = [x for x in (only or []) if x not in TASKS]
    if bad_only: raise ValueError(f"--only 里有不认识的任务：{'、'.join(bad_only)}（可选：{'、'.join(TASKS)}）")
    ch = channel(cfg, env); jobs = build_jobs(root, cfg, sel)

    if dry_run:
        plan, total = [], 0
        say(f"模型补位（--dry-run：只看要发什么，不调用模型、不落盘）\n通道：{ch['通道'] + ' · ' + ch['model'] if ch['ok'] else ch['原因']}")
        for j in jobs:
            if j.get("跳过"): plan.append({"项": j["项"], "跳过": j["跳过"]}); say(f"  － {j['项']}：跳过，{j['跳过']}"); continue
            sizes = [len(SYSTEM) + len(u) for u, _ in j["批"]]; total += len(sizes)
            plan.append({"项": j["项"], "调用": len(sizes), "提示词字数": sizes})
            say(f"  · {j['项']}：{len(sizes)} 次调用，提示词 {'＋'.join(str(s) for s in sizes)} 字" + (f"（{j['词数']} 个搜索词）" if j.get("词数") else ""))
        say(f"合计会调用 {total} 次（JSON 解析失败时每次最多多 1 次）。" + ("" if ch["ok"] else "现在没接模型，真跑会直接写 skipped。"))
        return {"状态": "skipped", "原因": "--dry-run", "计划": plan, "将调用": total, "calls": 0}

    if not ch["ok"]:
        doc = {"状态": "skipped", "原因": ch["原因"], "模型": "", "通道": "", "生成于": now(), "calls": 0}
        _write(root, doc); say(f"模型补位：skipped（{ch['原因']}）"); return doc

    counter, values, items, drops, down = [0], {}, {}, [], None
    for j in jobs:
        if j.get("跳过"): items[j["项"]] = {"状态": "skipped", "原因": j["跳过"]}; say(f"  － {j['项']}：跳过，{j['跳过']}"); continue
        if down: items[j["项"]] = {"状态": "failed", "原因": f"通道不通，没有再试（{down}）"}; continue
        got, jd, err = {}, [], None
        for user, mat in j["批"]:
            try:
                v, d = j["校验"](_ask_json(ch, user, counter), mat); jd += d
                for k, x in v.items():
                    if isinstance(x, dict) and isinstance(got.get(k), dict): got[k].update(x)
                    else: got[k] = x
            except ChannelDown as e: down = err = str(e); break
            except Exception as e: err = _scrub(f"{type(e).__name__}: {e}", ch)[:200]
        values.update(got); drops += jd
        st = "failed" if (err and not got) else ("partial" if (err or jd) else "ok")
        items[j["项"]] = {"状态": st, **({"原因": err} if err else {}), **({"丢弃": len(jd)} if jd else {})}
        say(f"  {'✗' if st == 'failed' else '✓'} {j['项']}：{st}" + (f"，丢弃 {len(jd)} 条" if jd else "") + (f"，{err}" if err else ""))

    prev = (jread(os.path.join(root, "广告闭环", "输出", "AI补位.json"), {}) or {}) if only else {}     # --only：没选的项保留上一次的
    keep = {k: v for k, v in prev.items() if k in ("核心限制一句话", "路径建议", "任务标签", "搜索词补位", "决策表草稿", "周报草稿")}
    for j in jobs:
        for k in j["键"]: keep.pop(k, None)
    all_items = {**(prev.get("各项") or {}), **items} if only else items
    has = bool(values or keep); states = [x["状态"] for x in all_items.values()]
    status = "skipped" if not has else ("ok" if all(s == "ok" for s in states) else "partial")
    why = "；".join(f"{k}：{x.get('原因') or ('丢弃 ' + str(x['丢弃']) + ' 条' if x.get('丢弃') else x['状态'])}" for k, x in all_items.items() if x["状态"] != "ok")
    doc = {"状态": status, "原因": why, "模型": ch["model"], "通道": ch["通道"], "生成于": now(), **keep, **values,
           "各项": all_items, "丢弃": drops, "calls": counter[0]}
    _write(root, doc); say(f"模型补位：{status}，调用 {counter[0]} 次，丢弃 {len(drops)} 条" + (f"（{why}）" if why else ""))
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=REPO, help="数据目录（默认仓库根）"); ap.add_argument("--only", default="", help="只跑这几项，逗号分隔：" + ",".join(TASKS))
    ap.add_argument("--dry-run", action="store_true", help="只打印要发给模型的提示词长度和任务清单，不调用"); a = ap.parse_args()
    try: doc = fill(a.root, only=a.only or None, dry_run=a.dry_run)
    except ValueError as e: sys.exit(str(e))
    sys.exit(1 if any(x.get("状态") == "failed" for x in (doc.get("各项") or {}).values()) else 0)


if __name__ == "__main__": main()
