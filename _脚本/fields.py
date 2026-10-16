# -*- coding: utf-8 -*-
"""把一条动作翻成广告后台认得的字段：实体、操作、Campaign / 广告组（名称与 ID）、SKU / ASIN、关键词 / 匹配 / 关键词 ID、改哪个字段。
只用标准库。名称与 ID 取自 <数据目录>/显示映射.json（演示数据才有）；没有这个文件时原样显示原名、ID 留空。"""
import hashlib, json, os, re

MATCH = {"exact": "精确", "phrase": "词组", "broad": "广泛", "negativeExact": "精确否定"}
def money(v):
    try: return f"{float(v):g}"
    except (TypeError, ValueError): return v


ADS_TYPES = {"暂停广告产品", "补挂广告产品", "下调预算", "降竞价", "换道否定", "竞品词否定", "竞品词降价单独跑", "粗规则否词"}


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

    def kw_id(self, camp, kw, match):
        return "5" + str(int(hashlib.sha1(f"{camp}|{kw}|{match}".encode()).hexdigest(), 16))[:14] if self.on else ""

    def enrich(self, a):
        t, camp, obj, old, new = a["type"], a["campaign"], a["object"], a["old"], a["new"]
        f = {"实体": "", "操作": "", "改什么": "", "通道": "Amazon Ads API" if t in ADS_TYPES else ""}
        if camp and camp != "—": f.update(self.camp(camp.split("、")[0]))
        if "、" in (camp or ""): f["涉及活动"] = [self.camp(c)["Campaign"] for c in camp.split("、")]
        if t in ("暂停广告产品", "补挂广告产品"):
            f.update(self.prod(obj)); f.update({"实体": "Product Ad", "操作": "update" if t == "暂停广告产品" else "create", "改什么": "State",
                                                 "现值": "enabled" if t == "暂停广告产品" else "—", "新值": "paused" if t == "暂停广告产品" else "enabled"})
        elif t == "下调预算":
            f.update({"实体": "Campaign", "操作": "update", "改什么": "Daily Budget", "现值": f"${money(old)}", "新值": f"${money(new)}"})
        elif t == "降竞价":
            m = re.match(r"(.+)（(\w+)）$", obj); kw, mt = (m.group(1), m.group(2)) if m else (obj, "")
            f.update({"实体": "Keyword", "操作": "update", "改什么": "Bid", "关键词": kw, "匹配": MATCH.get(mt, mt), "关键词 ID": self.kw_id(camp, kw, mt), "现值": f"${money(old)}", "新值": f"${money(new)}"})
        elif t in ("换道否定", "竞品词否定", "粗规则否词"):
            f.update({"实体": "Negative Keyword", "操作": "create", "改什么": "否定关键词", "关键词": obj, "匹配": "精确否定", "现值": "—", "新值": "enabled"})
        elif t == "竞品词降价单独跑":
            f.update(self.camp(self.exact)); f.update({"实体": "Keyword", "操作": "create", "改什么": "Bid", "关键词": obj, "匹配": "精确", "现值": old, "新值": new})
        elif t == "交回运营判断":
            f.update({"实体": "Negative Keyword", "操作": "待定", "改什么": "全活动补否 / 撤回否定", "关键词": obj, "匹配": "精确否定", "通道": "人工判断"})
        elif t == "Listing 建议稿":
            f.update({"实体": "Listing", "操作": "建议稿", "改什么": "规格表 · 主图", "ASIN": self.parent, "通道": "SP-API · Listing", "现值": old, "新值": new})
        elif t == "查证":
            f.update({"实体": "补货单" if obj == "补货到仓日期" else "Campaign", "操作": "回填", "改什么": obj, "ASIN": self.parent if obj == "补货到仓日期" else "",
                      "通道": "领星 ERP" if obj == "补货到仓日期" else "人工判断"})
        return f


# 导出成广告后台批量上传表的列（Ads API 通道）
BULK_COLS = ["Product", "Entity", "Operation", "Campaign ID", "Ad Group ID", "Keyword ID", "Campaign Name (Informational only)", "Ad Group Name (Informational only)",
             "SKU", "ASIN (Informational only)", "Keyword Text", "Match Type", "State", "Bid", "Daily Budget", "动作编号", "依据"]
_MT = {"精确": "exact", "词组": "phrase", "广泛": "broad", "精确否定": "negativeExact"}


def bulk_row(a, f):
    st = "paused" if f.get("新值") == "paused" else "enabled"
    bid = f["新值"].lstrip("$") if f.get("改什么") == "Bid" else ""
    bud = f["新值"].lstrip("$") if f.get("改什么") == "Daily Budget" else ""
    return ["Sponsored Products", f.get("实体", ""), f.get("操作", ""), f.get("Campaign ID", ""), f.get("广告组 ID", "") if f.get("实体") != "Campaign" else "", f.get("关键词 ID", ""),
            f.get("Campaign", ""), f.get("广告组", "") if f.get("实体") != "Campaign" else "", f.get("SKU", ""), f.get("ASIN", ""), f.get("关键词", ""), _MT.get(f.get("匹配", ""), ""),
            st, bid, bud, a["no"], a["why"]]
