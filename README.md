## 🚀 Way to AIC | 通往 AI 电商之路
---
### 🌐 官网 Website
- https://waytoaic.com
- https://www.waytoaic.com
---

### 👥 社群招募 Community
`Way to AIC 社群招募 | WaytoAIC.com`

<p align="center">
  <img src="https://github.com/user-attachments/assets/d9f8bbf4-2056-4780-975d-86c885b52bab" width="70%">
</p>

---

### 📣 公众号 WeChat Official Account
`维正 WaytoAIC`

<p align="center">
  <img src="https://github.com/user-attachments/assets/71c71a5c-e68a-4f30-9afb-f2b056619991" width="300">
</p>

---

### 🧠 知识星球 Xiaozhixing
`AI电商之路 WaytoAIC`

<p align="center">
  <img src="https://github.com/user-attachments/assets/9eccef07-0e84-45a7-a415-affcb18c928d" width="200">
  <img src="https://github.com/user-attachments/assets/4e99fbc3-1981-4fee-b113-c9821141102d" width="400">
</p>

---

### 🧩 About Way to AIC

**AIC = AI Commerce**

在 AI 重塑商业的时代，我们希望和每一个拥抱 AI 的卖家：

- 找到场景
- 定义问题
- 积累能力
- 设计系统

共同通往 AI 电商之路。

> Way to AIC 不是教学，不是工具，
> 而是一条所有电商人共同走的进化之路。

### WaytoAIC 理念 | Principles

| 中文 | English |
|---|---|
| 场景先于方法 | Context before method |
| AI 的价值来自真实业务场景，而不是技术本身。 | AI creates value through real business contexts, not through technology alone. |
| 问题先于答案 | Problem before answer |
| 定义问题，比拥有工具更重要。 | Defining the problem matters more than collecting tools. |
| 系统胜过技巧 | System over tricks |
| 技巧是术，系统才是道，决定卖家的上限。 | Tricks are tactical; systems define long-term leverage and ceiling. |
| 共创优于独行 | Co-creation over solo progress |
| 我们相信，真正的进化发生在共同探索的过程中。 | Real evolution happens through shared exploration. |

# ads-workbench · 广告周检本地工作台 / Local Ads Review Workbench

一个能点、能跑的本地工作台：把「看到 ACOS 高」推进到「有人点头、有日期、能复盘的动作清单」。只用 Python 标准库＋SQLite＋pandas，断网可用，**默认不连任何广告后台**（广告接口已在真实店铺跑通，开关默认关，见下）。

一套四层，可以只用第一层，也可以一层层装上去：

| 层 | 是什么 | 在哪 |
|---|---|---|
| 工作台 | 能点的页面＋状态库＋流水线：算数、找异常、起草动作、人审批 | `工作台/`、`_脚本/pipeline.py` |
| 技能包 | 10 个技能：先算账定目标 → 拆指标找限制 → 判断每条广告的任务 → 选利润路径 → 才是出价否词 | `skills/` |
| Agent | 装了技能包、页面里能问、每周自己醒的那个壳（Hermes；也可以只接一条模型通道） | `agent/` |
| Harness | 把它围住的七样：触发、配方、上下文、工具、护栏、状态、评估 | `_脚本/weekly.py`、`口径.json`、`评测/` |

分工只有一句：**数字归脚本，判断归模型，拍板归人。** 没接模型，前两样照常，页面标「没接模型」。

A runnable local workbench that turns an Amazon ads report into a reviewed, dated action list. Python stdlib + SQLite + pandas, works offline, **never touches your ad console**. Four layers you can adopt one at a time: workbench, skill pack, agent, harness. Scripts own the numbers, the model owns the reading and drafting, humans own every decision.

![首屏](截图/工作台-首屏.png)

## 快速开始 / Quick start

```bash
git clone https://github.com/WaytoAIC/ads-workbench ~/ads-lab
cd ~/ads-lab && pip install pandas && python3 工作台/app.py
```

打开 http://localhost:8810 ，点「跑第一圈」。Mac 也可以双击 `启动工作台.command`。不要放在「桌面」目录下。
Open http://localhost:8810 and click “跑第一圈”.

## 里面有什么 / What's inside

- **Loop 六动作**：读取状态 → 判断下一步 → 执行 → 验证 → 写入状态 → 判断停止条件（`流程图/`，另有项目架构图）
- **六页**（左侧导航，按「人来干什么」分）：**首页**（今天要处理什么 ＋ 先算账 ＋ 这周的结论）｜**行动**（列表 → 详情，带五步进度线和动手前的三问；通过／驳回必填理由／导出上传表）｜**广告活动**（14 个活动、各自的任务 → 构成，任务由人确认）｜**原因**（经营拆解：指标树、四条路径、决策表｜问题连线：问题 → 分析 H1–H6 → 对策 A–E → 动作）｜**Agent 运行**（这一圈｜每周自己跑｜它的构成）｜**设置**（目标与经营口径、Agent 接通状态、数据源、口径、执行通道、权限、演示模式、重置）
- 持续运行历史回放（`历史回放.json`）、原因树（`_脚本/tree.py` 连线）、活动构成（`_脚本/structure.py`）、按通道导出（`_脚本/fields.py` 把动作翻成广告后台字段）
- 权限与状态流转在服务端强制；改一个输入再跑，输出跟着变；人驳回过的下一圈不再提
- `实操手册.html`：学员两轮 18 步｜`学员材料/任务卡.md`：交三样、热身题、三层验收｜`台上操作卡-业务工作台.md`：讲师 7 步｜`数据说明.md`
- 换成自己的数据：`数据格式.md` ＋ 模板 `我的数据-示例/` ＋ `python3 _脚本/import_my_data.py 我的数据 ~/ads-lab-mine`
- **经营核算**（`_脚本/biz.py`，不调模型）：目标 TACOS ＝ 定价毛利率 − 要留的利润率、单品日预算、TACOS 拆到 CPC／CVR／客单价、只指一个「核心限制」、每条广告的任务（纯利型／推自然位／测词拓词／收割／防守）、四条利润路径的测算、九栏决策表
- **归因**（`_脚本/attribution.py`，不调模型）：「原因 · 问题连线」里，每个问题拆到是谁造成的，每条分析并排摆支持和不支持的证据、最多能解释多少、把握几成、还缺什么；人对每条分析下判断，Agent 可以被叫去深挖并把结果存回节点
- **从接口取数**（`_脚本/ads_report.py`）：广告侧的八张表（搜索词报告、活动、广告组、关键词竞价、否定词、广告产品、商品定位、否定 ASIN）可以直接从 Amazon Ads API 拉，格式和手工导出的一样；手工导表仍然可用，人自己放的文件不会被覆盖。生意侧的数（件数、销售额、库存、毛利）仍然人填。页面「广告接口 → 取数」，或 `python3 _脚本/ads_report.py pull <目录> --asin …`。已在真实店铺实测
- **广告接口**（`_脚本/ads_api.py`）：Amazon Ads API 统一版 v1，走本机紫鸟代理。读（广告账号、活动、广告组、投放对象、商品广告）和三类写（暂停商品广告、暂停关键词、广告组里否定 ASIN）已在真实店铺上发过并回读；其余动作能翻成请求预演。`check` 连通、`preview` 预演、`execute` 执行一条；执行开关默认关，演示数据永远不发。跑通记录见 `Ads接口跑通记录.json`
- **技能包**（`skills/`，MIT）：`ads-router` 入口＋ 9 个专用技能＋共享口径。装进 Claude Code／Codex：`bash skills/install.sh --target claude`；装进 Hermes 见下一条
- **Agent**（`agent/`）：`bash agent/install_hermes.sh` 一条命令装人设、技能包和每周定时；页面右下角「问 Agent」直接问这一圈的数据，要发群它只出草稿、你点了才发 → `agent/README.md`
- **每周一圈**（`_脚本/weekly.py`）：读回状态 → 数据体检 → 跑一圈 → 经营核算 → 模型补位 → 自检 → 起草周报 → 留痕（`运行记录/`）；`--dry-run` 先空跑。`_脚本/agent_run.py` 是它的等价入口 → `装进Agent.md`
- **模型补位**（`_脚本/llm.py`）：模型只写文字和选项，不写新数字；枚举不在口径里的、编出数字的，校验时丢弃。没接模型就跳过
- **评测**（`评测/`＋`_脚本/eval.py`）：改了规则或换了模型，跑一遍考卷看有没有回归
- 阈值只有一处：`口径.json`。流水线读它，技能包引用它，页面「设置」能看

Six-step loop, a six-page workbench organised by what the human is there to do (Home, Actions, Campaigns, Causes, Agent runs, Settings), server-enforced roles and state transitions, a deterministic profit model (target TACOS, per-campaign job, four profit paths), a 10-skill pack, a Hermes agent you can ask from the page, a weekly harness loop with run logs and evals, a student handbook with a task card, and an instructor card. UI and docs are in Chinese.

## 文件地图 / File map

| 文件 | 干什么 |
|---|---|
| `工作台/app.py` | 后端：Loop 六格、权限、状态流转、导出（标准库＋SQLite） |
| `工作台/hub.py` | Agent／Harness 接线：问 Agent 转发、接通检查、岗位卡、七个部件的状态、群消息人闸 |
| `工作台/index.html` | 页面：六页（首页／行动／广告活动／原因／Agent 运行／设置），离线可用 |
| `_脚本/pipeline.py` | 算数、分组、异常、全类型动作规则、验证器（需要 pandas） |
| `_脚本/render.py` | 三栏表、行动卡、运行报告 |
| `_脚本/tree.py` | 「原因」页那棵树的连线：问题 → 分析 → 对策 → 动作类型，以及动作类型 → 执行通道 |
| `_脚本/structure.py` | 一个活动由什么构成（广告产品／关键词或商品定位／否定），给「广告活动」页用 |
| `_脚本/fields.py` | 动作 → 广告后台字段（Campaign／广告组／关键词／定位／改哪一栏），批量上传表 |
| `_脚本/history_sim.py` | 历史回放：同一套规则对前三圈历史数据跑，生成 `历史回放.json` |
| `_脚本/biz.py` | 经营核算 → `广告闭环/输出/经营.json`（算账、拆解、广告任务、利润路径、决策表） |
| `_脚本/attribution.py` | 归因 → `广告闭环/输出/归因.json`（每个问题是谁造成的、每条分析的正反证据与把握、还缺什么） |
| `_脚本/ads_api.py`／`Ads接口跑通记录.json` | 广告接口适配器（连通、预演、执行一条：先读现值、只提交一次、独立回读）／在真实店铺上跑通过什么（不含任何店铺信息） |
| `_脚本/ads_report.py`／`Ads接口文档.json` | 从广告接口取数（三份报表＋结构 → 八张表，手工导表可选）／新版接口能做什么、每条的依据（「广告接口 → 新版文档」页读它） |
| `_脚本/weekly.py` | 每周一圈（Harness 主循环）：八步、每步留痕、`--dry-run`；`agent_run.py` 是它的薄包装 |
| `_脚本/llm.py` | 模型补位 → `AI补位.json`；先校验再落盘 |
| `_脚本/eval.py`／`评测/` | 考卷与评分：确定性断言＋模型部分的一致率 |
| `口径.json` | 阈值与调幅的唯一来源 |
| `ads.config.json` | Agent 与 Harness 的配置：Hermes 地址和 profile、模型通道、每周节奏、推送（不放密钥） |
| `skills/` | 技能包：`ads-router`＋9 个专用技能＋`ads-shared/` 共享口径＋`install.sh` |
| `agent/` | `SOUL.md` 人设、`岗位卡.json`、`ads-weekly.sh` 定时脚本、`install_hermes.sh` 一键安装 |
| `docs/架构.md` | 四层怎么接：谁写哪个文件、`经营.json` 和 `AI补位.json` 的结构、接口、字段分工 |
| `tests/` | 流水线回归、经营核算、周跑、模型补位的单元测试（`python3 -m unittest discover tests`） |
| `_脚本/import_my_data.py` | 把自己的报表整理成工作台能读的样子 |
| `参数.json`／`分组规则.json` | 输入与活动分工／本品类五类词表 |
| `历史回放.json` | 前三圈模拟回放（页面只读） |
| `显示映射.json` | 演示数据的显示层：活动名、ID、广告组（真实数据目录不放它） |
| `_原始拉取/` | 脱敏演示数据 |
| `工作台.db` | 状态库（重置会删掉重建，不入库） |
| `学员材料/任务卡.md` | 学员任务卡：问题、交三样、热身题、跟练路线、三层验收、材料 |
| `装进Agent.md`／`agent/README.md` | 定时触发的三种接法／装进 Hermes 的四步 |
| `实操手册.html`／`台上操作卡-业务工作台.md` | 学员手册／讲师操作卡 |
| `数据格式.md`／`数据说明.md`／`我的数据-示例/` | 换自己的数据／脱敏说明／模板 |
| `流程图/` | 工作台运转流程、项目架构 |

## 数据 / Data

示例是脱敏并替换过品类的演示数据（浴室防滑垫／NORDLY），竞品品牌名全部是编的。换成自己的数据：照 `数据格式.md` 准备一份搜索词报告加三张手填小表，导入后 `python3 工作台/app.py --root <目录>`；真实数据只留在你自己电脑上。
Sample data is desensitized demo data with a substituted category; all competitor brand names are fictional.

## 方法来源 / Credits

经营框架（先算账定目标、指标拆解、广告任务、利润路径、新品期节奏）参考了两场行业分享，并吸收了几个开源广告诊断项目的口径写法；规则、阈值和措辞为本仓自定，以 `口径.json` 和 `skills/` 为准。

## License

MIT
