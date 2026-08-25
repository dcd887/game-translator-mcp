# -*- coding: utf-8 -*-
"""scanner.py / writer.py / reporter.py 单元测试。"""
from __future__ import annotations

import json
import asyncio
import tempfile
from pathlib import Path

import pytest

from game_translator_mcp.scanner import TranslatableFile, scan_directory, _detect_format, SKIP_PATTERNS
from game_translator_mcp.writer import GameWriter, WriteError
from game_translator_mcp.reporter import FileResult, ReportGenerator
from game_translator_mcp.mcp_server import preview_translate_game


# ── scanner ──────────────────────────────────────────────────────────────────

class TestDetectFormat:
    def test_known_extensions(self):
        assert _detect_format(Path("a.json")) == "json"
        assert _detect_format(Path("a.lang")) == "lang"
        assert _detect_format(Path("a.txt")) == "txt"
        assert _detect_format(Path("a.ini")) == "ini"
        assert _detect_format(Path("a.xml")) == "xml"
        assert _detect_format(Path("a.yaml")) == "yaml"
        assert _detect_format(Path("a.yml")) == "yaml"
        assert _detect_format(Path("a.sii")) == "sii"
        assert _detect_format(Path("a.tsv")) == "tsv"

    def test_unknown_extension(self):
        assert _detect_format(Path("a.exe")) is None
        assert _detect_format(Path("a.png")) is None


class TestScanDirectory:
    def _make_files(self, tmpdir: Path, files: dict[str, bytes]) -> Path:
        for rel, content in files.items():
            p = tmpdir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        return tmpdir

    def test_finds_json_and_lang(self, tmp_path: Path):
        self._make_files(tmp_path, {
            "assets/game/lang/en_us.json": json.dumps({"item.stick": "Stick"}).encode(),
            "assets/game/lang/zh_cn.json": json.dumps({"item.stick": "木棍"}).encode(),
            "strings.lang": b"title=Test\ngui.ok=OK\n",
        })
        results = scan_directory(tmp_path)
        formats = {r.format for r in results}
        assert "json" in formats
        assert "lang" in formats

    def test_skips_binary_files(self, tmp_path: Path):
        self._make_files(tmp_path, {
            "assets/textures/block.png": b"\x89PNG\r\n",
            "assets/audio/bgm.mp3": b"ID3",
            "config.json": json.dumps({"a": "1"}).encode(),
        })
        results = scan_directory(tmp_path)
        assert len(results) == 1
        assert results[0].path.name == "config.json"

    def test_skips_large_files(self, tmp_path: Path):
        big = b"x" * (11 * 1024 * 1024)  # 11 MB
        self._make_files(tmp_path, {"big.json": big})
        results = scan_directory(tmp_path)
        assert len(results) == 0

    def test_large_file_included_with_custom_threshold(self, tmp_path: Path):
        big = b"x" * (11 * 1024 * 1024)  # 11 MB（超过默认 10MB）
        self._make_files(tmp_path, {"huge.json": big})
        # 默认阈值下会被跳过
        assert len(scan_directory(tmp_path)) == 0
        # 传参调高阈值后不再跳过（超过 11MB 才跳过）
        assert len(scan_directory(tmp_path, max_size_bytes=12 * 1024 * 1024)) == 1

    def test_env_var_threshold(self, tmp_path: Path, monkeypatch):
        big = b"x" * (11 * 1024 * 1024)  # 11 MB
        self._make_files(tmp_path, {"huge.json": big})
        monkeypatch.setenv("SCAN_MAX_SIZE_MB", "12")
        assert len(scan_directory(tmp_path)) == 1

    def test_skips_texture_dir(self, tmp_path: Path):
        self._make_files(tmp_path, {
            "assets/textures/font.png": b"notreal",
            "assets/textures/block.png": b"notreal",
            "config.json": json.dumps({"a": "1"}).encode(),
        })
        results = scan_directory(tmp_path)
        for r in results:
            assert "textures" not in str(r.path)

    def test_nonexistent_dir_raises(self):
        with pytest.raises(ValueError):
            scan_directory("/nonexistent/path/that/does/not/exist")

    def test_line_count(self, tmp_path: Path):
        data = b"a=1\nb=2\nc=3\n"
        self._make_files(tmp_path, {"test.lang": data})
        results = scan_directory(tmp_path)
        assert len(results) == 1
        assert results[0].line_count == 3  # 3 newlines


# ── writer ───────────────────────────────────────────────────────────────────

class TestWriterSerialize:
    @pytest.mark.parametrize("fmt,expected_key", [
        ("json", "key"),
        ("lang", "key"),
        ("txt", "key"),
        ("ini", "key"),
        ("xml", "string"),
        ("sii", "key"),
        ("tsv", "key"),
    ])
    def test_roundtrip_json(self, fmt, expected_key):
        entries = {"key": "value", "hello": "world"}
        data = GameWriter._serialize(entries, fmt)
        assert isinstance(data, bytes)
        # verify it decodes
        text = data.decode("utf-8")
        assert len(text) > 0

    def test_json_serialization(self):
        entries = {"a": "1", "b": "2"}
        data = GameWriter._serialize(entries, "json")
        parsed = json.loads(data)
        assert parsed == entries

    def test_lang_serialization(self):
        entries = {"a": "你好", "b": "世界"}
        data = GameWriter._serialize(entries, "lang")
        lines = data.decode().strip().split("\n")
        assert "a=你好" in lines
        assert "b=世界" in lines

    def test_xml_serialization(self):
        entries = {"greeting": "Hello"}
        data = GameWriter._serialize(entries, "xml")
        text = data.decode()
        assert '<?xml version="1.0"' in text
        assert 'name="greeting"' in text
        assert ">Hello<" in text

    def test_sii_serialization(self):
        entries = {"Key": "Value"}
        data = GameWriter._serialize(entries, "sii")
        text = data.decode()
        assert 'Key="Value"' in text

    def test_unsupported_format_raises(self):
        with pytest.raises(ValueError, match="不支持的格式"):
            GameWriter._serialize({"a": "1"}, "binary")


class TestWriterWrite:
    def test_copy_mode_creates_output(self, tmp_path: Path):
        src_dir = tmp_path / "game" / "assets" / "game" / "lang"
        src_dir.mkdir(parents=True)
        src_file = src_dir / "en_us.json"
        src_file.write_bytes(json.dumps({"a": "1"}).encode())

        info = TranslatableFile(
            path=src_file,
            format="json",
            line_count=1,
            raw_data=b'{"a":"1"}',
        )
        out_root = tmp_path / "output"
        writer = GameWriter(out_root, mode="copy", source_root=tmp_path)
        out = writer.write(info, {"a": "一"}, "json")
        expected = str(out_root / "game" / "assets" / "game" / "lang" / "en_us.json")
        assert out == expected
        assert Path(out).exists()

    def test_inplace_mode_overwrites(self, tmp_path: Path):
        orig = tmp_path / "data.json"
        orig.write_bytes(json.dumps({"a": "1"}).encode())
        info = TranslatableFile(
            path=orig,
            format="json",
            line_count=1,
            raw_data=b'{"a":"1"}',
        )
        writer = GameWriter(tmp_path, mode="inplace")
        out = writer.write(info, {"a": "一"}, "json")
        assert out == str(orig)
        restored = json.loads(orig.read_text())
        assert restored == {"a": "一"}

    def test_count_entries(self):
        n = GameWriter.count_entries(json.dumps({"a": "1", "b": "2"}).encode(), "json")
        assert n == 2

    def test_count_entries_empty(self):
        n = GameWriter.count_entries(b"{}", "json")
        assert n == 0


# ── reporter ─────────────────────────────────────────────────────────────────

class TestReportGenerator:
    def test_all_success(self):
        results = [
            FileResult(path="a.json", format="json", status="success",
                       entries_total=5, entries_translated=5),
        ]
        report = ReportGenerator().generate(results, "TestGame")
        assert "TestGame" in report
        assert "✅ 成功：1" in report
        assert "总词条数：5" in report

    def test_mixed_results(self):
        results = [
            FileResult(path="ok.json", format="json", status="success", entries_total=3, entries_translated=3),
            FileResult(path="skip.lang", format="lang", status="skipped", entries_total=10, message="已有汉化输出，跳过"),
            FileResult(path="fail.xml", format="xml", status="failed", entries_total=0, message="网络错误"),
            FileResult(path="bad.sii", format="sii", status="unsupported", entries_total=0, message="不支持"),
        ]
        report = ReportGenerator().generate(results, "Mixed")
        assert "✅ 成功：1" in report
        assert "⏭️  跳过：1" in report
        assert "❌ 失败：1" in report
        assert "🚫 不支持：1" in report
        assert "skip.lang" in report
        assert "fail.xml" in report

    def test_empty_results(self):
        report = ReportGenerator().generate([], "Empty")
        assert "Empty" in report
        assert "总文件数：0" in report


# ── preview（--dry-run，零成本预览）────────────────────────────────────────────

class TestPreviewTranslate:
    def test_preview_reports_files_and_entries(self, tmp_path: Path):
        (tmp_path / "lang").mkdir()
        (tmp_path / "lang" / "en_us.json").write_bytes(
            json.dumps({"item.stick": "Stick", "item.iron": "Iron Ingot"}).encode()
        )
        (tmp_path / "lang" / "menu.lang").write_text("title=Test\ngui.ok=OK\n")

        result = json.loads(asyncio.run(preview_translate_game(str(tmp_path))))
        assert result["total_files"] == 2
        assert result["total_entries"] == 4
        assert result["formats"]["json"] == 1
        assert result["formats"]["lang"] == 1
        assert result["total_source_chars"] > 0
        assert result["estimated_tokens_rough"] >= 1
        # 预览绝不写文件、不产出 output 目录，也没有 token 消费字段
        assert "output_dir" not in result
        assert "preview" not in result or not result["preview"]

    def test_preview_nonexistent_dir(self, tmp_path: Path):
        result = json.loads(asyncio.run(preview_translate_game(str(tmp_path / "nope"))))
        assert "error" in result
