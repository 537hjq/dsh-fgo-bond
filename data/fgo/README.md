# FGO（Mooncell）本地数据集

数据来源：
- 英灵图鉴/数据 https://fgo.wiki/w/英灵图鉴/数据 （483 条）
- 礼装图鉴/数据 https://fgo.wiki/w/礼装图鉴/数据 （2707 条）
- 补充字段来自 Mooncell 的 SMW 查询接口 `api.php?action=ask`（职阶、稀有度、ATK/HP、COST、画师、声优、礼装效果等）

## 文件

| 文件 | 说明 |
| --- | --- |
| `fgo.db` | SQLite 数据库，表 `servants`、`craft_essences`、`servant_params`、`servant_np`、`servant_skills`、`servant_bond_ce` |
| `servants.csv` | 英灵表（UTF-8 BOM，可直接用 Excel 打开） |
| `craft_essences.csv` | 礼装表（同上） |
| `query.py` | 查询脚本（`stats` / `s` / `ce` / `show` / `sql`） |
| `update.py` | 一键刷新：数据页 → SMW → 详情页 → 重新入库 |
| `fetch_all.py` | 抓取两张数据页与 SMW 字段（`raw/` 下为抓取结果） |
| `fetch_pages.py` | 增量抓取从者详情页（`raw/pages/<id>.txt`） |
| `fetch_slang.py` | 抓取「FGO黑话·梗·成句」全部词条（`raw/slang_pages.json`） |
| `build.py` | 由 `raw/` 生成英灵/礼装表与 CSV |
| `build_details.py` | 解析详情页，生成基础数值/宝具/技能/羁绊礼装表 |
| `build_slang.py` | 解析黑话词条中的从者/礼装链接，生成黑话映射表 |
| `name_zh.json` | 未翻译日文名的中文译名字典（显示为“中文译名（日文原名）”） |
| `build_summary.txt` / `build_details_summary.txt` | 最近一次构建的统计摘要 |

## 字段

### servants（英灵）
`id` 序号；`name_cn` / `name_jp` / `name_en` 名称；`name_link` 图鉴链接名；
`alias` 常用别名（& 分隔）；`obtain_method` 获取方式（| 分隔）；`tag` 标签；
`rarity` 稀有度；`class` 职阶；`alignment1` / `alignment2` 阵营属性；`sub_attribute` 副属性；
`gender` 性别；`atk_base` / `atk_max` 基础/满级 ATK；`hp_base` / `hp_max` 基础/满级 HP；
`cost` COST；`illustrator` 画师；`voice` 声优；`wiki_page` 对应 wiki 页面名。

### craft_essences（礼装）
`id` 礼装序号；`name` 中文名（未翻译的为日文原名）；`name_jp` 日文名；`name_link` 链接名；
`alias` 别名；`effect` 持有技能（未翻译条目为日文）；`effect_max` 最大解放效果（部分条目为空）；
`skill_smw` SMW 中的持有技能字段；`tag` 标签；`type` 分类（牵绊/情人节/期间限定/卡池常驻/活动奖励/兑换/纪念/EXP卡/掉落加成/剧情限定/未知）；
`event` 是否活动相关（1/0）；`rarity` 稀有度；`cost` COST；
`atk_base` / `atk_max`；`hp_base` / `hp_max`；`illustrator` 画师；`wiki_page` 页面名。

### servant_params（从者基础数值，键值对）
`ser_id`, `key`, `value`。包含 `稀有度/职阶/属性1/属性2/副属性/性别/身高/体重/筋力~宝具/COST/基础ATK/满级ATK/基础HP/满级HP/配卡/hit数/NP率/出星率/即死率/暴击权重/特性1..N/昵称` 等。

### servant_np（宝具）
`servant_id`, `idx`, `name_cn`, `name_sub`(上标), `name_jp`, `name_jp_sub`, `card`, `np_type`, `rank`, `kind`, `strengthened`, `effects`(JSON：desc + values)。

### servant_skills（技能）
`servant_id`, `slot`(技能1/2/3、职阶技能N), `name_cn`, `name_jp`, `cd`, `strengthened`, `effects`(JSON), `extra`(JSON：rank/icon)。

### servant_bond_ce（羁绊礼装映射）
`servant_id`, `ce_id`, `ce_name`, `effect`。

### slang_term / slang_servant / slang_ce（黑话）
`slang_term`：`term`, `category`, `excerpt`（词条释义摘要）。
`slang_servant`：`term`, `category`, `servant_id`, `ord`（词条内链接出现顺序，越小越主要）。
`slang_ce`：`term`, `category`, `ce_id`, `ord`。

## 用法

```bash
PY=python   # 或本机 python 路径
$PY query.py stats
$PY query.py show 阿尔托莉雅          # 基础数值 + 宝具 + 技能 + 羁绊礼装推荐
$PY query.py show 岳父                # 支持黑话：自动解析为 兰斯洛特
$PY query.py slang 岳父               # 查看黑话释义与指代的从者/礼装
$PY query.py team "呆毛王 + 214 + 岳父"  # 多从者：百分比羁绊礼装最优分配（不重复）
$PY query.py filter "来自NFF的爱 + 异星之神 + 五星 + 女性"  # 礼装条件 + 限制条件 → 符合条件的英灵
$PY query.py show --id 2
$PY query.py s 阿尔托莉雅 --rarity 5
$PY query.py s --class 弓 --rarity 5
$PY query.py s --method 活动赠送 --rarity 4
$PY query.py ce 宝石 --rarity 4
$PY query.py ce --type 牵绊 --rarity 5
$PY query.py ce --effect NP获得量
$PY query.py sql "select id,name_cn,class,rarity from servants where class='Avenger' order by id"
```

数据更新（英灵/礼装一直在更新，需要最新内容时运行一次）：

```bash
$PY update.py
```

### 队伍查询规则（team）

`query.py team "英灵A + 英灵B + 英灵C"`：

- 百分比羁绊礼装对**全队符合条件者**生效（不是只对佩戴者生效）
- 每张礼装只能出现一次，最多选与队伍人数相同的张数
- 单张收益 = 最大解放加成 × 适用人数；按全队总收益从高到低选，使合计羁绊加成最大
- 只统计百分比加成，固定点数（英灵肖像 +50）不计入

## 已知限制
- 数据页本身不含实装日期，只能用 `id` 近似表示实装先后。
- 极少数尚未公开/不可获得的从者（E－火/水/宏/星玛丽、马里斯·迦勒底亚斯）没有稀有度。
- 最新一批礼装的名称与效果在 wiki 上仍是日文原文。
- 数据为 2026-10-25 抓取的快照，更新需重跑 `fetch_all.py` + `build.py`。
