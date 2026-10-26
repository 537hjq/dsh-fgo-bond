# -*- coding: utf-8 -*-
"""Fetch every servant detail page (wikitext) so 宝具/技能 can be parsed.

Incremental: pages already on disk with non-trivial size are skipped unless --force.
"""
import os, sys, time, urllib.parse, urllib.request, sqlite3, concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
PAGES = os.path.join(RAW, "pages")
os.makedirs(PAGES, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DSH-fgo/1.0"}


def fetch(title, tries=3):
    url = "https://fgo.wiki/index.php?title=" + urllib.parse.quote(title) + "&action=raw"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 + i * 2)
    raise last


def main(force=False):
    con = sqlite3.connect(os.path.join(HERE, "fgo.db"))
    rows = con.execute("select id, wiki_page, name_cn from servants order by id").fetchall()
    con.close()
    todo = []
    for sid, page, name in rows:
        if not page:
            continue
        p = os.path.join(PAGES, "%d.txt" % sid)
        if not force and os.path.exists(p) and os.path.getsize(p) > 500:
            continue
        todo.append((sid, page, p))
    print("pages to fetch:", len(todo), flush=True)

    def work(item):
        sid, page, p = item
        try:
            txt = fetch(page)
        except Exception as e:  # noqa
            print("FAIL", sid, page, e, flush=True)
            return 0
        if txt.lstrip().startswith("#重定向"):
            target = txt.split("[[", 1)[1].split("]]", 1)[0].split("|")[0]
            try:
                txt = fetch(target)
            except Exception as e:  # noqa
                print("FAIL-REDIR", sid, target, e, flush=True)
                return 0
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(txt)
        return 1

    done = 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for n in ex.map(work, todo):
            done += n
            if done and done % 25 == 0:
                print("fetched", done, flush=True)
    print("DONE fetched", done, flush=True)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
