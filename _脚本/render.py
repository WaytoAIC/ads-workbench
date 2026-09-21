# -*- coding: utf-8 -*-
"""把 pipeline 的事实与动作渲染成：三栏表、选项比较、行动卡、运行记录、单页运行报告。所有数字来自 数字.json，不手写。"""
import json, os, html, collections, datetime
import pandas as pd
import pipeline as pl
from pipeline import P, OUT, CARD, ROOT, RAW, usd, pct, B
E = lambda x: html.escape(str(x))
arrow = lambda xs: " → ".join(xs)

def unclean_negatives():                                  # 只在一个活动里否了、别处还在花钱的词
    b = pl.win(pl.s, B); out = []
    words = {w for ws in pl.ne_by_camp.values() for w in ws}
    for w in words:
        where = [c for c, ws in pl.ne_by_camp.items() if w in ws]
        d = b[(b["用户搜索词"].str.lower() == w) & (~b["广告活动"].isin(where))]
        if d["广告花费"].sum() > 0:
            out.append({"词": w, "只否在": "、".join(where), "别处活动数": int(d["广告活动"].nunique()), "花费": float(d["广告花费"].sum()), "点击": int(d["广告点击量"].sum()), "订单": int(d["广告订单量"].sum()),
                        "ACOS": (float(d["广告花费"].sum() / d["广告销售额"].sum()) if d["广告销售额"].sum() else None)})
    return sorted(out, key=lambda x: -x["花费"])

def docs(F, rows, summ):
    W, Y, I, R = F["逐周"], F["四周"], F["库存"], float(P["补货到仓周数"]); gB = F["分组账-近14天"]; spB, spA = F["SP-近14天"], F["SP-前14天"]; lk = unclean_negatives()[:3]
    risk = "、".join(f"{x['SKU']}（上周卖 {x['上周销量']}，可售 {x['可售']}＝{x['可售周数']} 周）" for x in I["将断货SKU"]) or "无"
    grp_line = "｜".join(f"{k[k.find('-')+1:]} {usd(v['广告花费'])}（{pct(v['占比'])}，ACOS {pct(v['ACOS']) if v['ACOS'] else '—'}）" for k, v in gB.items())
    lane_line = "、".join(f"{x['广告活动']} {usd(x['花费'])}" + (f"（ACOS {pct(x['ACOS'],0)}）" if x["ACOS"] else "") for x in F["头部词分道"][:5])
    bt8 = next(x for x in F["回测"] if x["点击阈值"] == 8); bt5 = next(x for x in F["回测"] if x["点击阈值"] == 5)
    sanlan = f"""# 诊断 · 三栏表（{P['任务编号']} v{P.get('版本',1)}，今天按 {P['今天']} 算）

数据：{P['显示店铺']}｜{P['显示产品']}｜SP 报表 {pl.A[0]}～{B[1]} 按天、利润报表按周、FBA 库存快照、FBA 退货。口径核对：活动报告花费 {usd(F['口径核对']['活动报告花费'])} vs 搜索词报告 {usd(F['口径核对']['搜索词报告花费'])}。**{P['归因未满']} 归因未满，订单偏少。**

## 事实（可复算）
1. **四周经营账**：销售额 {usd(Y['销售额'])}｜{Y['件数']:,} 件｜均价 ${Y['均价']:.2f}。广告费 {usd(Y['广告费'])}＝SP {pct(Y['SP占比'],0)}＋SB {pct(Y['SB占比'],0)}＋SBV {pct(Y['SBV占比'],0)}。TACOS **{pct(Y['TACOS'])}**；广告前毛利率（盈亏线）{pct(Y['盈亏线'])}，广告后 **{pct(Y['广告后毛利率'])}**。
2. **逐周**：件数 {arrow(str(w['件数']) for w in W)}；广告费 {arrow(usd(w['广告费']) for w in W)}；TACOS {arrow(pct(w['TACOS']) for w in W)}。末周广告费 {F['末周环比']['广告费']:+.0%}，件数 {F['末周环比']['件数']:+.0%}。
3. **SP 逐周**：ACOS {arrow(pct(w['SP_ACOS']) for w in W)}；CVR {arrow(pct(w['SP_CVR']) for w in W)}；CPC {arrow(f"${w['SP_CPC']:.2f}" for w in W)}；CTR {pct(W[0]['SP_CTR'],2)} → {pct(W[-1]['SP_CTR'],2)}。
4. **近 14 天分组账（SP {usd(spB['花费'])}）**：{grp_line}。**泛词＋跑偏合计 {usd(F['泛词加跑偏']['花费'])}＝{pct(F['泛词加跑偏']['占比'])}。**
5. **同词多活动**：{F['同词多活动']['词数']} 个搜索词同时被 ≥3 个活动买，合计 {usd(F['同词多活动']['花费'])}＝**{pct(F['同词多活动']['占比'],0)}**。头部 4 词（{'、'.join(F['头部词'])}）花在：{lane_line}；精确组只占 **{pct(F['精确组占头部词花费'])}**。关键词竞价 ${F['活动']['竞价区间'][0]}–{F['活动']['竞价区间'][1]}，几乎一刀切。
6. **否词没否干净**：{'；'.join(f"{x['词']} 只在「{x['只否在']}」否了，近 14 天仍从另外 {x['别处活动数']} 个活动花 {usd(x['花费'])}（{x['订单']} 单）" for x in lk) or '未发现'}。
7. **库存**：可售 {I['可售']:,}、调拨中 {I['调拨中']:,}、途中 {I['途中']:,}；上周卖 {I['上周销量']:,} 件，整体够 **{I['整体可售周数']:.1f} 周**。将断货：{risk}。两周内会断货的 {len(I['两周内断货SKU'])} 个 SKU（{'、'.join(I['两周内断货SKU'])}）占上周件数 {pct(I['两周内断货占上周件数'],0)}，合计可售 {I['两周内断货可售']} 件＝{I['两周内断货可售周数']:.2f} 周。
8. **回测**（站在 {pl.A[1]} 用粗规则"点击 ≥8 且 0 单"）：标得出 {bt8['当时会标的词']} 个词，其中 {bt8['其中后来出单的词']} 个后 14 天出了单。阈值放到 5：{bt5['当时会标的词']} 个词 {usd(bt5['当时已花'])}，其中 {bt5['其中后来出单的词']} 个后来出单（{bt5['后14天订单']} 单），{bt5['其中运营已否']} 个运营已经否掉。
9. **退货**：已退回 {F['已退回件']} 件，{'、'.join(f'{k} {v} 件' for k, v in F['退货原因'])}。退款率逐周 {arrow(pct(w['退款率']) for w in W)}。

## 推断（带依据，和什么情况下不成立）
- **这个品的广告问题不在跑偏词。** 依据：事实 4、8。不成立的情况：分组是 AI 按语义分的，明细在 `分组明细-近14天-请人工纠错.csv`，分错了要重算。
- **广告正在给快断货的主力规格买流量。** 依据：事实 7。将断货的 SKU 占上周件数 {pct(I['将断货占上周件数'],0)}；若买不到想要的规格的人直接流失，等效 ACOS 从 {pct(spB['ACOS'],0)} 升到约 {pct(F['断货后等效ACOS'],0)}（盈亏线 {pct(Y['盈亏线'])}）。不成立的情况：顾客会自己换到同规格的另一款。
- **竞价一刀切，精确组没起到收割作用。** 依据：事实 5。不成立的情况：这是运营有意为之。
- **末周增长放缓可能与断货有关。** 依据：事实 2、7，只有时间重合，证据弱。

## 未知（缺什么，去哪取）
- 目标 ACOS、阶段优先级、上一轮有意为之的判断：问老板或运营（现按目标 {pct(float(P['目标ACOS']),0)}、盈亏线 {pct(Y['盈亏线'])} 跑）。
- 在途货实际到仓日：问供应链（现按 {R:g} 周）。
- 核心词自然排名：{pct(Y['广告归因销售额占比'],0)} 的销售额带广告归因（SB、SBV 口径宽，是上限）；需关键词工具，付费，未查。
- SB、SBV 占广告费 {pct(Y['SB占比']+Y['SBV占比'],0)}，明细未分析。
"""
    open(f"{OUT}/诊断-三栏表.md", "w", encoding="utf-8").write(sanlan)
    t = summ["按类型"]; nA = t.get("暂停广告产品", 0)
    NAMES = {"A": "保主力规格", "B": "结构去重", "C": "竞品词分拣", "D": "只做否词", "E": "查退款与到仓"}; chosen = summ["取舍项"]
    P["取舍"] = "选了 " + "、".join(f"{k} {NAMES[k]}" for k in chosen) + ("；没选 " + "、".join(f"{k} {NAMES[k]}" for k in NAMES if k not in chosen) if len(chosen) < 5 else "")
    gB_ = F["分组账-近14天"]
    opts = [{"key": "A", "名称": "先保主力规格", "做什么": "将断货的 SKU 暂停广告（到仓快就只降预算），同规格库存足的另一款补挂上去", "何时选": "补货 2 周内到不了仓",
             "代价": f"不动：断货后每周 {usd(W[-1]['广告费'])} 广告费里约 {pct(I['将断货占上周件数'],0)}（≈{usd(F['断货每周白花上限'])}）买的是买不到想要的规格的点击【推断，上限】。动：另一款转化没验证过，短期单量会掉", "可逆": "可逆，到仓即恢复"},
            {"key": "B", "名称": "结构去重", "做什么": "头部 4 词回主干组，别的组里做精确否定；词组、广泛竞价压到精确之下", "何时选": "想知道每个词到底值多少钱",
             "代价": f"直接成本 $0；过渡期可能丢曝光。现在 {pct(F['同词多活动']['占比'],0)} 的花费是重复买的", "可逆": "可逆"},
            {"key": "C", "名称": "竞品品牌词分拣", "做什么": "赚钱的留；出过单但 ACOS 高于盈亏线的单独降价跑；零单且样本够的才否", "何时选": "任何时候",
             "代价": f"竞品词近 14 天 {usd(gB_.get('3-竞品品牌词',{}).get('广告花费',0))}（前 14 天 {usd(F['分组账-前14天'].get('3-竞品品牌词',{}).get('广告花费',0))}）；风险低", "可逆": "可逆"},
            {"key": "D", "名称": "只做否词（粗规则）", "做什么": "点击 ≥8 且 0 单的泛词、跑偏词一律精确否定", "何时选": "只想做最省事的",
             "代价": f"近 14 天最多省 {usd(F['泛词加跑偏']['花费'])}（占花费 {pct(F['泛词加跑偏']['占比'])}）；回测：粗规则标出的 {F['回测'][1]['当时会标的词']} 个词里 {F['回测'][1]['其中后来出单的词']} 个后来出单", "可逆": "可逆"},
            {"key": "E", "名称": "先查退款和到仓", "做什么": "Listing 加选规格提示出建议稿；供应链回填到仓日", "何时选": "退款继续涨",
             "代价": f"只花时间；末周退款率 {pct(W[-1]['退款率'])}", "可逆": "—"}]
    for o in opts: o["已选"] = o["key"] in chosen; o["动作条数"] = summ["按取舍项"].get(o["key"], 0)
    json.dump(opts, open(f"{OUT}/选项.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    xuan = f"""# 选项比较（不替你选）

| # | 动作 | 什么时候该选 | 代价／收益（折成钱） | 可逆吗 |
|---|---|---|---|---|
| A | **先保主力规格**：将断货的 SKU 暂停广告（或只降预算），同规格库存足的另一款补挂上去 | 补货 2 周内到不了仓 | 不动：断货后每周 {usd(W[-1]['广告费'])} 广告费里约 {pct(I['将断货占上周件数'],0)}（≈{usd(F['断货每周白花上限'])}）买的是买不到想要的规格的点击【推断，上限】。动：另一款转化没验证过，短期单量会掉 | 可逆，到仓即恢复 |
| B | **结构去重**：头部 4 词回主干组，别的组里做精确否定；词组、广泛竞价压到精确之下 | 想知道每个词到底值多少钱 | 直接成本 $0；过渡期可能丢曝光。收益：串道的花费停掉，之后才谈得上按词调竞价 | 可逆 |
| C | **竞品品牌词分拣**：赚钱的留，出过单但 ACOS 高于盈亏线的单独降价跑，零单且样本够的才否 | 任何时候 | 竞品词近 14 天 {usd(gB.get('3-竞品品牌词',{}).get('广告花费',0))}（前 14 天 {usd(F['分组账-前14天'].get('3-竞品品牌词',{}).get('广告花费',0))}）；风险低 | 可逆 |
| D | **只做否词**（课堂原套路）：泛词＋跑偏词 | 只想做最省事的 | 近 14 天最多省 {usd(F['泛词加跑偏']['花费'])}；回测显示粗规则标的词一半后来出单，有误否风险 | 可逆 |
| E | **先查退款为什么涨**，再决定要不要继续放量 | 退款继续涨 | 只花时间；末周退款率 {pct(W[-1]['退款率'])} | — |

**{P['取舍人']}的取舍**：{P['取舍']}；在途货按 **{R:g} 周**到仓算。
"""
    open(f"{OUT}/选项比较.md", "w", encoding="utf-8").write(xuan)
    a_text = (f"按 `广告产品调整表.csv` 暂停 {nA} 条广告产品（{'、'.join(summ['暂停SKU'])}），保留 {summ['保留广告产品']} 条；补挂 {t.get('补挂广告产品',0)} 条同规格库存足的另一款" if nA
              else f"补货 {R:g} 周就到，不暂停；{t.get('下调预算',0)} 个含将断货 SKU 的活动预算先降 30%，到仓后恢复")
    parts = []
    if "A" in chosen: parts.append(f"**A** {a_text}。")
    if "B" in chosen: parts.append(f"**B** {t.get('换道否定',0)} 条换道精确否定；{t.get('降竞价',0)} 条降竞价（单次 ≤15%，精确不动、成为最高一档）。")
    if "C" in chosen: parts.append(f"**C** 竞品词分拣 {summ['竞品词分拣']}：{t.get('竞品词降价单独跑',0)} 个单独降价跑，{t.get('竞品词否定',0)} 个否定，另有 {t.get('交回运营判断',0)} 个运营否过但出过单的词交回运营定。")
    if "D" in chosen: parts.append(f"**D** 粗规则否词 {t.get('粗规则否词',0)} 条（注意回测里的误伤率）。")
    if "E" in chosen: parts.append("**E** Listing 加选规格提示出建议稿；供应链回填到仓日。")
    card = f"""# 行动卡 {P['任务编号']} v{P.get('版本',1)}（状态：待确认）

生成：{P['今天']}｜{P['显示店铺']}｜{P['显示产品']}｜取舍人：{P['取舍人']}

| 字段 | 填写 |
|---|---|
| 1 业务问题 | 新品第 5 周，上周卖 {W[-1]['件数']} 件、广告费 {usd(W[-1]['广告费'])}、广告后毛利率 {pct(W[-1]['广告后毛利率'],0)}。**将断货的 SKU 占上周件数 {pct(I['将断货占上周件数'],0)}，补货要 {R:g} 周，广告还主要挂在这条线上**；{pct(F['同词多活动']['占比'],0)} 的 SP 花费是同一批词被 3 个以上活动重复买；退款率四周从 {pct(W[0]['退款率'])} 升到 {pct(W[-1]['退款率'])}。 |
| 2 已知事实（附来源与周期） | 见 `输出/诊断-三栏表.md` 事实 1–9。 |
| 3 判断与待证假设（与事实分开写） | ①断货后等效 ACOS 约 {pct(F['断货后等效ACOS'],0)}，越过盈亏线 {pct(Y['盈亏线'])}（假设顾客不会自己换款）。②头部词在非主干组里属于串道，清掉不伤量。③竞价一刀切不是有意为之（待运营确认）。④退款上升主因是「{F['退货原因'][0][0]}」（只有 {F['已退回件']} 件样本）。 |
| 4 具体动作 | 共 {summ['合计']} 条，见 `输出/动作清单.csv`。{' '.join(parts)}{(f" **读回上轮**：已确认的 {summ['沿用上轮已确认']} 条沿用不重派；被驳回的 {len(summ['上轮被驳回不再提'])} 条不再原样提；另有 {len(summ['已确认但新输入下不再建议'])} 条是旧输入下确认的、新输入下规则已不再建议，请复核。") if (summ['沿用上轮已确认'] or summ['上轮被驳回不再提'] or summ['已确认但新输入下不再建议']) else ""} |
| 5 接手岗位 | A、B、C：广告运营（自己到后台操作，AI 不碰后台）。E：Listing 负责人、供应链。 |
| 6 执行条件（满足什么才开始 / 什么情况不做） | 运营在工作台逐条把状态改成「已确认」才执行；驳回必须填理由。到仓周数变了就改参数重跑，未确认的旧动作自动作废。{P['归因未满']} 归因未满，执行前到后台核这三天的订单。 |
| 7 完成时间 | A：次日当天。B、C：两天内。E：四天内出建议稿。 |
| 8 成本条件（上限、谁批准） | 不加任何预算；竞价单次调幅 ≤15%；A 执行后周销量会掉，下限由{P['取舍人']}批。 |
| 9 复核证据与观察期（= 下一次运行的触发与检查项） | **观察 6 天，{P['复盘日']} 复盘**（同一套脚本重跑）。逐项看：①将断货 SKU 的广告是否已停，整体可售周数是否从 {I['整体可售周数']:.1f} 回到 ≥4；②补挂款同规格的 CVR 对比原款 {pct(spB['CVR'])}；③头部 4 词在非主干组的花费是否归零，精确组占比是否从 {pct(F['精确组占头部词花费'])} 升上来；④SP 的 CPC 是否从 ${spB['CPC']:.2f} 降下来、ACOS 是否 ≤{pct(float(P['目标ACOS']),0)}，件数掉了多少；⑤单独降价跑的竞品词 ACOS 是否回到盈亏线内；⑥退款率是否还在 {pct(W[-1]['退款率'],0)} 上下，新退回件里首因占比；⑦SB、SBV 明细是否已分析。观察期没满只报进度，不下结论。 |

自检：数字能复算（`_脚本/pipeline.py`，带断言）；事实和假设分开了；接手人读完知道做什么；写明了何时能判断结果。
"""
    fn = f"{CARD}/行动卡-{P['任务编号']}{'' if int(P.get('版本',1)) == 1 else 'v'+str(P['版本'])}.md"; open(fn, "w", encoding="utf-8").write(card)
    cells = [l for l in card.splitlines() if l.startswith("| ") and l[2].isdigit()]; assert len(cells) == 9 and all(len(c) > 30 for c in cells), "行动卡九格不全"
    return {"行动卡": cells, "行动卡文件": fn}

def table(df):
    h = "".join(f"<th>{E(c)}</th>" for c in df.columns); body = "".join("<tr>" + "".join(f"<td>{E(v)}</td>" for v in r) + "</tr>" for r in df.itertuples(index=False))
    return f'<div class="scroll"><table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'

def report(F, rows, summ, base_url=None):
    W, Y, I = F["逐周"], F["四周"], F["库存"]; gB = F["分组账-近14天"]; t = summ["按类型"]
    wk = pd.DataFrame([{"周": w["周"], "件数": w["件数"], "销售额": usd(w["销售额"]), "广告费": usd(w["广告费"]), "其中 SP": usd(w["SP"]), "SB": usd(w["SB"]), "SBV": usd(w["SBV"]), "TACOS": pct(w["TACOS"]), "SP 的 ACOS": pct(w["SP_ACOS"]), "退款率": pct(w["退款率"]), "广告后毛利率": pct(w["广告后毛利率"])} for w in W])
    grp = pd.DataFrame([{"分组": k[k.find('-')+1:], "花费": usd(v["广告花费"]), "占比": pct(v["占比"]), "点击": int(v["广告点击量"]), "订单": int(v["广告订单量"]), "CVR": pct(v["CVR"]), "CPC": f"${v['CPC']:.2f}", "ACOS": (pct(v["ACOS"]) if v["ACOS"] else "—")} for k, v in gB.items()])
    lane = pd.DataFrame([{"广告活动": x["广告活动"], "花费": usd(x["花费"]), "点击": x["点击"], "订单": x["订单"], "ACOS": (pct(x["ACOS"], 0) if x["ACOS"] else "—")} for x in F["头部词分道"]])
    invd = pd.DataFrame(sorted(pl.inv.values(), key=lambda r: -(r[5] or 0))[:8], columns=["SKU", "可售", "调拨中", "途中(含未发)", "上上周销量", "上周销量", "可售周数", "上周退款", "上周广告费", "上周销售额"])
    acts = pd.DataFrame(rows); by = acts.groupby(["取舍项", "类型"]).size().reset_index(name="条数")
    sample = acts.groupby("类型").head(2)[["动作编号", "类型", "广告活动", "对象", "现值", "新值", "依据", "状态"]]
    calls = collections.Counter(json.loads(l)["path"] for l in open(f"{RAW}/调用记录.jsonl", encoding="utf-8")); calls_df = pd.DataFrame([{"接口（全部只读）": p, "调用次数": n} for p, n in calls.most_common()])
    CSS = """:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--mute:#5d6b7c;--line:#e2e6ec;--acc:#1f5fbf;--warn:#b42318;--ok:#1a7f4b;--tag:#eef3fb}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#12161c;--card:#1a2029;--ink:#e6eaf0;--mute:#9aa7b7;--line:#2a323e;--acc:#7fb0ff;--warn:#ff8b7e;--ok:#5fd39a;--tag:#202a38}}
:root[data-theme=dark]{--bg:#12161c;--card:#1a2029;--ink:#e6eaf0;--mute:#9aa7b7;--line:#2a323e;--acc:#7fb0ff;--warn:#ff8b7e;--ok:#5fd39a;--tag:#202a38}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,"PingFang SC","Helvetica Neue",sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 64px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:0 0 10px}h3{font-size:15px;margin:16px 0 6px;color:var(--mute)}
.sub{color:var(--mute);margin:0 0 16px}.badge{display:inline-block;background:var(--acc);color:#fff;border-radius:4px;padding:1px 8px;font-size:12px;margin-left:8px;vertical-align:middle}.badge.red{background:var(--warn)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 18px 14px;margin:14px 0}.step{display:inline-block;background:var(--acc);color:#fff;border-radius:50%;width:26px;height:26px;text-align:center;line-height:26px;margin-right:8px;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:10px 0}.tile{background:var(--tag);border-radius:8px;padding:10px 12px}.tile b{display:block;font-size:20px}.tile span{color:var(--mute);font-size:12.5px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13.5px;margin:6px 0}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;white-space:nowrap}td:last-child{white-space:normal}th{color:var(--mute);font-weight:500}
.key{border-left:3px solid var(--warn);padding:6px 12px;margin:10px 0;background:var(--tag);border-radius:0 6px 6px 0}.ok{border-left-color:var(--ok)}ul{margin:6px 0 6px 20px;padding:0}pre{white-space:pre-wrap;font:13.5px/1.6 inherit;margin:0}details{margin:8px 0}summary{cursor:pointer;color:var(--acc)}a{color:var(--acc)}"""
    real = "未脱敏" in P.get("数据标记", "")
    CMP = ('<section><h2>和课堂虚构案例对照</h2>' + table(pd.DataFrame([{"": "异常在哪", "虚构案例": "ACOS 35% 超盈亏线", "这个案例": f"ACOS {pct(F['SP-近14天']['ACOS'],0)} 没超线；主力规格断货、花费重复、退款上升"}, {"": "跑偏词", "虚构案例": "12 个词，占花费 22%", "这个案例": f"泛词＋跑偏只占 {pct(F['泛词加跑偏']['占比'])}"},
           {"": "只看搜索词报告够吗", "虚构案例": "够", "这个案例": f"不够：要库存、利润、退货才看得见真问题；SB、SBV 占广告费 {pct(Y['SB占比']+Y['SBV占比'],0)}"}, {"": "人的取舍", "虚构案例": "否掉「砍一半预算」", "这个案例": P['取舍']}])) + '</section>') if real else ""
    H = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>广告周检运行报告</title><style>{CSS}</style></head><body><main>
<h1>新品广告周检 · 运行报告<span class="badge{' red' if real else ''}">{E(P['任务编号'])} v{P.get('版本',1)}</span></h1>
<p class="sub">{E(P['显示店铺'])}｜{E(P['显示产品'])}｜数据 {pl.A[0]}～{B[1]}｜{E(P.get('数据标记',''))}{f'｜<a href="{E(base_url)}">打开工作台</a>' if base_url else ''}</p>
<section><h2>一句话</h2><div class="key">问题不在跑偏词：泛词加跑偏词只占 SP 花费 {pct(F['泛词加跑偏']['占比'])}。真正的异常是<b>将断货的 SKU 占上周件数 {pct(I['将断货占上周件数'],0)}、补货要 {float(P['补货到仓周数']):g} 周，广告还主要挂在这条线上</b>；其次是 {pct(F['同词多活动']['占比'],0)} 的花费被多个活动重复买、竞价一刀切；退款率四周升到 {pct(W[-1]['退款率'])}，已退回件里 {pct(F['退货首因占比'],0)} 是「{E(F['退货原因'][0][0])}」。</div>
<div class="tiles"><div class="tile"><b>{usd(Y['销售额'])}</b><span>四周销售额（{Y['件数']:,} 件）</span></div><div class="tile"><b>{usd(Y['广告费'])}</b><span>广告费：SP {pct(Y['SP占比'],0)}／SB {pct(Y['SB占比'],0)}／SBV {pct(Y['SBV占比'],0)}</span></div><div class="tile"><b>{pct(Y['TACOS'])}</b><span>TACOS（盈亏线 {pct(Y['盈亏线'])}）</span></div><div class="tile"><b>{pct(Y['广告后毛利率'])}</b><span>广告后毛利率</span></div><div class="tile"><b>{I['整体可售周数']:.1f} 周</b><span>整体可售；占销量 {pct(I['两周内断货占上周件数'],0)} 的 {len(I['两周内断货SKU'])} 个 SKU 只有 {I['两周内断货可售周数']:.2f} 周</span></div><div class="tile"><b>{pct(W[-1]['退款率'])}</b><span>末周退款率（首周 {pct(W[0]['退款率'])}）</span></div></div></section>
<section><h2><span class="step">1</span>发现异常：没有目标，就没有异常</h2><p>目标 ACOS {pct(float(P['目标ACOS']),0)}、盈亏线 {pct(Y['盈亏线'])}。SP 的 ACOS {pct(F['SP-近14天']['ACOS'])} 并不流血；异常出在末周广告费 {F['末周环比']['广告费']:+.0%}、件数只 {F['末周环比']['件数']:+.0%}，以及库存。</p>{table(wk)}</section>
<section><h2><span class="step">2</span>判断原因：事实、推断、未知分开</h2><h3>近 14 天搜索词分组账（分组是 AI 按语义做的，报表里没有这一列；明细留给人纠错）</h3>{table(grp)}
<h3>头部 4 个词花在哪些活动（精确组只占 {pct(F['精确组占头部词花费'])}）</h3>{table(lane)}<h3>库存与动销（按上周销量排，前 8）</h3>{table(invd)}
<h3>已退回 {F['已退回件']} 件的原因</h3><p>{"｜".join(f"{E(k)} {v} 件" for k, v in F['退货原因'])}</p>
<details><summary>完整三栏表</summary><pre>{E(open(f"{OUT}/诊断-三栏表.md", encoding="utf-8").read())}</pre></details></section>
<section><h2><span class="step">3</span>制定动作：AI 摆选项和代价，人取舍</h2><pre>{E(open(f"{OUT}/选项比较.md", encoding="utf-8").read())}</pre></section>
<section><h2><span class="step">4</span>调用工具执行：只出清单，停在「待确认」</h2><p>本轮 <b>{summ['合计']} 条动作</b>，每条一个编号，写进工作台的动作清单；人在表里改状态，下一轮读回。</p>{table(by)}<h3>每类前两条样例</h3>{table(sample)}
<h3>竞品品牌词分拣</h3><p>{E(summ['竞品词分拣'])}。零单的词样本不够就先观察，不直接否。</p><h3>这一轮调过的数据接口</h3>{table(calls_df)}</section>
<section><h2><span class="step">5</span>复盘学习：先回测，再约 {E(P['复盘日'])}</h2><p>动作还没执行，所以这是<b>回测</b>：站在 {pl.A[1]} 用粗规则标词，看这些词后 14 天自己怎样。</p>{table(pd.DataFrame(F['回测']))}
<div class="key">转化率 {pct(F['SP-近14天']['CVR'],0)} 的品，几次点击不出单很正常；靠粗规则否词省不出钱，还会误伤。真 Loop 的第一圈：行动卡第 9 格约定 <b>{E(P['复盘日'])}</b> 复盘，同一套脚本重跑。</div></section>
{CMP}<section><h2>照实说</h2><ul><li>手动触发，定时没接；AI 全程只读，没碰广告后台，动作全部「待确认」。</li><li>没做：SB 和 SBV 明细、关键词自然排名、评论。{E(P['归因未满'])} 归因未满。</li><li>「断货后每周约 {usd(F['断货每周白花上限'])} 广告费白花」是推断的上限，前提是顾客不会自己换款。</li></ul></section></main></body></html>"""
    fn = f"{ROOT}/运行报告-{P['任务编号']}.html"; open(fn, "w", encoding="utf-8").write(H); return fn

if __name__ == "__main__":
    F = pl.facts(); rows, summ = pl.actions(F); d = docs(F, rows, summ)
    base_url = (json.load(open(f"{ROOT}/工作台.json")).get("url") if os.path.exists(f"{ROOT}/工作台.json") else None)
    fn = report(F, rows, summ, base_url)
    json.dump({"行动卡": d["行动卡"], "报告": fn, "汇总": summ}, open(f"{OUT}/渲染结果.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{P['任务编号']} v{P.get('版本',1)}｜到仓 {P['补货到仓周数']} 周 → 动作 {summ['合计']} 条 {summ['按类型']}"); print("行动卡：", d["行动卡文件"]); print("报告：", fn)
