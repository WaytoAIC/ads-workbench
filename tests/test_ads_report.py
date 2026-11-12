# -*- coding: utf-8 -*-
"""从广告接口取数 _脚本/ads_report.py 的测试。全部用假通道和假下载，不联网、不花积分、不碰任何真实店铺。
假数据是拿 我的数据-示例/ 里那几张手工表反推出来的：所以「接口拉的」和「手工导的」应该整理出同一份工作台输入。
用法：python3 -m unittest tests.test_ads_report -v"""
import csv, datetime, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_biz import REPO
sys.path.insert(0, os.path.join(REPO, "_脚本")); import ads_api as A, ads_report as R  # noqa: E402

SAMPLE = os.path.join(REPO, "我的数据-示例"); CFG = {"store": "测试店", "store_id": "", "country": "US", "enabled": False, "通道": "假"}
rd = lambda f: list(csv.DictReader(open(os.path.join(SAMPLE, f), encoding="utf-8-sig")))
num = lambda v: float(str(v).replace("$", "").replace(",", "").replace("%", "") or 0)
AUTO = {"紧密匹配": "KEYWORDS_CLOSE_MATCH", "宽泛匹配": "KEYWORDS_LOOSE_MATCH", "同类产品": "PRODUCT_SUBSTITUTES", "关联商品": "PRODUCT_COMPLEMENTS"}
PLACE = {"搜索顶部加价": "TOP_OF_SEARCH", "商品页面加价": "PRODUCT_PAGE", "其余位置加价": "REST_OF_SEARCH"}
STG = {"固定": "MANUAL", "只降低": "SALES_DOWN_ONLY", "提高和降低": "SALES_UP_AND_DOWN"}


def world():
    """把示例里的手工表变成「接口会回的样子」。"""
    st = rd("搜索词报告.csv"); names = sorted({r["Campaign Name"] for r in st} | {r["广告活动"] for r in rd("活动.csv")}); cid = {n: f"9{i:03d}" for i, n in enumerate(names)}; gid = {n: f"8{i:03d}" for i, n in enumerate(names)}
    act = {r["广告活动"]: r for r in rd("活动.csv")}; camps = []
    for n in names:
        a = act.get(n, {})
        camps.append({"campaignId": cid[n], "name": n, "state": "ENABLED", "budgets": [{"budgetType": "MONETARY", "recurrenceTimePeriod": "DAILY", "budgetValue": {"monetaryBudgetValue": {"monetaryBudget": {"currencyCode": "USD", "value": num(a.get("日预算", 0))}}}}],
                      "optimizations": {"bidSettings": {"bidStrategy": STG.get(a.get("竞价策略", ""), "MANUAL"), "bidAdjustments": {"placementBidAdjustments": [{"placement": v, "percentage": int(num(a[k]))} for k, v in PLACE.items() if a.get(k)]}}}})
    groups = [{"adGroupId": gid[r["广告活动"]], "campaignId": cid[r["广告活动"]], "name": r["广告组"], "state": r["状态"].upper(), "bid": {"defaultBid": num(r["默认竞价"])}} for r in rd("广告组.csv")]
    T = []; base = lambda c, **k: {"targetId": f"7{len(T):04d}", "campaignId": cid[c], "adGroupId": gid[c], "adProduct": "SPONSORED_PRODUCTS", "targetLevel": "AD_GROUP", **k}
    for r in rd("关键词竞价.csv"): T.append(base(r["广告活动"], negative=False, state=r["状态"].upper(), targetType="KEYWORD", bid={"bid": num(r["竞价"])}, targetDetails={"keywordTarget": {"keyword": r["关键词"], "matchType": r["匹配类型"].upper()}}))
    for r in rd("否定词.csv"): T.append(base(r["广告活动"], negative=True, state="ENABLED", targetType="KEYWORD", targetDetails={"keywordTarget": {"keyword": r["否定词"], "matchType": "PHRASE" if "hrase" in r["匹配类型"] else "EXACT"}}))
    for r in rd("商品定位.csv"):
        v = r["定位"]; k = dict(negative=False, state=(r["状态"] or "enabled").upper(), bid={"bid": num(r["竞价"])})
        if v in AUTO: T.append(base(r["广告活动"], targetType="THEME", targetDetails={"themeTarget": {"matchType": AUTO[v]}}, **k))
        elif v.upper().startswith("B0") and len(v) == 10: T.append(base(r["广告活动"], targetType="PRODUCT", targetDetails={"productTarget": {"matchType": "PRODUCT_EXACT", "productIdType": "ASIN", "product": {"productId": v}}}, **k))
        else: T.append(base(r["广告活动"], targetType="PRODUCT_CATEGORY", targetDetails={"productCategoryTarget": {"productCategoryRefinement": {"productCategoryRefinement": {"productCategoryId": "1", "productCategoryIdResolved": v}}}}, **k))
    for r in rd("否定ASIN.csv"): T.append(base(r["广告活动"], negative=True, state="ENABLED", targetType="PRODUCT", targetDetails={"productTarget": {"matchType": "PRODUCT_EXACT", "productIdType": "ASIN", "product": {"productId": r["ASIN"]}}}))
    T.append(base(names[0], negative=False, state="ARCHIVED", targetType="KEYWORD", bid={"bid": 9}, targetDetails={"keywordTarget": {"keyword": "已归档的词", "matchType": "EXACT"}}))
    ads = [{"adId": f"6{i:04d}", "campaignId": cid[r["广告活动"]], "adGroupId": gid[r["广告活动"]], "state": r["状态"].upper(), "creative": {"productCreative": {"productCreativeSettings": {"advertisedProduct": {"productId": r["SKU"], "productIdType": "SKU", "resolvedProductId": r["ASIN"], "resolvedProductIdType": "ASIN"}}}}} for i, r in enumerate(rd("广告产品.csv"))]
    iso = lambda d: datetime.datetime.strptime(d, "%b %d, %Y").date().isoformat()
    term = [{"date": iso(r["Date"]), "campaignId": cid[r["Campaign Name"]], "campaignName": r["Campaign Name"], "adGroupName": r["Ad Group Name"], "targeting": r["Targeting"], "matchType": r["Match Type"] if r["Match Type"] in ("BROAD", "PHRASE", "EXACT") else "TARGETING_EXPRESSION",
             "searchTerm": r["Customer Search Term"], "impressions": int(num(r["Impressions"])), "clicks": int(num(r["Clicks"])), "cost": num(r["Spend"]), "sales7d": num(r["7 Day Total Sales"]), "purchases7d": int(num(r["7 Day Total Orders (#)"])), "unitsSoldClicks7d": int(num(r["7 Day Total Units (#)"]))} for r in st]
    days = sorted({t["date"] for t in term})
    adp = [{"date": days[-1], "campaignId": a["campaignId"], "campaignName": next(n for n in names if cid[n] == a["campaignId"]), "advertisedAsin": "B0TEST" + f"{i % 3:04d}", "advertisedSku": a["creative"]["productCreative"]["productCreativeSettings"]["advertisedProduct"]["productId"], "cost": 1.0, "sales7d": 2.0} for i, a in enumerate(ads)]
    by = {}
    for t in term: by[(t["date"], t["campaignId"], t["campaignName"])] = by.get((t["date"], t["campaignId"], t["campaignName"]), 0) + t["cost"]
    camp = [{"date": d, "campaignId": c, "campaignName": n, "cost": round(v, 2)} for (d, c, n), v in by.items()]
    place = [{"date": d, "campaignId": c, "campaignName": n, "placementClassification": pc, "impressions": 100, "clicks": 10, "cost": round(v * share, 2), "sales7d": round(v * share * 3, 2), "purchases7d": 1}
             for (d, c, n), v in by.items() for pc, share in (("Top of Search on-Amazon", 0.5), ("Detail Page on-Amazon", 0.3), ("Other on-Amazon", 0.2))]
    return {"campaigns": camps, "adGroups": groups, "targets": T, "ads": ads, "搜索词": term, "广告产品": adp, "活动": camp, "广告位": place, "end": days[-1], "cid": cid}


W = world()


class Fake:
    def __init__(self, slow=0, dup=False, fail=None):
        self.log, self.slow, self.dup, self.fail, self.polls = [], slow, dup, fail, 0

    def __call__(self, args):
        self.log.append(args)
        if args[:2] == ["account", "stores"]: return [{"store_id": 100, "store_name": "测试店"}]
        if args[:2] == ["account", "platform-auths"]: return [{"seller_account_id": 100, "region": "NA", "auth_status": 1}]
        method, path = args[1], args[2]; body = json.loads(args[args.index("--body") + 1]) if "--body" in args else None
        if path.endswith("/v2/profiles"): return [{"profileId": 9, "countryCode": "US", "currencyCode": "USD", "accountInfo": {"type": "seller"}}]
        if path.endswith("/reporting/reports") and method == "POST":
            t = body["configuration"]["reportTypeId"] + ("/placement" if "campaignPlacement" in body["configuration"]["groupBy"] else "")
            rid = {"spSearchTerm": "11111111-1111-4111-8111-111111111111", "spAdvertisedProduct": "22222222-2222-4222-8222-222222222222", "spCampaigns": "33333333-3333-4333-8333-333333333333", "spCampaigns/placement": "44444444-4444-4444-8444-444444444444"}[t]
            if self.dup: raise A.AdsError("接口回了业务错误：The Request is a duplicate of : " + rid)
            return {"reportId": rid, "status": "PENDING"}
        if "/reporting/reports/" in path and method == "GET":
            self.polls += 1; rid = path.rsplit("/", 1)[1]; name = {"1": "搜索词", "2": "广告产品", "3": "活动", "4": "广告位"}[rid[0]]
            if self.fail == name: return {"reportId": rid, "status": "FAILED", "failureReason": "报表类型不支持这个列"}
            if self.polls <= self.slow: return {"reportId": rid, "status": "PROCESSING"}
            return {"reportId": rid, "status": "COMPLETED", "url": "https://example.invalid/" + name}
        for kind in ("campaigns", "adGroups", "targets", "ads"):
            if path.endswith("query/" + kind):
                inc = set(body["campaignIdFilter"]["include"]); return {kind: [x for x in W[kind] if x["campaignId"] in inc and x["state"] in body["stateFilter"]["include"]]}
        raise AssertionError("没想到的调用 " + path)

    def n(self, method, frag): return sum(1 for a in self.log if a[0] == "http" and a[1] == method and frag in a[2])
    def writes(self): return [a for a in self.log if a[0] == "http" and any(k in a[2] for k in ("/update/", "/create/", "/delete/"))]


fetch = lambda url: W[url.rsplit("/", 1)[1]]
TODAY = datetime.date.fromisoformat(W["end"]) + datetime.timedelta(days=1)


def pull(out, f=None, root=None, **k):
    f = f or Fake(); root = root or tempfile.mkdtemp(prefix="ads-rpt-root-")
    with mock.patch.object(A, "settings", return_value=dict(CFG)), mock.patch.object(A, "local_env", return_value={}):
        return R.pull(root, out, transport=f, fetch=fetch, sleep=lambda s: None, today=TODAY, days=31, **k), f, root


class 取数(unittest.TestCase):
    def setUp(self): self.out = tempfile.mkdtemp(prefix="ads-rpt-")
    def tearDown(self): shutil.rmtree(self.out, ignore_errors=True)
    def rows(self, f): return list(csv.reader(open(os.path.join(self.out, f), encoding="utf-8-sig")))

    def test_没圈产品_只出产品清单_不读结构(self):
        d, f, _ = pull(self.out)
        self.assertFalse(d["ok"]); self.assertFalse(d["圈定"]); self.assertEqual([x["名"] for x in d["文件"]], ["接口-产品清单.csv"])
        self.assertEqual(f.n("POST", "/reporting/reports"), 4); self.assertEqual(f.n("POST", "/query/"), 0); self.assertEqual(f.writes(), [])
        h = json.loads(f.log[3][f.log[3].index("--headers") + 1]); self.assertEqual(h["Content-Type"], R.CT); self.assertEqual(h["Amazon-Advertising-API-Scope"], "9")
        self.assertIn("/proxy/na/reporting/reports", f.log[3][2]); self.assertNotIn("adsApi", f.log[3][2])

    def test_圈定之后_八张表都写出来_和手工表对得上(self):
        d, f0, _ = pull(self.out, like="")  # 先不圈：看产品清单
        d, f, _ = pull(self.out, asins=["B0TEST0000", "B0TEST0001", "B0TEST0002"])
        self.assertEqual(f.n("POST", "/reporting/reports"), 0, "同一天第二次拉，不该重建报表")
        self.assertTrue(d["ok"], d["步骤"]); got = {x["名"]: x["行数"] for x in d["文件"] if x["来源"] == "接口"}
        for name, src in (("活动.csv", "活动.csv"), ("广告组.csv", "广告组.csv"), ("关键词竞价.csv", "关键词竞价.csv"), ("否定词.csv", "否定词.csv"), ("广告产品.csv", "广告产品.csv"), ("商品定位.csv", "商品定位.csv"), ("否定ASIN.csv", "否定ASIN.csv")):
            self.assertEqual(got[name], len(rd(src)) if name != "活动.csv" else got[name], name)
        self.assertEqual(got["搜索词报告.csv"], len(W["搜索词"])); self.assertEqual(got["广告位.csv"], len(W["广告位"]))
        self.assertEqual({r[2] for r in self.rows("广告位.csv")[1:]}, {"搜索顶部", "商品页面", "其余位置"})
        kw = self.rows("关键词竞价.csv"); self.assertNotIn("已归档的词", [r[1] for r in kw]); self.assertEqual(kw[0], ["广告活动", "关键词", "匹配类型", "竞价", "状态"])
        tg = {r[2] for r in self.rows("商品定位.csv")[1:]}; self.assertTrue({"close-match", "loose-match"} & tg)
        act = {r[0]: r for r in self.rows("活动.csv")[1:]}; self.assertEqual((act["自动-主"][2], act["自动-主"][4]), ("自动", "50")); self.assertEqual(act["词组主干"][1], "188.0")
        self.assertEqual(f.writes(), []); self.assertNotIn("接口编号.json", [x["名"] for x in d["文件"]]); self.assertTrue(os.path.exists(os.path.join(self.out, "接口编号.json")))

    def test_接口拉的和手工导的_整理出同一份搜索词输入(self):
        import pandas as pd
        pull(self.out, asins=["B0TEST0000", "B0TEST0001", "B0TEST0002"])
        for f in R.HAND_FILES: shutil.copy(os.path.join(SAMPLE, f), self.out)
        a, b = tempfile.mkdtemp(prefix="ads-rpt-a-"), tempfile.mkdtemp(prefix="ads-rpt-b-")
        for src, dst in ((self.out, a), (SAMPLE, b)):
            p = subprocess.run([sys.executable, os.path.join(REPO, "_脚本", "import_my_data.py"), src, dst], capture_output=True, text=True); self.assertEqual(p.returncode, 0, p.stdout[-600:] + p.stderr[-600:])
        x, y = (pd.read_pickle(f"{d}/_原始拉取/本父体-SP搜索词-按天.pkl") for d in (a, b))
        self.assertEqual(len(x), len(y))
        for c in ("广告花费", "广告销售额", "广告点击量", "广告订单量", "广告曝光量"): self.assertAlmostEqual(float(x[c].sum()), float(y[c].sum()), places=2, msg=c)
        self.assertEqual(sorted(x["匹配类型"].unique()), sorted(y["匹配类型"].unique()))
        pl = pd.read_pickle(f"{a}/_原始拉取/报表-adPlacementReport-0.pkl"); self.assertEqual(sorted(pl["广告位"].unique()), ["placementProductPage", "placementRestOfSearch", "placementTop"])
        self.assertAlmostEqual(float(pl["广告花费"].sum()), float(x["广告花费"].sum()), delta=len(pl) * 0.01); self.assertFalse(os.path.exists(f"{b}/_原始拉取/报表-adPlacementReport-0.pkl"))   # 手工那份没放广告位表
        for name in ("本父体-spKeyword.json", "本父体-spNeKeyword.json", "本父体-spGroup.json", "本父体-spTarget.json", "本父体-spNeTarget.json", "基础-spAdProduct-全店.json"):
            ja, jb = (R.jread(f"{d}/_原始拉取/{name}") for d in (a, b)); self.assertEqual(len(ja), len(jb), name)
        ka, kb = (sorted((k["keywordText"], k["matchType"], k["bid"], k["state"]) for k in R.jread(f"{d}/_原始拉取/本父体-spKeyword.json")) for d in (a, b)); self.assertEqual(ka, kb)
        ca, cb = ({c["name"]: (c["budget"], c["biddingStrategy"], c["targetingType"]) for c in R.jread(f"{d}/_原始拉取/本父体-spCampaign.json")} for d in (a, b))
        for n, v in cb.items(): self.assertEqual(ca[n], v, n)

    def test_人自己放的表_接口不覆盖(self):
        open(os.path.join(self.out, "活动.csv"), "w", encoding="utf-8").write("广告活动,日预算\n我手填的,1\n")
        d, _, _ = pull(self.out, like="主干")
        self.assertTrue(d["ok"]); self.assertEqual(next(x for x in d["文件"] if x["名"] == "活动.csv")["来源"], "人放的，没动")
        self.assertIn("我手填的", open(os.path.join(self.out, "活动.csv"), encoding="utf-8").read())
        d, _, _ = pull(self.out, like="主干"); self.assertEqual(next(x for x in d["文件"] if x["名"] == "广告组.csv")["来源"], "接口")     # 接口自己上次写的，可以更新

    def test_报表没生成完_先停_下次接着取不重建(self):
        f = Fake(slow=99); d, _, root = pull(self.out, f, like="主干", wait=120, every=60)
        self.assertFalse(d["ok"]); self.assertEqual(len(d["还在生成"]), 4); self.assertTrue(os.path.exists(os.path.join(self.out, ".接口任务.json"))); self.assertEqual(f.n("POST", "/reporting/reports"), 4)
        f2 = Fake(); d2, _, _ = pull(self.out, f2, like="主干")
        self.assertTrue(d2["ok"], d2["步骤"]); self.assertEqual(f2.n("POST", "/reporting/reports"), 0); self.assertEqual(f2.n("GET", "/reporting/reports/"), 4); self.assertFalse(os.path.exists(os.path.join(self.out, ".接口任务.json")))

    def test_平台说这份报表刚建过_就用已有的那一份(self):
        d, f, _ = pull(self.out, Fake(dup=True), like="主干"); self.assertTrue(d["ok"], d["步骤"])

    def test_报表生成失败_照实说_不凑数(self):
        d, _, _ = pull(self.out, Fake(fail="搜索词"), like="主干")
        self.assertFalse(d["ok"]); self.assertIn("生成失败", d["步骤"][-1]["说明"]); self.assertFalse(os.path.exists(os.path.join(self.out, "搜索词报告.csv")))

    def test_数据目录在仓库里面_一个请求都不发(self):
        f = Fake(); d, _, _ = pull(os.path.join(REPO, "我的数据-不该写到这"), f, like="主干")
        self.assertFalse(d["ok"]); self.assertIn("仓库", d["步骤"][-1]["说明"]); self.assertEqual(f.log, []); self.assertFalse(os.path.exists(os.path.join(REPO, "我的数据-不该写到这")))

    def test_运行记录只留个数_不留名字和编号(self):
        d, _, root = pull(self.out, asins=["B0TEST0000"]); t = json.dumps(R.jread(os.path.join(root, "运行记录", "ads-api-报表.json")), ensure_ascii=False)
        for bad in ("B0TEST", "11111111-1111", "词组主干", "9000", "7000"): self.assertNotIn(bad, t)

    def test_日期范围_最多31天_太早的不让拉(self):
        self.assertEqual(R.window(90, "2026-08-31", datetime.date(2026, 9, 1)), ("2026-08-01", "2026-08-31"))
        with self.assertRaises(A.AdsError): R.window(31, "2026-05-01", datetime.date(2026, 9, 1))

    def test_后来多要一份报表_只建缺的那份(self):
        import gzip
        pull(self.out); cf = os.path.join(self.out, ".接口报表.json.gz")
        with gzip.open(cf, "rt", encoding="utf-8") as fh: c = json.load(fh)
        del c["R"]["广告位"]
        with gzip.open(cf, "wt", encoding="utf-8") as fh: json.dump(c, fh, ensure_ascii=False)     # 模拟：昨天版本的脚本只缓存了三份
        d, f, _ = pull(self.out, like="主干"); self.assertTrue(d["ok"], d["步骤"]); self.assertEqual(f.n("POST", "/reporting/reports"), 1)


class 每周自动取数(unittest.TestCase):
    """每周一圈里那一步：默认关；开了也只在「自己的数据」上跑，缺配置就照实说、沿用现有数据。"""
    def setUp(self):
        import weekly as WK; self.WK = WK; self.root = tempfile.mkdtemp(prefix="ads-wk-")

    def test_默认不取_配置里要显式打开(self):
        self.assertFalse((self.WK.Weekly(self.root, dry=True).cfg.get("ads_api") or {}).get("每周自动取数"))

    def test_仓库自带的演示数据_不取(self):
        self.assertIn("演示数据", self.WK.Weekly(REPO, dry=True).s_pull())

    def test_没配数据目录或没圈产品_照实说_沿用现有数据(self):
        with mock.patch.object(A, "local_env", return_value={}), mock.patch.object(A, "settings", return_value=dict(CFG)):
            ok, note = self.WK.Weekly(self.root, dry=True).s_pull()
        self.assertFalse(ok); self.assertIn("沿用现有数据", note)
        with mock.patch.object(A, "local_env", return_value={"ADS_DATA_DIR": tempfile.mkdtemp()}), mock.patch.object(A, "settings", return_value=dict(CFG)):
            ok, note = self.WK.Weekly(self.root, dry=True).s_pull()
        self.assertFalse(ok); self.assertIn("ADS_SCOPE_ASINS", note)

    def test_演练只说会做什么_不调接口(self):
        with mock.patch.object(A, "local_env", return_value={"ADS_DATA_DIR": tempfile.mkdtemp(), "ADS_SCOPE_ASINS": "B0TEST0000"}), mock.patch.object(A, "settings", return_value=dict(CFG)), mock.patch.object(R, "pull", side_effect=AssertionError("演练不该真拉")):
            self.assertIn("演练", self.WK.Weekly(self.root, dry=True).s_pull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
