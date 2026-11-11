# -*- coding: utf-8 -*-
"""模型补位的护栏测试：全部用假通道（monkeypatch llm.ask），不连任何模型、不读任何真密钥。
跑法：python3 -m pytest tests/test_llm.py -q -p no:cacheprovider"""
import json, os, sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "_脚本"))
import llm  # noqa: E402

FAKE_ENV = {"ADS_LLM_KEY": "sk-test-not-a-real-key", "ADS_LLM_BASE": "http://127.0.0.1:9/v1", "ADS_LLM_MODEL": "fake-model"}
LABELS = {"0": "0-自家品牌词", "1": "1-核心大词", "2": "2-属性长尾", "3": "3-竞品品牌词", "41": "4a-跑偏(需求不同)", "42": "4b-泛词(不是浴缸淋浴用)", "5": "5-ASIN投放"}
BIZ = {   # 照 docs/架构.md 第二节的示例结构造的一份
    "写入方": "脚本", "生成于": "2026-08-03",
    "算账": {"定价毛利率": 0.486, "目标广告后利润率": 0.15, "目标TACOS": 0.336, "当前TACOS": 0.285, "TACOS余量": 0.051, "判定": "在目标内",
             "当前广告后利润率": 0.202, "近7天日均销售额": 3119.0, "单品日预算": 1048.0, "现日预算合计": 589.0, "上周日均广告费": 866.0, "阶段": "新品期", "阶段要求": "先要量"},
    "拆解": {"公式": ["TACOS = ACOS × 广告销售额占比"],
             "节点": [{"名": "TACOS", "值": 0.285, "对比": "目标 33.6%", "判定": "正常"}, {"名": "ACOS（全部广告）", "值": 0.297}, {"名": "广告销售额占比", "值": 0.957}],
             "核心限制": {"变量": "库存", "规则": "整体可售周数 < 补货到仓周数", "依据": ["整体可售 3.1 周，补货到仓要 4 周"]},
             "归因路径": {"入口": "利润率差", "步骤": ["TACOS 28.5% 低于目标 33.6%"]}},
    "任务": [{"活动": "词组主干", "建议任务": "纯利型", "依据": "ACOS 25.9% 低于目标 TACOS 33.6%，近 14 天 224 单", "完成情况": "达标", "标记": ["纯利型候选"]},
             {"活动": "广泛大词", "建议任务": "测词拓词", "依据": "近 14 天 31 单", "完成情况": "看不出", "标记": []}],
    "路径": {"候选": [{"key": "增单", "名": "把订单做大", "适用": False, "理由": "库存不够", "测算": {"现广告单": 493}},
                     {"key": "降耗", "名": "减少广告消耗", "适用": True, "理由": "TACOS 28.5%", "测算": {}},
                     {"key": "调价", "名": "调整售价", "适用": False, "理由": "", "测算": {}}, {"key": "重构", "名": "重新设计", "适用": False, "理由": "", "测算": {}}],
             "脚本建议": "先解决库存"},
    "决策表": {"当前状态": "TACOS 28.5%，在目标内", "首要目标": "（人定）", "核心限制": "库存", "选择方向": "先解决库存", "执行方案": "", "投入边界": "", "验证标准": "", "复盘时间": "2026-08-10", "后续选择": ""}}
GOOD = {
    "核心限制": {"一句话": "库存只够 3.1 周，补货要 4 周，先保主力规格不断货。"},
    "路径": {"选": "降耗", "理由": "TACOS 28.5% 在目标 33.6% 内，库存不够放量。", "不选其他的理由": "增单受库存限制；调价、重构证据不足。"},
    "任务": {"词组主干": {"任务": "纯利型", "理由": "ACOS 25.9% 低于目标 TACOS 33.6%"}, "广泛大词": {"任务": "测词拓词", "理由": "证据不足"}},
    "搜索词": {"shower mat for elderly": "2-属性长尾", "kitchen rug": "4a-跑偏(需求不同)"},
    "决策表": {"决策表草稿": {"首要目标": "稳住利润，先不断货", "执行方案": "先处理待审批的 3 条动作", "验证标准": "到复盘日 TACOS 仍不高于 33.6%", "复盘时间": "2026-08-10"},
              "周报草稿": "## 这周结论\nTACOS 28.5%，在目标内；核心限制是库存。\n## 要你拍板\n待审批 3 条：降竞价 2、换道否定 1。\n## 下周看什么\n1. 库存回到 4 周没有？2. TACOS 还在目标内吗？3. 降竞价后单量掉没掉？"},
}


def make_root(tmp_path, biz=True):
    out = tmp_path / "广告闭环" / "输出"; out.mkdir(parents=True)
    if biz: (out / "经营.json").write_text(json.dumps(BIZ, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "分组规则.json").write_text(json.dumps({"COMP": "halvex", "OFF": "kitchen", "INTENT": "tub|shower", "CORE": "bathtub", "MOD": "large", "标签": LABELS}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "参数.json").write_text(json.dumps({"复盘日": "2026-08-10"}, ensure_ascii=False), encoding="utf-8")
    (out / "分组明细-近14天-请人工纠错.csv").write_text(
        "﻿用户搜索词,分组,广告花费\nbathtub mat,1-核心大词,800\nshower mat for elderly,4b-泛词(不是浴缸淋浴用),12.5\nkitchen rug,4b-泛词(不是浴缸淋浴用),30\nfloor mat,4b-泛词(不是浴缸淋浴用),3\n", encoding="utf-8")
    acts = [{"类型": "降竞价", "对象": "a", "状态": "待确认"}, {"类型": "降竞价", "对象": "b", "状态": "待确认"}, {"类型": "换道否定", "对象": "c", "状态": "待确认"}]
    (out / "动作清单.json").write_text(json.dumps(acts, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


def fake_ask(replies, log=None):
    """假通道：看提示词里的任务名回对应的 JSON。replies 的值可以是 dict（回 JSON）、str（原样回）、list（按次序回）。"""
    def ask(ch, system, user, max_tokens=8000):
        key = next(k for k, mark in (("核心限制", "任务：用一句话"), ("路径", "任务：在候选路径里"), ("任务", "任务：给每个广告活动"), ("搜索词", "正则没认出来"), ("决策表", "任务：写两样草稿")) if mark in user)
        if log is not None: log.append((key, system, user))
        r = replies[key]
        if isinstance(r, list): r = r.pop(0)
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
    return ask


def run(tmp_path, monkeypatch, replies, **kw):
    root = make_root(tmp_path, biz=kw.pop("biz", True)); monkeypatch.setattr(llm, "ask", fake_ask(replies, kw.pop("log", None)))
    doc = llm.fill(root, env=dict(FAKE_ENV), cfg=json.loads(json.dumps(llm.DEFAULT_CFG)), quiet=True, **kw)
    saved = json.load(open(os.path.join(root, "广告闭环", "输出", "AI补位.json"), encoding="utf-8"))
    return doc, saved


def test_all_good_is_ok(tmp_path, monkeypatch):
    doc, saved = run(tmp_path, monkeypatch, dict(GOOD))
    assert doc["状态"] == "ok", doc.get("原因")
    assert doc["calls"] == 5 and doc["丢弃"] == []
    assert saved["路径建议"]["选"] == "降耗" and saved["任务标签"]["词组主干"]["任务"] == "纯利型"
    assert saved["搜索词补位"] == GOOD["搜索词"] and set(saved["决策表草稿"]) == set(llm.DRAFT_COLS) and "这周结论" in saved["周报草稿"]
    assert saved["核心限制一句话"].startswith("库存") and saved["通道"] == "openai · 127.0.0.1"


def test_enum_outside_is_dropped(tmp_path, monkeypatch):
    replies = dict(GOOD, 路径={"选": "加预算冲量", "理由": "证据不足", "不选其他的理由": "证据不足"},
                   任务={"词组主干": {"任务": "冲排名", "理由": "证据不足"}, "广泛大词": {"任务": "测词拓词", "理由": "证据不足"}, "不存在的活动": {"任务": "收割", "理由": "x"}},
                   搜索词={"shower mat for elderly": "6-新发明的分组", "kitchen rug": "4a-跑偏(需求不同)", "not in list": "1-核心大词"})
    doc, saved = run(tmp_path, monkeypatch, replies)
    assert doc["状态"] == "partial"
    assert "路径建议" not in saved                                              # 四条之外的路径：整项丢弃
    assert saved["任务标签"] == {"广泛大词": {"任务": "测词拓词", "理由": "证据不足"}}     # 六类之外的、不是给定活动的：那一条丢弃
    assert saved["搜索词补位"] == {"kitchen rug": "4a-跑偏(需求不同)"}             # 标签之外的、不是给定词的：那一条丢弃
    assert {d["项"] for d in saved["丢弃"]} == {"路径", "任务", "搜索词"} and len(saved["丢弃"]) == 5
    assert all(d.get("原因") for d in saved["丢弃"])


def test_invented_number_is_dropped(tmp_path, monkeypatch):
    replies = dict(GOOD, 核心限制={"一句话": "库存只够 3.1 周，断货后 ACOS 会涨到 99.9%。"},
                   路径={"选": "降耗", "理由": "每周能省 $12,345。", "不选其他的理由": "证据不足"},
                   任务={"词组主干": {"任务": "纯利型", "理由": "ACOS 25.9% 低于目标 TACOS 33.6%"}, "广泛大词": {"任务": "测词拓词", "理由": "ACOS 25.9%，还行"}})
    doc, saved = run(tmp_path, monkeypatch, replies)
    assert doc["状态"] == "partial"
    assert "核心限制一句话" not in saved and "路径建议" not in saved               # 编出来的 99.9%、$12,345
    assert list(saved["任务标签"]) == ["词组主干"]                               # 25.9% 是别的活动的数，不是「广泛大词」自己的依据
    why = {d["项"]: d["原因"] for d in saved["丢弃"]}
    assert "99.9%" in why["核心限制"] and "$12,345" in why["路径"] and "25.9%" in why["任务"]
    assert "周报草稿" in saved and "决策表草稿" in saved                          # 没编数的照常落盘


def test_number_guard_matches_rounding():
    allowed = llm.allowed_numbers({"TACOS": 0.285, "依据": "近 14 天 224 单，花费 $1,587.47"})
    assert llm.invented("TACOS 28.5%，约 29%，花了 $1,587，也就是 $1.6k", allowed) == []
    assert llm.invented("TACOS 30%", allowed) == ["30%"] and llm.invented("花了 ＄2,000", allowed) == ["＄2,000"]
    assert llm.invented("没有带符号的数字 224 和 999 不查", allowed) == []


def test_no_model_writes_skipped(tmp_path, monkeypatch):
    root = make_root(tmp_path); called = []
    monkeypatch.setattr(llm, "ask", lambda *a, **k: called.append(1) or "{}")
    doc = llm.fill(root, env={}, cfg=json.loads(json.dumps(llm.DEFAULT_CFG)), quiet=True)
    saved = json.load(open(os.path.join(root, "广告闭环", "输出", "AI补位.json"), encoding="utf-8"))
    assert doc["状态"] == saved["状态"] == "skipped" and saved["原因"] == "没接模型" and doc["calls"] == 0 and not called
    cfg = json.loads(json.dumps(llm.DEFAULT_CFG)); cfg["llm"]["enabled"] = True
    assert llm.fill(root, env={"ADS_LLM": "0", **FAKE_ENV}, cfg=cfg, quiet=True)["状态"] == "skipped" and not called      # ADS_LLM=0 强制关


def test_missing_biz_does_not_crash(tmp_path, monkeypatch):
    log = []
    doc, saved = run(tmp_path, monkeypatch, dict(GOOD), biz=False, log=log)
    assert [k for k, _, _ in log] == ["搜索词"] and doc["calls"] == 1             # 只有不依赖经营.json 的那一项真的调了
    assert saved["状态"] == "partial" and saved["搜索词补位"] == GOOD["搜索词"]
    for item in ("核心限制", "路径", "任务", "决策表＋周报"):
        assert saved["各项"][item]["状态"] == "skipped" and "经营.json 不存在" in saved["各项"][item]["原因"]
    assert "经营.json 不存在" in saved["原因"]


def test_biz_with_error_field_is_skipped(tmp_path, monkeypatch):
    root = make_root(tmp_path); p = os.path.join(root, "广告闭环", "输出", "经营.json")
    json.dump({"错误": "缺利润表"}, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    monkeypatch.setattr(llm, "ask", fake_ask(dict(GOOD)))
    doc = llm.fill(root, env=dict(FAKE_ENV), cfg=json.loads(json.dumps(llm.DEFAULT_CFG)), quiet=True)
    assert doc["各项"]["路径"]["状态"] == "skipped" and "缺利润表" in doc["各项"]["路径"]["原因"]


def test_bad_json_retries_once(tmp_path, monkeypatch):
    doc, saved = run(tmp_path, monkeypatch, dict(GOOD, 核心限制=["抱歉，我先解释一下……", GOOD["核心限制"]], 路径=["不是 JSON", "还不是 JSON"]))
    assert doc["calls"] == 7                                                     # 5 次 + 核心限制重试 1 次 + 路径重试 1 次
    assert "核心限制一句话" in saved and "路径建议" not in saved
    assert saved["各项"]["路径"]["状态"] == "failed" and "JSON 解析失败" in saved["各项"]["路径"]["原因"] and saved["状态"] == "partial"


def test_system_prompt_states_the_rules(tmp_path, monkeypatch):
    log = []
    run(tmp_path, monkeypatch, dict(GOOD), log=log)
    system = log[0][1]
    assert "不许编新数字" in system and "枚举只能" in system and "证据不足" in system and "只回一个 JSON" in system
    task_prompt = next(u for k, _, u in log if k == "任务"); assert all(t in task_prompt for t in llm.TASK_TYPES)
    assert "floor mat" in next(u for k, _, u in log if k == "搜索词") and "bathtub mat\"" not in next(u for k, _, u in log if k == "搜索词")   # 只送兜底分组里的词


def test_key_never_lands_on_disk_or_stdout(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path); monkeypatch.setattr(llm, "ask", fake_ask(dict(GOOD)))
    llm.fill(root, env=dict(FAKE_ENV), cfg=json.loads(json.dumps(llm.DEFAULT_CFG)))
    printed = capsys.readouterr(); blob = printed.out + printed.err
    for dirpath, _, files in os.walk(root):
        for f in files: blob += open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore").read()
    assert FAKE_ENV["ADS_LLM_KEY"] not in blob


def test_channel_down_stops_trying(tmp_path, monkeypatch):
    root = make_root(tmp_path); calls = []
    def ask(ch, system, user, max_tokens=8000): calls.append(1); raise llm.ChannelDown("超时")
    monkeypatch.setattr(llm, "ask", ask)
    doc = llm.fill(root, env=dict(FAKE_ENV), cfg=json.loads(json.dumps(llm.DEFAULT_CFG)), quiet=True)
    assert len(calls) == 1 and doc["状态"] == "skipped" and "超时" in doc["原因"]
    assert all(x["状态"] == "failed" for x in doc["各项"].values())


def test_hermes_fallback_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "HERMES_HOME", tmp_path / "no-hermes")
    cfg = json.loads(json.dumps(llm.DEFAULT_CFG)); cfg["llm"]["enabled"] = True
    ch = llm.channel(cfg, env={})
    assert not ch["ok"] and "这个 profile 还没有 API_SERVER_KEY" in ch["原因"]
    prof = tmp_path / "no-hermes" / "profiles" / "ads-agent"; prof.mkdir(parents=True); (prof / ".env").write_text("OTHER=1\nAPI_SERVER_KEY=local-test-key\n", encoding="utf-8")
    ch = llm.channel(cfg, env={})
    assert ch["ok"] and ch["base"] == "http://127.0.0.1:8642/p/ads-agent/v1" and ch["通道"] == "hermes · ads-agent" and ch["model"] == "ads-agent"


def test_channel_order_env_over_config():
    cfg = json.loads(json.dumps(llm.DEFAULT_CFG)); cfg["llm"].update({"enabled": True, "base": "https://cfg.example/v1", "model": "cfg-model", "key_env": "MY_KEY"})
    ch = llm.channel(cfg, env={"MY_KEY": "k1"})
    assert ch["ok"] and ch["base"] == "https://cfg.example/v1" and ch["model"] == "cfg-model" and ch["api"] == "openai"
    ch = llm.channel(cfg, env={"MY_KEY": "k1", "ADS_LLM_BASE": "https://env.example", "ADS_LLM_MODEL": "env-model", "ADS_LLM_API": "anthropic", "ADS_LLM_KEY": "k2"})
    assert (ch["base"], ch["model"], ch["api"], ch["key"]) == ("https://env.example", "env-model", "anthropic", "k2")
    assert "MY_KEY" in llm.channel(cfg, env={})["原因"]                             # 配了地址没给密钥：说清缺哪个环境变量，不偷偷换通道
    assert llm.channel(json.loads(json.dumps(llm.DEFAULT_CFG)), env={"MY_KEY": "k1", "OPENAI_API_KEY": "x"})["原因"] == "没接模型"


def test_dry_run_calls_nothing_and_writes_nothing(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path); monkeypatch.setattr(llm, "ask", lambda *a, **k: pytest.fail("dry-run 不该调模型"))
    plan = llm.fill(root, dry_run=True, env=dict(FAKE_ENV), cfg=json.loads(json.dumps(llm.DEFAULT_CFG)))
    assert plan["将调用"] == 5 and plan["calls"] == 0 and len(plan["计划"]) == 5
    assert not os.path.exists(os.path.join(root, "广告闭环", "输出", "AI补位.json"))
    assert "提示词" in capsys.readouterr().out


def test_only_keeps_the_rest(tmp_path, monkeypatch):
    doc, saved = run(tmp_path, monkeypatch, dict(GOOD))
    monkeypatch.setattr(llm, "ask", fake_ask({"路径": {"选": "增单", "理由": "证据不足", "不选其他的理由": "证据不足"}}))
    doc2 = llm.fill(str(tmp_path), only="路径", env=dict(FAKE_ENV), cfg=json.loads(json.dumps(llm.DEFAULT_CFG)), quiet=True)
    assert doc2["calls"] == 1 and doc2["路径建议"]["选"] == "增单" and doc2["任务标签"] == saved["任务标签"] and doc2["周报草稿"] == saved["周报草稿"]
    with pytest.raises(ValueError): llm.fill(str(tmp_path), only="不存在的项", env=dict(FAKE_ENV), quiet=True)
