# -*- coding: utf-8 -*-
"""广告位加价规则的测试：在仓库副本里放一张造出来的广告位报表，跑流水线，看出的动作对不对。只写副本，不动仓库。
仓库自带的演示数据里没有广告位报表（不编数据），所以演示仍然只提醒「广告位待补数据」——那一头由 test_pipeline_regress 守着。
用法：python3 -m unittest tests.test_placement -v"""
import os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_biz import REPO, SCENE, copy_repo, jread, jwrite

# (活动, 广告位, 点击, 订单, 花费, 销售额)：近 14 天合计
CASES = [("自动-主", "placementTop", 40, 0, 60.0, 0.0),                 # 现在加价 50%，40 次点击 0 单 → 下调
         ("词组拓词", "placementRestOfSearch", 30, 2, 90.0, 100.0),       # 现在加价 30%，ACOS 90% 超盈亏线 → 下调
         ("词组主干", "placementProductPage", 25, 1, 50.0, 60.0),         # 现在加价 2%，ACOS 83% → 降到 0
         ("词组主干", "placementTop", 30, 6, 30.0, 300.0),                # 现在没加价，ACOS 10%、6 单 → 上调到 10%
         ("自动-主", "placementProductPage", 12, 0, 20.0, 0.0),           # 点击不够数 → 不动
         ("词组拓词", "placementTop", 50, 0, 80.0, 0.0)]                  # 0 单但现在没加价：降不了，不归这条管 → 不动


def run(with_report=True, patch=None):
    import pandas as pd
    d = tempfile.mkdtemp(prefix="ads-pl-"); copy_repo(d); P = jread(f"{d}/参数.json"); P.update(SCENE["v1"]); jwrite(f"{d}/参数.json", P)
    for f in ("读回状态.json",):
        if os.path.exists(f"{d}/广告闭环/输出/{f}"): os.remove(f"{d}/广告闭环/输出/{f}")
    if with_report:
        day = P["窗口近"][1]; cid = {c["name"]: c["campaignId"] for c in jread(f"{d}/_原始拉取/本父体-活动.json")}
        pd.DataFrame([{"日期": pd.Timestamp(day), "广告活动": c, "广告活动ID": cid[c], "广告位": k, "广告花费": sp, "广告曝光量": ck * 50, "广告点击量": ck, "广告订单量": od, "广告销售额": sl} for c, k, ck, od, sp, sl in CASES]
                     ).to_pickle(f"{d}/_原始拉取/报表-adPlacementReport-0.pkl")
    if patch: patch(d)
    r = subprocess.run([sys.executable, f"{d}/_脚本/pipeline.py"], capture_output=True, text=True, env=dict(os.environ, ADS_ROOT=d, PYTHONDONTWRITEBYTECODE="1"))
    return d, r


class 广告位加价(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d, r = run(); assert r.returncode == 0, r.stderr[-800:]
        cls.rows = jread(f"{cls.d}/广告闭环/输出/动作清单.json"); cls.pl = {(x["广告活动"], x["对象"]): x for x in cls.rows if "广告位加价" in x["类型"]}; cls.checks = jread(f"{cls.d}/广告闭环/输出/验证器.json")
        cls.d0, r0 = run(False); assert r0.returncode == 0, r0.stderr[-800:]; cls.rows0 = jread(f"{cls.d0}/广告闭环/输出/动作清单.json")

    def test_没有报表_只提醒待补数据_验证器还是九条(self):
        self.assertEqual(sum(1 for x in self.rows0 if x["类型"] == "广告位待补数据"), 1); self.assertFalse([x for x in self.rows0 if "广告位加价" in x["类型"]])
        self.assertEqual(len(jread(f"{self.d0}/广告闭环/输出/验证器.json")), 9)

    def test_有报表_不再提醒待补_出四条调整(self):
        self.assertFalse([x for x in self.rows if x["类型"] == "广告位待补数据"])
        self.assertEqual(set(self.pl), {("自动-主", "搜索顶部"), ("词组拓词", "其余位置"), ("词组主干", "商品页面"), ("词组主干", "搜索顶部")})
        self.assertEqual(len(self.rows), len(self.rows0) - 1 + 4)                       # 别的动作一条不多一条不少

    def test_下调_折到出价上最多降百分之十五_降到零为止(self):
        a = self.pl[("自动-主", "搜索顶部")]; self.assertEqual((a["类型"], a["现值"], a["新值"]), ("下调广告位加价", "50%", "28%"))        # 1.5 × 0.85 = 1.275 → 往安全的一侧取整 28%
        b = self.pl[("词组拓词", "其余位置")]; self.assertEqual((b["现值"], b["新值"]), ("30%", "11%"))                                  # 1.3 × 0.85 = 1.105 → 11%
        c = self.pl[("词组主干", "商品页面")]; self.assertEqual((c["现值"], c["新值"]), ("2%", "0%"))
        for x in (a, b, c): self.assertEqual(x["取舍项"], "B"); self.assertIn("近 14 天这个位置", x["依据"])
        self.assertIn("一单没出", a["依据"]); self.assertIn("超盈亏线", b["依据"])

    def test_上调_从没加价提到百分之十(self):
        u = self.pl[("词组主干", "搜索顶部")]; self.assertEqual((u["类型"], u["现值"], u["新值"]), ("上调广告位加价", "0%", "10%"))

    def test_验证器多一条_并且通过(self):
        self.assertEqual(len(self.checks), 10); self.assertTrue(all(c["通过"] for c in self.checks)); self.assertIn("广告位加价单次调整", self.checks[-1]["检查"])

    def test_上调有上限(self):
        def patch(d):
            cs = jread(f"{d}/_原始拉取/本父体-spCampaign.json")
            for c in cs:
                if c["name"] == "词组主干": c["placementAdjustments"] = [{"placement": "placementTop", "percentage": 95}]
            jwrite(f"{d}/_原始拉取/本父体-spCampaign.json", cs)
        d, r = run(patch=patch); self.assertEqual(r.returncode, 0, r.stderr[-600:])
        u = next(x for x in jread(f"{d}/广告闭环/输出/动作清单.json") if x["类型"] == "上调广告位加价"); self.assertEqual((u["现值"], u["新值"]), ("95%", "100%"))

    def test_批量上传表_广告位那两列填上了(self):
        sys.path.insert(0, os.path.join(REPO, "_脚本")); import fields as FD
        a = self.pl[("自动-主", "搜索顶部")]; act = {"type": a["类型"], "campaign": a["广告活动"], "object": a["对象"], "old": a["现值"], "new": a["新值"], "no": "X-1", "why": a["依据"]}
        f = FD.Mapper(self.d, jread(f"{self.d}/参数.json")).enrich(act); row = dict(zip(FD.BULK_COLS, FD.bulk_row(act, f)))
        self.assertEqual((row["Entity"], row["Operation"], row["Placement"], row["Percentage"]), ("Bidding Adjustment", "update", "Placement Top", "28"))
        self.assertTrue(row["Campaign ID"]); self.assertEqual((row["Ad Group ID"], row["Bid"], row["State"]), ("", "", ""))
        self.assertEqual(f["通道"], "Amazon Ads API")

    def test_接口预演_带上这个活动其余位置的加价(self):
        import sqlite3
        sys.path.insert(0, os.path.join(REPO, "_脚本")); import ads_api as A
        a = self.pl[("自动-主", "搜索顶部")]; f = {"Campaign ID": "C1", "广告位": a["对象"], "广告位现值": {"TOP_OF_SEARCH": 50}}
        route, body, miss = A.build({"type": a["类型"], "old": a["现值"], "new": a["新值"], "object": a["对象"]}, f)
        self.assertEqual((route, miss), ("update/campaigns", [])); self.assertEqual(body["campaigns"][0]["optimizations"]["bidSettings"]["bidAdjustments"]["placementBidAdjustments"], [{"placement": "TOP_OF_SEARCH", "percentage": 28}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
