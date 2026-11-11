#!/bin/bash
# 把广告 Agent 装进本机 Hermes：备份 → 人设 → 技能包 → 定时脚本 → 每周定时。
# 不碰任何密钥，不改模型配置。可以反复跑（已有的定时不会重复建）。
#
#   bash agent/install_hermes.sh                     # 装到 profile「ads-agent」
#   bash agent/install_hermes.sh --profile 我的名字   # 换一个 profile（要先 hermes profile create 我的名字）
#   bash agent/install_hermes.sh --dry-run           # 只说会做什么，不动手
#   bash agent/install_hermes.sh --no-cron           # 不建每周定时
#   bash agent/install_hermes.sh --archive-old '旧技能-* 另一个目录'   # 把 profile 里旧的同类技能挪进 skill-backups/（可给多个，空格隔开）
set -eu
PROFILE="ads-agent"; DRY=0; CRON=1; OLD=""; SCHEDULE="0 9 * * 1"; JOB="广告周检 每周一圈"
while [ $# -gt 0 ]; do case "$1" in
  --profile) PROFILE="$2"; shift 2;; --dry-run) DRY=1; shift;; --no-cron) CRON=0; shift;;
  --archive-old) OLD="$2"; shift 2;; --schedule) SCHEDULE="$2"; shift 2;;
  *) echo "不认识的参数：$1"; exit 2;; esac; done

WB="$(cd "$(dirname "$0")/.." && pwd)"; PD="$HOME/.hermes/profiles/$PROFILE"; TS="$(date +%Y%m%d-%H%M%S)"
say() { echo "· $*"; }
run() { if [ $DRY -eq 1 ]; then echo "  [只演示] $*"; else "$@"; fi; }

command -v hermes >/dev/null || { echo "没找到 hermes 命令：先装 Hermes，或者只用工作台（不装 Agent 也能跑一圈）。"; exit 1; }
[ -d "$PD" ] || { echo "没有 profile「$PROFILE」：先运行 hermes profile create $PROFILE，再跑这个脚本。"; exit 1; }
[ -d "$WB/skills" ] || { echo "仓里没有 skills/ 目录"; exit 1; }
echo "工作台：$WB"; echo "装到：  $PD"; [ $DRY -eq 1 ] && echo "（只演示，不动手）"

say "1/5 备份这次会动到的东西 → $PD/backups/before-ads-workbench-$TS.tgz"
if [ $DRY -eq 0 ]; then
  mkdir -p "$PD/backups"
  ( cd "$PD" && tar -czf "backups/before-ads-workbench-$TS.tgz" $(ls -d SOUL.md skills scripts cron/jobs.json 2>/dev/null) )
fi

say "2/5 人设 SOUL.md（绑定到这个工作台目录）"
if [ $DRY -eq 0 ]; then
  sed "s|{{WORKBENCH}}|$WB|g" "$WB/agent/SOUL.md" > "$PD/SOUL.md.new"
  [ -f "$WB/agent/SOUL.local.md" ] && { echo; cat "$WB/agent/SOUL.local.md"; } >> "$PD/SOUL.md.new"    # 本机专属的补充（不进仓）
  mv "$PD/SOUL.md.new" "$PD/SOUL.md"
fi

say "3/5 技能包 → $PD/skills/"
run bash "$WB/skills/install.sh" --target hermes --profile "$PROFILE"
if [ -n "$OLD" ]; then                      # 可以给多个，空格隔开
  for pat in $OLD; do for d in "$PD"/skills/$pat; do
    [ -d "$d" ] || continue
    case "$(basename "$d")" in ads-*) continue;; esac          # 刚装的新技能不动
    say "    旧技能挪走：$(basename "$d") → skill-backups/$TS/"
    run mkdir -p "$PD/skill-backups/$TS"; run mv "$d" "$PD/skill-backups/$TS/"
  done; done
fi

say "4/5 定时脚本 → $PD/scripts/ads-weekly.sh"
if [ $DRY -eq 0 ]; then
  mkdir -p "$PD/scripts"
  sed "s|__WORKBENCH__|$WB|g" "$WB/agent/ads-weekly.sh" > "$PD/scripts/ads-weekly.sh"; chmod +x "$PD/scripts/ads-weekly.sh"
fi

if [ $CRON -eq 1 ]; then
  if grep -q "ads-weekly.sh" "$PD/cron/jobs.json" 2>/dev/null; then
    say "5/5 每周定时已经有了，不重复建"
  else
    say "5/5 每周定时：$SCHEDULE 跑 ads-weekly.sh（不经过模型，脚本就是任务；结果只留本机）"
    run hermes -p "$PROFILE" cron create "$SCHEDULE" --no-agent --script ads-weekly.sh --name "$JOB" --deliver local
  fi
else
  say "5/5 跳过每周定时（--no-cron）"
fi

echo
echo "装好了。接下来："
echo "  1) 先空跑一遍：  bash $PD/scripts/ads-weekly.sh --dry-run"
echo "  2) 页面里问它：  需要这个 profile 有一把 API 服务密钥（见 agent/README.md 第 3 步）；没有也不影响每周一圈。"
echo "  3) 想撤回：      tar -xzf $PD/backups/before-ads-workbench-$TS.tgz -C $PD ；定时用 hermes -p $PROFILE cron list / remove"
