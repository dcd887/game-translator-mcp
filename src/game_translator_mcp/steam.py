# -*- coding: utf-8 -*-
"""Steam 游戏发现模块。

扫描 Steam 库，返回已安装游戏的可翻译文件列表。
支持路径：
  - Windows: C:\\Program Files (x86)\\Steam\\steamapps\\common\\
  - Windows: C:\\Steam\\steamapps\\common\\
  - 自定义 libraryfolders.vdf 路径
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .scanner import TranslatableFile, scan_directory


def _parse_vdf(text: str) -> dict[str, str]:
    """极简 VDF 解析，提取 appid -> install dir。"""
    results: dict[str, str] = {}
    current_id = None
    for line in text.splitlines():
        m = re.match(r'"appid"\s+"(\d+)"', line)
        if m:
            current_id = m.group(1)
            continue
        m = re.match(r'\s+"installdir"\s+"([^"]+)"', line)
        if m and current_id:
            results[current_id] = m.group(1)
            current_id = None
    return results


def discover_steam_games(
    steam_path: Optional[Path] = None,
    library_paths: Optional[list[Path]] = None,
) -> list[dict]:
    """发现 Steam 已安装游戏，返回包含可翻译文件信息的列表。"""
    steam_root = steam_path or _default_steam_path()
    if not steam_root or not steam_root.exists():
        return []

    apps_dir = steam_root / "steamapps"
    common_dir = apps_dir / "common"

    results = []
    if common_dir.exists():
        for game_dir in sorted(common_dir.iterdir()):
            if not game_dir.is_dir():
                continue
            try:
                files = scan_directory(game_dir)
                if files:
                    results.append({
                        "name": game_dir.name,
                        "path": str(game_dir),
                        "translatable_files": len(files),
                        "files": [
                            {"path": str(f.path), "format": f.format, "lines": f.line_count}
                            for f in files[:20]  # 只返回前20个作为预览
                        ],
                    })
            except Exception:
                continue

    return results


def _default_steam_path() -> Optional[Path]:
    candidates = [
        Path("C:/Program Files (x86)/Steam"),
        Path("C:/Steam"),
        Path.home() / ".steam" / "steam",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_game_by_name(game_name: str) -> Optional[dict]:
    """按名称关键词查找 Steam 游戏。"""
    games = discover_steam_games()
    for g in games:
        if game_name.lower() in g["name"].lower():
            return g
    return None
