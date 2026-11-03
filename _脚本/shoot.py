# -*- coding: utf-8 -*-
"""给实操手册截图：无头 Chrome 开页面 → PIL 裁掉空白。
用法：python3 _脚本/shoot.py <url> <输出.png> [--w 1440] [--h 900] [--full]
  --full：高窗口整页截，再按内容裁边（配合页面的 ?only=区块id 只留一块）；不带 --full 就是 w×h 首屏。
页面参数：only=s1,tree 只显示这些区块并隐藏侧栏顶栏；open=first|all 展开审批分组；ap=全部 审批筛选；sel=H:H1 选中诊断树节点；hk=2 历史回放第几圈。"""
import os, subprocess, sys, tempfile
from PIL import Image, ImageChops
CHROME = next((p for p in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"] if os.path.exists(p)), None)
if not CHROME: sys.exit("没找到 Chrome")
url, out = sys.argv[1], sys.argv[2]; a = sys.argv
w = int(a[a.index("--w") + 1]) if "--w" in a else 1440; h = int(a[a.index("--h") + 1]) if "--h" in a else 900; full = "--full" in a
H = 6000 if full else h
tmp = tempfile.mkdtemp()
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2", f"--window-size={w},{H}", "--virtual-time-budget=6000",
                f"--user-data-dir={tmp}", f"--screenshot={out}", url], check=True, capture_output=True)
im = Image.open(out).convert("RGB")
if full:
    bg = im.getpixel((im.width - 2, im.height - 2)); diff = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L").point(lambda v: 255 if v > 8 else 0)
    bb = diff.getbbox()
    if bb: pad = 16; im = im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(im.width, bb[2] + pad), min(im.height, bb[3] + pad)))
if im.width > w: im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)   # 2 倍采样后缩回 1 倍宽，字清楚、文件小
im.save(out, optimize=True); print(out, im.size)
