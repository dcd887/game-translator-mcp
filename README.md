mcp-name: io.github.dcd887/game-translator

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

> 📚 **想知道你的游戏在被支持范围内吗？** 先看这里 → **[SUPPORTED_GAMES.md](SUPPORTED_GAMES.md)**（含已实测游戏、引擎→格式速查表、不支持清单）。
> 快速判断口诀：**文案只要是明文文件就能汉化**；不确定就 `python -m game_translator_mcp preview <目录>` 零成本看一眼。

**不适用范围 / 已知限制**：

- Unity 打包的 `.pak` / `.vpk` / `catalog.json` 二进制资源，需先解包才能处理
- 幻兽帕鲁等使用 `.locres` 的 Unreal 游戏，需 UnrealPak 解包
- 战雷 / 绝地求生等服务端下发或加密的文本，不提供破解支持
- 单个文本文件超过大小阈值（默认 10MB，防误扫二进制），扫描时跳过 —— **阈值可用 `--max-size-mb N` 或环境变量 `SCAN_MAX_SIZE_MB` 调高**（部分游戏明文配置刚好超 10MB 时很有用）

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
SCAN_MAX_SIZE_MB=10          # 单个文本文件大小阈值（MB），超过跳过；明文文件较大的游戏可调高
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
# 零成本预览：先看会扫到哪些文件、多少条文本、预估多少 token（不调用 AI、不写文件）
python -m game_translator_mcp preview <游戏目录路径>

# 若游戏的明文配置文件超过 10MB 被跳过，可用 --max-size-mb 调高阈值再扫
python -m game_translator_mcp preview <游戏目录路径> --max-size-mb 30

# 扫描游戏目录，列出可翻译文件
python -m game_translator_mcp check <游戏目录路径>

# 执行完整汉化
python -m game_translator_mcp translate <游戏目录路径> --modid mygame

# 预览翻译效果（抽样翻译，不写入文件）
python -m game_translator_mcp dry-run <游戏目录路径>

# 列出 Steam 库中的可翻译游戏
python -m game_translator_mcp steam
```

> 💡 **先 preview 再 translate**：翻译会消耗 token，默认输出到独立目录 `translated_output/` 不会覆盖原文件。正式执行前先跑 `preview` 估一下工作量，避免白花 token。

## MCP 工具

| 工具名 | 功能 |
|--------|------|
| `preview_translate_game` | **零成本预览**（--dry-run）：先扫出会处理哪些文件、每种格式数量、总条目数、预估 token，不调 AI、不消耗额度、不写文件 |
| `scan_game_directory` | 扫描目录，返回可翻译文件列表 + 文本量估算 |
| `translate_game` | 完整汉化流程：扫描 → AI 翻译 → 回写 → 生成报告 |
| `dry_run_translate` | 抽样预览翻译效果（会调用 AI 翻译一小部分样例），不实际写入文件 |
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

## 新手怎么用（一句话版）

1. **先预览，不花钱**：`python -m game_translator_mcp preview "游戏目录"` → 看会翻译多少条。
2. **觉得量合适就翻译**：`python -m game_translator_mcp translate "游戏目录" --modid mygame` → 结果输出到 `translated_output/`，**原文件一个都不动**。
3. **翻好了？照着下面「导入汉化」复制回游戏里**，中文就生效了。

### 怎么把汉化「装」进游戏（导入 / 覆盖原文件教学）

本工具默认是**copy 模式**：只把翻译结果写到 `translated_output/` 目录，绝不侵入你的原游戏文件。这样安全，但中文不会立即生效——你需要自己把汉化文件**放进游戏认得到的位置**。不同游戏的「位置」不一样，通常是这三种情况：

| 游戏类型 | 汉化文件该放哪 | 说明 |
|----------|---------------|------|
| **我的世界模组/资源包** | 装成一个**资源包**（把 `translated_output` 里的 `.json` 按 `assets/<modid>/lang/` 结构打包，或用 mc-pack-builder-mcp 生成），在游戏里启用该资源包 | 模组文案以官方资源包方式覆盖 |
| **Steam / 大多单机游戏** | 找到游戏目录里的**原语言文件**（英文的 `en_us.json` / `Localization` 文件夹），把汉化文件**改名成游戏读取的那个语言名**（比如 `zh_cn.json`），**覆盖**进去 | 改完重进游戏/重启生效 |
| **只有特定语言名的** | 作为**可选语言**丢进游戏的本地化目录 | 在游戏设置里切换语言到中文 |

⚠️ **覆盖前请一定留备份**——这是能安全撤回去的唯一办法：

```bash
# 以某游戏的 Localization/english.json 为例：先把原文件备份，再覆盖
cp "游戏目录/Localization/english.json" "游戏目录/Localization/english.json.bak"
cp "translated_output/你汉化后的文件.json" "游戏目录/Localization/english.json"
```

> 如果你不确定该放哪，**直接把游戏目录 + 汉化输出目录一起发给 AI**，让它帮你判断文件对应关系、给出准确的复制命令 —— 因为本工具就是给 AI Agent 调用的。

> 需要我把这份「导入/覆盖」说明做成逐步演示（配上具体游戏的实际路径）吗？告诉我你的游戏和目录，我就演示给你看。

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
| `mcp_server.py` | MCP 服务器入口，暴露 5 个工具供 AI Agent 调用 |
| `cli.py` | 命令行接口，支持 check / preview / dry-run / translate / steam 子命令 |

## 设计要点

1. **智能缓存**：对 `{modid}::key::value` 做 SHA-256 哈希，相同原文只翻译一次，结果持久化到 `translator_cache.json`
2. **零成本预览**：`preview_translate_game` 先扫文件、估条目数和 token，不调 AI、不写文件，帮你决定要不要花钱翻译
3. **已有汉化跳过**：若输出目录中已存在相同格式的翻译文件，自动跳过，避免覆盖社区翻译
4. **批量翻译**：每条请求携带最多 `BATCH_SIZE` 个条目，一次 API 调用返回全部结果，大幅降低 token 和延迟
5. **供应商自适应**：检测用户配置了哪个 key 就用哪个（custom > agnes > dashscope），可选 DeepSeek 做 fallback，不绑定任何一家
6. **零侵入输出**：默认 copy 模式生成独立输出目录，不修改原游戏文件

## 测试

```bash
python -m pytest tests/ -v
# 或
pytest tests/ -v
```

所有测试均在 Windows + Python 3.14 环境下通过（89 tests passed，含新增 8 类明文格式用例与零成本预览 preview 用例）。

### 真实汉化测试

结合真实游戏文件做了端到端汉化验证（使用 agnes ai），结果已归档到 [`tests/reports/`](tests/reports/README.md)：

- ✅ **REPO**（怪兽跑图）：`Menu/HUD/Game.tsv` 共 **603** 条，全部真实翻译并回写为 TSV，成功 602 条
- ✅ **Portal 2**：Source 引擎 VDF（UTF-16）端到端汉化，`basemodui_english.txt` 共 2231 条明文可翻译，回写保留 UTF-16 BOM
- ✅ **Biped 2**：`localization_en.txt` 明文 `key=value` 928 条，可直接汉化
- ✅ **新增明文格式**：`.csv` / `.properties` / `.po` / `.strings` / `.resx` / `.xliff` / `.rpy` / `.srt` / `.ass` 全部做了真实翻译与回写验证；其中 `.rpy`/`.srt`/`.ass` 采用**原位 token 回填**，不破坏脚本/字幕结构
- 🔍 其余游戏（Isaac / Palworld / CSGO 等）：文本封装于私有资源包或仅引擎配置，详见测试报告

## 欢迎补充游戏库

本工具支持任意**明文文本格式**的游戏/模组。如果你的游戏文案以明文文件（`.json` / `.tsv` / `.lang` / `.sii` / `.vdf` 等）存储，欢迎通过 Issue / PR 补充游戏库，一起扩展现有解析器。

- 已完成的支持范围见 **[SUPPORTED_GAMES.md](SUPPORTED_GAMES.md)**
- 详细测试与新增游戏接入指引见 [`tests/reports/`](tests/reports/README.md)
- 新格式接入步骤见下方「贡献指南」

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
