# -*- coding: utf-8 -*-
"""Parse servant detail wikitext into 基础数值 / 宝具 / 技能 tables, and map 羁绊礼装 from CE data."""
import json, os, re, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "raw", "pages")
DB = os.path.join(HERE, "fgo.db")


# ---------------- wikitext helpers ----------------
def find_templates(text, tpl_name):
    out = []
    key = "{{" + tpl_name
    i = 0
    while True:
        p = text.find(key, i)
        if p < 0:
            break
        nxt = text[p + len(key)] if p + len(key) < len(text) else ""
        if nxt not in ("|", "}", "\n", "\r", " "):
            i = p + len(key)
            continue
        depth, j = 0, p
        while j < len(text):
            if text.startswith("{{", j):
                depth += 1
                j += 2
                continue
            if text.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    inner = text[p + 2:j - 2]
                    # drop the template name itself, keep the parameter body
                    body = inner.split("|", 1)[1] if "|" in inner else ""
                    out.append((p, j, body))
                    break
                continue
            j += 1
        i = j if j > p else p + 2
    return out


def split_params(inner):
    parts, buf = [], []
    db = sb = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        two = inner[i:i + 2]
        if two == "{{":
            db += 1
            buf.append(two)
            i += 2
            continue
        if two == "}}":
            db -= 1
            buf.append(two)
            i += 2
            continue
        if two == "[[":
            sb += 1
            buf.append(two)
            i += 2
            continue
        if two == "]]":
            sb -= 1
            buf.append(two)
            i += 2
            continue
        if ch == "|" and db == 0 and sb == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def clean(v):
    if v is None:
        return ""
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<ref[^>]*/>", "", v)
    v = re.sub(r"\{\{color\|[^|]*\|([^{}]*)\}\}", r"\1", v)
    v = re.sub(r"\{\{ruby\|([^|]*)\|([^}]*)\}\}", r"\1", v)
    v = re.sub(r"\{\{ja\|([^{}]*)\}\}", r"\1", v)
    v = re.sub(r"\{\{修正\|([^|}]*)\|[^{}]*\}\}", r"\1", v)
    v = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\[\[([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = v.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    v = re.sub(r"'''?", "", v)
    return re.sub(r"\s+", " ", v).strip()


def kv_params(parts):
    d, pos = {}, []
    for p in parts:
        eq = p.find("=")
        cm = p.find("<!--")
        if eq > 0 and (cm == -1 or eq < cm):
            k = p[:eq].strip()
            if k and re.fullmatch(r"[\w\u4e00-\u9fff（）()・/\-+ ]{1,40}", k):
                d[k] = p[eq + 1:]
                continue
        pos.append(p)
    return d, pos


def positional(parts):
    pos = kv_params(parts)[1]
    if pos and pos[0].strip() == "":
        pos = pos[1:]
    return pos


def section(text, name, next_names):
    m = re.search(r"^==%s==\s*$" % re.escape(name), text, re.M)
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for n in next_names:
        m2 = re.search(r"^==%s==\s*$" % re.escape(n), text[start:], re.M)
        if m2:
            end = min(end, start + m2.start())
    return text[start:end]


# ---------------- parsers ----------------
NP_KEYS = ["中文名", "国服上标", "日文名", "日服上标", "卡色", "类型", "阶级", "种类"]


def parse_np(blocks):
    raw = []
    for _s, _e, inner in blocks:
        d, _ = kv_params(split_params(inner))
        eff = []
        for letter in "ABCDEFGH":
            desc = d.get("效果" + letter, "")
            if not desc.strip():
                continue
            vals = [clean(d.get("数值%s%d" % (letter, i), "")) for i in range(1, 6)]
            while vals and vals[-1] == "":
                vals.pop()
            eff.append({"desc": clean(desc), "values": vals})
        rec = {k: clean(d.get(k, "")) for k in NP_KEYS}
        rec["effects"] = eff
        if rec["中文名"] or rec["日文名"]:
            raw.append(rec)
    # group by Chinese name, keep the last (strengthened) version
    order, byname = [], {}
    for r in raw:
        n = r["中文名"]
        if n not in byname:
            order.append(n)
            byname[n] = []
        byname[n].append(r)
    out = []
    for n in order:
        versions = byname[n]
        r = dict(versions[-1])
        r["strengthened"] = len(versions) > 1
        out.append(r)
    return out


def looks_value(v):
    v = v.strip()
    if v in ("", "∅", "-", "—"):
        return True
    return bool(re.match(r"^[-+]?\d+(\.\d+)?%?(\*N)?$", v))


def parse_held_skills(sec):
    events = []
    for m in re.finditer(r"'''技能(\d)[^']*'''", sec):
        events.append((m.start(), "label", "技能" + m.group(1)))
    for s, e, inner in find_templates(sec, "持有技能"):
        events.append((s, "block", inner))
    events.sort(key=lambda x: x[0])
    res, cur = [], ""
    for _, kind, val in events:
        if kind == "label":
            cur = val
            continue
        parts = split_params(val)
        pos = positional(parts)
        named, _ = kv_params(parts)
        if len(pos) < 4:
            continue
        icon, name_cn, name_jp, cd = [clean(x) for x in pos[:4]]
        rest = pos[4:]
        eff, i = [], 0
        while i < len(rest):
            desc = rest[i]
            if desc.strip() != "" and looks_value(desc):
                i += 1
                continue
            vals, j = [], i + 1
            while j < len(rest) and len(vals) < 10 and looks_value(rest[j]):
                vals.append(clean(rest[j]))
                j += 1
            while vals and vals[-1] == "":
                vals.pop()
            if desc.strip() != "" or vals:
                eff.append({"desc": clean(desc), "values": vals})
            i = j if j > i + 1 else i + 1
        res.append({"slot": cur or "技能", "icon": icon, "name_cn": name_cn,
                    "name_jp": name_jp, "cd": cd, "effects": eff,
                    "named": {k: clean(v) for k, v in named.items()}})
    order, byslot = [], {}
    for r in res:
        if r["slot"] not in byslot:
            order.append(r["slot"])
            byslot[r["slot"]] = []
        byslot[r["slot"]].append(r)
    final = []
    for s in order:
        blocks = byslot[s]
        # 优先使用非「剧情限定/助战」版本；其中最后一个通常是强化后版本
        normal = [b for b in blocks if b.get("named", {}).get("用途") != "剧情限定"]
        use = normal or blocks
        r = dict(use[-1])
        r["strengthened"] = len(use) > 1
        final.append(r)
    return final


def parse_class_skills(sec):
    out = []
    blocks = find_templates(sec, "职阶技能")
    if not blocks:
        return out
    # 同一页可能有「真名想起前/后」等多套，取最后一套（最终形态）
    _s, _e, inner = blocks[-1]
    pos = [clean(p) for p in positional(split_params(inner))]
    i = 0
    while i + 3 < len(pos):
        name, rank = pos[i + 1], pos[i + 2]
        if name in ("", "？", "？？", "？？？") or rank in ("？", "？？", "？？？"):
            i += 4
            continue
        out.append({"slot": "职阶技能", "icon": pos[i], "name_cn": name,
                    "rank": rank, "effects": [{"desc": pos[i + 3], "values": []}]})
        i += 4
    for idx, r in enumerate(out, 1):
        r["slot"] = "职阶技能%d" % idx
    return out


def norm(s):
    if not s:
        return ""
    s = s.replace("\u3000", "").replace(" ", "")
    for a, b in (("〔", "("), ("〕", ")"), ("（", "("), ("）", ")"),
                 ("【", "("), ("】", ")"), ("[", "("), ("]", ")"), ("・", "·")):
        s = s.replace(a, b)
    return s.lower()


def parse_base(blocks):
    if not blocks:
        return {}
    d, _ = kv_params(split_params(blocks[0][2]))
    return {k: clean(v) for k, v in d.items() if clean(v)}


# ---------------- bond CE mapping ----------------
JP_CLASS = {
    "セイバー": "Saber", "アーチャー": "Archer", "ランサー": "Lancer", "ライダー": "Rider",
    "キャスター": "Caster", "アサシン": "Assassin", "バーサーカー": "Berserker",
    "アヴェンジャー": "Avenger", "アルターエゴ": "Alterego", "ルーラー": "Ruler",
    "フォーリナー": "Foreigner", "プリテンダー": "Pretender", "ムーンキャンサー": "MoonCancer",
    "シールダー": "Shielder", "ビースト": "Beast",
}


def norm_class(s):
    s = s.strip()
    return JP_CLASS.get(s, s)


def map_bond_ces(con, params):
    """Score-based match of 羁绊礼装 for every servant with parsed 基础数值."""
    rows = con.execute(
        "select id, name, effect, effect_max from craft_essences where type='牵绊'").fetchall()
    con.row_factory = sqlite3.Row
    parsed = []
    for ce in rows:
        eff = (ce["effect"] or "").strip()
        m = re.match(r"^([^（(]+)[（(]([^)）]+)[)）]\s*装[备備]", eff)
        name = m.group(1).strip() if m else ""
        cls = m.group(2).strip() if m else ""
        if not name:
            m2 = re.match(r"^([^（(]+?)\s*装[备備]", eff)
            name = m2.group(1).strip() if m2 else ""
        parsed.append({"ce": ce, "name": name, "cls": norm_class(cls) if cls else ""})

    out = {}
    for sid, p in params.items():
        cls = p.get("职阶", "")
        cls_set = {norm_class(x) for x in re.split(r"[、,，/]", cls) if x.strip()}
        names = set()
        for key in ("中文战斗名", "中文卡面名", "中文名", "日文名", "英文名"):
            n = norm(p.get(key, ""))
            if n:
                names.add(n)
        for alias in p.get("昵称", "").split(","):
            if alias.strip():
                names.add(norm(alias))
        best, best_score = None, 0
        for e in parsed:
            if not e["name"]:
                continue
            bn = norm(e["name"])
            # class filter
            if e["cls"] and cls_set:
                ecls = {norm_class(x) for x in re.split(r"[、,，/]", e["cls"]) if x.strip()}
                if not (ecls & cls_set):
                    continue
            score = 0
            for n in names:
                if not n or len(n) < 2:
                    continue
                if bn == n:
                    score = max(score, 100 + len(n))
                elif bn.startswith(n) or n.startswith(bn):
                    score = max(score, 80 + len(n))
                elif n in bn:
                    score = max(score, 60 + len(n))
                elif bn and bn in n:
                    score = max(score, 50 + len(bn))
            if score > best_score:
                best, best_score = e, score
        if best and best_score >= 50:
            out[sid] = {"ce_id": best["ce"]["id"], "ce_name": best["ce"]["name"],
                        "effect": best["ce"]["effect"]}
    return out


# ---------------- main ----------------
def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    servants = cur.execute("select id, name_cn, wiki_page from servants order by id").fetchall()

    cur.executescript("""
    DROP TABLE IF EXISTS servant_params;
    DROP TABLE IF EXISTS servant_np;
    DROP TABLE IF EXISTS servant_skills;
    DROP TABLE IF EXISTS servant_bond_ce;
    CREATE TABLE servant_params (servant_id INTEGER, key TEXT, value TEXT,
        PRIMARY KEY (servant_id, key));
    CREATE TABLE servant_np (servant_id INTEGER, idx INTEGER, name_cn TEXT, name_sub TEXT,
        name_jp TEXT, name_jp_sub TEXT, card TEXT, np_type TEXT, rank TEXT, kind TEXT,
        strengthened INTEGER, effects TEXT, PRIMARY KEY (servant_id, idx));
    CREATE TABLE servant_skills (servant_id INTEGER, slot TEXT, name_cn TEXT, name_jp TEXT,
        cd TEXT, strengthened INTEGER, effects TEXT, extra TEXT,
        PRIMARY KEY (servant_id, slot));
    CREATE TABLE servant_bond_ce (servant_id INTEGER PRIMARY KEY, ce_id INTEGER,
        ce_name TEXT, effect TEXT);
    """)

    stats = {"pages": 0, "np": 0, "skills": 0, "params": 0}
    params_by_servant = {}
    for row in servants:
        sid = row["id"]
        p = os.path.join(PAGES, "%d.txt" % sid)
        if not os.path.exists(p):
            continue
        text = open(p, encoding="utf-8").read()
        stats["pages"] += 1

        base = parse_base(find_templates(text, "基础数值"))
        if base:
            stats["params"] += 1
            params_by_servant[sid] = base
            for k, v in base.items():
                cur.execute("INSERT OR REPLACE INTO servant_params VALUES (?,?,?)", (sid, k, v))

        np_sec = section(text, "宝具", ["技能", "资料", "素材需求", "语音"])
        for idx, r in enumerate(parse_np(find_templates(np_sec, "宝具")), 1):
            cur.execute("INSERT OR REPLACE INTO servant_np VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid, idx, r["中文名"], r["国服上标"], r["日文名"], r["日服上标"],
                         r["卡色"], r["类型"], r["阶级"], r["种类"],
                         1 if r.get("strengthened") else 0,
                         json.dumps(r["effects"], ensure_ascii=False)))
            stats["np"] += 1

        sk_sec = section(text, "技能", ["素材需求", "资料", "宝具", "语音"])
        skills = parse_held_skills(sk_sec) + parse_class_skills(sk_sec)
        for r in skills:
            slot = r["slot"]
            effects = r["effects"]
            extra = {"rank": r.get("rank", ""), "icon": r.get("icon", "")}
            extra.update(r.get("named", {}))
            cur.execute("INSERT OR REPLACE INTO servant_skills VALUES (?,?,?,?,?,?,?,?)",
                        (sid, slot, r["name_cn"], r.get("name_jp", ""), r.get("cd", ""),
                         1 if r.get("strengthened") else 0,
                         json.dumps(effects, ensure_ascii=False),
                         json.dumps(extra, ensure_ascii=False)))
            stats["skills"] += 1
    con.commit()

    bonds = map_bond_ces(con, params_by_servant)
    for sid, b in bonds.items():
        cur.execute("INSERT OR REPLACE INTO servant_bond_ce VALUES (?,?,?,?)",
                    (sid, b["ce_id"], b["ce_name"], b["effect"]))
    con.commit()
    con.close()

    stats["bond"] = len(bonds)
    print("stats:", stats)
    with open(os.path.join(HERE, "build_details_summary.txt"), "w", encoding="utf-8") as f:
        f.write(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
