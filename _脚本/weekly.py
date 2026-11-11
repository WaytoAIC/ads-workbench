#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每周一圈（Harness 的主循环）：读回状态 → 数据体检 → 跑一圈 → 经营核算 → 模型补位 → 自检 → 起草周报 → 留痕。
用法：python3 _脚本/weekly.py [--root 数据目录] [--trigger 定时] [--dry-run] [--no-llm]

每步失败只记进 problems，不拦后面；唯一的例外是「缺输入」（参数.json 三样必填、必需报表）：直接停，退出码 2。
--dry-run：不写状态库、不跑流水线、不重算经营、不调模型、不推送、不写周报文件，只把会做什么说一遍（日志和 runs.jsonl 照记，标 dry_run）。
--no-llm：跳过模型补位，其余照跑。
留痕：<数据目录>/运行记录/weekly-<时间>.log、runs.jsonl（每圈一行）、周报-<日期>.md（只起草，不发）。
退出码：0 正常；1 有步骤失败；2 缺输入没跑。
只读报表、只通过 工作台/app.py 写本机状态库，不碰任何广告后台；动作全部停在「待确认」，等人审批。只用标准库。"""
import argparse, datetime, importlib.util, json, os, sqlite3, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import llm as LLM  # noqa: E402

REQUIRED = ("目标ACOS", "补货到仓周数", "产品阶段")          # 和 app._loop 第 ② 格查的是同三样
CIRCLE = "①②③④⑤⑥"
RAW_REQUIRED = ("本父体-SP搜索词-按天.pkl", "在线产品-本父体.json", "本父体-活动.json", "库存与动销-按SKU.json", "利润-父体-四周.json")   # 流水线硬读的五样
STRUCT_TABLES = {"活动设置": "本父体-spCampaign.json", "广告组": "本父体-spGroup.json", "关键词": "本父体-spKeyword.json", "否定关键词": "本父体-spNeKeyword.json",
                 "商品定位": "本父体-spTarget.json", "否定 ASIN": "本父体-spNeTarget.json", "广告产品": "基础-spAdProduct-全店.json"}      # 七张结构表（可缺，缺了对应动作不出）
HUMAN_STATES = ("已确认", "已执行", "已验证", "驳回")
jread = LLM.jread
pct = lambda v: "—" if not isinstance(v, (int, float)) else f"{v * 100:.1f}%"


def load_app(root):
    """用 importlib 加载 工作台/app.py。它顶层用 argparse 读 sys.argv，所以先把 argv 摆好再还原；__name__ 不是 __main__，不会起 HTTP 服务。
    工作台那边导入时会把本机的 agent/.env.local 灌进环境变量（给页面用）；这里导入完把 ADS_LLM* 还原，
    每周一圈的模型通道只认「调它的人给的环境变量 → ads.config.json → Hermes」，演练和真跑看到的是同一条通道。"""
    old, env = sys.argv, {k: v for k, v in os.environ.items() if k.startswith("ADS_LLM")}
    try:
        sys.argv = ["app.py", "--root", root]
        spec = importlib.util.spec_from_file_location("app", os.path.join(REPO, "工作台", "app.py"))
        app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app); return app
    finally:
        sys.argv = old
        for k in [k for k in os.environ if k.startswith("ADS_LLM") and k not in env]: del os.environ[k]
        os.environ.update(env)


def preflight(root):
    """参数.json 里三样必填输入缺了，连状态库都建不起来；这里先查，缺就报「缺输入」，不往下跑。"""
    p = os.path.join(root, "参数.json")
    if not os.path.exists(p): return ["参数.json 不存在"]
    P = jread(p)
    if not isinstance(P, dict): return ["参数.json 读不出来（不是合法 JSON）"]
    return [k for k in REQUIRED if P.get(k) in (None, "")]


def push(hook, text):
    req = urllib.request.Request(hook, data=json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r: return r.read().decode("utf-8", "replace")[:200]


def biz_stale(root):
    """经营.json 要不要重算：没有、里面有「错误」、或比它的输入（数字.json / 参数.json / 口径.json / biz.py）旧。"""
    out = os.path.join(root, "广告闭环", "输出"); p = os.path.join(out, "经营.json")
    if not os.path.exists(p): return True
    B = jread(p)
    if not isinstance(B, dict) or B.get("错误"): return True
    srcs = [os.path.join(out, "数字.json"), os.path.join(root, "参数.json"), os.path.join(root, "口径.json"), os.path.join(REPO, "口径.json"), os.path.join(HERE, "biz.py")]
    return any(os.path.exists(s) and os.path.getmtime(s) > os.path.getmtime(p) for s in srcs)


def run_biz(root, timeout=180):
    """跑一次 _脚本/biz.py（确定性，不调模型）。返回 (退出码或 None＝脚本还没就位, 一句话)。"""
    p = os.path.join(HERE, "biz.py")
    if not os.path.exists(p): return None, "_脚本/biz.py 还没就位"
    try: r = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=timeout, env=dict(os.environ, ADS_ROOT=root))     # 和 app.run_biz 同一种调法
    except subprocess.TimeoutExpired: return 124, f"biz.py 超时（{timeout}s）"
    tail = [l for l in (r.stderr if r.returncode else r.stdout).strip().splitlines() if l.strip()]
    return r.returncode, (tail[-1][:200] if tail else "")


class Weekly:
    def __init__(self, root, trigger="定时", dry=False, no_llm=False):
        self.root = os.path.abspath(root); self.trigger, self.dry, self.no_llm = trigger, dry, no_llm
        self.out = os.path.join(self.root, "广告闭环", "输出"); self.rec_dir = os.path.join(self.root, "运行记录")
        self.stamp = datetime.datetime.now(); self.cfg = LLM.load_config(self.root)
        self.lines, self.steps, self.problems, self.missing = [], [], [], []
        self.cells, self.ran, self.biz, self.report_path, self.log_path = [], False, None, None, None
        self.llm = {"状态": "skipped", "calls": 0, "原因": "还没走到"}; self.llm_doc = None

    # ---------- 输出 ----------
    def say(self, s=""):
        print(s, flush=True); self.lines.append(s)

    def detail(self, s): self.lines.append(s)             # 只进日志，不上屏

    def step(self, name, fn):
        t0 = time.time()
        try:
            r = fn(); ok, note = r if isinstance(r, tuple) else (True, r)
        except Exception as e:                            # 一步坏了不拦后面
            ok, note = False, f"{type(e).__name__}: {e}"
        note = str(note)
        self.steps.append({"name": name, "ok": bool(ok), "ms": int((time.time() - t0) * 1000), "note": note[:400]})
        if not ok: self.problems.append(f"{name}：{note}"[:400])
        self.say(f"{'✓' if ok else '✗'} {name}：{note}")
        return ok

    # ---------- 读状态库（只读；写只走 app.py） ----------
    def state(self):
        try:
            c = LLM.db_ro(self.root)
            if c is None: return None
            try:
                t = c.execute("SELECT * FROM task").fetchone()
                if not t: return None
                run = c.execute("SELECT * FROM run ORDER BY version DESC LIMIT 1").fetchone()
                return {"task": dict(t), "actions": [dict(r) for r in c.execute("SELECT * FROM action ORDER BY no")], "run": dict(run) if run else None}
            finally: c.close()
        except sqlite3.Error: return None

    # ---------- 1 读回状态 ----------
    def s_readback(self):
        st = self.state()
        if st is None: return "状态库还没建，这是第一次跑，没有上一圈可读"
        t = st["task"]; acts = [a for a in st["actions"] if a["status"] != "作废"]
        ok_n = sum(1 for a in acts if a["status"] in ("已确认", "已执行", "已验证")); done = sum(1 for a in acts if a["status"] in ("已执行", "已验证"))
        rej = [a for a in acts if a["status"] == "驳回"]
        for a in rej: self.detail(f"    驳回理由：{a['type']}｜{a['object']} —— {a['reason']}")
        return (f"任务 {t['id']} · {t['status']} · v{t['version']}；上一圈人通过 {ok_n} 条、驳回 {len(rej)} 条、执行了 {done} 条"
                + (f"；{len(rej)} 条驳回理由已读回（下一圈不再提）" if rej else ""))

    # ---------- 2 数据体检 ----------
    def s_inputs(self):
        miss = preflight(self.root); P = jread(os.path.join(self.root, "参数.json")); P = P if isinstance(P, dict) else {}
        raw = os.path.join(self.root, "_原始拉取")
        miss += [f"_原始拉取/{f}" for f in RAW_REQUIRED if not os.path.exists(os.path.join(raw, f))]
        if not os.path.exists(os.path.join(self.root, "分组规则.json")): miss.append("分组规则.json")
        win_a, win_b = P.get("窗口前"), P.get("窗口近")
        if P and not (isinstance(win_a, list) and isinstance(win_b, list) and len(win_a) == 2 and len(win_b) == 2): miss.append("参数.json 的数据窗口（窗口前 / 窗口近）")
        if miss:
            self.missing = miss
            return False, f"缺输入：{'、'.join(miss)} → 这一圈不跑，上一份有效结果不动。补齐后重跑，接手人：老板"
        have = [k for k, f in STRUCT_TABLES.items() if os.path.exists(os.path.join(raw, f))]; lack = [k for k in STRUCT_TABLES if k not in have]
        note = f"三样必填齐；必需报表 {len(RAW_REQUIRED)}/{len(RAW_REQUIRED)}；数据窗口 {win_a[0]}～{win_b[1]}（今天按 {P.get('今天', '?')} 算）；结构表 {len(have)}/{len(STRUCT_TABLES)}"
        if lack: note += f"（缺 {'、'.join(lack)}，对应的动作不出）"
        try:
            gap = (datetime.date.fromisoformat(str(P.get("今天"))) - datetime.date.fromisoformat(str(win_b[1]))).days
            if gap > 7: note += f"；⚠ 数据窗口比「今天」早 {gap} 天，先导新报表再看结论"
        except ValueError: pass
        return note

    # ---------- 3 跑一圈 ----------
    def s_loop(self):
        if self.dry:
            st = self.state()
            guess = "状态库还没建 → 真跑会首次运行，出 v1" if st is None else (
                f"任务状态是「{st['task']['status']}」→ 真跑不会重跑" if st["task"]["status"] != "待处理" else "任务是「待处理」→ 真跑会比对输入，变了就出新版本")
            return f"演练：会调 app.init_db() → app.loop(\"Agent\", \"{self.trigger}\")，这次不执行；{guess}"
        app = load_app(self.root); app.init_db(); app.loop("Agent", self.trigger)
        self.cells = [dict(s) for s in app.PROG["steps"]]; by = {c["i"]: c for c in self.cells}
        for c in self.cells:
            self.detail(f"    {'✗' if not c['ok'] else '✓'} {CIRCLE[c['i'] - 1] if 1 <= c['i'] <= 6 else '!'} {c['name']}：{c['detail']}")
            for x in c.get("extra") or []: self.detail(f"        {x}")
        failed = [c for c in self.cells if not c["ok"]]; self.ran = bool(5 in by and by[5]["ok"])
        if failed:
            if 2 in by and not by[2]["ok"] and "缺输入" in by[2]["detail"]: self.missing = [by[2]["detail"].split("→")[0].replace("缺输入：", "").strip()]
            return False, "；".join(f"{c['name']}：{c['detail']}" for c in failed)
        if self.ran: return f"{by[2]['detail']} {by[3]['detail'].split('，用时')[0]}；{by[4]['detail']}"
        return f"不重跑：{by[2]['detail'] if 2 in by else '没有走到判断那一格'}"

    # ---------- 4 经营核算 ----------
    def s_biz(self):
        p = os.path.join(self.out, "经营.json"); has_script = os.path.exists(os.path.join(HERE, "biz.py")); did = ""
        if self.dry: did = "演练：不重算；"
        elif has_script and biz_stale(self.root):
            rc, tail = run_biz(self.root); self.detail(f"    biz.py 退出码 {rc}：{tail}")
            if rc: return False, f"biz.py 退出码 {rc}：{tail}"
            did = "已重算；"
        elif has_script: did = "已是最新，不重算；"
        if not os.path.exists(p):
            return (False, "biz.py 跑完了但没有产出 经营.json") if (has_script and not self.dry) else f"跳过：{did}经营.json 不存在" + ("" if has_script else "（_脚本/biz.py 还没就位）")
        B = jread(p)
        if not isinstance(B, dict): return False, "经营.json 读不出来（不是合法 JSON）"
        if B.get("错误"): return False, f"经营.json 里有错误：{str(B['错误'])[:200]}"
        A = B.get("算账") or {}
        self.biz = {"判定": A.get("判定"), "核心限制": ((B.get("拆解") or {}).get("核心限制") or {}).get("变量"), "脚本建议": (B.get("路径") or {}).get("脚本建议"),
                    "当前TACOS": A.get("当前TACOS"), "目标TACOS": A.get("目标TACOS")}
        return f"{did}TACOS {pct(A.get('当前TACOS'))}／目标 {pct(A.get('目标TACOS'))} → {self.biz['判定'] or '没给判定'}；核心限制：{self.biz['核心限制'] or '没给'}；脚本建议路径：{self.biz['脚本建议'] or '没给'}"

    # ---------- 5 模型补位 ----------
    def s_llm(self):
        if self.dry:
            plan = LLM.fill(self.root, dry_run=True, cfg=self.cfg, quiet=True); ch = LLM.channel(self.cfg)
            self.llm = {"状态": "skipped", "calls": 0, "原因": "--dry-run"}
            return f"跳过：--dry-run 不调模型（{'真跑会调用 ' + str(plan['将调用']) + ' 次' if ch['ok'] else '现在' + ch['原因'] + '，真跑也会跳过'}）"
        if self.no_llm:
            self.llm = {"状态": "skipped", "calls": 0, "原因": "--no-llm"}; return "跳过：--no-llm"
        out = f"{self.root}/广告闭环/输出"; stale = f"{out}/.模型补位过期"; prev = {}
        try: prev = json.load(open(f"{out}/AI补位.json", encoding="utf-8"))
        except (OSError, ValueError): pass
        fresh = prev.get("状态") in ("ok", "partial") and not (os.path.exists(stale) and os.path.getmtime(stale) >= os.path.getmtime(f"{out}/AI补位.json"))
        if not self.ran and fresh:                                     # 这一圈没重跑、数字没变：不为同一份数字重复花模型调用
            self.llm = {"状态": prev.get("状态"), "calls": 0, "原因": "沿用上次的补位"}; self.llm_doc = prev
            return "跳过：这一圈没有重跑，数字没变，沿用上次的模型补位（不重复调用）"
        r = LLM.fill(self.root, cfg=self.cfg, quiet=True); self.llm_doc = r
        if r.get("状态") in ("ok", "partial") and os.path.exists(stale): os.remove(stale)   # 新补位对得上现在的数字了，页面可以重新显示
        self.llm = {"状态": r.get("状态"), "calls": r.get("calls", 0), "原因": r.get("原因") or "", "丢弃": len(r.get("丢弃") or [])}
        for k, x in (r.get("各项") or {}).items(): self.detail(f"    {k}：{x.get('状态')}" + (f"（{x.get('原因')}）" if x.get("原因") else ""))
        for d in r.get("丢弃") or []: self.detail(f"    丢弃 {d.get('项')}" + (f"｜{d.get('键')}" if d.get("键") else "") + f"：{d.get('原因')}")
        failed = [k for k, x in (r.get("各项") or {}).items() if x.get("状态") == "failed"]
        if r.get("状态") == "skipped" and not failed: return f"跳过：{r.get('原因')}"
        note = f"{r.get('状态')}，调用 {r.get('calls', 0)} 次，校验丢弃 {len(r.get('丢弃') or [])} 条" + (f"（{r.get('原因')}）" if r.get("原因") else "")
        return (not failed), note

    # ---------- 6 自检 ----------
    def s_check(self):
        ok, bits = True, []
        checks = jread(os.path.join(self.out, "验证器.json"), []) or []
        if checks:
            bad = [x["检查"] for x in checks if not x.get("通过")]
            bits.append(f"验证器 {len(checks) - len(bad)}/{len(checks)}" + ("" if self.ran else "（上一轮的结果）") + (f"，没过：{'；'.join(bad)}" if bad else ""))
            ok = ok and not bad
        else: bits.append("验证器还没跑过")
        st = self.state()
        if st:
            ver = st["task"]["version"]; acts = [a for a in st["actions"] if a["status"] != "作废"]; cur = [a for a in acts if a["version"] == ver]
            if self.ran:
                moved = [a["no"] for a in cur if a["status"] != "待确认"]
                bits.append(f"本圈 {len(cur)} 条新动作全部停在「待确认」" if not moved else f"✗ 本圈新动作有 {len(moved)} 条不在「待确认」：{'、'.join(moved[:5])}"); ok = ok and not moved
            else:
                dist = {}
                for a in acts: dist[a["status"]] = dist.get(a["status"], 0) + 1
                bits.append("动作库：" + ("、".join(f"{k} {v}" for k, v in dist.items()) or "空"))
            ghost = [a["no"] for a in st["actions"] if a["status"] in HUMAN_STATES and (a.get("by") or "") in ("", "Agent")]
            bits.append("没有 Agent 代人审批的动作" if not ghost else f"✗ {len(ghost)} 条动作改了状态却没有人的署名：{'、'.join(ghost[:5])}"); ok = ok and not ghost
        else: bits.append("状态库还没建")
        rows = jread(os.path.join(self.out, "动作清单.json"), []) or []
        if rows and any(r.get("状态") != "待确认" for r in rows): ok = False; bits.append("✗ 动作清单.json 里有不是「待确认」的行")
        ai = jread(os.path.join(self.out, "AI补位.json"))
        if not isinstance(ai, dict): bits.append("AI补位.json 还没有")
        else:
            wrong = []
            if ai.get("路径建议") and ai["路径建议"].get("选") not in LLM.PATHS: wrong.append("路径建议.选")
            wrong += [f"任务标签.{k}" for k, v in (ai.get("任务标签") or {}).items() if not isinstance(v, dict) or v.get("任务") not in LLM.enums(self.root)[0]]
            bits.append(f"AI补位：{ai.get('状态')}" + (f"（{ai.get('原因')}）" if ai.get("原因") else "") + ("" if self.llm_doc is not None else "，不是这一圈写的")
                        + (f"，✗ 枚举不合法：{'、'.join(wrong[:5])}" if wrong else "")); ok = ok and not wrong
        return ok, "；".join(bits)

    # ---------- 7 起草周报 ----------
    def facts(self):
        """摘要和周报共用的一份事实（全部来自状态库和脚本产物）。"""
        st = self.state(); P = jread(os.path.join(self.root, "参数.json"), {}) or {}; checks = jread(os.path.join(self.out, "验证器.json"), []) or []
        acts = st["actions"] if st else []; t = st["task"] if st else None; ver = t["version"] if t else 0
        new = [a for a in acts if a["version"] == ver and a["status"] != "作废"]; pend = [a for a in acts if a["status"] == "待确认"]
        return {"task": t, "run": st["run"] if st else None, "P": P, "version": ver, "new": new, "pending": pend,
                "review": [a for a in acts if (a.get("note") or "").startswith("⚠")], "rejected": [a for a in acts if a["status"] == "驳回"],
                "checks": checks, "win": (f"{P['窗口前'][0]} ～ {P['窗口近'][1]}" if P.get("窗口前") and P.get("窗口近") else "?")}

    def s_report(self):
        F = self.facts(); P, t = F["P"], F["task"]; day = f"{self.stamp:%Y-%m-%d}"
        draft = (self.llm_doc or {}).get("周报草稿") if (self.llm_doc or {}).get("状态") in ("ok", "partial") else None
        L = [f"# 广告周检周报 · {day}（草稿，没有发）", ""]
        L.append(f"> 来源：{'Agent 写（模型 ' + str(self.llm_doc.get('模型')) + '，过了数字与枚举校验）；末尾「脚本附注」是脚本拼的' if draft else '脚本按规则拼的（这一圈没有模型草稿：' + (self.llm.get('原因') or self.llm.get('状态') or '') + '）'}"
                 + ("　〔演练，不是正式的一圈〕" if self.dry else ""))
        L.append(f"> {P.get('显示店铺', '?')}｜{P.get('显示产品', '?')}｜数据 {F['win']}｜任务 {t['id'] if t else P.get('任务编号', '?')} · {t['status'] if t else '还没建'} · v{F['version']}")
        L.append("")
        ck = f"验证器 {sum(1 for x in F['checks'] if x.get('通过'))}/{len(F['checks'])}" if F["checks"] else "验证器还没跑过"
        opts = {o.get("key"): o.get("名称") for o in (jread(os.path.join(self.out, "选项.json"), []) or []) if isinstance(o, dict)}
        by_item = {}
        for a in F["pending"]: by_item.setdefault(a["item"], {}).setdefault(a["type"], 0); by_item[a["item"]][a["type"]] += 1
        if draft:
            L += [draft.strip(), "", "---", f"脚本附注：待审批 {len(F['pending'])} 条「待确认」；{ck}；复盘日 {P.get('复盘日', '?')}。"]
        else:
            L.append("## 这周结论")
            if F["run"] and F["run"].get("conclusion"): L.append(f"- {F['run']['conclusion']}")
            L.append("- 这一圈：" + ("演练，没有真跑" if self.dry else (f"出了 v{F['version']}，{len(F['new'])} 条新动作" if self.ran else "没有重跑（输入没变或任务不在「待处理」）")) + f"；{ck}")
            L.append(f"- 经营：TACOS {pct(self.biz['当前TACOS'])}／目标 {pct(self.biz['目标TACOS'])} → {self.biz['判定']}；核心限制：{self.biz['核心限制']}；脚本建议路径：{self.biz['脚本建议']}" if self.biz
                     else "- 经营核算这一圈没有（经营.json 不存在），利润路径和决策表先空着")
            L += ["", "## 要你拍板"]
            if F["pending"]:
                L.append(f"- 待审批 {len(F['pending'])} 条，按对策：")
                for k in sorted(by_item): L.append(f"  - {k} {opts.get(k) or ''}：{sum(by_item[k].values())} 条（" + "、".join(f"{ty} {n}" for ty, n in sorted(by_item[k].items(), key=lambda kv: -kv[1])) + "）")
            else: L.append("- 没有待审批的动作")
            if F["review"]: L.append(f"- {len(F['review'])} 条旧确认标了「请复核」：输入变了，规则不再建议，撤回还是照做要你定")
            if F["rejected"]:
                L.append(f"- 上一圈驳回 {len(F['rejected'])} 条，这一圈没有再提：")
                L += [f"  - {a['type']}｜{a['object']}：{a['reason']}" for a in F["rejected"][:5]]
            if self.biz: L.append("- 决策表的「首要目标」和各活动的广告任务，等你在工作台确认")
            L += ["", "## 下周看什么", f"- 复盘日 {P.get('复盘日', '?')}：对着每条已执行动作的「怎么算成功」回读，标「已验证」或撤回"]
            if self.biz: L.append(f"- TACOS 相对目标有没有变（现在 {self.biz['判定']}）；核心限制「{self.biz['核心限制']}」松了没有")
            L.append("- 改了目标 / 到仓周数 / 取舍，或导了新报表，把任务标回「待处理」再触发")
        if self.problems: L += ["", "## 这一圈的问题"] + [f"- {p}" for p in self.problems]
        text = "\n".join(L) + "\n"
        self.detail(""); [self.detail("    " + l) for l in text.splitlines()]; self.detail("")
        if self.dry: return "演练：按规则拼了一份，只进日志，不写 周报-*.md（免得盖掉正式那份）"
        os.makedirs(self.rec_dir, exist_ok=True)
        path = os.path.join(self.rec_dir, f"周报-{day}.md")
        with open(path, "w", encoding="utf-8") as f: f.write(text)
        self.report_path = path
        return f"{'用了模型草稿' if draft else '按规则拼了一份'} → 运行记录/{os.path.basename(path)}（只起草，没有发）"

    # ---------- 8 留痕 ----------
    def s_keep(self):
        os.makedirs(self.rec_dir, exist_ok=True)
        base = os.path.join(self.rec_dir, f"weekly-{self.stamp:%Y%m%d-%H%M%S}"); self.log_path = base + ".log"; n = 1
        while os.path.exists(self.log_path): n += 1; self.log_path = f"{base}-{n}.log"      # 同一秒里跑了两圈也不互相盖
        with open(self.log_path, "w", encoding="utf-8") as f: f.write("\n".join(self.lines) + "\n")
        return f"日志 → 运行记录/{os.path.basename(self.log_path)}；runs.jsonl 追加一行"

    # ---------- 摘要 ----------
    def summary(self):
        F = self.facts(); P, t = F["P"], F["task"]; by = {c["i"]: c for c in self.cells}
        if self.missing:
            return (f"【广告周检 Agent】{self.root}\n  ✗ 缺输入：{'、'.join(self.missing)} → 没有跑，上一份有效结果不动。\n  补齐后重跑。接手人：老板。"
                    + (f"\n运行记录：运行记录/{os.path.basename(self.log_path)}" if self.log_path else ""))
        L = [f"【广告周检 Agent】任务 {t['id']} · {t['status']} · v{t['version']} · 触发：{self.trigger} · {t['updated_at']}" if t else f"【广告周检 Agent】状态库还没建 · 触发：{self.trigger}",
             f"店铺：{P.get('显示店铺', '?')}｜产品：{P.get('显示产品', '?')}｜数据：{F['win']}"]
        if self.dry: L.append("〔演练 --dry-run：没有写状态库、没有跑流水线、没有调模型、没有推送〕")
        else:
            L.append("六格：")
            for i in range(1, 7):
                s = by.get(i)
                L.append(f"  {'✗' if s and not s['ok'] else '✓' if s else '－'} {CIRCLE[i - 1]} " + (f"{s['name']}：{s['detail']}" if s else "（没走到）"))
            if 0 in by: L.append(f"  ✗ 意外错误：{by[0]['detail']}")
        if self.ran:
            cnt = {}
            for a in F["new"]: cnt[a["type"]] = cnt.get(a["type"], 0) + 1
            L.append(f"新动作 {len(F['new'])} 条：" + "、".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])))
        else: L.append("新动作：本圈没有生成" + ("" if self.dry else "（见上面六格的原因）"))
        L.append(f"待审批：{len(F['pending'])} 条「待确认」" + (f"；另有 {len(F['review'])} 条旧确认标了「请复核」" if F["review"] else ""))
        ck = F["checks"]
        L.append((f"验证器：{sum(1 for x in ck if x.get('通过'))}/{len(ck)}" + ("" if self.ran else "（上一轮的结果）")) if ck else "验证器：还没跑过")
        L.append(f"经营：TACOS {pct(self.biz['当前TACOS'])}／目标 {pct(self.biz['目标TACOS'])} → {self.biz['判定']}｜核心限制：{self.biz['核心限制']}｜脚本建议路径：{self.biz['脚本建议']}" if self.biz
                 else "经营：这一圈没有经营核算（经营.json 不存在）")
        L.append(f"模型补位：{self.llm.get('状态')}" + (f"，调用 {self.llm['calls']} 次" if self.llm.get("calls") else "") + (f"（{self.llm['原因']}）" if self.llm.get("原因") else ""))
        if self.report_path: L.append(f"周报草稿：运行记录/{os.path.basename(self.report_path)}（只起草，没有发；要发到群，人在工作台点）")
        L.append("这一圈八步：" + " ".join(f"{'✓' if s['ok'] else '✗'}{s['name']}" for s in self.steps))
        if self.problems: L.append("✗ 有步骤失败（退出码 1）：" + "；".join(self.problems))
        L.append(f"下一次触发：{P.get('复盘日', '?')} 复盘日；或改了目标 / 到仓周数 / 取舍后标回「待处理」再触发")
        L.append(f"运行记录：运行记录/{os.path.basename(self.log_path) if self.log_path else '（没写成）'}、运行记录/runs.jsonl")
        L.append("说明：Agent 只读数据、只写本机状态库，没有碰广告后台；动作要人在工作台审批后，人去后台上传。")
        return "\n".join(L)

    # ---------- 主流程 ----------
    def run(self):
        self.say(f"广告周检 · 每周一圈 {self.stamp:%Y-%m-%d %H:%M:%S}｜数据目录 {self.root}｜触发：{self.trigger}" + ("｜--dry-run" if self.dry else "") + ("｜--no-llm" if self.no_llm else ""))
        self.step("读回状态", self.s_readback)
        if self.step("数据体检", self.s_inputs) or not self.missing:
            self.step("跑一圈", self.s_loop)
            self.step("经营核算", self.s_biz)
            self.step("模型补位", self.s_llm)
            self.step("自检", self.s_check)
            self.step("起草周报", self.s_report)
        self.step("留痕", self.s_keep)
        code = 2 if self.missing else (1 if self.problems else 0)
        text = self.summary(); self.say(""); self.say(text)
        hook = os.environ.get((self.cfg.get("飞书") or {}).get("webhook_env") or "FEISHU_WEBHOOK"); mode = (self.cfg.get("weekly") or {}).get("推送", "草稿")
        if hook and (self.dry or mode != "摘要"): self.say("没有推送飞书：" + ("--dry-run" if self.dry else f"ads.config.json 里 weekly.推送＝{mode}（改成「摘要」才会把这段运行摘要推到群；周报正文任何时候都要人在工作台点了才发）"))
        elif hook:
            try: self.say("已推送飞书：" + push(hook, text))
            except Exception as e:
                print(f"推送飞书失败：{type(e).__name__}: {e}", file=sys.stderr, flush=True); self.lines.append(f"推送飞书失败：{type(e).__name__}")
        F = self.facts()
        rec = {"at": f"{self.stamp:%Y-%m-%d %H:%M:%S}", "trigger": self.trigger, "dry_run": self.dry, "steps": self.steps, "version": F["version"],
               "actions": len(F["new"]), "pending": len(F["pending"]), "llm": {"状态": self.llm.get("状态"), "calls": self.llm.get("calls", 0)}, "problems": self.problems,
               "exit": code, "task": (F["task"] or {}).get("id"), "status": (F["task"] or {}).get("status"), "ran": self.ran, "biz": self.biz,
               "seconds": round((datetime.datetime.now() - self.stamp).total_seconds(), 1),
               "log": f"运行记录/{os.path.basename(self.log_path)}" if self.log_path else None, "report": f"运行记录/{os.path.basename(self.report_path)}" if self.report_path else None}
        try:
            os.makedirs(self.rec_dir, exist_ok=True)
            with open(os.path.join(self.rec_dir, "runs.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if self.log_path:
                with open(self.log_path, "w", encoding="utf-8") as f: f.write("\n".join(self.lines) + "\n")
        except OSError as e:
            print(f"运行记录没写成：{e}", file=sys.stderr, flush=True); code = code or 1
        return code


def run(root=REPO, trigger="定时", dry_run=False, no_llm=False):
    """给 agent_run.py、eval.py 调：跑一圈，返回退出码（0 正常 / 1 有步骤失败 / 2 缺输入没跑）。"""
    return Weekly(root, trigger, dry_run, no_llm).run()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=REPO, help="数据目录（默认仓库根）"); ap.add_argument("--trigger", default="定时", help="触发方式，写进运行记录（默认「定时」）")
    ap.add_argument("--dry-run", action="store_true", help="演练：不写状态库、不跑流水线、不调模型、不推送"); ap.add_argument("--no-llm", action="store_true", help="跳过模型补位")
    a = ap.parse_args(); sys.exit(run(a.root, a.trigger, a.dry_run, a.no_llm))


if __name__ == "__main__": main()
