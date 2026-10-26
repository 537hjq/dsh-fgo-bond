# -*- coding: utf-8 -*-
"""Fetch all 黑话 (slang) pages under 'FGO黑话·梗·成句/...' and save their wikitext."""
import json, os, time, urllib.parse, urllib.request, concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DSH-fgo/1.0"}
PREFIX = "FGO黑话·梗·成句/"


def api(params):
    url = "https://fgo.wiki/api.php?" + urllib.parse.urlencode(params)
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            time.sleep(1.5 + i * 2)
    raise RuntimeError("api failed: %s" % params)


def raw(title):
    url = "https://fgo.wiki/index.php?title=" + urllib.parse.quote(title) + "&action=raw"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def main():
    titles, cont = [], {}
    while True:
        p = {"action": "query", "list": "allpages", "apprefix": PREFIX,
             "aplimit": "500", "format": "json", "apnamespace": "0"}
        p.update(cont)
        d = api(p)
        titles += [m["title"] for m in d["query"]["allpages"]]
        if "continue" in d:
            cont = d["continue"]
        else:
            break
    print("slang pages:", len(titles), flush=True)

    pages = {}

    def work(t):
        try:
            return t, raw(t)
        except Exception as e:  # noqa
            print("FAIL", t, e, flush=True)
            return t, ""

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i, (t, txt) in enumerate(ex.map(work, titles), 1):
            pages[t] = txt
            if i % 40 == 0:
                print("fetched", i, flush=True)

    out = os.path.join(RAW, "slang_pages.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    print("saved", out, len(pages))


if __name__ == "__main__":
    main()
