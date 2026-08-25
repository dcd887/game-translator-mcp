# -*- coding: utf-8 -*-
"""回写模块：将翻译结果按原格式写回文件，或生成独立汉化补丁。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .parser import TextParser, decode_text


class WriteError(Exception):
    pass


_VDF_ENCODINGS: tuple[tuple[bytes, str, bytes, str], ...] = (
    (b"\xff\xfe", "utf-16-le", b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be", b"\xfe\xff", "utf-16-be"),
    (b"\xef\xbb\xbf", "utf-8-sig", b"", "utf-8"),
)


def _detect_encoding(raw: bytes) -> tuple[str, bytes]:
    """检测原始编码：返回 (解码用编码名, 回写时需保留的 BOM 前缀)。"""
    for bom, dec, wbom, enc in _VDF_ENCODINGS:
        if raw.startswith(bom):
            return dec, wbom
    return "utf-8", b""


def _vdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _serialize_vdf(entries: dict[str, str], raw: bytes) -> bytes:
    """生成 Valve 语言 VDF 并保留原始编码 / BOM（Source 引擎，如 Portal 2）。

    原文 "lang" { "Language" ... "Tokens" { ... } } 会被规范化重写为等价的
    平铺结构（保留所有 key-value 与原始语言名），丢弃原空白/注释布局。
    """
    # 从原始数据提取语言名（Language），保证回写后仍能按原语言加载
    lang = "English"
    try:
        m = re.search(r'^\s*"Language"\s+"([^"]+)"', decode_text(raw), re.MULTILINE)
        if m:
            lang = m.group(1).replace('\\"', '"')
    except Exception:
        pass
    dec, wbom = _detect_encoding(raw)
    lines = ['"lang"', "{", '\t"Language"\t"%s"' % _vdf_escape(lang), '\t"Tokens"', "\t{"]
    for k, v in entries.items():
        lines.append('\t\t"%s"\t"%s"' % (_vdf_escape(k), _vdf_escape(v)))
    lines += ["\t}", "}", ""]
    text = "\r\n".join(lines) if dec.startswith("utf-16") else "\n".join(lines)
    body = text.encode(dec, errors="replace")
    return wbom + body


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

        data = self._serialize(entries, fmt, file_info.raw_data if fmt == "vdf" else None)
        out_path.write_bytes(data)
        return str(out_path)

    @classmethod
    def _serialize(cls, entries: dict[str, str], fmt: str, raw: Optional[bytes] = None) -> bytes:
        if fmt == "vdf":
            return _serialize_vdf(entries, raw or b"")
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
        if fmt == "tsv":
            lines = [f"{k}\t{v}" for k, v in entries.items()]
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
