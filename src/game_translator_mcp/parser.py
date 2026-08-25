# -*- coding: utf-8 -*-
"""多格式文本解析器：从不同文件格式中提取 key-value 文本对。

支持的格式：
  .json  → {"key": "value"}
  .lang  → key=value  （Minecraft 格式）
  .txt   → key=value  或纯文本段落
  .ini   → [section]\nkey = value
  .xml   → <string name="key">value</string> 或 <text>value</text>
  .yaml  → key: value
  .sii   → Key="value"  （Euro Truck Simulator 2）
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class ParseError(Exception):
    pass


# ── 各格式解析函数（模块级，便于存入 _PARSERS 字典）────────────────────────

def _parse_json(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="replace")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}") from None
    if not isinstance(obj, dict):
        raise ParseError(f"JSON 顶层必须为对象，实际为 {type(obj).__name__}")
    return {str(k): str(v) for k, v in obj.items()}


def _parse_lang(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    # 有效 key：必须以字母/下划线开头，后续可为字母数字/_/-/点
    key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-\.]*)=.*$")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = key_re.match(stripped)
        if not m:
            continue
        key = m.group(1)
        value = stripped[len(key) + 1:].strip()
        result[key] = value
    return result


def _parse_txt(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    key_re = re.compile(r"^[A-Za-z0-9_\-\.]+$")
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key_re.match(key):
                result[key] = value
            else:
                result[f"line_{i}"] = stripped
        else:
            result[f"line_{i}"] = stripped
    return result


def _parse_ini(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    current_section = ""
    key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-\.]*)\s*=\s*(.+)$")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].strip()
            continue
        m = key_re.match(stripped)
        if m:
            key = m.group(1)
            if current_section:
                key = f"{current_section}.{key}"
            result[key] = m.group(2).strip()
    return result


def _parse_xml(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    # 只处理已知文本标签
    TAG_NAMES = frozenset({"string", "text", "tag", "message", "title", "description"})
    idx = 0
    while idx < len(text):
        tag_match = re.search(r"<(\w+)(\s[^>\/]*)?(/?>)", text[idx:])
        if not tag_match:
            break
        tag_name = tag_match.group(1)
        attrs_str = tag_match.group(2) or ""
        pos_after_tag = idx + tag_match.end()

        # 跳过处理指令等
        if tag_match.group(0).startswith("<?"):
            idx = pos_after_tag
            continue

        if tag_match.group(3).startswith("/>"):
            # 自闭合标签
            if tag_name in TAG_NAMES:
                name_m = re.search(r'name="([^"]*)"', attrs_str)
                if name_m:
                    key = f"{tag_name}.{name_m.group(1)}"
                    result[key] = ""
            idx = pos_after_tag
            continue

        if tag_name not in TAG_NAMES:
            idx = pos_after_tag
            continue

        close_tag = f"</{tag_name}>"
        end_idx = text.find(close_tag, pos_after_tag)
        if end_idx == -1:
            break
        content = text[pos_after_tag:end_idx].strip()
        name_m = re.search(r'name="([^"]*)"', attrs_str)
        if name_m:
            key = f"{tag_name}.{name_m.group(1)}"
        else:
            key = f"{tag_name}.{len(result)}"
        result[key] = content
        idx = end_idx + len(close_tag)
    return result


def _parse_yaml(data: bytes) -> dict[str, str]:
    if not _HAS_YAML:
        return {}
    text = data.decode("utf-8", errors="replace")
    obj = yaml.safe_load(text)
    if not isinstance(obj, dict):
        raise ParseError(f"YAML 顶层必须为对象，实际为 {type(obj).__name__}")
    result: dict[str, str] = {}

    def _flatten(obj, prefix: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_prefix = f"{prefix}{k}." if prefix else f"{k}."
                _flatten(v, new_prefix)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _flatten(v, f"{prefix}[{i}].")
        else:
            result[prefix.rstrip(".")] = str(obj)

    _flatten(obj, "")
    return result


def _parse_sii(data: bytes) -> dict[str, str]:
    text = data.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    key_re = re.compile(r'^(\w+)="([^"]*)"$')
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = key_re.match(stripped)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def _parse_tsv(data: bytes) -> dict[str, str]:
    """TSV 制表符分隔的 key\\t值 格式（常见于 Unity 本地化表）。"""
    text = data.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in stripped:
            key, _, value = stripped.partition("\t")
            key = key.strip()
            if key:
                result[key] = value.strip()
        else:
            # 无制表符的行按原文保留（可能是空值条目或表头）
            if stripped:
                key_re = re.compile(r"^[A-Za-z0-9_\-\.]+$")
                if "=" in stripped:
                    key, _, value = stripped.partition("=")
                    key = key.strip()
                    if key_re.match(key):
                        result[key] = value.strip()
    return result


# ── 主解析器类 ─────────────────────────────────────────────────────────────

_PARSERS: dict[str, callable] = {
    "json": _parse_json,
    "lang": _parse_lang,
    "txt": _parse_txt,
    "ini": _parse_ini,
    "xml": _parse_xml,
    "yaml": _parse_yaml,
    "sii": _parse_sii,
    "tsv": _parse_tsv,
}


class TextParser:
    """多格式文本解析器。"""

    @classmethod
    def parse(cls, data: bytes, fmt: str) -> dict[str, str]:
        parser = _PARSERS.get(fmt)
        if parser is None:
            raise ValueError(f"不支持的格式: {fmt!r}")
        return parser(data)

    @classmethod
    def guess_format_from_path(cls, path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".sii":
            return "sii"
        if ext == ".lang":
            return "lang"
        if ext == ".tsv":
            return "tsv"
        if ext in (".json", ".txt", ".ini", ".xml", ".yaml", ".yml"):
            return "yaml" if ext == ".yml" else ext.lstrip(".")
        return "txt"
