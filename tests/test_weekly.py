# -*- coding: utf-8 -*-
"""每周一圈的测试：每个用例都在临时副本上跑（仓库本身的状态库和产物不动），不接模型、不推送。
跑法：python3 -m pytest tests/test_weekly.py -q -p no:cacheprovider      （流水线要 pandas）"""
import json, os, shutil, sqlite3, subprocess, sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "_脚本")
sys.path.insert(0, SCRIPTS)
SKIP = shutil.ignore_patterns(".git", "工作台.db*", "运行记录", "__pycache__", ".pytest_cache", "评测", "tests", "截图", "流程图", "学员材料", "*.html", "skills", "agent", "docs")
DEMO = {"目标ACOS": 0.3, "补货到仓周数": 4, "产品阶段": "新品期", "取舍项": ["A", "B", "C", "E"], "版本": 1}


def clean_env():
    env = {k: v for k, v in os.environ.items() if k != "FEISHU_WEBHOOK" and not k.startswith("ADS_LLM")}
    env.update({"ADS_LLM": "0", "PYTHONDONTWRITEBYTECODE": "1"}); return env


def edit_params(root, **kw):
    p = os.path.join(root, "参数.json"); P = json.load(open(p, encoding="utf-8"))
    for k, v in kw.items():
        if v is None: P.pop(k, None)
        else: P[k] = v
    json.dump(P, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


@pytest.fixture
def root(tmp_path):
    dst = str(tmp_path / "ws"); shutil.copytree(REPO, dst, ignore=SKIP)
    for stale in ("AI补位.json", "经营.json"):                      # 仓里上一圈留下的补位和经营核算不带进来
        p = os.path.join(dst, "广告闭环", "输出", stale)
        if os.path.exists(p): os.remove(p)
    edit_params(dst, **DEMO); return dst


def weekly(root, *args, script="weekly.py"):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), "--root", root, *args], capture_output=True, text=True, env=clean_env(), timeout=300)


def runs(root):
    p = os.path.join(root, "运行记录", "runs.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8").read().splitlines()] if os.path.exists(p) else []


def task(root):
    c = sqlite3.connect(os.path.join(root, "工作台.db")); c.row_factory = sqlite3.Row
    try: return dict(c.execute("SELECT * FROM task").fetchone()), [dict(r) for r in c.execute("SELECT * FROM action")]
    finally: c.close()


def step(rec, name): return next(s for s in rec["steps"] if s["name"] == name)


def test_first_run_makes_v1_and_one_record(root):
    r = weekly(root)
    assert r.returncode == 0, r.stdout + r.stderr
    t, acts = task(root)
    assert t["version"] == 1 and t["status"] == "待核对" and acts and all(a["status"] == "待确认" for a in acts)
    rs = runs(root); assert len(rs) == 1
    rec = rs[0]
    assert rec["version"] == 1 and rec["actions"] == len(acts) == rec["pending"] and rec["dry_run"] is False and rec["trigger"] == "定时" and rec["problems"] == [] and rec["exit"] == 0
    assert [s["name"] for s in rec["steps"]] == ["读回状态", "数据体检", "跑一圈", "经营核算", "模型补位", "自检", "起草周报", "留痕"]
    assert all(set(s) >= {"name", "ok", "ms", "note"} and s["ok"] for s in rec["steps"])
    assert rec["llm"] == {"状态": "skipped", "calls": 0}
    assert "【广告周检 Agent】任务" in r.stdout and "✓ 跑一圈：" in r.stdout and "待审批：" in r.stdout
    recs = os.listdir(os.path.join(root, "运行记录"))
    assert any(f.startswith("周报-") and f.endswith(".md") for f in recs) and any(f.startswith("weekly-") and f.endswith(".log") for f in recs)
    report = open(os.path.join(root, rec["report"]), encoding="utf-8").read()
    assert "没有发" in report and all(h in report for h in ("这周结论", "要你拍板", "下周看什么")) and f"待审批 {len(acts)} 条" in report


def test_same_input_again_does_not_rerun(root):
    assert weekly(root).returncode == 0
    r = weekly(root, "--trigger", "手动")
    assert r.returncode == 0, r.stdout + r.stderr
    rs = runs(root); assert len(rs) == 2
    assert "不重跑" in step(rs[1], "跑一圈")["note"] and step(rs[1], "跑一圈")["ok"] and rs[1]["trigger"] == "手动" and rs[1]["ran"] is False
    assert task(root)[0]["version"] == 1 and rs[1]["version"] == 1 and rs[1]["pending"] == rs[0]["pending"]


def test_same_input_marked_pending_again_still_does_not_rerun(root):
    assert weekly(root).returncode == 0
    c = sqlite3.connect(os.path.join(root, "工作台.db")); c.execute("UPDATE task SET status='待处理'"); c.commit(); c.close()      # 人点了「重新触发」但输入没改
    r = weekly(root); rs = runs(root)
    assert r.returncode == 0 and "不重跑" in step(rs[1], "跑一圈")["note"] and task(root)[0]["version"] == 1


def test_missing_required_input_exits_2(root):
    edit_params(root, 补货到仓周数=None)
    r = weekly(root)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "缺输入" in r.stdout and "补货到仓周数" in r.stdout
    assert not os.path.exists(os.path.join(root, "工作台.db"))                    # 没跑，状态库都不建
    rec = runs(root)[0]
    assert rec["exit"] == 2 and [s["name"] for s in rec["steps"]] == ["读回状态", "数据体检", "留痕"] and "补货到仓周数" in rec["problems"][0]


def test_dry_run_creates_no_db(root):
    r = weekly(root, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not any(f.startswith("工作台.db") for f in os.listdir(root))
    rec = runs(root)[0]
    assert rec["dry_run"] is True and rec["llm"]["calls"] == 0 and "演练" in step(rec, "跑一圈")["note"] and rec["report"] is None
    assert not any(f.startswith("周报-") for f in os.listdir(os.path.join(root, "运行记录")))
    assert not os.path.exists(os.path.join(root, "广告闭环", "输出", "AI补位.json"))


def test_no_llm_flag_skips_model(root):
    r = weekly(root, "--no-llm")
    rec = runs(root)[0]
    assert r.returncode == 0 and "--no-llm" in step(rec, "模型补位")["note"] and not os.path.exists(os.path.join(root, "广告闭环", "输出", "AI补位.json"))


def test_failed_step_exits_1_and_keeps_last_good_result(root):
    assert weekly(root).returncode == 0
    before = open(os.path.join(root, "广告闭环", "输出", "动作清单.json"), encoding="utf-8").read()
    open(os.path.join(root, "_原始拉取", "库存与动销-按SKU.json"), "w", encoding="utf-8").write("{ 坏的 JSON")
    c = sqlite3.connect(os.path.join(root, "工作台.db")); c.execute("UPDATE task SET status='待处理', arrive_weeks=2"); c.commit(); c.close()
    r = weekly(root); rec = runs(root)[1]
    assert r.returncode == 1, r.stdout + r.stderr
    assert not step(rec, "跑一圈")["ok"] and rec["problems"] and step(rec, "留痕")["ok"] and "✗ 跑一圈：" in r.stdout
    assert open(os.path.join(root, "广告闭环", "输出", "动作清单.json"), encoding="utf-8").read() == before      # 上一份有效结果没被盖
    assert task(root)[0]["status"] == "遇到问题" and task(root)[0]["version"] == 1


def test_agent_run_wrapper_keeps_old_exit_codes(root):
    r = weekly(root, "--trigger", "手动", script="agent_run.py")
    assert r.returncode == 0 and "【广告周检 Agent】任务" in r.stdout and "触发：手动" in r.stdout and len(runs(root)) == 1
    edit_params(root, 目标ACOS=None)
    r = weekly(root, script="agent_run.py")
    assert r.returncode == 2 and "缺输入" in r.stdout                               # 老约定：失败或缺输入都是 2


def test_model_draft_is_used_but_never_sent(root, monkeypatch):
    import weekly as W
    monkeypatch.delenv("FEISHU_WEBHOOK", raising=False); monkeypatch.setenv("ADS_LLM", "0")
    sent = []; monkeypatch.setattr(W, "push", lambda hook, text: sent.append(text) or "ok")
    draft = "## 这周结论\n模型写的结论。\n## 要你拍板\n模型写的拍板项。\n## 下周看什么\n三个问题。"
    monkeypatch.setattr(W.LLM, "fill", lambda root, **kw: {"状态": "ok", "原因": "", "模型": "fake-model", "calls": 5, "丢弃": [], "各项": {}, "周报草稿": draft})
    code = W.Weekly(root).run()
    rec = runs(root)[0]
    assert code == 0 and rec["llm"] == {"状态": "ok", "calls": 5}
    report = open(os.path.join(root, rec["report"]), encoding="utf-8").read()
    assert "模型写的结论" in report and "Agent 写" in report and "脚本附注" in report and not sent


def test_loading_the_workbench_does_not_change_the_model_channel(root, monkeypatch):
    import weekly as W
    for k in [k for k in os.environ if k.startswith("ADS_LLM")]: monkeypatch.delenv(k)
    W.load_app(root)                                                             # 工作台导入时会读本机的 agent/.env.local
    assert not [k for k in os.environ if k.startswith("ADS_LLM")]
    assert W.LLM.channel(W.LLM.load_config(root))["ok"] is False                 # 仓里的默认配置：没接模型
    monkeypatch.setenv("ADS_LLM", "0"); W.load_app(root); assert os.environ["ADS_LLM"] == "0"
