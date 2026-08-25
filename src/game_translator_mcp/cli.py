# -*- coding: utf-8 -*-
"""CLI 命令行入口（避免 mcp_server.py 自引用的循环导入）。

用法：
  python -m game_translator_mcp check <directory>
  python -m game_translator_mcp translate <directory> [--modid name] [--batch-size N]
  python -m game_translator_mcp steam
  python -m game_translator_mcp              # 启动 MCP server（默认）
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from .mcp_server import mcp, scan_game_directory, translate_game
from .steam import discover_steam_games


def cli_main() -> None:
    args = sys.argv[1:]
    if not args:
        mcp.run()
        return

    cmd = args[0]
    if cmd == "check":
        if len(args) < 2:
            print("用法: python -m game_translator_mcp check <directory>")
            return
        result = asyncio.run(scan_game_directory(args[1]))
        print(result)
    elif cmd == "translate":
        if len(args) < 2:
            print("用法: python -m game_translator_mcp translate <directory> [--modid name] [--batch-size N]")
            return
        modid = "game"
        batch_size = 15
        i = 1
        while i < len(args):
            if args[i] == "--modid" and i + 1 < len(args):
                modid = args[i + 1]
                i += 2
            elif args[i] == "--batch-size" and i + 1 < len(args):
                batch_size = int(args[i + 1])
                i += 2
            else:
                i += 1
        result = asyncio.run(translate_game(args[1], modid=modid, batch_size=batch_size))
        print(result)
    elif cmd == "steam":
        games = discover_steam_games()
        print(json.dumps({"games": len(games), "list": games}, ensure_ascii=False, indent=2))
    else:
        mcp.run()
