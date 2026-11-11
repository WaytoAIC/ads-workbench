# -*- coding: utf-8 -*-
"""工作台 ↔ Agent / Harness 的接线（只用标准库）：
  问 Agent 转发（先走本机 Hermes，没接上再走直连模型）、健康检查、岗位卡、技能清单、Harness 七个部件的状态、群消息人闸。
密钥只在这个进程里读和用：不写文件、不进日志、不回给页面。"""
import datetime, glob, json, os, time, urllib.error, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = ["纯利型", "推自然位", "测词拓词", "收割", "防守", "未判定"]          # 活动任务六类（和 docs/架构.md 一致）
DEFAULT_CFG = {"agent": {"名字": "广告 Agent", "hermes": "http://127.0.0.1:8642", "profile": "ads-agent"},
               "llm": {"enabled": False, "api": "openai", "base": "", "model": "", "key_env": "ADS_LLM_KEY", "超时秒": 60},
               "weekly": {"schedule": "0 9 * * 1", "推送": "草稿"}, "飞书": {"webhook_env": "FEISHU_WEBHOOK", "群名": ""}}


def local_env():
    """本机的模型通道配置 agent/.env.local（不进仓）。可以直接写 ADS_LLM_KEY，也可以只写钥匙在哪个文件、叫什么名（ADS_KEY_FILE + ADS_KEY_NAME）。"""
    env = {}
    try:
        for line in open(f"{REPO}/agent/.env.local", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = os.path.expandvars(os.path.expanduser(v.strip().strip("\"'")))
    except OSError:
        return {}
    if not env.get("ADS_LLM_KEY") and env.get("ADS_KEY_FILE") and env.get("ADS_KEY_NAME"):
        try:
            for line in open(env["ADS_KEY_FILE"], encoding="utf-8"):
                if line.startswith(env["ADS_KEY_NAME"] + "="):
                    env["ADS_LLM_KEY"] = line.split("=", 1)[1].strip().strip("\"'"); break
        except OSError:
            pass
    return {k: v for k, v in env.items() if k.startswith("ADS_LLM")}


def llm_env():
    """给模型通道用的环境：真的环境变量优先，其次才是 agent/.env.local。不改 os.environ，谁要用谁显式拿。"""
    return {**local_env(), **{k: v for k, v in os.environ.items() if k.startswith("ADS_LLM")}}


def jread(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return d


def cfg(root):
    c = json.loads(json.dumps(DEFAULT_CFG))
    for p in (f"{REPO}/ads.config.json", f"{root}/ads.config.json"):          # 数据目录里的覆盖仓里的
        for k, v in (jread(p) or {}).items():
            c[k].update(v) if isinstance(v, dict) and isinstance(c.get(k), dict) else c.__setitem__(k, v)
    return c


def _server_key(profile):
    """Hermes 给每个 profile 的 API 服务密钥，放在它自己的 .env 里。读不到返回 None。"""
    try:
        for line in open(os.path.expanduser(f"~/.hermes/profiles/{profile}/.env"), encoding="utf-8"):
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        pass
    return None


def _llm(c):
    """直连模型通道：环境变量 → 配置。返回 (api, base, key, model)；没配齐返回 None。"""
    L = c["llm"]; E = llm_env()
    if E.get("ADS_LLM") == "0":
        return None
    api = E.get("ADS_LLM_API") or L.get("api") or "openai"
    base = (E.get("ADS_LLM_BASE") or L.get("base") or "").rstrip("/")
    key = E.get("ADS_LLM_KEY") or os.environ.get(L.get("key_env") or "ADS_LLM_KEY") or ""
    model = E.get("ADS_LLM_MODEL") or L.get("model") or ""
    return (api, base, key, model) if base and key and model else None


def _get(url, key=None, timeout=2.5):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {}), timeout=timeout)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


_H = {"at": 0, "v": None}


def health(root, fresh=False):
    """四样各自通不通：工作台、Hermes 网关、Agent 路由和密钥、直连模型。结果缓存 20 秒。"""
    if not fresh and _H["v"] and time.time() - _H["at"] < 20:
        return _H["v"]
    c = cfg(root); a = c["agent"]; prof = a["profile"]; base = f"{a['hermes']}/p/{prof}/v1"
    code = _get(f"{base}/health"); key = _server_key(prof)
    gw = {"名": "Hermes 网关", "ok": code != 0, "说明": f"{a['hermes']} " + ("在跑" if code else "连不上"), "怎么修": "" if code else "启动 Hermes 网关（hermes gateway start），或把 ads.config.json 里的 hermes 地址改对"}
    rt = {"名": f"Agent「{prof}」", "ok": code == 200, "说明": "路由通了" if code == 200 else ("网关没开" if not code else f"网关回 {code}：没有这个 profile"),
          "怎么修": "" if code == 200 else "运行 bash agent/install_hermes.sh 把 Agent 装进 Hermes"}
    if not key:
        ky = {"名": "对话密钥", "ok": False, "说明": f"profile「{prof}」的 .env 里没有 API_SERVER_KEY，页面问不了它", "怎么修": "给这个 profile 配一把 API 服务密钥（见 agent/README.md 第 3 步），不要写进仓库"}
    else:
        m = _get(f"{base}/models", key) if code == 200 else 0
        ky = {"名": "对话密钥", "ok": m == 200, "说明": "能对话" if m == 200 else ("等网关和路由先通" if not m else f"密钥不对（网关回 {m}）"), "怎么修": "" if m == 200 else "核对 profile 的 API_SERVER_KEY"}
    L = _llm(c)
    lm = {"名": "直连模型（备用）", "ok": bool(L), "说明": f"{L[3]}（{L[0]} 接口）" if L else "没配。Hermes 没接上时，问 Agent 和模型补位都会停用", "怎么修": "" if L else "设环境变量 ADS_LLM_BASE / ADS_LLM_KEY / ADS_LLM_MODEL 后重启工作台"}
    via = "hermes" if (rt["ok"] and ky["ok"]) else ("llm" if L else None)
    _H.update(at=time.time(), v={"可问": bool(via), "走哪条": via, "名字": a.get("名字", "广告 Agent"), "profile": prof, "项": [{"名": "工作台", "ok": True, "说明": "在跑", "怎么修": ""}, gw, rt, ky, lm]})
    return _H["v"]


OBJ = {"问题": ("问题", "归因.json 的「问题」里同名的那一项（是谁造成的、各占多少）"), "分析": ("分析", "归因.json 的「分析」里同编号的那一项（支持、反对、最多能解释多少、还缺什么）"),
       "对策": ("对策", "归因.json 的「对策」里同字母的那一项，和 选项.json"), "动作": ("动作类型", "动作清单.json 里同类型的那些行")}


def _hyp_rule(root):
    out = f"{root}/广告闭环/输出"; names = [a["指标"] for a in (jread(f"{out}/数字.json") or {}).get("异常", [])]; opts = [f"{o['key']}（{o.get('名称', '')}）" for o in (jread(f"{out}/选项.json") or [])]
    return ("对方问「还漏了什么原因」「提一条新的分析」时：先看 归因.json 里已有的几条分析和 人的判断.json，别重复提；去明细里找一条现有分析没覆盖、又查得出数的原因。"
            "每条写进一个单独的代码块，第一行写 ```新分析 ，结尾 ``` ，一次最多两条。块里严格按这个格式，一行一项：\n"
            "问题：一句问句\n来自：它在解释哪个问题（只能从这些里选，原样照抄：" + "；".join(names) + "）\n指向：它支持哪条对策，写字母，没有就留空（现有：" + "、".join(opts) + "）\n"
            "结论：一句话，带数\n把握：高、中、低三选一\n把握依据：一句话，样本多大、是确定数还是推断\n支持：\n- 一条证据，带数（出自哪个文件）\n反对：\n- 一条反过来的证据（出自哪个文件）\n"
            "还缺：\n- 缺什么｜去哪取｜拿到后能判断什么\n不成立：什么情况下这条分析不成立\n"
            "块外说明「点下面的按钮，人采纳了才会长到树上」。你自己从明细里算出来的数，在出处里写清是从哪个文件怎么算的。") if names else ""


def object_hint(obj):
    """页面把「正在看的对象」结构化地带过来：是什么、编号、名字。告诉 Agent 去哪读它，不让它猜。"""
    if not obj or obj.get("type") not in OBJ: return ""
    kind, where = OBJ[obj["type"]]
    return (f"\n对方点着的对象：{kind}「{str(obj.get('id', ''))[:40]} {str(obj.get('label', ''))[:80]}」。它的材料在 广告闭环/输出/{where}；"
            "人对各条分析下过的判断和存下的备注在 广告闭环/输入/人的判断.json，人不认同的要先看他的理由。")


# ------------------------------------------------------------------ Agent 提出的新分析：解析、核对（人采纳后才长到树上）
HYP_KEYS = ["问题", "来自", "指向", "结论", "把握", "把握依据", "不成立"]; HYP_LISTS = ["支持", "反对", "还缺"]


def parse_hypothesis(text):
    """把 ```新分析 块里的文字拆成结构。一行一个「键：值」；「支持：」「反对：」「还缺：」下面每条一行，以 - 开头。"""
    import re
    d = {k: "" for k in HYP_KEYS}; d.update({k: [] for k in HYP_LISTS}); cur = None
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line: continue
        m = re.match(r"^([\u4e00-\u9fa5]{2,4})\s*[:：]\s*(.*)$", line)
        if m and m.group(1) in HYP_KEYS + HYP_LISTS:
            k, v = m.group(1), m.group(2).strip(); cur = k if k in HYP_LISTS else None
            if k in HYP_KEYS: d[k] = v
            elif v: d[k].append(v)
            continue
        if cur and re.match(r"^([-*•]|\d+[.、])\s*", line): d[cur].append(re.sub(r"^([-*•]|\d+[.、])\s*", "", line))
        elif cur and d[cur]: d[cur][-1] += line
    def evi(x):
        m = re.search(r"[（(]([^（()）]{2,60})[)）]\s*$", x)
        return {"话": (x[:m.start()].rstrip("，,。； ") if m else x), "出处": (m.group(1) if m else "Agent 没写出处")}
    def miss(x):
        a = [t.strip() for t in re.split(r"[｜|]", x) if t.strip()]
        return {"缺什么": a[0] if a else x, "去哪取": a[1] if len(a) > 1 else "—", "拿到后": a[2] if len(a) > 2 else "—"}
    d["来自"] = [t.strip().strip("「」") for t in re.split(r"[；;、，,]", d["来自"]) if t.strip()]
    d["指向"] = (re.findall(r"[A-Z]", d["指向"]) or [""])[0]; d["把握"] = next((x for x in ("高", "中", "低") if x in d["把握"]), "")
    d["支持"], d["反对"], d["还缺"] = [evi(x) for x in d["支持"]], [evi(x) for x in d["反对"]], [miss(x) for x in d["还缺"]]
    return d


def check_hypothesis(root, d, existing=()):
    """返回 (改正后的草稿, 不能采纳的原因[], 提醒[])。带 $ 或 % 的数在脚本产物里找不到的，不拦，但标出来让人核。"""
    out = f"{root}/广告闭环/输出"; F = jread(f"{out}/数字.json") or {}; names = [a["指标"] for a in F.get("异常", [])]; opts = [o["key"] for o in (jread(f"{out}/选项.json") or [])]
    errs, flags = [], []
    if len(d["问题"]) < 6: errs.append("没有写清「问题」（要一句完整的问句）")
    if d["问题"] and any(d["问题"] == q for q in existing): errs.append("树上已经有一条一样的分析")
    fixed = []
    for n in d["来自"]:
        hit = [x for x in names if x == n] or [x for x in names if n and (n in x or x in n)]
        if len(hit) == 1: fixed.append(hit[0])
        else: errs.append(f"「来自」里的「{n}」对不上现有的问题（现有：{'、'.join(names)}）")
    d["来自"] = list(dict.fromkeys(fixed))
    if not d["来自"] and not any("来自" in e for e in errs): errs.append("没有写它来自哪个问题")
    if d["指向"] and d["指向"] not in opts: flags.append(f"「指向」写的对策 {d['指向']} 不在这一圈的对策里，已当成没写"); d["指向"] = ""
    if not d["结论"]: errs.append("没有写「结论」")
    if not d["把握"]: errs.append("没有写「把握」（高、中、低）")
    if not d["支持"] and not d["反对"]: errs.append("支持和反对的证据都是空的")
    try:
        import importlib.util
        sp = importlib.util.spec_from_file_location("llm_check", os.path.join(REPO, "_脚本", "llm.py")); L = importlib.util.module_from_spec(sp); sp.loader.exec_module(L)
        allowed = L.allowed_numbers([F, jread(f"{out}/经营.json"), jread(f"{out}/归因.json"), jread(f"{out}/动作清单.json"), jread(f"{root}/口径.json") or jread(f"{REPO}/口径.json"), jread(f"{root}/参数.json")])
        for e in d["支持"] + d["反对"]:
            bad = L.invented(e["话"], allowed)
            if bad: e["核对"] = "脚本算好的结果里找不到 " + "、".join(bad) + "：可能是它从明细里自己算的，采纳前核一下"
        for k in ("结论", "把握依据"):
            bad = L.invented(d[k], allowed)
            if bad: flags.append(f"「{k}」里的 {'、'.join(bad)} 在脚本算好的结果里找不到")
    except Exception as e:
        flags.append(f"数字没核成（{type(e).__name__}），采纳前自己对一下")
    n_bad = sum(1 for e in d["支持"] + d["反对"] if e.get("核对"))
    if n_bad: flags.append(f"{n_bad} 条证据里有数字在脚本算好的结果里找不到，已在那几条下面标出")
    return d, errs, flags


def system_prompt(root, context="", obj=None):
    return ("你在「广告周检工作台」的「问 Agent」面板里回答，对面是老板或广告运营。先给结论，再给依据（带数字，说明出自哪个文件）。"
            f"数字只用工作台目录 {root} 里脚本算好的：广告闭环/输出/数字.json（事实与异常）、经营.json（算账、拆解、广告任务、利润路径、决策表）、"
            "归因.json（每个问题是谁造成的、每条分析的正反证据和把握）、动作清单.json、验证器.json、读回状态.json（人驳回过什么）；阈值看 口径.json。没有的数就直说缺什么、去哪取，不估不编。"
            "判断方法按已装的 ads-* 技能，先看 ads-router。每条建议说清三件事：为什么做、预期改变什么、多久复盘。"
            "你不审批、不改目标、不改状态库、不上传广告后台、不发任何消息：动作通过还是驳回，人在「行动」页点。"
            "要花钱调用取数接口之前，先说清调什么、调几次，等对方确认。回答控制在一屏内，用简单 Markdown（加粗、列表、小表格）。"
            "对方要「发到群」「同步给团队」时：把群消息完整写在一个代码块里，第一行写 ```群消息 ，结尾 ``` ；块里只放正文；"
            "块外用一句话说明「点下面的按钮才会发出去」，不要说已经发出。数据是脱敏演示数据时，不猜原品类。"
            "对方让你「深挖」「补证据」「找反例」某条分析时：先把归因.json 里它的「还缺」逐条看，能从现有文件里查到的就去查；"
            "然后把结果完整写在一个代码块里，第一行写 ```归因补充 ，结尾 ``` ；块里分三段，每段以「支持：」「反对：」「还缺：」开头，每条一行、带数字、括号里写出自哪个文件；"
            "块外用一句话说你现在更信还是更不信这条分析、为什么，并说明「点下面的按钮才会存到这个节点」。你自己不改任何文件。"
            + _hyp_rule(root)
            + (f"\n对方当前在工作台看的是：{context}" if context else "") + object_hint(obj))


def _pack(root):
    """直连模型没有工具可用，把这一圈的要点直接塞进提示词（只放脚本算好的）。"""
    out = f"{root}/广告闭环/输出"; F = jread(f"{out}/数字.json") or {}; B = jread(f"{out}/经营.json") or {}; A = jread(f"{out}/动作清单.json") or []
    cnt = {}
    for x in A:
        cnt[x.get("类型")] = cnt.get(x.get("类型"), 0) + 1
    pack = {"异常": F.get("异常"), "四周": F.get("四周"), "逐周": F.get("逐周"), "库存": F.get("库存"), "算账": B.get("算账"), "拆解": B.get("拆解"), "广告任务": B.get("任务"),
            "利润路径": B.get("路径"), "决策表": B.get("决策表"), "归因": jread(f"{out}/归因.json"), "人的判断": jread(f"{root}/广告闭环/输入/人的判断.json"), "本轮动作按类型": cnt, "人驳回过": (jread(f"{out}/读回状态.json") or {}).get("被驳回的动作"), "口径": jread(f"{root}/口径.json") or jread(f"{REPO}/口径.json")}
    return "\n你没有读文件的工具。下面是脚本这一圈算好的全部要点（JSON），只能用这里面的数：\n" + json.dumps(pack, ensure_ascii=False, default=str)[:90000]


class _Once:
    """把一段完整回答包成 OpenAI 流式格式的两行，页面那头不用分两种解析。"""
    def __init__(self, text):
        self.lines = [b"data: " + json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False).encode() + b"\n", b"\n", b"data: [DONE]\n", b"\n"]
    def readline(self): return self.lines.pop(0) if self.lines else b""
    def close(self): pass


def open_agent(root, messages, context="", obj=None):
    """返回 (上游响应, 走哪条)。上游是 OpenAI 兼容的 SSE 流，原样转给页面。接不上抛 RuntimeError（话是给人看的）。"""
    hl = health(root); c = cfg(root); a = c["agent"]
    hist = [{"role": m["role"], "content": str(m.get("content", ""))} for m in messages if m.get("role") in ("user", "assistant")][-12:]
    if not hist:
        raise RuntimeError("没有问题内容")
    if hl["走哪条"] == "hermes":
        url, key, model, sysm = f"{a['hermes']}/p/{a['profile']}/v1/chat/completions", _server_key(a["profile"]), a["profile"], system_prompt(root, context, obj)
    elif hl["走哪条"] == "llm":
        api, base, key, model = _llm(c); sysm = system_prompt(root, context, obj) + _pack(root)
        if api == "anthropic":                                                    # Anthropic 接口：一次取完，包成一条流式消息给页面
            try:
                r = urllib.request.urlopen(urllib.request.Request(f"{base}/v1/messages", data=json.dumps({"model": model, "max_tokens": 2000, "system": sysm, "messages": hist}).encode(),
                                           headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}), timeout=c["llm"].get("超时秒", 60) * 3)
                text = "".join(x.get("text", "") for x in json.loads(r.read()).get("content", []) if x.get("type") == "text")
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"上游返回 {e.code}（模型接口）")
            except Exception as e:
                raise RuntimeError(f"连不上模型接口：{type(e).__name__}")
            return _Once(text), "llm"
        url = f"{base}/chat/completions"
    else:
        bad = next((x for x in hl["项"][1:4] if not x["ok"]), hl["项"][3])
        raise RuntimeError(f"Agent 还没接通：{bad['说明']}。{bad['怎么修']}")
    req = urllib.request.Request(url, data=json.dumps({"model": model, "stream": True, "messages": [{"role": "system", "content": sysm}] + hist}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=600), hl["走哪条"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"上游返回 {e.code}（{'Hermes' if hl['走哪条'] == 'hermes' else '模型接口'}）")
    except Exception as e:
        raise RuntimeError(f"连不上{'Hermes' if hl['走哪条'] == 'hermes' else '模型接口'}：{type(e).__name__}")


def post_to_group(root, text, who):
    """人在页面点了才会走到这里。发到配置的群机器人，留痕到 运行记录/sent.log。"""
    c = cfg(root)["飞书"]; hook = os.environ.get(c.get("webhook_env") or "FEISHU_WEBHOOK", ""); name = c.get("群名") or "配置的群"
    if not hook:
        return 400, {"error": f"还没配群机器人：设环境变量 {c.get('webhook_env') or 'FEISHU_WEBHOOK'}（飞书群机器人的 Webhook）后重启工作台。草稿可以先复制。"}
    ok, info = False, ""
    try:
        r = urllib.request.urlopen(urllib.request.Request(hook, data=json.dumps({"msg_type": "text", "content": {"text": text}}).encode(), headers={"Content-Type": "application/json"}), timeout=15)
        j = json.loads(r.read() or b"{}"); ok = (j.get("code", j.get("StatusCode", 0)) == 0); info = "" if ok else str(j.get("msg") or j)[:200]
    except Exception as e:
        info = f"{type(e).__name__}"
    os.makedirs(f"{root}/运行记录", exist_ok=True)
    with open(f"{root}/运行记录/sent.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\t{'ok' if ok else 'fail'}\t{who}\t{name}\t{len(text)} 字\t{info}\n")
    return (200, {"ok": True, "group": name, "at": f"{datetime.datetime.now():%H:%M}"}) if ok else (502, {"error": f"没发出去：{info or '群机器人没有确认'}"})


def skills(root):
    """仓里的技能包清单，以及装进 Agent 没有。"""
    prof = cfg(root)["agent"]["profile"]; out = []
    for p in sorted(glob.glob(f"{REPO}/skills/*/SKILL.md")):
        name = desc = ""; txt = open(p, encoding="utf-8").read()
        if txt.startswith("---"):
            for line in txt.split("---", 2)[1].splitlines():
                if line.startswith("name:"): name = line.split(":", 1)[1].strip().strip('"\'')
                if line.startswith("description:"): desc = line.split(":", 1)[1].strip().strip('"\'')
        name = name or os.path.basename(os.path.dirname(p))
        out.append({"名": name, "说明": desc, "已装进Agent": os.path.isdir(os.path.expanduser(f"~/.hermes/profiles/{prof}/skills/{name}"))})
    return out


def runlog(root, n=12):
    p = f"{root}/运行记录/runs.jsonl"; rows = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8").read().splitlines()[-n:]:
            try: rows.append(json.loads(line))
            except ValueError: pass
    return rows[::-1]


def weekly_draft(root):
    fs = sorted(glob.glob(f"{root}/运行记录/周报-*.md"))
    return {"文件": os.path.basename(fs[-1]), "正文": open(fs[-1], encoding="utf-8").read()} if fs else None


def cron_job(root):
    """定时装上没有：看 Hermes 这个 profile 的定时清单里有没有指向 weekly 的那一条（只读文件，不调命令）。"""
    prof = cfg(root)["agent"]["profile"]
    for p in glob.glob(os.path.expanduser(f"~/.hermes/profiles/{prof}/cron/*.json")) + glob.glob(os.path.expanduser(f"~/.hermes/profiles/{prof}/cron*.json")):
        try: txt = open(p, encoding="utf-8").read()
        except OSError: continue
        if "ads-weekly" in txt or "ads_weekly" in txt:
            return True
    return False


def harness(root, st):
    """Harness 七个部件各自的状态。st 是 app.state() 里已经算好的几样，避免重复读库。"""
    out = f"{root}/广告闭环/输出"; sk = skills(root); rl = runlog(root, 1); ev = sorted(glob.glob(f"{root}/评测/结果-*.json") + glob.glob(f"{REPO}/评测/结果-*.json"))
    kj = os.path.exists(f"{root}/口径.json") or os.path.exists(f"{REPO}/口径.json"); biz = os.path.exists(f"{out}/经营.json"); cj = cron_job(root)
    last = rl[0] if rl else None; res = jread(ev[-1]) if ev else None; chk = st.get("checks") or []
    row = lambda k, where, ok, note: {"部件": k, "落在哪": where, "状态": "ok" if ok is True else ("off" if ok is False else "warn"), "说明": note}
    return [
        row("触发", "页面「跑一圈」· Hermes 每周定时 · 问 Agent", True if cj else None, ("每周定时已装" if cj else "每周定时还没装（bash agent/install_hermes.sh）") + (f"；上次周跑 {last['at'][5:16]}（{last.get('trigger', '')}）" if last and last.get("at") else "；还没有周跑记录")),
        row("配方", "skills/ · 口径.json", True if (sk and kj) else None, f"技能 {len(sk)} 个（装进 Agent {sum(1 for x in sk if x['已装进Agent'])} 个）；口径.json {'在' if kj else '缺'}"),
        row("上下文", "数字.json · 经营.json · 驳回理由 · 运行记录/", True if (st.get("hasRun") and biz) else None, ("这一圈的事实和经营核算都在" if st.get("hasRun") and biz else "还没跑过，或经营核算没出") + f"；人驳回过 {st.get('rejected', 0)} 条"),
        row("工具", "_脚本/*.py（只读数据）· Hermes 上的取数技能", True, "流水线、经营核算、周跑、评测都是本机脚本；工作台不连广告后台"),
        row("护栏", "状态机 · 权限表 · 验证器 · 字段分工 · 群消息人闸", (all(x["通过"] for x in chk) if chk else None), (f"验证器 {sum(1 for x in chk if x['通过'])}/{len(chk)} 项通过" if chk else "还没跑过验证器") + "；动作一律停在待审批，群消息人点了才发"),
        row("状态", "工作台.db · 广告闭环/输出/", True, f"任务 {st.get('status', '')} · v{st.get('version', 0)} · 待审批 {st.get('pending', 0)} 条"),
        row("评估", "评测/ · _脚本/eval.py · 每条动作的复盘日", (not res.get("失败")) if res else None, (f"最近一次评测 {res.get('日期', '')}：{res.get('通过', '?')} 条通过、{res.get('失败', '?')} 条失败" + (f"、{res['跳过']} 条跳过" if res.get("跳过") else "")) if res else "还没跑过评测（python3 _脚本/eval.py）"),
    ]
