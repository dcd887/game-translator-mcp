# 汉化测试结果（Test Reports）

本目录记录各游戏的**真实汉化测试结果**，供使用者评估工具效果与质量。
所有测试均在本地副本上执行，**不修改原始游戏文件**。

## 测试环境

- 平台：Windows / Python 3.14
- 翻译供应商：agnes ai（OpenAI 兼容，`agnes-2.5-flash`）
- 测试方式：将游戏本地化文件复制到本地副本 → 完整汉化 → 对比验证
- 单测：72/72 passed

---

## ✅ REPO（怪兽跑图）— TSV 完整汉化

**来源文件**：`REPO_Data/StreamingAssets/Localizations/Default/*.tsv`

| 文件 | 条目数 | 结果 |
|------|--------|------|
| `Game.tsv` | 14 | ✅ 全部翻译 |
| `HUD.tsv` | 192 | ✅ 全部翻译 |
| `Menu.tsv` | 397 | ✅ 396 条 |
| **合计** | **603** | **成功 602，失败 0** |

### 汉化样例

| 原文 | 译文 |
|------|------|
| `MAIN.SINGLEPLAYER` = Singleplayer | 单人游戏 |
| `MAIN.SETTINGS` = Settings | 设置 |
| `MAIN.QUIT_GAME` = Quit Game | 退出游戏 |
| `POPUP.PRIVATE_GAME.BODY` = The friend with the best computer\nshould host. | 电脑配置最好的朋友\n来创建房间。 |
| `BIG_MESSAGE.EXTRACTION.ACTIVATED` = Extraction point activated | 撤离点已激活 |
| `TUTORIAL.SNEAKING.TEXT` = Press [crouch] to sneak. Monsters are less likely to see you. | 按[蹲下键]潜行。怪物更难发现你。 |
| `REGIONS.REGION.CN` = Chinese Mainland | 中国内地 |

**结论**：603 条 TSV 全量汉化，602 条成功，回写保留 TSV 制表符格式，可直接用于游戏本地化。

---

## ✅ Portal 2 — VDF（Source 引擎）端到端汉化

Portal 2 的本地化文案以 **VDF**（Valve 键值格式）明文存储（`.txt` 后缀，UTF-16 编码）。此前不支持，现已加入解析器：

- **扫描**：自动嗅探 `.txt` 内容识别为 `vdf` 格式
- **解析**：解码 UTF-16（BOM 自动检测），提取 `"Tokens"` 内全部 key-value，`basemodui_english.txt` 共有 **2231** 条
- **回写**：生成规范 VDF `"lang" { "Language" ... "Tokens" { ... } }`，**保留 UTF-16 LE BOM 与原语言名**
- **单测**：新增 `TestParseVDF`（UTF-8 / UTF-16LE / 重复 key / 格式嗅探）

### 汉化样例（实际调用 agnes ai 翻译）

| 原文 | 译文 |
|------|------|
| `"Intro_Hello"` = Hello | 你好 |
| `"Menu_Play"` = Play | 开始游戏 |
| `"Menu_Settings"` = Settings | 设置 |
| `"Puzzle_Title"` = The Cake Is a Lie | 蛋糕是谎言 |

**验证**：UTF-16 BOM 保留、VDF 结构完整、`Language` 值保留，中文正确写入，可被 Source 引擎加载。

---

## ✅ Biped 2 — 明文 `key=value` 可汉化

`Biped2_Data/StreamingAssets/LocalizationData/localization_en.txt` 为 **UTF-8 `key=value`** 明文，**928** 条（含所有关卡名、按钮、提示文案），现有 `.txt` 解析器即可直接汉化，无需新格式支持。

---

## 🔍 其它 Steam 游戏扫描结果

对本机其它 Steam 游戏进行了可翻译文本扫描，结论如下：

| 游戏 | 可翻译文件 | 实际文案 | 说明 |
|------|-----------|----------|------|
| The Binding of Isaac Rebirth | 17 | 配置/文档 | 游戏文案在 `.a`/.dat 资源中 |
| Palworld | — | `.locres` | Unreal 资源包，需 UnrealPak 解包 |
| CSGO / HUSHED / theHunterCotW / How to Fish / Big Walk / Don't Panic 等 | — | 引擎配置/音频映射 | 无明文游戏文案 |

> 多数商业游戏的文案封装在私有资源包（`.vpk`/`.pak`/`.locres`）中，需先解包。本工具聚焦**明文文本文件**的汉化，详见 README「适用范围」。

---

## 🤝 欢迎补充游戏库

本工具支持任意**明文文本格式**的游戏/模组。如果你熟悉的游戏满足以下条件，欢迎贡献测试数据或一起扩展解析器：

1. **游戏文案以明文文件存储**（`.json` / `.tsv` / `.lang` / `.txt` / `.ini` / `.xml` / `.yaml` / `.sii` 或其它可读文本格式）
2. 游戏名 + 文件样例 + 预期格式，可通过 Issue / PR / Discussion 提交
3. 新格式可在 `parser.py` 添加解析函数、在 `scanner.py` 注册扩展名，并补充单元测试

已收录 / 已验证的游戏库见 [game-library.md](game-library.md)（欢迎扩充）。