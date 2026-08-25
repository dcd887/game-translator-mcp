# game-translator-mcp

通用游戏汉化 MCP 工具 —— 扫描游戏目录，调用 AI 翻译，回写中文文本。

> 定位：一个可以被 AI Agent 调用的「汉化能力」，而非独立的汉化软件。可与 mc-translator-mcp、mc-pack-builder-mcp 等工具协同工作。

## 适用范围

本工具面向**文本以明文文件存储**的游戏/模组进行汉化，属于"文本汉化"而非"资源包注入"。

| 适用范围 | 说明 |
|----------|------|
| 支持的文本格式 | `.json` / `.lang` / `.txt` / `.ini` / `.xml` / `.yaml` / `.sii` / `.tsv` / `.vdf`（UTF-8 / UTF-16 自动 BOM 检测）/ `.csv` / `.properties` / `.po` / `.strings` / `.resx` / `.xliff` / `.rpy` / `.srt` / `.ass` |
| 典型的适用对象 | Minecraft 模组、欧洲卡车模拟器 2、**Source 引擎游戏（Portal 2 / HL2 / L4D 的 VDF）**、Ren'Py 视觉小说（galgame）、字幕（SRT/ASS）、gettext(.po)、Unity 明文本地化表、Steam 明文配置文件 |
| 输入 | 游戏根目录或任意文本文件目录 |
| 输出 | 独立汉化目录（copy 模式），不改动原游戏文件 |

**不适用范围 / 已知限制**：

- Unity 打包的 `.pak` / `.vpk` / `catalog.json` 二进制资源，需先解包才能处理
- 幻兽帕鲁等使用 `.locres` 的 Unreal 游戏，需 UnrealPak 解包
- 战雷 / 绝地求生等服务端下发或加密的文本，不提供破解支持
- 超过 10MB 的文本文件（防误扫二进制），扫描时自动跳过

> 提示：Unity 游戏虽有大量 `.json`/`.xml`，但多数是引擎配置而非游戏文案；扫描器会如实返回，是否值得翻译由使用者判断。

## 使用条件

| 条件 | 说明 |
|------|------|
| Python | ≥ 3.10 |
| 依赖 | 见 `pyproject.toml`（mcp、openai、pydantic 等） |
| 联网 | 必须能联网调用 AI 翻译 API |
| API Key | **不绑定任何特定供应商**。由使用者自任选一个 OpenAI 兼容供应商，提供 key / base_url / 模型名（见下方「配置」），这是翻译能力的必要前提 |
| 可移植性 | 纯 Python + 标准依赖，可在 Windows / macOS / Linux 本地跑通，无平台耦合 |
| 授权 | 汉化后的文本仅限个人学习 / 非商业用途；商用需确认游戏与模组的二次分发条款 |

**AI 供应商完全由使用者配置**（检测哪个 key 已配置就用哪个，优先级 `custom > agnes > dashscope > deepseek`）：

- **自定义 OpenAI 兼容供应商**（推荐，最通用）：`TRANSLATOR_API_KEY` + `TRANSLATOR_BASE_URL` + `TRANSLATOR_MODEL`，任意兼容接口平台都可用
- **agnes ai**：`AGNES_API_KEY` + `AGNES_BASE_URL` + `AGNES_MODEL`
- **通义千问**：`DASHSCOPE_API_KEY`
- **DeepSeek**（可选 fallback）：`DEEPSEEK_API_KEY`

## 安装

```bash
cd game-translator-mcp
pip install -e ".[dev]"
```

## 配置

复制 `.env.example` 为 `.env` 并填写你要用的供应商：

```bash
cp .env.example .env
```

任选一种方式（检测到哪个 key 就用哪个，优先级 `custom > agnes > dashscope > deepseek`）：

```bash
# 方式 A（推荐，最通用）：自定义 OpenAI 兼容供应商 —— 填你自己的 key / 网关地址 / 模型名
TRANSLATOR_API_KEY=sk-xxx
TRANSLATOR_BASE_URL=https://your-gateway.example.com/v1
TRANSLATOR_MODEL=your-model

# 方式 B：agnes ai（也可展开为 OpenAi 兼容平台）
# AGNES_API_KEY=sk-xxx
# AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
# AGNES_MODEL=agnes-2.5-flash

# 方式 C：通义千问
# DASHSCOPE_API_KEY=sk-your-qwen-key-here

# 方式 D：DeepSeek（可选，主供应商失败时 fallback）
# DEEPSEEK_API_KEY=

BATCH_SIZE=15                # 每批翻译条数，越高越省 token
OUTPUT_DIR=translated_output # 汉化输出目录
```

> 配置优先级：先读环境变量，其次读项目根目录 `.env` 文件，最后为内置默认值。
> API Key 由使用者自备，自行寻求对应平台申请（如 agnes / 通义 / DeepSeek / 其它 OpenAI 兼容网关）。

> **可移植性**：本工具不绑定任何云服务供应商，只要在目标机器配置好上述任一套 API 参数即可本地运行，适用于 CI、Docker 或任意平台。

## 启动方式

### 作为 MCP 服务器（供 AI Agent 调用）

```bash
python -m game_translator_mcp
```

Trae / Claude Desktop 配置示例：

```json
{
  "mcpServers": {
    "game-translator-mcp": {
      "command": "python",
      "args": ["-m", "game_translator_mcp"]
    }
  }
}
```

LangChain Agent 集成（`PYTHONPATH` 指向 `src/`）：

```json
{
  "mcpServers": {
    "game-translator-mcp": {
      "command": "python",
      "args": ["-m", "game_translator_mcp"],
      "env": {
        "PYTHONPATH": "/path/to/game-translator-mcp/src"
      }
    }
  }
}
```

### CLI 模式

```bash
# 扫描游戏目录，列出可翻译文件
python -m game_translator_mcp check <游戏目录路径>

# 执行完整汉化
python -m game_translator_mcp translate <游戏目录路径> --modid mygame

# 预览翻译效果（不写入文件）
python -m game_translator_mcp translate <游戏目录路径> --modid mygame --dry-run

# 列出 Steam 库中的可翻译游戏
python -m game_translator_mcp steam
```

## MCP 工具

| 工具名 | 功能 |
|--------|------|
| `scan_game_directory` | 扫描目录，返回可翻译文件列表 + 文本量估算 |
| `translate_game` | 完整汉化流程：扫描 → AI 翻译 → 回写 → 生成报告 |
| `dry_run_translate` | 预览翻译效果，不实际修改文件 |
| `list_steam_games` | 发现本地 Steam 库中已安装的可翻译游戏 |

## 使用示例

### 自然语言调用（通过 Trae）

> "帮我扫描一下我的 Steam 游戏里哪些有可翻译文本"

> "帮我翻译 'RimWorld' 这个游戏的英文文本"

> "预览一下 'Factorio' 的汉化效果，不要实际写入"

### 直接命令行调用

```bash
# 汉化一个模组目录
python -m game_translator_mcp translate "path/to/my-mod" --modid mymod

# 输出目录默认为 translated_output/
# 汉化报告自动生成到 translated_output/report.txt
```

## 输出结构

```
translated_output/
├── my-mod/
│   ├── assets/my-mod/lang/zh_cn.json
│   └── ...（保持原目录结构）
├── rimworld/
│   ├── Assets/StreamingAssets/Localization/zh-cn.json
│   └── ...
└── report.txt           # 汉化报告
```

## 核心模块

| 模块 | 功能 |
|------|------|
| `scanner.py` | 扫描游戏目录，识别可翻译文件，过滤二进制/大文件 |
| `parser.py` | 多格式文本解析器（JSON / LANG / TXT / INI / XML / YAML / SII / TSV / VDF / CSV / properties / PO / strings / resx / xliff / rpy / srt / ass） |
| `translator.py` | 任意 OpenAI 兼容供应商批量翻译（custom / agnes / 通义 / DeepSeek）+ SHA-256 缓存 |
| `writer.py` | 回写翻译结果，保持原格式，支持 copy / inplace 两种模式 |
| `reporter.py` | 生成清晰的汉化报告（成功 / 跳过 / 失败统计） |
| `steam.py` | Steam 游戏发现，解析 VDF 索引文件 |
| `mcp_server.py` | MCP 服务器入口，暴露 4 个工具供 AI Agent 调用 |
| `cli.py` | 命令行接口，支持 check / translate / steam 子命令 |

## 设计要点

1. **智能缓存**：对 `{modid}::key::value` 做 SHA-256 哈希，相同原文只翻译一次，结果持久化到 `translator_cache.json`
2. **已有汉化跳过**：若输出目录中已存在相同格式的翻译文件，自动跳过，避免覆盖社区翻译
3. **批量翻译**：每条请求携带最多 `BATCH_SIZE` 个条目，一次 API 调用返回全部结果，大幅降低 token 和延迟
4. **供应商自适应**：检测用户配置了哪个 key 就用哪个（custom > agnes > dashscope），可选 DeepSeek 做 fallback，不绑定任何一家
5. **零侵入输出**：默认 copy 模式生成独立输出目录，不修改原游戏文件

## 测试

```bash
python -m pytest tests/ -v
# 或
pytest tests/ -v
```

所有测试均在 Windows + Python 3.14 环境下通过（87 tests passed，含新增 8 类明文格式用例）。

### 真实汉化测试

结合真实游戏文件做了端到端汉化验证（使用 agnes ai），结果已归档到 [`tests/reports/`](tests/reports/README.md)：

- ✅ **REPO**（怪兽跑图）：`Menu/HUD/Game.tsv` 共 **603** 条，全部真实翻译并回写为 TSV，成功 602 条
- ✅ **Portal 2**：Source 引擎 VDF（UTF-16）端到端汉化，`basemodui_english.txt` 共 2231 条明文可翻译，回写保留 UTF-16 BOM
- ✅ **Biped 2**：`localization_en.txt` 明文 `key=value` 928 条，可直接汉化
- ✅ **新增明文格式**：`.csv` / `.properties` / `.po` / `.strings` / `.resx` / `.xliff` / `.rpy` / `.srt` / `.ass` 全部做了真实翻译与回写验证；其中 `.rpy`/`.srt`/`.ass` 采用**原位 token 回填**，不破坏脚本/字幕结构
- 🔍 其余游戏（Isaac / Palworld / CSGO 等）：文本封装于私有资源包或仅引擎配置，详见测试报告

## 欢迎补充游戏库

本工具支持任意**明文文本格式**的游戏/模组。如果你的游戏文案以明文文件（`.json` / `.tsv` / `.lang` / `.sii` / `.vdf` 等）存储，欢迎通过 Issue / PR 补充游戏库，一起扩展现有解析器。详细指引见 [`tests/reports/`](tests/reports/README.md)。

## 与现有工具链的关系

| 工具 | 协作方式 |
|------|----------|
| `mc-translator-mcp` | Minecraft 专用强化版；本工具的 MC 子集 |
| `mc-pack-builder-mcp` | 构建整合包时自动检测模组是否需要汉化，并调用本工具完成翻译 |
| `mc-mod-config-mcp` | 汉化完成后检查配置文件格式是否正常 |
| LangChain Agent | 通过 MCP stdio 协议接入，支持自然语言驱动汉化流程 |

## 贡献指南

添加对新游戏格式的支持：

1. 在 `parser.py` 中添加新的解析函数（如 `_parse_locres`）
2. 注册到 `_PARSERS` 字典
3. 在 `scanner.py` 的 `SUPPORTED_EXTENSIONS` 中添加扩展名
4. 在 `tests/test_parser.py` 中添加对应测试

## 许可证

MIT License — 自由使用、修改和分发。
