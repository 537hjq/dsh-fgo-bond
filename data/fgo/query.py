# -*- coding: utf-8 -*-
"""Query helper for the local FGO (Mooncell) servant / craft-essence dataset.

Usage examples:
  python query.py stats
  python query.py s 阿尔托莉雅
  python query.py s --class Avenger --rarity 5
  python query.py s --method 活动赠送 --rarity 4
  python query.py ce 宝石
  python query.py ce --type 牵绊 --rarity 4
  python query.py ce --effect NP获得量
  python query.py sql "select id,name_cn,class,rarity from servants where class='Avenger' order by id"
"""
import os, sqlite3, sys, argparse, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "fgo.db")

# 可选的拼音库（放在 vendor/ 下），用于同音错字匹配
sys.path.insert(0, os.path.join(HERE, "vendor"))
try:
    from pypinyin import lazy_pinyin as _lazy_pinyin
    _PY_OK = True
except Exception:  # noqa
    _PY_OK = False


def name_distance(a, b):
    """按拼音比较两个名字的距离：同音字算相同。"""
    if not a or not b:
        return 99
    if abs(len(a) - len(b)) > 1:
        return 99
    if _PY_OK:
        la, lb = _lazy_pinyin(a), _lazy_pinyin(b)
    else:
        la, lb = list(a), list(b)
    prev = list(range(len(lb) + 1))
    for i in range(1, len(la) + 1):
        cur = [i]
        for j in range(1, len(lb) + 1):
            cost = 0 if la[i - 1] == lb[j - 1] else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]

# Chinese / short class names -> canonical English class
CLASS_ALIASES = {
    "剑": "Saber", "剑阶": "Saber", "saber": "Saber",
    "弓": "Archer", "弓阶": "Archer", "archer": "Archer",
    "枪": "Lancer", "枪阶": "Lancer", "lancer": "Lancer",
    "骑": "Rider", "骑阶": "Rider", "rider": "Rider",
    "术": "Caster", "术阶": "Caster", "caster": "Caster",
    "杀": "Assassin", "杀阶": "Assassin", "assassin": "Assassin",
    "狂": "Berserker", "狂阶": "Berserker", "berserker": "Berserker",
    "仇": "Avenger", "复仇": "Avenger", "avenger": "Avenger",
    "丑": "Alterego", "他人格": "Alterego", "ae": "Alterego",
    "尺": "Ruler", "裁定": "Ruler", "ruler": "Ruler",
    "降": "Foreigner", "降临": "Foreigner", "foreigner": "Foreigner",
    "伪": "Pretender", "pretender": "Pretender",
    "月": "MoonCancer", "mooncancer": "MoonCancer", "mc": "MoonCancer",
    "盾": "Shielder", "shielder": "Shielder",
    "兽": "Beast", "beast": "Beast",
}


KANA_RE = re.compile(r"[\u3040-\u309f\u30a1-\u30fa]")

# 未翻译的日文名 → 中文译名（显示为 “中文译名（日文原名）”）
try:
    with open(os.path.join(HERE, "name_zh.json"), encoding="utf-8") as _f:
        NAME_ZH = json.load(_f)
except Exception:
    NAME_ZH = {}


def jp_name(s):
    """日文名：显示为 中文译名（日文原名）；只有汉字写法差异的按中文写法显示。"""
    if not s:
        return s
    zh = NAME_ZH.get(s.strip())
    if zh:
        return ("%s（%s）" % (zh, s.strip())) if KANA_RE.search(s) else zh
    if KANA_RE.search(s):
        return "（中文名待补）"
    return s

SEVEN = {"Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker"}
CLASSES = SEVEN | {"Avenger", "Alterego", "Ruler", "Foreigner", "Pretender",
                   "MoonCancer", "Shielder", "Beast", "UnBeast"}
ALIGN_WORDS = {"秩序", "混沌", "中立", "善", "恶", "中庸", "夏", "狂", "新娘", "神性"}
SUBATTR = {"天", "地", "人", "星", "兽", " Beast"}


def _num(s):
    m = re.search(r"增加\s*([0-9.]+)\s*%", s or "")
    if m:
        return float(m.group(1))
    m = re.search(r"增加\s*([0-9.]+)\s*(?:点)?\b", s or "")
    return float(m.group(1)) if m else 0.0


def _ce_condition(effect):
    """Classify a bond CE: ('specific' with condition list) / 'generic' / 'flat' / 'none'."""
    if not effect:
        return [], "none"
    if "牵绊点数增加" in effect:          # flat bonus (+50 etc.), any servant can use it
        return [], "flat"
    m = re.search(r"关卡通关时(.+?)获得的牵绊(?:值|点数)增加", effect)
    if not m:
        return [], ("generic" if "获得的牵绊值增加" in effect else "none")
    cond = m.group(1)
    cond = cond.replace("特性", "").replace("职阶", "").strip()
    alts = [a.strip() for a in re.split(r"或", cond) if a.strip()]
    out = []
    for a in alts:
        atoms = [x.strip("〔〕[]()（） ") for x in re.split(r"且", a)]
        atoms = [x for x in atoms if x]
        if atoms:
            out.append(atoms)
    return out, "specific"


def load_params(c, sid):
    """从者基础数值 + 特性集合；保留详情页显式特性供严格条件匹配。"""
    p = {r["key"]: r["value"] for r in c.execute(
        "select key,value from servant_params where servant_id=?", (sid,))}
    explicit = {r["value"].strip() for r in c.execute(
        "select key,value from servant_params where servant_id=? "
        "and key like '特性%' and key not like '%备注' and value is not null",
        (sid,)) if r["value"].strip()}
    p["_explicit_traits"] = explicit
    try:
        p["_traits"] = {r["trait"] for r in c.execute(
            "select trait from servant_traits where servant_id=?", (sid,))}
    except Exception:  # noqa
        p["_traits"] = set()
    return p


def _has_trait(p, kw):
    if kw in p.get("_traits", set()):
        return True
    blob = " ".join(p.get(k, "") for k in p if k.startswith("特性"))
    return kw in blob or kw in " ".join([p.get(k, "") for k in p if k.startswith("属性")])


def _match_atom(atom, p):
    a = atom.replace("的从者", "").replace("从者", "").replace("特性", "").strip()
    cls = p.get("职阶", "")
    if a in CLASSES:
        return cls == a
    if a in ("七骑士", "七騎"):
        return cls in SEVEN
    if a in ALIGN_WORDS:
        return a in (p.get("属性1", "") + p.get("属性2", "") + p.get("职阶", "")) or \
            a in (p.get("属性1", "") + p.get("属性2", ""))
    if a in ("天", "地", "人", "星", "兽"):
        return p.get("副属性", "") == a
    if a in ("女性", "男性", "性别不明", "不明"):
        return a == p.get("性别", "")
    if a == "拥有星之力" or a == "星之力":
        tr = p.get("_traits", set())
        return p.get("副属性", "") == "星" or "拥有星之力的从者" in tr
    if a in ("兽科", "獸科"):
        tr = p.get("_explicit_traits", set())
        return ("兽科" in tr or p.get("副属性", "") == "兽")
    if a == "持有灵衣之人" or a == "持有灵衣":
        tr = p.get("_traits", set())
        return ("持有灵衣之人" in tr or
                any("灵衣" in v for k, v in p.items() if k.startswith("立绘") or k.startswith("文件")))
    if a in ("活在当下的人类",):
        return _has_trait(p, a)
    if "Fate/stay night" in atom or "FSN" in atom:
        return _has_trait(p, "FSN从者") or _has_trait(p, "Fate/stay night从者")
    # fallback: substring in traits/attributes/nickname
    if a in p.get("_traits", set()):
        return True
    blob = " ".join(p.get(k, "") for k in p if not k.startswith("_")) + p.get("昵称", "")
    return a in blob


def _match_ce(ce, p):
    alts, kind = _ce_condition(ce["effect"])
    if kind == "flat":
        return True, "任意从者"
    if kind == "generic":
        return True, "通用"
    if kind == "none":
        return False, ""
    for atoms in alts:
        if all(_match_atom(a, p) for a in atoms):
            return True, "且".join(atoms)
    return False, ""


def bond_recommendations(c, sid, p):
    """Return (own_bond_ce, picks) — percentage bond CEs first (desc), flat +points last."""
    own = c.execute("""select b.ce_id, b.ce_name, b.effect, e.rarity, e.cost, e.effect_max
                       from servant_bond_ce b left join craft_essences e on e.id=b.ce_id
                       where b.servant_id=?""", (sid,)).fetchone()
    rows = c.execute("""select id,name,rarity,cost,type,effect,effect_max
                        from craft_essences where effect like '%牵绊%' and type!='牵绊'""").fetchall()
    pct, flat = [], []
    for ce in rows:
        ok, cond = _match_ce(ce, p)
        if not ok:
            continue
        base = _num(ce["effect"])
        mx = _num(ce["effect_max"]) or base
        item = (ce, cond, base, mx)
        if "牵绊点数增加" in (ce["effect"] or ""):
            flat.append(item)
        else:
            pct.append(item)

    def dedupe(items):
        seen, out = set(), []
        for ce, cond, base, mx in items:
            key = (ce["effect"] or "", base, mx)
            if key in seen:
                continue
            seen.add(key)
            out.append((ce, cond, base, mx))
        return out

    # 百分比类：按最大解放 / 基础加成从高到低
    pct = dedupe(pct)
    pct.sort(key=lambda x: (-x[3], -x[2], x[0]["cost"] or 0))
    # 固定点数类：同样从高到低，但整体排在最后（同类同效果只留一张）
    flat = dedupe(flat)
    flat.sort(key=lambda x: (-x[3], -x[2]))
    flat = flat[:1]
    return own, pct + flat


def canon_class(v):
    if not v:
        return v
    s = str(v).strip()
    return CLASS_ALIASES.get(s, CLASS_ALIASES.get(s.lower(), s))


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def like(v):
    return "%" + str(v) + "%"


def print_rows(rows, cols):
    if not rows:
        print("(no result)")
        return
    print(" | ".join(cols))
    print("-+-".join("-" * len(c) for c in cols))
    for r in rows:
        print(" | ".join("" if r[c] is None else str(r[c]) for c in cols))


def cmd_stats(_):
    c = con()
    print("servants:", c.execute("select count(*) from servants").fetchone()[0])
    print("craft_essences:", c.execute("select count(*) from craft_essences").fetchone()[0])
    for tbl in ("servant_params", "servant_np", "servant_skills", "servant_bond_ce"):
        try:
            n = c.execute("select count(*) from %s" % tbl).fetchone()[0]
            print("%s: %d" % (tbl, n))
        except sqlite3.OperationalError:
            print("%s: (not built yet — run build_details.py)" % tbl)
    print("\nservants by rarity:")
    for r in c.execute("select rarity,count(*) n from servants group by rarity order by rarity"):
        print("  %s星: %d" % (r["rarity"], r["n"]))
    print("\nservants by class:")
    for r in c.execute("select class,count(*) n from servants group by class order by n desc"):
        print("  %s: %d" % (r["class"], r["n"]))
    print("\ncraft essences by type:")
    for r in c.execute("select type,count(*) n from craft_essences group by type order by n desc"):
        print("  %s: %d" % (r["type"], r["n"]))
    print("\ncraft essences by rarity:")
    for r in c.execute("select rarity,count(*) n from craft_essences group by rarity order by rarity"):
        print("  %s星: %d" % (r["rarity"], r["n"]))


def cmd_servant(a):
    c = con()
    where, args = [], []
    if a.name:
        where.append("(name_cn like ? or name_jp like ? or name_en like ? or alias like ? or name_link like ?)")
        args += [like(a.name)] * 5
    for field, val in (("class", a.klass), ("rarity", a.rarity), ("obtain_method", a.method),
                       ("alignment1", a.alignment1), ("alignment2", a.alignment2),
                       ("sub_attribute", a.sub_attribute), ("tag", a.tag),
                       ("illustrator", a.illustrator), ("voice", a.voice)):
        if val:
            if field == "rarity":
                where.append("rarity = ?")
                args.append(val)
            elif field == "class":
                where.append("class like ?")
                args.append(like(canon_class(val)))
            else:
                where.append("%s like ?" % field)
                args.append(like(val))
    sql = "select id,name_cn,name_jp,rarity,class,obtain_method,atk_max,hp_max,cost,alias from servants"
    if where:
        sql += " where " + " and ".join(where)
    sql += " order by id"
    rows = c.execute(sql, args).fetchall()
    cols = ["id", "name_cn", "name_jp", "rarity", "class", "obtain_method", "atk_max", "hp_max", "cost", "alias"]
    print_rows(rows, cols)
    print("\ncount:", len(rows))


def cmd_ce(a):
    c = con()
    where, args = [], []
    if a.name:
        where.append("(name like ? or name_jp like ? or alias like ? or name_link like ?)")
        args += [like(a.name)] * 4
    if a.effect:
        where.append("(effect like ? or skill_smw like ?)")
        args += [like(a.effect)] * 2
    for field, val in (("type", a.type), ("rarity", a.rarity), ("illustrator", a.illustrator),
                       ("tag", a.tag), ("event", a.event)):
        if val:
            if field in ("rarity", "event"):
                where.append("%s = ?" % field)
                args.append(val)
            else:
                where.append("%s like ?" % field)
                args.append(like(val))
    sql = "select id,name,name_jp,rarity,cost,type,atk_max,hp_max,illustrator,effect from craft_essences"
    if where:
        sql += " where " + " and ".join(where)
    sql += " order by id"
    rows = c.execute(sql, args).fetchall()
    cols = ["id", "name", "name_jp", "rarity", "cost", "type", "atk_max", "hp_max", "illustrator", "effect"]
    print_rows(rows, cols)
    print("\ncount:", len(rows))


def cmd_sql(a):
    c = con()
    rows = c.execute(a.query).fetchall()
    if not rows:
        print("(no result)")
        return
    cols = list(rows[0].keys())
    print_rows(rows, cols)


def _fmt_effect(eff, indent="  - ", mode="skill"):
    lines = []
    for e in eff:
        desc = e.get("desc", "")
        vals = e.get("values", [])
        if not desc:
            continue
        if not vals:
            lines.append("%s%s" % (indent, desc))
        elif len(vals) == 1:
            lines.append("%s%s：%s" % (indent, desc, vals[0]))
        else:
            label = "%d档" % len(vals)
            if mode == "np":
                if "宝具升级" in desc:
                    label = "宝具Lv"
                elif "Over Charge" in desc or "OverCharge" in desc or "充能" in desc:
                    label = "OC"
            elif len(vals) == 10:
                label = "Lv1→10"
            lines.append("%s%s：%s → %s（%s）" % (indent, desc, vals[0], vals[-1], label))
    return lines


def _report(c, row):
    import json
    sid = row["id"]
    p = load_params(c, sid)
    lines = []
    star = "★" * int(p.get("稀有度") or row["rarity"] or 0)
    lines.append("【基础数值】%s（%s / %s）" % (row["name_cn"], row["class"], star))
    lines.append("阵营：%s·%s ｜ 副属性：%s ｜ 性别：%s ｜ 身高：%s ｜ 体重：%s" % (
        p.get("属性1", ""), p.get("属性2", ""), p.get("副属性", ""), p.get("性别", ""),
        p.get("身高", "—"), p.get("体重", "—")))
    lines.append("ATK：%s → %s ｜ HP：%s → %s ｜ COST：%s" % (
        p.get("基础ATK") or row["atk_base"], p.get("满级ATK") or row["atk_max"],
        p.get("基础HP") or row["hp_base"], p.get("满级HP") or row["hp_max"],
        p.get("COST") or row["cost"]))
    cards = [p.get(k, "") for k in ("第一张卡", "第二张卡", "第三张卡", "第四张卡", "第五张卡")]
    if any(cards):
        lines.append("配卡：%s ｜ hit：Q%s A%s B%s EX%s 宝具%s" % (
            " ".join(cards), p.get("Q卡hit数", "?"), p.get("A卡hit数", "?"),
            p.get("B卡hit数", "?"), p.get("EX卡hit数", "?"), p.get("宝具卡hit数", "?")))
    stats = [(k, p.get(k)) for k in ("筋力", "耐久", "敏捷", "魔力", "幸运", "宝具") if p.get(k)]
    if stats:
        lines.append("｜ ".join("%s %s" % (k, v) for k, v in stats))
    extra = []
    for k in ("出星率", "即死率", "暴击权重"):
        if p.get(k):
            extra.append("%s %s" % (k, p[k]))
    if extra:
        lines.append("｜ ".join(extra))
    lines.append("获取方式：%s ｜ 声优：%s ｜ 画师：%s" % (
        row["obtain_method"] or p.get("获取途径", ""), p.get("声优", ""), p.get("画师", "")))
    traits = [p.get(k, "") for k in p if k.startswith("特性") and p.get(k)]
    if traits:
        lines.append("特性：%s" % "、".join(traits))

    # NP
    lines.append("")
    lines.append("【宝具】")
    nps = c.execute("select * from servant_np where servant_id=? order by idx", (sid,)).fetchall()
    if not nps:
        lines.append("  （未解析到宝具数据）")
    for np in nps:
        npname = jp_name(np["name_cn"])
        head = "  %s" % npname
        meta = "  %s·%s ｜ 阶级 %s ｜ %s" % (np["card"], np["np_type"], np["rank"], np["kind"])
        if np["strengthened"]:
            meta += "（已强化）"
        lines.append(head)
        lines.append(meta)
        lines.extend(_fmt_effect(json.loads(np["effects"]), indent="    · ", mode="np"))

    # skills
    lines.append("")
    lines.append("【技能】")
    sks = c.execute("select * from servant_skills where servant_id=? order by rowid", (sid,)).fetchall()
    for sk in sks:
        if sk["slot"].startswith("职阶技能"):
            continue
        ex = json.loads(sk["extra"] or "{}")
        tag = "，已强化" if sk["strengthened"] else ""
        skname = jp_name(sk["name_cn"])
        lines.append("  %s：%s%s（CD %s%s）" % (sk["slot"], skname,
                                              (" " + ex.get("rank", "")) if ex.get("rank") else "",
                                              sk["cd"], tag))
        lines.extend(_fmt_effect(json.loads(sk["effects"])))
    cs = [sk for sk in sks if sk["slot"].startswith("职阶技能")]
    if cs:
        lines.append("  职阶技能：")
        for sk in cs:
            ex = json.loads(sk["extra"] or "{}")
            eff = json.loads(sk["effects"])
            desc = eff[0]["desc"] if eff else ""
            rank = ex.get("rank", "")
            csname = jp_name(sk["name_cn"])
            lines.append("    · %s%s：%s" % (csname, (" " + rank) if rank else "", desc))

    # bond CE + recommendations
    own, picks = bond_recommendations(c, sid, p)
    lines.append("")
    lines.append("【羁绊礼装】")
    if own and own["ce_name"]:
        rar = "★%s" % own["rarity"] if own["rarity"] else ""
        cost = "COST %s" % own["cost"] if own["cost"] else ""
        ce_name = own["ce_name"]
        ce_name = jp_name(ce_name)
        lines.append("  %s（%s %s）" % (ce_name, rar, cost))
        eff = own["effect"] or ""
        if KANA_RE.search(eff):
            eff = "（该礼装效果暂无中文说明）"
        lines.append("  效果：%s" % eff)
        lines.append("  获取：该从者牵绊等级达到 Lv.10 时获得")
    else:
        lines.append("  （该从者暂无羁绊礼装数据）")

    lines.append("")
    lines.append("【提升牵绊获取的礼装·推荐（按最大解放）】")
    pct = [x for x in picks if "牵绊点数增加" not in (x[0]["effect"] or "")]
    flat = [x for x in picks if "牵绊点数增加" in (x[0]["effect"] or "")]
    shown = 0
    for ce, cond, base, mx in pct[:6]:
        shown += 1
        gain = "+%g%%" % mx
        condtxt = "" if cond in ("通用", "") else "〔%s〕" % cond
        name = ce["name"] or ""
        name = jp_name(name)
        lines.append("  %d. %s（★%s COST %s）%s：%s" % (
            shown, name, ce["rarity"], ce["cost"], condtxt, gain))
    for ce, cond, base, mx in flat[:1]:
        shown += 1
        name = ce["name"]
        if (name or "").startswith("英灵肖像"):
            name = "英灵肖像（任意一张）"
        elif KANA_RE.search(name or ""):
            name = jp_name(name)
        lines.append("  %d. %s（★%s COST %s）〔任意从者〕：+%g 点（固定）" % (
            shown, name, ce["rarity"], ce["cost"], base))
    if shown == 0:
        lines.append("  （没有找到适用的牵绊加成礼装）")
    return "\n".join(lines)


def slang_servants(c, term, fuzzy=False):
    if fuzzy:
        sql = """select s.id, s.name_cn, s.class, s.rarity, s.obtain_method,
                        min(ss.ord) o, group_concat(distinct ss.category) cats
                 from slang_servant ss join servants s on s.id=ss.servant_id
                 where ss.term like ? group by s.id order by o"""
        return c.execute(sql, ("%" + term + "%",)).fetchall()
    sql = """select s.id, s.name_cn, s.class, s.rarity, s.obtain_method,
                    min(ss.ord) o, group_concat(distinct ss.category) cats
             from slang_servant ss join servants s on s.id=ss.servant_id
             where ss.term=? group by s.id order by o"""
    return c.execute(sql, (term,)).fetchall()


def slang_ces(c, term):
    return c.execute("""select e.id, e.name, e.rarity, e.cost, min(sc.ord) o
                        from slang_ce sc join craft_essences e on e.id=sc.ce_id
                        where sc.term=? group by e.id order by o""", (term,)).fetchall()


def cmd_slang(a):
    c = con()
    term = a.term
    info = c.execute("select term,category,excerpt from slang_term where term=?", (term,)).fetchone()
    servers = slang_servants(c, term)
    ces = slang_ces(c, term)
    if not info and not servers and not ces:
        servers = slang_servants(c, term, fuzzy=True)
        info = None
        if not servers:
            print("没有找到黑话「%s」。可试试：python query.py slang 岳父" % term)
            return
        print("未找到完全匹配，以下是包含「%s」的词条：" % term)
        for r in servers[:15]:
            print("  %s  →  %s（%s %s）" % (r["name_cn"], "★" * int(r["rarity"] or 0), r["class"], r["cats"]))
        return
    if info:
        print("【%s】（%s）" % (info["term"], info["category"]))
        if info["excerpt"]:
            print(info["excerpt"])
        print()
    if servers:
        print("指代从者：")
        for r in servers:
            print("  %s  %s  %s %s" % (r["id"], r["name_cn"], "★" * int(r["rarity"] or 0),
                                       r["class"]))
    if ces:
        print("指代礼装：")
        for r in ces:
            print("  %s  %s  ★%s COST%s" % (r["id"], r["name"], r["rarity"], r["cost"]))
    if len(servers) == 1:
        print("\n（可直接问这个名字，如：%s）" % servers[0]["name_cn"])


def find_servants(c, name):
    """Resolve a user-supplied name (formal name / alias / slang / id-ish) to servant rows.

    支持「水/泳装/夏」前缀：先按去掉前缀的名字查，再限定泳装版本。
    """
    swim = False
    core = name
    if name.startswith("泳装") and len(name) > 2:
        core, swim = name[2:], True
    elif name and name[0] in "水夏" and len(name) > 1:
        core, swim = name[1:], True

    def keep(rows):
        if swim:
            return [r for r in rows if ("泳装" in (r["tag"] or "") or "水着" in (r["tag"] or ""))]
        # 没写「水/泳装」时，同名词条优先非泳装的原版
        if len(rows) > 1:
            plain = [r for r in rows if not ("泳装" in (r["tag"] or "") or "水着" in (r["tag"] or ""))]
            if plain:
                return plain
        return rows

    # 1) 精确同名
    rows = keep(c.execute("select * from servants where name_cn=? or name_link=? order by id",
                          (core, core)).fetchall())
    if rows:
        exact_link = [r for r in rows if r["name_link"] == core]
        return exact_link or rows
    # 1.5) 别名完全相等
    rows = keep([r for r in c.execute("select * from servants order by id")
                 if core in [t.strip() for t in re.split(r"[&,，、]", r["alias"] or "")]])
    if rows:
        return rows
    # 2) 子串匹配
    rows = keep(c.execute("""select * from servants where name_cn like ? or name_jp like ?
                             or name_en like ? or alias like ? or name_link like ?
                             order by id""", (like(core),) * 5).fetchall())
    if not rows:
        ids = [r["servant_id"] for r in c.execute(
            "select servant_id from servant_params where key in ('中文名','中文战斗名','中文卡面名') and value like ?",
            (like(core),))]
        if ids:
            q = ",".join("?" * len(set(ids)))
            rows = keep(c.execute("select * from servants where id in (%s) order by id" % q,
                                  tuple(set(ids))).fetchall())
    # 3) 别名片段包含
    if not rows:
        for r in c.execute("select * from servants order by id"):
            toks = [t.strip() for t in re.split(r"[&,，、]", r["alias"] or "") if t.strip()]
            if any(len(t) >= 2 and (t in core or core in t) for t in toks):
                rows.append(r)
        rows = keep(rows)
    # 4) 近似拼写/同音字（如 伊仕塔尔 → 伊什塔尔、水妖催 → 水妖崔）
    if not rows:
        scored = []
        for r in c.execute("select * from servants order by id"):
            toks = [r["name_cn"], r["name_link"]] + \
                   [t.strip() for t in re.split(r"[&,，、]", r["alias"] or "") if t.strip()]
            ds = [name_distance(x, core) for x in toks if x and len(x) >= 2]
            if ds and min(ds) <= 1:
                scored.append((min(ds), r))
        if scored:
            best = min(s[0] for s in scored)
            rows = keep([r for d, r in scored if d == best])
            prefer = [r for r in rows if name_distance(r["name_link"] or "", core) == best]
            if prefer and len(prefer) < len(rows):
                rows = prefer
    # 5) 黑话
    if not rows:
        sl = slang_servants(c, core)
        if not sl:
            sl = slang_servants(c, core, fuzzy=True)
        if sl:
            ids = list(dict.fromkeys(r["id"] for r in sl))
            q = ",".join("?" * len(ids))
            rows = keep(c.execute("select * from servants where id in (%s) order by id" % q,
                                  tuple(ids)).fetchall())
    if len(rows) > 1:
        exact_link = [r for r in rows if r["name_link"] == core]
        if exact_link:
            rows = exact_link
    return rows


def cmd_show(a):
    c = con()
    if a.id:
        row = c.execute("select * from servants where id=?", (a.id,)).fetchone()
        if not row:
            print("未找到 id=%s 的从者" % a.id)
            return
        print(_report(c, row))
        return
    if not a.name:
        print("用法: query.py show <从者名>  或  query.py show --id 2")
        return
    rows = find_servants(c, a.name)
    if not rows:
        print("未找到「%s」，可试试其它写法或别名。" % a.name)
        return
    if len(rows) > 1:
        print("匹配到 %d 个从者：" % len(rows))
        for r in rows:
            print("  %s  %s  %s %s  %s" % (r["id"], r["name_cn"], "★" * int(r["rarity"] or 0),
                                           r["class"], r["obtain_method"]))
        print("\n请用更精确的名称，或 query.py show --id <id>")
        return
    print(_report(c, rows[0]))


def cmd_team(a):
    """英灵 + 英灵 + 英灵 → 全队百分比羁绊礼装最优分配（每张礼装只用一次）。"""
    import itertools
    c = con()
    raw = " ".join(a.names)
    parts = [p.strip() for p in re.split(r"[+＋]", raw) if p.strip()]
    if len(parts) < 2:
        print("格式：query.py team \"英灵A + 英灵B + 英灵C\"（至少 2 个）")
        return
    resolved = []
    for name in parts:
        rows = find_servants(c, name)
        if not rows:
            print("找不到「%s」，可试试其它写法或别名。" % name)
            return
        if len(rows) > 1:
            print("「%s」匹配到多个从者，请写更精确：" % name)
            for r in rows[:8]:
                print("  %s  %s  %s %s" % (r["id"], r["name_cn"], "★" * int(r["rarity"] or 0), r["class"]))
            return
        resolved.append(rows[0])

    # 礼装效果对全队符合条件者生效：逐张计算“适用人数 × 加成”，取收益最高的 N 张（N=队伍人数）
    p_list = [load_params(c, row["id"]) for row in resolved]
    ce_rows = c.execute("""select id,name,rarity,cost,type,effect,effect_max
                           from craft_essences where effect like '%牵绊%' and type!='牵绊'""").fetchall()
    cands = []
    for ce in ce_rows:
        if "牵绊点数增加" in (ce["effect"] or ""):
            continue  # 只推荐百分比加成
        mx = _num(ce["effect_max"]) or _num(ce["effect"])
        if not mx:
            continue
        matches, conds = [], []
        for i, p in enumerate(p_list):
            ok, cond = _match_ce(ce, p)
            if ok:
                matches.append(i)
                conds.append(cond)
        if matches:
            cands.append((ce, matches, conds, mx))
    if not cands:
        print("没有找到适用于该队伍的百分比羁绊礼装。")
        return
    # 100% 适配 = 队伍里每个从者都符合条件
    full = [c for c in cands if len(c[1]) == len(resolved)]
    full.sort(key=lambda x: (-x[3], x[0]["id"]))
    partial = [c for c in cands if len(c[1]) < len(resolved)]
    partial.sort(key=lambda x: (-(x[3] * len(x[1])), -x[3], x[0]["id"]))

    def cond_of(conds):
        real = sorted(set(c for c in conds if c not in ("通用", "")))
        return ("〔%s〕" % "／".join(real)) if real else "〔通用〕"

    if full:
        # 只显示最高一档：有 20% 就只列 20%；否则列 15%/10%；再没有就列当前最高档
        top = full[0][3]
        if top >= 20:
            full = [c for c in full if c[3] >= 20]
        elif any(c[3] in (10.0, 15.0) for c in full):
            full = [c for c in full if c[3] in (10.0, 15.0)]
        else:
            full = [c for c in full if c[3] == top]
        print("（全队都符合条件）：")
        print()
        for i, (ce, matches, conds, mx) in enumerate(full, 1):
            print("%d、%s（★%s COST %s）%s：+%g%%" % (
                i, jp_name(ce["name"]), ce["rarity"], ce["cost"], cond_of(conds), mx))
            print()
    else:
        print("没有 100% 适配的百分比羁绊礼装。")


RARITY_WORDS = {"一星": 1, "二星": 2, "三星": 3, "四星": 4, "五星": 5,
                "1星": 1, "2星": 2, "3星": 3, "4星": 4, "5星": 5,
                "SSR": 5, "SR": 4, "R": 3}
GENDERS = {"女性", "男性", "性别不明", "不明"}
GENDER_ALIASES = {"女": "女性", "男": "男性"}
ALIGN_PARTS = {"秩序", "混沌", "中立", "善", "恶", "中庸", "夏", "狂", "新娘", "神性"}


def find_bond_ce(c, name):
    """按名字找羁绊加成礼装（只在本土羁绊加成礼装范围内）"""
    rows = c.execute("""select * from craft_essences
                        where effect like '%牵绊%' and type!='牵绊'""").fetchall()
    exact = [r for r in rows if (r["name"] or "") == name]
    if exact:
        return exact
    part = [r for r in rows if name and (name in (r["name"] or "") or (r["name"] or "") in name)]
    return part


def _trait_pred(t):
    def f(row, p):
        traits = p.get("_traits", set())
        # 基础特性中的“兽科”或“兽科从者[条件]”可命中；条件特性仅在持有灵衣时生效。
        if t == "兽科":
            explicit = p.get("_explicit_traits", set())
            if any("兽科" in value for value in explicit):
                return True
            has_costume = ("持有灵衣之人" in traits or "持有灵衣" in traits or
                           any("灵衣" in v for k, v in p.items()
                               if k.startswith("立绘") or k.startswith("文件")))
            return has_costume and "兽科从者" in traits
        if t in traits or (t + "从者") in traits:
            return True
        if t in ("持有灵衣", "持有灵衣之人", "灵衣"):
            return ("持有灵衣之人" in traits or
                    any("灵衣" in v for k, v in p.items() if k.startswith("立绘") or k.startswith("文件")))
        if t in ("拥有星之力", "星之力"):
            return p.get("副属性") == "星" or "拥有星之力的从者" in traits
        if t == "七骑士":
            return row["class"] in SEVEN
        blob = " ".join(p.get(k, "") for k in p if k.startswith("特性"))
        return t in blob
    return f


def _parse_alignment_parts(t):
    """Parse alignment combinations with separators or compact Chinese text."""
    parts = [x.strip() for x in re.split(r"[·・、/，,&＆]|且", t) if x.strip()]
    if len(parts) > 1 and all(x in ALIGN_PARTS for x in parts):
        return parts
    if len(parts) == 1 and parts[0] == t:
        # Accept common compact forms such as “秩序善” and “混沌恶”.
        candidates = sorted(ALIGN_PARTS, key=len, reverse=True)
        compact = []
        rest = t
        while rest:
            match = next((x for x in candidates if rest.startswith(x)), None)
            if match is None:
                return []
            compact.append(match)
            rest = rest[len(match):]
        if len(compact) > 1:
            return compact
    return []


def _parse_alignment_gender_parts(t):
    """Parse conjunctions such as “秩序&女” or “秩序·女性”."""
    parts = [x.strip() for x in re.split(r"[·・、/，,&＆]|且", t) if x.strip()]
    if len(parts) <= 1 or not all(x in ALIGN_PARTS or x in GENDERS or x in GENDER_ALIASES
                                   for x in parts):
        return []
    return [(GENDER_ALIASES.get(x, x)) for x in parts]


def constraint_pred(tok):
    """把“其他限制条件”翻译成 (row, p) -> bool。无法识别返回 None。"""
    t = tok.strip()
    if not t:
        return None
    t = GENDER_ALIASES.get(t, t)
    if t in RARITY_WORDS:
        v = RARITY_WORDS[t]
        return lambda row, p: int(row["rarity"] or 0) == v
    m = re.fullmatch(r"★?([1-5])星?", t)
    if m:
        v = int(m.group(1))
        return lambda row, p: int(row["rarity"] or 0) == v
    if t in GENDERS:
        return lambda row, p: p.get("性别") == ("性别不明" if t == "不明" else t)
    if t in ("天", "地", "人", "星", "兽"):
        return lambda row, p: p.get("副属性") == t
    # 斜杠表示条件或，例如“恶/星”；星在此表示副属性。
    if "/" in t or "／" in t:
        or_parts = [x.strip() for x in re.split(r"[/／]", t) if x.strip()]
        if len(or_parts) > 1:
            def matches_or(row, p):
                for part in or_parts:
                    if part in ("天", "地", "人", "星", "兽"):
                        if p.get("副属性") == part:
                            return True
                    elif part in ALIGN_PARTS:
                        if part in (p.get("属性1", "") + p.get("属性2", "")):
                            return True
                    else:
                        pred = _trait_pred(part)
                        if pred(row, p):
                            return True
                return False
            return matches_or
    # 阵营与性别组合，如“秩序&女”或“秩序·女性”。
    alignment_gender_parts = _parse_alignment_gender_parts(t)
    if len(alignment_gender_parts) > 1:
        def matches_alignment_gender(row, p):
            alignment = p.get("属性1", "") + p.get("属性2", "")
            return all((part in alignment) if part in ALIGN_PARTS else
                       p.get("性别") == part for part in alignment_gender_parts)
        return matches_alignment_gender
    # 阵营组合，如 秩序·善 / 混沌且恶 / 秩序善；这些分隔符表示“且”。
    alignment_parts = _parse_alignment_parts(t)
    if len(alignment_parts) > 1:
        return lambda row, p: all(x in (p.get("属性1", "") + p.get("属性2", ""))
                               for x in alignment_parts)
    if t in ALIGN_PARTS:
        return lambda row, p: t in (p.get("属性1", "") + p.get("属性2", ""))
    cls = canon_class(t)
    if cls in CLASSES:
        return lambda row, p: row["class"] == cls
    for kw in ("期间限定", "活动赠送", "剧情限定", "常驻", "友情点召唤", "通关报酬", "初始获得"):
        if t == kw or t == kw + "从者":
            return lambda row, p, kw=kw: kw in (row["obtain_method"] or "")
    return _trait_pred(t)


def cmd_filter(a):
    """羁绊礼装 + 羁绊礼装 + 其他限制条件 → 所有符合条件的英灵"""
    c = con()
    raw = " ".join(a.terms)
    parts = [x.strip() for x in re.split(r"[+＋]", raw) if x.strip()]
    if not parts:
        print("格式：query.py filter \"礼装A + 礼装B + 五星 + 女性\"")
        return
    ce_preds, labels = [], []
    cons = []
    for tok in parts:
        ces = find_bond_ce(c, tok)
        if len(ces) == 1:
            ce = ces[0]
            ce_preds.append(lambda row, p, ce=ce: _match_ce(ce, p)[0])
            labels.append("礼装「%s」" % jp_name(ce["name"]))
            continue
        if len(ces) > 1:
            print("「%s」匹配到多张羁绊礼装，请写更精确：" % tok)
            for r in ces[:10]:
                print("  %s（★%s）" % (jp_name(r["name"]), r["rarity"]))
            return
        pred = constraint_pred(tok)
        if pred is None:
            print("无法识别条件「%s」。" % tok)
            return
        cons.append(pred)
        labels.append(tok)

    rows = c.execute("select * from servants order by id").fetchall()
    matched = []
    for row in rows:
        p = load_params(c, row["id"])
        if all(f(row, p) for f in ce_preds) and all(f(row, p) for f in cons):
            matched.append(row)
    if not matched:
        print("没有符合条件的英灵。")
        return
    print("符合条件的英灵（%d）：" % len(matched))
    for i, row in enumerate(matched, 1):
        print("%d、%s（%s ★%s）" % (i, jp_name(row["name_cn"]), row["class"], row["rarity"]))


def main():
    p = argparse.ArgumentParser(description="FGO local dataset query")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats").set_defaults(func=cmd_stats)

    s = sub.add_parser("s", help="search servants")
    s.add_argument("name", nargs="?")
    s.add_argument("--class", dest="klass")
    s.add_argument("--rarity", type=int)
    s.add_argument("--method")
    s.add_argument("--alignment1")
    s.add_argument("--alignment2")
    s.add_argument("--sub-attribute", dest="sub_attribute")
    s.add_argument("--tag")
    s.add_argument("--illustrator")
    s.add_argument("--voice")
    s.set_defaults(func=cmd_servant)

    e = sub.add_parser("ce", help="search craft essences")
    e.add_argument("name", nargs="?")
    e.add_argument("--effect")
    e.add_argument("--type")
    e.add_argument("--rarity", type=int)
    e.add_argument("--illustrator")
    e.add_argument("--tag")
    e.add_argument("--event")
    e.set_defaults(func=cmd_ce)

    q = sub.add_parser("sql", help="run raw SQL")
    q.add_argument("query")
    q.set_defaults(func=cmd_sql)

    sh = sub.add_parser("show", help="show full report for one servant")
    sh.add_argument("name", nargs="?")
    sh.add_argument("--id", type=int)
    sh.set_defaults(func=cmd_show)

    sl = sub.add_parser("slang", help="look up 黑话(slang) term")
    sl.add_argument("term")
    sl.set_defaults(func=cmd_slang)

    tm = sub.add_parser("team", help="英灵 + 英灵 + … → 全队羁绊加成礼装最优分配")
    tm.add_argument("names", nargs="+")
    tm.set_defaults(func=cmd_team)

    fl = sub.add_parser("filter", help="羁绊礼装 + 羁绊礼装 + 其他限制条件 → 符合条件的英灵")
    fl.add_argument("terms", nargs="+")
    fl.set_defaults(func=cmd_filter)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
