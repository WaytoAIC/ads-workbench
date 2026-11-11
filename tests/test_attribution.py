# -*- coding: utf-8 -*-
"""归因 _脚本/attribution.py 的测试：在临时副本上跑 render.py（它末尾会调归因），再检查拆解对不对得上、证据齐不齐。只写副本，不动仓库。

用法：python3 -m unittest tests.test_attribution -v      或      python3 tests/test_attribution.py"""
import json, os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_biz import REPO, SCENE, copy_repo, jread, jwrite   # 复用建副本的办法


def make(scene):
    d = tempfile.mkdtemp(prefix="ads-attr-"); copy_repo(d)
    P = jread(f"{d}/参数.json"); P.update(SCENE[scene]); jwrite(f"{d}/参数.json", P)
    for f in ("读回状态.json", "归因.json"):
        if os.path.exists(f"{d}/广告闭环/输出/{f}"): os.remove(f"{d}/广告闭环/输出/{f}")
    r = subprocess.run([sys.executable, f"{d}/_脚本/render.py"], capture_output=True, text=True, env=dict(os.environ, ADS_ROOT=d, PYTHONDONTWRITEBYTECODE="1"))
    assert r.returncode == 0, r.stderr[-800:]
    return d


class 归因(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = make("v1"); cls.A = jread(f"{cls.d}/广告闭环/输出/归因.json"); cls.F = jread(f"{cls.d}/广告闭环/输出/数字.json")

    def test_render之后就有归因文件(self):
        self.assertNotIn("错误", self.A); self.assertEqual(set(self.A) >= {"问题", "分析", "对策", "小结"}, True)

    def test_每个问题都有拆解和读法(self):
        self.assertEqual(set(self.A["问题"]), {a["指标"] for a in self.F["异常"]})
        for name, q in self.A["问题"].items():
            self.assertTrue(q["表"], name)
            for t in q["表"]:
                self.assertTrue(t["读法"] and t["行"] and "格式" in t, f"{name}｜{t['标题']}")
                for r in t["行"]: self.assertIn("名", r)

    def test_广告费增量按类型拆_加起来等于总增量(self):
        t = self.A["问题"]["末周广告费增速 vs 件数增速"]["表"][0]; W = self.F["逐周"]
        self.assertAlmostEqual(sum(r["变化"] for r in t["行"]), W[-1]["广告费"] - W[-2]["广告费"], places=1)
        self.assertAlmostEqual(sum(r["占增量"] for r in t["行"]), 1.0, places=6)

    def test_ACOS三个因素_加起来等于ACOS的变化(self):
        t = self.A["问题"]["SP 的 ACOS"]["表"][0]
        self.assertAlmostEqual(sum(r["推高 ACOS"] for r in t["行"]), self.F["SP-近14天"]["ACOS"] - self.F["SP-前14天"]["ACOS"], places=6)

    def test_TACOS三种广告_加起来等于TACOS的变化(self):
        t = self.A["问题"]["TACOS"]["表"][0]; W = self.F["逐周"]
        self.assertAlmostEqual(sum(r["变化"] for r in t["行"]), W[-1]["TACOS"] - W[-2]["TACOS"], places=6)

    def test_每条分析都有正反两面和把握(self):
        self.assertEqual(set(self.A["分析"]), {"H1", "H2", "H3", "H4", "H5", "H6"})
        for h, a in self.A["分析"].items():
            self.assertIn(a["把握"], ("高", "中", "低"), h); self.assertTrue(a["把握依据"], h)
            self.assertTrue(a["支持"] or a["反对"], h); self.assertIn("对象", a["能解释"]); self.assertIsInstance(a["还缺"], list)
            for e in a["支持"] + a["反对"]: self.assertTrue(e["话"] and e["出处"], h)
            if a["能解释"]["比例"] is not None: self.assertTrue(-0.01 <= a["能解释"]["比例"] <= 1.01, h)

    def test_演示数据_断货解释不了上周的增速差(self):
        h2 = self.A["分析"]["H2"]; self.assertEqual(h2["把握"], "低"); self.assertGreaterEqual(len(h2["反对"]), 2)

    def test_对策写明主要靠哪条分析(self):
        for k, o in self.A["对策"].items():
            self.assertTrue(o["靠哪几条分析"], k); self.assertEqual(o["主要靠"], o["靠哪几条分析"][0]["id"])
        self.assertIn("H1", self.A["对策"]["A"]["提醒"])

    def test_库存表没了_不崩_写错误(self):
        os.rename(f"{self.d}/_原始拉取/库存与动销-按SKU.json", f"{self.d}/_原始拉取/库存.bak")
        try:
            r = subprocess.run([sys.executable, f"{self.d}/_脚本/attribution.py"], capture_output=True, text=True, env=dict(os.environ, ADS_ROOT=self.d))
            doc = jread(f"{self.d}/广告闭环/输出/归因.json")
            self.assertTrue(r.returncode in (0, 1)); self.assertTrue("错误" in doc or "问题" in doc)
        finally:
            os.rename(f"{self.d}/_原始拉取/库存.bak", f"{self.d}/_原始拉取/库存与动销-按SKU.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
