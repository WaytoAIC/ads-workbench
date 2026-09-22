#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地业务工作台 · 广告周检        启动：python3 工作台/app.py        打开：http://localhost:8810
一条流程、明确的使用者、一处数据存储（SQLite）、一个操作入口（这个页面），Agent 处理、人检查。
只用 Python 标准库；分析流水线在 ../_脚本/（需要 pandas）。只监听本机，不连任何广告后台。"""
import argparse, csv, datetime, io, json, os, shutil, sqlite3, subprocess, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("--root", default=os.path.dirname(HERE)); ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8810)))
ARGS, _ = ap.parse_known_args()
ROOT = os.path.abspath(ARGS.root); SCRIPTS = os.path.join(os.path.dirname(HERE), "_脚本")
OUT, CARD_DIR, RAW = f"{ROOT}/广告闭环/输出", f"{ROOT}/广告闭环/行动卡", f"{ROOT}/_原始拉取"
DB, PARAMS = f"{ROOT}/工作台.db", f"{ROOT}/参数.json"
ROLES = ["老板", "广告运营", "供应链"]
CAN = {"改取舍": {"老板"}, "改目标": {"老板"}, "改到仓": {"老板", "供应链"}, "点动作": {"老板", "广告运营"}, "跑一圈": {"老板", "广告运营"}, "重置": {"老板"}}
NEXT = {"待确认": {"已确认", "驳回"}, "已确认": {"已执行", "待确认"}, "驳回": {"待确认"}, "已执行": {"已验证", "已确认"}, "已验证": set(), "作废": set()}
now = lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
jread = lambda p, d=None: json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
for _d in (OUT, CARD_DIR, f"{ROOT}/广告闭环/输入"): os.makedirs(_d, exist_ok=True)
LOCK = threading.Lock(); PROG = {"running": False, "steps": [], "started": None}

def db():
    c = sqlite3.connect(DB, timeout=15); c.row_factory = sqlite3.Row; c.execute("PRAGMA journal_mode=WAL"); return c
def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS task(id TEXT PRIMARY KEY, status TEXT, target_acos REAL, arrive_weeks REAL, stage TEXT, options TEXT, version INT, owner TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS run(task_id TEXT, version INT, at TEXT, trigger TEXT, inputs TEXT, summary TEXT, conclusion TEXT, seconds REAL, PRIMARY KEY(task_id, version));
        CREATE TABLE IF NOT EXISTS action(no TEXT PRIMARY KEY, task_id TEXT, version INT, item TEXT, type TEXT, campaign TEXT, object TEXT, old TEXT, new TEXT, why TEXT, spend REAL, reversible TEXT,
                                          status TEXT, by TEXT, reason TEXT, note TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS card(no TEXT PRIMARY KEY, task_id TEXT, version INT, status TEXT, fields TEXT, review_date TEXT);
        CREATE TABLE IF NOT EXISTS event(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, who TEXT, kind TEXT, ref TEXT, detail TEXT);""")
        if not c.execute("SELECT 1 FROM task").fetchone():
            P = jread(PARAMS); c.execute("INSERT INTO task VALUES(?,?,?,?,?,?,?,?,?)", (P["任务编号"], "待处理", float(P["目标ACOS"]), float(P["补货到仓周数"]), P["产品阶段"],
                      json.dumps(P.get("取舍项") or ["A", "B", "C", "E"]), 0, P.get("取舍人", "老板"), now()))
            c.execute("INSERT INTO event(at,who,kind,ref,detail) VALUES(?,?,?,?,?)", (now(), "系统", "建任务", P["任务编号"], "新建周检任务，状态＝待处理"))
def log(c, who, kind, ref, detail): c.execute("INSERT INTO event(at,who,kind,ref,detail) VALUES(?,?,?,?,?)", (now(), who, kind, ref, detail))

# ------------------------------------------------------------------ Loop：六个动作
def step(i, name, detail, ok=True, extra=None):
    PROG["steps"].append({"i": i, "name": name, "detail": detail, "ok": ok, "extra": extra, "t": round(time.time() - PROG["started"], 2)})
def loop(who="Agent", trigger="手动"):
    with LOCK:
        PROG.update({"running": True, "steps": [], "started": time.time()})
        try: _loop(who, trigger)
        except Exception as e: step(0, "意外错误", f"{type(e).__name__}: {e}", ok=False)
        finally: PROG["running"] = False
def _loop(who, trigger):
    c = db(); t = dict(c.execute("SELECT * FROM task").fetchone()); tid = t["id"]
    acts = [dict(r) for r in c.execute("SELECT * FROM action WHERE task_id=?", (tid,))]
    dist = {}
    for a in acts: dist[a["status"]] = dist.get(a["status"], 0) + 1
    rej = [a for a in acts if a["status"] == "驳回"]; done = [a for a in acts if a["status"] in ("已确认", "已执行", "已验证")]
    key = lambda a: {"动作编号": a["no"], "类型": a["type"], "广告活动": a["campaign"], "对象": a["object"], "驳回理由": a["reason"]}
    json.dump({"读回时间": now(), "被驳回的动作": [key(a) for a in rej], "已处理的动作": [key(a) for a in done]}, open(f"{OUT}/读回状态.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    dist_s = "、".join(f"{k} {v}" for k, v in dist.items()) or "空"
    step(1, "读取状态", f"任务 {tid}：状态＝{t['status']}。动作库：{dist_s}。人驳回过 {len(rej)} 条、确认过 {len(done)} 条。", extra=[f"驳回理由：{a['object']} —— {a['reason']}" for a in rej])
    if t["status"] != "待处理":
        step(2, "判断下一步", f"状态是「{t['status']}」，没有待处理的任务 → 本轮不跑。"); step(6, "判断停止条件", "停。等人把任务标成「待处理」，或到复盘日。"); return
    miss = [n for n, v in (("目标 ACOS", t["target_acos"]), ("补货到仓周数", t["arrive_weeks"]), ("产品阶段", t["stage"])) if v in (None, "")]
    if miss:
        c.execute("UPDATE task SET status='遇到问题', updated_at=? WHERE id=?", (now(), tid)); log(c, "Agent", "遇到问题", tid, f"缺输入：{'、'.join(miss)}。没有跑，上一份有效结果未动。"); c.commit()
        step(2, "判断下一步", f"缺输入：{'、'.join(miss)} → 标「遇到问题」，不拿旧数据硬跑，上一份有效结果不动。", ok=False); step(6, "判断停止条件", "停。补齐后重新标「待处理」。接手人：老板。"); return
    P0 = jread(PARAMS)
    inputs = {"目标ACOS": t["target_acos"], "补货到仓周数": t["arrive_weeks"], "产品阶段": t["stage"], "取舍项": sorted(json.loads(t["options"])), "数据窗口": P0.get("窗口近"),
              "规则版本": __import__("hashlib").md5(open(f"{ROOT}/分组规则.json", "rb").read()).hexdigest()[:8]}   # 新报表导入后窗口会变、改了分组规则，都算输入变了
    last = c.execute("SELECT * FROM run WHERE task_id=? ORDER BY version DESC LIMIT 1", (tid,)).fetchone()
    if last and json.loads(last["inputs"]) == inputs:
        c.execute("UPDATE task SET status='待核对', updated_at=? WHERE id=?", (now(), tid)); log(c, "Agent", "跳过", tid, "重复触发：输入没变，不重跑。"); c.commit()
        step(2, "判断下一步", "输入和上一轮一模一样，结果已在库里 → 同一份输入不重复跑。"); step(6, "判断停止条件", "停。状态改回「待核对」。"); return
    ver = (last["version"] + 1) if last else 1
    diff = "；".join(f"{k}：{json.loads(last['inputs']).get(k)} → {v}" for k, v in inputs.items() if json.loads(last["inputs"]).get(k) != v) if last else ""
    step(2, "判断下一步", (f"输入变了（{diff}）→ 重跑，出 v{ver}。" if last else "首次运行 → 跑 v1。"))
    c.execute("UPDATE task SET status='处理中', updated_at=? WHERE id=?", (now(), tid)); c.commit()
    P = dict(P0); P.update({"目标ACOS": inputs["目标ACOS"], "补货到仓周数": inputs["补货到仓周数"], "产品阶段": inputs["产品阶段"], "取舍项": inputs["取舍项"], "版本": ver, "触发方式": trigger})
    bak = f"{ROOT}/.上一份有效结果"; shutil.rmtree(bak, ignore_errors=True); shutil.copytree(f"{ROOT}/广告闭环", bak)
    json.dump(P, open(PARAMS, "w", encoding="utf-8"), ensure_ascii=False, indent=1); t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "render.py")], capture_output=True, text=True, env=dict(os.environ, ADS_ROOT=ROOT))
    secs = round(time.time() - t0, 1); checks = jread(f"{OUT}/验证器.json", [])
    if r.returncode != 0:
        err = (r.stderr.strip().splitlines() or ["?"])[-1][:300]; bad = [x["检查"] for x in checks if not x["通过"]]
        shutil.rmtree(f"{ROOT}/广告闭环", ignore_errors=True); shutil.copytree(bak, f"{ROOT}/广告闭环"); json.dump(P0, open(PARAMS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        c.execute("UPDATE task SET status='遇到问题', updated_at=? WHERE id=?", (now(), tid)); log(c, "Agent", "遇到问题", tid, f"流水线失败：{err}。已恢复上一份有效结果。"); c.commit()
        step(3, "执行", f"失败：{err}", ok=False); step(4, "验证", "未通过：" + ("；".join(bad) or "流水线中断"), ok=False); step(6, "判断停止条件", "停，交人接手。上一份有效结果已恢复，没有被覆盖。"); return
    rows, R = jread(f"{OUT}/动作清单.json"), jread(f"{OUT}/渲染结果.json"); summ = R["汇总"]
    step(3, "执行", f"读报表 → 分组账 → 异常 → {summ['合计']} 条动作 → 行动卡 → 报告，用时 {secs} 秒。只读数据，没有碰广告后台。", extra=[f"{k} {v} 条" for k, v in summ["按类型"].items()])
    step(4, "验证", f"验证器 {sum(1 for x in checks if x['通过'])}/{len(checks)} 项通过。", extra=[("✓ " if x["通过"] else "✗ ") + x["检查"] for x in checks])
    voided = c.execute("UPDATE action SET status='作废', note=?, updated_at=? WHERE task_id=? AND status='待确认'", (f"输入已变，由 v{ver} 取代", now(), tid)).rowcount
    kept = c.execute("SELECT COUNT(*) FROM action WHERE task_id=? AND status NOT IN ('作废','待确认')", (tid,)).fetchone()[0]
    stale = summ.get("已确认但新输入下不再建议", [])
    for no in stale: c.execute("UPDATE action SET note=?, updated_at=? WHERE no=?", (f"⚠ 输入已变（v{ver}），新输入下规则不再建议这一条，请复核：撤回还是照做", now(), no))
    for x in rows:
        c.execute("INSERT OR REPLACE INTO action VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (x["动作编号"], tid, ver, x["取舍项"], x["类型"], str(x["广告活动"]), str(x["对象"]), str(x["现值"]), str(x["新值"]), x["依据"],
                  (float(x["近14天涉及花费"]) if x.get("近14天涉及花费") not in ("", None) else None), x["可逆"], "待确认", None, None, None, now()))
    c.execute("UPDATE card SET status='已结案' WHERE task_id=? AND status!='已结案'", (tid,))
    cno = f"C-{tid}" + ("" if ver == 1 else f"v{ver}"); fields = [cell.split("|")[2].strip() for cell in R["行动卡"]]
    c.execute("INSERT OR REPLACE INTO card VALUES(?,?,?,?,?,?)", (cno, tid, ver, "待确认", json.dumps(fields, ensure_ascii=False), P["复盘日"]))
    F = jread(f"{OUT}/数字.json"); top = F["异常"][0]
    concl = f"最该管的是「{top['指标']}」：{top['现值']}（{top['参照']}）。{top['说明']}。泛词＋跑偏词只占花费 {F['泛词加跑偏']['占比']:.1%}，不是主要问题。"
    c.execute("INSERT OR REPLACE INTO run VALUES(?,?,?,?,?,?,?,?)", (tid, ver, now(), trigger, json.dumps(inputs, ensure_ascii=False), json.dumps(summ, ensure_ascii=False), concl, secs))
    c.execute("UPDATE task SET status='待核对', version=?, updated_at=? WHERE id=?", (ver, now(), tid))
    log(c, "Agent", "写入", f"{tid} v{ver}", f"新动作 {len(rows)} 条；作废 {voided} 条没人点过的旧动作；保留 {kept} 条人处理过的；提醒复核 {len(stale)} 条；沿用上轮已确认 {summ.get('沿用上轮已确认',0)} 条；被驳回不再提 {len(summ.get('上轮被驳回不再提',[]))} 条"); c.commit()
    step(5, "写入状态", f"新动作 {len(rows)} 条入库，全部「待确认」；作废 {voided} 条没人点过的旧动作；人处理过的 {kept} 条原样保留；被驳回的 {len(summ.get('上轮被驳回不再提',[]))} 条不再提；{len(stale)} 条旧确认标了「请复核」。行动卡 {cno}。")
    step(6, "判断停止条件", f"停在「待核对」，等人处理 {len(rows)} 条动作。下一次触发：{P['复盘日']} 复盘，或输入改变。永久停止：连续两次缺资料、单日花费翻三倍、行动卡结案。")

# ------------------------------------------------------------------ 状态快照（页面只读这一个接口）
def sanlan():
    p = f"{OUT}/诊断-三栏表.md"; out = {"事实": [], "推断": [], "未知": []}
    if not os.path.exists(p): return out
    cur = None
    for line in open(p, encoding="utf-8"):
        line = line.rstrip()
        if line.startswith("## "): cur = next((k for k in out if k in line), None)
        elif cur and (line[:2] in ("- ",) or (line[:1].isdigit() and ". " in line[:4])): out[cur].append(line.split(" ", 1)[1] if line.startswith("- ") else line.split(". ", 1)[1])
    return out
def state():
    c = db(); t = dict(c.execute("SELECT * FROM task").fetchone()); t["options"] = json.loads(t["options"]); P = jread(PARAMS)
    runs = [dict(r) for r in c.execute("SELECT * FROM run ORDER BY version DESC")]
    for r in runs: r["inputs"], r["summary"] = json.loads(r["inputs"]), json.loads(r["summary"])
    has = bool(runs); card = c.execute("SELECT * FROM card ORDER BY version DESC LIMIT 1").fetchone()
    calls = {}
    if os.path.exists(f"{RAW}/调用记录.jsonl"):
        for l in open(f"{RAW}/调用记录.jsonl", encoding="utf-8"): k = json.loads(l)["path"]; calls[k] = calls.get(k, 0) + 1
    inv = sorted(jread(f"{RAW}/库存与动销-按SKU.json", []), key=lambda r: -(r[5] or 0))
    return {"meta": {"店铺": P["显示店铺"], "产品": P["显示产品"], "数据标记": P.get("数据标记", ""), "周期": f"{P['窗口前'][0]} ～ {P['窗口近'][1]}", "复盘日": P["复盘日"], "今天": P["今天"], "归因未满": P.get("归因未满", "")},
            "roles": ROLES, "can": {k: sorted(v) for k, v in CAN.items()}, "task": t, "hasRun": has, "facts": jread(f"{OUT}/数字.json") if has else None, "sanlan": sanlan() if has else None,
            "options": jread(f"{OUT}/选项.json") if has else None, "checks": jread(f"{OUT}/验证器.json") if has else None, "inventory": inv if has else [],
            "actions": [dict(r) for r in c.execute("SELECT * FROM action ORDER BY version DESC, no")], "card": ({**dict(card), "fields": json.loads(card["fields"])} if card else None),
            "runs": runs, "events": [dict(r) for r in c.execute("SELECT * FROM event ORDER BY id DESC LIMIT 80")], "calls": calls, "progress": PROG}

# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        b = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False, default=str).encode() if not isinstance(body, str) else body.encode())
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"): return self.send(200, open(f"{HERE}/index.html", "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/state": return self.send(200, state())
        if u.path == "/api/progress": return self.send(200, PROG)
        if u.path == "/arch":
            f = os.path.join(os.path.dirname(HERE), "流程图", "项目架构.html")
            return self.send(200, open(f, "rb").read(), "text/html; charset=utf-8") if os.path.exists(f) else self.send(404, {"error": "还没有架构图"})
        if u.path == "/flow":
            f = os.path.join(os.path.dirname(HERE), "流程图", "工作台运转流程.html")
            return self.send(200, open(f, "rb").read(), "text/html; charset=utf-8") if os.path.exists(f) else self.send(404, {"error": "还没有流程图"})
        if u.path == "/report":
            fs = sorted(f for f in os.listdir(ROOT) if f.startswith("运行报告-") and f.endswith(".html"))
            return self.send(200, open(f"{ROOT}/{fs[-1]}", "rb").read(), "text/html; charset=utf-8") if fs else self.send(404, {"error": "还没有报告"})
        if u.path == "/api/export.csv":
            st = parse_qs(u.query).get("status", ["已确认"])[0]; buf = io.StringIO(); w = csv.writer(buf); w.writerow(["动作编号", "类型", "广告活动", "对象", "现值", "新值", "依据", "确认人", "状态"])
            for r in db().execute("SELECT * FROM action WHERE status=? ORDER BY no", (st,)): w.writerow([r["no"], r["type"], r["campaign"], r["object"], r["old"], r["new"], r["why"], r["by"], r["status"]])
            return self.send(200, ("﻿" + buf.getvalue()).encode(), "text/csv; charset=utf-8", {"Content-Disposition": "attachment; filename*=UTF-8''" + "%E5%B7%B2%E7%A1%AE%E8%AE%A4%E6%B8%85%E5%8D%95.csv"})
        self.send(404, {"error": "not found"})
    def do_POST(self):
        u = urlparse(self.path); n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"{}"); who = body.get("who") or "老板"
        deny = lambda what: self.send(403, {"error": f"「{what}」这一步，{who}没有权限。能做的人：{'、'.join(sorted(CAN[what]))}"})
        if PROG["running"] and u.path != "/api/run": return self.send(409, {"error": "Agent 正在跑，等它写完状态再操作"})
        c = db()
        if u.path == "/api/run":
            if who not in CAN["跑一圈"]: return deny("跑一圈")
            if PROG["running"]: return self.send(409, {"error": "已经在跑了"})
            threading.Thread(target=loop, args=("Agent", body.get("trigger") or "手动"), daemon=True).start(); return self.send(200, {"ok": True})
        if u.path == "/api/inputs":
            t = dict(c.execute("SELECT * FROM task").fetchone()); ch = []
            for k, col, perm, cast in (("target_acos", "target_acos", "改目标", float), ("arrive_weeks", "arrive_weeks", "改到仓", float), ("stage", "stage", "改目标", str), ("options", "options", "改取舍", None)):
                if k not in body: continue
                v = body[k]; v = None if v in ("", None) else (json.dumps(sorted(v)) if k == "options" else cast(v))
                if v == t[col] or (k == "options" and v == json.dumps(sorted(json.loads(t[col])))): continue
                if who not in CAN[perm]: return deny(perm)
                if k == "options" and not json.loads(v): return self.send(400, {"error": "至少选一条路"})
                c.execute(f"UPDATE task SET {col}=? WHERE id=?", (v, t["id"])); ch.append(f"{ {'target_acos':'目标 ACOS','arrive_weeks':'补货到仓周数','stage':'产品阶段','options':'取舍'}[k] }：{t[col]} → {v}")
            if ch or body.get("retrigger"):
                c.execute("UPDATE task SET status='待处理', updated_at=? WHERE id=?", (now(), t["id"])); log(c, who, "改输入" if ch else "重新触发", t["id"], "；".join(ch) or "输入没动，只把状态改回「待处理」"); c.commit()
            return self.send(200, {"ok": True, "changed": ch})
        if u.path.startswith("/api/action/"):
            if who not in CAN["点动作"]: return deny("点动作")
            no = u.path.rsplit("/", 1)[1]; a = c.execute("SELECT * FROM action WHERE no=?", (no,)).fetchone(); new = body.get("status")
            if not a: return self.send(404, {"error": "没有这条动作"})
            if new not in NEXT.get(a["status"], set()): return self.send(400, {"error": f"「{a['status']}」不能直接改成「{new}」"})
            if new == "驳回" and not (body.get("reason") or "").strip(): return self.send(400, {"error": "驳回必须填理由：下一轮 Agent 要读它"})
            c.execute("UPDATE action SET status=?, by=?, reason=?, updated_at=? WHERE no=?", (new, who, (body.get("reason") or "").strip() or (a["reason"] if new != "待确认" else None), now(), no))
            log(c, who, new, no, f"{a['type']}｜{a['object']}" + (f"｜理由：{body.get('reason')}" if new == "驳回" else "")); c.commit(); return self.send(200, {"ok": True})
        if u.path == "/api/bulk":
            if who not in CAN["点动作"]: return deny("点动作")
            n_ = c.execute("UPDATE action SET status='已确认', by=?, updated_at=? WHERE status='待确认' AND type=?", (who, now(), body.get("type"))).rowcount
            log(c, who, "批量确认", body.get("type"), f"{n_} 条"); c.commit(); return self.send(200, {"ok": True, "n": n_})
        if u.path == "/api/reset":
            if who not in CAN["重置"]: return deny("重置")
            c.close()
            for f in (DB, DB + "-wal", DB + "-shm", f"{OUT}/读回状态.json"):
                if os.path.exists(f): os.remove(f)
            P = jread(PARAMS); P.update({"版本": 1, "补货到仓周数": 4, "目标ACOS": 0.30, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"], "触发方式": "手动"}); json.dump(P, open(PARAMS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            PROG.update({"running": False, "steps": [], "started": None}); init_db(); return self.send(200, {"ok": True})
        self.send(404, {"error": "not found"})

if __name__ == "__main__":
    init_db(); srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), H)
    print(f"广告周检工作台 → http://localhost:{ARGS.port}    数据目录：{ROOT}", flush=True); srv.serve_forever()
