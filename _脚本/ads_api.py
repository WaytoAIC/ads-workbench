#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Amazon Ads API 适配器（统一版 v1）。只用标准库。默认什么都不发；读要人点，写要人点两次。

走哪条路：本机的紫鸟代理 `zn-open-eco http … --module amazon-ads-api`（店铺在紫鸟里授权过 Amazon Ads API 才能用）。
  读：POST /adsApi/v1/query/{campaigns|adGroups|targets|ads}，GET /v2/profiles
  写：POST /adsApi/v1/{update|create}/{campaigns|adGroups|targets|ads}
每次 http 调用耗紫鸟积分（读也算）。

三个命令：
  python3 _脚本/ads_api.py check              连一次：授权 → 广告账号 → 各读一页活动。只记个数，不记名字和编号
  python3 _脚本/ads_api.py preview            把「已通过」的动作翻成接口请求，只打印不发
  python3 _脚本/ads_api.py execute <动作编号> --yes "<确认的话>"    发一条、回读一次；只对实测过的几类开放

规矩（照已经真实跑通的那套做法）：
  1. 店铺身份逐层核对：紫鸟店铺 → 广告授权 → 广告账号的国家和币种，对不上就停。
  2. 写之前先读一次现值，和动作上记的不一样就不发（后台已经被人改过）。
  3. 一条动作只提交一次；结果不明不重发，标「待核实」交人。
  4. 写完独立回读，回读对上才算「已执行」。
  5. 只用暂停，不用归档／删除。
配置：本机 agent/.env.local（不进仓）里写 ADS_STORE_NAME（紫鸟里的店铺名关键词）、ADS_COUNTRY（US／UK／DE…）；ads.config.json 的 ads_api.enabled 为真才允许 execute。"""
import argparse, datetime, json, os, shutil, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = {"US": "na", "CA": "na", "MX": "na", "BR": "na", "UK": "eu", "GB": "eu", "DE": "eu", "FR": "eu", "IT": "eu", "ES": "eu", "NL": "eu", "SE": "eu", "PL": "eu", "JP": "fe", "AU": "fe", "SG": "fe"}
KINDS = {"campaigns": "campaignId", "adGroups": "adGroupId", "targets": "targetId", "ads": "adId"}
STRATEGY = {"固定竞价": "MANUAL", "动态竞价-只降低": "SALES_DOWN_ONLY", "动态竞价-提高和降低": "SALES_UP_AND_DOWN"}
MATCH = {"精确": "EXACT", "词组": "PHRASE", "广泛": "BROAD", "exact": "EXACT", "phrase": "PHRASE", "broad": "BROAD"}

# 动作类型 → (路由, 改的是什么, 在真实店铺上跑通过没有)。「跑通过」＝真实提交并独立回读成功过；其余是同一套接口、按官方字段起草、没在真实店铺上发过。
ROUTES = {
    "暂停广告产品": ("update/ads", "商品广告的状态 → 暂停", True),
    "暂停关键词": ("update/targets", "关键词的状态 → 暂停", True),
    "否定 ASIN": ("create/targets", "在广告组里新增一条否定商品", True),
    "暂停 ASIN 定位": ("update/targets", "商品定位的状态 → 暂停", False), "暂停 类目定位": ("update/targets", "类目定位的状态 → 暂停", False), "关闭自动投放组": ("update/targets", "自动投放某一组的状态 → 暂停", False),
    "降竞价": ("update/targets", "关键词的竞价", False), "关键词降竞价": ("update/targets", "关键词的竞价", False), "关键词提竞价": ("update/targets", "关键词的竞价", False),
    "ASIN 定位降竞价": ("update/targets", "商品定位的竞价", False), "ASIN 定位提竞价": ("update/targets", "商品定位的竞价", False), "类目定位降竞价": ("update/targets", "类目定位的竞价", False), "类目定位提竞价": ("update/targets", "类目定位的竞价", False),
    "自动投放组降竞价": ("update/targets", "自动投放某一组的竞价", False), "自动投放组提竞价": ("update/targets", "自动投放某一组的竞价", False),
    "下调预算": ("update/campaigns", "活动的日预算", False), "预算上调": ("update/campaigns", "活动的日预算", False), "改竞价策略": ("update/campaigns", "活动的竞价策略", False),
    "下调默认竞价": ("update/adGroups", "广告组的默认竞价", False),
    "补挂广告产品": ("create/ads", "在广告组里新增一条商品广告", False),
    "搜索词收割": ("create/targets", "新增一个精确关键词并出价", False), "竞品词降价单独跑": ("create/targets", "新增一个精确关键词并出价", False),
    "换道否定": ("create/targets", "新增一条否定关键词（精确）", False), "来源组否定": ("create/targets", "新增一条否定关键词（精确）", False), "竞品词否定": ("create/targets", "新增一条否定关键词（精确）", False), "粗规则否词": ("create/targets", "新增一条否定关键词（精确）", False),
}
PROVEN = {k for k, v in ROUTES.items() if v[2]}


class AdsError(RuntimeError):
    pass


def jread(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError): return d


def local_env():
    env = {}
    try:
        for line in open(f"{REPO}/agent/.env.local", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip().strip("\"'")
    except OSError: pass
    return {**env, **{k: v for k, v in os.environ.items() if k.startswith("ADS_")}}


def settings(root):
    c = {"enabled": False, "通道": "紫鸟代理", "单次最多几条": 20}
    for p in (f"{REPO}/ads.config.json", f"{root}/ads.config.json"): c.update((jread(p) or {}).get("ads_api") or {})
    e = local_env(); c["store"] = e.get("ADS_STORE_NAME", ""); c["store_id"] = e.get("ADS_STORE_ID", ""); c["country"] = (e.get("ADS_COUNTRY") or "US").upper()
    return c


def unwrap(v):
    """紫鸟代理的回包：业务错误一律当失败；带 data 的取 data。"""
    if isinstance(v, dict):
        if v.get("success") is False or v.get("errors") or v.get("error_code", 0) != 0 or v.get("ret", 0) != 0 or v.get("code", 200) not in (0, 200):
            raise AdsError("接口回了业务错误：" + str(v.get("message") or v.get("msg") or v.get("ret") or v.get("code"))[:160])
        if "data" in v and ("code" in v or "error_code" in v or "ret" in v): return v["data"]
    return v


class Channel:
    """一次连接：先认清是哪个店、哪个广告账号，之后的读写都带着这个身份。transport 可以换成假的做测试。"""
    def __init__(self, cfg, transport=None):
        self.cfg, self.calls, self.t = cfg, 0, transport or self._cli; self.account = self.region = self.profile = None

    @staticmethod
    def _cli(args):
        exe = shutil.which("zn-open-eco") or "/opt/homebrew/bin/zn-open-eco"
        if not os.path.exists(exe): raise AdsError("没找到 zn-open-eco：这条路要先装紫鸟的命令行并登录")
        p = subprocess.run([exe] + args, capture_output=True, text=True, timeout=60)
        if p.returncode: raise AdsError("紫鸟命令行执行失败：" + (p.stderr.strip().splitlines() or ["?"])[-1][:160])
        out = p.stdout; i = min([x for x in (out.find("{"), out.find("[")) if x >= 0] or [0])      # 命令行有时在 JSON 后面带一段提示文字，只取 JSON
        return json.JSONDecoder().raw_decode(out[i:])[0]

    def call(self, args): return unwrap(self.t(args))

    def http(self, method, path, body=None, scoped=True):
        if not self.account: raise AdsError("还没核对店铺身份")
        h = {"X-Account-Id": str(self.account), "Content-Type": "application/json", "Accept": "application/json"}
        if scoped: h["Amazon-Advertising-API-Scope"] = str(self.profile["profileId"])
        self.calls += 1
        return self.call(["http", method, f"/proxy/{self.region}{path}", "--module", "amazon-ads-api", "--headers", json.dumps(h)] + (["--body", json.dumps(body, ensure_ascii=False)] if body is not None else []))

    def identify(self):
        c = self.cfg; country = c["country"]; self.region = REGION.get(country)
        if not c.get("store"): raise AdsError("没配店铺：在 agent/.env.local 里写 ADS_STORE_NAME=紫鸟里的店铺名")
        if not self.region: raise AdsError(f"不认识的站点 {country}")
        stores = [s for s in (self.call(["account", "stores", "--store-name", c["store"]]) or []) if isinstance(s, dict)]
        if not stores: raise AdsError(f"紫鸟里按「{c['store']}」没找到店铺")
        ids = {str(s.get("store_id") or s.get("browser_id")) for s in stores}
        if c.get("store_id"): ids &= {str(c["store_id"])}              # 同名店铺不止一个时，在 agent/.env.local 里用 ADS_STORE_ID 指定
        auths = [a for a in (self.call(["account", "platform-auths", "--platform-type", "amazon-ads-api"]) or []) if isinstance(a, dict)]
        ok = [a for a in auths if str(a.get("seller_account_id")) in ids and str(a.get("region", "")).lower() == self.region and a.get("auth_status") == 1]
        if len(ok) != 1: raise AdsError(f"按「{c['store']}」找到 {len(stores)} 个店铺，其中在 {self.region.upper()} 大区有有效 Amazon Ads 授权的是 {len(ok)} 个，要正好 1 个（不止一个就在 agent/.env.local 里加 ADS_STORE_ID）")
        self.account = ok[0]["seller_account_id"]                    # 同名的几个店里，只认在这个大区授权过广告接口的那一个
        profiles = self.http("GET", "/v2/profiles", scoped=False)
        cc = "UK" if country == "GB" else country
        mine = [p for p in profiles if isinstance(p, dict) and p.get("countryCode") == cc and (p.get("accountInfo") or {}).get("type") == "seller"]
        if len(mine) != 1: raise AdsError(f"{cc} 站的卖家广告账号找到 {len(mine)} 个，要正好 1 个")
        self.profile = mine[0]; return self

    def query(self, kind, flt=None, pages=20):
        if kind not in KINDS: raise AdsError("只能读活动、广告组、投放对象、广告")
        body = {"adProductFilter": {"include": ["SPONSORED_PRODUCTS"]}, "stateFilter": {"include": ["ENABLED", "PAUSED", "ARCHIVED"]}, "maxResults": 100, **(flt or {})}
        rows, seen, tokens = [], set(), set()
        for _ in range(pages):
            r = self.http("POST", f"/adsApi/v1/query/{kind}", body)
            if not isinstance(r, dict) or not isinstance(r.get(kind), list): raise AdsError(f"读{kind}的回包不是预期的样子")
            for x in r[kind]:
                k = str(x.get(KINDS[kind]) or "")
                if not k or k in seen: raise AdsError("回包里有重复或没有编号的对象")
                seen.add(k); rows.append(x)
            tok = r.get("nextToken")
            if not tok: return rows, True
            if tok in tokens: raise AdsError("翻页卡住了")
            tokens.add(tok); body["nextToken"] = tok
        return rows, False


STATE = {"ENABLED": "投放中", "PAUSED": "已暂停", "ARCHIVED": "已归档"}


def count(rows):
    out = {}
    for r in rows: k = STATE.get(r.get("state"), str(r.get("state", "?"))); out[k] = out.get(k, 0) + 1
    return out


def check(root, transport=None, save=True):
    """连一次，只留个数：不存名字、不存编号。"""
    cfg = settings(root); ch = Channel(cfg, transport); now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc = {"时间": now, "通道": cfg["通道"], "站点": cfg["country"], "步骤": [], "ok": False}
    def step(name, ok, note): doc["步骤"].append({"名": name, "ok": ok, "说明": note})
    try:
        ch.identify(); p = ch.profile
        step("店铺和广告授权", True, f"紫鸟里的店铺对上了，{ch.region.upper()} 大区的 Amazon Ads 授权有效")
        step("广告账号", True, f"{p.get('countryCode')} 站卖家账号，币种 {p.get('currencyCode')}，时区 {p.get('timezone', '—')}")
        camps, full = ch.query("campaigns", pages=3); step("读活动", True, f"读到 {len(camps)} 个 SP 活动{'' if full else '（只读了前 300 个）'}：" + "、".join(f"{k} {v}" for k, v in count(camps).items()))
        live = [c for c in camps if c.get("state") == "ENABLED"] or camps
        if live:
            cid = str(live[0]["campaignId"]); f = {"campaignIdFilter": {"include": [cid]}}
            groups, _ = ch.query("adGroups", f, pages=1); step("读广告组", True, f"取其中一个活动：{len(groups)} 个广告组")
            if groups:
                f2 = {**f, "adGroupIdFilter": {"include": [str(groups[0]["adGroupId"])]}}
                tg, _ = ch.query("targets", f2, pages=1); neg = sum(1 for t in tg if t.get("negative")); kw = sum(1 for t in tg if t.get("targetType") == "KEYWORD" and not t.get("negative"))
                step("读投放对象", True, f"其中一个广告组：{len(tg)} 个投放对象（关键词 {kw}、否定 {neg}、其他 {len(tg) - kw - neg}）")
                ads, _ = ch.query("ads", f2, pages=1); step("读商品广告", True, f"同一个广告组：{len(ads)} 条商品广告：" + "、".join(f"{k} {v}" for k, v in count(ads).items()))
        doc["ok"] = True
    except AdsError as e: step("没走通", False, str(e))
    except Exception as e: step("没走通", False, f"{type(e).__name__}")
    doc["调用次数"] = ch.calls
    if save:
        os.makedirs(f"{root}/运行记录", exist_ok=True); json.dump(doc, open(f"{root}/运行记录/ads-api-连通.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return doc


# ------------------------------------------------------------------ 动作 → 接口请求
def build(a, f, currency="USD"):
    """a：动作清单里的一行（type/old/new/object…）；f：fields.py 翻好的后台字段。返回 (路由, 请求体, 缺什么[])。"""
    t = a["type"]; route = ROUTES[t][0]; miss = []; need = lambda k: f.get(k) or miss.append(k) or f"<缺 {k}>"
    num = lambda v: float(str(v).lstrip("$").replace(",", "")) if str(v).lstrip("$").replace(",", "").replace(".", "", 1).isdigit() else (miss.append("新值不是数") or None)
    sp = {"adProduct": "SPONSORED_PRODUCTS"}
    if t == "暂停广告产品": body = {"ads": [{"adId": need("广告 ID"), "state": "PAUSED"}]}
    elif t == "补挂广告产品": body = {"ads": [{**sp, "adGroupId": need("广告组 ID"), "adType": "PRODUCT_AD", "state": "ENABLED", "creative": {"productCreative": {"productCreativeSettings": {"advertisedProduct": {"productIdType": "SKU", "productId": need("SKU")}}}}}]}
    elif t in ("下调预算", "预算上调"): body = {"campaigns": [{"campaignId": need("Campaign ID"), "budgets": [{"budgetType": "MONETARY", "recurrenceTimePeriod": "DAILY", "budgetValue": {"monetaryBudgetValue": {"monetaryBudget": {"currencyCode": currency, "value": num(a["new"])}}}}]}]}
    elif t == "改竞价策略": body = {"campaigns": [{"campaignId": need("Campaign ID"), "optimizations": {"bidSettings": {"bidStrategy": STRATEGY.get(str(a["new"])) or miss.append("认不出的竞价策略") or str(a["new"])}}}]}
    elif t == "下调默认竞价": body = {"adGroups": [{"adGroupId": need("广告组 ID"), "bid": {"defaultBid": num(a["new"])}}]}
    elif route == "update/targets":
        tid = f.get("关键词 ID") or f.get("定位 ID") or miss.append("投放对象 ID") or "<缺 投放对象 ID>"
        body = {"targets": [{"targetId": tid, **({"state": "PAUSED"} if ("暂停" in t or "关闭" in t) else {"bid": {"bid": num(a["new"])}})}]}
    elif t in ("搜索词收割", "竞品词降价单独跑"):
        body = {"targets": [{**sp, "campaignId": need("Campaign ID"), "adGroupId": need("广告组 ID"), "negative": False, "state": "ENABLED", "targetType": "KEYWORD", "targetLevel": "AD_GROUP",
                             "targetDetails": {"keywordTarget": {"keyword": f.get("关键词") or a["object"], "matchType": "EXACT"}}, "bid": {"bid": num(a["new"])}}]}
    elif t == "否定 ASIN":
        body = {"targets": [{**sp, "campaignId": need("Campaign ID"), "adGroupId": need("广告组 ID"), "negative": True, "state": "ENABLED", "targetType": "PRODUCT", "targetLevel": "AD_GROUP",
                             "targetDetails": {"productTarget": {"matchType": "PRODUCT_EXACT", "product": {"productId": f.get("ASIN") or a["object"], "productIdType": "ASIN"}}}}]}
    else:                                                                    # 四类否定关键词
        body = {"targets": [{**sp, "campaignId": need("Campaign ID"), "adGroupId": need("广告组 ID"), "negative": True, "state": "ENABLED", "targetType": "KEYWORD", "targetLevel": "AD_GROUP",
                             "targetDetails": {"keywordTarget": {"keyword": f.get("关键词") or a["object"], "matchType": "EXACT"}}}]}
    return route, body, [m for m in miss if m]


def preview(root, status="已确认", types=None):
    """把某个状态的广告类动作翻成请求。不联网、不花积分。演示数据的编号是生成的，一律标「不能发」。"""
    import sqlite3
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fields as FIELDS
    P = jread(f"{root}/参数.json") or {}; MP = FIELDS.Mapper(root, P); demo = MP.on; out = []
    c = sqlite3.connect(f"file:{root}/工作台.db?mode=ro", uri=True); c.row_factory = sqlite3.Row
    for r in c.execute("SELECT * FROM action WHERE status=? ORDER BY no", (status,)):
        a = dict(r)
        if a["type"] not in ROUTES or (types and a["type"] not in types): continue
        f = MP.enrich(a); route, body, miss = build(a, f)
        why = "演示数据：活动、广告组、关键词的编号是按格式生成的，真实账号里没有这些对象" if demo else ("缺：" + "、".join(miss) if miss else ("" if a["type"] in PROVEN else "这一类还没在真实店铺上发过，先只预演"))
        out.append({"动作编号": a["no"], "类型": a["type"], "改什么": ROUTES[a["type"]][1], "路由": "POST /adsApi/v1/" + route, "请求体": body, "跑通过": a["type"] in PROVEN, "能发": not why, "为什么不能发": why,
                    "发之前": "先读一次现值，和动作上记的不一样就不发", "发之后": "独立回读，对上了才标「已执行」"})
    return {"演示数据": demo, "状态": status, "条数": len(out), "请求": out}


def execute(root, no, confirm_text, transport=None):
    """一条动作：读现值 → 提交一次 → 独立回读。只开放实测过的几类；演示数据永远不发。"""
    cfg = settings(root)
    if not cfg.get("enabled"): raise AdsError("执行开关没开：ads.config.json 里 ads_api.enabled 是假的。现在只能预演")
    if not (confirm_text or "").strip(): raise AdsError("要人写一句确认的话才发")
    pv = preview(root, "已确认"); item = next((x for x in pv["请求"] if x["动作编号"] == no), None)
    if not item: raise AdsError("这条动作不在「已通过」里，或者不是广告类动作")
    if not item["能发"]: raise AdsError("这条不能发：" + item["为什么不能发"])
    ch = Channel(cfg, transport).identify(); route = item["路由"].split("/adsApi/v1/")[1]; kind = route.split("/")[1]; body = item["请求体"]; obj = body[kind][0]; idk = KINDS[kind]
    log = {"动作编号": no, "时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "确认的话": confirm_text, "路由": item["路由"], "结果": "待核实"}
    try:
        if route.startswith("update/"):
            before, _ = ch.query(kind, {idk + "Filter": {"include": [str(obj[idk])]}}, pages=1)
            if len(before) != 1: raise AdsError("发之前没读到这个对象，不发")
            if obj.get("state") == "PAUSED" and before[0].get("state") != "ENABLED": raise AdsError(f"它现在已经是 {before[0].get('state')}，不用再发")
            log["发之前"] = before[0].get("state")
        ch.http("POST", "/adsApi/v1/" + route, body); log["已提交"] = True                     # 只提交这一次
        flt = {idk + "Filter": {"include": [str(obj[idk])]}} if route.startswith("update/") else {"campaignIdFilter": {"include": [str(obj["campaignId"])]}, "adGroupIdFilter": {"include": [str(obj["adGroupId"])]}}
        after, _ = ch.query(kind, flt, pages=3)
        if route.startswith("update/"): ok = len(after) == 1 and all(after[0].get(k) == v for k, v in obj.items() if k in ("state",))
        else: ok = any(t.get("negative") is True and json.dumps(obj["targetDetails"], sort_keys=True) in json.dumps(t.get("targetDetails"), sort_keys=True) or (t.get("targetDetails") or {}) == obj["targetDetails"] for t in after)
        log["结果"] = "已执行并回读" if ok else "待核实"
    except AdsError as e:
        log["错误"] = str(e); log["结果"] = "待核实" if log.get("已提交") else "没发"
    os.makedirs(f"{root}/运行记录", exist_ok=True)
    with open(f"{root}/运行记录/ads-api-执行.jsonl", "a", encoding="utf-8") as fh: fh.write(json.dumps(log, ensure_ascii=False) + "\n")
    return log


def main():
    ap = argparse.ArgumentParser(description="Amazon Ads API 适配器：check 连通｜preview 预演｜execute 执行一条"); ap.add_argument("cmd", choices=["check", "preview", "execute"]); ap.add_argument("no", nargs="?")
    ap.add_argument("--root", default=os.environ.get("ADS_ROOT") or REPO); ap.add_argument("--status", default="已确认"); ap.add_argument("--yes", default="")
    a = ap.parse_args(); root = os.path.abspath(a.root)
    if a.cmd == "check":
        print("⚠️ 接下来的接口调用将消耗紫鸟积分（大约 5 次）。"); d = check(root)
        for s in d["步骤"]: print(("✓ " if s["ok"] else "✗ ") + s["名"] + "：" + s["说明"])
        print(f"调用 {d['调用次数']} 次 → 运行记录/ads-api-连通.json"); return 0 if d["ok"] else 1
    if a.cmd == "preview":
        d = preview(root, a.status); print(f"{d['状态']}的广告类动作 {d['条数']} 条" + ("（演示数据，只预演）" if d["演示数据"] else ""))
        for x in d["请求"][:8]: print(f"  {x['动作编号']} {x['类型']} → {x['路由']} {json.dumps(x['请求体'], ensure_ascii=False)[:150]}" + ("" if x["能发"] else f"　✗ {x['为什么不能发'][:30]}"))
        return 0
    try: r = execute(root, a.no or "", a.yes)
    except AdsError as e: print("没发：" + str(e)); return 2
    print(json.dumps(r, ensure_ascii=False)); return 0 if r["结果"] == "已执行并回读" else 1


if __name__ == "__main__":
    sys.exit(main())
