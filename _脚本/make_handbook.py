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

R1 = [
step(0, "开工前检查", 2,
  p("电脑上要有三样：Codex、Python 3（3.9 以上）、一个浏览器。工作台只用 Python 标准库加 pandas，不装别的。"),
  say("帮我检查这台电脑有没有 python3 和 pip，各是什么版本；再检查 python3 能不能 import pandas。缺哪个告诉我怎么装，先别动手装。"),
  see("python3 报出版本号（3.9 以上都行），pandas 能导入。"),
  stuck("缺 pandas：让它执行 <code>pip install pandas</code>（报权限错就加 <code>--user</code>）。Windows 学员：把后面所有 python3 都当成 python，其余一样。")),
step(1, "把工作台拿下来、跑起来", 5,
  p("<b>不要放在「桌面」或「文稿」下面</b>，Mac 会拦着后台进程不让读那里的文件。"),
  say("做三件事：\n1. 把 https://github.com/WaytoAIC/ads-workbench 克隆到 ~/ads-lab\n2. 确认 ~/ads-lab 里有 工作台/app.py、_脚本/、_原始拉取/、参数.json、分组规则.json\n3. 在 ~/ads-lab 下启动 python3 工作台/app.py，告诉我浏览器该打开哪个地址\n启动后这个进程要一直开着，别关；它只监听本机，不联网。"),
  see("它报出 <code>http://localhost:8810</code>。浏览器打开：顶栏写着「广告周检工作台」，右上角状态是「R-001 · 待处理」，页面中间一张卡「任务 R-001 已建好」和一个「跑第一圈」按钮。Mac 学员也可以直接双击仓库里的「启动工作台.command」。"),
  stuck("报 <code>Address already in use</code>：让它加 <code>--port 8811</code> 再起，地址跟着换。报 <code>Operation not permitted</code>：仓库放在了桌面或文稿下，挪到 ~/ads-lab 再来。页面空白：等两秒刷新；还空白就看终端有没有红字，贴给 Codex。")),
step(2, "跑第一圈，看六个格子", 3,
  p("数据是脱敏并替换过品类的演示数据（浴室防滑垫），不连任何广告后台；「跑一圈」只读本机文件。"),
  do("点右上角「跑第一圈」。"),
  see("顶上六个格子依次亮起：① 读取状态 → ② 判断下一步 → ③ 执行 → ④ 验证 → ⑤ 写入状态 → ⑥ 判断停止条件，一秒左右跑完。② 写「首次运行 → 跑 v1」；③ 写「读报表 → 分组账 → 异常 → 60 多条动作 → 行动卡 → 报告」；④ 写「验证器 7/7 项通过」；⑥ 写「停在「待核对」，等人处理」。顶栏状态变成「待核对 · v1」，下面长出六张指标卡和五个区块。点任何一格能展开细节。<b>它跑完就停，不会自己再动。</b>"),
  img("00-首屏.png", "跑完第一圈的首屏：六个格子、六张指标卡。右上角从左到右：身份、任务状态、流程图、运行报告、重置、跑一圈。"),
  say("把 ~/ads-lab/工作台/app.py 里 _loop 这个函数的六步，用大白话一步一句讲给我听。然后指出：哪一步是它自己不做、留给人做的；哪两种情况下它会在第 2 步就停下来。"),
  see("它能说出第 6 步是停下等人；两种停：没有待处理的任务、缺输入。"),
  stuck("某一格变红：点开那一格看原因，把原话贴给 Codex 问怎么办。多半是终端里的进程被关了。")),
step(3, "读 ① 发现异常", 4,
  p("表格五列：判定（严重／要管／留意／正常）、指标、现值、对着什么比、说明。<b>右边三个输入是人填的</b>：目标 ACOS、补货到仓还要几周、产品阶段。每一条异常都是拿现值对着这三个输入和盈亏线比出来的。"),
  img("01-发现异常.png", "① 发现异常：左边是判定表，右边是三个人填的输入。"),
  see("「库存够卖几周」排第一，红色「严重」——够卖的周数小于补货要的周数；「退款率」橙色「要管」；「同一批词被几个活动重复买」约七成，黄色「留意」；「SP 的 ACOS」「TACOS」「泛词＋跑偏词」都是绿色「正常」，泛词只占花费不到 5%。<b>没有目标，就没有异常；你以为的问题（跑偏词）不是问题。</b>"),
  say("读 ~/ads-lab/广告闭环/输出/数字.json 里「异常」这一段，用大白话告诉我：每一条是拿哪个数、对着哪个目标比出来的？哪一条和「补货到仓周数」这个输入有关？如果目标 ACOS 从 30% 改成 20%，哪一行会变色？"),
  see("它指出库存那一行用的是到仓周数；目标 ACOS 改成 20% 后「SP 的 ACOS」会从正常变成留意。"),
  stuck("它凭印象讲：让它「去文件里读，把数念给我听」。")),
step(4, "读 ② 判断原因，只看三处", 5,
  p("上面三栏：<b>事实</b>（每条能复算，带算式）、<b>推断</b>（每条写了依据和「什么情况下不成立」）、<b>未知</b>（缺什么、去哪取）。下面五个页签：分组账／头部词花在哪／库存／逐周／退货原因。"),
  img("02-判断原因.png", "② 判断原因：三栏在上，页签在下。分组是 AI 按语义做的，报表里没有这一列。"),
  do("切到「库存」页签：按上周销量排，看「够卖几周」那一列，带红色三角的就是两周内会断货的规格。再切「头部词花在哪」：头部四个词的花费大头在词组和广泛两个活动里，精确活动只占一成多。"),
  img("02b-库存页签.png", "「库存」页签：销量最大的规格反而最先断货。"),
  say("三栏表里「推断」的第二条，依据是哪几条事实？它自己写的「不成立的情况」是什么？如果我是老板，要去问谁才能把它变成事实？"),
  see("它能指回事实的编号，说出要去问供应链（到仓日）或运营（竞价是不是有意为之）。"),
  stuck("页签切不动：看页面最上面「跑一圈」是不是还在转，等它停。")),
step(5, "③ 制定动作：做一次取舍", 3,
  p("五张卡＝五条路：A 保主力规格、B 结构去重、C 竞品词分拣、D 只做否词、E 查退款和到仓。每张写了做什么、代价、什么时候该选、可逆吗，右下角是本轮各出了几条动作。蓝色边框的是已选中的。"),
  img("03-制定动作.png", "③ 制定动作：AI 摆选项和代价，不替你选。"),
  do("点一下 D「只做否词」这张卡，读它的代价：近 14 天最多省几百美元，回测里粗规则标出的词大半后来出了单。再点一下取消。今天不要点「按这个取舍重新生成」，第二轮再用。"),
  say("读 ~/ads-lab/广告闭环/输出/选项.json，把五条路按「能省或能保多少钱／风险多大／可逆吗」列成一张表。然后回答：如果只能做一件，数据更支持哪一件？说完理由，但最后由我定。"),
  see("一张五行表；它多半推荐 A（库存），并说明这是建议不是决定。<b>取舍是人的。</b>")),
step(6, "④ 当一回运营：确认、驳回", 5,
  p("每一行是一条动作：编号／广告活动／对象／现值 → 新值／依据／状态与操作。状态只有六种：待确认 → 已确认 → 已执行 → 已验证，或驳回，或作废。"),
  img("04-动作清单.png", "④ 调用工具执行：按类型分组，每条能确认或驳回。"),
  do("1. 展开「暂停广告产品」这一组（点组名）。\n2. 第一行点「确认」：状态变成蓝色「已确认」，下面出现「老板 · 时间」，按钮变成「标为已执行」和「撤回」。\n3. 第二行点「驳回」：出现输入框。什么都不写直接「提交」——被拦：「驳回必须填理由：下一轮 Agent 要读它」。写一句真话，比如「这个规格下周有一批货到，先不停」，回车或点「提交」：状态变橙色「驳回」，理由留在行里。\n4. 把右上角「我是」切成「供应链」，再随便点一行的「确认」——被拦：「「点动作」这一步，供应链没有权限」。切回「老板」。\n5. 看一眼「这一类全部确认」按钮在哪，今天别点。\n6. 点右上角「导出已确认清单」：下载一个 CSV，这就是回公司交给运营的表。"),
  see("状态条上多出蓝色一段、橙色一段，图例的数字跟着变。"),
  stuck("想反悔：已确认的点「撤回」，驳回的点「撤回驳回」。")),
step(7, "全课关键体验：改一个输入，再跑一圈", 8,
  p("假设供应链刚告诉你：货一周就到。"),
  do("7a. 回到 ①，把「补货到仓还要几周」从 4 改成 1，点「保存，任务回到「待处理」」。顶栏状态变回「待处理」。\n7b. 点右上角「跑一圈」。"),
  img("06-改输入后六格.png", "第二圈：第 1 格读回了你点过的（确认 2、驳回 1），第 2 格写明为什么重跑。"),
  see("① 读取状态：「人驳回过 1 条、确认过 2 条」；② 判断下一步：「输入变了（补货到仓周数：4.0 → 1.0）→ 重跑，出 v2」；⑤ 写入状态：「新动作 30 多条入库…作废 60 多条没人点过的旧动作；人处理过的 3 条原样保留…1 条旧确认标了「请复核」」。顶栏变「待核对 · v2」。"),
  do("7c. 到 ④，勾上右上角「显示作废」。"),
  img("04b-第二版动作清单.png", "第二版的 ④：第一组变成「下调预算」，「暂停广告产品」这一组没有了。"),
  img("04c-上一版人处理过的.png", "往下翻：你确认过的带「请复核」，你驳回的带理由，没人点过的划线作废。"),
  see("货一周就到，不该停广告，所以「暂停」全没了，换成十几条「下调预算」。「上一版里人处理过的（v1）」这一组：你确认过的那条带着「⚠ 输入已变（v2），新输入下规则不再建议这一条，请复核」，你驳回的那条带着理由原样留着，其余划线「作废｜输入已变，由 v2 取代」。"),
  say("打开 ~/ads-lab/工作台.db（SQLite），只读，不许改：告诉我 action 表里第 1 版和第 2 版各多少条、各是什么状态；我确认和驳回的那几条现在是什么状态、note 字段写了什么；run 表里两次运行的 inputs 差在哪。"),
  see("它用 sqlite3 或 python 查库，报出的数和页面一致。结论：<b>输出跟着输入变；模型可以忘，系统状态不能忘。</b>"),
  stuck("页面没变化：看第 2 格。写「输入没变」＝你没点保存；写「没有待处理的任务」＝状态没回到待处理。")),
step(8, "故意弄坏两次，看它会不会停", 3,
  do("8a. 什么都不改，点 ① 里的「原样再触发」，再点「跑一圈」。"),
  see("第 2 格：「输入和上一轮一模一样，结果已在库里 → 同一份输入不重复跑」；第 6 格：「停。状态改回「待核对」」。⑤ 的运行历史没有多出一行。"),
  do("8b. 把「补货到仓还要几周」清空，保存，「跑一圈」。"),
  img("07-遇到问题.png", "缺输入：第 2 格变红，第 3、4、5 格根本没跑。"),
  see("第 2 格变红：「缺输入：补货到仓周数 → 标「遇到问题」，不拿旧数据硬跑，上一份有效结果不动」；顶栏状态「遇到问题」带红点；④ 里的动作一条没变。<b>没有停止条件的自动化，不是员工，是事故。</b>"),
  do("8c. 把到仓周数填回 4，保存，「跑一圈」——会出 v3（输入又变了），「暂停」那一组回来了。"),
  stuck("8b 之后第 2 格一直红：正常，它在等人补输入；填回去再跑就恢复。")),
step(9, "看 ⑤ 复盘学习，和流程图", 4,
  p("三块：左上是回测和你驳回过的；左下是运行历史（v1／v2／v3 各自的输入、动作条数、用时）和操作记录（谁、什么时候、做了什么）；右边是行动卡九个字段，第 9 格默认展开——它就是下一次什么时候跑、看哪几个数。"),
  img("05-复盘.png", "⑤ 复盘学习：回测、运行历史、操作记录、行动卡。"),
  do("点顶栏「流程图」，新开一页：人、Agent、停与异常、状态库四条泳道，就是你刚才走的这一圈。右上角「演示」可全屏。"),
  say("读 ~/ads-lab/广告闭环/行动卡/ 里最新一张卡的第 9 格，把它改写成一张到期检查清单：哪天、看哪几个数、各自过线标准是多少、没过线说明什么。再看 ⑤ 的操作记录，用三句话复述今天这一圈：人做了什么、Agent 做了什么、哪些是它没做的。"),
  see("一张 6–7 项的清单，每项有数、有线；三句话里有「上传后台是人做的」。")),
]
R2 = [
step(10, "把自己的报表放进来", 15,
  p("放到 <code>~/ads-lab/我的数据/</code>，表头照 <code>我的数据-示例/</code> 抄，细节看 <code>数据格式.md</code>。<b>真实数据只留在你自己电脑上。</b>没带数据的学员：继续用示例，从第 12 步起练「写分组规则」。"),
  """<table><tr><th>文件</th><th>从哪来</th><th></th></tr>
<tr><td>搜索词报告.csv</td><td>广告后台 → 报告 → 创建报告：商品推广／搜索词／按天／最近 30 天以上，下载 CSV。英文表头不用改</td><td>必需</td></tr>
<tr><td>周度经营.csv</td><td>手填，每行一周：件数、销售额（业务报告）；SP／SB／SBV 广告费（广告后台）；退款件；广告前毛利率</td><td>必需</td></tr>
<tr><td>库存.csv</td><td>手填，每行一个 SKU：可售、上周销量（FBA 库存页、业务报告）</td><td>必需</td></tr>
<tr><td>产品.json、参数.json、分组规则.json</td><td>第 11、12 步做</td><td>必需</td></tr>
<tr><td>活动.csv／关键词竞价.csv／否定词.csv／广告产品.csv／退货.csv</td><td>广告后台批量操作导出、广告产品报告、退货报告；没有就少几类动作</td><td>可选</td></tr></table>""",
  say("看一下 我的数据/ 里的文件：每个多少行、有哪些列；搜索词报告的时间从哪天到哪天、涉及几个广告活动。先别分析，也别改文件。"),
  see("行数、列名、时间范围。<b>先确认周期完整</b>：至少 3 周，建议 4 周以上；最近 3 天归因没满，订单会偏少。"),
  stuck("近 4 周点击不到 300 次：换一个量大的产品。搜索词报告只有汇总没有按天：重新导一份「每日」的。")),
step(11, "你亲手填：目标与约束", 10,
  p("必须人填。AI 看得到报表，看不到你为什么这么投。"),
  say("一项一项问我，我答你记，写成 我的数据/参数.json 和 我的数据/产品.json（格式照 我的数据-示例/）：目标 ACOS 是多少；广告前毛利率（盈亏线）是多少；现在是新品期、成长期还是成熟期；补货几周到仓；哪个活动是精确、哪个是词组、哪个是广泛（名字要和报表里一模一样）；品牌名、客单价。再单独写一份 我的数据/目标与约束.md：哪些词永远不许否，上一轮有哪些是我有意为之的（比如故意开广泛抢曝光）。你可以从报表里列候选给我看，但不许替我填。"),
  see("两个 json 加一页纸，全是你的话。"),
  stuck("不知道盈亏线：售价减去采购、头程、佣金、FBA 费，再除以售价。分不清哪个活动是精确：看报表「匹配类型」一列，哪个活动全是精确匹配。")),
step(12, "写你这个品类的分组规则", 20,
  p("每个品类做一次。示例的规则在 <code>分组规则.json</code>，五类词表都是正则，<b>不许照抄——那是另一个品类的词</b>。"),
  say("照 ~/ads-lab/分组规则.json 的结构给我的品类做一份，存到 我的数据/分组规则.json。先把我搜索词报告里花费前 80 的搜索词读一遍，给我一份候选：哪些是核心大词（CORE）、有购买意图的词根（INTENT）、属性词（MOD）、竞品品牌（COMP）、跑偏（OFF）。每一类列 5 个例子给我定。我点头之后再写成正则，然后拿全部搜索词试分，告诉我每组多少词、多少花费，以及你拿不准的 10 个词。SKU正则先写一个匹配不到的。"),
  see("它停下来让你定；试分后「拿不准的 10 个词」由你一条条判，判完它改规则再试。"),
  stuck("它想用示例的词表：叫停。它把没有购买意图的词也归进核心词：让它先解释 INTENT 这一类是干什么的，再改。")),
step(13, "导入，起一个你自己的工作台", 10,
  say("用 python3 _脚本/import_my_data.py 我的数据 ~/ads-lab-mine 导入，把它打印的「列对应」「导入了多少」「窗口」原样念给我。然后用 python3 工作台/app.py --root ~/ads-lab-mine --port 8811 再起一个工作台，告诉我地址。先别跑圈。"),
  see("列对应表里八个必需列都对上了；周度经营几周、库存几个 SKU、可选表各多少条；窗口是报表最后 28 天。浏览器开 <code>http://localhost:8811</code>，看到的是你自己的产品，状态「待处理」。演示的 8810 可以一直开着，两个互不影响。"),
  stuck("认不出列：按它打印出来的表头改列名（中文）再来。参数里的活动名不在报表里：照它列出的名字改，一个字都不能差。报「至少要 3 周」：回后台重导。")),
step(14, "跑第一圈，先看大盘，再改规则", 10,
  do("在 8811 页面点「跑第一圈」。"),
  say("读 ~/ads-lab-mine/广告闭环/输出/数字.json，把三件事念给我听：分组账（每组花费、占比、ACOS）；同一个词被几个活动同时买的花费占比；头部四个词各花在哪些活动。然后打开 输出/分组明细-近14天-请人工纠错.csv，把花费前 50 里你觉得分错组的列出来。数字一律从文件里取，不许心算。"),
  see("你逐条判分错的词，让它改 我的数据/分组规则.json，重新导入到同一个目录，在页面点「原样再触发」再「跑一圈」：第 2 格写「输入变了（规则版本…）→ 重跑」，分组账跟着变。反复两三次，直到花费前 50 里没有分错的。"),
  stuck("三栏表里「未知」很长：正常，可选表没给的部分它都会写成未知。")),
step(15, "摆选项，你来选", 5,
  say("基于 ~/ads-lab-mine 这一轮的事实和我的目标与约束，给 3–5 个可选动作。每个写清：什么时候该选、代价折成钱是多少、可逆吗。不要替我选。"),
  do("你口头选，并说一句为什么。到 ③ 点卡片改成你的取舍，点「按这个取舍重新生成」，再「跑一圈」。"),
  see("第 2 格写「输入变了（取舍项…）」；④ 只剩你选的那几类动作。")),
step(16, "当一回运营，导出清单", 10,
  do("在 ④ 逐条确认或驳回；驳回写理由。做完点「导出已确认清单」。"),
  say("把我导出的 已确认清单.csv 按类型拆成三张表：否定词（广告活动、否定词、匹配方式）、竞价（广告活动、关键词、匹配、新竞价）、广告产品（广告活动、SKU、动作）。每张表最上面加一行：来自哪一版、谁确认的、什么时候。我拿去后台批量操作用。"),
  see("三张表。<b>上传广告后台这一步，永远是人做。</b>传完回到 ④，把上传过的动作点「标为已执行」。"),
  stuck("清单里有一条你后来觉得不对：回 ④ 点「撤回」，它就不会进下一次导出。")),
step(17, "到日子，人来复盘", 10,
  p("这一步没有 AI 替你判断。行动卡第 9 格写的那一天："),
  do("1. 从后台重新导一份包含最近一周的搜索词报告，覆盖 我的数据/搜索词报告.csv；周度经营.csv 加一行；库存.csv 更新可售和上周销量。\n2. 重新导入到同一个目录：python3 _脚本/import_my_data.py 我的数据 ~/ads-lab-mine（状态库不会被动，你点过的都在）。\n3. 刷新 8811 页面，点「原样再触发」再「跑一圈」。"),
  see("第 1 格读回了你「已执行」的动作；第 2 格写「输入变了（数据窗口：…）→ 重跑」；指标卡和 ① 换成新一周的数。上一张卡第 9 格里的几个数，你逐项对：到了 → 把对应动作点「标为已验证」，操作记录里就有了结论；没到 → 别硬归因，看三栏表的「未知」缺什么，补数据。"),
  say("把 ~/ads-lab-mine/广告闭环/行动卡/ 里上一张卡的第 9 格，和这一圈 输出/数字.json 里对应的数逐项对照，列成表：指标、当时说要看的线、现在的值、过没过。过不了的，告诉我三栏表里哪条「未知」可能是原因。不要替我下结论。"),
  see("一张对照表。<b>跑过两圈、第 9 格逐项对过、有验证结论的，才算数字员工。</b>")),
]
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
<p>页面从上到下五块，对应课上那张图的五步；最上面一条是这一圈的六个动作。右上角从左到右：<b>我是</b>（老板／广告运营／供应链，权限不同）、<b>任务状态</b>、<b>流程图</b>、<b>运行报告</b>、<b>重置</b>（清空状态库，回到没跑过的样子；不动数据文件）、<b>跑一圈</b>。</p>
<table><tr><th>区块</th><th>里面是什么</th><th>谁在动</th></tr>
<tr><td>Loop 六动作</td><td>读取状态 → 判断下一步 → 执行 → 验证 → 写入状态 → 判断停止条件；每跑一圈亮一遍</td><td>Agent</td></tr>
<tr><td>六张指标卡</td><td>上周销售额、广告费、TACOS、SP 的 ACOS、库存够卖几周、退款率；带四周小趋势</td><td>脚本</td></tr>
<tr><td>① 发现异常</td><td>判定表；右边三个输入（目标 ACOS、到仓周数、阶段）</td><td>你填输入</td></tr>
<tr><td>② 判断原因</td><td>事实／推断／未知三栏；五个证据页签</td><td>AI 分组、脚本算数</td></tr>
<tr><td>③ 制定动作</td><td>五条路各带代价，点卡片选</td><td>你取舍</td></tr>
<tr><td>④ 调用工具执行</td><td>动作清单：确认／驳回（必填理由）／已执行／已验证；导出已确认清单</td><td>你点头，人去后台</td></tr>
<tr><td>⑤ 复盘学习</td><td>回测、运行历史、操作记录、行动卡九格（第 9 格＝下次怎么触发）</td><td>下一圈先读回</td></tr></table>

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
<tr><td>点确认没反应，提示没有权限</td><td>右上角「我是」不对：老板和广告运营能点动作，只有老板能改取舍和目标，供应链只能改到仓周数。</td></tr>
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
<tr><td>待确认 / 已确认 / 已执行 / 已验证 / 驳回 / 作废</td><td>动作的六种状态。Agent 只会生成「待确认」；后面每一步都是人点的；「作废」是输入变了之后，没人点过的旧动作自动退场。</td></tr></table>

<h2 id="files">文件地图</h2>
<table><tr><th>路径</th><th>是什么</th></tr>
<tr><td>工作台/app.py、工作台/index.html</td><td>后端和页面。标准库加 SQLite，不联网。</td></tr>
<tr><td>工作台.db</td><td>状态库：任务、动作、行动卡、运行、操作记录。「重置」会删掉重建。</td></tr>
<tr><td>_原始拉取/</td><td>报表数据（演示版已脱敏并换了品类）。</td></tr>
<tr><td>参数.json、分组规则.json</td><td>三个输入和活动分工；你这个品类的五类词表。</td></tr>
<tr><td>广告闭环/输出/</td><td>每一圈的产物：数字.json（所有事实和异常）、诊断-三栏表.md、选项.json、动作清单.csv／.json、验证器.json、分组明细-近14天-请人工纠错.csv</td></tr>
<tr><td>广告闭环/行动卡/</td><td>每一版的行动卡（九格）。</td></tr>
<tr><td>运行报告-R-001.html、流程图/</td><td>单页报告（顶栏「运行报告」）；一圈 Loop 的流程图（顶栏「流程图」）。</td></tr>
<tr><td>数据格式.md、我的数据-示例/、_脚本/import_my_data.py</td><td>第二轮：自己的数据怎么准备、模板、导入脚本。</td></tr>
<tr><td>_脚本/pipeline.py、_脚本/render.py</td><td>算数、规则、验证器；三栏表、行动卡、报告。</td></tr></table>
<p class="lead">包的地址：github.com/WaytoAIC/ads-workbench　·　示例数据是脱敏并替换过品类的演示数据，没有一个数是真实值</p>
</main><script>function cp(b){{navigator.clipboard.writeText(b.nextElementSibling.innerText).then(()=>{{b.textContent="已复制";setTimeout(()=>b.textContent="复制",1200)}})}}</script></body></html>"""
io.open(OUT, "w", encoding="utf-8").write(HEAD + BODY); print("写出", OUT, len(HEAD + BODY), "字符")
