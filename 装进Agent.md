# 装进 Agent：让它每周一自己跑一圈

网页上的「跑一圈」是手动点的。`_脚本/agent_run.py` 把同一条 Loop 拿出来不起网页直接跑，跑完打印一段纯文本摘要（任务状态、六格各一句、新动作按类型、待审批条数、验证器、下次触发）；设了环境变量 `FEISHU_WEBHOOK` 就把同一段文本推到飞书群。六格有失败或缺输入，退出码 2。

```bash
python3 _脚本/agent_run.py                       # 用仓库根当数据目录，触发方式记作「定时」
python3 _脚本/agent_run.py --root ~/ads-lab-mine --trigger 手动
FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxxx' python3 _脚本/agent_run.py
```

**它只读报表、只写本机状态库（`工作台.db`），不碰任何广告后台。** 动作仍然是「待确认」，要人在工作台 ⑤ 里审批、人去后台上传、回来标「已执行」。重复触发不重跑（输入没变就跳过），缺输入就停下报「遇到问题」。

## 接法一：macOS launchd / cron（每周一 9 点）

```bash
crontab -e      # 加一行（目录改成你的）
0 9 * * 1 cd ~/ads-lab && FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxxx' /usr/bin/python3 _脚本/agent_run.py >> ~/ads-lab/agent.log 2>&1
```

- 用 `which python3` 查你装了 pandas 的那个解释器路径，替换掉 `/usr/bin/python3`。
- 目录别放「桌面」「文稿」下，否则 cron 会被 macOS 隐私保护拦住读不到文件。
- 想用 launchd：同一条命令写进 `~/Library/LaunchAgents/com.ads-lab.weekly.plist` 的 `ProgramArguments`，`StartCalendarInterval` 填 `Weekday=1, Hour=9`，`launchctl load` 它；效果一样，合上盖子错过的那次会在下次开机补跑。

## 接法二：Hermes 定时任务

在 Hermes 里建一个每周一 9:00 的定时任务，提示词照这个写：

```
到 ~/ads-lab 目录，执行 python3 _脚本/agent_run.py --trigger 定时。
把它打印的整段文本原样转给我，不要改写、不要总结；退出码是 2 就在最前面加一行「⚠ 这圈没跑成，要人看」。
除了这个脚本，不要运行别的命令，不要改任何文件。
```

要 Hermes 自己推飞书，就把 `FEISHU_WEBHOOK` 写进它的运行环境；否则让它把文本发到你指定的群就行。

## 接法三：飞书自定义机器人的 webhook 怎么拿

1. 打开要收消息的飞书群 → 右上角「群设置」→「群机器人」→「添加机器人」→ 选「自定义机器人」。
2. 起名（比如「广告周检」），下一步会给一条 `https://open.feishu.cn/open-apis/bot/v2/hook/…` 的 webhook 地址，复制下来。
3. 安全设置选「自定义关键词」，填 `广告周检`（脚本的每段摘要都以「【广告周检 Agent】」开头，能过关键词校验）。
4. 把地址放进环境变量 `FEISHU_WEBHOOK`：写在 cron 那一行里、或 `~/.zshrc` 里 `export FEISHU_WEBHOOK=…`。**别写进仓库、别发群**，它等于这个群的发言权。

脚本发的是最简单的文本消息：`{"msg_type":"text","content":{"text":"…"}}`。推送失败只在终端报一句，不影响这圈的结果和退出码。

## 跑完之后

- 摘要里「待审批 N 条」就是要人做的事：打开工作台（`python3 工作台/app.py`）到 ⑤ 分类审批里通过或驳回。
- 「下一次触发」是复盘日；到日子前想再跑，改了目标 / 到仓周数 / 取舍就会自动标回「待处理」。
- 连着两次缺资料、单日花费翻三倍、行动卡结案：这三种情况 Agent 会停，等人接手。
