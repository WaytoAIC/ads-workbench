# -*- coding: utf-8 -*-
"""经营核算 _脚本/biz.py 的测试：在临时目录里 rsync 两份仓库副本（v1＝到仓 4 周；r1＝到仓周数改成 1），先跑 render.py（它末尾会调 biz），
再按需改副本里的 参数.json / 数字.json 单跑 biz.py。只写副本，不动仓库。结构与枚举以 docs/架构.md 第二节为准。

用法：python3 -m unittest tests.test_biz -v      或      python3 tests/test_biz.py"""
import json, os, shutil, subprocess, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = {"v1": {"版本": 1, "补货到仓周数": 4, "目标ACOS": 0.30, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"]},
         "r1": {"版本": 2, "补货到仓周数": 1, "目标ACOS": 0.30, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"]}}
SKIP_COPY = [".git", "工作台.db*", "__pycache__", ".上一份有效结果", "运行记录", "截图", "流程图", "*.html"]
TASKS = {"纯利型", "推自然位", "测词拓词", "收割", "防守", "未判定"}
DONE = {"达标", "未达标", "看不出"}
MARKS = {"纯利型候选", "任务没完成", "预算吃紧"}
LIMITS = {"库存", "CPC", "CVR", "广告销售额占比", "无效广告", "利润空间", "无明显限制"}
ENTRIES = {"利润率差", "单量低于预期", "销量超预期"}
ADVICE = {"增单", "降耗", "调价", "重构", "先解决库存"}
NINE = ["当前状态", "首要目标", "核心限制", "选择方向", "执行方案", "投入边界", "验证标准", "复盘时间", "后续选择"]
NODES = ["TACOS", "ACOS（全部广告）", "广告销售额占比", "CPC", "CVR", "客单价"]


def jread(f):
    with open(f, encoding="utf-8") as h: return json.load(h)


def jwrite(f, o):
    with open(f, "w", encoding="utf-8") as h: json.dump(o, h, ensure_ascii=False, indent=1)


def tread(f):
    with open(f, encoding="utf-8") as h: return h.read()


def twrite(f, text):
    with open(f, "wb" if isinstance(text, bytes) else "w", **({} if isinstance(text, bytes) else {"encoding": "utf-8"})) as h: h.write(text)


def copy_repo(dst):
    if shutil.which("rsync"):
        subprocess.run(["rsync", "-a"] + [x for p in SKIP_COPY for x in ("--exclude", p)] + [REPO + "/", dst + "/"], check=True)
    else:
        shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns(*SKIP_COPY), dirs_exist_ok=True)


def script(d, name):
    return subprocess.run([sys.executable, f"{d}/_脚本/{name}"], capture_output=True, text=True, env=dict(os.environ, ADS_ROOT=d))


class Biz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ads-biz-"); cls.dir, cls.keep = {}, {}
        for scene, upd in SCENE.items():
            d = os.path.join(cls.tmp, scene); copy_repo(d)
            P = jread(f"{d}/参数.json"); P.update(upd); P.pop("定价毛利率", None); P.pop("目标广告后利润率", None); jwrite(f"{d}/参数.json", P)
            back = f"{d}/广告闭环/输出/读回状态.json"
            if os.path.exists(back): os.remove(back)
            r = script(d, "render.py"); assert r.returncode == 0, f"{scene} 的 render.py 失败：{r.stderr[-800:]}"
            cls.dir[scene] = d; cls.keep[scene] = {f: tread(f"{d}/{f}") for f in ("参数.json", "广告闭环/输出/数字.json", "广告闭环/输出/经营.json")}

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.tmp, ignore_errors=True)

    def tearDown(self):                                      # 每条测试改过的输入都还原，测试之间互不影响
        for scene, files in self.keep.items():
            for f, text in files.items(): twrite(f"{self.dir[scene]}/{f}", text)

    def biz(self, scene="v1"): return jread(f"{self.dir[scene]}/广告闭环/输出/经营.json")
    def F(self, scene="v1"): return jread(f"{self.dir[scene]}/广告闭环/输出/数字.json")

    def rerun(self, scene="v1", params=None, facts=None, code=0):
        """改副本里的 参数.json（params：dict 合并，值为 None 表示删键）或 数字.json（facts：函数），单跑 biz.py，返回新的 经营.json。"""
        d = self.dir[scene]
        if params is not None:
            P = jread(f"{d}/参数.json")
            for k, v in params.items(): P.pop(k, None) if v is None else P.__setitem__(k, v)
            jwrite(f"{d}/参数.json", P)
        if facts is not None: F = jread(f"{d}/广告闭环/输出/数字.json"); facts(F); jwrite(f"{d}/广告闭环/输出/数字.json", F)
        r = script(d, "biz.py"); self.assertEqual(r.returncode, code, r.stderr[-800:]); return self.biz(scene)

    # ---- 结构 ----
    def test_render之后就有经营文件(self):
        for scene in SCENE:
            B = self.biz(scene); self.assertNotIn("错误", B); self.assertEqual(B["写入方"], "脚本")
            for k in ("生成于", "算账", "拆解", "任务", "路径", "决策表"): self.assertIn(k, B)

    def test_比率是小数不是百分号字符串(self):
        A = self.biz()["算账"]
        for k in ("定价毛利率", "目标广告后利润率", "目标TACOS", "当前TACOS", "TACOS余量", "当前广告后利润率"):
            self.assertIsInstance(A[k], float, k); self.assertLess(abs(A[k]), 1, k)
        for k in ("近7天日均销售额", "单品日预算", "现日预算合计", "上周日均广告费"): self.assertIsInstance(A[k], (int, float), k)
        for n in self.biz()["拆解"]["节点"]: self.assertNotIsInstance(n["值"], str, n["名"])

    # ---- 算账 ----
    def test_目标TACOS等于定价毛利率减目标利润率(self):
        for scene in SCENE:
            A = self.biz(scene)["算账"]
            self.assertAlmostEqual(A["目标TACOS"], A["定价毛利率"] - A["目标广告后利润率"], places=4)
            self.assertAlmostEqual(A["TACOS余量"], A["目标TACOS"] - A["当前TACOS"], places=4)
            self.assertAlmostEqual(A["当前广告后利润率"], A["定价毛利率"] - A["当前TACOS"], places=4)

    def test_算账的数能在数字文件里复算(self):
        A, F = self.biz()["算账"], self.F(); W, Y = F["逐周"], F["四周"]
        self.assertAlmostEqual(A["定价毛利率"], Y["盈亏线"], places=4); self.assertAlmostEqual(A["当前TACOS"], Y["TACOS"], places=4)
        self.assertAlmostEqual(A["近7天日均销售额"], W[-1]["销售额"] / 7, places=2); self.assertAlmostEqual(A["上周日均广告费"], W[-1]["广告费"] / 7, places=2)
        self.assertAlmostEqual(A["单品日预算"], A["近7天日均销售额"] * A["目标TACOS"], places=1)
        self.assertAlmostEqual(A["现日预算合计"], F["活动"]["名义日预算合计"], places=2)
        self.assertEqual(A["判定"], "在目标内"); self.assertEqual(A["阶段"], "新品期"); self.assertTrue(A["阶段要求"])

    def test_定价毛利率_人填和数据两种来源(self):
        A = self.rerun(params={"定价毛利率": 0.5, "目标广告后利润率": 0.1})["算账"]
        self.assertEqual(A["定价毛利率来源"], "人填"); self.assertEqual(A["定价毛利率"], 0.5); self.assertAlmostEqual(A["目标TACOS"], 0.4, places=4)
        self.assertEqual(A["目标广告后利润率来源"], "人填")
        A = self.rerun(params={"定价毛利率": None, "目标广告后利润率": None})["算账"]
        self.assertTrue(A["定价毛利率来源"].startswith("数据"), A["定价毛利率来源"]); self.assertAlmostEqual(A["定价毛利率"], self.F()["四周"]["盈亏线"], places=4)
        self.assertEqual(A["目标广告后利润率来源"], "口径默认")
        self.assertAlmostEqual(A["目标广告后利润率"], jread(f"{REPO}/口径.json")["经营"]["默认目标广告后利润率"], places=4)

    def test_判定三档(self):
        tacos = self.F()["四周"]["TACOS"]
        self.assertEqual(self.rerun(params={"定价毛利率": tacos + 0.20, "目标广告后利润率": 0.10})["算账"]["判定"], "在目标内")
        self.assertEqual(self.rerun(params={"定价毛利率": tacos + 0.05, "目标广告后利润率": 0.10})["算账"]["判定"], "超出目标")
        B = self.rerun("r1", params={"定价毛利率": tacos - 0.05, "目标广告后利润率": 0.10})
        self.assertEqual(B["算账"]["判定"], "已亏损"); self.assertEqual(B["拆解"]["核心限制"]["变量"], "利润空间"); self.assertEqual(B["路径"]["脚本建议"], "重构")

    def test_阶段不在四个里_写缺(self):
        A = self.rerun(params={"产品阶段": "清仓期"})["算账"]
        self.assertIsNone(A["阶段要求"]); self.assertIn("阶段要求", A["缺"])

    # ---- 拆解 ----
    def test_TACOS约等于ACOS乘广告销售额占比(self):
        for scene in SCENE:
            N = {n["名"]: n for n in self.biz(scene)["拆解"]["节点"]}; self.assertEqual(list(N), NODES)
            acos, share = N["ACOS（全部广告）"], N["广告销售额占比"]
            if share["值"] is None or acos["值"] is None: self.assertTrue(share.get("缺") or acos.get("缺"))
            else: self.assertAlmostEqual(N["TACOS"]["值"], acos["值"] * share["值"], delta=0.002)
            for n in N.values():
                for k in ("名", "值", "对比", "上周", "变化", "判定"): self.assertIn(k, n)
                self.assertIn(n["判定"], ("正常", "偏高", "偏低", None))
                if n["值"] is None or n["判定"] is None: self.assertTrue(n.get("缺"), n["名"])

    def test_只有SP广告销售额时_占比写null加缺(self):
        def sp_only(F): F["四周"]["广告销售额口径"] = "仅SP"
        N = {n["名"]: n for n in self.rerun(facts=sp_only)["拆解"]["节点"]}
        self.assertIsNone(N["广告销售额占比"]["值"]); self.assertTrue(N["广告销售额占比"]["缺"])
        self.assertAlmostEqual(N["ACOS（全部广告）"]["值"], self.F()["SP-近14天"]["ACOS"], places=4); self.assertIn("SP", N["ACOS（全部广告）"]["缺"])

    def test_核心限制_v1是库存_到仓改成1以后不是(self):
        L = self.biz("v1")["拆解"]["核心限制"]
        self.assertEqual(L["变量"], "库存"); self.assertTrue(L["规则"].startswith("①")); self.assertTrue(L["依据"])
        self.assertEqual(self.biz("v1")["路径"]["脚本建议"], "先解决库存")
        L = self.biz("r1")["拆解"]["核心限制"]
        self.assertNotEqual(L["变量"], "库存"); self.assertIn(L["变量"], LIMITS); self.assertNotEqual(self.biz("r1")["路径"]["脚本建议"], "先解决库存")

    def test_核心限制_按固定顺序往下判(self):
        tacos = self.F("r1")["四周"]["TACOS"]; over = {"定价毛利率": tacos + 0.05, "目标广告后利润率": 0.10}          # TACOS 超目标、没到亏损
        B = self.rerun("r1", params=dict(over, 目标ACOS=0.05))                                                    # ACOS 也高于目标 → ③
        self.assertIn(B["拆解"]["核心限制"]["变量"], ("CPC", "CVR")); self.assertTrue(B["拆解"]["核心限制"]["规则"].startswith("③")); self.assertEqual(B["路径"]["脚本建议"], "降耗")
        B = self.rerun("r1", params=dict(over, 目标ACOS=0.90))                                                    # ACOS 正常 → ④
        self.assertEqual(B["拆解"]["核心限制"]["变量"], "广告销售额占比"); self.assertEqual(B["拆解"]["归因路径"]["入口"], "利润率差")
        def waste(F): F["活动表"]["近14天"]["词组主干"]["ACOS"] = 0.99                                              # 最大的活动 ACOS 超盈亏线 → ⑤
        B = self.rerun("r1", params={"定价毛利率": None, "目标广告后利润率": None, "目标ACOS": 0.30}, facts=waste)
        self.assertEqual(B["拆解"]["核心限制"]["变量"], "无效广告"); self.assertEqual(B["路径"]["脚本建议"], "降耗")

    def test_归因路径(self):
        for scene in SCENE:
            D = self.biz(scene)["拆解"]; G = D["归因路径"]
            self.assertIn(D["核心限制"]["变量"], LIMITS); self.assertIn(G["入口"], ENTRIES)
            self.assertTrue(3 <= len(G["步骤"]) <= 5, G["步骤"]); self.assertTrue(all(isinstance(s, str) and s for s in G["步骤"]))

    # ---- 任务 ----
    def test_任务覆盖活动表全部活动_枚举合法(self):
        for scene in SCENE:
            T, tab = self.biz(scene)["任务"], self.F(scene)["活动表"]
            self.assertEqual({t["活动"] for t in T}, set(tab["近14天"]) | set(tab["前14天"])); self.assertEqual(len(T), len({t["活动"] for t in T}))
            for t in T:
                self.assertIn(t["建议任务"], TASKS, t["活动"]); self.assertIn(t["完成情况"], DONE, t["活动"]); self.assertTrue(set(t["标记"]) <= MARKS, t)
                self.assertTrue(t["依据"]); self.assertEqual("纯利型候选" in t["标记"], t["建议任务"] == "纯利型"); self.assertEqual("任务没完成" in t["标记"], t["完成情况"] == "未达标")

    def test_任务规则_演示数据(self):
        B = self.biz(); T = {t["活动"]: t for t in B["任务"]}; tt, gm = B["算账"]["目标TACOS"], B["算账"]["定价毛利率"]; tab = self.F()["活动表"]["近14天"]
        K = jread(f"{REPO}/口径.json"); n, ck = K["经营"]["纯利型订单门槛"], K["门槛"]["活动级判断点击"]
        for name, p in tab.items():
            pure = p["ACOS"] is not None and p["ACOS"] < tt and p["订单"] >= n
            self.assertEqual(T[name]["建议任务"] == "纯利型", pure, name)
            if p["ACOS"] is not None and p["ACOS"] > gm and p["点击"] >= ck: self.assertEqual(T[name]["完成情况"], "未达标", name)
        self.assertEqual(T["词组主干"]["建议任务"], "纯利型"); self.assertEqual(T["自动-主"]["建议任务"], "测词拓词")
        self.assertIn("预算吃紧", T["精确主干"]["标记"])

    def test_活动表删掉_不崩_任务为空并写缺(self):
        def drop(F): F.pop("活动表")
        B = self.rerun(facts=drop)
        self.assertNotIn("错误", B); self.assertEqual(B["任务"], []); self.assertIn("任务", B["缺"])
        self.assertEqual([c["key"] for c in B["路径"]["候选"]], ["增单", "降耗", "调价", "重构"]); self.assertEqual(list(B["决策表"]), NINE)
        waste = next(c for c in B["路径"]["候选"] if c["key"] == "降耗")["测算"]
        self.assertIsNone(waste["无效广告花费"]); self.assertTrue(waste["缺"])

    # ---- 路径与决策表 ----
    def test_四条路径齐全(self):
        for scene in SCENE:
            R = self.biz(scene)["路径"]
            self.assertEqual([c["key"] for c in R["候选"]], ["增单", "降耗", "调价", "重构"]); self.assertIn(R["脚本建议"], ADVICE)
            for c in R["候选"]:
                self.assertIsInstance(c["适用"], bool); self.assertTrue(c["名"] and c["理由"]); self.assertIsInstance(c["测算"], dict)
                for k, v in c["测算"].items():
                    if v is None: self.assertIn("缺", c["测算"], f"{c['key']}.{k} 是 null 却没写缺")
            m = {c["key"]: c["测算"] for c in R["候选"]}
            for k in ("现广告单", "现自然单", "广告可承担订单占比"): self.assertIn(k, m["增单"])
            self.assertEqual(m["调价"]["价格弹性"], "未知")
        self.assertFalse(next(c for c in self.biz("v1")["路径"]["候选"] if c["key"] == "增单")["适用"])       # 库存撑不住时不谈增单
        self.assertTrue(next(c for c in self.biz("r1")["路径"]["候选"] if c["key"] == "增单")["适用"]); self.assertEqual(self.biz("r1")["路径"]["脚本建议"], "增单")

    def test_决策表九栏齐全(self):
        for scene in SCENE:
            B = self.biz(scene); T = B["决策表"]
            self.assertEqual(list(T), NINE); self.assertTrue(all(isinstance(v, str) and v for v in T.values()))
            self.assertTrue(T["首要目标"].startswith("（人定）")); self.assertIn(B["路径"]["脚本建议"], T["首要目标"])
            self.assertTrue(T["核心限制"].startswith(B["拆解"]["核心限制"]["变量"])); self.assertIn(jread(f"{self.dir[scene]}/参数.json")["复盘日"], T["复盘时间"])

    # ---- 出错时 ----
    def test_数字文件坏了_写错误字段_退出码1(self):
        def broken(F): F.pop("四周")
        B = self.rerun(facts=broken, code=1)
        self.assertIn("错误", B); self.assertEqual(B["写入方"], "脚本")

    def test_biz失败不让render失败(self):
        d = self.dir["v1"]; good = tread(f"{d}/_脚本/biz.py")
        try:
            twrite(f"{d}/_脚本/biz.py", "raise RuntimeError('故意弄坏')\n")
            r = script(d, "render.py"); self.assertEqual(r.returncode, 0, r.stderr[-800:])
            self.assertIn("错误", self.biz()); self.assertIn("经营核算", r.stderr); self.assertEqual(len(jread(f"{d}/广告闭环/输出/动作清单.json")), 89)
        finally:
            twrite(f"{d}/_脚本/biz.py", good)

    def test_口径缺键回退默认值(self):
        d = self.dir["v1"]; text = tread(f"{d}/口径.json")
        try:
            K = json.loads(text); K.pop("经营"); K.pop("复盘"); jwrite(f"{d}/口径.json", K)
            B = self.rerun(); B.pop("生成于"); want = json.loads(self.keep["v1"]["广告闭环/输出/经营.json"]); want.pop("生成于")
            self.assertEqual(B, want)
        finally:
            twrite(f"{d}/口径.json", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
