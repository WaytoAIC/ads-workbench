#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 入口（等价写法）：不起网页，直接跑每周一圈，打印一段纯文本摘要；设了 FEISHU_WEBHOOK 且 ads.config.json 的 weekly.推送＝摘要，才会把摘要推到飞书群（默认不推）。
用法：python3 _脚本/agent_run.py [--root 数据目录] [--trigger 定时] [--dry-run] [--no-llm]
现在是 _脚本/weekly.py 的薄包装：八步都在那边（读回状态 → 数据体检 → 跑一圈 → 经营核算 → 模型补位 → 自检 → 起草周报 → 留痕）。
退出码沿用老约定：有失败或缺输入＝2，正常＝0（weekly.py 自己分得更细：1 有步骤失败 / 2 缺输入没跑）。
只读数据、只写本机状态库（<数据目录>/工作台.db），不碰任何广告后台。只用标准库。"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import weekly  # noqa: E402
from weekly import REQUIRED, load_app, preflight, push  # noqa: E402,F401  老的导入点保留


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0]); ap.add_argument("--root", default=REPO, help="数据目录（默认仓库根）")
    ap.add_argument("--trigger", default="定时", help="触发方式，写进运行记录（默认「定时」）")
    ap.add_argument("--dry-run", action="store_true", help="演练：不写状态库、不调模型、不推送"); ap.add_argument("--no-llm", action="store_true", help="跳过模型补位")
    a = ap.parse_args()
    sys.exit(2 if weekly.run(a.root, a.trigger, a.dry_run, a.no_llm) else 0)


if __name__ == "__main__": main()
