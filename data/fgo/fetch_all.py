# -*- coding: utf-8 -*-
"""Fetch FGO wiki (Mooncell) servant & craft-essence data into local JSON."""
import json, os, sys, time, urllib.parse, urllib.request

BASE = "https://fgo.wiki"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DSH-data-collector/1.0"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
os.makedirs(OUT, exist_ok=True)


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa
            last = e
            time.sleep(2 + i * 3)
    raise last


def save(name, text):
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("saved", name, len(text))


def raw_page(title, fname):
    url = BASE + "/index.php?title=" + urllib.parse.quote(title) + "&action=raw"
    save(fname, fetch(url))


def ask_all(query, fname_base, limit=500, max_offset=9000):
    """Paginate SMW ask query (limit/offset must live inside the query string)."""
    allres = {}
    offset = 0
    page = 0
    while offset < max_offset:
        q = "%s|limit=%d|offset=%d" % (query, limit, offset)
        url = (BASE + "/api.php?action=ask&format=json&query="
               + urllib.parse.quote(q, safe=""))
        data = json.loads(fetch(url))
        qd = data.get("query", {})
        results = qd.get("results", {}) or {}
        n = len(results)
        for k, v in results.items():
            allres[k] = v
        page += 1
        print(fname_base, "page", page, "offset", offset, "got", n, "total", len(allres), flush=True)
        if n == 0:
            break
        offset += n
        nxt = data.get("query-continue-offset")
        if nxt is not None and nxt != offset:
            offset = nxt
        if n < limit:
            break
        time.sleep(0.3)
    save(fname_base + ".json", json.dumps(allres, ensure_ascii=False))


if __name__ == "__main__":
    # 1. raw data pages
    raw_page("英灵图鉴/数据", "servants_page.txt")
    raw_page("礼装图鉴/数据", "craft_essences_page.txt")

    # 2. SMW: servants
    servant_q = ("[[分类:从者]]|?序号|?稀有度|?职阶|?属性1|?属性2|?副属性|?性别"
                 "|?基础ATK|?满级ATK|?基础HP|?满级HP|?COST|?画师|?声优")
    ask_all(servant_q, "servants_smw", 500)

    # 3. SMW: craft essences - basic
    ce_q = ("[[分类:概念礼装]]|?礼装序号|?中文名称|?日文名称|?稀有度|?COST"
            "|?基础ATK|?满级ATK|?基础HP|?满级HP|?画师")
    ask_all(ce_q, "ces_smw", 500)

    # 4. SMW: craft essence skills
    ce_skill_q = "[[分类:概念礼装]]|?礼装序号|?礼装持有技能"
    ask_all(ce_skill_q, "ces_skill_smw", 500)

    print("DONE")
