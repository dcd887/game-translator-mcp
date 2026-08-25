# -*- coding: utf-8 -*-
"""回写模块：将翻译结果按原格式写回文件，或生成独立汉化补丁。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .parser import TextParser


class WriteError(Exception):
    pass


class GameWriter:
    """将翻译结果写回原始格式，或输出到独立目录。"""

    def __init__(self, output_root: Path, mode: str = "copy", source_root: Optional[Path] = None) -> None:
        """
        mode:
          "copy"   → 输出到新目录，不修改原文件（推荐）
          "inplace"→ 直接覆盖原文件（慎用）
        source_root:
          源文件所在根目录，copy 模式下用于计算相对路径（与 mcp_server 中的 target 对应）
        """
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.source_root = source_root.resolve() if source_root is not None else None

    def write(
        self,
        file_info,
        entries: dict[str, str],
        fmt: str,
        backup: bool = True,
    ) -> str:
        """写回翻译结果，返回输出文件路径。

        file_info 是 scanner.TranslatableFile 对象。
        """
        if self.mode == "inplace":
            if backup:
                bak = file_info.path.with_suffix(file_info.path.suffix + ".bak")
                if not bak.exists():
                    file_info.path.write_bytes(file_info.raw_data)
            out_path = file_info.path
        else:
            # copy 模式：将文件路径相对于 source_root 计算
            if self.source_root is not None and file_info.path.is_relative_to(self.source_root):
                rel_str = str(file_info.path.relative_to(self.source_root)).replace("\\", "/")
            else:
                path_str = str(file_info.path)
                anchor = file_info.path.anchor
                if anchor and path_str.startswith(anchor):
                    rel_str = path_str[len(anchor):]
                else:
                    try:
                        rel_str = str(file_info.path.relative_to(Path("/")))
                    except ValueError:
                        rel_str = file_info.path.name
                rel_str = rel_str.lstrip("/\\").replace("\\", "/")
            out_path = Path(str(self.output_root) + ("/" + rel_str if rel_str else "" + file_info.path.name))
            out_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._serialize(entries, fmt)
        out_path.write_bytes(data)
        return str(out_path)

    @classmethod
    def _serialize(cls, entries: dict[str, str], fmt: str) -> bytes:
        if fmt == "json":
            return json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8")
        if fmt == "lang":
            lines = [f"{k}={v}" for k, v in entries.items()]
            return ("\n".join(lines) + "\n").encode("utf-8")
        if fmt == "txt":
            lines = [f"{k}={v}" for k, v in entries.items()]
            return ("\n".join(lines) + "\n").encode("utf-8")
        if fmt == "ini":
            lines = [f"{k} = {v}" for k, v in entries.items()]
            return ("\n".join(lines) + "\n").encode("utf-8")
        if fmt == "xml":
            parts = ['<?xml version="1.0" encoding="UTF-8"?>']
            for k, v in entries.items():
                parts.append(f'  <string name="{k}">{v}</string>')
            return ("\n".join(parts) + "\n").encode("utf-8")
        if fmt == "yaml":
            try:
                import yaml
                return yaml.dump(
                    entries, allow_unicode=True, sort_keys=False, width=200
                ).encode("utf-8")
            except ImportError:
                lines = [f"{k}: {v}" for k, v in entries.items()]
                return ("\n".join(lines) + "\n").encode("utf-8")
        if fmt == "sii":
            lines = [f'{k}="{v}"' for k, v in entries.items()]
            return ("\n".join(lines) + "\n").encode("utf-8")
        raise ValueError(f"不支持的格式: {fmt!r}")

    @classmethod
    def count_entries(cls, data: bytes, fmt: str) -> int:
        """统计条目数。"""
        try:
            entries = TextParser.parse(data, fmt)
            return len(entries)
        except Exception:
            return 0
