# -*- coding: utf-8 -*-
"""文件扫描模块：扫描游戏目录，识别可翻译的文本文件。

支持格式及扩展名：
  - .json  → JSON key-value 语言文件
  - .lang  → Minecraft .lang 格式 (key=value)
  - .txt   → 简单 key=value 文本（忽略 # 注释行）
  - .ini   → INI 配置文件中的 string 段
  - .xml   → XML 中的 <string> / <text> 元素
  - .yaml  → YAML 中的字符串值
  - .sii   → 欧洲卡车模拟器2 格式（Key="value"）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".json", ".lang", ".txt", ".ini", ".xml", ".yaml", ".yml", ".sii",
})

SKIP_PATTERNS: frozenset[str] = frozenset({
    "__pycache__", ".git", ".svn", "node_modules", ".venv", "venv",
    "build", "dist", ".DS_Store", "Thumbs.db", "assets/textures",
    "assets/models", "assets/audio", "assets/fonts", ".minecraft/saves",
    ".minecraft/mods", ".minecraft/config",
})


@dataclass(frozen=True)
class TranslatableFile:
    """一个可翻译文件的元信息。"""
    path: Path
    format: str          # "json" | "lang" | "txt" | "ini" | "xml" | "yaml" | "sii"
    line_count: int = 0  # 预估行数（快速估算）
    raw_data: bytes = field(default=b"", repr=False)

    @property
    def stem(self) -> str:
        return self.path.name


def _detect_format(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext == ".json":
        return "json"
    if ext == ".lang":
        return "lang"
    if ext in (".txt",):
        return "txt"
    if ext == ".ini":
        return "ini"
    if ext == ".xml":
        return "xml"
    if ext in (".yaml", ".yml"):
        return "yaml"
    if ext == ".sii":
        return "sii"
    if ext == ".tsv":
        return "tsv"
    return None


def _should_skip(path: Path, root: Path) -> bool:
    try:
        rel = str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        rel = str(path).replace("\\", "/")
    parts = rel.split("/")
    for part in parts:
        if part in SKIP_PATTERNS:
            return True
    return False


def scan_directory(
    directory: str | Path,
    extensions: Optional[Iterable[str]] = None,
    skip_patterns: Optional[frozenset[str]] = None,
) -> list[TranslatableFile]:
    """扫描目录，返回所有可翻译文件列表。

    按文件大小过滤：超过 10MB 的二进制文件会被跳过。
    """
    base = Path(directory).resolve()
    if not base.is_dir():
        raise ValueError(f"目录不存在: {base}")

    allowed = set(SUPPORTED_EXTENSIONS)
    if extensions:
        allowed |= {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}

    results: list[TranslatableFile] = []
    max_size = 10 * 1024 * 1024  # 10MB

    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if _should_skip(path, base):
            continue
        fmt = _detect_format(path)
        if fmt is None:
            continue
        try:
            size = path.stat().st_size
            if size > max_size:
                continue
            data = path.read_bytes()
            line_count = data.count(b"\n") + data.count(b"\r")
            results.append(TranslatableFile(
                path=path,
                format=fmt,
                line_count=line_count,
                raw_data=data,
            ))
        except (OSError, UnicodeDecodeError):
            continue  # 跳过无法读取的文件

    return results


def scan_game_by_name(game_name: str, root_directories: Optional[list[Path]] = None) -> list[TranslatableFile]:
    """通过游戏名称关键词在指定目录中搜索可翻译文件。"""
    candidates: list[Path] = []
    search_roots = root_directories or [Path.home() / "Desktop", Path.home() / "Documents"]
    for root in search_roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_dir():
                continue
            if game_name.lower() in p.name.lower():
                candidates.append(p)
    results: list[TranslatableFile] = []
    for candidate in candidates:
        results.extend(scan_directory(candidate))
    return results
