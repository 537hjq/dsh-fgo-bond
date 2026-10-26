# -*- coding: utf-8 -*-
"""Build structured servant / craft-essence datasets from raw wiki pages + SMW dumps."""
import json, os, re, sqlite3, csv

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")


def parse_blocks(text):
    text = text.replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    items = []
    for b in blocks:
        d = {}
        for line in b.split("\n"):
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
        if d.get("id"):
            items.append(d)
    return items


def load_smw(name):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)


def pv(p, key):
    """first value of a printout, unwrapping page-type dicts"""
    v = p.get(key)
    if not v:
        return ""
    x = v[0]
    if isinstance(x, dict):
        return x.get("fulltext", "")
    return x


def pv_all(p, key):
    v = p.get(key)
    if not v:
        return ""
    out = []
    for x in v:
        if isinstance(x, dict):
            out.append(x.get("fulltext", ""))
        else:
            out.append(str(x))
    return "|".join([a for a in out if a])


def build_servants():
    page = parse_blocks(open(os.path.join(RAW, "servants_page.txt"), encoding="utf-8").read())
    smw = load_smw("servants_smw.json")

    # map smw by integer id
    attrs = {}
    for page_name, rec in smw.items():
        p = rec.get("printouts", {})
        sid = pv(p, "序号")
        try:
            key = int(str(sid).strip())
        except Exception:
            continue
        if not key:
            continue
        attrs.setdefault(key, {})
        a = attrs[key]
        # prefer records that actually carry attributes
        if a and not pv(p, "职阶"):
            continue
        a.update({
            "rarity": pv(p, "稀有度"),
            "class": pv(p, "职阶"),
            "attr1": pv_all(p, "属性1"),
            "attr2": pv_all(p, "属性2"),
            "sub_attr": pv_all(p, "副属性"),
            "gender": pv_all(p, "性别"),
            "atk_base": pv(p, "基础ATK"),
            "atk_max": pv(p, "满级ATK"),
            "hp_base": pv(p, "基础HP"),
            "hp_max": pv(p, "满级HP"),
            "cost": pv(p, "COST"),
            "illustrator": pv_all(p, "画师"),
            "voice": pv_all(p, "声优"),
            "smw_page": page_name,
        })

    rows = []
    for d in page:
        sid = int(d["id"])
        a = attrs.get(sid, {})
        rows.append({
            "id": sid,
            "name_cn": d.get("name_cn", ""),
            "name_jp": d.get("name_jp", ""),
            "name_en": d.get("name_en", ""),
            "name_link": d.get("name_link", ""),
            "alias": d.get("name_other", ""),
            "obtain_method": d.get("method", "").replace("<br>", "|").replace("\n", "|"),
            "tag": d.get("tag", ""),
            "rarity": a.get("rarity", ""),
            "class": a.get("class", ""),
            "alignment1": a.get("attr1", ""),
            "alignment2": a.get("attr2", ""),
            "sub_attribute": a.get("sub_attr", ""),
            "gender": a.get("gender", ""),
            "atk_base": a.get("atk_base", ""),
            "atk_max": a.get("atk_max", ""),
            "hp_base": a.get("hp_base", ""),
            "hp_max": a.get("hp_max", ""),
            "cost": a.get("cost", ""),
            "illustrator": a.get("illustrator", ""),
            "voice": a.get("voice", ""),
            "wiki_page": a.get("smw_page", d.get("name_link", "")),
        })
    rows.sort(key=lambda r: r["id"])
    return rows


def build_ces():
    page = parse_blocks(open(os.path.join(RAW, "craft_essences_page.txt"), encoding="utf-8").read())
    smw = load_smw("ces_smw.json")
    skills = load_smw("ces_skill_smw.json")

    attrs = {}
    for page_name, rec in smw.items():
        p = rec.get("printouts", {})
        cid = pv(p, "礼装序号")
        try:
            key = int(str(cid).strip())
        except Exception:
            continue
        attrs.setdefault(key, {}).update({
            "name_cn": pv(p, "中文名称"),
            "name_jp": pv(p, "日文名称"),
            "rarity": pv(p, "稀有度"),
            "cost": pv(p, "COST"),
            "atk_base": pv(p, "基础ATK"),
            "atk_max": pv(p, "满级ATK"),
            "hp_base": pv(p, "基础HP"),
            "hp_max": pv(p, "满级HP"),
            "illustrator": pv_all(p, "画师"),
            "smw_page": page_name,
        })

    skill_map = {}
    for page_name, rec in skills.items():
        p = rec.get("printouts", {})
        cid = pv(p, "礼装序号")
        try:
            key = int(str(cid).strip())
        except Exception:
            continue
        skill_map[key] = pv(p, "礼装持有技能")

    rows = []
    for d in page:
        cid = int(d["id"])
        a = attrs.get(cid, {})
        pname = d.get("name", "")
        cn_name = a.get("name_cn", "")
        import re as _re
        kana = _re.compile(r"[\u3040-\u309f\u30a1-\u30fa]")
        # 页面标题仍是日文、而 SMW 里有中文名时，优先用中文名
        name = cn_name if (cn_name and kana.search(pname)) else pname
        rows.append({
            "id": cid,
            "name": name or cn_name,
            "name_link": d.get("name_link", ""),
            "alias": d.get("name_other", ""),
            "name_jp": a.get("name_jp", ""),
            "effect": d.get("des", ""),
            "effect_max": d.get("des_max", ""),
            "skill_smw": skill_map.get(cid, ""),
            "tag": d.get("tag", ""),
            "type": d.get("type", ""),
            "event": d.get("event", ""),
            "rarity": a.get("rarity", ""),
            "cost": a.get("cost", ""),
            "atk_base": a.get("atk_base", ""),
            "atk_max": a.get("atk_max", ""),
            "hp_base": a.get("hp_base", ""),
            "hp_max": a.get("hp_max", ""),
            "illustrator": a.get("illustrator", ""),
            "wiki_page": a.get("smw_page", d.get("name_link", "")),
        })
    rows.sort(key=lambda r: r["id"])
    return rows


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_db(servants, ces):
    path = os.path.join(HERE, "fgo.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("""CREATE TABLE servants (
        id INTEGER PRIMARY KEY, name_cn TEXT, name_jp TEXT, name_en TEXT, name_link TEXT,
        alias TEXT, obtain_method TEXT, tag TEXT, rarity INTEGER, class TEXT,
        alignment1 TEXT, alignment2 TEXT, sub_attribute TEXT, gender TEXT,
        atk_base INTEGER, atk_max INTEGER, hp_base INTEGER, hp_max INTEGER, cost INTEGER,
        illustrator TEXT, voice TEXT, wiki_page TEXT)""")
    cur.execute("""CREATE TABLE craft_essences (
        id INTEGER PRIMARY KEY, name TEXT, name_link TEXT, alias TEXT, name_jp TEXT,
        effect TEXT, effect_max TEXT, skill_smw TEXT, tag TEXT, type TEXT, event TEXT,
        rarity INTEGER, cost INTEGER, atk_base INTEGER, atk_max INTEGER,
        hp_base INTEGER, hp_max INTEGER, illustrator TEXT, wiki_page TEXT)""")
    cur.executemany("INSERT INTO servants VALUES (%s)" % ",".join("?" * len(servants[0])),
                    [tuple(r.values()) for r in servants])
    cur.executemany("INSERT INTO craft_essences VALUES (%s)" % ",".join("?" * len(ces[0])),
                    [tuple(r.values()) for r in ces])
    cur.execute("CREATE INDEX idx_servants_name ON servants(name_cn)")
    cur.execute("CREATE INDEX idx_ces_name ON craft_essences(name)")
    con.commit()
    con.close()
    return path


def main():
    servants = build_servants()
    ces = build_ces()
    write_csv(os.path.join(HERE, "servants.csv"), servants)
    write_csv(os.path.join(HERE, "craft_essences.csv"), ces)
    db = write_db(servants, ces)

    from collections import Counter
    lines = []
    lines.append("servants=%d ces=%d db=%s" % (len(servants), len(ces), db))
    lines.append("servants_with_rarity=%d with_class=%d" %
                 (sum(1 for r in servants if r["rarity"] != ""), sum(1 for r in servants if r["class"] != "")))
    lines.append("servants rarity dist: " + str(sorted(Counter(r["rarity"] for r in servants).items(), key=lambda x: str(x[0]))))
    lines.append("servants class dist: " + str(sorted(Counter(r["class"] for r in servants).items(), key=lambda x: -x[1])))
    lines.append("ces_with_rarity=%d with_effect=%d with_skill_smw=%d" %
                 (sum(1 for r in ces if r["rarity"] != ""), sum(1 for r in ces if r["effect"]),
                  sum(1 for r in ces if r["skill_smw"])))
    lines.append("ces rarity dist: " + str(sorted(Counter(r["rarity"] for r in ces).items(), key=lambda x: str(x[0]))))
    lines.append("ces type dist: " + str(sorted(Counter(r["type"] for r in ces).items(), key=lambda x: -x[1])))
    lines.append("servant id range: %d..%d, missing: %s" % (
        servants[0]["id"], servants[-1]["id"],
        [i for i in range(1, servants[-1]["id"] + 1) if i not in {r["id"] for r in servants}][:20]))
    lines.append("ce id range: %d..%d, count gaps: %d" % (
        ces[0]["id"], ces[-1]["id"],
        (ces[-1]["id"] - ces[0]["id"] + 1) - len(ces)))
    with open(os.path.join(HERE, "build_summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
