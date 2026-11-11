#!/bin/bash
# 广告周检 · 每周一圈（Hermes 定时用 --no-agent 调它：脚本就是任务，stdout 原样交给 Hermes）。
# 安装时 agent/install_hermes.sh 会把下一行换成本机的工作台目录，再拷到 profile 的 scripts/ 下。
set -u
WB="__WORKBENCH__"
cd "$WB" || { echo "工作台目录不在：$WB"; exit 1; }

# 模型通道（可选）。环境里已有 ADS_LLM_* 就用；否则读本机的 agent/.env.local（不进仓）。
# .env.local 里可以直接写 ADS_LLM_KEY，也可以只写「钥匙在哪个文件、叫什么名」，脚本运行时去取：
#   ADS_LLM_API=openai|anthropic  ADS_LLM_BASE=…  ADS_LLM_MODEL=…  ADS_KEY_FILE=/路径/到/密钥文件  ADS_KEY_NAME=变量名
if [ -f agent/.env.local ]; then set -a; . agent/.env.local; set +a; fi
if [ -z "${ADS_LLM_KEY:-}" ] && [ -n "${ADS_KEY_FILE:-}" ] && [ -n "${ADS_KEY_NAME:-}" ] && [ -f "$ADS_KEY_FILE" ]; then
  ADS_LLM_KEY=$(grep "^${ADS_KEY_NAME}=" "$ADS_KEY_FILE" | head -1 | cut -d= -f2- | tr -d "\"'")
  export ADS_LLM_KEY
fi

export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
mkdir -p 运行记录
OUT="运行记录/.cron-last.out"
python3 _脚本/weekly.py --trigger 定时 "$@" > "$OUT" 2>&1
rc=$?
# 只把结尾摘要交给 Hermes；完整日志在 运行记录/weekly-*.log
tail -n 24 "$OUT"
[ $rc -eq 2 ] && echo "缺输入没跑：到工作台首页补齐目标后重跑。"
[ $rc -eq 1 ] && echo "有步骤失败：看 运行记录/ 里最新的日志。"
exit $rc
