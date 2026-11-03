#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 入口：不起网页，直接跑一圈 Loop，打印一段纯文本摘要；设了 FEISHU_WEBHOOK 就同时推到飞书群。
用法：python3 _脚本/agent_run.py [--root 数据目录] [--trigger 定时]
只读数据、只写本机状态库（<数据目录>/工作台.db），不碰任何广告后台。六格有失败（或缺输入）退出码 2。只用标准库。"""
import argparse, importlib.util, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
REQUIRED = ("目标ACOS", "补货到仓周数", "产品阶段")     # 和 app._loop 第 ② 格查的是同三样
CIRCLE = "①②③④⑤⑥"


def load_app(root):
    """用 importlib 加载 工作台/app.py。它顶层用 argparse 读 sys.argv，所以先把 argv 摆好；__name__ 不是 __main__，不会起 HTTP 服务。"""
    sys.argv = ["app.py", "--root", root]
    spec = importlib.util.spec_from_file_location("app", os.path.join(REPO, "工作台", "app.py"))
    app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app); return app


def preflight(root):
    """参数.json 里三样必填输入缺了，连状态库都建不起来；这里先查，缺就报「缺输入」，不往下跑。"""
    p = os.path.join(root, "参数.json")
    if not os.path.exists(p): return ["参数.json 不存在"]
    P = json.load(open(p, encoding="utf-8"))
    return [k for k in REQUIRED if P.get(k) in (None, "")]


def summary(S, trigger):
    t, meta, steps = S["task"], S["meta"], S["progress"]["steps"]
    by_i = {s["i"]: s for s in steps}; failed = [s for s in steps if not s["ok"]]
    ran = 5 in by_i and by_i[5]["ok"]
    L = [f"【广告周检 Agent】任务 {t['id']} · {t['status']} · v{t['version']} · 触发：{trigger} · {t['updated_at']}",
         f"店铺：{meta['店铺']}｜产品：{meta['产品']}｜数据：{meta['周期']}", "六格："]
    for i in range(1, 7):
        s = by_i.get(i)
        L.append(f"  {'✗' if s and not s['ok'] else '✓' if s else '－'} {CIRCLE[i-1]} " + (f"{s['name']}：{s['detail']}" if s else "（没走到）"))
    if 0 in by_i: L.append(f"  ✗ 意外错误：{by_i[0]['detail']}")
    if ran:
        new = [a for a in S["actions"] if a["version"] == t["version"]]; cnt = {}
        for a in new: cnt[a["type"]] = cnt.get(a["type"], 0) + 1
        L.append(f"新动作 {len(new)} 条：" + "、".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])))
    else: L.append("新动作：本圈没有生成（见上面六格的原因）")
    pending = sum(1 for a in S["actions"] if a["status"] == "待确认"); review = sum(1 for a in S["actions"] if (a.get("note") or "").startswith("⚠"))
    L.append(f"待审批：{pending} 条「待确认」" + (f"；另有 {review} 条旧确认标了「请复核」" if review else ""))
    ck = S.get("checks") or []
    L.append(f"验证器：{sum(1 for x in ck if x['通过'])}/{len(ck)}" + ("" if ran else "（上一轮的结果）") if ck else "验证器：还没跑过")
    L.append(f"下一次触发：{meta['复盘日']} 复盘日；或改了目标 / 到仓周数 / 取舍后标回「待处理」再触发")
    L.append("说明：Agent 只读数据、只写本机状态库，没有碰广告后台；动作要人在工作台审批后，人去后台上传。")
    return "\n".join(L), bool(failed)


def push(hook, text):
    req = urllib.request.Request(hook, data=json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r: return r.read().decode("utf-8", "replace")[:200]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0]); ap.add_argument("--root", default=REPO, help="数据目录（默认仓库根）")
    ap.add_argument("--trigger", default="定时", help="触发方式，写进运行记录（默认「定时」）"); a = ap.parse_args(); root = os.path.abspath(a.root)
    miss = preflight(root)
    if miss:
        text = f"【广告周检 Agent】{root}\n  ✗ ② 判断下一步：缺输入：{'、'.join(miss)} → 没有跑，上一份有效结果不动。\n  补齐 参数.json 后重跑。接手人：老板。"; failed = True
    else:
        try:
            app = load_app(root); app.init_db(); app.loop("Agent", a.trigger); text, failed = summary(app.state(), a.trigger)
        except Exception as e: text, failed = f"【广告周检 Agent】{root}\n  ✗ 意外错误：{type(e).__name__}: {e}", True
    print(text, flush=True)
    hook = os.environ.get("FEISHU_WEBHOOK")
    if hook:
        try: print("已推送飞书：" + push(hook, text), flush=True)
        except Exception as e: print(f"推送飞书失败：{type(e).__name__}: {e}", file=sys.stderr, flush=True)
    sys.exit(2 if failed else 0)


if __name__ == "__main__": main()
