# -*- coding: utf-8 -*-
"""把一条动作翻成广告后台认得的字段：实体、操作、Campaign / 广告组（名称与 ID）、SKU / ASIN、关键词 / 匹配 / 关键词 ID、定位表达式 / 定位 ID、改哪个字段。
只用标准库。名称与 ID 取自 <数据目录>/显示映射.json（演示数据才有）；没有这个文件时原样显示原名、ID 留空。"""
import hashlib, json, os, re

MATCH = {"exact": "精确", "phrase": "词组", "broad": "广泛", "negativeExact": "精确否定"}
AUTO_EXPR = {"紧密匹配": "close-match", "宽泛匹配": "loose-match", "同类产品": "substitutes", "关联商品": "complements"}   # 批量上传表里自动四组的写法
STRATEGY_BULK = {"固定竞价": "Fixed bid", "动态竞价-只降低": "Dynamic bids - down only", "动态竞价-提高和降低": "Dynamic bids - up and down"}
def money(v):
    try: return f"{float(str(v).lstrip('$')):g}"
    except (TypeError, ValueError): return v


# 动作类型 → (实体, 操作, 改什么)。走 Amazon Ads API（现在＝导出批量上传表）的都在这里
KW_BID = {"降竞价", "关键词降竞价", "关键词提竞价"}
TG_BID = {f"{k}{d}竞价" for k in ("ASIN 定位", "类目定位", "自动投放组") for d in ("降", "提")}
TG_PAUSE = {"暂停 ASIN 定位", "暂停 类目定位", "关闭自动投放组"}
NEG_KW = {"换道否定", "竞品词否定", "粗规则否词", "来源组否定"}
ADS_TYPES = {"暂停广告产品", "补挂广告产品", "下调预算", "预算上调", "改竞价策略", "下调默认竞价", "暂停关键词", "搜索词收割", "竞品词降价单独跑", "否定 ASIN"} | KW_BID | TG_BID | TG_PAUSE | NEG_KW


class Mapper:
    def __init__(self, root, params):
        f = os.path.join(root, "显示映射.json")
        m = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
        self.on, self.C, self.P, self.parent = bool(m), m.get("活动", {}), m.get("商品", {}), m.get("父 ASIN", "")
        self.exact = params.get("精确活动", "")

    def camp(self, name):
        c = self.C.get(name)
        if not c: return {"Campaign": name, "Campaign ID": "", "广告组": "", "广告组 ID": "", "别名": name}
        return {"Campaign": c["Campaign"], "Campaign ID": c["Campaign ID"], "广告组": c["广告组"], "广告组 ID": c["广告组 ID"], "别名": name, "投放方式": c["投放方式"]}

    def prod(self, sku):
        p = self.P.get(sku)
        return {"SKU": p["卖家 SKU"], "ASIN": p["ASIN"], "SKU 别名": sku} if p else {"SKU": sku, "ASIN": "", "SKU 别名": sku}

    def asin(self, a):
        """定位里的自家子体占位（C04）换成显示用的 ASIN；别家的 b0demo 占位原样。"""
        hit = next((p["ASIN"] for p in self.P.values() if p.get("占位", "").upper() == a.upper()), None)
        return hit or a

    def kw_id(self, camp, kw, match):
        return "5" + str(int(hashlib.sha1(f"{camp}|{kw}|{match}".encode()).hexdigest(), 16))[:14] if self.on else ""

    def tg_id(self, camp, expr):
        return "6" + str(int(hashlib.sha1(f"{camp}|{expr}".encode()).hexdigest(), 16))[:14] if self.on else ""

    def enrich(self, a):
        t, camp, obj, old, new = a["type"], a["campaign"], a["object"], a["old"], a["new"]
        f = {"实体": "", "操作": "", "改什么": "", "通道": "Amazon Ads API" if t in ADS_TYPES else ""}
        if camp and camp != "—": f.update(self.camp(camp.split("、")[0]))
        if "、" in (camp or ""): f["涉及活动"] = [self.camp(c)["Campaign"] for c in camp.split("、")]
        m = re.match(r"(.+)（(\w+)）$", obj or ""); kw, mt = (m.group(1), m.group(2)) if m else (obj, "")
        if t in ("暂停广告产品", "补挂广告产品"):
            f.update(self.prod(obj)); f.update({"实体": "Product Ad", "操作": "update" if t == "暂停广告产品" else "create", "改什么": "State",
                                                 "现值": "enabled" if t == "暂停广告产品" else "—", "新值": "paused" if t == "暂停广告产品" else "enabled"})
        elif t in ("下调预算", "预算上调"):
            f.update({"实体": "Campaign", "操作": "update", "改什么": "Daily Budget", "现值": f"${money(old)}", "新值": f"${money(new)}"})
        elif t == "改竞价策略":
            f.update({"实体": "Campaign", "操作": "update", "改什么": "Bidding Strategy", "现值": old, "新值": new})
        elif t == "下调默认竞价":
            f.update({"实体": "Ad Group", "操作": "update", "改什么": "Ad Group Default Bid", "现值": f"${money(old)}", "新值": f"${money(new)}"})
        elif t in KW_BID:
            f.update({"实体": "Keyword", "操作": "update", "改什么": "Bid", "关键词": kw, "匹配": MATCH.get(mt, mt), "关键词 ID": self.kw_id(camp, kw, mt), "现值": f"${money(old)}", "新值": f"${money(new)}"})
        elif t == "暂停关键词":
            f.update({"实体": "Keyword", "操作": "update", "改什么": "State", "关键词": kw, "匹配": MATCH.get(mt, mt), "关键词 ID": self.kw_id(camp, kw, mt), "现值": "enabled", "新值": "paused"})
        elif t in TG_BID or t in TG_PAUSE:
            e = AUTO_EXPR.get(obj) or re.sub(r'asin="([^"]+)"', lambda m_: f'asin="{self.asin(m_.group(1))}"', obj)
            f.update({"实体": "Product Targeting", "操作": "update", "改什么": "Bid" if t in TG_BID else "State", "定位": e, "定位 ID": self.tg_id(camp, obj),
                      "现值": f"${money(old)}" if t in TG_BID else "enabled", "新值": f"${money(new)}" if t in TG_BID else "paused"})
        elif t in NEG_KW:
            f.update({"实体": "Negative Keyword", "操作": "create", "改什么": "否定关键词", "关键词": obj, "匹配": "精确否定", "现值": "—", "新值": "enabled"})
        elif t == "否定 ASIN":
            f.update({"实体": "Negative Product Targeting", "操作": "create", "改什么": "否定商品定位", "定位": obj, "现值": "—", "新值": "enabled"})
        elif t in ("竞品词降价单独跑", "搜索词收割"):
            f.update(self.camp(camp if t == "搜索词收割" else self.exact)); f.update({"实体": "Keyword", "操作": "create", "改什么": "Bid", "关键词": obj, "匹配": "精确", "现值": "—" if t == "搜索词收割" else old, "新值": f"${money(new)}"})
        elif t == "交回运营判断":
            f.update({"实体": "Negative Keyword", "操作": "待定", "改什么": "全活动补否 / 撤回否定", "关键词": obj, "匹配": "精确否定", "通道": "人工判断"})
        elif t == "广告位待补数据":
            f.update({"实体": "Bidding Adjustment", "操作": "不动", "改什么": "广告位加价（缺广告位报表，没出规则）", "现值": old, "新值": new, "通道": "人工判断"})
        elif t == "Listing 建议稿":
            f.update({"实体": "Listing", "操作": "建议稿", "改什么": "规格表 · 主图", "ASIN": self.parent, "通道": "SP-API · Listing", "现值": old, "新值": new})
        elif t == "查证":
            f.update({"实体": "补货单" if obj == "补货到仓日期" else "Campaign", "操作": "回填", "改什么": obj, "ASIN": self.parent if obj == "补货到仓日期" else "",
                      "通道": "领星 ERP" if obj == "补货到仓日期" else "人工判断"})
        return f


# 导出成广告后台批量上传表的列（Ads API 通道）。一行一个实体；没用到的列留空，和后台模板一样
BULK_COLS = ["Product", "Entity", "Operation", "Campaign ID", "Ad Group ID", "Keyword ID", "Product Targeting ID", "Campaign Name (Informational only)", "Ad Group Name (Informational only)",
             "SKU", "ASIN (Informational only)", "Keyword Text", "Match Type", "Product Targeting Expression", "State", "Daily Budget", "Ad Group Default Bid", "Bid", "Bidding Strategy", "动作编号", "依据"]
_MT = {"精确": "exact", "词组": "phrase", "广泛": "broad", "精确否定": "negativeExact"}


def bulk_row(a, f):
    ent, what, new = f.get("实体", ""), f.get("改什么", ""), f.get("新值", "")
    val = lambda w: new.lstrip("$") if what == w else ""
    camp_lvl = ent == "Campaign"
    # State 列：只有改状态、或新建实体时才填；只改竞价/预算的行留空，免得上传时顺手改了状态
    st = new if what == "State" else ("enabled" if f.get("操作") == "create" else "")
    return ["Sponsored Products", ent, f.get("操作", ""), f.get("Campaign ID", ""), "" if camp_lvl else f.get("广告组 ID", ""), f.get("关键词 ID", ""), f.get("定位 ID", ""),
            f.get("Campaign", ""), "" if camp_lvl else f.get("广告组", ""), f.get("SKU", ""), f.get("ASIN", ""), f.get("关键词", ""), _MT.get(f.get("匹配", ""), ""), f.get("定位", ""),
            st, val("Daily Budget"), val("Ad Group Default Bid"), val("Bid"), STRATEGY_BULK.get(new, "") if what == "Bidding Strategy" else "", a["no"], a["why"]]
