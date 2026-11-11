#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评测：把 评测/考卷.json 里的每个案例在临时副本上跑一遍（每周一圈 → 经营核算），逐条核对硬断言，出一张「案例 × 断言」通过表和总分。
用法：python3 _脚本/eval.py [--root 数据目录] [--llm] [--times 3] [--case 案例id] [--keep]

确定性部分（默认）：动作数、动作类型有无、验证器、动作状态、TACOS 恒等式、枚举、核心限制变量、脚本建议路径……全部来自脚本产物，不调模型。
涉及 经营.json 的断言，在 _脚本/biz.py 还没就位时标「跳过：经营.json 不存在」，不算失败。
--llm：每个案例把模型补位跑 --times 次，报告枚举项的一致率（几次是否相同）和被校验丢弃的条数；这一步要花模型调用，开跑前先报次数。
        模型写得好不好（是否只用给定数字、是否分清事实与推断、是否给了三问）按考卷里的「模型评分口径」由人或另一个模型打分，这里不自动判。
结果：<数据目录>/评测/结果-<日期>.json，Markdown 摘要打到 stdout。仓库本身的状态库和产物不动。退出码：有断言失败＝1，否则 0。"""
import argparse, datetime, json, os, shutil, sqlite3, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import llm as LLM  # noqa: E402
import weekly as W  # noqa: E402

SKIP = shutil.ignore_patterns(".git", "工作台.db*", "运行记录", "评测", "tests", "__pycache__", ".pytest_cache", ".上一份有效结果", "截图", "流程图", "学员材料", "*.html", "skills", "agent", "docs")
CORE_VARS = ["库存", "CPC", "CVR", "广告销售额占比", "无效广告", "利润空间", "无明显限制"]
VERDICTS = ["在目标内", "超出目标", "已亏损"]
PATH_ADVICE = LLM.PATHS + ["先解决库存"]
NEEDS_BIZ = {"经营恒等式", "任务枚举合法", "路径枚举合法", "核心限制枚举合法", "判定", "核心限制变量", "核心限制变量不是", "脚本建议", "脚本建议不是", "经营不崩", "缺数有标注"}
PASS, FAIL, SKIPPED = "通过", "失败", "跳过"
jread = LLM.jread


def clean_env():
    env = {k: v for k, v in os.environ.items() if k != "FEISHU_WEBHOOK" and not k.startswith("ADS_LLM")}      # 评测不推送；确定性部分不接模型
    env.update({"ADS_LLM": "0", "PYTHONDONTWRITEBYTECODE": "1"}); return env


def set_keys(path, changes):
    P = jread(path, {}) or {}
    for k, v in changes.items():
        if v is None: P.pop(k, None)
        else: P[k] = v
    json.dump(P, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def del_key(path, keys):
    o = jread(path)
    if not isinstance(o, dict): return
    cur = o
    for k in keys[:-1]:
        cur = cur.get(k) if isinstance(cur, dict) else None
        if cur is None: return
    if isinstance(cur, dict): cur.pop(keys[-1], None)
    json.dump(o, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def has_key(o, key):
    if isinstance(o, dict): return key in o or any(has_key(v, key) for v in o.values())
    if isinstance(o, list): return any(has_key(v, key) for v in o)
    return False


def collect(ws):
    out = os.path.join(ws, "广告闭环", "输出"); G = {"数字": jread(os.path.join(out, "数字.json")), "验证器": jread(os.path.join(out, "验证器.json")), "经营": jread(os.path.join(out, "经营.json")),
                                                  "经营在": os.path.exists(os.path.join(out, "经营.json")), "task": None, "actions": []}
    try:
        c = LLM.db_ro(ws)
        if c is not None:
            t = c.execute("SELECT * FROM task").fetchone(); G["task"] = dict(t) if t else None
            G["actions"] = [dict(r) for r in c.execute("SELECT * FROM action")]; c.close()
    except sqlite3.Error: pass
    return G


def near(a, b, tol): return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= tol


def judge(name, want, G, exit_code):
    """一条断言 → (通过 / 失败 / 跳过, 说明)。"""
    B = G["经营"] if isinstance(G["经营"], dict) else None
    if name in NEEDS_BIZ and not G["经营在"]: return SKIPPED, "经营.json 不存在"
    ver = (G["task"] or {}).get("version"); cur = [a for a in G["actions"] if a["version"] == ver and a["status"] != "作废"]
    A, D, R = (B or {}).get("算账") or {}, (B or {}).get("拆解") or {}, (B or {}).get("路径") or {}
    core, advice = (D.get("核心限制") or {}).get("变量"), R.get("脚本建议")
    as_list = lambda v: v if isinstance(v, list) else [v]
    ok = lambda cond, got: (PASS if cond else FAIL, got)
    if name == "退出码": return ok(exit_code == want, f"实际 {exit_code}，期望 {want}")
    if name == "动作数": return ok(len(cur) == want, f"实际 {len(cur)} 条，期望 {want}")
    if name in ("有动作类型", "没有动作类型"):
        types = {a["type"] for a in cur}; hit = [x for x in as_list(want) if x in types]
        if name == "有动作类型": return ok(len(hit) == len(as_list(want)), "缺：" + "、".join(x for x in as_list(want) if x not in types) if len(hit) != len(as_list(want)) else "都有")
        return ok(not hit, ("不该有却有：" + "、".join(hit)) if hit else "都没有")
    if name == "验证器全过":
        ck = G["验证器"] or []; bad = [x["检查"] for x in ck if not x.get("通过")]
        return ok(bool(ck) and not bad, f"{len(ck) - len(bad)}/{len(ck)}" + (f"，没过：{'；'.join(bad)}" if bad else ""))
    if name == "动作全部待确认":
        moved = [a["no"] for a in cur if a["status"] != "待确认"]; return ok(bool(cur) and not moved, f"{len(cur) - len(moved)}/{len(cur)} 条在「待确认」")
    if name == "TACOS恒等式":
        Y = (G["数字"] or {}).get("四周") or {}
        if not Y.get("销售额"): return FAIL, "数字.json 里没有四周销售额"
        return ok(near(Y.get("广告费", 0) / Y["销售额"], Y.get("TACOS"), 1e-6), f"广告费÷销售额＝{Y.get('广告费', 0) / Y['销售额']:.4f}，TACOS＝{Y.get('TACOS')}")
    if B is None: return FAIL, "经营.json 读不出来"
    if name == "经营不崩": return ok(True, "经营.json 是合法 JSON" + ("，带「错误」字段" if B.get("错误") else ""))
    if name == "缺数有标注":
        tasks = B.get("任务") or []; all_unk = all(t.get("建议任务") == "未判定" for t in tasks)
        return ok(bool(B.get("错误")) or has_key(B, "缺") or not tasks or all_unk, "有「缺」或「错误」标注" if (B.get("错误") or has_key(B, "缺")) else ("任务为空或全是未判定" if (not tasks or all_unk) else "活动表没了，却照常给了任务，也没标缺什么"))
    if B.get("错误"): return FAIL, f"经营.json 里有错误：{str(B['错误'])[:80]}"
    if name == "经营恒等式":
        nodes = {n.get("名"): n.get("值") for n in D.get("节点") or []}; acos = next((v for k, v in nodes.items() if str(k).startswith("ACOS")), None); bad = []
        if not near(nodes.get("TACOS"), (acos or 0) * (nodes.get("广告销售额占比") or 0), 0.002): bad.append(f"TACOS {nodes.get('TACOS')} ≠ ACOS {acos} × 广告销售额占比 {nodes.get('广告销售额占比')}")
        if not near(A.get("目标TACOS"), (A.get("定价毛利率") or 0) - (A.get("目标广告后利润率") or 0), 0.0015): bad.append("目标TACOS ≠ 定价毛利率 − 目标广告后利润率")
        if not near(A.get("TACOS余量"), (A.get("目标TACOS") or 0) - (A.get("当前TACOS") or 0), 0.0015): bad.append("TACOS余量 ≠ 目标TACOS − 当前TACOS")
        Y = (G["数字"] or {}).get("四周") or {}
        if not near(A.get("当前TACOS"), Y.get("TACOS"), 0.0015): bad.append(f"当前TACOS {A.get('当前TACOS')} ≠ 数字.json 四周 TACOS {Y.get('TACOS')}")
        return ok(not bad, "；".join(bad) or "四条等式都成立")
    if name == "任务枚举合法":
        bad = [f"{t.get('活动')}＝{t.get('建议任务')}" for t in B.get("任务") or [] if t.get("建议任务") not in LLM.enums(REPO)[0]]
        return ok(not bad, "；".join(bad[:5]) or f"{len(B.get('任务') or [])} 个活动的建议任务都在六类里")
    if name == "路径枚举合法":
        bad = [str(c.get("key")) for c in R.get("候选") or [] if c.get("key") not in LLM.PATHS] + ([f"脚本建议＝{advice}"] if advice not in PATH_ADVICE else [])
        return ok(not bad, "；".join(bad) or f"候选 {len(R.get('候选') or [])} 条、脚本建议「{advice}」都合法")
    if name == "核心限制枚举合法": return ok(core in CORE_VARS, f"实际「{core}」")
    if name == "判定": return ok(A.get("判定") in as_list(want), f"实际「{A.get('判定')}」，期望 {'／'.join(as_list(want))}")
    if name == "核心限制变量": return ok(core in as_list(want), f"实际「{core}」，期望 {'／'.join(as_list(want))}")
    if name == "核心限制变量不是": return ok(core not in as_list(want), f"实际「{core}」，不该是 {'／'.join(as_list(want))}")
    if name == "脚本建议": return ok(advice in as_list(want), f"实际「{advice}」，期望 {'／'.join(as_list(want))}")
    if name == "脚本建议不是": return ok(advice not in as_list(want), f"实际「{advice}」，不该是 {'／'.join(as_list(want))}")
    return FAIL, "考卷里写了评测脚本不认识的断言"


def enum_slots(doc):
    s = {}
    if (doc.get("路径建议") or {}).get("选"): s["路径建议.选"] = doc["路径建议"]["选"]
    s.update({f"任务标签.{k}": v.get("任务") for k, v in (doc.get("任务标签") or {}).items()})
    s.update({f"搜索词补位.{k}": v for k, v in (doc.get("搜索词补位") or {}).items()})
    return s


def run_llm(ws, times):
    """同一份输入把模型补位跑 times 次：枚举项几次都一样的比例、被校验丢弃的条数。"""
    runs = [LLM.fill(ws, quiet=True) for _ in range(times)]; slots = [enum_slots(r) for r in runs]
    keys = sorted(set().union(*[set(s) for s in slots])); same = [k for k in keys if all(k in s for s in slots) and len({s[k] for s in slots}) == 1]
    return {"次数": times, "状态": [r.get("状态") for r in runs], "原因": [r.get("原因") for r in runs if r.get("原因")][:1], "调用": sum(r.get("calls", 0) for r in runs),
            "枚举项": len(keys), "一致": len(same), "一致率": (round(len(same) / len(keys), 3) if keys else None), "不一致的项": [k for k in keys if k not in same][:20],
            "丢弃": sum(len(r.get("丢弃") or []) for r in runs), "丢弃原因": [d.get("原因") for r in runs for d in (r.get("丢弃") or [])][:10]}


def run_case(case, root, llm_times=0, keep=False):
    tmp = tempfile.mkdtemp(prefix="ads-eval-"); ws = os.path.join(tmp, "ws"); shutil.copytree(root, ws, ignore=SKIP)
    try:
        for stale in ("经营.json", "AI补位.json"):
            p = os.path.join(ws, "广告闭环", "输出", stale)
            if os.path.exists(p): os.remove(p)
        set_keys(os.path.join(ws, "参数.json"), {"目标ACOS": 0.3, "补货到仓周数": 4, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"], "版本": 1, "定价毛利率": None, "目标广告后利润率": None})   # 先回到演示基线
        set_keys(os.path.join(ws, "参数.json"), case.get("改参数") or {})
        r = subprocess.run([sys.executable, os.path.join(HERE, "weekly.py"), "--root", ws, "--no-llm", "--trigger", "评测"], capture_output=True, text=True, env=clean_env(), timeout=600)
        note = ""
        for m in case.get("跑完流水线后") or []:
            if m.get("删键"): del_key(os.path.join(ws, m["删键"][0]), m["删键"][1:])
        if case.get("跑完流水线后"):
            rc, tail = W.run_biz(ws); note = "改完产物后重算经营：" + ("biz.py 还没就位" if rc is None else f"biz.py 退出码 {rc}" + (f"（{tail}）" if rc else ""))
        G = collect(ws); rows = []
        for name, want in (case.get("期望") or {}).items():
            res, why = judge(name, want, G, r.returncode); rows.append({"断言": name, "期望": want, "结果": res, "说明": why})
        out = {"id": case["id"], "说明": case.get("说明", ""), "退出码": r.returncode, "备注": note, "断言": rows,
               "摘要尾": [l for l in r.stdout.splitlines() if l.startswith(("✓", "✗"))], "模型看点": case.get("模型看点", [])}
        if llm_times: out["模型"] = run_llm(ws, llm_times)
        if keep: out["副本"] = ws
        return out
    finally:
        if not keep: shutil.rmtree(tmp, ignore_errors=True)


def markdown(res):
    cols = []
    for c in res["案例"]:
        for a in c["断言"]:
            if a["断言"] not in cols: cols.append(a["断言"])
    mark = {PASS: "✓", FAIL: "✗", SKIPPED: "－"}
    L = [f"# 广告周检评测 · {res['日期']}", "", f"考卷：{res['考卷']}（{len(res['案例'])} 个案例）｜数据目录：{res['数据目录']}",
         f"**总分 {res['通过']}/{res['通过'] + res['失败']}**（通过 {res['通过']}、失败 {res['失败']}、跳过 {res['跳过']}；跳过的不计分）", "",
         "| 案例 | " + " | ".join(cols) + " |", "|---|" + "|".join(":-:" for _ in cols) + "|"]
    for c in res["案例"]:
        by = {a["断言"]: a["结果"] for a in c["断言"]}; L.append(f"| {c['id']} | " + " | ".join(mark.get(by.get(k), "") for k in cols) + " |")
    L += ["", "✓ 通过　✗ 失败　－ 跳过（依赖的东西还没就位）　空白＝这个案例不考这一条"]
    bad = [(c["id"], a) for c in res["案例"] for a in c["断言"] if a["结果"] == FAIL]
    if bad: L += ["", "## 失败"] + [f"- {cid}｜{a['断言']}：{a['说明']}" for cid, a in bad]
    sk = {}
    for c in res["案例"]:
        for a in c["断言"]:
            if a["结果"] == SKIPPED: sk.setdefault(a["说明"], []).append(f"{c['id']}·{a['断言']}")
    if sk: L += ["", "## 跳过"] + [f"- {why}：{len(xs)} 条（{'、'.join(xs[:6])}{'…' if len(xs) > 6 else ''}）" for why, xs in sk.items()]
    if any(c.get("模型") for c in res["案例"]):
        L += ["", "## 模型补位的稳定性", "", "| 案例 | 次数 | 状态 | 调用 | 枚举项 | 几次都一样 | 一致率 | 被校验丢弃 |", "|---|:-:|---|:-:|:-:|:-:|:-:|:-:|"]
        for c in res["案例"]:
            m = c.get("模型") or {}
            L.append(f"| {c['id']} | {m.get('次数', '')} | {'／'.join(str(s) for s in m.get('状态', []))} | {m.get('调用', '')} | {m.get('枚举项', '')} | {m.get('一致', '')} | "
                     f"{'—' if m.get('一致率') is None else format(m['一致率'], '.0%')} | {m.get('丢弃', '')} |")
        why = sorted({x for c in res["案例"] for x in (c.get("模型") or {}).get("原因", [])})
        if why: L += ["", "没出枚举项的原因：" + "；".join(why)]
        L += ["", "文字写得好不好不在这里判：按考卷的「模型评分口径」逐条打分。"] + [f"- {x}" for x in res.get("模型评分口径", [])]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0]); ap.add_argument("--root", default=REPO, help="数据目录（默认仓库根）；只读它，案例都在临时副本上跑")
    ap.add_argument("--llm", action="store_true", help="每个案例再把模型补位跑 --times 次，看枚举一致率和丢弃条数（要花模型调用）"); ap.add_argument("--times", type=int, default=3)
    ap.add_argument("--case", default="", help="只跑这一个案例 id"); ap.add_argument("--keep", action="store_true", help="保留临时副本，便于事后翻看"); a = ap.parse_args()
    root = os.path.abspath(a.root); paper_p = next((p for p in (os.path.join(root, "评测", "考卷.json"), os.path.join(REPO, "评测", "考卷.json")) if os.path.exists(p)), None)
    if not paper_p: sys.exit("找不到 评测/考卷.json")
    paper = json.load(open(paper_p, encoding="utf-8")); cases = [c for c in paper["案例"] if not a.case or c["id"] == a.case]
    if not cases: sys.exit(f"考卷里没有案例「{a.case}」")
    times = 0
    if a.llm:
        ch = LLM.channel(LLM.load_config(root))
        if not ch["ok"]: print(f"--llm：{ch['原因']}，模型部分跳过，只跑确定性断言。", file=sys.stderr, flush=True)
        else:
            per = LLM.fill(root, dry_run=True, quiet=True)["将调用"]; times = max(a.times, 1)
            print(f"--llm：{len(cases)} 个案例 × {times} 次 × 每次至多 {per} 次调用 ≈ {len(cases) * times * per} 次模型调用（通道 {ch['通道']} · {ch['model']}）。", file=sys.stderr, flush=True)
    done = []
    for c in cases:
        print(f"跑案例 {c['id']} …", file=sys.stderr, flush=True); done.append(run_case(c, root, times, a.keep))
    cnt = {k: sum(1 for c in done for x in c["断言"] if x["结果"] == k) for k in (PASS, FAIL, SKIPPED)}
    res = {"日期": f"{datetime.date.today()}", "生成于": LLM.now(), "考卷": os.path.relpath(paper_p, root) if paper_p.startswith(root) else paper_p, "数据目录": root,
           "通过": cnt[PASS], "失败": cnt[FAIL], "跳过": cnt[SKIPPED], "总分": (round(cnt[PASS] / (cnt[PASS] + cnt[FAIL]), 3) if cnt[PASS] + cnt[FAIL] else None),
           "模型评分口径": paper.get("模型评分口径", []), "案例": done}
    out_dir = os.path.join(root, "评测"); os.makedirs(out_dir, exist_ok=True); out_p = os.path.join(out_dir, f"结果-{res['日期']}.json")
    json.dump(res, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(markdown(res)); print(f"\n结果 → {out_p}")
    sys.exit(1 if cnt[FAIL] else 0)


if __name__ == "__main__": main()
