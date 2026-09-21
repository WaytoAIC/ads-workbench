# -*- coding: utf-8 -*-
"""广告周检流水线（通用版，不含任何真实标识）：原始报表 + 参数.json → 分组账/事实 → 动作清单 → 三栏表/行动卡 → 运行报告。
脚本管确定性（算数、规则、验证器）；语义分组表在 group() 里，明细留给人纠错；取舍来自 参数.json（人定）。"""
import json, os, re, html, collections, warnings
import pandas as pd
warnings.filterwarnings("ignore")
ROOT = os.environ.get("ADS_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, IN, OUT, CARD = f"{ROOT}/_原始拉取", f"{ROOT}/广告闭环/输入", f"{ROOT}/广告闭环/输出", f"{ROOT}/广告闭环/行动卡"
for d in (IN, OUT, CARD): os.makedirs(d, exist_ok=True)
P = json.load(open(f"{ROOT}/参数.json", encoding="utf-8"))
NUM = ["广告花费", "广告曝光量", "广告点击量", "广告订单量", "广告销售额"]
A, B = tuple(P["窗口前"]), tuple(P["窗口近"])
RUN, VER = P["任务编号"], int(P.get("版本", 1))
J = lambda name: json.load(open(f"{RAW}/{name}", encoding="utf-8"))
usd = lambda v: f"${v:,.0f}"; pct = lambda v, n=1: f"{v*100:.{n}f}%"

# ---------------- 读数 ----------------
s = pd.read_pickle(f"{RAW}/本父体-SP搜索词-按天.pkl")
for n in NUM: s[n] = pd.to_numeric(s[n], errors="coerce").fillna(0)
s["日期"] = pd.to_datetime(s["日期"])
kids, camps_l, kws, ne, adprod = J("在线产品-本父体.json"), J("本父体-活动.json"), J("本父体-spKeyword.json"), J("本父体-spNeKeyword.json"), J("基础-spAdProduct-全店.json")
camps = {str(c["campaignId"]): c for c in camps_l}; cname = {i: c["name"] for i, c in camps.items()}
adprod = [r for r in adprod if str(r["campaignId"]) in camps]
inv = {r[0]: r for r in J("库存与动销-按SKU.json")}
prof = {k_: v[0] for k_, v in J("利润-父体-四周.json").items()}
ret = J("FBA退货-本父体.json")
BRAND = (kids[0].get("brand") or kids[0].get("amazonBrand") or "").strip().lower()
ne_by_camp = collections.defaultdict(set)
for n_ in ne: ne_by_camp[cname[str(n_["campaignId"])]].add(n_["keywordText"].lower())

RULES = json.load(open(f"{ROOT}/分组规则.json", encoding="utf-8"))          # 品类相关的词表放在数据目录，脚本本身不含任何品类信息
LAB = RULES["标签"]
def group(t):
    t = str(t).lower().strip()
    if re.match(r"^(b0[a-z0-9]{8}|c\d\d)$", t): return LAB["5"]
    if BRAND and BRAND in t: return LAB["0"]
    if re.search(RULES["COMP"], t): return LAB["3"]
    if re.search(RULES["OFF"], t): return LAB["41"]
    if not re.search(RULES["INTENT"], t): return LAB["42"]
    if re.search(RULES["CORE"], t) and not re.search(RULES["MOD"], t): return LAB["1"]
    return LAB["2"]
s["分组"] = s["用户搜索词"].map(group)
def agg(df, by):
    g = df.groupby(by)[NUM].sum()
    g["CTR"] = g["广告点击量"] / g["广告曝光量"]; g["CVR"] = g["广告订单量"] / g["广告点击量"]
    g["CPC"] = g["广告花费"] / g["广告点击量"]; g["ACOS"] = g["广告花费"] / g["广告销售额"]
    return g
win = lambda df, w: df[(df["日期"] >= w[0]) & (df["日期"] <= w[1])]
def parse_sku(x):
    m = re.match(RULES["SKU正则"], x); return m.groups() if m else (None, None, None)

# ---------------- 一、事实 ----------------
def facts():
    F = {}
    for w, tag in ((A, "前"), (B, "近")):                       # 输入/ 两期 CSV，表头与课堂虚构版一致
        d = win(s, w).groupby(["广告活动", "匹配类型", "用户搜索词"])[NUM].sum().reset_index(); d.insert(0, "日期范围", f"{w[0]}~{w[1]}")
        d = d.rename(columns={"用户搜索词": "客户搜索词", "广告曝光量": "曝光量", "广告点击量": "点击量", "广告花费": "花费(USD)", "广告订单量": "7天总订单数", "广告销售额": "7天总销售额(USD)"})
        d.sort_values("花费(USD)", ascending=False).to_csv(f"{IN}/搜索词报告-{w[0][5:].replace('-','')}-{w[1][5:].replace('-','')}.csv", index=False, encoding="utf-8-sig")
    c = pd.read_pickle(f"{RAW}/报表-adCampaignReport-0.pkl"); c = c[c["广告活动ID"].astype(str).isin(camps)].copy(); c["日期"] = pd.to_datetime(c["日期"])
    for n in NUM: c[n] = pd.to_numeric(c[n], errors="coerce").fillna(0)
    F["口径核对"] = {"活动报告花费": round(c["广告花费"].sum(), 2), "搜索词报告花费": round(s["广告花费"].sum(), 2)}
    assert abs(c["广告花费"].sum() - s["广告花费"].sum()) / c["广告花费"].sum() < 0.01, "搜索词报告与活动报告花费相差超过 1%"
    wk = []
    for key in sorted(prof):
        x = prof[key]; ad = -x["cpcCost"]; d0 = pd.Timestamp(f"{key[:4]}-{key[4:6]}-{key[6:]}"); cw = c[(c["日期"] >= d0) & (c["日期"] < d0 + pd.Timedelta(days=7))][NUM].sum()
        wk.append({"周": f"{key[4:6]}/{key[6:]} 起", "件数": int(x["salesNum"]), "销售额": x["productSales"], "广告费": ad, "SP": -x["cpcSpCost"], "SB": -x["cpcSbCost"], "SBV": -x["cpcSbvCost"],
                   "TACOS": ad / x["productSales"], "退款率": x["refundNum"] / x["salesNum"], "退款件": int(x["refundNum"]), "广告后毛利率": x["grossProfit"] / x["productSales"],
                   "SP_ACOS": cw["广告花费"] / cw["广告销售额"], "SP_CVR": cw["广告订单量"] / cw["广告点击量"], "SP_CPC": cw["广告花费"] / cw["广告点击量"], "SP_CTR": cw["广告点击量"] / cw["广告曝光量"]})
    F["逐周"] = wk
    S_, U_, AD = sum(w["销售额"] for w in wk), sum(w["件数"] for w in wk), sum(w["广告费"] for w in wk); GP = sum(prof[k_]["grossProfit"] for k_ in prof)
    F["四周"] = {"销售额": S_, "件数": U_, "均价": S_ / U_, "广告费": AD, "SP占比": sum(w["SP"] for w in wk) / AD, "SB占比": sum(w["SB"] for w in wk) / AD, "SBV占比": sum(w["SBV"] for w in wk) / AD,
               "TACOS": AD / S_, "盈亏线": (GP + AD) / S_, "广告后毛利率": GP / S_, "广告归因销售额占比": sum(prof[k_]["cpcSales"] for k_ in prof) / S_, "退款件": sum(w["退款件"] for w in wk)}
    F["末周环比"] = {"广告费": wk[-1]["广告费"] / wk[-2]["广告费"] - 1, "件数": wk[-1]["件数"] / wk[-2]["件数"] - 1}
    for w, tag in ((A, "前14天"), (B, "近14天")):
        g = agg(win(s, w), "分组"); tot = win(s, w)[NUM].sum(); assert abs(g["广告花费"].sum() - tot["广告花费"]) < 0.01, "分组合计≠总计"
        g["占比"] = g["广告花费"] / tot["广告花费"]
        F[f"分组账-{tag}"] = {i: {k_: (None if v != v or v == float("inf") else round(float(v), 4)) for k_, v in r.items()} for i, r in g.iterrows()}
        F[f"SP-{tag}"] = {"花费": tot["广告花费"], "点击": int(tot["广告点击量"]), "订单": int(tot["广告订单量"]), "销售额": tot["广告销售额"], "ACOS": tot["广告花费"] / tot["广告销售额"],
                         "CVR": tot["广告订单量"] / tot["广告点击量"], "CPC": tot["广告花费"] / tot["广告点击量"]}
    gB = F["分组账-近14天"]; F["泛词加跑偏"] = {"花费": sum(v["广告花费"] for k_, v in gB.items() if k_.startswith("4")), "占比": sum(v["占比"] for k_, v in gB.items() if k_.startswith("4"))}
    b = win(s, B); bt_ = agg(b, "用户搜索词")
    multi = b.groupby("用户搜索词").agg(活动数=("广告活动", "nunique"), 花费=("广告花费", "sum")).query("活动数>=3")
    F["同词多活动"] = {"词数": int(len(multi)), "花费": multi["花费"].sum(), "占比": multi["花费"].sum() / b["广告花费"].sum()}
    head = [t for t in bt_.sort_values("广告花费", ascending=False).index if not group(t).startswith("5")][:4]; F["头部词"] = head
    hb = b[b["用户搜索词"].isin(head)]; lane = hb.groupby("广告活动")[NUM].sum().sort_values("广告花费", ascending=False)
    F["头部词分道"] = [{"广告活动": i, "花费": r["广告花费"], "点击": int(r["广告点击量"]), "订单": int(r["广告订单量"]), "ACOS": (r["广告花费"] / r["广告销售额"] if r["广告销售额"] else None)} for i, r in lane.iterrows()]
    F["精确组占头部词花费"] = float(lane["广告花费"].get(P["精确活动"], 0) / lane["广告花费"].sum()); F["头部词花费"] = float(lane["广告花费"].sum())
    ga, gb = agg(win(s, A), "用户搜索词"), agg(win(s, B), "用户搜索词"); neg_all = {x for v in ne_by_camp.values() for x in v}; bt = []
    for th in (5, 8, 10):
        f_ = ga[(ga["广告点击量"] >= th) & (ga["广告订单量"] == 0)]; later = gb.reindex(f_.index).fillna(0)
        bt.append({"点击阈值": th, "当时会标的词": int(len(f_)), "当时已花": round(f_["广告花费"].sum(), 2), "后14天又花": round(later["广告花费"].sum(), 2), "后14天订单": int(later["广告订单量"].sum()),
                   "其中后来出单的词": int((later["广告订单量"] > 0).sum()), "其中运营已否": int(sum(i.lower() in neg_all for i in f_.index))})
    F["回测"] = bt; pd.DataFrame(bt).to_csv(f"{OUT}/回测-汇总.csv", index=False, encoding="utf-8-sig")
    rows = sorted(inv.values(), key=lambda r: -(r[5] or 0)); tw = sum(r[5] for r in rows); top4 = rows[:4]
    out_ = [r for r in rows if r[6] is not None and r[6] < 1 and r[5] > 0]
    F["库存"] = {"可售": sum(r[1] for r in rows), "调拨中": sum(r[2] for r in rows), "途中": sum(r[3] for r in rows), "上周销量": tw, "整体可售周数": sum(r[1] for r in rows) / tw,
               "前四SKU": [r[0] for r in top4], "前四占上周件数": sum(r[5] for r in top4) / tw, "前四可售": sum(r[1] for r in top4), "前四可售周数": sum(r[1] for r in top4) / sum(r[5] for r in top4),
               "将断货SKU": [{"SKU": r[0], "上周销量": r[5], "可售": r[1], "可售周数": r[6]} for r in out_], "将断货占上周件数": sum(r[5] for r in out_) / tw}
    soon = [r for r in rows if r[6] is not None and r[6] < 2 and r[5] > 0]
    F["库存"].update({"两周内断货SKU": [r[0] for r in soon], "两周内断货占上周件数": sum(r[5] for r in soon) / tw, "两周内断货可售": sum(r[1] for r in soon), "两周内断货可售周数": (sum(r[1] for r in soon) / sum(r[5] for r in soon) if soon else None)})
    F["断货后等效ACOS"] = F["SP-近14天"]["ACOS"] / (1 - F["库存"]["将断货占上周件数"]); F["断货每周白花上限"] = wk[-1]["广告费"] * F["库存"]["将断货占上周件数"]
    rc = collections.Counter(x["reasonStr"] for x in ret); F["退货原因"] = rc.most_common(); F["已退回件"] = len(ret); F["退货首因占比"] = rc.most_common(1)[0][1] / len(ret)
    F["活动"] = {"个数": len(camps), "名义日预算合计": sum(float(c_["budget"]) for c_ in camps.values()), "上周日均SP花费": wk[-1]["SP"] / 7,
               "竞价区间": [min(float(k_["bid"]) for k_ in kws if k_["state"] == "enabled" and k_["matchType"] != "theme"), max(float(k_["bid"]) for k_ in kws if k_["state"] == "enabled")], "已有否词": len(ne)}
    Rw, TA, be_ = float(P["补货到仓周数"]), float(P["目标ACOS"]), F["四周"]["盈亏线"]; an = []
    def flag(name, val, ref, level, note): an.append({"指标": name, "现值": val, "参照": ref, "级别": level, "说明": note})
    I_ = F["库存"]
    flag("库存够卖几周", f"{I_['整体可售周数']:.1f} 周", f"补货到仓要 {Rw:g} 周", "critical" if I_["整体可售周数"] < Rw else "good",
         (f"将断货的 SKU 占上周件数 {pct(I_['将断货占上周件数'],0)}；两周内会断货的 {len(I_['两周内断货SKU'])} 个 SKU 只剩 {I_['两周内断货可售周数']:.2f} 周" if I_["两周内断货SKU"] else "各 SKU 库存充足"))
    flag("退款率", pct(wk[-1]["退款率"]), f"首周 {pct(wk[0]['退款率'])}", "serious" if (wk[-1]["退款率"] > 0.05 and wk[-1]["退款率"] > 1.5 * wk[0]["退款率"]) else "good", f"已退回 {F['已退回件']} 件里 {pct(F['退货首因占比'],0)} 是「{F['退货原因'][0][0]}」")
    flag("同一批词被几个活动重复买", pct(F["同词多活动"]["占比"], 0), "≥3 个活动同时买的花费占比", "warning" if F["同词多活动"]["占比"] > 0.5 else "good", f"{F['同词多活动']['词数']} 个搜索词、{usd(F['同词多活动']['花费'])}；精确组只占头部词花费的 {pct(F['精确组占头部词花费'])}")
    flag("末周广告费增速 vs 件数增速", f"{F['末周环比']['广告费']:+.0%} vs {F['末周环比']['件数']:+.0%}", "广告费不该比件数涨得快", "warning" if F["末周环比"]["广告费"] > F["末周环比"]["件数"] + 0.03 else "good", "多花的钱没有换来等比例的单")
    a_ = F["SP-近14天"]["ACOS"]
    flag("SP 的 ACOS", pct(a_), f"目标 {pct(TA,0)}｜盈亏线 {pct(be_)}", "critical" if a_ > be_ else ("warning" if a_ > TA else "good"), "高于目标、没过盈亏线：不流血，但也没到该放量的水平" if TA < a_ <= be_ else ("已越过盈亏线，每一单都在亏" if a_ > be_ else "在目标内"))
    flag("TACOS", pct(F["四周"]["TACOS"]), f"盈亏线 {pct(be_)}", "good" if F["四周"]["TACOS"] < be_ * 0.7 else "warning", f"广告后毛利率 {pct(F['四周']['广告后毛利率'])}")
    flag("泛词＋跑偏词", pct(F["泛词加跑偏"]["占比"]), "占 SP 花费", "good" if F["泛词加跑偏"]["占比"] < 0.10 else "warning", "不是主要问题：别把力气花在否词上" if F["泛词加跑偏"]["占比"] < 0.10 else "值得清一轮")
    order_ = {"critical": 0, "serious": 1, "warning": 2, "good": 3}; F["异常"] = sorted(an, key=lambda x: order_[x["级别"]])
    out = gb.copy(); out.insert(0, "分组", [group(i) for i in out.index]); out.sort_values("广告花费", ascending=False).round(3).to_csv(f"{OUT}/分组明细-近14天-请人工纠错.csv", encoding="utf-8-sig")
    json.dump(F, open(f"{OUT}/数字.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    return F

# ---------------- 二、动作清单（取舍来自人；规则来自 参数.json） ----------------
def actions(F):
    R = float(P["补货到仓周数"]); T = 0 if R <= 1 else (1 if R <= 3 else 2); TARGET = float(P["目标ACOS"]); rows, tabA = [], []
    b = win(s, B); ever = set(s.groupby("用户搜索词")["广告订单量"].sum().loc[lambda x: x > 0].index.str.lower())
    back = json.load(open(f"{OUT}/读回状态.json", encoding="utf-8")) if os.path.exists(f"{OUT}/读回状态.json") else {}
    key_of = lambda x: (x["类型"], str(x["广告活动"]), str(x["对象"]))
    REJ = {key_of(x): x for x in back.get("被驳回的动作", [])}; DONE = {key_of(x): x for x in back.get("已处理的动作", [])}; seen_done, skipped_rej = set(), []
    CHOSEN = set(P.get("取舍项") or ["A", "B", "C", "E"])
    def add(item, typ, camp, obj, old, new, why, spend="", rev="可逆"):
        if item not in CHOSEN: return                                  # 人没选的路，不生成动作
        k_ = (typ, str(camp), str(obj))
        if k_ in REJ: skipped_rej.append({"动作编号": REJ[k_]["动作编号"], "类型": typ, "广告活动": str(camp), "对象": str(obj), "驳回理由": REJ[k_].get("驳回理由")}); return   # 人驳回过：不再原样提
        if k_ in DONE: seen_done.add(k_); return                                                                                                   # 人确认过：沿用，不重复派
        rows.append({"取舍项": item, "类型": typ, "广告活动": camp, "对象": obj, "现值": old, "新值": new, "依据": why, "近14天涉及花费": spend, "可逆": rev})
    # A 保主力规格
    enabled = collections.defaultdict(set)
    for r in adprod:
        if r["state"] == "enabled": enabled[cname[str(r["campaignId"])]].add(r["sku"])
    paused = collections.defaultdict(list)
    for r in sorted(adprod, key=lambda r: (cname[str(r["campaignId"])], r["sku"])):
        i = inv.get(r["sku"]); camp = cname[str(r["campaignId"])]
        if not i: continue
        W = i[6]
        if r["state"] != "enabled": sug, why = "不动", "当前已暂停"
        elif T > 0 and W is not None and W < T: sug, why = "暂停", f"可售 {i[1]} 件、上周卖 {i[5]} 件＝{W} 周；补货要 {R:g} 周"; paused[camp].append(r["sku"])
        else: sug, why = "保留", (f"可售 {i[1]} 件＝{W} 周" if W is not None else "上周无销量")
        tabA.append({"广告活动": camp, "SKU": r["sku"], "当前状态": r["state"], "可售": i[1], "上周销量": i[5], "可售周数": W, "建议": sug, "依据": why, "状态": "待确认"})
        if sug == "暂停": add("A", "暂停广告产品", camp, r["sku"], "投放中", "暂停", why)
    for camp, skus in paused.items():                                 # 补挂库存足的同规格另一款
        for sku in skus:
            st_, pk, sz = parse_sku(sku)
            for cand, i in inv.items():
                c_st, c_pk, c_sz = parse_sku(cand)
                if c_pk == pk and c_sz == sz and c_st != st_ and i[6] is not None and i[6] >= R and cand not in enabled[camp]:
                    add("A", "补挂广告产品", camp, cand, "未投放", "投放", f"同规格的 {sku} 将断货；{cand} 可售 {i[1]} 件＝{i[6]} 周，撑得到补货到仓")
    if T == 0:                                                        # 到仓很快：不暂停，只降预算
        for camp, skus in enabled.items():
            risk = [x for x in skus if inv.get(x) and inv[x][6] is not None and inv[x][6] < 1]
            if risk:
                bud = float(next(c_["budget"] for c_ in camps.values() if c_["name"] == camp))
                add("A", "下调预算", camp, "日预算", bud, round(bud * 0.7), f"组内 {len(risk)} 个 SKU 一周内会断货；补货 {R:g} 周就到，不暂停，预算先降 30%，到仓后恢复")
    pd.DataFrame(tabA).to_csv(f"{OUT}/广告产品调整表.csv", index=False, encoding="utf-8-sig")
    # B 结构去重：换道否定 + 竞价分层
    negs = []
    g = b[b["用户搜索词"].isin(F["头部词"])].groupby(["用户搜索词", "广告活动"])[NUM].sum().reset_index()
    for _, r in g.iterrows():
        if r["广告活动"] in P["主干活动"] or r["广告花费"] <= 0 or r["用户搜索词"].lower() in ne_by_camp[r["广告活动"]]: continue
        negs.append({"广告活动": r["广告活动"], "否定词": r["用户搜索词"], "匹配方式": "精确否定", "来由": "B 换道", "近14天该组花费": round(r["广告花费"], 2), "近14天该组订单": int(r["广告订单量"]), "状态": "待确认"})
        add("B", "换道否定", r["广告活动"], r["用户搜索词"], "在本组出词", "本组精确否定", f"头部词串到了这个组（近14天 {usd(r['广告花费'])}、{int(r['广告订单量'])} 单）；不是弃词，让它回主干组跑", round(r["广告花费"], 2))
    t = pd.read_pickle(f"{RAW}/报表-adTargeringReport-0.pkl"); t = t[t["广告活动ID"].astype(str).isin(camps)].copy(); t["日期"] = pd.to_datetime(t["日期"])
    for n in NUM: t[n] = pd.to_numeric(t[n], errors="coerce").fillna(0)
    t14 = win(t, B).groupby(["广告活动", "投放"])[NUM].sum()
    bids_by = collections.defaultdict(list)
    for k_ in kws:
        if k_["state"] == "enabled" and k_["matchType"] != "theme": bids_by[cname[str(k_["campaignId"])]].append(float(k_["bid"]))
    E = float(pd.Series(bids_by[P["精确活动"]]).median()); bidrows = []
    for k_ in kws:
        if k_["state"] != "enabled" or k_["matchType"] == "theme": continue
        camp, old = cname[str(k_["campaignId"])], float(k_["bid"]); new = None
        if camp == P["词组活动"] and old > 0.95 * E: new, why = round(0.946 * E, 2), f"词组竞价 {old} 高于精确 {E}；压到精确之下，让精确组收割"
        elif camp == P["广泛活动"] and old > 0.95 * E: new, why = round(0.888 * E, 2), f"广泛竞价 {old} 高于精确 {E}；广泛只负责拓词，压到最低一档"
        elif camp not in P["主干活动"]:
            med = float(pd.Series(bids_by[camp]).median())
            if old > med * 1.05: new, why = round(med, 2), f"高于本组中位竞价 {med}，且头部词从这里串道"
        if new is None: continue
        key = (camp, k_["keywordText"]); sp = float(t14["广告花费"].get(key, 0)); ck = int(t14["广告点击量"].get(key, 0))
        bidrows.append({"广告活动": camp, "关键词": k_["keywordText"], "匹配": k_["matchType"], "现竞价": old, "新竞价": new, "调幅": f"{new/old-1:.0%}", "近14天花费": round(sp, 2), "近14天点击": ck, "状态": "待确认"})
        add("B", "降竞价", camp, f"{k_['keywordText']}（{k_['matchType']}）", old, new, why, round(sp, 2))
    pd.DataFrame(bidrows).to_csv(f"{OUT}/竞价调整表.csv", index=False, encoding="utf-8-sig")
    # C 竞品品牌词分拣（四周全量，样本更大）
    allp = agg(s, "用户搜索词"); allp["分组"] = [group(i) for i in allp.index]; comp = allp[allp["分组"] == "3-竞品品牌词"].sort_values("广告花费", ascending=False)
    cvr0, price, be = F["SP-近14天"]["CVR"], F["四周"]["均价"], F["四周"]["盈亏线"]; tabC = []
    for term_, r in comp.iterrows():
        ck, od, sp, sl = int(r["广告点击量"]), int(r["广告订单量"]), r["广告花费"], r["广告销售额"]; p0 = (1 - cvr0) ** ck; acos = sp / sl if sl else None
        where = "、".join(c_ for c_, ws in ne_by_camp.items() if term_.lower() in ws) or "—"
        if od == 0 and p0 <= 0.05: cls, sug = "否", "全部活动精确否定"
        elif od == 0: cls, sug = "观察", f"样本不足：按基准转化率 {pct(cvr0,0)}，{ck} 次点击一单不出的概率还有 {pct(p0,0)}"
        elif acos > be: cls, sug = "降价单独跑", f"出过单不能否；单独建精确词，竞价＝目标 ACOS {pct(TARGET,0)} × 转化率 × 客单价 ≈ ${max(0.5, TARGET*(od/ck)*price):.2f}"
        else: cls, sug = "留", "ACOS 在盈亏线内，保持"
        if sp < 0.00077 * float(s["广告花费"].sum()) and cls in ("观察", "留"): continue      # 太小的不进分拣表，留在分组明细里
        tabC.append({"搜索词": term_, "点击": ck, "订单": od, "花费": round(sp, 2), "ACOS": (pct(acos, 0) if acos else "—"), "分拣": cls, "建议": sug, "运营已在这些活动否过": where, "状态": "待确认"})
        if cls == "降价单独跑": add("C", "竞品词降价单独跑", P["精确活动"], term_, f"ACOS {pct(acos,0)}", sug.split("≈ ")[-1], f"{ck} 次点击 {od} 单，ACOS 高于盈亏线 {pct(be)}", round(sp, 2))
        if cls == "否":
            for camp in sorted(set(s[s["用户搜索词"] == term_]["广告活动"])):
                if term_.lower() not in ne_by_camp[camp]:
                    negs.append({"广告活动": camp, "否定词": term_, "匹配方式": "精确否定", "来由": "C 零单且样本足够", "近14天该组花费": "", "近14天该组订单": 0, "状态": "待确认"}); add("C", "竞品词否定", camp, term_, "出词", "精确否定", f"{ck} 次点击 0 单，偶然的概率 {pct(p0,0)}", round(sp, 2))
        if where != "—" and od > 0: add("C", "交回运营判断", where, term_, "只在一个活动里否了", "全活动补否，还是撤回否定？", f"它在别的活动出过 {od} 单（花 {usd(sp)}，ACOS {pct(acos,0)}）", round(sp, 2))
    pd.DataFrame(tabC).to_csv(f"{OUT}/竞品品牌词分拣表.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(negs or [{"广告活动": "", "否定词": "", "匹配方式": "", "来由": "", "近14天该组花费": "", "近14天该组订单": "", "状态": "待确认"}][:len(negs) or 0]).to_csv(f"{OUT}/否词清单.csv", index=False, encoding="utf-8-sig")
    # D 只做否词（课堂原套路的粗规则）：近 14 天 点击≥8 且 0 单 的泛词、跑偏词
    gb_ = agg(b, "用户搜索词")
    for term_, r in gb_[(gb_["广告点击量"] >= 8) & (gb_["广告订单量"] == 0)].sort_values("广告花费", ascending=False).iterrows():
        if not group(term_).startswith("4") or term_.lower() in ever: continue
        for camp in sorted(set(b[b["用户搜索词"] == term_]["广告活动"])):
            if term_.lower() not in ne_by_camp[camp] and "D" in CHOSEN:
                negs.append({"广告活动": camp, "否定词": term_, "匹配方式": "精确否定", "来由": "D 粗规则", "近14天该组花费": round(r["广告花费"], 2), "近14天该组订单": 0, "状态": "待确认"})
                add("D", "粗规则否词", camp, term_, "出词", "精确否定", f"近 14 天 {int(r['广告点击量'])} 次点击 0 单；按基准转化率，纯属偶然的概率 {pct((1-cvr0)**int(r['广告点击量']),0)}", round(r["广告花费"], 2))
    # E 查证
    if F["逐周"][-1]["退款率"] > 0.05:
        top, n_ = F["退货原因"][0]; add("E", "Listing 建议稿", "—", f"退货首因：{top}", f"退款率 {pct(F['逐周'][-1]['退款率'])}", "规格表与主图加选码提示，出建议稿走 A/B，不直接替换", f"已退回 {F['已退回件']} 件里 {n_} 件是这个原因", "", "可逆")
    add("E", "查证", "—", "补货到仓日期", f"按 {R:g} 周估", "供应链回填实际到仓日", "到仓周数决定 A 的力度；改了这个数，动作清单要重算", "", "—")
    for i, r in enumerate(rows, 1):
        r.update({"动作编号": f"{RUN}{'' if VER == 1 else f'v{VER}'}-{i:03d}", "周检任务": RUN, "版本": VER, "状态": "待确认"})
    # ---- 验证器（底线）：逐项留痕；任何一项不过，整轮作废、不写入 ----
    neg_cd = {n_["否定词"].lower() for n_ in negs if n_["来由"][0] in "CD"}
    checks = [("否词清单里没有自家品牌词", not any(BRAND and BRAND in n_["否定词"].lower() for n_ in negs)),
              ("C、D 类否词里没有出过单的词", not (neg_cd & ever)),
              ("没有重复否定已经否过的词", all(n_["否定词"].lower() not in ne_by_camp[n_["广告活动"]] for n_ in negs)),
              ("竞价单次调幅不超过 15%", all(abs(float(x["调幅"].strip("%"))) <= 15 for x in bidrows)),
              ("所有动作都停在「待确认」", all(r["状态"] == "待确认" for r in rows)),
              ("搜索词报告与活动报告花费相差 <1%", abs(F["口径核对"]["活动报告花费"] - F["口径核对"]["搜索词报告花费"]) / F["口径核对"]["活动报告花费"] < 0.01),
              ("只生成了人选中的取舍项", all(r["取舍项"] in CHOSEN for r in rows))]
    json.dump([{"检查": c, "通过": bool(ok)} for c, ok in checks], open(f"{OUT}/验证器.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = [c for c, ok in checks if not ok]; assert not bad, "验证器未通过：" + "；".join(bad)
    cols = ["动作编号", "周检任务", "版本", "取舍项", "类型", "广告活动", "对象", "现值", "新值", "依据", "近14天涉及花费", "可逆", "状态"]
    pd.DataFrame(rows)[cols].to_csv(f"{OUT}/动作清单.csv", index=False, encoding="utf-8-sig"); json.dump(rows, open(f"{OUT}/动作清单.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    cnt = collections.Counter(r["类型"] for r in rows)
    stale = [v["动作编号"] for k_, v in DONE.items() if k_ not in seen_done]          # 人确认过、但新输入下规则已不再建议的
    return rows, {"取舍项": sorted(CHOSEN), "按取舍项": dict(collections.Counter(r["取舍项"] for r in rows)), "沿用上轮已确认": len(seen_done), "上轮被驳回不再提": skipped_rej, "已确认但新输入下不再建议": stale, "按类型": dict(cnt), "合计": len(rows), "竞品词分拣": dict(collections.Counter(x["分拣"] for x in tabC)), "保留广告产品": sum(1 for x in tabA if x["建议"] == "保留"), "暂停SKU": sorted({r["对象"] for r in rows if r["类型"] == "暂停广告产品"})}

if __name__ == "__main__":
    F = facts(); rows, summ = actions(F)
    json.dump(summ, open(f"{OUT}/动作汇总.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[{P['显示店铺']}] {RUN} v{VER}｜到仓 {P['补货到仓周数']} 周｜目标 ACOS {pct(float(P['目标ACOS']),0)}")
    print(f"  四周销售额 {usd(F['四周']['销售额'])}｜TACOS {pct(F['四周']['TACOS'])}｜盈亏线 {pct(F['四周']['盈亏线'])}｜SP 近14天 ACOS {pct(F['SP-近14天']['ACOS'])}｜整体可售 {F['库存']['整体可售周数']:.1f} 周｜末周退款率 {pct(F['逐周'][-1]['退款率'])}")
    print(f"  泛词＋跑偏占 {pct(F['泛词加跑偏']['占比'])}｜同词多活动占 {pct(F['同词多活动']['占比'],0)}｜精确组占头部词 {pct(F['精确组占头部词花费'])}")
    print(f"  动作 {summ['合计']} 条：{summ['按类型']}｜竞品词分拣 {summ['竞品词分拣']}｜验证器通过")
