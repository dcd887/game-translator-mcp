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


_TEXT_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
)


def decode_text(data: bytes) -> str:
    """按 BOM 检测并解码文本：UTF-8 / UTF-16 Liitle-Endian / UTF-16 Big-Endian。

    无 BOM 时按 UTF-8 容错解码（损耗可接受）。UTF-16 解码会残留 U+FEFF
    BOM 字符，统一剥离到首个非空白字符之前。
    """
    for bom, enc in _TEXT_BOMS:
        if data.startswith(bom):
            return data.decode(enc).lstrip("\ufeff")
    return data.decode("utf-8", errors="replace").lstrip("\ufeff")


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


_VDF_DUP_SUFFIX = "##_DUP_"
_VDF_SKIP_KEYS = frozenset({"lang", "Language", "Tokens", "Platforms", "...", "$POSITION"})

def _parse_vdf(data: bytes) -> dict[str, str]:
    """Valve VDF 语言文件解析（Source 引擎，如 Portal 2 / HL2 / L4D）。

    结构： "lang" { "Language" "English" "Tokens" { "key" "value" ... } }
    支持 UTF-8 / UTF-16（LE/BE/BOM 自动检测）。
    支持重复 key（平台条件，如 [$WIN32]），用 `##_DUP_N` 后缀保序，
    回写时可无损还原。
    """
    text = decode_text(data)
    result: dict[str, str] = {}
    seen: dict[str, int] = {}
    key_re = re.compile(r'^\s*"([^"]+)"\s+"(.*)"\s*\[?[^]]*\]?\s*$')
    for raw in text.splitlines():
        line = raw.rstrip()
        m = key_re.match(line)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2)
        # 跳过结构关键字（lang / Language / Tokens / Platforms 等）
        if key in _VDF_SKIP_KEYS:
            continue
        # 值可能含转义后的引号，移除行尾条件标记后的残留
        value = value.replace('\\"', '"')
        if key not in seen:
            seen[key] = 0
            result[key] = value
        else:
            seen[key] += 1
            result[f"{key}{_VDF_DUP_SUFFIX}{seen[key]}"] = value
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


# ── 嵌入式文本占位（rpy / srt / ass）────────────────────────────────────────
# 这类格式是「脚本/字幕 + 文本」混合体，翻译时不能重建，否则破坏结构。
# 方案：解析阶段把文本片段替换为唯一 token，key=token、value=原文；
# writer 用「同一套 tokenizer」对原始文件重新生成骨架，再把每个 token
# 原位替换为译文，其余内容(脚本/时间戳/样式)原样保留。
_EMBED_TOKEN = "\x02ETS{}\x02"  # 双端控制字符包裹，原文几乎不会出现

# Ren'Py 引号字符串字面量（支持多行与 \" 转义）
_RPY_STR_RE = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')')


def _tokenize_rpy(text: str) -> tuple[str, list[str]]:
    """返回 (带 token 的骨架, 按顺序的原文本列表)。

    保留字符串两侧的引号，只把引号内的内容替换为 token，
    这样译文回填后结构仍是合法的 Ren'Py 字符串字面量。
    """
    texts: list[str] = []
    counter = [0]

    def _replace(m: re.Match) -> str:
        counter[0] += 1
        raw = m.group(0)
        quote = raw[0]
        texts.append(raw[1:-1])  # 不含引号的内容
        return quote + _EMBED_TOKEN.format(counter[0]) + quote

    skeleton = _RPY_STR_RE.sub(_replace, text)
    return skeleton, texts


def _tokenize_srt(text: str) -> tuple[str, list[str]]:
    """返回 (带 token 的骨架, 按顺序的原文文本块列表)。"""
    lines = text.splitlines()
    out: list[str] = []
    texts: list[str] = []
    counter = [0]
    i = 0
    n = len(lines)
    while i < n:
        cur = lines[i]
        if cur.strip().isdigit() and i + 1 < n and "-->" in lines[i + 1]:
            out.append(cur)
            out.append(lines[i + 1])
            j = i + 2
            body: list[str] = []
            while j < n and lines[j].strip():
                body.append(lines[j])
                j += 1
            if body:
                counter[0] += 1
                texts.append("\n".join(body))
                out.append(_EMBED_TOKEN.format(counter[0]))
            else:
                out.append("")
            out.append("")  # 保留时间行后与下一条之间的空行分隔
            i = j
            while i < n and not lines[i].strip():
                i += 1
        else:
            out.append(cur)
            i += 1
    return "\n".join(out), texts


def _tokenize_ass(text: str) -> tuple[str, list[str]]:
    """返回 (带 token 的骨架, 按顺序的原文 Text 列表)。"""
    lines: list[str] = []
    texts: list[str] = []
    counter = [0]
    for line in text.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) == 10:
                counter[0] += 1
                token = _EMBED_TOKEN.format(counter[0])
                texts.append(parts[9])
                parts[9] = token
                lines.append(",".join(parts))
                continue
        lines.append(line)
    return "\n".join(lines), texts


def _parse_rpy(data: bytes) -> dict[str, str]:
    """Ren'Py 视觉小说脚本（galgame）。提取所有引号字符串字面量，token 占位。"""
    _, texts = _tokenize_rpy(decode_text(data))
    return {_EMBED_TOKEN.format(i + 1): t for i, t in enumerate(texts)}


def _parse_srt(data: bytes) -> dict[str, str]:
    """SRT 字幕。提取每条字幕的文本块，token 占位。"""
    _, texts = _tokenize_srt(decode_text(data))
    return {_EMBED_TOKEN.format(i + 1): t for i, t in enumerate(texts)}


def _parse_ass(data: bytes) -> dict[str, str]:
    """ASS/SSA 字幕。提取 Dialogue 行 Text 字段，token 占位。"""
    _, texts = _tokenize_ass(decode_text(data))
    return {_EMBED_TOKEN.format(i + 1): t for i, t in enumerate(texts)}


def _parse_csv(data: bytes) -> dict[str, str]:
    """CSV 逗号分隔，取前两列 key,value（表头/列数不固定则只取两列的简单形式）。"""
    text = decode_text(data)
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "," in stripped:
            key, _, value = stripped.partition(",")
            key = key.strip().strip('"')
            value = value.strip().strip('"')
            if key:
                result[key] = value
    return result


def _parse_properties(data: bytes) -> dict[str, str]:
    """Java .properties：key=value（支持 : / =，忽略 # 与 ! 注释）。"""
    text = decode_text(data)
    result: dict[str, str] = {}
    key_re = re.compile(r"^([A-Za-z0-9_\.\-]+)\s*[:=]\s*(.*)$")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            continue
        m = key_re.match(stripped)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def _parse_po(data: bytes) -> dict[str, str]:
    """GNU gettext .po：对每条 msgid，映射为「待翻译源文本」。

    po 语义：msgid 是源文本（英文），msgstr 是译文。
    因此返回 {msgid: msgid}（未翻译项以原文为待译值，已翻译项保留 msgstr），
    这样流水线会翻译源文本并写回 msgstr。多行片段会拼接。跳过包头。
    """
    text = decode_text(data)
    result: dict[str, str] = {}
    lines = text.splitlines()
    n = len(lines)
    i = 0

    def _gather(lno: int, prefix: str) -> tuple[str, int]:
        seg = ""
        m = re.match(rf'{re.escape(prefix)}"(.*)"\s*$', lines[lno])
        if m:
            seg = m.group(1).replace('\\"', '"').replace("\\n", "\n")
        nxt = lno + 1
        while nxt < n and lines[nxt].strip().startswith('"'):
            seg += lines[nxt].strip()[1:-1].replace('\\"', '"').replace("\\n", "\n")
            nxt += 1
        return seg, nxt

    while i < n:
        if lines[i].strip().startswith("msgid "):
            msgid, i = _gather(i, "msgid ")
            while i < n and not lines[i].strip().startswith("msgstr"):
                i += 1
            if i >= n:
                break
            msgstr, i = _gather(i, "msgstr ")
            # 跳过包头（msgid 为空）与无源文本的项
            if msgid and msgid not in result:
                result[msgid] = msgstr if msgstr else msgid
        else:
            i += 1
    return result


def _parse_strings(data: bytes) -> dict[str, str]:
    """Apple .strings（macOS/iOS）："key" = "value"; 每行一条。"""
    text = decode_text(data)
    result: dict[str, str] = {}
    key_re = re.compile(r'^\s*"([^"]+)"\s*=\s*"(.*)"\s*;\s*$')
    for line in text.splitlines():
        m = key_re.match(line)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def _parse_resx(data: bytes) -> dict[str, str]:
    """.NET .resx：XML <data name="key"><value>v</value></data>。"""
    text = decode_text(data)
    result: dict[str, str] = {}
    for m in re.finditer(r"<data[^>]*?name=\"([^\"]+)\"[^>]*>(.*?)</data>", text, re.S):
        key = m.group(1)
        v = m.group(2)
        vm = re.search(r"<value>(.*?)</value>", v, re.S)
        result[key] = vm.group(1) if vm else ""
    return result


def _parse_xliff(data: bytes) -> dict[str, str]:
    """XLIFF/XLIFF 2：<trans-unit id="…"><source>…</source><target>…</target></trans-unit>。"""
    text = decode_text(data)
    result: dict[str, str] = {}
    for m in re.finditer(r"<trans-unit[^>]*>(.*?)</trans-unit>", text, re.S):
        unit = m.group(1)
        key_m = re.search(r'<source[^>]*>(.*?)</source>', unit, re.S)
        tgt_m = re.search(r'<target[^>]*>(.*?)</target>', unit, re.S)
        if key_m:
            src = key_m.group(1)
            result[src] = tgt_m.group(1) if tgt_m else ""
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
    "vdf": _parse_vdf,
    "ini": _parse_ini,
    "xml": _parse_xml,
    "yaml": _parse_yaml,
    "sii": _parse_sii,
    "tsv": _parse_tsv,
    "csv": _parse_csv,
    "properties": _parse_properties,
    "po": _parse_po,
    "strings": _parse_strings,
    "resx": _parse_resx,
    "xliff": _parse_xliff,
    "rpy": _parse_rpy,
    "srt": _parse_srt,
    "ass": _parse_ass,
}


class TextParser:
    """多格式文本解析器。"""

    @classmethod
    def parse(cls, data: bytes, fmt: str) -> dict[str, str]:
        parser = _PARSERS.get(fmt)
        if parser is None:
            raise ValueError(f"不支持的格式: {fmt!r}")
        return parser(data)

    @staticmethod
    def looks_like_vdf(data: bytes) -> bool:
        """按内容嗅探是否为 Valve VDF 语言文件（`"key" "value"` 形式），支持 UTF-16。"""
        text = decode_text(data)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return False
        head = lines[0]
        if head == '"lang"' or head in ("{", '"lang" {'):
            kv_lines = sum(
                1 for l in lines if re.match(r'^"[^"]+"\s+".*"', l)
            )
            return kv_lines > 3
        return False

    @classmethod
    def guess_format_from_path(cls, path: Path, data: bytes | None = None) -> str:
        ext = path.suffix.lower()
        if ext == ".sii":
            return "sii"
        if ext == ".lang":
            return "lang"
        if ext == ".tsv":
            return "tsv"
        if ext in (".csv",):
            return "csv"
        if ext in (".properties",):
            return "properties"
        if ext in (".po", ".pot"):
            return "po"
        if ext in (".strings",):
            return "strings"
        if ext in (".resx",):
            return "resx"
        if ext in (".xliff", ".xlf"):
            return "xliff"
        if ext == ".rpy":
            return "rpy"
        if ext == ".srt":
            return "srt"
        if ext in (".ass", ".ssa"):
            return "ass"
        if ext == ".txt" and data is not None and cls.looks_like_vdf(data):
            return "vdf"
        if ext in (".json", ".txt", ".ini", ".xml", ".yaml", ".yml"):
            return "yaml" if ext == ".yml" else ext.lstrip(".")
        return "txt"
