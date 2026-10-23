# game-translator-mcp

[![M8ven Verified](https://m8ven.ai/badge/mcp/dcd887/game-translator-mcp?variant=verified)](https://m8ven.ai/mcp/dcd887/game-translator-mcp?s=readme)

A game localization MCP server. Point it at a game folder; it scans text files, translates them through an LLM, and writes the result back — without touching the original files.

## Tools

| Tool | What it does |
|---|---|
| `scan_game_directory` | Find translatable files and estimate volume |
| `preview_translate_game` | Zero-cost estimate (no API calls, no writes) |
| `translate_game` | Full run: translate + write back + report |
| `dry_run_translate` | Preview translations without writing |
| `list_steam_games` | List installed Steam games that contain text files |

## Supported formats

`.json` `.lang` `.txt` `.ini` `.xml` `.yaml` `.sii` `.tsv` `.vdf` `.csv` `.properties` `.po` `.strings` `.resx` `.xliff` `.rpy` `.srt` `.ass` — UTF-8 / UTF-16 (BOM auto-detect).

## Not supported

- Unity `.pak` / `.vpk` / `catalog.json` binaries (unpack first)
- Unreal `.locres` (needs UnrealPak)
- Server-side or encrypted text (no cracking)

## Install

```bash
pip install -e .
python -m game_translator_mcp preview <game-dir>
```

Requires an OpenAI-compatible API key (see `.env.example`).

## Design notes

- **copy mode**: output goes to a separate folder; originals are never modified
- **batching + cache**: repeated strings are translated once
- **honest reporting**: every skipped file is reported with a reason

## License

MIT
