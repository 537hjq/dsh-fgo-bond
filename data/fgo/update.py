# -*- coding: utf-8 -*-
"""One-shot refresh: 数据页 -> SMW -> 从者详情页 -> 解析入库。

用法: python update.py
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
STEPS = [
    ("fetch_all.py", "抓取英灵/礼装数据页 + SMW 字段"),
    ("build.py", "生成 servants / craft_essences 表与 CSV"),
    ("fetch_pages.py", "增量抓取从者详情页（宝具/技能用）"),
    ("build_details.py", "解析基础数值/宝具/技能/羁绊礼装"),
    ("fetch_traits.py", "抓取特性归属（含兽科从者等条件特性）"),
    ("fetch_slang.py", "抓取 FGO 黑话·梗·成句 全部词条"),
    ("build_slang.py", "构建黑话 → 从者/礼装 映射"),
]


def main():
    t0 = time.time()
    for script, desc in STEPS:
        print("\n=== %s: %s ===" % (script, desc), flush=True)
        r = subprocess.run([PY, os.path.join(HERE, script)], cwd=HERE)
        if r.returncode != 0:
            print("!! %s failed (exit %d)" % (script, r.returncode), flush=True)
            sys.exit(r.returncode)
    print("\n更新完成，用时 %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
