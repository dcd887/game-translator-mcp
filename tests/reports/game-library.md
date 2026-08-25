# 游戏库（欢迎补充）

记录已验证 / 已支持汉化的游戏与格式。**欢迎提交 Issue / PR 补充**。

## 已实测汉化

| 游戏 | 格式 | 状态 | 说明 |
|------|------|------|------|
| REPO（怪兽跑图） | `.tsv` | ✅ 完整汉化测试通过 | 详见 [tests/reports](tests/reports/README.md)，603 条全量翻译 |
| Portal 2 | `.txt`(VDF) | ✅ 端到端汉化验证通过 | Source 引擎 UTF-16 VDF，2231 条明文可翻译，回写保留 UTF-16 BOM |
| Biped 2 | `.txt` | ✅ 明文可汉化 | `LocalizationData/localization_en.txt` 为 `key=value`，928 条 |

## 已支持格式（解析器已内置）

`.json` / `.lang` / `.txt` / `.ini` / `.xml` / `.yaml` / `.sii` / `.tsv` / `.vdf`（UTF-8 与 UTF-16，自动 BOM 检测）

> VDF 说明：Source 引擎（Portal 2 / HL2 / L4D）本地化文件为 VDF，通常以 `.txt` 结尾且为 UTF-16 编码。扫描器会自动嗅探内容并识别为 `vdf`，回写时保留原始编码与 BOM。

## 扫描过但暂不支持（文案封装于二进制）

| 游戏 | 原因 |
|------|------|
| The Binding of Isaac Rebirth | 文案在 `.a` / `.dat` 资源 |
| Palworld | 文案在 `.locres`（Unreal 资源包），需 UnrealPak 解包 |
| CSGO / HUSHED / theHunterCotW / How to Fish / Big Walk 等 | 明文仅为引擎配置 / 音频映射 / 工具配置，无游戏文案 |

## 如何补充一款新游戏

1. 确认你的游戏文案是**明文文本**（`.json` / `.tsv` / `.lang` / `.sii` / `.vdf` 或其它可读格式）
2. 若格式已支持：直接把 `游戏目录` 交给本工具汉化即可
3. 若格式**未支持**：
   - 在 `parser.py` 添加解析函数（参考 `_parse_tsv`），注册到 `_PARSERS`
   - 在 `scanner.py` 的 `SUPPORTED_EXTENSIONS` 添加扩展名
   - 在 `tests/test_parser.py` 补充单元测试
   - 错误率提示：完成后可把「游戏名 + 文件样例」提交到 GitHub，帮助完善游戏库