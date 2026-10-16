# -*- coding: utf-8 -*-
"""历史回放（模拟）：假设 Agent 从上线第 2 周起每周一跑一圈，回放前三圈。
数据是真实历史（已脱敏）；每圈按当时能看到的 14 天数据出动作；审批与执行是模拟的；
「下周结果」取的是该对象下一周的真实表现——当时并没有真的执行，所以只说明下周发生了什么，不代表动作效果。
输出 <数据目录>/历史回放.json，页面只读，不写状态库。    用法：python3 _脚本/history_sim.py   （ADS_ROOT 指定数据目录）"""
import json, os, collections, datetime as dt
import pandas as pd
import pipeline as pl
from pipeline import P, NUM, ROOT, usd, pct

TARGET, CAP = float(P["目标ACOS"]), 0.15
F = json.load(open(f"{pl.OUT}/数字.json", encoding="utf-8")); W, BE = F["逐周"], F["四周"]["盈亏线"]
t, _ = pl.derived("报表-adTargeringReport-0.pkl", ["日期", "投放", "匹配类型", "广告活动", "广告活动ID"]); t["日期"] = pd.to_datetime(t["日期"])
for n in NUM: t[n] = pd.to_numeric(t[n], errors="coerce").fillna(0)
cr, _ = pl.derived("报表-adCampaignReport-0.pkl", ["日期", "广告活动", "广告活动ID"]); cr["日期"] = pd.to_datetime(cr["日期"])
for n in NUM: cr[n] = pd.to_numeric(cr[n], errors="coerce").fillna(0)
s = pl.s
bid = {(pl.cname[str(k["campaignId"])], k["keywordText"].lower(), k["matchType"]): float(k["bid"]) for k in pl.kws if k["state"] == "enabled"}
MT = {"精确匹配": "exact", "词组匹配": "phrase", "广泛匹配": "broad"}
budget = {c["name"]: float(c["budget"]) for c in pl.camps_l}
exact_kw = {k["keywordText"].lower() for k in pl.kws if k["matchType"] == "exact"}
D0 = pd.Timestamp(P["窗口前"][0])                      # 第 1 周第一天（与利润报表的周对齐）
MEM = {"bid": {}, "rej": set(), "paused": set(), "touched": {}}     # 跨圈记忆：执行后的竞价、人驳回过的、已暂停的、上一圈刚动过的（观察期）
REJ = ["新品期先保曝光，这周不动", "这是品牌防守位，花费再高也留着", "样本太少，再看一周", "运营有意在测这个词"]


def stat(df):
    sp, sl, ck, od = df["广告花费"].sum(), df["广告销售额"].sum(), int(df["广告点击量"].sum()), int(df["广告订单量"].sum())
    return {"花费": round(float(sp), 2), "点击": ck, "订单": od, "ACOS": (float(sp / sl) if sl else None), "CPC": (float(sp / ck) if ck else None)}


def run_at(k):
    """第 k 周结束后的周一跑：看最近 14 天（第 1 圈只有 7 天），出动作。"""
    end = D0 + pd.Timedelta(days=7 * k - 1); start = max(D0, end - pd.Timedelta(days=13)); nxt = (end + pd.Timedelta(days=1), end + pd.Timedelta(days=7))
    win, nwin = (lambda df: df[(df["日期"] >= start) & (df["日期"] <= end)]), (lambda df: df[(df["日期"] >= nxt[0]) & (df["日期"] <= nxt[1])])
    lwin = lambda df: df[(df["日期"] > end - pd.Timedelta(days=7)) & (df["日期"] <= end)]
    acts, back = [], collections.Counter()
    ok_ = lambda a: (a["campaign"], str(a.get("kw") or a.get("target") or ""), a.get("match") or a.get("kind") or "")
    def add(**a):
        o = ok_(a)
        if (a["type"], o) in MEM["rej"]: back["上圈驳回，不再原样提"] += 1; return
        if o in MEM["paused"]: back["已暂停，跳过"] += 1; return
        if MEM["touched"].get(o) == k - 1 and a["type"] not in ("来源组否定",): back["上圈刚动过，观察一周"] += 1; return
        acts.append(a)
    # 关键词：降价 / 提价 / 暂停（手动关键词投放）
    tk = win(t[t["匹配类型"].isin(MT)]).groupby(["广告活动", "投放", "匹配类型"])[NUM].sum()
    for (camp, kw, mt), r in tk.iterrows():
        b = bid.get((camp, str(kw).lower(), MT[mt]))
        if b is None: continue
        if (camp, str(kw), MT[mt]) in MEM["bid"]: b = MEM["bid"][(camp, str(kw), MT[mt])]; back["读回执行后的新竞价"] += 1
        ck, od, sp, sl = int(r["广告点击量"]), int(r["广告订单量"]), r["广告花费"], r["广告销售额"]; ac = sp / sl if sl else None
        key = dict(campaign=camp, kw=kw, match=MT[mt], obj_kind="kw")
        if od == 0 and ck >= 15: add(type="暂停关键词", level="关键词", field="State", old="enabled", new="paused", why=f"近 {(end-start).days+1} 天 {ck} 次点击 0 单，花 {usd(sp)}", **key)
        elif ac and ac > BE and ck >= 10: add(type="关键词降竞价", level="关键词", field="Bid", old=f"${b:.2f}", new=f"${max(0.2, b*(1-CAP)):.2f}", why=f"ACOS {pct(ac,0)} 超盈亏线 {pct(BE)}；单次降 15%", **key)
        elif ac and ac < TARGET * 0.6 and od >= 3: add(type="关键词提竞价", level="关键词", field="Bid", old=f"${b:.2f}", new=f"${b*1.10:.2f}", why=f"ACOS {pct(ac,0)} 远低于目标 {pct(TARGET,0)}、{od} 单；提 10% 抢量", **key)
    # 商品定位：ASIN 定位 / 类目定位 / 自动四组
    tp = win(t[~t["匹配类型"].isin(MT) & (t["匹配类型"] != "主题匹配")]).groupby(["广告活动", "投放", "匹配类型"])[NUM].sum()
    for (camp, tg, mt), r in tp.iterrows():
        ck, od, sp, sl = int(r["广告点击量"]), int(r["广告订单量"]), r["广告花费"], r["广告销售额"]; ac = sp / sl if sl else None; cpc = sp / ck if ck else 0
        auto = camp.startswith("自动"); kind = "自动投放组" if auto else ("ASIN 定位" if str(tg).lower().startswith("b0") else "类目定位")
        expr = (f"{tg}" if auto else (f'asin="{str(tg).upper()}"' if kind == "ASIN 定位" else f'category="{tg}"'))
        key = dict(campaign=camp, target=expr, obj_kind="target", kind=kind); mb = MEM["bid"].get((camp, expr, kind))
        cb, est = (mb, "") if mb else (cpc * 1.15, "≈")
        if od == 0 and ck >= 8 and not auto: add(type=f"暂停 {kind}", level="商品定位", field="State", old="enabled", new="paused", why=f"{ck} 次点击 0 单，花 {usd(sp)}", **key)
        elif ac and ac > BE and ck >= 8: add(type=f"{kind}降竞价", level="自动投放" if auto else "商品定位", field="Bid", old=f"{est}${cb:.2f}", new=f"${cb*(1-CAP):.2f}", why=f"ACOS {pct(ac,0)} 超盈亏线" + ("；现竞价按 CPC 估" if est else ""), **key)
        elif ac and ac < TARGET * 0.6 and od >= 3: add(type=f"{kind}提竞价", level="自动投放" if auto else "商品定位", field="Bid", old=f"{est}${cb:.2f}", new=f"${cb*1.10:.2f}", why=f"ACOS {pct(ac,0)}、{od} 单；提 10%" + ("；现竞价按 CPC 估" if est else ""), **key)
    # 搜索词：收割成精确词（成对：新建 + 来源组否定）；泛词跑偏词否定
    st = win(s).groupby(["用户搜索词", "广告活动"])[NUM].sum().reset_index()
    for _, r in st.iterrows():
        term, camp, od, ck, sp = str(r["用户搜索词"]), r["广告活动"], int(r["广告订单量"]), int(r["广告点击量"]), r["广告花费"]
        if pl.group(term).startswith("5"): continue
        if od >= 3 and term.lower() not in exact_kw and camp not in P["主干活动"]:
            exact_kw.add(term.lower()); cpc = sp / ck if ck else 0.8
            add(type="搜索词收割", level="关键词", field="新建精确关键词", campaign=P["精确活动"], kw=term, match="exact", obj_kind="kw", old="—", new=f"${cpc:.2f}", why=f"在「{pl.cname.get(str(r.get('广告活动ID','')),camp)}」出了 {od} 单；收进精确组单独出价", src=camp)
            add(type="来源组否定", level="否定", field="否定关键词", campaign=camp, kw=term, match="negativeExact", obj_kind="kw", old="—", new="enabled", why="收割后在来源组精确否定，避免两个组抢同一个词")
        elif od == 0 and ck >= 10 and pl.group(term).startswith("4"):
            add(type="否定关键词", level="否定", field="否定关键词", campaign=camp, kw=term, match="negativeExact", obj_kind="kw", old="—", new="enabled", why=f"{ck} 次点击 0 单，属于泛词/跑偏词")
    # 活动：预算上调 / 竞价策略
    cw = lwin(cr).groupby("广告活动")[NUM].sum()
    for camp, r in cw.iterrows():
        b = budget.get(camp); sl = r["广告销售额"]; ac = r["广告花费"] / sl if sl else None; per_day = r["广告花费"] / 7
        if b and per_day >= 0.9 * b and ac and ac <= TARGET: add(type="预算上调", level="活动", field="Daily Budget", campaign=camp, obj_kind="camp", old=f"${b:g}", new=f"${round(b*1.2):g}", why=f"日均花 {usd(per_day)}＝预算的 {pct(per_day/b,0)}，ACOS {pct(ac,0)} 在目标内")
        elif ac and ac > BE and r["广告点击量"] >= 30: add(type="改竞价策略", level="活动", field="Bidding Strategy", campaign=camp, obj_kind="camp", old="动态竞价-提高和降低", new="动态竞价-只降低", why=f"整个活动 ACOS {pct(ac,0)} 超盈亏线，先不让系统往上加价")
    # 模拟审批 → 执行 → 下周看结果（下周数据是真实的）
    for i, a in enumerate(acts):
        a["no"] = f"H{k}-{i+1:03d}"; rej = (acts[i-1]["审批"] == "驳回") if a["type"] == "来源组否定" else (i % 7 == 3)   # 来源组否定跟着它那条收割走
        a["审批"] = "驳回" if rej else "通过"; a["理由"] = REJ[i % len(REJ)] if rej else ""
        o = ok_(a)
        if rej: MEM["rej"].add((a["type"], o))
        else:
            MEM["touched"][o] = k
            if a["field"] == "Bid": MEM["bid"][o] = float(a["new"].lstrip("$"))
            if a["field"] == "State" and a["new"] == "paused": MEM["paused"].add(o)
        a["执行"] = "—" if rej else ("已执行（模拟，次日上传）" if a["type"] not in ("改竞价策略",) else "已执行（模拟）")
        if a["obj_kind"] == "kw": cur, nx = (lwin(s), nwin(s)); f_ = lambda d: d[(d["用户搜索词"].str.lower() == a["kw"].lower())] if a["type"] == "搜索词收割" else d[(d["用户搜索词"].str.lower() == a["kw"].lower()) & (d["广告活动"] == a["campaign"])] if a["type"] in ("来源组否定", "否定关键词") else d[(d["广告活动"] == a["campaign"]) & (d["投放"].astype(str).str.lower() == a["kw"].lower())]
        elif a["obj_kind"] == "target": cur, nx = (lwin(t), nwin(t)); f_ = lambda d: d[(d["广告活动"] == a["campaign"]) & (d["投放"].astype(str).str.lower() == a["target"].split('"')[1].lower() if '"' in a["target"] else d["投放"] == a["target"])]
        else: cur, nx = (lwin(cr), nwin(cr)); f_ = lambda d: d[d["广告活动"] == a["campaign"]]
        a["本周"], a["下周"] = stat(f_(cur)), stat(f_(nx)); a["下周结果"] = verdict(a)
    wk = W[k - 1] if k - 1 < len(W) else None
    an = []
    if wk:
        if wk["SP_ACOS"] > TARGET: an.append(f"SP ACOS {pct(wk['SP_ACOS'])} 高于目标 {pct(TARGET,0)}")
        if wk["TACOS"] > BE * 0.7: an.append(f"TACOS {pct(wk['TACOS'])} 接近盈亏线")
        if k > 1 and W[k-2]["广告费"] and wk["广告费"] / W[k-2]["广告费"] - 1 > wk["件数"] / max(1, W[k-2]["件数"]) - 1 + 0.03: an.append("广告费比件数涨得快")
        if k > 1 and wk["退款率"] > 1.5 * W[0]["退款率"] and wk["退款率"] > 0.03: an.append(f"退款率 {pct(wk['退款率'])} 比首周高")
    return {"圈": k, "运行日": (end + pd.Timedelta(days=1)).strftime("%m-%d"), "看的数据": f"{start:%m-%d} ～ {end:%m-%d}", "下周": f"{nxt[0]:%m-%d} ～ {nxt[1]:%m-%d}",
            "周": wk and {x: wk[x] for x in ("周", "件数", "销售额", "广告费", "TACOS", "SP_ACOS", "退款率")}, "异常": an, "读回": dict(back), "动作": acts}


def verdict(a):
    c, n = a["本周"], a["下周"]; t_ = a["type"]
    if a["审批"] == "驳回": return {"结果": "没执行", "说明": "人驳回了，下一圈不再原样提"}
    if t_.startswith("暂停") or t_ in ("否定关键词", "来源组否定"):
        return {"结果": "省下" if n["花费"] < c["花费"] else "持平", "说明": f"下周这个对象花 {usd(n['花费'])}（本周 {usd(c['花费'])}）"}
    if "降竞价" in t_ or t_ == "改竞价策略":
        if c["ACOS"] is None or n["ACOS"] is None: return {"结果": "看不出", "说明": f"下周 {n['点击']} 次点击、{n['订单']} 单，样本不够"}
        return {"结果": "好转" if n["ACOS"] < c["ACOS"] else "变差", "说明": f"ACOS {pct(c['ACOS'],0)} → {pct(n['ACOS'],0)}"}
    if "提竞价" in t_ or t_ in ("预算上调", "搜索词收割"):
        return {"结果": "好转" if n["订单"] > c["订单"] else ("持平" if n["订单"] == c["订单"] else "变差"), "说明": f"订单 {c['订单']} → {n['订单']}，花费 {usd(c['花费'])} → {usd(n['花费'])}"}
    return {"结果": "—", "说明": ""}


if __name__ == "__main__":
    weeks = int(((s["日期"].max().normalize() - D0).days + 1) // 7)
    runs = [run_at(k) for k in range(1, weeks)]          # 最后一周 = 本周真实运行（状态库里的 v1），不回放
    out = {"说明": "历史回放（模拟）：数据是真实历史（已脱敏）；每圈的动作按当时能看到的数据由同一套规则生成；审批与执行是模拟的；「下周结果」是该对象下一周的真实表现，当时并没有真的执行，不代表动作效果。",
           "生成于": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "圈": runs}
    json.dump(out, open(f"{ROOT}/历史回放.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    for r in runs: print(r["运行日"], r["看的数据"], len(r["动作"]), dict(collections.Counter(a["type"] for a in r["动作"])))
