# -*- coding: utf-8 -*-
"""把「我的数据」文件夹（卖家后台导出的搜索词报告 + 三张手填小表）整理成工作台能读的 _原始拉取/。
用法：python3 _脚本/import_my_data.py <我的数据目录> <输出根目录>
      之后：python3 工作台/app.py --root <输出根目录> --port 8811
文件说明见 数据格式.md；模板见 我的数据-示例/。只读你的文件，不联网。"""
import json, os, re, shutil, sys
import pandas as pd
SRC, DST = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]); RAW = f"{DST}/_原始拉取"; os.makedirs(RAW, exist_ok=True)
need = lambda f: (f"{SRC}/{f}" if os.path.exists(f"{SRC}/{f}") else sys.exit(f"缺少必需文件：{f}（照 数据格式.md 准备）"))
opt = lambda f: f"{SRC}/{f}" if os.path.exists(f"{SRC}/{f}") else None
def read(f): return pd.read_csv(f, encoding="utf-8-sig", dtype=str).fillna("")
norm = lambda h: re.sub(r"[\s_\-（）()#%:：]", "", str(h)).lower()
money = lambda v: float(re.sub(r"[^\d.\-]", "", str(v)) or 0)
COLS = {  # 目标列: ([候选关键词，按优先级], [出现就排除的关键词])
    "日期": (["date", "日期"], ["update", "更新"]), "广告活动": (["campaignname", "广告活动名称", "campaign", "广告活动"], ["id", "portfolio", "组合", "state", "状态", "budget", "预算"]),
    "投放": (["targeting", "投放"], ["type", "类型", "report"]), "匹配类型": (["matchtype", "匹配类型", "match", "匹配"], []),
    "用户搜索词": (["customersearchterm", "searchterm", "客户搜索词", "用户搜索词", "搜索词"], []),
    "广告曝光量": (["impressions", "展示量", "曝光量", "曝光", "展示"], []), "广告点击量": (["clicks", "点击量", "点击"], ["rate", "率", "cost", "费用", "cpc", "per"]),
    "广告花费": (["spend", "花费", "cost"], ["perclick", "每次", "cpc", "acos", "sales", "销售"]),
    "广告销售额": (["7daytotalsales", "totalsales", "7天总销售额", "总销售额", "sales", "销售额"], ["sku", "acos", "roas", "other", "其他", "advertised", "推广"]),
    "广告订单量": (["7daytotalorders", "totalorders", "7天总订单数", "总订单数", "orders", "订单"], ["rate", "率", "conversion", "转化", "sku", "other"]),
    "广告销量": (["7daytotalunits", "totalunits", "7天总销量", "总销量", "units", "销量"], ["sku", "other", "其他", "advertised", "推广"]),
}
def map_cols(df, required):
    got, hs = {}, {norm(h): h for h in df.columns}
    for tgt, (cands, bad) in COLS.items():
        for c in cands:
            hit = [h for n, h in hs.items() if c in n and not any(b in n for b in bad)]
            if hit: got[tgt] = hit[0]; break
    miss = [t for t in required if t not in got]
    if miss: sys.exit(f"搜索词报告里认不出这些列：{miss}\n它的表头是：{list(df.columns)}\n把对应列改名成中文（如 日期/广告活动/投放/匹配类型/客户搜索词/曝光量/点击量/花费/7天总销售额/7天总订单数）再来。")
    return got

# ---- 1. 搜索词报告（必需） ----
st = read(need("搜索词报告.csv")); m = map_cols(st, ["日期", "广告活动", "用户搜索词", "广告曝光量", "广告点击量", "广告花费", "广告销售额", "广告订单量"])
d = pd.DataFrame({k: st[v] for k, v in m.items()})
for k in ("投放", "匹配类型", "广告销量"):
    if k not in d: d[k] = d["用户搜索词"] if k == "投放" else ("—" if k == "匹配类型" else d["广告订单量"])
d["日期"] = pd.to_datetime(d["日期"], errors="coerce"); bad_dates = int(d["日期"].isna().sum()); d = d.dropna(subset=["日期"])
for k in ("广告曝光量", "广告点击量", "广告订单量", "广告销量"): d[k] = d[k].map(money).astype(int)
for k in ("广告花费", "广告销售额"): d[k] = d[k].map(money).round(2)
d["匹配类型"] = d["匹配类型"].str.strip().str.lower().map(lambda x: {"broad": "广泛匹配", "phrase": "词组匹配", "exact": "精确匹配", "": "—"}.get(x, x))
AUTO_CN = {"close-match": "紧密匹配", "loose-match": "宽泛匹配", "substitutes": "同类产品", "complements": "关联商品"}   # 后台导出的自动投放四组写法 → 流水线用的中文名
def norm_tgt(v):
    """「投放」列统一成流水线能对上的写法：asin="B0…" → B0…；category="…" → 类目名；close-match 等 → 中文四组名；其余原样。"""
    v = str(v).strip(); m_ = re.match(r'^(asin|category)\s*=\s*"?(.*?)"?$', v, re.I)
    if m_: return m_.group(2).strip()
    return AUTO_CN.get(re.sub(r"[\s_]+", "-", v.lower()), v)
d["投放"] = d["投放"].map(norm_tgt)
d["广告活动"] = d["广告活动"].str.strip(); camps = sorted(d["广告活动"].unique()); cid = {c: f"C{i+1:02d}" for i, c in enumerate(camps)}; d["广告活动ID"] = d["广告活动"].map(cid)
span = (d["日期"].max() - d["日期"].min()).days + 1
if span < 21: sys.exit(f"搜索词报告只覆盖 {span} 天（{d['日期'].min().date()}～{d['日期'].max().date()}），至少要 3 周，建议 4 周。")
if span < 28: print(f"提示：搜索词报告只覆盖 {span} 天，「前 14 天」窗口不完整，前后对比会偏。")
d = d[["日期", "用户搜索词", "投放", "匹配类型", "广告活动", "广告活动ID", "广告花费", "广告曝光量", "广告点击量", "广告订单量", "广告销售额", "广告销量"]]
d.to_pickle(f"{RAW}/本父体-SP搜索词-按天.pkl")
end = d["日期"].max(); W = lambda a, b: [(end - pd.Timedelta(days=a)).strftime("%Y-%m-%d"), (end - pd.Timedelta(days=b)).strftime("%Y-%m-%d")]

# ---- 2. 三张手填小表 + 产品 + 参数（必需） ----
wk = read(need("周度经营.csv")); prof = {}
for _, r in wk.iterrows():
    k = pd.to_datetime(r["周起始日"]).strftime("%Y%m%d"); units, sales = int(money(r["件数"])), money(r["销售额"]); sp, sb, sbv = money(r.get("SP广告费", 0)), money(r.get("SB广告费", 0)), money(r.get("SBV广告费", 0))
    gm = money(r["广告前毛利率"]); gm = gm / 100 if gm > 1 else gm; ad = sp + sb + sbv
    d0 = pd.Timestamp(k); adsales = float(d[(d["日期"] >= d0) & (d["日期"] < d0 + pd.Timedelta(days=7))]["广告销售额"].sum())
    prof[k] = [{"salesNum": units, "refundNum": int(money(r.get("退款件", 0))), "productSales": sales, "cpcCost": -ad, "cpcSpCost": -sp, "cpcSbCost": -sb, "cpcSbvCost": -sbv, "cpcSales": adsales, "grossProfit": round(sales * gm - ad, 2), "grossProfitRate": round((sales * gm - ad) / sales, 4) if sales else 0}]
if len(prof) < 2: sys.exit("周度经营.csv 至少要 2 行（建议 4 行，每行一周）")
json.dump(prof, open(f"{RAW}/利润-父体-四周.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
inv = read(need("库存.csv")); rows = []
for _, r in inv.iterrows():
    av, tr, ib = int(money(r["可售"])), int(money(r.get("调拨中", 0))), int(money(r.get("途中", 0))); w3, w4 = int(money(r.get("上上周销量", 0))), int(money(r["上周销量"]))
    rows.append([r["SKU"].strip(), av, tr, ib, w3, w4, (round(av / w4, 1) if w4 else None), int(money(r.get("上周退款", 0))), money(r.get("上周广告费", 0)), money(r.get("上周销售额", 0))])
json.dump(rows, open(f"{RAW}/库存与动销-按SKU.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
prod = json.load(open(need("产品.json"), encoding="utf-8"))
json.dump([{"asin": prod.get("父ASIN", "P001"), "sku": (rows[0][0] if rows else "SKU"), "brand": prod.get("品牌", ""), "title": prod.get("显示产品", ""), "standardPrice": prod.get("客单价", 0)}], open(f"{RAW}/在线产品-本父体.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
P = json.load(open(need("参数.json"), encoding="utf-8"))
for k in ("目标ACOS", "补货到仓周数", "产品阶段", "精确活动", "词组活动", "广泛活动"):
    if k not in P: sys.exit(f"参数.json 缺 {k}")
for k in ("精确活动", "词组活动", "广泛活动"):
    if P[k] not in cid: sys.exit(f"参数.json 里 {k}＝「{P[k]}」不在报表的广告活动里。报表里有：{camps}")
P.setdefault("主干活动", [P["精确活动"], P["词组活动"], P["广泛活动"]]); P.setdefault("显示店铺", "我的店铺"); P.setdefault("显示产品", prod.get("显示产品", "我的产品")); P.setdefault("取舍人", "老板"); P.setdefault("取舍项", ["A", "B", "C", "E"])
P.update({"数据标记": "自己的数据（只在本机）", "今天": (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), "窗口前": W(27, 14), "窗口近": W(13, 0), "归因未满": "最近 3 天", "任务编号": P.get("任务编号", "R-001"), "版本": 1, "触发方式": "手动"})
P.setdefault("复盘日", (end + pd.Timedelta(days=8)).strftime("%Y-%m-%d")); P["取舍"] = "（由取舍项生成）"
json.dump(P, open(f"{DST}/参数.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1); shutil.copy(need("分组规则.json"), f"{DST}/分组规则.json")

# ---- 3. 可选表 ----
act = read(opt("活动.csv")) if opt("活动.csv") else pd.DataFrame(); bud = {r["广告活动"].strip(): money(r.get("日预算", 0)) for _, r in act.iterrows()} if len(act) else {}
tt = {r["广告活动"].strip(): ("auto" if str(r.get("投放类型", "")).lower().startswith(("auto", "自动")) else "manual") for _, r in act.iterrows()} if len(act) else {}
json.dump([{"campaignId": cid[c], "name": c, "state": "enabled", "targetingType": tt.get(c, "manual"), "budget": bud.get(c, 0), "creationDate": ""} for c in camps], open(f"{RAW}/本父体-活动.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# 3a. 活动设置（竞价策略、广告位加价）→ spCampaign.json：活动.csv 里有这几列才填，没有就留空；没有 活动.csv 就写空列表
ST = lambda x: "paused" if str(x).strip().lower().startswith(("pause", "暂停")) else "enabled"
col = lambda df, *keys: next((h for h in df.columns if any(k in norm(h) for k in keys)), None)           # 按关键词模糊找列名
def strategy(v):
    """固定/只降低/提高和降低、fixed/down_only/up_and_down、后台英文 Dynamic bids - down only、接口名 legacyForSales/autoForSales/manual 都认；认不出留空。"""
    v = str(v).strip().lower()
    if not v: return ""
    if any(k in v for k in ("up", "提高", "autoforsales")): return "up_and_down"
    if any(k in v for k in ("down", "降低", "只降", "legacy")): return "down_only"
    if any(k in v for k in ("fix", "固定", "manual")): return "fixed"
    return ""
pctv = lambda v: (lambda x: int(x) if x == int(x) else x)(money(v))                                           # 20 / 20% / 20.5% 都行
c_stg, c_pl = (col(act, "竞价策略", "biddingstrategy", "strategy"), {"placementTop": col(act, "搜索顶部", "topofsearch", "placementtop"), "placementProductPage": col(act, "商品页面", "productpage"), "placementRestOfSearch": col(act, "其余位置", "restofsearch")}) if len(act) else ("", {})
act_by = {r["广告活动"].strip(): r for _, r in act.iterrows()} if len(act) else {}
camp_set = []
for c in camps if len(act) else []:
    r = act_by.get(c); pl_ = [{"placement": k, "percentage": pctv(r[h])} for k, h in c_pl.items() if r is not None and h and money(r[h])]
    camp_set.append({"campaignId": cid[c], "name": c, "state": "enabled", "targetingType": tt.get(c, "manual"), "budget": bud.get(c, 0), "biddingStrategy": (strategy(r[c_stg]) if r is not None and c_stg else ""), "placementAdjustments": pl_, "startDate": ""})
n_set = sum(1 for x in camp_set if x["biddingStrategy"] or x["placementAdjustments"])
def rows_of(f, fn):
    if not opt(f): return []
    out = []
    for _, r in read(opt(f)).iterrows():
        c = r["广告活动"].strip()
        if c in cid: out.append(fn(r, cid[c]))
    return out
MT = lambda x: {"broad": "broad", "phrase": "phrase", "exact": "exact", "广泛": "broad", "词组": "phrase", "精确": "exact"}.get(str(x).strip().lower()[:2] if re.match(r"[一-鿿]", str(x)) else str(x).strip().lower(), str(x).strip().lower())
kws = rows_of("关键词竞价.csv", lambda r, c: {"campaignId": c, "keywordText": r["关键词"].strip(), "matchType": MT(r.get("匹配类型", "")), "bid": money(r["竞价"]), "state": ("paused" if str(r.get("状态", "")).lower().startswith(("pause", "暂停")) else "enabled")})
ne = rows_of("否定词.csv", lambda r, c: {"campaignId": c, "keywordText": r["否定词"].strip(), "matchType": ("negativePhrase" if "phrase" in str(r.get("匹配类型", "")).lower() or "词组" in str(r.get("匹配类型", "")) else "negativeExact"), "state": "enabled"})
ap = rows_of("广告产品.csv", lambda r, c: {"campaignId": c, "sku": r["SKU"].strip(), "asin": r.get("ASIN", ""), "state": ("paused" if str(r.get("状态", "")).lower().startswith(("pause", "暂停")) else "enabled")})
# 3b. 广告组（默认竞价）→ spGroup.json：groupId＝AG+活动序号；同一活动第二个组起加 -2、-3（流水线每个活动只认一个组，取最后一个）
groups = rows_of("广告组.csv", lambda r, c: {"campaignId": c, "groupId": "", "name": str(r.get("广告组", "")).strip() or r["广告活动"].strip(), "defaultBid": money(r["默认竞价"]), "state": ST(r.get("状态", ""))})
n_g = {}
for g_ in groups: n_g[g_["campaignId"]] = n_g.get(g_["campaignId"], 0) + 1; g_["groupId"] = f"AG{g_['campaignId'][1:]}" + (f"-{n_g[g_['campaignId']]}" if n_g[g_["campaignId"]] > 1 else "")
gid_of = {(g_["campaignId"], g_["name"].lower()): g_["groupId"] for g_ in groups}
# 3c. 商品定位 / 自动四组 → spTarget.json：「定位」列 B0 开头 10 位＝ASIN 定位；紧密匹配/宽泛匹配/同类产品/关联商品（或 close-match 等）＝自动四组；其余当类目，名称＝原文
AUTO_T = {"紧密匹配": "QUERY_HIGH_REL_MATCHES", "宽泛匹配": "QUERY_BROAD_REL_MATCHES", "同类产品": "ASIN_SUBSTITUTE_RELATED", "关联商品": "ASIN_ACCESSORY_RELATED"}
def expr(v):
    v = norm_tgt(v)
    if re.fullmatch(r"b0[a-z0-9]{8}", v.lower()): return "manual", {"type": "ASIN_SAME_AS", "value": v.upper(), "名称": None}
    if v in AUTO_T: return "auto", {"type": AUTO_T[v], "value": None, "名称": v}
    return "manual", {"type": "ASIN_CATEGORY_SAME_AS", "value": None, "名称": v}
def tgt_row(r, c):
    et, e = expr(r["定位"]); gname = str(r.get("广告组", "")).strip().lower()
    return {"campaignId": c, "groupId": gid_of.get((c, gname)) or gid_of.get((c, cid_name[c].lower())) or f"AG{c[1:]}", "targetId": "", "expressionType": et, "expression": [e], "bid": money(r["竞价"]), "state": ST(r.get("状态", ""))}
cid_name = {v: k for k, v in cid.items()}                                                                       # 活动ID → 活动名（广告组.csv 没填广告组名时按活动名对）
targets = rows_of("商品定位.csv", tgt_row)
for i, x in enumerate(targets, 1): x["targetId"] = f"TG{i:03d}"
# 3d. 否定 ASIN → spNeTarget.json
ne_tg = rows_of("否定ASIN.csv", lambda r, c: {"campaignId": c, "expression": [{"type": "ASIN_SAME_AS", "value": str(r["ASIN"]).strip().upper()}]})
for name, obj in (("本父体-spKeyword.json", kws), ("本父体-spNeKeyword.json", ne), ("基础-spAdProduct-全店.json", ap), ("本父体-spCampaign.json", camp_set), ("本父体-spGroup.json", groups), ("本父体-spTarget.json", targets), ("本父体-spNeTarget.json", ne_tg)):
    json.dump(obj, open(f"{RAW}/{name}", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ret = []
if opt("退货.csv"):
    for _, r in read(opt("退货.csv")).iterrows(): ret += [{"reasonStr": r["原因"].strip()}] * max(1, int(money(r.get("件数", 1)) or 1))
json.dump(ret, open(f"{RAW}/FBA退货-本父体.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(f"{RAW}/调用记录.jsonl", "w", encoding="utf-8").write(json.dumps({"path": "本地文件：搜索词报告.csv 等，未调任何接口"}) + "\n")
unused = [h for h in st.columns if h not in m.values()]
print(f"导入完成 → {DST}\n  搜索词报告 {len(d)} 行｜{d['日期'].min().date()}～{end.date()}（{span} 天）｜广告活动 {len(camps)} 个｜日期无法解析被丢弃 {bad_dates} 行\n  列对应：{m}\n  没用上的列（{len(unused)}）：{unused}\n  周度经营 {len(prof)} 周｜库存 {len(rows)} 个 SKU｜活动预算 {len(bud)}｜关键词竞价 {len(kws)}｜否定词 {len(ne)}｜广告产品 {len(ap)}｜退货 {len(ret)} 件\n  活动设置（竞价策略/广告位加价）{n_set}｜广告组 {len(groups)}｜商品定位 {len(targets)}｜否定ASIN {len(ne_tg)}\n  窗口：前 {P['窗口前']}，近 {P['窗口近']}；复盘日 {P['复盘日']}\n下一步：python3 工作台/app.py --root {DST} --port 8811")
