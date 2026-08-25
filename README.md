# game-translator-mcp

通用游戏汉化 MCP 工具 —— 扫描游戏目录，调用 AI 翻译，回写中文文本。

> 定位：一个可以被 AI Agent 调用的「汉化能力」，而非独立的汉化软件。可与 mc-translator-mcp、mc-pack-builder-mcp 等工具协同工作。

## 支持的游戏与格式

| 状态 | 游戏 | 格式 | 说明 |
|------|------|------|------|
| ✅ 完整支持 | Minecraft (Java) | `.json` / `.lang` | 已验证 |
| ✅ 完整支持 | 欧洲卡车模拟器 2 | `.sii` | 格式清晰，结构稳定 |
| ✅ 完整支持 | 通用游戏 | `.json` / `.txt` / `.ini` / `.xml` / `.yaml` | 多格式解析器 |
| 🔄 计划支持 | Unity 游戏 | `.asset` 文本块 | 需 UnityPy 或反序列化 |
| 🔄 计划支持 | 幻兽帕鲁 | `.locres` | 需 UnrealPak 解包 |
| ❌ 暂不支持 | 战雷 / 绝地求生 | 加密或服务器下发 | 需要额外解包工具 |

## 安装

```bash
cd game-translator-mcp
pip install -e ".[dev]"
```

## 配置

复制 `.env.example` 为 `.env` 并填入 API Key：

```bash
cp .env.example .env
```

必填项：

```bash
DASHSCOPE_API_KEY=sk-your-qwen-key-here
# DEEPSEEK_API_KEY=          # 可选，通义千问失败时自动 fallback
BATCH_SIZE=15                # 每批翻译条数，越高越省 token
OUTPUT_DIR=translated_output # 汉化输出目录
```

API Key 申请：
- 通义千问（推荐）：[阿里云百炼控制台](https://bailian.console.aliyun.com/)
- DeepSeek（备选）：[DeepSeek 开放平台](https://platform.deepseek.com/)

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
python -m game_translator_mcp translate "C:/Users/kjds/Desktop/games/my-mod" --modid mymod

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
| `parser.py` | 多格式文本解析器（JSON / LANG / TXT / INI / XML / YAML / SII） |
| `translator.py` | 通义千问批量翻译 + SHA-256 缓存，避免重复消耗 token |
| `writer.py` | 回写翻译结果，保持原格式，支持 copy / inplace 两种模式 |
| `reporter.py` | 生成清晰的汉化报告（成功 / 跳过 / 失败统计） |
| `steam.py` | Steam 游戏发现，解析 VDF 索引文件 |
| `mcp_server.py` | MCP 服务器入口，暴露 4 个工具供 AI Agent 调用 |
| `cli.py` | 命令行接口，支持 check / translate / steam 子命令 |

## 设计要点

1. **智能缓存**：对 `{modid}::key::value` 做 SHA-256 哈希，相同原文只翻译一次，结果持久化到 `translator_cache.json`
2. **已有汉化跳过**：若输出目录中已存在相同格式的翻译文件，自动跳过，避免覆盖社区翻译
3. **批量翻译**：每条请求携带最多 `BATCH_SIZE` 个条目，一次 API 调用返回全部结果，大幅降低 token 和延迟
4. **fallback 策略**：通义千问失败时自动尝试 DeepSeek，确保翻译服务高可用
5. **零侵入输出**：默认 copy 模式生成独立输出目录，不修改原游戏文件

## 测试

```bash
python -m pytest tests/ -v
# 或
pytest tests/ -v
```

所有测试均在 Windows + Python 3.14 环境下通过（66 tests passed）。

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
