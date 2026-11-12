#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Amazon Ads API 取数：把广告侧的表拉成「我的数据」文件夹里的样子（和手工导出的是同一个格式）。只用标准库。

拉什么：
  报表（异步，POST /reporting/reports → 轮询 GET /reporting/reports/{id} → 下载）：
    搜索词·按天（spSearchTerm）、广告产品·按天（spAdvertisedProduct）、活动·按天（spCampaigns）、广告位·按天（spCampaigns 按广告位汇总）
  结构（POST /adsApi/v1/query/…）：活动、广告组、投放对象（关键词／否定／商品定位／自动四组）、商品广告
写成什么（数据格式.md 里的那几张表）：
  搜索词报告.csv、广告位.csv、活动.csv、广告组.csv、关键词竞价.csv、否定词.csv、广告产品.csv、商品定位.csv、否定ASIN.csv
  周度经营-接口预填.csv（只填得出 SP 广告费；件数、销售额、退款、毛利率广告接口里没有，要人补完再改名成 周度经营.csv）
拉不到的：库存.csv、产品.json、参数.json、分组规则.json —— 不是广告数据，仍然手填。

手工导表仍然可用：同一个文件夹里，人自己放的文件不会被覆盖（接口只更新它自己上次写的那些）。

  python3 _脚本/ads_report.py pull <我的数据目录>                       先不圈产品：只出 接口-产品清单.csv，看这家店在投哪些 ASIN
  python3 _脚本/ads_report.py pull <我的数据目录> --asin B0AAA,B0BBB    圈定一个产品（它的子体 ASIN），拉齐上面那些表
  python3 _脚本/ads_report.py pull <我的数据目录> --campaign-like 关键词  或者按活动名里的字圈
  python3 _脚本/ads_report.py pull <我的数据目录> --asin … --then-import <工作台根目录>   拉完直接整理成工作台能读的样子

每次调用都耗紫鸟积分：建 4 份报表 4 次，每分钟问一轮进度（最多 10 分钟），结构约 4～10 次。2026-11-12 在真实店铺上实测：四份报表第一次 26 次，圈定后再拉 5 次。
注意两条官方规矩：搜索词报表只保留 65 天、只含被点过的词；这套报表接口（Reporting v3）2027-06-30 停止出数，届时要换成 /adsApi/v1/create/reports。
报表没生成完就先停，任务编号记在目录里；过一会儿再跑同一条命令会接着取，不会重复建。
真实数据只写到你给的目录，不能是这个仓库里面。运行记录里只留个数。"""
import argparse, csv, datetime, gzip, json, os, re, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ads_api as A  # noqa: E402

CT = "application/vnd.createasyncreportrequest.v3+json"
NUM = ["impressions", "clicks", "cost", "purchases7d", "sales7d", "unitsSoldClicks7d"]
REPORTS = {   # 名字 → 报表类型、汇总到哪一层、要哪些列。都是按天、SP。
    "搜索词": {"reportTypeId": "spSearchTerm", "groupBy": ["searchTerm"], "columns": ["date", "campaignId", "campaignName", "adGroupId", "adGroupName", "keywordId", "targeting", "matchType", "keywordType", "searchTerm"] + NUM,
            "filters": [{"field": "keywordType", "values": ["BROAD", "EXACT", "PHRASE", "TARGETING_EXPRESSION", "TARGETING_EXPRESSION_PREDEFINED"]}]},
    "广告产品": {"reportTypeId": "spAdvertisedProduct", "groupBy": ["advertiser"], "columns": ["date", "campaignId", "campaignName", "adGroupId", "adGroupName", "adId", "advertisedAsin", "advertisedSku"] + NUM},
    "活动": {"reportTypeId": "spCampaigns", "groupBy": ["campaign"], "columns": ["date", "campaignId", "campaignName", "campaignStatus", "campaignBudgetAmount", "campaignBiddingStrategy"] + NUM},
    "广告位": {"reportTypeId": "spCampaigns", "groupBy": ["campaign", "campaignPlacement"], "columns": ["date", "campaignId", "campaignName", "placementClassification"] + NUM},   # SP 没有单独的广告位报表：活动报表按广告位汇总
}
MAX_DAYS, KEEP_DAYS = 31, 65                 # 官方文档：一份报表最多跨 31 天；搜索词报表只保留 65 天（其余多数 95 天），按最短的卡
ST = {"ENABLED": "enabled", "PAUSED": "paused"}
STRATEGY = {"MANUAL": "固定", "SALES_DOWN_ONLY": "只降低", "SALES_UP_AND_DOWN": "提高和降低"}
PLACE = {"TOP_OF_SEARCH": "搜索顶部加价", "PRODUCT_PAGE": "商品页面加价", "REST_OF_SEARCH": "其余位置加价"}
AUTO = {"KEYWORDS_CLOSE_MATCH": "close-match", "KEYWORDS_LOOSE_MATCH": "loose-match", "PRODUCT_SUBSTITUTES": "substitutes", "PRODUCT_COMPLEMENTS": "complements"}   # 新版把自动投放四组叫「主题投放」
API_FILES = ["搜索词报告.csv", "广告位.csv", "活动.csv", "广告组.csv", "关键词竞价.csv", "否定词.csv", "广告产品.csv", "商品定位.csv", "否定ASIN.csv", "周度经营-接口预填.csv", "接口-产品清单.csv", "接口编号.json"]
HAND_FILES = ["周度经营.csv", "库存.csv", "产品.json", "参数.json", "分组规则.json"]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def jread(p, d=None):
    try:
        with open(p, encoding="utf-8") as fh: return json.load(fh)
    except (OSError, ValueError): return d


def jwrite(p, v):
    with open(p, "w", encoding="utf-8") as fh: json.dump(v, fh, ensure_ascii=False, indent=1)


def data_dir(root, out=None):
    """数据写到哪：命令行给的 > agent/.env.local 的 ADS_DATA_DIR > ads.config.json 的 ads_api.数据目录。不能在仓库里面。"""
    out = out or A.local_env().get("ADS_DATA_DIR") or A.settings(root).get("数据目录") or ""
    if not out: return ""
    out = os.path.abspath(os.path.expanduser(out)); repo = os.path.realpath(A.REPO)
    if os.path.isdir(os.path.join(repo, ".git")) and (os.path.realpath(out) + os.sep).startswith(repo + os.sep):
        raise A.AdsError("数据目录不能放在这个仓库里面（这是真实店铺的数据）。换一个仓库外面的目录，比如 ~/ads-lab-mine/我的数据")
    return out


def window(days, end=None, today=None):
    today = today or datetime.date.today(); end = datetime.date.fromisoformat(end) if end else today - datetime.timedelta(days=1)
    days = max(7, min(int(days), MAX_DAYS)); start = end - datetime.timedelta(days=days - 1)
    if (today - start).days > KEEP_DAYS: raise A.AdsError(f"开始日期 {start} 太早：搜索词报表只保留 {KEEP_DAYS} 天，更早的已经拿不到了")
    return start.isoformat(), end.isoformat()


# ------------------------------------------------------------------ 报表：建 → 问进度 → 下载
def body(name, start, end):
    r = REPORTS[name]
    return {"name": f"ads-workbench {r['reportTypeId']} {start}~{end}", "startDate": start, "endDate": end,
            "configuration": {"adProduct": "SPONSORED_PRODUCTS", "reportTypeId": r["reportTypeId"], "groupBy": r["groupBy"], "columns": r["columns"], "timeUnit": "DAILY", "format": "GZIP_JSON", **({"filters": r["filters"]} if r.get("filters") else {})}}


def create(ch, name, start, end):
    try: r = ch.http("POST", "/reporting/reports", body(name, start, end), ctype=CT)
    except A.AdsError as e:                                    # 同样的报表刚建过：平台回「重复」，并给出已有的那一份的编号，直接用它
        m = UUID.search(str(e))
        if m and ("duplicate" in str(e).lower() or "重复" in str(e)): return m.group(0)
        raise
    if not isinstance(r, dict) or not r.get("reportId"): raise A.AdsError("建报表的回包里没有报表编号")
    return str(r["reportId"])


def status(ch, rid):
    r = ch.http("GET", f"/reporting/reports/{rid}")
    if not isinstance(r, dict) or not r.get("status"): raise A.AdsError("问报表进度的回包不是预期的样子")
    return r


def download(url):
    """报表文件在亚马逊给的临时地址上，直接下载；不经过紫鸟，也不带任何授权。只当数据解析。"""
    if not str(url).lower().startswith("https://"): raise A.AdsError("报表下载地址不是 https")
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ads-workbench"}), timeout=120).read()
    try: raw = gzip.decompress(raw)
    except OSError: pass
    rows = json.loads(raw.decode("utf-8"))
    if not isinstance(rows, list): raise A.AdsError("报表文件不是一张表")
    return rows


def reports(ch, out, start, end, names=None, wait=600, every=60, sleep=time.sleep, fetch=download, say=print):
    """返回 (已取到的 {名字: 行}, 还在生成的 [名字])。任务编号记在 <out>/.接口任务.json，下次接着取。"""
    names = names or list(REPORTS); tf = os.path.join(out, ".接口任务.json"); task = jread(tf) or {}; cf = os.path.join(out, ".接口报表.json.gz"); key = [start, end, ch.cfg["country"], datetime.date.today().isoformat()]
    got = {}
    try:
        with gzip.open(cf, "rt", encoding="utf-8") as fh: c = json.load(fh)
        if c.get("key") == key: got = {n: c["R"][n] for n in names if n in c["R"]}
    except (OSError, ValueError, KeyError): pass
    if got: say(f"  报表：{'、'.join(got)} 今天已经取过这一段，直接用（不重建、不花积分）")
    names = [n for n in names if n not in got]
    if not names: return got, []
    if task.get("范围") != [start, end] or task.get("站点") != ch.cfg["country"]: task = {"范围": [start, end], "站点": ch.cfg["country"], "报表": {}}
    for n in names:
        if n not in task["报表"]: task["报表"][n] = create(ch, n, start, end); say(f"  建报表：{n}"); jwrite(tf, task)
    pending, waited = list(names), 0
    while pending:
        if waited: sleep(every)
        elif every: sleep(min(every, 30))                         # 刚建完不会立刻好，先等一会儿再问
        waited += every or 1
        for n in list(pending):
            st = status(ch, task["报表"][n]); s = str(st["status"]).upper()
            if s == "COMPLETED": got[n] = fetch(st.get("url")); pending.remove(n); say(f"  取到：{n} {len(got[n])} 行")
            elif s in ("FAILED", "FATAL", "CANCELLED"):
                task["报表"].pop(n, None); jwrite(tf, task); raise A.AdsError(f"报表「{n}」生成失败：{str(st.get('failureReason') or s)[:120]}")
        if pending and waited >= wait: break
    if not pending and os.path.exists(tf): os.remove(tf)
    if got:
        with gzip.open(cf, "wt", encoding="utf-8") as fh: json.dump({"key": key, "R": got}, fh, ensure_ascii=False)     # 同一天再拉（先看产品清单、再圈产品；或后来多要一份报表）只建缺的
    return got, pending


# ------------------------------------------------------------------ 圈定产品 → 结构
def scope(rows_ad, rows_camp, asins=None, like=None):
    """这次只要哪些活动。asins：投过这些 ASIN 的活动；like：活动名里含这几个字。都没给＝不圈。"""
    asins = {a.strip().upper() for a in (asins or []) if a.strip()}; like = (like or "").strip().lower()
    if not asins and not like: return None
    ids = {str(r.get("campaignId")) for r in rows_ad if str(r.get("advertisedAsin", "")).upper() in asins} if asins else {str(r.get("campaignId")) for r in rows_ad + rows_camp}
    if like: ids = {str(r.get("campaignId")) for r in rows_ad + rows_camp if like in str(r.get("campaignName", "")).lower() and str(r.get("campaignId")) in ids}
    return ids


def chunks(xs, n): xs = list(xs); return [xs[i:i + n] for i in range(0, len(xs), n)]


def structure(ch, cids, size=500):
    out = {"campaigns": [], "adGroups": [], "targets": [], "ads": []}
    for kind, per in (("campaigns", 1000), ("adGroups", 100), ("targets", 100), ("ads", 100)):
        for part in chunks(sorted(cids), per):
            flt = {"campaignIdFilter": {"include": part}, "stateFilter": {"include": ["ENABLED", "PAUSED"]}}
            try: rows, full = ch.query(kind, flt, pages=50, size=size)
            except A.AdsError:
                if size <= 100: raise
                rows, full = ch.query(kind, flt, pages=200, size=100)     # 这类对象不接受大页，退回每页 100
            if not full: raise A.AdsError(f"{kind} 太多，没读完")
            out[kind] += rows
    return out


def place_name(v):
    """报表里的广告位写法 → 搜索顶部／商品页面／其余位置。官方文档没列全取值，按字面认；认不出的原样留着，规则不会用它。"""
    s = str(v or "").lower()
    if "business" in s: return "Amazon Business"
    if "off" in s and "amazon" in s: return "站外"
    if "top" in s: return "搜索顶部"
    if "detail" in s or "product" in s: return "商品页面"
    if "rest" in s or "other" in s: return "其余位置"
    return str(v or "")


def budget(c):
    for b in c.get("budgets") or []:
        if b.get("recurrenceTimePeriod") == "DAILY":
            v = ((b.get("budgetValue") or {}).get("monetaryBudgetValue") or {}).get("monetaryBudget") or {}
            if v.get("value") is not None: return v["value"]
    return ""


def tables(S, R, cids, start, end):
    """结构 S + 报表 R → 各张表的行（第一行是表头）。只留圈定的活动。"""
    cname = {str(c["campaignId"]): str(c.get("name", "")).strip() for c in S["campaigns"]}; gname = {str(g["adGroupId"]): str(g.get("name", "")).strip() for g in S["adGroups"]}
    gbid = {str(g["adGroupId"]): (g.get("bid") or {}).get("defaultBid") for g in S["adGroups"]}
    auto = {str(t.get("campaignId")) for t in S["targets"] if t.get("targetType") == "THEME"}
    sku_asin = {}
    for r in R.get("广告产品", []):
        if r.get("advertisedSku") and r.get("advertisedAsin"): sku_asin[str(r["advertisedSku"])] = str(r["advertisedAsin"])
    T = {"活动.csv": [["广告活动", "日预算", "投放类型", "竞价策略", "搜索顶部加价", "商品页面加价", "其余位置加价"]], "广告组.csv": [["广告活动", "广告组", "默认竞价", "状态"]],
         "关键词竞价.csv": [["广告活动", "关键词", "匹配类型", "竞价", "状态"]], "否定词.csv": [["广告活动", "否定词", "匹配类型"]], "广告产品.csv": [["广告活动", "SKU", "ASIN", "状态"]],
         "商品定位.csv": [["广告活动", "广告组", "定位", "竞价", "状态"]], "否定ASIN.csv": [["广告活动", "ASIN"]]}
    for c in S["campaigns"]:
        bs = ((c.get("optimizations") or {}).get("bidSettings") or {}); pl = {p.get("placement"): p.get("percentage") for p in ((bs.get("bidAdjustments") or {}).get("placementBidAdjustments") or [])}
        T["活动.csv"].append([cname[str(c["campaignId"])], budget(c), "自动" if str(c["campaignId"]) in auto else "手动", STRATEGY.get(bs.get("bidStrategy"), ""), *[pl.get(k) or "" for k in PLACE]])
    for g in S["adGroups"]: T["广告组.csv"].append([cname.get(str(g.get("campaignId")), ""), gname[str(g["adGroupId"])], gbid[str(g["adGroupId"])] if gbid[str(g["adGroupId"])] is not None else "", ST.get(g.get("state"), "")])
    for t in S["targets"]:
        cn = cname.get(str(t.get("campaignId")), ""); gn = gname.get(str(t.get("adGroupId")), ""); d = t.get("targetDetails") or {}; neg = t.get("negative") is True; st = ST.get(t.get("state"), "")
        bid = (t.get("bid") or {}).get("bid"); bid = bid if bid is not None else (gbid.get(str(t.get("adGroupId"))) if gbid.get(str(t.get("adGroupId"))) is not None else "")
        if not cn: continue
        ty = t.get("targetType")
        if ty == "KEYWORD":
            k = d.get("keywordTarget") or {}; mt = str(k.get("matchType", "")).lower()
            if neg: T["否定词.csv"].append([cn, k.get("keyword", ""), "negativePhrase" if mt == "phrase" else "negativeExact"])
            else: T["关键词竞价.csv"].append([cn, k.get("keyword", ""), mt, bid, st])
        elif ty == "PRODUCT":
            asin = str(((d.get("productTarget") or {}).get("product") or {}).get("productId", "")).upper()
            if neg: T["否定ASIN.csv"].append([cn, asin])
            else: T["商品定位.csv"].append([cn, gn, asin, bid, st])
        elif ty == "THEME" and not neg:
            m = (d.get("themeTarget") or {}).get("matchType")
            if m in AUTO: T["商品定位.csv"].append([cn, gn, AUTO[m], bid, st])
        elif ty == "PRODUCT_CATEGORY" and not neg:
            ref = ((d.get("productCategoryTarget") or {}).get("productCategoryRefinement") or {}).get("productCategoryRefinement") or {}
            T["商品定位.csv"].append([cn, gn, str(ref.get("productCategoryIdResolved") or ref.get("productCategoryId") or "类目"), bid, st])
    for a in S["ads"]:
        p = ((((a.get("creative") or {}).get("productCreative") or {}).get("productCreativeSettings") or {}).get("advertisedProduct") or {})
        sku = p.get("productId", "") if p.get("productIdType") == "SKU" else ""; asin = p.get("resolvedProductId") if p.get("resolvedProductIdType") == "ASIN" else (p.get("productId") if p.get("productIdType") == "ASIN" else sku_asin.get(str(sku), ""))
        T["广告产品.csv"].append([cname.get(str(a.get("campaignId")), ""), sku, asin or "", ST.get(a.get("state"), "")])
    mt = lambda v: str(v).upper() if str(v).upper() in ("BROAD", "PHRASE", "EXACT") else ""
    T["搜索词报告.csv"] = [["日期", "广告活动", "广告组", "投放", "匹配类型", "客户搜索词", "曝光量", "点击量", "花费", "7天总销售额", "7天总订单数", "7天总销量"]] + [
        [r.get("date"), str(r.get("campaignName", "")).strip(), r.get("adGroupName", ""), r.get("targeting", ""), mt(r.get("matchType")), r.get("searchTerm", ""), r.get("impressions") or 0, r.get("clicks") or 0, r.get("cost") or 0, r.get("sales7d") or 0, r.get("purchases7d") or 0, r.get("unitsSoldClicks7d") or 0]
        for r in sorted(R.get("搜索词", []), key=lambda r: (str(r.get("date")), str(r.get("campaignName")), str(r.get("searchTerm")))) if cids is None or str(r.get("campaignId")) in cids]
    T["广告位.csv"] = [["日期", "广告活动", "广告位", "曝光量", "点击量", "花费", "7天总销售额", "7天总订单数"]] + [
        [r.get("date"), str(r.get("campaignName", "")).strip(), place_name(r.get("placementClassification")), r.get("impressions") or 0, r.get("clicks") or 0, r.get("cost") or 0, r.get("sales7d") or 0, r.get("purchases7d") or 0]
        for r in sorted(R.get("广告位", []), key=lambda r: (str(r.get("date")), str(r.get("campaignName")), str(r.get("placementClassification")))) if cids is None or str(r.get("campaignId")) in cids]
    e = datetime.date.fromisoformat(end); wk = [["周起始日", "件数", "销售额", "SP广告费", "SB广告费", "SBV广告费", "退款件", "广告前毛利率"]]
    for i in (3, 2, 1, 0):
        a = e - datetime.timedelta(days=7 * i + 6); b = a + datetime.timedelta(days=6)
        if a.isoformat() < start: continue
        sp = sum(float(r.get("cost") or 0) for r in R.get("活动", []) if (cids is None or str(r.get("campaignId")) in cids) and a.isoformat() <= str(r.get("date")) <= b.isoformat())
        wk.append([a.isoformat(), "", "", round(sp, 2), "", "", "", ""])
    T["周度经营-接口预填.csv"] = wk
    ids = {"说明": "接口里的真实编号，只留在本机。通过接口执行动作时要用。", "活动": {cname[k]: k for k in cname}, "广告组": {f"{cname.get(str(g.get('campaignId')), '')}｜{gname[str(g['adGroupId'])]}": str(g["adGroupId"]) for g in S["adGroups"]},
           "投放对象": [{"活动": cname.get(str(t.get("campaignId")), ""), "类型": t.get("targetType"), "否定": t.get("negative") is True, "编号": str(t.get("targetId"))} for t in S["targets"]], "商品广告": [{"活动": cname.get(str(a.get("campaignId")), ""), "编号": str(a.get("adId"))} for a in S["ads"]]}
    return T, ids


def products(rows):
    """没圈产品时给人看的清单：这家店在投哪些 ASIN，各花了多少。"""
    by = {}
    for r in rows:
        a = str(r.get("advertisedAsin", "")).upper()
        if not a: continue
        x = by.setdefault(a, {"sku": set(), "camp": set(), "cost": 0.0, "sales": 0.0}); x["sku"].add(str(r.get("advertisedSku", ""))); x["camp"].add(str(r.get("campaignName", ""))); x["cost"] += float(r.get("cost") or 0); x["sales"] += float(r.get("sales7d") or 0)
    return [["ASIN", "SKU", "投它的活动数", "花费", "广告销售额", "活动名（前几个）"]] + [[a, "、".join(sorted(x["sku"]))[:80], len(x["camp"]), round(x["cost"], 2), round(x["sales"], 2), "、".join(sorted(x["camp"])[:4])] for a, x in sorted(by.items(), key=lambda kv: -kv[1]["cost"])]


def save(out, T, ids=None):
    """写文件。人自己放的不动：上次不是接口写的、现在又已经在那儿的文件，一律跳过。"""
    mf = os.path.join(out, ".接口拉取.json"); mine = set((jread(mf) or {}).get("文件") or []); files = []
    for name, rows in T.items():
        p = os.path.join(out, name)
        if os.path.exists(p) and name not in mine: files.append({"名": name, "行数": None, "来源": "人放的，没动"}); continue
        with open(p, "w", encoding="utf-8-sig", newline="") as fh: csv.writer(fh).writerows(rows)
        mine.add(name); files.append({"名": name, "行数": len(rows) - 1, "来源": "接口"})
    if ids is not None: jwrite(os.path.join(out, "接口编号.json"), ids); mine.add("接口编号.json")
    jwrite(mf, {"文件": sorted(mine), "时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return files


def pull(root, out=None, asins=None, like=None, days=MAX_DAYS, end=None, transport=None, fetch=download, sleep=time.sleep, wait=600, every=60, say=lambda s: None, record=True, today=None):
    """拉一次。返回只含个数的记录（也写到 运行记录/ads-api-报表.json）。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"); cfg = A.settings(root); ch = A.Channel(cfg, transport)
    doc = {"时间": now, "站点": cfg["country"], "步骤": [], "文件": [], "ok": False, "还在生成": [], "圈定": bool(asins or like)}
    def step(name, ok, note): doc["步骤"].append({"名": name, "ok": ok, "说明": note}); say(("✓ " if ok else "✗ ") + name + "：" + note)
    try:
        out = data_dir(root, out)
        if not out: raise A.AdsError("没说数据写到哪：命令行给目录，或在 agent/.env.local 里写 ADS_DATA_DIR=仓库外面的一个目录")
        os.makedirs(out, exist_ok=True); doc["目录"] = out; start, end = window(days, end, today); doc["范围"] = [start, end]
        ch.identify(); step("店铺和广告账号", True, f"{ch.profile.get('countryCode')} 站卖家账号，币种 {ch.profile.get('currencyCode')}")
        R, pending = reports(ch, out, start, end, wait=wait, every=every, sleep=sleep, fetch=fetch, say=say)
        if pending:
            doc["还在生成"] = pending; step("报表", False, f"{'、'.join(pending)} 还在生成（等了 {wait // 60} 分钟）。任务编号已记下，过几分钟再拉一次会接着取，不会重复建")
            raise StopIteration
        step("报表", True, f"{start}～{end}，" + "、".join(f"{n} {len(R[n])} 行" for n in REPORTS))
        cids = scope(R["广告产品"], R["活动"], asins, like)
        if cids is None:
            doc["文件"] = save(out, {"接口-产品清单.csv": products(R["广告产品"])})
            step("圈定产品", False, f"还没圈产品：这家店这段时间投了 {len(products(R['广告产品'])) - 1} 个 ASIN，清单在 接口-产品清单.csv。挑一个产品的子体 ASIN，用 --asin 再拉一次（报表不会重建）")
            raise StopIteration
        if not cids: raise A.AdsError("按你给的 ASIN／活动名，没有圈到任何活动")
        step("圈定产品", True, f"圈到 {len(cids)} 个活动")
        S = structure(ch, cids); live = {str(c["campaignId"]) for c in S["campaigns"]}
        step("结构", True, f"活动 {len(S['campaigns'])}、广告组 {len(S['adGroups'])}、投放对象 {len(S['targets'])}、商品广告 {len(S['ads'])}（已归档的不要）")
        T, ids = tables(S, R, cids, start, end); doc["文件"] = save(out, T, ids)
        names = [r[0] for r in T["活动.csv"][1:]]
        if len(names) != len(set(names)): step("活动名", False, "有重名的活动：工作台按活动名对表，重名的会串。先在后台改名")
        miss = [f for f in HAND_FILES if not os.path.exists(os.path.join(out, f))]
        step("写表", True, f"{sum(1 for f in doc['文件'] if f['来源'] == '接口')} 张表写好" + (f"；{sum(1 for f in doc['文件'] if f['来源'] != '接口')} 张是人放的，没动" if any(f["来源"] != "接口" for f in doc["文件"]) else ""))
        doc["还要人补"] = miss + ([] if os.path.exists(os.path.join(out, "周度经营.csv")) else ["周度经营-接口预填.csv 补上件数、销售额、退款件、毛利率后改名成 周度经营.csv"])
        doc["ok"] = True
        if len(live) < len(cids): step("提醒", True, f"报表里有 {len(cids) - len(live)} 个活动现在已归档，结构表里没有它们")
    except StopIteration: pass
    except A.AdsError as e: step("没走通", False, str(e))
    except Exception as e: step("没走通", False, type(e).__name__)
    doc["调用次数"] = ch.calls
    if record:
        os.makedirs(f"{root}/运行记录", exist_ok=True); jwrite(f"{root}/运行记录/ads-api-报表.json", {k: v for k, v in doc.items()})
    return doc


def then_import(out, dst, say=print):
    miss = [f for f in HAND_FILES if not os.path.exists(os.path.join(out, f))]
    if miss: say("还不能整理成工作台的样子，缺人填的这几样：" + "、".join(miss) + "（见 数据格式.md）"); return 2
    p = subprocess.run([sys.executable, os.path.join(A.REPO, "_脚本", "import_my_data.py"), out, dst], capture_output=True, text=True)
    say((p.stdout or p.stderr).strip()[-1500:]); return p.returncode


def main():
    ap = argparse.ArgumentParser(description="从 Amazon Ads API 拉广告侧的数据，写成「我的数据」里的那几张表"); ap.add_argument("cmd", choices=["pull"]); ap.add_argument("out", nargs="?")
    ap.add_argument("--root", default=os.environ.get("ADS_ROOT") or A.REPO); ap.add_argument("--asin", default=""); ap.add_argument("--campaign-like", default=""); ap.add_argument("--days", type=int, default=MAX_DAYS); ap.add_argument("--end", default="")
    ap.add_argument("--wait", type=int, default=600); ap.add_argument("--then-import", default="")
    a = ap.parse_args(); e = A.local_env(); asins = [x for x in (a.asin or e.get("ADS_SCOPE_ASINS", "")).split(",") if x.strip()]; like = a.campaign_like or e.get("ADS_SCOPE_CAMPAIGN_LIKE", "")
    print("⚠️ 接下来的接口调用将消耗紫鸟积分（建报表 4 次，每分钟问一轮进度，结构约 4～10 次）。")
    d = pull(os.path.abspath(a.root), a.out, asins, like, a.days, a.end or None, wait=a.wait, say=print)
    for f in d["文件"]: print(f"  {f['名']}：{f['行数'] if f['行数'] is not None else '—'} 行（{f['来源']}）")
    if d.get("还要人补"): print("还要人补：" + "；".join(d["还要人补"]))
    print(f"调用 {d['调用次数']} 次 → {d.get('目录', '')}")
    if d["ok"] and a.then_import: return then_import(d["目录"], os.path.abspath(os.path.expanduser(a.then_import)))
    return 0 if d["ok"] else (3 if d["还在生成"] or not d["圈定"] else 1)


if __name__ == "__main__":
    sys.exit(main())
