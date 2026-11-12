# -*- coding: utf-8 -*-
"""Amazon Ads API 适配器 _脚本/ads_api.py 的测试。全部用假通道，不联网、不花积分、不碰任何真实店铺。
用法：python3 -m unittest tests.test_ads_api -v"""
import json, os, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_biz import REPO
sys.path.insert(0, os.path.join(REPO, "_脚本")); import ads_api as A  # noqa: E402

CFG = {"store": "测试店", "store_id": "", "country": "US", "enabled": True, "通道": "假"}


class Fake:
    """假通道：按命令回固定的东西，并记下每次调用。ads 的状态可以被 update 改掉，用来测回读。"""
    def __init__(self, ad_state="ENABLED", apply=True, stores=1, auths=1):
        self.log, self.ad_state, self.apply, self.stores, self.auths = [], ad_state, apply, stores, auths

    def __call__(self, args):
        self.log.append(args)
        if args[:2] == ["account", "stores"]: return [{"store_id": 100 + i, "store_name": "测试店"} for i in range(self.stores)]
        if args[:2] == ["account", "platform-auths"]: return [{"seller_account_id": 100 + i, "region": "NA", "auth_status": 1} for i in range(self.auths)]
        path = args[2]; body = json.loads(args[args.index("--body") + 1]) if "--body" in args else None
        if path.endswith("/v2/profiles"): return [{"profileId": 9, "countryCode": "US", "currencyCode": "USD", "timezone": "America/Los_Angeles", "accountInfo": {"type": "seller"}}, {"profileId": 8, "countryCode": "CA", "accountInfo": {"type": "seller"}}]
        if path.endswith("query/campaigns"):
            if body.get("nextToken") == "p2": return {"campaigns": [{"campaignId": "c3", "state": "PAUSED"}]}
            return {"campaigns": [{"campaignId": "c1", "state": "ENABLED"}, {"campaignId": "c2", "state": "PAUSED"}], "nextToken": "p2"}
        if path.endswith("query/adGroups"): return {"adGroups": [{"adGroupId": "g1", "state": "ENABLED"}]}
        if path.endswith("query/targets"): return {"targets": [{"targetId": "t1", "state": "ENABLED", "negative": False, "targetType": "KEYWORD"}, {"targetId": "t2", "state": "ENABLED", "negative": True, "targetType": "PRODUCT"}]}
        if path.endswith("query/ads"): return {"ads": [{"adId": "a1", "state": self.ad_state}]}
        if path.endswith("update/ads"):
            if self.apply: self.ad_state = body["ads"][0]["state"]
            return {"success": [{"index": 0}], "error": []}
        raise AssertionError("没想到的调用 " + path)

    def writes(self): return [a for a in self.log if a[0] == "http" and ("/update/" in a[2] or "/create/" in a[2] or "/delete/" in a[2])]


class 身份与读取(unittest.TestCase):
    def test_逐层核对身份_请求带上店铺和广告账号(self):
        f = Fake(); ch = A.Channel(CFG, f).identify()
        self.assertEqual((ch.region, ch.profile["profileId"]), ("na", 9))
        rows, full = ch.query("campaigns"); self.assertEqual((len(rows), full), (3, True))
        h = json.loads(f.log[-1][f.log[-1].index("--headers") + 1]); self.assertEqual((h["X-Account-Id"], h["Amazon-Advertising-API-Scope"]), ("100", "9"))
        self.assertIn("/proxy/na/adsApi/v1/query/campaigns", f.log[-1][2]); self.assertEqual(f.writes(), [])

    def test_同名店铺有两个都授权了_停下来要人指定(self):
        with self.assertRaises(A.AdsError): A.Channel(CFG, Fake(stores=2, auths=2)).identify()
        self.assertEqual(A.Channel({**CFG, "store_id": "101"}, Fake(stores=2, auths=2)).identify().account, 101)

    def test_没授权广告接口_不发任何请求(self):
        f = Fake(auths=0)
        with self.assertRaises(A.AdsError): A.Channel(CFG, f).identify()
        self.assertFalse(any(a[0] == "http" for a in f.log))

    def test_业务错误当失败(self):
        with self.assertRaises(A.AdsError): A.unwrap({"ret": 30020, "msg": "路径不对"})

    def test_连通检查_只留个数_不留编号(self):
        with mock.patch.object(A, "settings", return_value=dict(CFG)):
            d = A.check("/tmp", Fake(), save=False)
        self.assertTrue(d["ok"]); txt = json.dumps(d, ensure_ascii=False)
        self.assertIn("读到 3 个 SP 活动", txt); self.assertNotIn("c1", txt); self.assertNotIn('"100"', txt)


class 动作翻成请求(unittest.TestCase):
    F = {"Campaign ID": "C", "广告组 ID": "G", "关键词 ID": "K", "关键词": "kw", "SKU": "S", "ASIN": "B0X", "广告 ID": "AD"}

    def one(self, t, new="1.05", f=None): return A.build({"type": t, "old": "1.2", "new": new, "object": "obj"}, self.F if f is None else f)

    def test_每一类动作都有路由_都翻得出来(self):
        for t in A.ROUTES:
            pl = "广告位加价" in t; f = {**self.F, "广告位": "搜索顶部", "广告位现值": {"TOP_OF_SEARCH": 50, "PRODUCT_PAGE": 20}} if pl else None
            route, body, miss = self.one(t, new=("动态竞价-只降低" if t == "改竞价策略" else "28%" if pl else "1.05"), f=f); self.assertEqual(route, A.ROUTES[t][0], t); self.assertEqual(miss, [], t)
            self.assertEqual(len(next(iter(body.values()))), 1, t)

    def test_改广告位加价_只改一个位置_其余位置原样带上(self):
        f = {**self.F, "广告位": "搜索顶部", "广告位现值": {"TOP_OF_SEARCH": 50, "PRODUCT_PAGE": 20}}
        _, body, miss = A.build({"type": "下调广告位加价", "old": "50%", "new": "28%", "object": "搜索顶部"}, f); self.assertEqual(miss, [])
        self.assertEqual(body["campaigns"][0]["optimizations"]["bidSettings"]["bidAdjustments"]["placementBidAdjustments"], [{"placement": "PRODUCT_PAGE", "percentage": 20}, {"placement": "TOP_OF_SEARCH", "percentage": 28}])
        _, _, miss = A.build({"type": "下调广告位加价", "old": "50%", "new": "28%", "object": "搜索顶部"}, {**self.F, "广告位": "搜索顶部", "广告位现值": None})
        self.assertIn("这个活动现在各位置的加价", miss)                       # 不知道其余位置现在加了多少，就不发
        self.assertNotIn("下调广告位加价", A.PROVEN)

    def test_几类典型动作的请求长什么样(self):
        self.assertEqual(self.one("暂停广告产品")[1], {"ads": [{"adId": "AD", "state": "PAUSED"}]})
        self.assertEqual(self.one("关键词降竞价")[1], {"targets": [{"targetId": "K", "bid": {"bid": 1.05}}]})
        self.assertEqual(self.one("暂停关键词")[1], {"targets": [{"targetId": "K", "state": "PAUSED"}]})
        b = self.one("下调预算", "15")[1]["campaigns"][0]; self.assertEqual(b["budgets"][0]["budgetValue"]["monetaryBudgetValue"]["monetaryBudget"], {"currencyCode": "USD", "value": 15.0})
        self.assertEqual(self.one("改竞价策略", "动态竞价-只降低")[1]["campaigns"][0]["optimizations"]["bidSettings"]["bidStrategy"], "SALES_DOWN_ONLY")
        n = self.one("否定 ASIN")[1]["targets"][0]; self.assertTrue(n["negative"]); self.assertEqual(n["targetDetails"]["productTarget"]["product"]["productId"], "B0X")
        k = self.one("换道否定")[1]["targets"][0]; self.assertEqual((k["negative"], k["targetDetails"]["keywordTarget"]["matchType"]), (True, "EXACT"))

    def test_缺编号_说得出缺什么(self):
        self.assertEqual(self.one("暂停广告产品", f={})[2], ["广告 ID"]); self.assertIn("Campaign ID", self.one("下调预算", "15", f={})[2])

    def test_只用暂停_不用归档和删除(self):
        self.assertFalse(any("delete" in v[0] for v in A.ROUTES.values()))
        for t in A.ROUTES: self.assertNotIn("ARCHIVED", json.dumps(self.one(t, new=("固定竞价" if t == "改竞价策略" else "1"))[1]))


class 执行的闸(unittest.TestCase):
    ITEM = {"动作编号": "X-1", "类型": "暂停广告产品", "路由": "POST /adsApi/v1/update/ads", "请求体": {"ads": [{"adId": "a1", "state": "PAUSED"}]}, "跑通过": True, "能发": True, "为什么不能发": ""}

    def run_one(self, fake, item=None, enabled=True, text="确认暂停"):
        with mock.patch.object(A, "settings", return_value={**CFG, "enabled": enabled}), mock.patch.object(A, "preview", return_value={"请求": [item or self.ITEM]}), mock.patch.object(A.os, "makedirs"), mock.patch("builtins.open", mock.mock_open()):
            return A.execute("/tmp/x", "X-1", text, fake)

    def test_开关没开_不发(self):
        f = Fake()
        with self.assertRaises(A.AdsError): self.run_one(f, enabled=False)
        self.assertEqual(f.log, [])

    def test_没写确认的话_不发(self):
        f = Fake()
        with self.assertRaises(A.AdsError): self.run_one(f, text="  ")
        self.assertEqual(f.log, [])

    def test_演示数据或缺编号_不发(self):
        f = Fake()
        with self.assertRaises(A.AdsError): self.run_one(f, item={**self.ITEM, "能发": False, "为什么不能发": "演示数据"})
        self.assertEqual(f.writes(), [])

    def test_正常_先读现值_只提交一次_回读对上才算(self):
        f = Fake(); r = self.run_one(f)
        self.assertEqual(r["结果"], "已执行并回读"); self.assertEqual(r["发之前"], "ENABLED"); self.assertEqual(len(f.writes()), 1)
        order = [a[2].split("/v1/")[-1] for a in f.log if a[0] == "http" and "/v1/" in a[2]]; self.assertEqual(order, ["query/ads", "update/ads", "query/ads"])

    def test_后台已经是暂停了_不发(self):
        f = Fake(ad_state="PAUSED"); r = self.run_one(f)
        self.assertEqual(r["结果"], "没发"); self.assertEqual(f.writes(), [])

    def test_提交了但回读对不上_标待核实_不重发(self):
        f = Fake(apply=False); r = self.run_one(f)
        self.assertEqual(r["结果"], "待核实"); self.assertEqual(len(f.writes()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
