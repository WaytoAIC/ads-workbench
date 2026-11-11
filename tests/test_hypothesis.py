# -*- coding: utf-8 -*-
"""Agent 提的新分析：解析和核对（工作台/hub.py）。人采纳之前，后端先看格式对不对、来自的问题存不存在、带 $ 和 % 的数在脚本产物里找不找得到。
在临时副本上跑一圈拿到产物再测，只写副本。      用法：python3 -m unittest tests.test_hypothesis -v"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_attribution import make
from test_biz import REPO
sys.path.insert(0, os.path.join(REPO, "工作台")); import hub  # noqa: E402

GOOD = """问题：多花的广告费是不是 SBV 加投造成的？
来自：末周广告费增速 vs 件数增速；TACOS
指向：E
结论：上周多花的 $892 里 SBV 占 76%
把握：中（没有 SBV 明细）
把握依据：按广告类型的周花费是确定数
支持：
- SBV 周花费从 $1,274 到 $1,956，多了 $682（数字.json 逐周）
- SBV 的点击单价涨了 $0.47（自己从明细算的）
反对：
- SBV 的归因口径宽，它也可能带来了增量订单（没有数据）
还缺：
- SBV 活动报告｜广告后台｜能看出是哪个活动加投的
不成立：SBV 的加投是有意放量"""


class 新分析(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.d = make("v1")

    def test_解析_键值和三段清单(self):
        d = hub.parse_hypothesis(GOOD)
        self.assertEqual(d["来自"], ["末周广告费增速 vs 件数增速", "TACOS"]); self.assertEqual((d["指向"], d["把握"]), ("E", "中"))
        self.assertEqual(len(d["支持"]), 2); self.assertEqual(d["支持"][0]["出处"], "数字.json 逐周"); self.assertNotIn("（", d["支持"][0]["话"][-3:])
        self.assertEqual(d["还缺"][0], {"缺什么": "SBV 活动报告", "去哪取": "广告后台", "拿到后": "能看出是哪个活动加投的"})

    def test_合规的能过_编出来的数被标出来但不拦(self):
        d, errs, flags = hub.check_hypothesis(self.d, hub.parse_hypothesis(GOOD))
        self.assertEqual(errs, []); self.assertIsNone(d["支持"][0].get("核对")); self.assertIn("$0.47", d["支持"][1]["核对"]); self.assertTrue(any("1 条证据" in f for f in flags))

    def test_来自写的不是现有问题_不能采纳(self):
        _, errs, _ = hub.check_hypothesis(self.d, hub.parse_hypothesis(GOOD.replace("末周广告费增速 vs 件数增速；TACOS", "转化率下滑")))
        self.assertTrue(any("对不上现有的问题" in e for e in errs))

    def test_来自写了简称_能对上唯一一个就认(self):
        d, errs, _ = hub.check_hypothesis(self.d, hub.parse_hypothesis(GOOD.replace("末周广告费增速 vs 件数增速；TACOS", "退款")))
        self.assertEqual(errs, []); self.assertEqual(d["来自"], ["退款率"])

    def test_缺问题缺把握缺证据_都说得出缺什么(self):
        _, errs, _ = hub.check_hypothesis(self.d, hub.parse_hypothesis("问题：短\n来自：TACOS\n结论：x"))
        self.assertEqual(len(errs), 3)

    def test_和树上已有的一样_不能重复采纳(self):
        _, errs, _ = hub.check_hypothesis(self.d, hub.parse_hypothesis(GOOD), existing=["多花的广告费是不是 SBV 加投造成的？"])
        self.assertTrue(any("已经有" in e for e in errs))

    def test_指向不存在的对策_当成没写并提醒(self):
        d, errs, flags = hub.check_hypothesis(self.d, hub.parse_hypothesis(GOOD.replace("指向：E", "指向：Z")))
        self.assertEqual((errs, d["指向"]), ([], "")); self.assertTrue(any("不在这一圈的对策里" in f for f in flags))


if __name__ == "__main__":
    unittest.main(verbosity=2)
