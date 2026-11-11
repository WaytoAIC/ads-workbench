#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归因：把「发现的问题」拆到是谁造成的，把每条「分析」的证据摆成正反两面。  → 广告闭环/输出/归因.json
只用标准库、不调模型、不联网；读 数字.json、库存与动销-按SKU.json、动作清单.json、选项.json、诊断-三栏表.md。
三层：
  问题：每个问题一张「是谁造成的」表（按渠道 / 活动 / 词组 / 规格 / 原因拆），加一句读法和涉及的钱。
  分析：每条分析的支持证据、反对证据、最多能解释这个问题的多少、把握几成、还缺什么数据。
  对策：它靠哪几条分析站住、其中最弱的一条把握如何、这一轮落成多少动作、涉及多少钱。
规矩：每个数都能在 数字.json 或原始表里复算；算不了的写 null 加「缺」，不填 0；这里只摆证据，不替人下结论。
用法：ADS_ROOT=<数据目录> python3 _脚本/attribution.py     （render.py 结尾也会调它；它失败不影响别的产物）"""
import datetime, json, math, os, sys

pct = lambda v, n=1: "—" if v is None else f"{v * 100:.{n}f}%"
usd = lambda v: "—" if v is None else f"${v:,.0f}"
pts = lambda v: "—" if v is None else f"{v * 100:+.1f} 个点"
sgn = lambda v: "—" if v is None else f"{'+' if v >= 0 else '−'}${abs(v):,.0f}"


def jread(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError): return d


def facts_text(root):
    """三栏表里编了号的事实原文（第 6 条「否词没否干净」只有文字）。"""
    out = {}
    try:
        on = False
        for line in open(f"{root}/广告闭环/输出/诊断-三栏表.md", encoding="utf-8"):
            if line.startswith("## "): on = "事实" in line; continue
            if on and line[:1].isdigit() and ". " in line[:4]: out[int(line.split(".", 1)[0])] = line.split(". ", 1)[1].strip().replace("**", "")
    except OSError: pass
    return out


def table(title, cols, rows, read, note=None, fmt=None, bar=None):
    """fmt：列名 → 钱｜钱±｜比例｜点｜数±｜周（没写的原样显示）；bar：哪一列旁边画条。页面照这个画，不自己猜。"""
    return {"标题": title, "列": cols, "行": rows, "读法": read, "格式": fmt or {}, **({"条": bar} if bar else {}), **({"口径": note} if note else {})}


# ------------------------------------------------------------------ 问题层
def q_stock(F, inv):
    I = F["库存"]; tw = sum(r[5] for r in inv) or 1; ad = sum(r[8] or 0 for r in inv)
    risk = [r for r in inv if r[6] is not None and r[6] < 1 and r[5] > 0]; soon = [r for r in inv if r[6] is not None and 1 <= r[6] < 2 and r[5] > 0]
    rows = [{"名": r[0], "上周卖": r[5], "占件数": r[5] / tw, "可售": r[1], "够卖几周": r[6], "上上周卖": r[4], "上周广告费": r[8], "标": ("将断货" if r in risk else "两周内断" if r in soon else "")}
            for r in sorted(inv, key=lambda r: -(r[5] or 0))[:10]]
    rad = sum(r[8] or 0 for r in risk)
    read = (f"撑不到 1 周的 {len(risk)} 个规格占上周件数 {pct(sum(r[5] for r in risk) / tw, 0)}；它们上周吃掉 {usd(rad)} 广告费，占按规格记账的广告费 {pct(rad / ad, 0) if ad else '—'}。"
            + (f"其中 {max(risk, key=lambda r: r[8] or 0)[0]} 一个规格就花了 {usd(max(r[8] or 0 for r in risk))}。" if risk else ""))
    return {"涉及金额": rad or None, "金额说明": "将断货规格上周的广告费（按规格记账）", "表": [table("按规格：谁快断了、广告还在不在它身上", ["规格", "上周卖", "占件数", "可售", "够卖几周", "上上周卖", "上周广告费", ""], rows, read,
            "上周广告费是广告报表里记在这个规格名下的花费，合计比利润表的广告费少一点（有的花费记不到规格）", {"占件数": "比例", "够卖几周": "周", "上周广告费": "钱"}, "上周广告费")]}


def q_refund(F, inv):
    W = F["逐周"]; tot = sum(r[7] or 0 for r in inv) or 0
    rows = [{"名": r[0], "上周退款": r[7], "上周卖": r[5], "退款率": (r[7] / r[5] if r[5] else None), "占退款": (r[7] / tot if tot else None)} for r in sorted(inv, key=lambda r: -(r[7] or 0))[:8] if r[7]]
    top3 = sum(x["上周退款"] for x in rows[:3]); n = F.get("已退回件") or 0
    reasons = [{"名": k, "件": v, "占比": v / n} for k, v in (F.get("退货原因") or [])] if n else []
    out = [table("按周：退款率怎么走的", ["周", "件数", "退款件", "退款率"], [{"名": w["周"], "件数": w["件数"], "退款件": w["退款件"], "退款率": w["退款率"]} for w in W],
                 f"退款率 {' → '.join(pct(w['退款率']) for w in W)}；退款晚于销售 1–2 周，前几周卖出的量现在才退回来，末周的率会被抬高。", None, {"退款率": "比例"}, "退款率")]
    if rows: out.append(table("按规格：退款集中在谁身上", ["规格", "上周退款", "上周卖", "退款率", "占退款"], rows, f"退款最多的 3 个规格占全部退款的 {pct(top3 / tot, 0)}。", "按规格的退款件是库存表口径，和利润表的退款件不是同一个数", {"退款率": "比例", "占退款": "比例"}, "占退款"))
    if reasons: out.append(table("按原因：买家退货时选的理由", ["原因", "件", "占比"], reasons, f"已退回的 {n} 件里，{pct(reasons[0]['占比'], 0)} 选的是「{reasons[0]['名']}」。样本只有 {n} 件。", None, {"占比": "比例"}, "占比"))
    return {"涉及金额": None, "金额说明": "退款的钱不在广告报表里，这里不折算", "表": out}


def q_dup(F):
    D = F["同词多活动"]; L = F.get("头部词分道") or []; tot = sum(x["花费"] for x in L) or 1
    rows = [{"名": x["广告活动"], "花费": x["花费"], "占头部词花费": x["花费"] / tot, "订单": x["订单"], "ACOS": x["ACOS"]} for x in L]
    solid = [x for x in L if x["花费"] / tot >= 0.1] or L                      # 花费太小的活动 ACOS 不稳，不拿来比
    best = min(solid, key=lambda x: x["ACOS"]) if L else None; big = L[0] if L else None
    read = (f"头部 {len(F.get('头部词') or [])} 个词近 14 天花了 {usd(F.get('头部词花费'))}，分散在 {len(L)} 个活动里：「{big['广告活动']}」接了 {pct(big['花费'] / tot, 0)}，精确组只接了 {pct(F.get('精确组占头部词花费'))}。"
            + (f"接得多的几个活动里，「{best['广告活动']}」ACOS 最低（{pct(best['ACOS'])}）。" if best else "")) if L else "没有头部词分道数据。"
    return {"涉及金额": D["花费"], "金额说明": "近 14 天同一批词被 3 个以上活动同时买的花费", "表": [table("头部词的钱花在了哪些活动", ["活动", "花费", "占头部词花费", "订单", "ACOS"], rows, read, None, {"花费": "钱", "占头部词花费": "比例", "ACOS": "比例"}, "占头部词花费")]}


def q_growth(F, inv):
    W = F["逐周"]; a, b = W[-2], W[-1]; d = b["广告费"] - a["广告费"]
    ch = [{"名": k, "上上周": a[k], "上周": b[k], "变化": b[k] - a[k], "贡献": ((b[k] - a[k]) / a["广告费"]), "占增量": ((b[k] - a[k]) / d if d else None)} for k in ("SP", "SB", "SBV")]
    top = max(ch, key=lambda x: x["变化"])
    out = [table("多花的广告费：按广告类型拆", ["类型", "上上周", "上周", "变化", "贡献", "占增量"], ch,
                 f"上周广告费比上上周多 {usd(d)}（{d / a['广告费']:+.0%}）。其中 {top['名']} 多了 {usd(top['变化'])}，占增量的 {pct(top['占增量'], 0)}；" + "、".join(f"{x['名']} {sgn(x['变化'])}" for x in ch if x is not top) + "。", None, {"上上周": "钱", "上周": "钱", "变化": "钱±", "贡献": "点", "占增量": "比例"}, "占增量")]
    T = F.get("活动表") or {}; n14, n7 = T.get("近14天") or {}, T.get("近7天")
    if n7:
        cs = sorted(({"名": k, "上上周": n14[k]["花费"] - n7.get(k, {}).get("花费", 0), "上周": n7.get(k, {}).get("花费", 0)} for k in n14), key=lambda x: -abs(x["上周"] - x["上上周"]))
        for x in cs: x["变化"] = x["上周"] - x["上上周"]
        dsp = sum(x["变化"] for x in cs)
        out.append(table("SP 里面：按活动拆", ["活动", "上上周", "上周", "变化"], cs[:8], f"SP 这一块多花 {usd(dsp)}：" + "、".join(f"「{x['名']}」{sgn(x['变化'])}" for x in cs[:3]) + "。", "SB、SBV 没有活动明细，拆不到活动；活动报告和利润表口径略有出入", {"上上周": "钱", "上周": "钱", "变化": "钱±"}, "变化"))
    du = sum(r[5] for r in inv) - sum(r[4] for r in inv)
    us = sorted(({"名": r[0], "上上周": r[4], "上周": r[5], "变化": r[5] - r[4], "够卖几周": r[6]} for r in inv), key=lambda x: -abs(x["变化"]))[:8]
    out.append(table("多卖的件数：按规格拆", ["规格", "上上周", "上周", "变化", "够卖几周"], us, f"件数多了 {du} 件：" + "、".join(f"{x['名']} {x['变化']:+d}" for x in us[:3]) + "。", None, {"变化": "数±", "够卖几周": "周"}, "变化"))
    return {"涉及金额": d, "金额说明": "上周比上上周多花的广告费", "表": out, "_ch": {x["名"]: x for x in ch}, "_d": d}


def q_acos(F):
    A, B = F["SP-前14天"], F["SP-近14天"]; aov = lambda x: x["销售额"] / x["订单"] if x.get("订单") else None
    da = B["ACOS"] - A["ACOS"]; parts = [("每次点击多少钱（CPC）", math.log(B["CPC"] / A["CPC"]), A["CPC"], B["CPC"], "$"), ("点击变成订单的比例（转化率）", -math.log(B["CVR"] / A["CVR"]), A["CVR"], B["CVR"], "%"),
                                         ("每单卖多少钱（客单价）", -math.log(aov(B) / aov(A)), aov(A), aov(B), "$")]
    tot = sum(p[1] for p in parts) or 1e-9
    show = lambda v, u: f"${v:.2f}" if u == "$" else pct(v)
    rows = [{"名": n, "前 14 天": show(a, u), "近 14 天": show(b, u), "推高 ACOS": l / tot * da} for n, l, a, b, u in parts]
    lead = max(rows, key=lambda r: abs(r["推高 ACOS"]))
    out = [table("ACOS 变化：是点击贵了、转化差了，还是卖便宜了", ["因素", "前 14 天", "近 14 天", "推高 ACOS"], rows,
                 f"SP 的 ACOS 从 {pct(A['ACOS'])} 到 {pct(B['ACOS'])}（{pts(da)}）。影响最大的是{lead['名'].split('（')[0]}：{pts(lead['推高 ACOS'])}。", "ACOS ＝ CPC ÷（转化率 × 客单价）；三项各自的变化按对数拆开，加起来等于 ACOS 的变化", {"推高 ACOS": "点"}, "推高 ACOS")]
    G0, G1 = F.get("分组账-前14天") or {}, F.get("分组账-近14天") or {}
    if G0 and G1:
        S0, R0 = sum(g["广告花费"] for g in G0.values()), sum(g["广告销售额"] for g in G0.values()); S1, R1 = sum(g["广告花费"] for g in G1.values()), sum(g["广告销售额"] for g in G1.values())
        rows2 = []
        for k in G1:
            g1, g0 = G1[k], G0.get(k)
            if not g0 or not g0["广告销售额"] or not g1["广告销售额"]:
                rows2.append({"名": k.split("-", 1)[-1], "花费": g1["广告花费"], "占比": g1["占比"], "ACOS": g1.get("ACOS"), "前 14 天 ACOS": (g0 or {}).get("ACOS"), "推高整体": None}); continue
            cf = (S1 - g1["广告花费"] + g1["广告销售额"] * g0["ACOS"]) / R1                 # 这一组的 ACOS 退回上期水平，整体会是多少
            rows2.append({"名": k.split("-", 1)[-1], "花费": g1["广告花费"], "占比": g1["占比"], "ACOS": g1["ACOS"], "前 14 天 ACOS": g0["ACOS"], "推高整体": S1 / R1 - cf})
        rows2.sort(key=lambda r: -(r["花费"] or 0)); worst = max((r for r in rows2 if r["推高整体"] is not None), key=lambda r: r["推高整体"], default=None)
        out.append(table("按词组：哪一类词在推高 ACOS", ["词组", "花费", "占比", "ACOS", "前 14 天 ACOS", "推高整体"], rows2,
                         (f"把某一类词的 ACOS 换回前 14 天的水平，看整体 ACOS 会少多少。推高最多的是「{worst['名']}」：{pts(worst['推高整体'])}。" if worst else "两个窗口对不上，拆不了。"), "推高整体＝现在的整体 ACOS − 假如这一类词的 ACOS 没变时的整体 ACOS", {"花费": "钱", "占比": "比例", "ACOS": "比例", "前 14 天 ACOS": "比例", "推高整体": "点"}, "推高整体"))
    return {"涉及金额": None, "金额说明": "ACOS 在目标内，不折算", "表": out}


def q_tacos(F):
    W = F["逐周"]; a, b = W[-2], W[-1]
    rows = [{"名": k, "上上周": a[k] / a["销售额"], "上周": b[k] / b["销售额"], "变化": b[k] / b["销售额"] - a[k] / a["销售额"]} for k in ("SP", "SB", "SBV")]
    top = max(rows, key=lambda r: r["变化"])
    return {"涉及金额": None, "金额说明": "TACOS 在盈亏线内，不折算", "表": [table("TACOS：三种广告各占销售额几个点", ["类型", "上上周", "上周", "变化"], rows,
            f"TACOS 从 {pct(a['TACOS'])} 到 {pct(b['TACOS'])}（{pts(b['TACOS'] - a['TACOS'])}）。{top['名']} 一项就占了 {pts(top['变化'])}。", "每种广告的花费 ÷ 当周总销售额，三项相加就是 TACOS", {"上上周": "比例", "上周": "比例", "变化": "点"}, "变化")]}


def q_waste(F):
    G = F.get("分组账-近14天") or {}; rows = [{"名": k.split("-", 1)[-1], "花费": g["广告花费"], "占比": g["占比"], "订单": g["广告订单量"], "ACOS": g.get("ACOS")} for k, g in G.items() if k[:1] == "4"]
    w = F["泛词加跑偏"]
    return {"涉及金额": w["花费"], "金额说明": "近 14 天泛词和跑偏词的花费", "表": [table("泛词和跑偏词：花了多少、出了几单", ["词组", "花费", "占比", "订单", "ACOS"], rows, f"两类加起来 {usd(w['花费'])}，只占 SP 花费的 {pct(w['占比'])}。全部否掉，每两周最多省这么多。", None, {"花费": "钱", "占比": "比例", "ACOS": "比例"}, "花费")]}


# ------------------------------------------------------------------ 分析层
def ev(text, src): return {"话": text, "出处": src}


def analyses(F, inv, Q, facts):
    I, Y, sp, W = F["库存"], F["四周"], F["SP-近14天"], F["逐周"]; a, b = W[-2], W[-1]
    risk = [r for r in inv if r[6] is not None and r[6] < 1 and r[5] > 0]; tw = sum(r[5] for r in inv) or 1; ad = sum(r[8] or 0 for r in inv) or 1
    rad = sum(r[8] or 0 for r in risk); ch = Q["末周广告费增速 vs 件数增速"].get("_ch", {}); d = Q["末周广告费增速 vs 件数增速"].get("_d") or 0
    L = F.get("头部词分道") or []; exact = next((x for x in L if "精确" in x["广告活动"]), None); lt = sum(x["花费"] for x in L) or 1
    best = min([x for x in L if x["花费"] / lt >= 0.1] or L, key=lambda x: x["ACOS"]) if L else None
    n_ret = F.get("已退回件") or 0; bt = next((x for x in F.get("回测", []) if x.get("点击阈值") == 8), None); g = F["泛词加跑偏"]
    A = {}
    A["H1"] = {"把握": "高", "把握依据": "库存和各规格的广告费都是报表里的确定数，不靠推断",
        "支持": [ev(f"撑不到 1 周的 {len(risk)} 个规格上周吃掉 {usd(rad)} 广告费，占按规格记账广告费的 {pct(rad / ad, 0)}", "库存与动销表"),
               ev(f"这些规格占上周件数 {pct(sum(r[5] for r in risk) / tw, 0)}，货到之前会先卖空", "库存与动销表"),
               ev(f"整体可售 {I['整体可售周数']:.1f} 周，补货到仓要更久", "库存快照 ＋ 人填的到仓周数")],
        "反对": [ev("买家点进来发现想要的规格没货，有一部分会换同规格的另一款，这部分广告费不算白花；换的比例报表里看不到", "没有数据")],
        "能解释": {"对象": "库存够卖几周", "说明": f"它不解释为什么缺货，只回答「缺货的规格还在花广告费吗」：在花，上周 {usd(rad)}", "比例": (rad / ad if ad else None)},
        "还缺": [{"缺什么": "断货后同规格另一款的转化率", "去哪取": "断货当周的业务报告（按子体）", "拿到后": "能算出真正白花了多少，而不是上限"}]}
    grew = [r for r in risk if r[5] > r[4]]
    A["H2"] = {"把握": "低", "把握依据": "只有时间上重合；能查到的三条数据都不支持",
        "支持": [ev(f"上周广告费 {b['广告费'] / a['广告费'] - 1:+.0%}、件数 {b['件数'] / a['件数'] - 1:+.0%}，和主力规格快断货发生在同一周", "利润表 ＋ 库存快照")],
        "反对": ([ev("将断货的规格上周件数还在涨：" + "、".join(f"{r[0]} {r[4]} → {r[5]}" for r in grew[:3]) + "；货还没断，拖不了销量", "库存与动销表")] if grew else [])
              + [ev(f"SP 的转化率 {pct(a['SP_CVR'])} → {pct(b['SP_CVR'])}，基本没动；如果是缺货拖的，转化率会先掉", "SP 广告报表")]
              + ([ev(f"多花的 {usd(d)} 里，{pct(ch['SBV']['占增量'], 0)} 来自 SBV（{sgn(ch['SBV']['变化'])}）；是视频广告加了投放，不是原来的钱换不来单", "利润表按广告类型")] if ch.get("SBV") and d else []),
        "能解释": {"对象": "末周广告费增速 vs 件数增速", "说明": "按现有数据，断货解释不了上周的增速差；它是接下来两周的风险，不是上周的原因", "比例": 0.0},
        "还缺": [{"缺什么": "各规格逐日的可售数和销量", "去哪取": "库存历史 ＋ 业务报告（按子体按天）", "拿到后": "能看出哪一天开始缺货、销量是不是那天掉的"},
               {"缺什么": "SBV 上周加投了什么", "去哪取": "广告后台 SBV 活动报告", "拿到后": "能判断多花的钱是有意放量还是预算没管住"}]}
    spshare = (ch["SP"]["占增量"] if ch.get("SP") and d else None)
    A["H3"] = {"把握": "中", "把握依据": "重复买是报表里的确定数；但「重复买＝浪费」是推断，要运营确认是不是有意这么搭的",
        "支持": [ev(f"{pct(F['同词多活动']['占比'], 0)} 的 SP 花费（{usd(F['同词多活动']['花费'])}）是同一批词被 3 个以上活动同时买", "搜索词报告"),
               ev(f"精确组只接住头部词花费的 {pct(F['精确组占头部词花费'])}，大头在词组和广泛里", "搜索词报告")]
              + ([ev(f"各活动竞价挤在 ${F['活动']['竞价区间'][0]}–${F['活动']['竞价区间'][1]} 之间，精确、词组、广泛几乎一个价", "关键词竞价表")] if F.get("活动", {}).get("竞价区间") else []),
        "反对": ([ev(f"头部词在「{best['广告活动']}」里 ACOS {pct(best['ACOS'])}，比在「{exact['广告活动']}」里的 {pct(exact['ACOS'])} 还低；把词收回精确组，不一定更省", "搜索词报告")] if exact and best and best is not exact and best["ACOS"] < exact["ACOS"] else [])
              + [ev(f"SP 整体 ACOS {pct(sp['ACOS'])}，在目标内；重复买没有把效率拖到线外", "SP 广告报表")],
        "能解释": {"对象": "末周广告费增速 vs 件数增速", "说明": (f"它只管 SP。上周多花的钱里 SP 只占 {pct(spshare, 0)}，所以它最多解释这么多" if spshare is not None else "它只管 SP，SB 和 SBV 的增量和它无关"), "比例": spshare},
        "还缺": [{"缺什么": "运营是不是有意让几个活动同时买头部词", "去哪取": "问运营", "拿到后": "有意的就不算问题，只调价差；无意的才去重"},
               {"缺什么": "头部词的自然排名", "去哪取": "关键词工具（付费，未查）", "拿到后": "排名已经稳了，就可以放心把词收进精确组降价"}]}
    rs = sorted(inv, key=lambda r: -(r[7] or 0)); rt = sum(r[7] or 0 for r in inv) or 1
    A["H4"] = {"把握": "低" if n_ret < 30 else "中", "把握依据": f"已退回的只有 {n_ret} 件，再多一周数据才稳",
        "支持": ([ev(f"已退回 {n_ret} 件里 {pct(F['退货首因占比'], 0)} 选的是「{F['退货原因'][0][0]}」", "FBA 退货报告")] if n_ret else [])
              + [ev(f"退款最多的 3 个规格（{'、'.join(r[0] for r in rs[:3])}）占全部退款的 {pct(sum(r[7] or 0 for r in rs[:3]) / rt, 0)}", "库存与动销表")],
        "反对": [ev("退款晚于销售 1–2 周：前几周销量翻倍，这些货现在才退回来，末周的退款率本来就会被抬高", "利润表逐周"),
               ev("买家选的退货理由不一定是真实原因，「尺寸不对」常被当成默认选项", "经验，没有数据")],
        "能解释": {"对象": "退款率", "说明": (f"能说明退回来的货里多数和尺寸有关；说明不了退款率为什么从 {pct(W[0]['退款率'])} 涨到 {pct(b['退款率'])}" if n_ret else "没有退货明细，解释不了"), "比例": (F.get("退货首因占比") if n_ret else None)},
        "还缺": [{"缺什么": "评论和退货留言里关于尺寸的原话", "去哪取": "评论 ＋ 退货留言", "拿到后": "能分清是尺寸图没标清，还是买家量错了"},
               {"缺什么": "按下单周算的退款率", "去哪取": "订单报告 ＋ 退货报告按订单号对上", "拿到后": "去掉「销量涨了、退款滞后」造成的假象"}]}
    leak = facts.get(6, ""); has = bool(leak) and "未发现" not in leak
    A["H5"] = {"把握": "高" if has else "中", "把握依据": "否词列表和搜索词报告直接对得上" if has else "这一轮没有对上的词",
        "支持": [ev(leak, "搜索词报告 ＋ 否词列表")] if has else [], "反对": [ev("运营可能是有意只在一个活动里否，让这个词留在别的活动里跑", "没有数据，要问运营")] if has else [ev("没有发现只否了一半的词", "搜索词报告 ＋ 否词列表")],
        "能解释": {"对象": "同一批词被几个活动重复买", "说明": "涉及的钱很小，是重复买里的一个小角落，不是主因", "比例": None},
        "还缺": [{"缺什么": "当时为什么只在一个活动里否", "去哪取": "问运营", "拿到后": "有意的保留，无意的补否"}] if has else []}
    A["H6"] = {"把握": "高", "把握依据": "花费占比是报表里的确定数；回测用的是同一份历史数据",
        "支持": [ev(f"泛词和跑偏词合计 {usd(g['花费'])}，只占 SP 花费的 {pct(g['占比'])}", "搜索词报告（分组后）")]
              + ([ev(f"回测：按「点击满 8 次没出单就否」的粗规则，当时会标 {bt['当时会标的词']} 个词，其中 {bt['其中后来出单的词']} 个后来出了单（{bt['后14天订单']} 单）", "搜索词报告前后各 14 天")] if bt else []),
        "反对": [ev("分组是按词表分的，分错的词会让这个占比偏低；明细可以人工改", "分组明细")],
        "能解释": {"对象": "泛词＋跑偏词", "说明": "这不是问题的原因，是一条排除：钱不在这里，别把力气花在否词上", "比例": g["占比"]},
        "还缺": []}
    return A


# ------------------------------------------------------------------ 对策层
def options(root, tree_links, A):
    acts = jread(f"{root}/广告闭环/输出/动作清单.json", []); opts = jread(f"{root}/广告闭环/输出/选项.json", []); rank = {"高": 3, "中": 2, "低": 1}; out = {}
    for o in opts:
        k = o["key"]; hs = tree_links.get(k, []); mine = [x for x in acts if x.get("取舍项") == k]
        money = sum(float(x["近14天涉及花费"]) for x in mine if x.get("近14天涉及花费") not in ("", None))
        cnt = {}
        for x in mine: cnt[x["类型"]] = cnt.get(x["类型"], 0) + 1
        weak = min(hs, key=lambda h: rank.get(A.get(h, {}).get("把握"), 0)) if hs else None; main = hs[0] if hs else None      # 第一条是这条对策主要靠的那条分析
        if not main: tip = ""
        elif A.get(main, {}).get("把握") != "高": tip = f"这条对策主要靠 {main}，把握{A[main]['把握']}：{A[main]['把握依据']}"
        elif weak != main and A.get(weak, {}).get("把握") != "高": tip = f"主要靠 {main}（把握高），站得住；另一条 {weak} 把握{A[weak]['把握']}，但对策不靠它成立"
        else: tip = ""
        out[k] = {"靠哪几条分析": [{"id": h, "把握": A.get(h, {}).get("把握")} for h in hs], "主要靠": main, "最弱的一条": weak, "动作": cnt, "动作数": len(mine), "近14天涉及花费": money or None, "提醒": tip}
    return out


LINKS = {"A": ["H1", "H2"], "B": ["H3", "H5"], "C": ["H5"], "D": ["H6"], "E": ["H4", "H2"]}     # 和 tree.py 里各条分析的「对策」一致；每条对策的第一条是它主要靠的
FROM = {"H1": ["库存够卖几周"], "H2": ["末周广告费增速 vs 件数增速", "库存够卖几周"], "H3": ["同一批词被几个活动重复买", "末周广告费增速 vs 件数增速", "SP 的 ACOS"],
        "H4": ["退款率"], "H5": ["同一批词被几个活动重复买"], "H6": ["泛词＋跑偏词"]}                    # 和 tree.py 里各条分析的「来自」一致


def build(root):
    out = f"{root}/广告闭环/输出"; F = jread(f"{out}/数字.json")
    if not F: raise RuntimeError("没有 数字.json：先跑一圈")
    inv = jread(f"{root}/_原始拉取/库存与动销-按SKU.json", []); facts = facts_text(root)
    Q = {"库存够卖几周": q_stock(F, inv), "退款率": q_refund(F, inv), "同一批词被几个活动重复买": q_dup(F), "末周广告费增速 vs 件数增速": q_growth(F, inv),
         "SP 的 ACOS": q_acos(F), "TACOS": q_tacos(F), "泛词＋跑偏词": q_waste(F)}
    A = analyses(F, inv, Q, facts)
    for q in Q.values():
        for k in [k for k in q if k.startswith("_")]: q.pop(k)
    for name, q in Q.items(): q["谁在查它"] = [h for h in A if name in FROM.get(h, [])]
    main = Q["末周广告费增速 vs 件数增速"]["表"][0]["读法"]
    return {"写入方": "脚本", "生成于": datetime.date.today().isoformat(), "问题": Q, "分析": A, "对策": options(root, LINKS, A),
            "小结": [Q["库存够卖几周"]["表"][0]["读法"], main, Q["同一批词被几个活动重复买"]["表"][0]["读法"]]}


def run(root):
    p = f"{root}/广告闭环/输出/归因.json"
    try: doc = build(root); code = 0
    except Exception as e:
        doc = {"写入方": "脚本", "错误": f"{type(e).__name__}: {e}"}; code = 1; print(f"归因没算出来：{doc['错误']}", file=sys.stderr)
    tmp = p + ".tmp"; json.dump(doc, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p)
    if not code: print(f"归因｜问题 {len(doc['问题'])} 个各有拆解｜分析 {len(doc['分析'])} 条：" + "、".join(f"{k} 把握{v['把握']}" for k, v in doc["分析"].items()) + f" → {p}")
    return code


if __name__ == "__main__":
    sys.exit(run(os.environ.get("ADS_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
