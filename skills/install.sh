#!/usr/bin/env bash
# 广告经营技能包安装脚本。
# 把 ads-shared 和十个 skill 目录（共 11 个）拷到目标位置。
# 只拷不删：目标位置已有同名目录时，先整体挪进带时间戳的备份目录，再拷新的。
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SHARED="ads-shared"
SKILLS=(
  ads-router
  ads-profit-target
  ads-diagnose
  ads-campaign-task
  ads-search-term
  ads-bid-budget
  ads-path-decision
  ads-weekly-review
  ads-launch
  ads-variant-season
)

TARGET=""
PROFILE="ads-agent"
DEST=""
DRY_RUN=0

usage() {
  cat <<'EOF'
用法：
  ./install.sh --target claude|codex|hermes [--profile 名字] [--dry-run]
  ./install.sh --dest 目录 [--dry-run]

选项：
  --target claude    装到 ~/.claude/skills
  --target codex     装到 ~/.codex/skills（设了 CODEX_HOME 就用它）
  --target hermes    装到 ~/.hermes/profiles/<profile>/skills（设了 HERMES_HOME 就用它）
  --profile 名字     只对 hermes 有用，默认 ads-agent
  --dest 目录        直接指定 skills 根目录（优先于 --target，用来测试或装到别处）
  --dry-run          只打印将要做什么，不创建、不拷贝、不备份
  -h, --help         显示这段说明

行为：
  - 拷 11 个目录：ads-shared（共享口径，不是技能，里面没有 SKILL.md）加十个 skill。
  - 目标位置已有同名目录：整体挪到 <skills 根目录>.bak-<时间戳>/ 下面，再拷新的。
    备份放在 skills 根目录之外，是为了不让旧版被当成重复的技能加载。
  - 不删除任何文件，不改目标位置里的其他目录。
EOF
}

die() { echo "错误：$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)  [ "$#" -ge 2 ] || die "--target 后面要跟 claude、codex 或 hermes"; TARGET="$2"; shift 2 ;;
    --profile) [ "$#" -ge 2 ] || die "--profile 后面要跟名字"; PROFILE="$2"; shift 2 ;;
    --dest)    [ "$#" -ge 2 ] || die "--dest 后面要跟目录"; DEST="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "不认识的参数：$1" ;;
  esac
done

# ---- 目标目录 ----
if [ -z "$DEST" ]; then
  case "$TARGET" in
    claude) DEST="$HOME/.claude/skills" ;;
    codex)  DEST="${CODEX_HOME:-$HOME/.codex}/skills" ;;
    hermes)
      case "$PROFILE" in
        ""|.|..|*/*|*\\*) die "profile 名字不合法：$PROFILE" ;;
      esac
      PROFILE_DIR="${HERMES_HOME:-$HOME/.hermes}/profiles/$PROFILE"
      if [ ! -d "$PROFILE_DIR" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then
          echo "注意：没有找到 profile 目录 $PROFILE_DIR（真装时会停下，不会替你新建 profile）"
        else
          die "没有找到 profile 目录 $PROFILE_DIR；先在 Hermes 里建好这个 profile，或用 --profile 指定已有的"
        fi
      fi
      DEST="$PROFILE_DIR/skills"
      ;;
    "") usage >&2; die "要用 --target 或 --dest 指定装到哪" ;;
    *)  die "--target 只认 claude、codex、hermes，收到的是：$TARGET" ;;
  esac
fi
DEST="${DEST%/}"
[ -n "$DEST" ] || die "目标目录不能是根目录"

# ---- 源目录自检 ----
[ -d "$SRC/$SHARED" ] || die "源目录里没有 $SHARED"
[ ! -e "$SRC/$SHARED/SKILL.md" ] || die "$SHARED 里不该有 SKILL.md（它不是可触发的技能）"
for s in "${SKILLS[@]}"; do
  [ -f "$SRC/$s/SKILL.md" ] || die "源目录里缺 $s/SKILL.md"
done
case "$DEST/" in
  "$SRC/"*) die "目标目录不能在技能包源目录里面" ;;
esac

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$DEST.bak-$TS"
ALL=("$SHARED" "${SKILLS[@]}")

if [ "$DRY_RUN" -eq 1 ]; then
  echo "【演练】不会改动任何文件"
fi
echo "来源：$SRC"
echo "目标：$DEST"
echo "共 ${#ALL[@]} 个目录："

copied=0
backed=0
for d in "${ALL[@]}"; do
  kind="skill"
  [ "$d" = "$SHARED" ] && kind="共享口径"
  if [ -e "$DEST/$d" ]; then
    echo "  备份  $DEST/$d  ->  $BACKUP/$d"
    backed=$((backed + 1))
    if [ "$DRY_RUN" -eq 0 ]; then
      mkdir -p "$BACKUP"
      mv "$DEST/$d" "$BACKUP/$d"
    fi
  fi
  echo "  拷贝  $d（$kind）  ->  $DEST/$d"
  copied=$((copied + 1))
  if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$DEST"
    # 用 tar 管道拷，顺手跳过 .DS_Store；不删除任何东西
    (cd "$SRC" && tar -cf - --exclude '.DS_Store' "$d") | (cd "$DEST" && tar -xf -)
  fi
done

echo
if [ "$DRY_RUN" -eq 1 ]; then
  echo "演练结束：将拷贝 $copied 个目录，其中 $backed 个会先备份到 $BACKUP/。"
  echo "去掉 --dry-run 才会真的安装。"
else
  echo "装好了：拷贝 $copied 个目录到 $DEST。"
  if [ "$backed" -gt 0 ]; then
    echo "原有的 $backed 个同名目录已挪到 $BACKUP/（没有删除）。"
  fi
  echo "如果应用会缓存技能，重启一下再用。入口技能是 ads-router。"
fi
