# -*- coding: utf-8 -*-
"""生成学员实操手册。用法：python3 _脚本/make_handbook.py            → 实操手册.html（图片相对路径）
                       python3 _脚本/make_handbook.py --embed 出.html → 单文件版（图片内嵌，可单独发人）"""
import base64, html, io, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); E = html.escape
EMBED = "--embed" in sys.argv; OUT = sys.argv[sys.argv.index("--embed") + 1] if EMBED else f"{ROOT}/实操手册.html"
def img(f, cap):
    src = f"截图/手册/{f}"
    if EMBED: src = "data:image/png;base64," + base64.b64encode(open(f"{ROOT}/截图/手册/{f}", "rb").read()).decode()
    return f'<img class="shot" src="{src}" alt="{E(cap)}"><p class="cap">{cap}</p>'
def say(t, lab="对 Codex 说"): return f'<div class="say"><span class="lab">{lab}</span><button onclick="cp(this)">复制</button><pre>{E(t)}</pre></div>'
def do(t): return f'<div class="say do"><span class="lab">在工作台上做</span><pre>{E(t)}</pre></div>'
def see(t): return f'<p class="see"><span class="lab">应该看到</span>{t}</p>'
def stuck(t): return f"<details><summary>卡住了</summary><p>{t}</p></details>"
def step(no, title, mins, *parts): return f'<section class="step"><div class="no">{no}</div><div class="c"><h3>{title}<span class="tm">约 {mins} 分钟</span></h3>{"".join(parts)}</div></section>'
p = lambda t: f"<p>{t}</p>"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from handbook_steps import build
R1, R2, PAGE, FILES = build(step, img, say, do, see, stuck, p)

CSS = """:root{--bg:#faf9f6;--fg:#1f1e1c;--mut:#6b675f;--line:#e3e0d8;--card:#fff;--acc:#b4532a;--say:#f3efe6}
@media(prefers-color-scheme:dark){:root{--bg:#191817;--fg:#ece9e2;--mut:#a09b90;--line:#34322e;--card:#22211f;--acc:#e08a5f;--say:#2a2825}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 16px 80px}h1{font-size:28px;margin:0 0 8px}h2{font-size:20px;margin:44px 0 14px;padding-top:18px;border-top:2px solid var(--fg)}
h3{font-size:17px;margin:0 0 4px}p{margin:6px 0}.lead{color:var(--mut)}.tm{font-weight:400;color:var(--mut);font-size:14px;margin-left:8px}
.rule{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:8px;padding:12px 16px;margin:18px 0}.rule ul{margin:6px 0 0 18px;padding:0}.rule li{margin:3px 0}
.step{display:flex;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
.no{flex:0 0 36px;height:36px;border-radius:50%;background:var(--fg);color:var(--bg);display:grid;place-items:center;font-weight:700}
.c{flex:1;min-width:0}.say{position:relative;background:var(--say);border-radius:8px;padding:10px 12px;margin:10px 0}.say.do{background:transparent;border:1px dashed var(--line)}
.say pre{margin:4px 0 0;white-space:pre-wrap;word-break:break-word;font:14.5px/1.65 inherit}
.lab{font-size:12px;font-weight:700;color:var(--acc);letter-spacing:.05em;margin-right:8px}
button{position:absolute;top:8px;right:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;padding:2px 10px;font-size:12px;cursor:pointer}
details{margin-top:6px;color:var(--mut);font-size:14.5px}summary{cursor:pointer}code{background:var(--say);padding:1px 5px;border-radius:4px;font-size:.9em}
table{border-collapse:collapse;width:100%;font-size:14.5px;margin:10px 0}td,th{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
img.shot{display:block;width:100%;border:1px solid var(--line);border-radius:8px;margin:10px 0 2px}.cap{font-size:13px;color:var(--mut);margin:0 0 10px}
.toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;margin:8px 0 0}.toc a{color:var(--acc);text-decoration:none}"""
HEAD = f'<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>广告实操手册 · Codex 版</title><style>{CSS}</style></head>'
BODY = f"""<body><main>
<h1>广告实操手册 · Codex 版</h1>
<p class="lead">从一份广告报表，到一张有人点头、有日期、能复盘的动作清单。全程不花钱，不用任何付费接口，不连广告后台。</p>
<div class="toc"><a href="#p0">先认识页面</a><a href="#r1">第一轮 · 示例（40 分钟）</a><a href="#pass">第一轮过线自查</a><a href="#r2">第二轮 · 自己的产品（90 分钟）</a><a href="#no">四条不许</a><a href="#faq">常见问题</a><a href="#terms">术语</a><a href="#files">文件地图</a></div>
<div class="rule"><b>怎么用这份手册：</b>每一步都是「对 Codex 说一句话，或在工作台上点一下 → 看它做 → 对照应该看到什么」。你不用敲命令，但每一步<b>你要看、要定</b>。每步标了大约要几分钟。</div>
<table><tr><th>谁干</th><th>干什么</th></tr>
<tr><td>脚本</td><td>算账、对目标找异常、按规则出动作、验证器、写状态库、出报告</td></tr>
<tr><td>AI（Codex）</td><td>读搜索词做语义分组；事实、推断、未知分开写；摆选项和代价；起草行动卡</td></tr>
<tr><td>你</td><td>填目标和约束、定分组规则、做取舍、逐条确认或驳回、去后台执行、到日子复盘</td></tr></table>

<h2 id="p0">先认识页面（1 分钟）</h2>
{PAGE}

<h2 id="r1">第一轮 · 用示例跑通（约 40 分钟，人人都做）</h2>{"".join(R1)}
<div class="rule" id="pass"><b>第一轮过线自查</b>（对应课上的五样：立项卡／两轮产出／一条异常处理／老板判断／下次怎么触发）<ul>
<li>你能对着 ① 说出三个输入分别是谁给的、为什么是这个数 —— 立项卡</li>
<li>运行历史里至少有 v1、v2 两圈，第二圈是改了输入后跑的 —— 两轮产出</li>
<li>第 8 步那次「遇到问题」在操作记录里，上一份结果没被覆盖 —— 一条异常处理</li>
<li>至少一条驳回，理由是你写的，而且它在下一圈没有再提 —— 老板判断</li>
<li>你能说出行动卡第 9 格里下次什么时候跑、看哪几个数 —— 下次怎么触发</li></ul></div>

<h2 id="r2">第二轮 · 换成你自己的产品（约 90 分钟，带了报表的学员做）</h2>{"".join(R2)}

<h2 id="no">四条不许（Codex 犯了就叫停）</h2>
<div class="rule">① 不许自己算数字，数字只从脚本产出里取。② 不许替你做取舍，也不许替你填「目标与约束」和分组规则。③ 样本不够的词不许否，出过单的词和自家品牌词永远不许否。④ 不许碰广告后台：动钱的动作一律停在「待确认」，上传是人做。</div>

<h2 id="faq">常见问题</h2>
<table><tr><th>现象</th><th>怎么办</th></tr>
<tr><td>页面打不开或空白</td><td>终端里那个进程是不是还在；不在就重新 <code>python3 工作台/app.py</code>。刷新一次。</td></tr>
<tr><td>Address already in use</td><td>端口被占，加 <code>--port 8811</code>。</td></tr>
<tr><td>Operation not permitted</td><td>仓库放在桌面或文稿下了，挪到 ~/ads-lab。</td></tr>
<tr><td>「跑一圈」按钮是灰的</td><td>上一圈还在跑；等一下。一直灰就刷新。</td></tr>
<tr><td>点通过没反应，提示没有权限</td><td>右上角「当前身份」不对：老板和广告运营能点动作，只有老板能改取舍和目标，供应链只能改到仓周数。</td></tr>
<tr><td>改了输入它没重跑</td><td>没点「保存，任务回到「待处理」」；或者第 2 格写了「输入没变」。</td></tr>
<tr><td>想回到刚开始的样子</td><td>右上角「重置」。它删的是状态库（谁点过什么），不删数据文件。</td></tr>
<tr><td>演示数据和自己的数据想同时看</td><td>演示在 8810，自己的在 8811，两个进程各开各的。</td></tr>
<tr><td>Codex 每条命令都要我批准</td><td>正常，点同意；嫌烦可以选「本次会话都允许」。</td></tr></table>

<h2 id="terms">术语</h2>
<table><tr><th>词</th><th>意思</th></tr>
<tr><td>ACOS</td><td>广告花费 ÷ 广告带来的销售额。只看广告这一笔。</td></tr>
<tr><td>TACOS</td><td>广告花费 ÷ 总销售额（含自然单）。看广告占整个生意的比重。</td></tr>
<tr><td>盈亏线</td><td>广告前毛利率。ACOS 超过它，这一单就是亏的。</td></tr>
<tr><td>归因未满</td><td>亚马逊按点击后 7 天算订单，最近几天的订单还没记全，所以偏少。</td></tr>
<tr><td>同词多活动</td><td>同一个搜索词被三个以上活动同时买，自己跟自己抢流量。</td></tr>
<tr><td>换道否定</td><td>不是不要这个词，是在跑偏的那个活动里把它否掉，让它回到主干活动去跑。</td></tr>
<tr><td>可售周数</td><td>可售库存 ÷ 上周销量。小于补货到仓周数，就是要断货。</td></tr>
<tr><td>头部词</td><td>近 14 天花费最高的四个搜索词。</td></tr>
<tr><td>诊断树</td><td>异常 → 分析 → 对策 → 动作的连线；一个异常可以引出多个分析，一个对策可以综合多个分析。</td></tr>
<tr><td>执行通道</td><td>动作最终交给谁执行：Amazon Ads API、SP-API Listing、领星 ERP、人工判断。没接通的通道，导出批量上传表由人上传。</td></tr>
<tr><td>批量上传表</td><td>广告后台「批量操作」认的 CSV：Entity／Operation／Campaign ID／Ad Group ID／Keyword Text／Match Type／State／Bid／Daily Budget。</td></tr>
<tr><td>请复核</td><td>人确认过、但新输入下规则不再建议的动作；系统不替你撤，只标出来。</td></tr>
<tr><td>待确认 / 已确认 / 已执行 / 已验证 / 驳回 / 作废</td><td>动作的六种状态。Agent 只会生成「待确认」；后面每一步都是人点的；「作废」是输入变了之后，没人点过的旧动作自动退场。</td></tr></table>

<h2 id="files">文件地图</h2>
{FILES}
<p class="lead">包的地址：github.com/WaytoAIC/ads-workbench　·　示例数据是脱敏并替换过品类的演示数据，没有一个数是真实值</p>
</main><script>function cp(b){{navigator.clipboard.writeText(b.nextElementSibling.innerText).then(()=>{{b.textContent="已复制";setTimeout(()=>b.textContent="复制",1200)}})}}</script></body></html>"""
io.open(OUT, "w", encoding="utf-8").write(HEAD + BODY); print("写出", OUT, len(HEAD + BODY), "字符")
