# 装进 Agent：让它每周一自己跑一圈

网页上的「跑一圈」是手动点的。`_脚本/weekly.py` 把每周该做的事串成八步，不起网页直接跑：

`读回状态 → 数据体检 → 跑一圈（和网页同一条 Loop）→ 经营核算 → 模型补位 → 自检 → 起草周报 → 留痕`

每步打一行「✓/✗ 步名：一句话」，结尾打一段给人看的摘要（任务状态、六格各一句、新动作按类型、待审批条数、验证器、经营结论、模型补位状态、周报草稿在哪、下次触发）。

```bash
python3 _脚本/weekly.py --dry-run                 # 先空跑：不写状态库、不跑流水线、不调模型、不推送，只说会做什么
python3 _脚本/weekly.py                           # 真跑：仓库根当数据目录，触发方式记作「定时」
python3 _脚本/weekly.py --root ~/ads-lab-mine --trigger 手动
python3 _脚本/weekly.py --no-llm                  # 跳过模型补位，其余照跑
python3 _脚本/agent_run.py                        # 老入口，等价写法（现在是 weekly.py 的薄包装，参数相同）
```

**它只读报表、只写本机状态库（`工作台.db`），不碰任何广告后台。** 动作全部停在「待确认」，要人在工作台审批、人去后台上传、回来标「已执行」。重复触发不重跑（输入没变就跳过）。周报只起草，不发群。

| 退出码 | `weekly.py` | `agent_run.py`（老约定） |
|---|---|---|
| 0 | 正常（包括「输入没变，不重跑」） | 0 |
| 1 | 有步骤失败：流水线报错、验证器没过、模型通道不通…… 其余步骤照样走完 | 2 |
| 2 | 缺输入没跑：`参数.json` 的目标 ACOS / 补货到仓周数 / 产品阶段、数据窗口，或必需的报表不在。上一份有效结果不动 | 2 |

## 先空跑，再接定时

```bash
python3 _脚本/weekly.py --dry-run
```

看到八行 ✓、结尾写着「演练」，说明数据目录、输入、报表都认得。这一步不会建 `工作台.db`，也不会动 `广告闭环/`。然后真跑一次，再接下面任一种定时。

## 接法一：macOS cron / launchd（每周一 9 点）

```bash
crontab -e      # 加一行（目录改成你的）
0 9 * * 1 cd ~/ads-lab && /usr/bin/python3 _脚本/weekly.py >> ~/ads-lab/运行记录/cron.out 2>&1
```

- 用 `which python3` 查你装了 pandas 的那个解释器路径，替换掉 `/usr/bin/python3`。
- 目录别放「桌面」「文稿」下，否则 cron 会被 macOS 隐私保护拦住读不到文件。
- cron 的环境很干净：要推飞书、要接模型，把环境变量写在这一行前面，或写进一个只有你能读的文件再 `source`（见下面两节）。别把值写进仓库。
- 想用 launchd：同一条命令写进 `~/Library/LaunchAgents/com.ads-lab.weekly.plist` 的 `ProgramArguments`，`StartCalendarInterval` 填 `Weekday=1, Hour=9`，`launchctl load` 它；合上盖子错过的那次会在下次开机补跑。

节奏记在 `ads.config.json` 的 `weekly.schedule`（默认 `0 9 * * 1`），是给人和页面看的；`weekly.py` 自己不定时，谁调它谁定时，改节奏要改 cron 那一行（或 Hermes 的定时）。

## 接法二：Hermes 定时任务

仓里带了一键安装：`bash agent/install_hermes.sh --dry-run` 先看它会做什么，去掉 `--dry-run` 再装。它会把 `agent/ads-weekly.sh`（里面就是调 `_脚本/weekly.py --trigger 定时`）装成 profile 的每周定时。细节见 `agent/README.md`。

手工建也行。在 Hermes 里建一个每周一 9:00 的定时任务，提示词照这个写：

```
到 ~/ads-lab 目录，执行 python3 _脚本/weekly.py --trigger 定时。
把它打印的最后一段摘要（从「【广告周检 Agent】」开始）原样转给我，不要改写、不要总结；
退出码是 2 就在最前面加一行「⚠ 缺输入，这圈没跑」，是 1 就加一行「⚠ 有步骤失败，要人看」。
除了这个脚本，不要运行别的命令，不要改任何文件，不要替我审批任何动作。
```

## 接法三：飞书自定义机器人（只推运行摘要）

1. 打开要收消息的飞书群 → 右上角「群设置」→「群机器人」→「添加机器人」→ 选「自定义机器人」。
2. 起名（比如「广告周检」），下一步会给一条 webhook 地址，复制下来。
3. 安全设置选「自定义关键词」，填 `广告周检`（摘要以「【广告周检 Agent】」开头，能过关键词校验）。
4. 把地址放进环境变量 `FEISHU_WEBHOOK`：写在 cron 那一行前面，或 `~/.zshrc` 里 `export FEISHU_WEBHOOK=…`。**别写进仓库、别发群**，它等于这个群的发言权。

默认**不推**：每周一圈只起草、只留痕，群里的话要人在工作台点了才发。想让它跑完自动报个平安，要两样都做：设 `FEISHU_WEBHOOK`，并把 `ads.config.json` 里 `weekly.推送` 改成 `"摘要"`。这时推过去的只是结尾那段运行摘要（这圈跑没跑、有几条等你批、哪步失败），格式 `{"msg_type":"text","content":{"text":"…"}}`；周报正文任何时候都不自动发。
`--dry-run` 不推送。环境变量换个名字，改 `飞书.webhook_env`。推送失败只在终端报一句，不影响这一圈的结果。

## 模型通道怎么配（可选）

不配也能跑：第五步会写「跳过：没接模型」，`AI补位.json` 里是 `状态: skipped`，周报用规则拼。配了之后模型只写六样文字：核心限制一句话、路径建议、任务标签草稿、搜索词补位、决策表草稿、周报草稿；枚举不合法、编了数字的会被 `llm.py` 丢掉。

解析顺序：**环境变量 → `ads.config.json` 的 `llm` 段 → 都没有且 `enabled` 为真时退回本机 Hermes 网关**。

| 环境变量 | 作用 |
|---|---|
| `ADS_LLM_BASE` | 接口地址（OpenAI 兼容接口写到 `/v1`） |
| `ADS_LLM_KEY` | 密钥。只在进程里用，不落盘、不进日志 |
| `ADS_LLM_MODEL` | 模型名 |
| `ADS_LLM_API` | `openai`（默认）或 `anthropic` |
| `ADS_LLM` | `0` 强制关，`1` 强制开（等于 `enabled: true`） |

- 只设环境变量就够了：有 `ADS_LLM_KEY` 或 `ADS_LLM_BASE`，不管 `enabled` 写的什么都会用。
- 想把地址和模型名固定下来：写进 `ads.config.json` 的 `llm.base` / `llm.model`，把 `enabled` 改成 `true`；**密钥仍然只放环境变量**，变量名由 `llm.key_env` 指定（默认 `ADS_LLM_KEY`）。配置文件里没有放密钥的地方。
- 什么都不填、只把 `enabled` 改成 `true`：走本机 Hermes 网关 `<agent.hermes>/p/<agent.profile>/v1`，密钥从这个 profile 自己的 `.env` 里的 `API_SERVER_KEY` 读。读不到就跳过，原因写「这个 profile 还没有 API_SERVER_KEY」。
- `llm.超时秒` 是单次调用的超时；`llm.搜索词补位上限` 是每圈最多送多少个正则没认出来的搜索词给模型。

接之前先看它要发什么：

```bash
python3 _脚本/llm.py --dry-run                    # 只打印任务清单和每个提示词多长，不调用
python3 _脚本/llm.py --only 周报                   # 只重跑其中一项，其余保留上一次的
```

每圈模型调用 5 次（搜索词超过一批会多几次，JSON 不合法时每次最多重试 1 次），次数记在 `runs.jsonl` 的 `llm.calls`。

## 去哪看运行记录

都在 `<数据目录>/运行记录/`（不进仓）：

| 文件 | 是什么 |
|---|---|
| `runs.jsonl` | 每圈一行 JSON：时间、触发、是否演练、八步各自的 ok / 耗时 / 一句话、版本、动作数、待审批数、模型状态和调用次数、problems、退出码。工作台「Agent 运行」页读的就是它 |
| `weekly-<时间>.log` | 这一圈的完整输出：八步、六格明细、驳回理由、周报草稿全文、摘要 |
| `周报-<日期>.md` | 周报草稿（有模型草稿用模型的，没有就按规则拼）。只起草，没有发 |

```bash
tail -1 运行记录/runs.jsonl | python3 -m json.tool      # 最近一圈
ls -t 运行记录/weekly-*.log | head -1 | xargs cat       # 最近一圈的完整日志
```

## 跑完之后

- 摘要里「待审批 N 条」就是要人做的事：打开工作台（`python3 工作台/app.py`），首页会列出要你处理的事，到「行动」里通过或驳回。驳回要写理由，下一圈 Agent 会读回来、不再提。
- 「下一次触发」是复盘日；到日子前想再跑，改了目标 / 到仓周数 / 取舍，任务会自动标回「待处理」。
- 退出码 2：按摘要里说的补齐输入再跑。退出码 1：看 `运行记录/` 里最新的日志，哪一步是 ✗。
- 想知道改了规则或换了模型之后这套东西还靠不靠谱：`python3 _脚本/eval.py`，见 `评测/README.md`。
