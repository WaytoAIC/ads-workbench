# -*- coding: utf-8 -*-
"""一个广告活动由什么构成：活动设置 → 广告组 → 广告产品 / 关键词 / 商品定位（含自动四组）/ 否定。
只用标准库，读 <数据目录>/_原始拉取/ 下的结构表，给页面「广告活动」用；哪张表没有就留空，页面写「没给这张表」。"""
import json, os

STRATEGY = {"fixed": "固定竞价", "down_only": "动态竞价-只降低", "up_and_down": "动态竞价-提高和降低"}
PLACE = {"placementTop": "搜索顶部", "placementProductPage": "商品页面", "placementRestOfSearch": "其余位置"}
AUTO = {"QUERY_HIGH_REL_MATCHES": "紧密匹配", "QUERY_BROAD_REL_MATCHES": "宽泛匹配", "ASIN_SUBSTITUTE_RELATED": "同类产品", "ASIN_ACCESSORY_RELATED": "关联商品"}
MATCH = {"exact": "精确", "phrase": "词组", "broad": "广泛", "theme": "主题", "negativeExact": "精确否定", "negativePhrase": "词组否定"}


def _j(raw, name):
    f = os.path.join(raw, name)
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def build(raw, mapper, perf=None):
    camps = _j(raw, "本父体-活动.json") or []
    cset = {str(c["campaignId"]): c for c in (_j(raw, "本父体-spCampaign.json") or [])}
    grp, kw, ne, tg, netg, ap = (_j(raw, n) for n in ("本父体-spGroup.json", "本父体-spKeyword.json", "本父体-spNeKeyword.json", "本父体-spTarget.json", "本父体-spNeTarget.json", "基础-spAdProduct-全店.json"))
    have = {"活动设置": bool(cset), "广告组": grp is not None, "关键词": kw is not None, "否定关键词": ne is not None, "商品定位": tg is not None, "否定 ASIN": netg is not None, "广告产品": ap is not None}
    by = lambda rows: {cid: [r for r in (rows or []) if str(r["campaignId"]) == cid] for cid in {str(c["campaignId"]) for c in camps}}
    G, K, N, T, NT, A = by(grp), by(kw), by(ne), by(tg), by(netg), by(ap)
    out = []
    for c in camps:
        cid, name = str(c["campaignId"]), c["name"]; s = cset.get(cid, {}); m = mapper.camp(name)
        def target(x):
            e = (x.get("expression") or [{}])[0]; t = e.get("type", "")
            if t in AUTO: return {"类别": "自动投放组", "对象": AUTO[t]}
            if t == "ASIN_CATEGORY_SAME_AS": return {"类别": "类目定位", "对象": str(e.get("名称") or e.get("value"))}
            return {"类别": "ASIN 定位", "对象": str(e.get("value")).upper()}
        out.append({
            "别名": name, "Campaign": m["Campaign"], "Campaign ID": m.get("Campaign ID", ""), "状态": c.get("state", ""), "投放方式": m.get("投放方式") or ("自动" if c.get("targetingType") == "auto" else "手动"),
            "日预算": c.get("budget"), "竞价策略": STRATEGY.get(s.get("biddingStrategy"), s.get("biddingStrategy") or ""),
            "广告位加价": [{"位置": PLACE.get(p["placement"], p["placement"]), "加价": p["percentage"]} for p in s.get("placementAdjustments", [])],
            "广告组": [{"名称": (m.get("广告组") or g.get("name", "")), "默认竞价": g.get("defaultBid"), "状态": g.get("state", "")} for g in G[cid]],
            "广告产品": [{**mapper.prod(a["sku"]), "状态": a.get("state", "")} for a in A[cid]],
            "关键词": [{"关键词": k["keywordText"], "匹配": MATCH.get(k["matchType"], k["matchType"]), "竞价": k.get("bid"), "状态": k.get("state", "")} for k in K[cid]],
            "商品定位": [{**target(x), "竞价": x.get("bid"), "状态": x.get("state", "")} for x in T[cid]],
            "否定关键词": [{"关键词": n["keywordText"], "匹配": MATCH.get(n["matchType"], n["matchType"])} for n in N[cid]],
            "否定 ASIN": [str(e.get("value")).upper() for x in NT[cid] for e in x.get("expression", []) if e.get("value")],
            "表现": (perf or {}).get(name),
        })
    out.sort(key=lambda r: -((r["表现"] or {}).get("花费") or 0))
    return {"活动": out, "有哪些表": have}
