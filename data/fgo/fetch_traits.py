# -*- coding: utf-8 -*-
"""Fetch servant trait membership (特性：XXX pages) needed by bond-CE conditions.

Creates table `servant_traits(servant_id, trait)` in fgo.db, merging:
- 基础数值模板里的 特性1..N
- 维基「特性：XXX」页面上列出的从者（含条件特性，如 兽科从者[条件]）
"""
import json, os, re, sqlite3, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
DB = os.path.join(HERE, "fgo.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DSH-fgo/1.0"}
ALWAYS = ["兽科从者", "持有灵衣之人", "活在当下的人类", "拥有星之力的从者",
          "Fate/stay night从者", "兔子系从者", "七骑士的从者"]


def api(params, tries=3):
    url = "https://fgo.wiki/api.php?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 + i * 2)
    raise last


def clean_atom(a):
    a = re.sub(r"[（(].*?[)）]", "", a)          # 去掉括号补充说明
    return a.strip("〔〕[]()（） 　")


def collect_condition_atoms(con):
    atoms = set()
    for (eff,) in con.execute(
            "select effect from craft_essences where effect like '%牵绊%' and type!='牵绊'"):
        if not eff:
            continue
        m = re.search(r"关卡通关时(.+?)获得的牵绊(?:值|点数)增加", eff)
        if not m:
            continue
        cond = m.group(1).replace("特性", "").replace("职阶", "")
        for alt in re.split(r"或", cond):
            for atom in re.split(r"且", alt):
                a = clean_atom(atom)
                if len(a) >= 2:
                    atoms.add(a)
    return atoms


SKIP = {"Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker",
        "Avenger", "Alterego", "Ruler", "Foreigner", "Pretender", "MoonCancer",
        "Shielder", "Beast", "UnBeast", "七骑士", "秩序", "混沌", "中立", "善", "恶",
        "中庸", "夏", "女性", "男性", "天", "地", "人", "星", "兽"}


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    atoms = collect_condition_atoms(con) | set(ALWAYS)
    atoms = sorted(a for a in atoms if a not in SKIP)
    print("trait pages to check:", atoms, flush=True)

    # servant name -> id
    name2id = {}
    for r in con.execute("select id,name_cn,name_link,wiki_page from servants"):
        for k in ("name_cn", "name_link", "wiki_page"):
            if r[k]:
                name2id.setdefault(r[k].strip(), r["id"])
    for r in con.execute("select servant_id,key,value from servant_params"):
        if r["key"] in ("中文名", "日文名", "英文名", "中文战斗名", "中文卡面名") and r["value"]:
            name2id.setdefault(r["value"].strip(), r["servant_id"])

    traits = {}
    for t in atoms:
        page = "特性：" + t
        try:
            d = api({"action": "parse", "page": page, "prop": "text",
                     "format": "json", "disablelimitreport": "1"})
        except Exception as e:  # noqa
            print("skip", t, e, flush=True)
            continue
        html = d.get("parse", {}).get("text", {}).get("*", "")
        titles = [urllib.parse.unquote(x).replace("_", " ")
                  for x in re.findall(r'href="/w/([^"#?]+)"', html)]
        ids = sorted({name2id[x] for x in titles if x in name2id})
        traits[t] = ids
        print(t, len(ids), flush=True)

    with open(os.path.join(RAW, "traits.json"), "w", encoding="utf-8") as f:
        json.dump(traits, f, ensure_ascii=False, indent=1)

    con.executescript("DROP TABLE IF EXISTS servant_traits;"
                      "CREATE TABLE servant_traits (servant_id INTEGER, trait TEXT);")
    rows = []
    for r in con.execute("select servant_id,key,value from servant_params"):
        if r["key"].startswith("特性") and r["value"] and "备注" not in r["key"]:
            rows.append((r["servant_id"], r["value"].strip()))
    for t, ids in traits.items():
        for sid in ids:
            rows.append((sid, t))
    con.executemany("INSERT INTO servant_traits VALUES (?,?)", rows)
    con.execute("CREATE INDEX idx_traits ON servant_traits(servant_id)")
    con.commit()
    con.close()
    print("servant_traits rows:", len(rows))


if __name__ == "__main__":
    main()
