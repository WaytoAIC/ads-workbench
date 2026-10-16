# -*- coding: utf-8 -*-
"""历史回放（模拟）：假设 Agent 从上线第 2 周起每周一跑一圈，回放前三圈。
数据是真实历史（已脱敏）；每圈按当时能看到的 14 天数据出动作；审批与执行是模拟的；
「下周结果」取的是该对象下一周的真实表现——当时并没有真的执行，所以只说明下周发生了什么，不代表动作效果。
输出 <数据目录>/历史回放.json，页面只读，不写状态库。    用法：python3 _脚本/history_sim.py   （ADS_ROOT 指定数据目录）"""
import json, os, re, math, collections, datetime as dt
import pandas as pd
import pipeline as pl
from pipeline import P, NUM, ROOT, usd, pct

TARGET, CAP, UP = float(P["目标ACOS"]), 0.15, 0.10
CHOSEN = set(P.get("取舍项") or ["A", "B", "C", "E"])                 # 人没选的取舍项，回放里也不出（与 pipeline.actions() 一致）
cut = lambda b_: max(0.2, math.ceil(b_ * (1 - CAP) * 100 - 1e-6) / 100); raise_ = lambda b_: math.floor(b_ * (1 + UP) * 100 + 1e-6) / 100   # 与 pipeline.actions() 同一套取整
F = json.load(open(f"{pl.OUT}/数字.json", encoding="utf-8")); W, BE = F["逐周"], F["四周"]["盈亏线"]
t, _ = pl.derived("报表-adTargeringReport-0.pkl", ["日期", "投放", "匹配类型", "广告活动", "广告活动ID"]); t["日期"] = pd.to_datetime(t["日期"])
for n in NUM: t[n] = pd.to_numeric(t[n], errors="coerce").fillna(0)
cr, _ = pl.derived("报表-adCampaignReport-0.pkl", ["日期", "广告活动", "广告活动ID"]); cr["日期"] = pd.to_datetime(cr["日期"])
for n in NUM: cr[n] = pd.to_numeric(cr[n], errors="coerce").fillna(0)
s = pl.s
# 结构表是期末快照：回放里窗口内有点击就说明当时在跑，所以关键词、定位不按现在的 state 过滤
bid = {(pl.cname[str(k["campaignId"])], k["keywordText"].lower(), k["matchType"]): float(k["bid"]) for k in pl.kws if k["matchType"] != "theme"}
MT = {"精确匹配": "exact", "词组匹配": "phrase", "广泛匹配": "broad"}
CID = {c["name"]: i for i, c in pl.camps.items()}
budget = {c["name"]: float(c["budget"]) for c in pl.camps_l}
exact_kw = {k["keywordText"].lower() for k in pl.kws if k["matchType"] == "exact"}
explicit = {(pl.cname[str(x["campaignId"])], pl.target_key(x)[2]) for x in pl.targets}      # 明确定位的 ASIN，不算「匹配到的别家商品页」
PLACE = {"placementTop": "搜索顶部", "placementProductPage": "商品页", "placementRestOfSearch": "搜索其余位置"}
D0 = pd.Timestamp(P["窗口前"][0])                      # 第 1 周第一天（与利润报表的周对齐）
MEM = {"bid": {}, "rej": set(), "paused": set(), "touched": {}, "flag": set()}     # 跨圈记忆：执行后的竞价/预算、人驳回过的、已暂停或已否定的、上一圈刚动过的（观察期）、已标过的缺数据
REJ = ["新品期先保曝光，这周不动", "这是品牌防守位，花费再高也留着", "样本太少，再看一周", "运营有意在测这个词"]
NEG = ("来源组否定", "粗规则否词", "否定 ASIN")


def stat(df):
    sp, sl, ck, od = df["广告花费"].sum(), df["广告销售额"].sum(), int(df["广告点击量"].sum()), int(df["广告订单量"].sum())
    return {"花费": round(float(sp), 2), "点击": ck, "订单": od, "ACOS": (float(sp / sl) if sl else None), "CPC": (float(sp / ck) if ck else None)}


ok_ = lambda a: (a["campaign"], str(a.get("kw") or a.get("target") or a["field"]), a.get("match") or a.get("kind") or "")
rep_of = lambda a: a["target"] if a["kind"] == "自动投放组" else a["target"].split('"')[1].lower()      # 对象写法 → 报表「投放」列的写法


def run_at(k):
    """第 k 周结束后的周一跑：看最近 14 天（第 1 圈只有 7 天），出动作。"""
    end = D0 + pd.Timedelta(days=7 * k - 1); start = max(D0, end - pd.Timedelta(days=13)); nxt = (end + pd.Timedelta(days=1), end + pd.Timedelta(days=7))
    win, nwin = (lambda df: df[(df["日期"] >= start) & (df["日期"] <= end)]), (lambda df: df[(df["日期"] >= nxt[0]) & (df["日期"] <= nxt[1])])
    lwin = lambda df: df[(df["日期"] > end - pd.Timedelta(days=7)) & (df["日期"] <= end)]
    upto = lambda df: df[df["日期"] <= end]
    days = (end - start).days + 1
    acts, back = [], collections.Counter()
    def add(item, **a):
        if item not in CHOSEN: return
        o = ok_(a)
        if (a["type"], o) in MEM["rej"]: back["上圈驳回，不再原样提"] += 1; return
        if o in MEM["paused"]: back["已暂停或已否定，跳过"] += 1; return
        if MEM["touched"].get(o) == k - 1 and a["type"] not in ("来源组否定",): back["上圈刚动过，观察一周"] += 1; return
        acts.append(a)
    def now(camp, obj, kind, default):
        """现值：上一圈执行过就读回执行后的新值，否则用结构表里的值。"""
        o = (camp, obj, kind)
        if o in MEM["bid"]: back["读回执行后的新竞价"] += 1; return MEM["bid"][o]
        return default
    perf = lambda r: (int(r["广告点击量"]), int(r["广告订单量"]), float(r["广告花费"]), (r["广告花费"] / r["广告销售额"] if r["广告销售额"] else None))
    # 关键词：降价 / 提价 / 暂停（手动关键词投放）
    tk = win(t[t["匹配类型"].isin(MT)]).groupby(["广告活动", "投放", "匹配类型"])[NUM].sum()
    for (camp, kw, mt), r in tk.iterrows():
        b = bid.get((camp, str(kw).lower(), MT[mt]))
        if b is None: continue
        b = now(camp, str(kw), MT[mt], b); ck, od, sp, ac = perf(r)
        key = dict(campaign=camp, kw=kw, match=MT[mt], obj_kind="kw")
        if od == 0 and ck >= 15: add("B", type="暂停关键词", level="关键词", field="State", old="enabled", new="paused", why=f"近 {days} 天 {ck} 次点击 0 单，花 {usd(sp)}", **key)
        elif ac and ac > BE and ck >= 10 and cut(b) < b: add("B", type="关键词降竞价", level="关键词", field="Bid", old=f"${b:.2f}", new=f"${cut(b):.2f}", why=f"ACOS {pct(ac,0)} 超盈亏线 {pct(BE)}；单次降 15%", **key)
        elif ac and ac < TARGET * 0.6 and od >= 3: add("B", type="关键词提竞价", level="关键词", field="Bid", old=f"${b:.2f}", new=f"${raise_(b):.2f}", why=f"ACOS {pct(ac,0)} 远低于目标 {pct(TARGET,0)}、{od} 单；提 10% 抢量", **key)
    # 商品定位与自动四组：现竞价读 spTarget；ASIN 定位看投放报告，类目定位、自动四组看搜索词报告的「投放」列（与 pipeline.actions() 一致）
    tp = win(t[~t["匹配类型"].isin(MT) & (t["匹配类型"] != "主题匹配")]).groupby(["广告活动", "投放"])[NUM].sum()
    sp_ = win(s).assign(投放=lambda d: d["投放"].astype(str)).groupby(["广告活动", "投放"])[NUM].sum()
    def tgt(camp, kind, expr, r, cb, est):
        ck, od, sp, ac = perf(r); auto = kind == "自动投放组"
        if (camp, expr, kind) in MEM["bid"]: cb, est = now(camp, expr, kind, cb), ""
        key = dict(campaign=camp, target=expr, obj_kind="target", kind=kind); lvl = "自动投放" if auto else "商品定位"; note = "；现竞价按 CPC 估（缺 spTarget）" if est else ""
        if od == 0 and ck >= (15 if auto else 8): add("B", type="关闭自动投放组" if auto else f"暂停 {kind}", level=lvl, field="State", old="enabled", new="paused", why=f"近 {days} 天 {ck} 次点击 0 单，花 {usd(sp)}", **key)
        elif ac and ac > BE and ck >= 8 and cut(cb) < cb: add("B", type=f"{kind}降竞价", level=lvl, field="Bid", old=f"{est}${cb:.2f}", new=f"${cut(cb):.2f}", why=f"ACOS {pct(ac,0)} 超盈亏线 {pct(BE)}；单次降 15%" + note, **key)
        elif ac and ac < TARGET * 0.6 and od >= 3: add("B", type=f"{kind}提竞价", level=lvl, field="Bid", old=f"{est}${cb:.2f}", new=f"${raise_(cb):.2f}", why=f"ACOS {pct(ac,0)}、{od} 单；提 10% 抢量" + note, **key)
    if pl.targets:
        for x in pl.targets:
            camp = pl.cname[str(x["campaignId"])]; kind, expr, rep = pl.target_key(x)
            src = tp if kind == "ASIN 定位" else sp_
            hit = [i for i in src.index if i[0] == camp and str(i[1]).lower() == rep]
            if hit: tgt(camp, kind, expr, src.loc[hit[0]], float(x["bid"]), "")
    else:                                                               # 没有 spTarget：退回按投放报告逐行看，现竞价按 CPC×1.15 估
        for (camp, tg), r in tp.iterrows():
            auto = camp.startswith("自动"); kind = "自动投放组" if auto else ("ASIN 定位" if str(tg).lower().startswith("b0") else "类目定位")
            expr = (f"{tg}" if auto else (f'asin="{str(tg).upper()}"' if kind == "ASIN 定位" else f'category="{tg}"'))
            tgt(camp, kind, expr, r, (r["广告花费"] / r["广告点击量"] if r["广告点击量"] else 0) * 1.15, "≈")
    # 搜索词：收割成精确词（成对：新建 + 来源组否定）；泛词、跑偏词粗规则否定（D，人没选就不出）
    st = win(s).groupby(["用户搜索词", "广告活动"])[NUM].sum().reset_index()
    ever = set(upto(s).groupby("用户搜索词")["广告订单量"].sum().loc[lambda x: x > 0].index.str.lower())      # 截至当圈出过单的词
    for _, r in st.iterrows():
        term, camp, od, ck, sp = str(r["用户搜索词"]), r["广告活动"], int(r["广告订单量"]), int(r["广告点击量"]), r["广告花费"]; g0 = pl.group(term)
        if g0[0] in "05": continue
        if od >= 3 and term.lower() not in exact_kw and camp not in P["主干活动"] and term.lower() not in pl.ne_by_camp[camp]:
            exact_kw.add(term.lower()); cpc = sp / ck if ck else 0.8
            add("B", type="搜索词收割", level="关键词", field="新建精确关键词", campaign=P["精确活动"], kw=term, match="exact", obj_kind="kw", old="—", new=f"${cpc:.2f}", why=f"在「{camp}」近 {days} 天 {od} 单；收进精确组单独出价（起价＝该词实际 CPC）", src=camp)
            add("B", type="来源组否定", level="否定", field="否定关键词", campaign=camp, kw=term, match="negativeExact", obj_kind="kw", old="—", new="enabled", why="收割后在来源组精确否定，避免两个组抢同一个词")
        elif od == 0 and ck >= 8 and g0.startswith("4") and term.lower() not in ever and term.lower() not in pl.ne_by_camp[camp]:
            add("D", type="粗规则否词", level="否定", field="否定关键词", campaign=camp, kw=term, match="negativeExact", obj_kind="kw", old="—", new="enabled", why=f"近 {days} 天 {ck} 次点击 0 单，属于泛词/跑偏词")
    # 否定 ASIN：自动组、类目定位匹配到的别家商品页，截至当圈累计点击 ≥8 且从没出过单（自家子体和明确定位的 ASIN 不在此列）
    for (term, camp), r in upto(s).groupby(["用户搜索词", "广告活动"])[NUM].sum().iterrows():
        a_ = str(term).lower(); ck, od, sp, _ = perf(r)
        if not pl.group(a_).startswith("5") or re.match(r"^c\d\d$", a_) or (camp, a_) in explicit or a_ in pl.neg_asin[camp] or a_ in ever or od or ck < 8: continue
        add("C", type="否定 ASIN", level="否定", field="否定商品定位", campaign=camp, target=f'asin="{a_.upper()}"', obj_kind="neg_asin", kind="否定 ASIN", old="—", new="enabled", why=f"累计 {ck} 次点击 0 单（花 {usd(sp)}）；匹配到的别家商品页")
    # 活动与广告组：预算上调（近 7 天日均）、竞价策略 / 默认竞价（近 14 天整个活动）——读 spCampaign、spGroup 的真实值
    c14, c7 = win(cr).groupby("广告活动")[NUM].sum(), lwin(cr).groupby("广告活动")[NUM].sum()
    for camp, r in c14.iterrows():
        cid = CID.get(camp)
        if cid is None: continue
        ck, od, sp, ac = perf(r); per_day = float(c7["广告花费"].get(camp, 0)) / 7
        b = now(camp, "Daily Budget", "", budget.get(camp) or 0)
        if b and per_day >= 0.9 * b and ac and ac <= TARGET:
            add("B", type="预算上调", level="活动", field="Daily Budget", campaign=camp, obj_kind="camp", old=f"${b:g}", new=f"${math.floor(b * 120 + 1e-6) / 100:g}", why=f"近 7 天日均花 {usd(per_day)}＝预算的 {pct(per_day/b,0)}，ACOS {pct(ac,0)} 在目标内；加 20%")
        if ac and ac > BE and ck >= 30:
            stg = (pl.camp_set.get(cid) or {}).get("biddingStrategy")
            if ("策略", camp) in MEM["flag"]: back["竞价策略已改成只降低"] += 1
            elif stg == "up_and_down":
                add("B", type="改竞价策略", level="活动", field="Bidding Strategy", campaign=camp, obj_kind="camp", old=pl.STRATEGY[stg], new=pl.STRATEGY["down_only"], why=f"整个活动 ACOS {pct(ac,0)} 超盈亏线，先不让系统往上加价")
            g_ = pl.groups.get(cid)
            if g_:
                db = now(camp, "Ad Group Default Bid", "", float(g_["defaultBid"]))
                if cut(db) < db: add("B", type="下调默认竞价", level="广告组", field="Ad Group Default Bid", campaign=camp, obj_kind="camp", old=f"${db:.2f}", new=f"${cut(db):.2f}", why=f"整个活动 ACOS {pct(ac,0)} 超盈亏线；默认竞价同步降 15%，之后新加的投放不从高价起步")
    # 广告位：设了加价但没有广告位报表 → 只标缺数据、不出调整；标过一次，后面几圈读回不重复提
    adj = {c_["name"]: (pl.camp_set.get(i_) or {}).get("placementAdjustments") for i_, c_ in pl.camps.items() if (pl.camp_set.get(i_) or {}).get("placementAdjustments")}
    if adj and not os.path.exists(f"{pl.RAW}/报表-adPlacementReport-0.pkl"):
        if "广告位" in MEM["flag"]: back["广告位仍缺报表，不重复提"] += 1
        else:
            now_ = "；".join(f"{k_}：" + "、".join(f"{PLACE.get(a['placement'], a['placement'])} +{a['percentage']}%" for a in v) for k_, v in adj.items())
            add("E", type="广告位待补数据", level="活动", field="广告位加价", campaign="、".join(adj), obj_kind="flag", old=now_, new="补广告位报表后再定", why=f"{len(adj)} 个活动设了广告位加价，但没有按广告位拆开的花费和订单，看不出加价值不值；不出调整动作")
    # 模拟审批 → 执行 → 下周看结果（下周数据是真实的）
    for i, a in enumerate(acts):
        a["no"] = f"H{k}-{i+1:03d}"; rej = (acts[i-1]["审批"] == "驳回") if a["type"] == "来源组否定" else (i % 7 == 3 and a["obj_kind"] != "flag")   # 来源组否定跟着它那条收割走；缺数据提示不走审批
        a["审批"] = "驳回" if rej else ("不走审批" if a["obj_kind"] == "flag" else "通过"); a["理由"] = REJ[i % len(REJ)] if rej else ""
        o = ok_(a)
        if rej: MEM["rej"].add((a["type"], o))
        else:
            MEM["touched"][o] = k
            if a["field"] in ("Bid", "Daily Budget", "Ad Group Default Bid"): MEM["bid"][o] = float(a["new"].lstrip("$"))
            if (a["field"] == "State" and a["new"] == "paused") or a["type"] in NEG: MEM["paused"].add(o)
            if a["type"] == "改竞价策略": MEM["flag"].add(("策略", a["campaign"]))
            if a["type"] == "广告位待补数据": MEM["flag"].add("广告位")
        a["执行"] = "—" if rej else ("不执行（只标缺数据）" if a["obj_kind"] == "flag" else "已执行（模拟）" if a["type"] == "改竞价策略" else "已执行（模拟，次日上传）")
        if a["obj_kind"] == "kw": cur, nx = (lwin(s), nwin(s)); f_ = lambda d: d[(d["用户搜索词"].str.lower() == a["kw"].lower())] if a["type"] == "搜索词收割" else d[(d["用户搜索词"].str.lower() == a["kw"].lower()) & (d["广告活动"] == a["campaign"])] if a["type"] in NEG else d[(d["广告活动"] == a["campaign"]) & (d["投放"].astype(str).str.lower() == a["kw"].lower())]
        elif a["obj_kind"] == "target":                                 # ASIN 定位在投放报告里有行；类目定位、自动四组看搜索词报告的「投放」列
            src_ = t if a["kind"] == "ASIN 定位" else s; cur, nx = (lwin(src_), nwin(src_)); f_ = lambda d: d[(d["广告活动"] == a["campaign"]) & (d["投放"].astype(str).str.lower() == rep_of(a))]
        elif a["obj_kind"] == "neg_asin": cur, nx = (lwin(s), nwin(s)); f_ = lambda d: d[(d["广告活动"] == a["campaign"]) & (d["用户搜索词"].str.lower() == rep_of(a))]
        else: cur, nx = (lwin(cr), nwin(cr)); f_ = lambda d: d[d["广告活动"].isin(a["campaign"].split("、"))]
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
    if t_ == "广告位待补数据": return {"结果": "—", "说明": "补了广告位报表才能判断加价值不值"}
    if t_.startswith(("暂停", "关闭")) or t_ in NEG:
        return {"结果": "省下" if n["花费"] < c["花费"] else "持平", "说明": f"下周这个对象花 {usd(n['花费'])}（本周 {usd(c['花费'])}）"}
    if "降竞价" in t_ or t_ in ("改竞价策略", "下调默认竞价"):
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
