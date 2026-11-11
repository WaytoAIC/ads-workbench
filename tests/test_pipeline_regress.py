# -*- coding: utf-8 -*-
"""回归：阈值收进 口径.json 之后，演示数据的结果一条都不能变。

做法：在临时目录里 rsync 几份仓库副本（不含 .git、状态库），各跑一遍 render.py，只写副本、不动仓库：
  · 收口前的脚本（从 git 取基线提交的 pipeline.py / render.py）对 现在的脚本 —— 动作清单逐条相同、验证器逐项相同、数字.json 除新增键外相同；
  · 两种输入都比：v1（到仓 4 周）和「到仓周数改成 1、版本改成 2」；
  · 把 口径.json 拿掉，结果也不变（缺文件回退到内置默认值）；改一个口径，结果会跟着变（说明脚本确实在读它）。
拿不到基线提交（不是 git 仓库、或浅克隆）时，「改前改后」那几条跳过，其余照跑。

用法：python3 -m unittest tests.test_pipeline_regress -v      或      python3 tests/test_pipeline_regress.py"""
import json, os, shutil, subprocess, sys, tempfile, unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "3627351bfd75a5697478f15a1f970eac5772afb5"          # 阈值收口之前的最后一个提交
EXPECT = {"v1": 89, "r1": 56}                              # 演示数据（_原始拉取/）在两种输入下的动作条数；换了演示数据要跟着改
SCENE = {"v1": {"版本": 1, "补货到仓周数": 4, "目标ACOS": 0.30, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"]},      # 与工作台「重置」写回的一致
         "r1": {"版本": 2, "补货到仓周数": 1, "目标ACOS": 0.30, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"]}}
NEW_TOP = ["活动搜索词-近14天"]                             # 数字.json 这次新增的键：比较时先拿掉
NEW_IN = {"四周": ["广告销售额", "广告销售额口径"], "活动表": ["近7天"]}
NEW_WEEK = ["广告销售额"]
OTHER_OUT = ["诊断-三栏表.md", "选项.json", "选项比较.md", "渲染结果.json", "动作清单.csv", "否词清单.csv", "回测-汇总.csv", "广告产品调整表.csv", "竞价调整表.csv", "竞品品牌词分拣表.csv", "分组明细-近14天-请人工纠错.csv"]   # 流水线的其余产物
SKIP_COPY = [".git", "工作台.db*", "__pycache__", ".上一份有效结果", "运行记录", "截图", "流程图", "*.html"]


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


def base_file(rel):
    """基线提交里的一个文件；取不到返回 None。"""
    r = subprocess.run(["git", "-C", REPO, "show", f"{BASE}:{rel}"], capture_output=True)
    return r.stdout if r.returncode == 0 and r.stdout else None


def make(tmp, name, scene, old=False, kj="keep"):
    """造一份副本并跑 render.py，返回 (副本目录, 进程结果)。old＝换成收口前的脚本；kj＝keep 原样 / drop 拿掉 口径.json / 一个函数（改口径）。"""
    d = os.path.join(tmp, name); copy_repo(d)
    P = jread(f"{d}/参数.json"); P.update(SCENE[scene]); jwrite(f"{d}/参数.json", P)
    back = f"{d}/广告闭环/输出/读回状态.json"                # 人在工作台点过的驳回、确认会改变动作清单：回归只比「没人点过」的状态
    if os.path.exists(back): os.remove(back)
    if old:
        for rel in ("_脚本/pipeline.py", "_脚本/render.py"): twrite(f"{d}/{rel}", base_file(rel))
    if kj == "drop": os.remove(f"{d}/口径.json")
    elif callable(kj): K = jread(f"{d}/口径.json"); kj(K); jwrite(f"{d}/口径.json", K)
    r = subprocess.run([sys.executable, f"{d}/_脚本/render.py"], capture_output=True, text=True, env=dict(os.environ, ADS_ROOT=d))
    return d, r


def out(d, name): return jread(f"{d}/广告闭环/输出/{name}")


def strip_new(F):
    F = json.loads(json.dumps(F))
    for k in NEW_TOP: F.pop(k, None)
    for k, ks in NEW_IN.items():
        for x in ks: (F.get(k) or {}).pop(x, None)
    for w in F.get("逐周") or []:
        for x in NEW_WEEK: w.pop(x, None)
    return F


class PipelineRegress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ads-regress-"); cls.has_base = base_file("_脚本/pipeline.py") is not None; cls.run_ = {}
        for scene in SCENE:
            cls.run_[("new", scene)] = make(cls.tmp, f"new_{scene}", scene)
            cls.run_[("nokj", scene)] = make(cls.tmp, f"nokj_{scene}", scene, kj="drop")
            if cls.has_base: cls.run_[("old", scene)] = make(cls.tmp, f"old_{scene}", scene, old=True)

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.tmp, ignore_errors=True)

    def ran(self, kind, scene):
        d, r = self.run_[(kind, scene)]; self.assertEqual(r.returncode, 0, f"{kind}/{scene} 的 render.py 失败：{r.stderr[-800:]}"); return d

    def test_现在的脚本_条数和验证器(self):
        for scene, n in EXPECT.items():
            with self.subTest(scene=scene):
                d = self.ran("new", scene); ck = out(d, "验证器.json")
                self.assertEqual(len(out(d, "动作清单.json")), n)
                self.assertEqual(len(ck), 9); self.assertTrue(all(x["通过"] for x in ck), [x["检查"] for x in ck if not x["通过"]])

    def test_改前改后_动作清单逐条相同(self):
        if not self.has_base: self.skipTest(f"拿不到基线提交 {BASE[:7]}（不是 git 仓库或浅克隆）")
        for scene in SCENE:
            with self.subTest(scene=scene):
                a, b = out(self.ran("old", scene), "动作清单.json"), out(self.ran("new", scene), "动作清单.json")
                self.assertEqual(len(a), len(b))
                for x, y in zip(a, b): self.assertEqual(x, y, f"动作 {x.get('动作编号')} 变了")

    def test_改前改后_验证器和数字相同(self):
        if not self.has_base: self.skipTest(f"拿不到基线提交 {BASE[:7]}（不是 git 仓库或浅克隆）")
        for scene in SCENE:
            with self.subTest(scene=scene):
                a, b = self.ran("old", scene), self.ran("new", scene)
                self.assertEqual(out(a, "验证器.json"), out(b, "验证器.json"))
                Fa, Fb = out(a, "数字.json"), out(b, "数字.json")
                self.assertEqual(Fa, strip_new(Fa), "基线的 数字.json 里已经有「新增键」，NEW_* 列表要更新")
                self.assertEqual(Fa, strip_new(Fb), "数字.json 除新增键外应当相同")

    def test_改前改后_其余产物相同(self):
        """三栏表、选项、行动卡、各张 csv：文字里的阈值改成读口径以后，一个字都不该变。"""
        if not self.has_base: self.skipTest(f"拿不到基线提交 {BASE[:7]}（不是 git 仓库或浅克隆）")
        for scene in SCENE:
            a, b = self.ran("old", scene), self.ran("new", scene)
            for sub in ("广告闭环/输出", "广告闭环/行动卡"):
                for n in (OTHER_OUT if sub.endswith("输出") else sorted(os.listdir(f"{a}/{sub}"))):
                    with self.subTest(scene=scene, file=n):
                        ta, tb = (tread(f"{d}/{sub}/{n}").replace(d, "<ROOT>") for d in (a, b))
                        self.assertEqual(ta, tb)

    def test_拿掉口径文件_结果不变(self):
        for scene in SCENE:
            with self.subTest(scene=scene):
                a, b = self.ran("new", scene), self.ran("nokj", scene)
                self.assertFalse(os.path.exists(f"{b}/口径.json"))
                for n in ("动作清单.json", "验证器.json", "数字.json"): self.assertEqual(out(a, n), out(b, n), n)

    def test_改一个口径_结果跟着变(self):
        def harder(K): K["门槛"]["搜索词收割订单"] = 999
        d, r = make(self.tmp, "changed_v1", "v1", kj=harder); self.assertEqual(r.returncode, 0, r.stderr[-800:])
        kinds = {x["类型"] for x in out(d, "动作清单.json")}; base = {x["类型"] for x in out(self.ran("new", "v1"), "动作清单.json")}
        self.assertIn("搜索词收割", base); self.assertNotIn("搜索词收割", kinds); self.assertNotIn("来源组否定", kinds)

    def test_口径文件_每个键都有说明(self):
        K = jread(f"{REPO}/口径.json")
        for g in ("调幅", "门槛", "判定", "复盘", "经营"):
            self.assertIn(g, K)
            for k in K[g]: self.assertIn(k, K["说明"][g], f"口径.json 的 {g}.{k} 没写说明")


if __name__ == "__main__":
    unittest.main(verbosity=2)
