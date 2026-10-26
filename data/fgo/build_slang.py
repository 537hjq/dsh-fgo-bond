# -*- coding: utf-8 -*-
"""Build 黑话(slang) -> 从者/礼装 mapping tables from raw/slang_pages.json."""
import json, os, re, sqlite3, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
DB = os.path.join(HERE, "fgo.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DSH-fgo/1.0"}
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def api(params):
    url = "https://fgo.wiki/api.php?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def make_excerpt(text, limit=260):
    if not text:
        return ""
    m = re.search(r"==+\s*名词释义\s*==+", text)
    body = text[m.end():] if m else text
    body = re.split(r"\n==+[^=\n]+==+\n", body, maxsplit=1)[0]
    body = re.sub(r"\{\{[^{}]*\}\}", "", body)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", body)
    body = re.sub(r"\[\[([^\]]*)\]\]", r"\1", body)
    body = re.sub(r"'''?", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:limit]


def resolve_redirects(titles):
    m = {}
    uniq = sorted(set(titles))
    for i in range(0, len(uniq), 50):
        chunk = uniq[i:i + 50]
        d = api({"action": "query", "titles": "|".join(chunk),
                 "redirects": "1", "format": "json"})
        q = d.get("query", {})
        for n in q.get("normalized", []):
            m[n["from"]] = n["to"]
        for r in q.get("redirects", []):
            m[r["from"]] = r["to"]
    # follow chains
    def resolve(t):
        seen = set()
        while t in m and t not in seen:
            seen.add(t)
            t = m[t]
        return t
    return {t: resolve(t) for t in uniq}


def main():
    pages = json.load(open(os.path.join(RAW, "slang_pages.json"), encoding="utf-8"))
    parsed = {}
    all_targets = []
    for title, text in pages.items():
        links = []
        for mm in LINK_RE.finditer(text or ""):
            tgt = mm.group(1).split("|")[0].split("#")[0].strip()
            if not tgt or ":" in tgt:
                continue
            links.append(tgt)
        parsed[title] = links
        all_targets.extend(links)

    resolved = resolve_redirects(all_targets)
    print("unique targets:", len(set(all_targets)), flush=True)

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
    DROP TABLE IF EXISTS slang_servant;
    DROP TABLE IF EXISTS slang_ce;
    DROP TABLE IF EXISTS slang_term;
    CREATE TABLE slang_servant (term TEXT, category TEXT, servant_id INTEGER, ord INTEGER);
    CREATE TABLE slang_ce (term TEXT, category TEXT, ce_id INTEGER, ord INTEGER);
    CREATE TABLE slang_term (term TEXT, category TEXT, excerpt TEXT);
    """)

    # name -> id maps
    s_map = {}
    for r in con.execute("select id,name_cn,name_link,wiki_page from servants"):
        for k in ("name_cn", "name_link", "wiki_page"):
            v = (r[k] or "").strip()
            if v:
                s_map.setdefault(v, r["id"])
    for r in con.execute("select servant_id,key,value from servant_params"):
        if r["key"] in ("中文名", "日文名", "英文名", "中文战斗名", "中文卡面名") and r["value"]:
            s_map.setdefault(r["value"].strip(), r["servant_id"])

    c_map = {}
    for r in con.execute("select id,name,name_link,wiki_page from craft_essences"):
        for k in ("name", "name_link", "wiki_page"):
            v = (r[k] or "").strip()
            if v:
                c_map.setdefault(v, r["id"])

    cur = con.cursor()
    n_s = n_c = 0
    for title, links in parsed.items():
        parts = title.split("/")
        category = parts[1] if len(parts) >= 3 else ""
        term = parts[-1]
        cur.execute("INSERT INTO slang_term VALUES (?,?,?)",
                    (term, category, make_excerpt(pages.get(title, ""))))
        seen_s, seen_c = set(), set()
        for i, tgt in enumerate(links):
            fin = resolved.get(tgt, tgt)
            sid = s_map.get(fin)
            if sid and sid not in seen_s:
                seen_s.add(sid)
                cur.execute("INSERT INTO slang_servant VALUES (?,?,?,?)", (term, category, sid, i))
                n_s += 1
            cid = c_map.get(fin)
            if cid and cid not in seen_c:
                seen_c.add(cid)
                cur.execute("INSERT INTO slang_ce VALUES (?,?,?,?)", (term, category, cid, i))
                n_c += 1
    cur.execute("CREATE INDEX idx_slang_s ON slang_servant(term)")
    cur.execute("CREATE INDEX idx_slang_c ON slang_ce(term)")
    con.commit()
    con.close()
    print("slang_servant rows:", n_s, "slang_ce rows:", n_c)


if __name__ == "__main__":
    main()
