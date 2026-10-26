---
name: fgo-bond
description: FGO（Mooncell 中文维基）英灵与羁绊礼装数据查询。用「英灵名」查基础数值/宝具/技能/羁绊礼装；用「A + B + C」查队伍羁绊加成礼装；用「礼装 + 礼装 + 条件」筛符合条件的英灵。当用户提到 FGO、英灵、从者、羁绊礼装、黑话（呆毛/妖崔/水提妈等）时使用。
---

# FGO 英灵 / 羁绊礼装查询

## 安装位置与路径约定

- 本 skill 目录（下称 `$SKILL`）= 包含本 SKILL.md 的目录，例如 `%USERPROFILE%\.dsh\skills\fgo-bond` 或 `<工作区>\.dsh\skills\fgo-bond`
- 数据与脚本在 `$SKILL\data\fgo`（下称 `$FGO`），随 skill 一起分发
- 所有命令都用 `$PY $FGO\query.py ...` 的形式；`$PY` 建议通过 DSH 的 `load_workspace_dependencies` 工具取得（返回的 `python` 字段），若没有就依次尝试 `python`、`py -3`

数据来自 Mooncell「英灵图鉴/数据」「礼装图鉴/数据」+ SMW 字段 + 从者详情页 + 特性页 + 黑话词条，是本地快照（离线可查）。
需要最新数据时运行 `$PY $FGO\update.py`（约 30 秒，需能访问 fgo.wiki，会重抓数据页/详情页/特性/黑话）。

## 三种提问 → 命令

### 1) 单个英灵：`英灵名`
```bash
$PY $FGO\query.py show "呆毛王"
$PY $FGO\query.py show --id 2
```
输出固定四段：基础数值 / 宝具 / 技能 / 羁绊礼装 + 提升羁绊获取礼装推荐。
名字支持正式名、别名、黑话、错别字（同音字）、214/215 这类代号；「水/泳装/夏」前缀优先泳装版，没写则优先非泳装原版。有歧义时会列候选，让用户选或改用 `--id`。

### 2) 队伍羁绊加成：`英灵 + 英灵 + 英灵`
```bash
$PY $FGO\query.py team "水提妈 + 妖催"
```
规则（用户已确认，必须照做）：
- 羁绊礼装对**全队符合条件者**生效，不是只对佩戴者生效
- 只输出 **100% 适配**（队伍每个从者都符合条件）的礼装
- 只显示最高一档：有 20% 就只列 20%；没有 20% 才列 15%/10%；再没有列当前最高档
- 只统计百分比（固定点数如英灵肖像 +50 不计入），按**最大解放**数值，每张礼装只出现一次，从高到低
- 输出格式严格照做（编号换行，并空行隔开）：
```
（全队都符合条件）：

1、来自NFF的爱（★5 COST 12）〔兽科从者〕：+20%

2、异星之神（★5 COST 12）〔恶／拥有星之力的从者〕：+20%
```

### 3) 条件筛选：`羁绊礼装 + 羁绊礼装 + 其他限制条件`
```bash
$PY $FGO\query.py filter "兽科 + 异星之神 + 弓阶"
$PY $FGO\query.py filter "来自NFF的爱 + 五星 + 女性"
```
每个 + 段可以是「羁绊加成礼装名」或限制条件，全部条件取交集，返回所有符合的英灵：
```
符合条件的英灵（3）：
1、阿塔兰忒（Archer ★4）
```
限制条件支持：职阶（Saber/剑阶/弓/枪/骑/术/杀/狂/仇/尺/降/伪/月/盾/兽）、星级（五星/★5/SSR…）、阵营（秩序/混沌/善/恶/中庸/夏，可用「秩序·善」）、性别、副属性（天/地/人/星/兽）、特性（兽科/兔子系/龙/神性/圆桌骑士/持有灵衣/活在当下的人类/七骑士/星之力等）、获取方式（期间限定/活动赠送/剧情限定/常驻/友情点召唤/通关报酬）。

## 其他命令
```bash
$PY $FGO\query.py slang 岳父        # 黑话释义 + 指代从者/礼装
$PY $FGO\query.py s --class 弓 --rarity 5
$PY $FGO\query.py ce --type 牵绊 --rarity 4
$PY $FGO\query.py stats
$PY $FGO\query.py sql "select ..."
```

## 输出语言规则（用户要求）
- 全中文回答；礼装/技能/宝具名优先中文名
- 未翻译的日文名显示为「中文译名（日文原名）」，译名对照在 `$FGO\name_zh.json`；新数据出现未翻译名时补进该文件，不要直接把日文当名字输出
- 属性/特性也用中文（「対魔力」这类日式写法显示为「对魔力」）

## 数据/实现提示
- `$FGO\fgo.db`：表 `servants` `craft_essences` `servant_params` `servant_np` `servant_skills` `servant_bond_ce` `servant_traits` `slang_term` `slang_servant` `slang_ce`
- `query.py` 的 `_match_ce` 判断礼装条件；`load_params` 会把 `servant_traits`（含「兽科从者[条件]」这类条件特性）并入匹配
- 若报 `no such table: slang_servant`：说明只跑了 `build.py` 重建库，需完整跑一遍 `$PY $FGO\update.py`
- FGO 队伍最多 6 人；超过 6 个名字时提示用户
- 拼音纠错依赖 `$FGO\vendor`（pypinyin），缺失时同音错字匹配会自动退化为普通编辑距离
