# 广告 Agent：装进 Hermes

工作台自己就能跑一圈。装 Agent 多三样：**每周自己醒**、**页面里能问它**、**在飞书里能问它**。三样可以分开要。

| 文件 | 是什么 |
|---|---|
| `SOUL.md` | 人设与规矩：守哪个工作台、读哪些文件、不做什么 |
| `岗位卡.json` | 页面「Agent 运行」上那张岗位卡的内容，改这里页面就变 |
| `ads-weekly.sh` | 每周一圈的定时脚本（调 `_脚本/weekly.py`） |
| `install_hermes.sh` | 一键安装：备份 → 人设 → 技能包 → 定时脚本 → 每周定时 |

## 第 1 步：装

```bash
hermes profile create ads-agent        # 已经有就跳过
bash agent/install_hermes.sh --dry-run # 先看它会做什么
bash agent/install_hermes.sh
```

它会先把要动的东西打包到 profile 的 `backups/`，再动手。不碰密钥，不改模型配置。

## 第 2 步：空跑一遍

```bash
bash ~/.hermes/profiles/ads-agent/scripts/ads-weekly.sh --dry-run
```

看到八步的清单、没有报错，每周一 9 点它就会自己跑。结果在 `运行记录/`，页面「Agent 运行」能看到。

## 第 3 步（可选）：让页面能问它

页面的「问 Agent」要通过 Hermes 网关和这个 profile 对话，需要它的 `.env` 里有一行 `API_SERVER_KEY=…`。
这把钥匙由你自己的密钥管理方式写进去（不要写进本仓库）。写好后重启 Hermes 网关，页面「设置 → Agent 接通状态」四项全绿就通了。

没有 Hermes 也能问：给工作台配一条直连模型通道，启动前设三个环境变量——

```bash
export ADS_LLM_BASE=…  ADS_LLM_KEY=…  ADS_LLM_MODEL=…     # OpenAI 兼容接口；Anthropic 接口再加 ADS_LLM_API=anthropic
python3 工作台/app.py
```

直连时模型没有工具，工作台会把这一圈脚本算好的要点塞给它，它只能用这些数回答。

## 第 4 步（可选）：每周一圈也用模型补位

定时脚本会读 `agent/.env.local`（已在 `.gitignore` 里）。两种写法任选：

```bash
# 写法一：直接放钥匙
ADS_LLM_BASE=…
ADS_LLM_KEY=…
ADS_LLM_MODEL=…

# 写法二：钥匙留在你原来的密钥文件里，这里只写它在哪、叫什么
ADS_LLM_API=anthropic
ADS_LLM_BASE=…
ADS_LLM_MODEL=…
ADS_KEY_FILE=/路径/到/你的密钥文件
ADS_KEY_NAME=那一行的变量名
```

不配也行：模型补位这一步会写「没接模型」然后跳过，其余七步照常。

## 撤回

```bash
tar -xzf ~/.hermes/profiles/ads-agent/backups/before-ads-workbench-<时间>.tgz -C ~/.hermes/profiles/ads-agent
hermes -p ads-agent cron list      # 找到「广告周检 每周一圈」
hermes -p ads-agent cron remove <id>
```

## 本机专属的补充

想给人设加几句只属于你自己的话（比如飞书机器人怎么接）：写在 `agent/SOUL.local.md`，安装时会接在 `SOUL.md` 后面；这个文件不进仓。
