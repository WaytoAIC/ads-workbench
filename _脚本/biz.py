# -*- coding: utf-8 -*-
"""经营核算（确定性：不调模型、不联网，只用标准库）。
数字.json + 参数.json + 口径.json + _原始拉取/ 的活动结构表 → 广告闭环/输出/经营.json：算账、拆解、广告任务、利润路径、决策表骨架。
结构与枚举见 docs/架构.md 第二节。规矩：每个数都能在 数字.json 或原始表里复算；比率写小数；缺数据的字段写 null，同级加「缺」（缺什么、去哪取），不填 0。
用法：ADS_ROOT=<数据目录> python3 _脚本/biz.py      render.py 跑完会自动调一次；失败时写一份带「错误」字段的 经营.json，不拦流水线。"""
import datetime, json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
usd = lambda v: f"${v:,.0f}"; pct = lambda v, n=1: f"{v*100:.{n}f}%"          # 与 pipeline.py 同一套格式
TASKS = ("纯利型", "推自然位", "测词拓词", "收割", "防守", "未判定")
LIMITS = ("库存", "CPC", "CVR", "广告销售额占比", "无效广告", "利润空间", "无明显限制")
# 口径.json 缺文件或缺键时的回退值（与 口径.json 的初始值相同）
DEFAULT = {"经营": {"默认目标广告后利润率": 0.15, "纯利型订单门槛": 10, "CPC环比涨幅警戒": 0.10, "CVR环比下滑警戒": 0.10, "无效广告花费占比警戒": 0.05,
                  "广告销售额占比警戒": 0.8, "相对目标偏低线": 0.8, "示例ACOS降幅": 0.10, "调价测算金额": 1.0},
           "判定": {"预算吃紧比例": 0.9}, "门槛": {"活动级判断点击": 30, "搜索词收割订单": 3}, "复盘": {"初查天数": 3, "决定天数": 7}}
# 四个推广阶段各自的要求（一句话）。页面上的「成长期」「成熟期」按最接近的一档读
STAGE = {"新品期": "以测试和攒数据为主，可以暂不把盈利放第一位，但要先定好测多久、最多亏到哪。",
         "放量期": "把单量推到目标规模；亏着放、平本放还是微利放，按公司给的 TACOS 上限执行。",
         "维稳期": "单量稳住的前提下改善利润：压广告成本、调订单结构，不为省钱丢规模。",
         "盈利期": "放大利润；先说清优先保利润额、利润率还是规模，再定广告投入。"}
STAGE_ALIAS = {"成长期": "放量期", "成熟期": "维稳期"}
PATHS = (("增单", "价格与 TACOS 不变，把订单做大"), ("降耗", "订单稳住，减少广告对利润的消耗"), ("调价", "调整售价"), ("重构", "重新设计价格-广告-利润的关系"))


def jread(f, default=None):
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else default


def ratio(v):
    """人填的比例：0.486、48.6、"48.6%" 都认；空或不是数返回 None。可以是 0 或负数（平本、允许亏）。"""
    if v in (None, ""): return None
    try: x = float(str(v).strip().rstrip("%"))
    except ValueError: return None
    return x / 100 if (abs(x) > 1 or str(v).strip().endswith("%")) else x


r4 = lambda v: None if v is None else round(float(v), 4)
r2 = lambda v: None if v is None else round(float(v), 2)
div = lambda a, b: None if (a is None or not b) else a / b
fp = lambda v, n=1: "缺" if v is None else pct(v, n)                        # 文字里的比率
pts = lambda d: f"{d*100:+.1f} 个点"                                        # 比率的变化：百分点
arrow = lambda xs: " → ".join(xs)


def judge(v, target, low):
    """高于目标＝偏高；低于「目标 × 偏低线」＝偏低（有余量没用上）；中间＝正常。"""
    if v is None or target is None: return None
    return "偏高" if v > target else ("偏低" if v < target * low else "正常")


class Ctx:
    """一圈经营核算用到的全部输入。"""
    def __init__(self, root):
        self.root, self.out, self.raw = root, f"{root}/广告闭环/输出", f"{root}/_原始拉取"
        self.F = jread(f"{self.out}/数字.json")
        if not self.F or not self.F.get("四周") or not self.F.get("逐周"): raise FileNotFoundError("广告闭环/输出/数字.json 不在或没有「四周」「逐周」：先跑 pipeline.py / render.py")
        self.P = jread(f"{root}/参数.json") or {}
        self.KJ = jread(f"{root}/口径.json") or jread(f"{REPO}/口径.json") or {}      # 先找数据目录，再找仓库根
        self.Y, self.W = self.F["四周"], self.F["逐周"]
        self.camps = jread(f"{self.raw}/本父体-活动.json")                              # 结构表：投放方式、日预算。没有就是 None

    def kj(self, group, key):
        v = (self.KJ.get(group) or {}).get(key)
        return DEFAULT[group][key] if v is None else v


# ---------------- 一、算账：能花多少、现在花了多少 ----------------
def suanzhang(c):
    Y, W, P, miss = c.Y, c.W, c.P, []
    gm_h, tp_h = ratio(P.get("定价毛利率")), ratio(P.get("目标广告后利润率"))
    gm = r4(gm_h if gm_h is not None else Y.get("盈亏线")); tp = r4(tp_h if tp_h is not None else c.kj("经营", "默认目标广告后利润率"))
    if gm is None: miss.append("定价毛利率：参数.json 没填，数字.json 也没有四周盈亏线；在工作台填「定价毛利率」（不含广告费的毛利率）")
    tt = r4(gm - tp) if gm is not None else None; tacos = r4(Y.get("TACOS"))
    room = r4(tt - tacos) if None not in (tt, tacos) else None
    verdict = None if None in (gm, tt, tacos) else ("已亏损" if tacos > gm else ("超出目标" if tacos > tt else "在目标内"))
    day_sales = r2(W[-1]["销售额"] / 7)
    names = set((c.F.get("活动表") or {}).get("近14天") or {})
    if c.camps and any(float(x.get("budget") or 0) for x in c.camps):
        budget = r2(sum(float(x.get("budget") or 0) for x in c.camps if x.get("state", "enabled") == "enabled" and (not names or x["name"] in names)))
    else:
        budget = r2((c.F.get("活动") or {}).get("名义日预算合计") or None)
        if budget is None: miss.append("现日预算合计：没有活动日预算；把日预算填进 活动.csv（或补 _原始拉取/本父体-活动.json）后重跑")
    stage = P.get("产品阶段"); key = STAGE_ALIAS.get(stage, stage); need = STAGE.get(key)
    if need and key != stage: need += f"（「{stage}」按{key}的要求读）"
    if not need: miss.append(f"阶段要求：产品阶段「{stage}」不在四个阶段里（{'、'.join(STAGE)}）；在工作台改「产品阶段」")
    A = {"定价毛利率": gm, "定价毛利率来源": "人填" if gm_h is not None else "数据：四周广告前毛利率",
         "目标广告后利润率": tp, "目标广告后利润率来源": "人填" if tp_h is not None else "口径默认",
         "目标TACOS": tt, "当前TACOS": tacos, "TACOS余量": room, "判定": verdict,
         "当前广告后利润率": r4(gm - tacos) if None not in (gm, tacos) else None,
         "近7天日均销售额": day_sales, "单品日预算": r2(day_sales * tt) if tt is not None else None, "现日预算合计": budget, "上周日均广告费": r2(W[-1]["广告费"] / 7),
         "阶段": stage, "阶段要求": need}
    if miss: A["缺"] = "；".join(miss)
    return A


# ---------------- 二、拆解：TACOS = ACOS × 广告销售额占比；ACOS = CPC ÷ (CVR × 客单价) ----------------
def chaijie(c, A):
    F, Y, W, P = c.F, c.Y, c.W, c.P; gm, tp, tt, tacos = A["定价毛利率"], A["目标广告后利润率"], A["目标TACOS"], A["当前TACOS"]
    ta = ratio(P.get("目标ACOS")); low = c.kj("经营", "相对目标偏低线")
    L, Pv = W[-1], (W[-2] if len(W) > 1 else None)                                 # 上周、前一周
    wow = lambda f: (None, None) if (Pv is None or f(L) is None or f(Pv) is None) else (f(L), f(L) - f(Pv))     # (上周值, 上周 − 前一周)
    # 全部广告的 ACOS 要有 SB、SBV 的归因销售额；只有 SP 销售额时退回 SP 的 ACOS，占比不给
    share = Y.get("广告归因销售额占比"); full = bool(share) and Y.get("广告销售额口径", "全部广告") == "全部广告"
    spA, spB = F.get("SP-前14天") or {}, F.get("SP-近14天") or {}
    sp = {k: sum((x.get(k) or 0) for x in (spA, spB)) for k in ("花费", "点击", "订单", "销售额")}
    if full:
        share = r4(share); acos = r4(div(Y["广告费"], Y["销售额"] * Y["广告归因销售额占比"])); acos_miss = None
        w_share = wow(lambda w: div(w.get("广告销售额"), w["销售额"])); w_acos = wow(lambda w: div(w["广告费"], w.get("广告销售额")))
    else:
        share, acos = None, r4(spB.get("ACOS") if spB.get("ACOS") is not None else div(sp["花费"], sp["销售额"]))
        acos_miss = "拿不到 SB、SBV 的广告销售额，这里是 SP 的 ACOS；在利润报表里补全部广告的归因销售额（cpcSales 含 SB、SBV）后重跑"
        w_share = (None, None); w_acos = wow(lambda w: w.get("SP_ACOS"))
    cpc, cvr, aov = r4(div(sp["花费"], sp["点击"])), r4(div(sp["订单"], sp["点击"])), r2(Y.get("均价"))
    w_tacos, w_cpc, w_cvr, w_aov = wow(lambda w: w.get("TACOS")), wow(lambda w: w.get("SP_CPC")), wow(lambda w: w.get("SP_CVR")), wow(lambda w: div(w["销售额"], w["件数"]))
    rel = lambda w: None if (w[0] is None or not (w[0] - w[1])) else w[1] / (w[0] - w[1])            # 相对前一周的涨跌幅
    cpc_up, cvr_dn, share_hi = c.kj("经营", "CPC环比涨幅警戒"), c.kj("经营", "CVR环比下滑警戒"), c.kj("经营", "广告销售额占比警戒")
    d_cpc, d_cvr = rel(w_cpc), rel(w_cvr)
    band = lambda d, up, dn: None if d is None else ("偏高" if d > up else ("偏低" if d < -dn else "正常"))

    def node(name, val, cmp_, w, change, verdict, miss=None):
        d = {"名": name, "值": val, "对比": cmp_, "上周": (r4(w[0]) if w[0] is not None else None), "变化": change, "判定": verdict}
        if w[0] is None: miss = "；".join(x for x in (miss, "上周、变化：逐周数据里没有这一项（至少要两周；全部广告的销售额要新版 pipeline.py 重跑才会写进逐周）") if x)
        if miss: d["缺"] = miss
        return d
    sp_note = "SB、SBV 没有点击数，这里是 SP 的（前后两个窗口合计）；补 SB、SBV 活动报表后才能算全部广告"
    nodes = [
        node("TACOS", tacos, f"目标 {fp(tt)}", w_tacos, (pts(w_tacos[1]) if w_tacos[1] is not None else None), judge(tacos, tt, low)),
        node("ACOS（全部广告）", acos, f"目标 {fp(ta, 0)}｜盈亏线 {fp(gm)}", w_acos, (pts(w_acos[1]) if w_acos[1] is not None else None), judge(acos, ta, low), acos_miss),
        node("广告销售额占比", share, f"警戒 {pct(share_hi, 0)}", w_share, (pts(w_share[1]) if w_share[1] is not None else None), (None if share is None else ("偏高" if share > share_hi else "正常")),
             ("只有 SP 的广告销售额，算不出全部广告的占比；去利润报表补 SB、SBV 的归因销售额" if share is None else None)),
        node("CPC", cpc, (f"前一周 ${Pv['SP_CPC']:.2f}" if Pv and Pv.get("SP_CPC") is not None else None), w_cpc, (f"{d_cpc*100:+.1f}%" if d_cpc is not None else None), band(d_cpc, cpc_up, cpc_up), sp_note),
        node("CVR", cvr, (f"前一周 {pct(Pv['SP_CVR'])}" if Pv and Pv.get("SP_CVR") is not None else None), w_cvr, (f"{pts(w_cvr[1])}（相对 {d_cvr*100:+.1f}%）" if d_cvr is not None else None), band(d_cvr, cvr_dn, cvr_dn), sp_note),
        node("客单价", aov, (f"SP 广告单均 ${sp['销售额']/sp['订单']:.2f}" if sp["订单"] else None), w_aov, (f"{rel(w_aov)*100:+.1f}%" if rel(w_aov) is not None else None), None,
             "判定：没有参照价（目标售价或竞品价），不判高低；值是四周销售额 ÷ 件数"),
    ]
    # ---- 核心限制：固定顺序，命中第一条即停 ----
    I, R = F.get("库存") or {}, (float(P["补货到仓周数"]) if P.get("补货到仓周数") not in (None, "") else 0.0)
    inv = next((a for a in F.get("异常") or [] if a.get("指标") == "库存够卖几周"), None)
    table = (F.get("活动表") or {}).get("近14天") or {}; total = sum((v.get("花费") or 0) for v in table.values()); waste_hi = c.kj("经营", "无效广告花费占比警戒")
    over = sorted(((k, v) for k, v in table.items() if gm is not None and v.get("ACOS") is not None and v["ACOS"] > gm), key=lambda kv: -kv[1]["花费"])     # ACOS 超盈亏线的活动
    big = [(k, v) for k, v in over if total and v["花费"] / total > waste_hi]
    RULE = {1: "① 库存撑不到补货到仓（数字.json 异常里「库存够卖几周」不是 good）→ 库存",
            2: "② TACOS 超过定价毛利率 → 利润空间",
            3: f"③ TACOS 超目标，且 ACOS 也高于目标 ACOS：CPC 环比涨幅超过 {pct(cpc_up, 0)} → CPC；否则转化率环比下滑超过 {pct(cvr_dn, 0)} → CVR；两个都没过线，取环比更不利的那个",
            4: "④ TACOS 超目标，但 ACOS 不高于目标 ACOS → 广告销售额占比",
            5: f"⑤ 存在 ACOS 超盈亏线、且花费占全部活动近 14 天花费超过 {pct(waste_hi, 0)} 的活动 → 无效广告",
            6: "⑥ 以上都不命中 → 无明显限制"}
    cpc_txt = f"SP 的 CPC 上周 ${w_cpc[0]:.2f}，环比 {d_cpc*100:+.1f}%" if d_cpc is not None else "CPC 没有逐周数据"
    cvr_txt = f"SP 的转化率上周 {pct(w_cvr[0])}，环比 {d_cvr*100:+.1f}%" if d_cvr is not None else "转化率没有逐周数据"
    if inv and inv.get("级别") != "good":
        var, hit = "库存", 1; why = [f"库存够卖 {inv['现值']}，{inv['参照']}", inv.get("说明") or ""]
        if I.get("将断货SKU"): why.append("将断货：" + "、".join(f"{x['SKU']}（上周卖 {x['上周销量']}，可售 {x['可售']}）" for x in I["将断货SKU"]))
    elif None not in (tacos, gm) and tacos > gm:
        var, hit = "利润空间", 2; why = [f"TACOS {pct(tacos)} 高于定价毛利率 {pct(gm)}：广告费把毛利吃完了", f"当前广告后利润率 {pct(gm - tacos)}，目标 {pct(tp)}"]
    elif None not in (tacos, tt) and tacos > tt and None not in (acos, ta) and acos > ta:
        hit = 3; var = "CPC" if (d_cpc is not None and d_cpc > cpc_up) else ("CVR" if (d_cvr is not None and -d_cvr > cvr_dn) else ("CPC" if (d_cpc or 0) >= -(d_cvr or 0) else "CVR"))
        why = [f"TACOS {pct(tacos)} 超目标 {pct(tt)}，ACOS {pct(acos)} 也高于目标 {pct(ta, 0)}", cpc_txt, cvr_txt]
    elif None not in (tacos, tt) and tacos > tt:
        var, hit = "广告销售额占比", 4
        why = [f"TACOS {pct(tacos)} 超目标 {pct(tt)}，但 ACOS {fp(acos)} " + (f"不高于目标 {pct(ta, 0)}" if None not in (acos, ta) else "和目标 ACOS 比不了（缺其中一个）"),
               (f"广告销售额占比 {pct(share)}：广告效率不差，是太多销售额要靠广告买" if share is not None else "广告销售额占比算不出（只有 SP 的广告销售额）")]
    elif big:
        var, hit = "无效广告", 5; why = [f"{k}：ACOS {pct(v['ACOS'])} 超盈亏线 {pct(gm)}，近 14 天花 {usd(v['花费'])}，占全部活动花费 {pct(v['花费'] / total)}" for k, v in big]
    else:
        var, hit = "无明显限制", 6
        why = [(f"库存够卖 {inv['现值']}，{inv['参照']}" if inv else "数字.json 里没有库存这一项，库存没判"),
               (f"TACOS {pct(tacos)} 在目标 {pct(tt)} 内，余量 {pts(tt - tacos)[1:]}" if None not in (tt, tacos) else "TACOS 或目标 TACOS 缺，超没超目标判不了"),
               (f"ACOS 超盈亏线的活动 {len(over)} 个，单个花费占比都不到 {pct(waste_hi, 0)}" if over else "没有 ACOS 超盈亏线的活动")]
    limit = {"变量": var, "规则": RULE[hit], "依据": [x for x in why if x]}
    # ---- 归因路径：按命中的限制选入口，逐层下钻 ----
    units = arrow(str(w["件数"]) for w in W); wow_units = (F.get("末周环比") or {}).get("件数"); sh = share
    if var == "库存":
        entry = "销量超预期"
        steps = [f"件数逐周 {units}" + (f"，末周环比 {wow_units:+.0%}" if wow_units is not None else "") + "：卖得比备货快",
                 (f"自然还是广告：广告销售额占比四周 {pct(sh)}" + (f"、上周 {pct(w_share[0])}" if w_share[0] is not None else "") + ("，销售额主要是广告买来的" if sh > 0.5 else "，销售额主要来自自然单") if sh is not None else "自然还是广告：算不出广告销售额占比（缺 SB、SBV 的归因销售额）"),
                 f"库存：整体可售 {I.get('整体可售周数', 0):.1f} 周，补货到仓要 {float(R):g} 周" + (f"；将断货的 SKU 占上周件数 {pct(I['将断货占上周件数'], 0)}" if I.get("将断货占上周件数") is not None else ""),
                 (f"广告还挂在将断货的规格上：断货后同样的广告费换不来单，等效 ACOS 约 {pct(F['断货后等效ACOS'], 0)}（盈亏线 {fp(gm)}）" if F.get("断货后等效ACOS") is not None else ""),
                 "定位到动作：先保主力规格（将断货的暂停或降预算，同规格库存足的补挂），到仓前不加预算、不提竞价"]
    elif var == "无明显限制":
        entry = "单量低于预期"
        steps = [f"没有单量目标可比（缺：目标日销，人定）；先看还能不能多卖：件数逐周 {units}" + (f"，末周环比 {wow_units:+.0%}" if wow_units is not None else ""),
                 f"转化还是流量：{cvr_txt}" + (f"；点击率上周 {pct(L['SP_CTR'], 2)}" if L.get("SP_CTR") is not None else ""),
                 (f"广告还是自然：广告销售额占比 {pct(sh)}，自然部分约 {pct(max(0, 1 - sh))}" if sh is not None else "广告还是自然：算不出广告销售额占比（缺 SB、SBV 的归因销售额）"),
                 f"效率够不够买更多：ACOS {fp(acos)}，目标 TACOS {fp(tt)}" + (f"，TACOS 余量 {pts(tt - tacos)[1:]}" if None not in (tt, tacos) else ""),
                 "定位：词不够还是位置不够，要看核心词自然排名（缺，需关键词工具）；现在能确定的是纯利型候选活动可以先放量"]
    else:
        entry = "利润率差"
        last = {"CPC": "定位：点击变贵是主因 → 查竞价和广告位加价，先降 ACOS 超盈亏线的投放",
                "CVR": "定位：转化下滑是主因 → 查价格、评价、主图和有没有断码",
                "广告销售额占比": "定位：广告效率不差，但太多销售额要靠广告买 → 看自然单能不能补、哪些广告的任务已经完成可以撤",
                "无效广告": "定位：" + "、".join(k for k, _ in big) + " 的 ACOS 超盈亏线 → 先处理这些活动，再看整体",
                "利润空间": "定位：TACOS 已经高于定价毛利率，只调广告补不回来 → 回到价格、广告、利润的关系重新设计"}[var]
        steps = [f"广告后利润率 {fp(A['当前广告后利润率'])}，目标 {fp(tp)}" + (f"，差 {pts(A['当前广告后利润率'] - tp)}" if A["当前广告后利润率"] is not None else ""),
                 f"哪块费用：TACOS {fp(tacos)}，目标 {fp(tt)}（定价毛利率 {fp(gm)}）",
                 f"获单成本高还是广告单占比高：ACOS {fp(acos)}（目标 {fp(ta, 0)}）；广告销售额占比 {fp(sh)}",
                 f"转化低还是点击贵：{cpc_txt}；{cvr_txt}", last]
    D = {"公式": ["TACOS = ACOS × 广告销售额占比", "ACOS = CPC ÷ (CVR × 客单价)"], "变化口径": "「上周」是最近一周，「变化」是上周比前一周；「值」是四周合计口径（CPC、CVR 是 SP 两个窗口合计）",
         "节点": nodes, "核心限制": limit, "归因路径": {"入口": entry, "步骤": [x for x in steps if x]}}
    return D, {"acos": acos, "share": share, "ta": ta, "over": over, "total": total, "w_share": w_share, "R": R}


# ---------------- 三、任务：每个活动在干什么、干成了没有 ----------------
def renwu(c, A):
    F, P = c.F, c.P; gm, tt = A["定价毛利率"], A["目标TACOS"]; T = F.get("活动表") or {}
    b14, a14, b7 = T.get("近14天") or {}, T.get("前14天") or {}, T.get("近7天")
    names = sorted(b14, key=lambda k: -(b14[k].get("花费") or 0)) + [n for n in a14 if n not in b14]
    if not names: return [], "任务：数字.json 里没有「活动表」（或是空的），没法逐个活动判任务；确认活动报告或搜索词报告在 _原始拉取/ 后重跑 pipeline.py"
    camps = {x["name"]: x for x in (c.camps or [])}; cid = {str(x["campaignId"]): x["name"] for x in (c.camps or [])}
    kws = {}
    for k in jread(f"{c.raw}/本父体-spKeyword.json") or []:
        if str(k.get("campaignId")) in cid: kws.setdefault(cid[str(k["campaignId"])], []).append(k)
    kids = jread(f"{c.raw}/在线产品-本父体.json") or [{}]; brand = (kids[0].get("brand") or kids[0].get("amazonBrand") or "").strip().lower()
    terms = F.get("活动搜索词-近14天")
    n_pure, n_term, n_click, tight = c.kj("经营", "纯利型订单门槛"), c.kj("门槛", "搜索词收割订单"), c.kj("门槛", "活动级判断点击"), c.kj("判定", "预算吃紧比例")
    trunk = [x for x in (P.get("词组活动"), P.get("广泛活动")) if x] + [x for x in (P.get("主干活动") or []) if x != P.get("精确活动")]
    human = jread(f"{c.root}/广告闭环/输入/活动任务.json") or {}          # 人在页面确认过的任务（工作台从状态库写出来）：完成情况按人定的判
    rows = []
    for name in names:
        p = b14.get(name) or {}; acos, od, ck, spend = p.get("ACOS"), int(p.get("订单") or 0), int(p.get("点击") or 0), float(p.get("花费") or 0)
        perf = f"近 14 天 {od} 单、ACOS {fp(acos)}" if p else "近 14 天没有花费"
        not_pure = "" if not p else (f"ACOS 不低于目标 TACOS {fp(tt)}" if (acos is None or tt is None or acos >= tt) else f"订单不到 {n_pure:g} 单")
        st = camps.get(name) or {}; auto = (st.get("targetingType") == "auto") if st else ("自动" in name or "auto" in name.lower())
        manual_kw = any(k.get("matchType") in ("phrase", "broad") for k in kws.get(name, []))
        miss = None
        tail = f"（{not_pure}，不算纯利型）" if not_pure else ""
        if None not in (acos, tt) and acos < tt and od >= n_pure: task, why = "纯利型", f"ACOS {pct(acos)} 低于目标 TACOS {pct(tt)}，近 14 天 {od} 单"
        elif auto: task, why = "测词拓词", f"投放方式是自动；{perf}{tail}"
        elif name == P.get("精确活动"): task, why = "收割", f"参数.json 指定的精确活动；{perf}{tail}"
        elif brand and (brand in name.lower() or any(brand in str(k.get("keywordText", "")).lower() for k in kws.get(name, []))): task, why = "防守", f"活动名或关键词含自家品牌词「{brand}」；{perf}"
        elif name in trunk and (manual_kw or name not in kws) and None not in (acos, gm) and acos <= gm: task, why = "推自然位", f"词组／广泛主干，ACOS {pct(acos)} 在盈亏线 {pct(gm)} 内；{perf}"
        else: task, why = "未判定", f"不是自动、精确收割、品牌防守，也不是盈亏线内的词组／广泛主干；{perf}" + (f"（{not_pure}）" if not_pure else "")
        # 完成情况（人确认过任务的，按人定的判；建议任务仍是脚本的）
        eff = (human.get(name) or {}).get("任务") or task
        if eff == "纯利型":
            p7 = (b7 or {}).get(name)
            if tt is None or (b7 is None and acos is None): done, how = "看不出", "缺目标 TACOS 或这个活动的 ACOS"
            elif b7 is None: done = "达标" if acos < tt else "未达标"; how = f"数字.json 没有近 7 天活动表，按近 14 天判：ACOS {pct(acos)}"
            elif p7 and p7.get("ACOS") is not None: done = "达标" if p7["ACOS"] < tt else "未达标"; how = f"近 7 天 ACOS {pct(p7['ACOS'])} {'仍低于' if done == '达标' else '已不低于'}目标 TACOS {pct(tt)}"
            else: done, how = "看不出", "近 7 天没有出单"
        elif eff == "测词拓词":
            if terms is None: done, how, miss = "看不出", "数字.json 里没有每个活动的出单搜索词", "活动搜索词-近14天：重跑 pipeline.py（新版会写这个键）"
            else:
                hit = [x for x in (terms.get(name) or {}).get("按订单前五", []) if x["订单"] >= n_term]
                done = "达标" if hit else "未达标"
                how = (f"近 14 天产出了订单 ≥{n_term:g} 的搜索词：" + "、".join(f"{x['词']}（{x['订单']} 单）" for x in hit[:3])) if hit else f"近 14 天没有产出订单 ≥{n_term:g} 的搜索词"
        else:
            done = "看不出"
            how, miss = {"收割": ("脚本只到活动层", "精确词各自的 ACOS 和自然排名（需关键词工具）"), "防守": ("脚本只到活动层", "品牌词搜索结果页的占位情况（需关键词工具）"),
                         "推自然位": ("自然位有没有涨，报表里看不到", "核心词自然排名（需关键词工具，付费，未查）"), "未判定": ("任务还没定", "人在页面确认这个活动的任务")}[eff]
        if not p: done, how = "看不出", "近 14 天没有花费"
        if (None not in (acos, gm) and acos > gm and ck >= n_click) or (p and od == 0 and ck >= n_click):          # 不管什么任务：亏着跑且样本够了，就是没完成
            done = "未达标"; how = (f"ACOS {pct(acos)} 超盈亏线 {pct(gm)}" if acos is not None else "0 单") + f"，近 14 天 {ck} 次点击，样本够了"
        marks = (["纯利型候选"] if task == "纯利型" else []) + (["任务没完成"] if done == "未达标" else [])
        bud = float(st.get("budget") or 0); per_day = (b7[name]["花费"] / 7 if (b7 and name in b7) else spend / 14)
        if bud and per_day >= tight * bud: marks.append("预算吃紧"); how += f"；日均花 {usd(per_day)}＝日预算 {usd(bud)} 的 {pct(per_day / bud, 0)}"
        row = {"活动": name, "建议任务": task, "依据": why, "完成情况": done, "完成依据": how, "标记": marks}
        if eff != task: row["人定任务"] = eff
        if miss: row["缺"] = miss
        rows.append(row)
    return rows, None


# ---------------- 四、路径：四条候选各自适不适用，带测算 ----------------
def lujing(c, A, D, X, tasks):
    F, W = c.F, c.W; gm, tp, tt, tacos, after = A["定价毛利率"], A["目标广告后利润率"], A["目标TACOS"], A["当前TACOS"], A["当前广告后利润率"]
    var, acos, share = D["核心限制"]["变量"], X["acos"], X["share"]; I = F.get("库存") or {}
    over_t = None not in (tacos, tt) and tacos > tt
    # 增单：目标 TACOS ÷ ACOS ＝ 广告在目标内最多能承担的订单占比
    drop = c.kj("经营", "示例ACOS降幅"); s = None if (acos is None or tt is None or acos <= 0) else min(1.0, max(0.0, tt / acos))
    acos2 = acos * (1 - drop) if acos is not None else None; s2 = None if (acos2 is None or tt is None or acos2 <= 0) else min(1.0, max(0.0, tt / acos2))
    sh_w = X["w_share"][0] if X["w_share"][0] is not None else share; units = W[-1].get("件数")
    ad_n = round(units * min(1.0, sh_w)) if None not in (units, sh_w) else None; nat_n = units - ad_n if ad_n is not None else None
    cap = lambda s_: None if (s_ is None or nat_n is None or s_ >= 1) else round(nat_n * s_ / (1 - s_))            # 自然单不变时，目标内最多买多少广告单
    m1 = {"当前ACOS": acos, "目标TACOS": tt, "广告可承担订单占比": r4(s), "现广告单": ad_n, "现自然单": nat_n, "目标内广告单上限": cap(s),
          "示例ACOS降幅": drop, "降后ACOS": r4(acos2), "降后广告可承担订单占比": r4(s2), "降后目标内广告单上限": cap(s2),
          "可多承担广告单": (cap(s2) - cap(s) if None not in (cap(s), cap(s2)) else None), "口径": "订单按上周件数近似，广告单＝上周件数 × 上周广告销售额占比（封顶 100%）；上限＝自然单不变时的算法"}
    gaps = []
    if ad_n is None: gaps.append("现广告单、现自然单：缺广告销售额占比（要 SB、SBV 的归因销售额）")
    if s is not None and s >= 1: gaps.append("目标内广告单上限：不用算，ACOS 低于目标 TACOS 时每个广告单都在目标内，广告单占比不设上限，能多买多少看流量和库存")
    elif m1["可多承担广告单"] is None and s is not None and s2 is not None and s2 >= 1: gaps.append("可多承担广告单：ACOS 降到示例值后已低于目标 TACOS，不再有上限")
    if s is None: gaps.append("广告可承担订单占比：缺 ACOS 或目标 TACOS")
    if gaps: m1["缺"] = "；".join(gaps)
    ok1 = var not in ("库存", "利润空间") and tacos is not None and tt is not None and not over_t
    if var == "库存": why1 = f"整体可售 {I.get('整体可售周数', 0):.1f} 周撑不到补货到仓（{float(X['R']):g} 周），现在增单只会更早断货"
    elif over_t or var == "利润空间": why1 = f"TACOS {fp(tacos)} 已超目标 {fp(tt)}，先把广告对利润的消耗降下来"
    elif not ok1: why1 = "缺 TACOS 或目标 TACOS，判不了"
    else: why1 = f"TACOS {pct(tacos)} 低于目标 {pct(tt)}，还有 {pts(tt - tacos)[1:]}余量；" + ("ACOS 或目标 TACOS 缺，算不出广告能承担多少" if s is None else f"ACOS {pct(acos)} 低于目标 TACOS，每个广告单都在目标内，可以直接多买" if s >= 1 else f"按目标 TACOS ÷ ACOS，广告最多承担 {pct(s, 0)} 的订单，其余要靠自然单")
    # 降耗：ACOS 超盈亏线、或有点击没出单的活动，花的钱算无效
    table = (F.get("活动表") or {}).get("近14天") or {}; total = X["total"]; waste_hi = c.kj("经营", "无效广告花费占比警戒")
    bad = sorted([k for k, v in table.items() if (gm is not None and v.get("ACOS") is not None and v["ACOS"] > gm) or (not v.get("订单") and (v.get("花费") or 0) > 0)], key=lambda k: -table[k]["花费"])
    waste = r2(sum(table[k]["花费"] for k in bad)) if table else None; sales14 = sum(w["销售额"] for w in W[-2:]) if len(W) >= 2 else None
    m2 = {"无效广告活动": bad if table else None, "无效广告花费": waste, "占全部活动花费": r4(div(waste, total)), "清掉后TACOS可降": r4(div(waste, sales14)),
          "口径": "活动表近 14 天里 ACOS 超盈亏线或 0 单的活动；可降幅度＝无效花费 ÷ 最近两周销售额，假设销售额不变，是上限"}
    if not table: m2["缺"] = "无效广告活动、无效广告花费：数字.json 里没有「活动表」"
    ok2 = over_t or var in ("CPC", "CVR", "无效广告", "广告销售额占比") or bool(total and waste and waste / total >= waste_hi)
    fact2 = (f"ACOS 超盈亏线或 0 单的活动 {len(bad)} 个、近 14 天花 {usd(waste)}（占 {pct(waste / total)}），清掉最多降 {pts(waste / sales14)[1:]}" if (bad and total and sales14) else "没有 ACOS 超盈亏线或 0 单的活动" if table else "缺活动表，算不出无效花费")
    why2 = (f"TACOS {fp(tacos)} 超目标 {fp(tt)}；" if over_t else f"TACOS {fp(tacos)} 在目标 {fp(tt)} 内；") + fact2 + ("" if ok2 else "，不是当务之急")
    # 调价：每件提价 X 美元，成本和销量不变时广告后利润率变多少
    up = float(c.kj("经营", "调价测算金额")); price = c.Y.get("均价")
    if None in (price, gm, tacos): m3 = {"客单价": r2(price), "提价金额": up, "提价后广告后利润率": None, "对广告后利润率的影响": None, "价格弹性": "未知", "缺": "提价后广告后利润率：缺客单价、定价毛利率或 TACOS"}
    else:
        new_after = (gm * price + up) / (price + up) - tacos * price / (price + up)
        m3 = {"客单价": r2(price), "提价金额": up, "提价后客单价": r2(price + up), "提价后广告后利润率": r4(new_after), "对广告后利润率的影响": r4(new_after - after), "价格弹性": "未知",
              "口径": "假设销量、广告费、单件成本都不变，多收的钱全部进毛利（没扣随售价变的佣金）；价格弹性未知，是上限"}
    ok3 = over_t
    why3 = (f"广告后利润率 {fp(after)} 低于目标 {fp(tp)}：自然单和 ACOS 都不好动时，可以小步测价" if ok3 else f"广告后利润率 {fp(after)} 已到目标 {fp(tp)}，不靠调价补利润") + \
           (f"；每件提 {usd(up)}，广告后利润率约 {pts(m3['对广告后利润率的影响'])}" if m3.get("对广告后利润率的影响") is not None else "") + "（价格弹性未知）"
    # 重构：只有 TACOS 高过定价毛利率、或销售额几乎都靠广告买时才谈
    share_hi = c.kj("经营", "广告销售额占比警戒"); lose = None not in (tacos, gm) and tacos > gm; heavy = share is not None and share > share_hi
    m4 = {"当前TACOS": tacos, "定价毛利率": gm, "广告销售额占比": share, "广告销售额占比警戒": share_hi}
    if None in (tacos, gm, share): m4["缺"] = "；".join(x for x in (("广告销售额占比：只有 SP 的广告销售额，去利润报表补 SB、SBV 的归因销售额" if share is None else ""), ("定价毛利率或 TACOS：见「算账」里的缺" if None in (tacos, gm) else "")) if x)
    why4 = (f"TACOS {pct(tacos)} 高于定价毛利率 {pct(gm)}，现在的价格和广告投入撑不起利润" if lose else
            f"广告销售额占比 {pct(share)} 超过 {pct(share_hi, 0)}：销售额几乎都要靠广告买（SB、SBV 归因口径宽，这个数是上限）" if heavy else
            f"TACOS {fp(tacos)} 没超过定价毛利率 {fp(gm)}，广告销售额占比 {fp(share)} 也没超过 {pct(share_hi, 0)}，现在的盈利模式还成立")
    cands = [dict(zip(("key", "名"), kn), 适用=bool(ok), 理由=why, 测算=m) for kn, ok, why, m in zip(PATHS, (ok1, ok2, ok3, lose or heavy), (why1, why2, why3, why4), (m1, m2, m3, m4))]
    if var == "库存": pick, basis = "先解决库存", "核心限制是库存：断货前谈增单、降耗都落不了地"
    elif var == "利润空间": pick, basis = "重构", "核心限制是利润空间：TACOS 高过定价毛利率"
    elif var in ("CPC", "CVR", "无效广告", "广告销售额占比"): pick, basis = "降耗", f"核心限制是{var}：先减少广告对利润的消耗"
    elif A["TACOS余量"] is not None and A["TACOS余量"] > 0: pick, basis = "增单", f"没有明显限制，TACOS 还有 {pts(A['TACOS余量'])[1:]}余量"
    else: pick, basis = "降耗", "没有明显限制，但 TACOS 没有余量（或算不出余量）"
    return {"候选": cands, "脚本建议": pick, "建议依据": basis}


# ---------------- 五、决策表：九栏一句话骨架（首要目标留给人） ----------------
def juece(c, A, D, X, tasks, R_):
    F, W, P = c.F, c.W, c.P; I = F.get("库存") or {}; pick, lim = R_["脚本建议"], D["核心限制"]; tt, gm, tacos = A["目标TACOS"], A["定价毛利率"], A["当前TACOS"]
    by = lambda t: [x["活动"] for x in tasks if x["建议任务"] == t]; undone = [x["活动"] for x in tasks if "任务没完成" in x["标记"]]; tightc = [x["活动"] for x in tasks if "预算吃紧" in x["标记"]]
    few = lambda xs, n=3: "、".join(xs[:n]) + (" 等" if len(xs) > n else "")
    L = W[-1]; price = div(L["销售额"], L["件数"])
    state = f"{A['阶段'] or '阶段未填'}；上周 {L['件数']} 件、均价 ${price or 0:.2f}；定价毛利率 {fp(gm)}（{A['定价毛利率来源']}）；TACOS {fp(tacos)}（目标 {fp(tt)}，{A['判定'] or '判不了'}）；ACOS {fp(X['acos'])}；广告销售额占比 {fp(X['share'])}"
    risk = "、".join(x["SKU"] for x in I.get("将断货SKU") or []) or "将断货的 SKU"
    task_line = "；".join(x for x in ((f"纯利型候选 {len(by('纯利型'))} 个（{few(by('纯利型'))}）" if by("纯利型") else ""), (f"任务没完成 {len(undone)} 个（{few(undone)}）" if undone else ""), (f"预算吃紧 {len(tightc)} 个（{few(tightc)}）" if tightc else "")) if x) or "活动任务还没判出来"
    direction = {"先解决库存": "先保住不断货，再谈增单还是降耗", "增单": "TACOS 有余量：纯利型广告放量，同时找自然单增量", "降耗": "订单稳住，改善广告效率、清掉没完成任务的花费", "重构": "重新设计价格、广告、利润的关系（提毛利换广告空间，或让利给售价换自然成交）", "调价": "小步测价"}[pick]
    plan = {"先解决库存": f"{risk} 先暂停或降预算，同规格库存足的补挂；{task_line}。逐条动作见动作清单，人确认后才执行",
            "增单": f"{task_line}；纯利型候选在目标 TACOS 内加预算，预算吃紧的先加。逐条动作见动作清单，人确认后才执行",
            "降耗": f"{task_line}；任务没完成的先降竞价或暂停，纯利型的不动。逐条动作见动作清单，人确认后才执行",
            "重构": f"先算两套账：提价后的定价毛利率和可给广告的比例、降价后的自然成交能不能补上；{task_line}"}.get(pick, task_line)
    bound = (f"单品日预算 {usd(A['单品日预算'])}（近 7 天日均销售额 {usd(A['近7天日均销售额'])} × 目标 TACOS {pct(tt)}）" if A["单品日预算"] is not None else "单品日预算算不出（缺目标 TACOS）") + \
            f"；现日预算合计 {usd(A['现日预算合计']) if A['现日预算合计'] is not None else '缺'}，上周日均广告费 {usd(A['上周日均广告费'])}；TACOS 不超过目标 {fp(tt)}，底线是定价毛利率 {fp(gm)}"
    check = {"先解决库存": f"整体可售周数从 {I.get('整体可售周数', 0):.1f} 周回到不低于补货到仓的 {float(X['R']):g} 周" + (f"，将断货 SKU 占上周件数从 {pct(I['将断货占上周件数'], 0)} 降下来" if I.get("将断货占上周件数") is not None else "") + f"；期间 TACOS 不超过 {fp(tt)}",
             "增单": f"周件数比上周的 {L['件数']} 件多，同时 TACOS 仍不超过 {fp(tt)}、纯利型活动的 ACOS 仍低于目标 TACOS",
             "降耗": f"TACOS 从 {fp(tacos)} 降到不超过 {fp(tt)}，周件数不比上周的 {L['件数']} 件明显少",
             "重构": f"新价格下 TACOS 回到定价毛利率以内，广告后利润率不低于 {fp(A['目标广告后利润率'])}"}.get(pick, "")
    d1, d2 = int(c.kj("复盘", "初查天数")), int(c.kj("复盘", "决定天数"))
    try: t0 = datetime.date.fromisoformat(str(P.get("今天"))); on = lambda n: f"（{t0 + datetime.timedelta(days=n):%m-%d}）"
    except ValueError: on = lambda n: ""
    review = f"执行后第 {d1} 天初查{on(d1)}：只看花费、点击有没有按预期变，不下结论；第 {d2} 天决定继续、调整还是停{on(d2)}" + (f"；本轮复盘日 {P['复盘日']}" if P.get("复盘日") else "")
    nxt = {"先解决库存": "库存接上了：按 TACOS 余量转去增单；接不上：继续压将断货规格的广告，推广目标服从库存",
           "增单": "有效：继续给纯利型活动加预算，一次一档；TACOS 冲过目标：撤回最后一次加的预算，改走降耗",
           "降耗": "有效：省下的钱先不花回去，稳两周再定；件数掉得多：撤回动作（都可逆），改查自然单为什么没接住",
           "重构": "新模型成立：按新的目标 TACOS 重排预算；不成立：退回原价，改走降耗"}.get(pick, "")
    return {"当前状态": state, "首要目标": f"（人定）脚本建议供参考：{pick}", "核心限制": f"{lim['变量']}：{lim['依据'][0] if lim['依据'] else ''}", "选择方向": direction + "（脚本建议，待人定）",
            "执行方案": plan, "投入边界": bound, "验证标准": check, "复盘时间": review, "后续选择": nxt}


def build(root):
    c = Ctx(root); A = suanzhang(c); D, X = chaijie(c, A); tasks, miss = renwu(c, A); R_ = lujing(c, A, D, X, tasks)
    B = {"写入方": "脚本", "生成于": str(c.P.get("今天") or datetime.date.today()), "算账": A, "拆解": D, "任务": tasks, "路径": R_, "决策表": juece(c, A, D, X, tasks, R_)}
    if miss: B["缺"] = miss
    return B


def run(root):
    """算一遍并写 经营.json；出错就写一份带「错误」字段的，返回 (是否成功, 内容)。不抛异常。"""
    out = f"{root}/广告闭环/输出"; os.makedirs(out, exist_ok=True)
    try: B, ok = build(root), True
    except Exception as e:                                                   # 经营核算是流水线之后的附加步骤：出错只留痕，不拦前面的结果
        B, ok = {"写入方": "脚本", "生成于": str(datetime.date.today()), "错误": f"{type(e).__name__}: {e}"}, False
        print(f"⚠ 经营核算失败（不影响动作清单）：{B['错误']}", file=sys.stderr)
    json.dump(B, open(f"{out}/经营.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return ok, B


if __name__ == "__main__":
    ROOT = os.environ.get("ADS_ROOT") or REPO
    ok, B = run(ROOT)
    if not ok: sys.exit(1)
    A, cnt = B["算账"], {}
    for x in B["任务"]: cnt[x["建议任务"]] = cnt.get(x["建议任务"], 0) + 1
    print(f"经营核算｜定价毛利率 {fp(A['定价毛利率'])}（{A['定价毛利率来源']}）｜目标 TACOS {fp(A['目标TACOS'])}｜当前 {fp(A['当前TACOS'])}（{A['判定']}）｜核心限制 {B['拆解']['核心限制']['变量']}｜脚本建议 {B['路径']['脚本建议']}")
    print("  任务：" + ("、".join(f"{k} {v}" for k, v in cnt.items()) or B.get("缺", "无")) + f" → {ROOT}/广告闭环/输出/经营.json")
