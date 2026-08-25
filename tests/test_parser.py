# -*- coding: utf-8 -*-
"""parser.py 单元测试 — 7 种格式的解析与反序列化。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from game_translator_mcp.parser import TextParser, ParseError


class TestParseJSON:
    def test_basic(self):
        data = json.dumps({"item.stick": "Stick", "block.grass": "Grass"}).encode()
        result = TextParser.parse(data, "json")
        assert result == {"item.stick": "Stick", "block.grass": "Grass"}

    def test_nested_values_toplevel_only(self):
        data = json.dumps({"key": "value", "nested": {"a": "b"}}).encode()
        result = TextParser.parse(data, "json")
        # nested dict value is coerced to string by str()
        assert result["key"] == "value"
        assert "nested" in result

    def test_empty_object(self):
        result = TextParser.parse(b"{}", "json")
        assert result == {}

    def test_invalid_json_raises(self):
        with pytest.raises(ParseError):
            TextParser.parse(b"{bad json", "json")

    def test_array_toplevel_raises(self):
        with pytest.raises(ParseError):
            TextParser.parse(b'["a", "b"]', "json")


class TestParseLang:
    def test_basic(self):
        data = b"title.multiline=Test\n\ngui.cancel=Cancel"
        result = TextParser.parse(data, "lang")
        assert result["title.multiline"] == "Test"
        assert result["gui.cancel"] == "Cancel"

    def test_skips_comments(self):
        data = b"# this is a comment\nkey=value\n## another comment"
        result = TextParser.parse(data, "lang")
        assert result == {"key": "value"}

    def test_empty_lines_ignored(self):
        data = b"\n\nkey=val\n\n"
        result = TextParser.parse(data, "lang")
        assert result == {"key": "val"}

    def test_value_with_equals(self):
        data = b"a=b=c=d"
        result = TextParser.parse(data, "lang")
        assert result["a"] == "b=c=d"

    def test_invalid_key_skipped(self):
        data = b"123invalid=value"
        result = TextParser.parse(data, "lang")
        assert result == {}


class TestParseTxt:
    def test_key_value(self):
        data = b"hello=world\nfoo=bar"
        result = TextParser.parse(data, "txt")
        assert result["hello"] == "world"
        assert result["foo"] == "bar"

    def test_plain_text_lines(self):
        data = b"Hello world\nSecond line\n"
        result = TextParser.parse(data, "txt")
        assert "line_0" in result
        assert "line_1" in result

    def test_comments_skipped(self):
        data = b"# comment\nkey=value\n# another"
        result = TextParser.parse(data, "txt")
        assert result == {"key": "value"}


class TestParseINI:
    def test_basic(self):
        data = b"[strings]\nhello=world\n[other]\nfoo=bar"
        result = TextParser.parse(data, "ini")
        assert result == {"strings.hello": "world", "other.foo": "bar"}

    def test_default_section(self):
        data = b"key=value\n[section]\nkey2=val2"
        result = TextParser.parse(data, "ini")
        assert result["key"] == "value"
        assert result["section.key2"] == "val2"

    def test_comments_skipped(self):
        data = b"; comment\n# comment\nclean=yes"
        result = TextParser.parse(data, "ini")
        assert result == {"clean": "yes"}

    def test_value_with_spaces(self):
        data = b"key = hello world "
        result = TextParser.parse(data, "ini")
        assert result["key"] == "hello world"


class TestParseXML:
    def test_string_elements(self):
        data = (
            b'<?xml version="1.0"?><resources>'
            b'<string name="greeting">Hello</string>'
            b'<string name="farewell">Bye</string>'
            b'</resources>'
        )
        result = TextParser.parse(data, "xml")
        assert result["string.greeting"] == "Hello"
        assert result["string.farewell"] == "Bye"

    def test_self_closing_string(self):
        data = b'<string name="empty"/>'
        result = TextParser.parse(data, "xml")
        assert result["string.empty"] == ""

    def test_no_match_empty(self):
        result = TextParser.parse(b"<html><body></body></html>", "xml")
        assert result == {}


class TestParseYAML:
    def test_basic(self):
        pytest.importorskip("yaml")
        data = b"greeting: Hello\nfarewell: Bye\n"
        result = TextParser.parse(data, "yaml")
        assert result == {"greeting": "Hello", "farewell": "Bye"}

    def test_nested(self):
        pytest.importorskip("yaml")
        data = b"menu:\n  coffee: Coffee\n  tea: Tea\n"
        result = TextParser.parse(data, "yaml")
        assert result["menu.coffee"] == "Coffee"
        assert result["menu.tea"] == "Tea"

    def test_list_items(self):
        pytest.importorskip("yaml")
        data = b"items:\n  - Apple\n  - Banana\n"
        result = TextParser.parse(data, "yaml")
        assert result["items.[0]"] == "Apple"
        assert result["items.[1]"] == "Banana"

    def test_invalid_toplevel_raises(self):
        pytest.importorskip("yaml")
        with pytest.raises(ParseError):
            TextParser.parse(b"- item1\n- item2\n", "yaml")

    def test_yaml_unavailable_returns_empty(self):
        import game_translator_mcp.parser as parser_mod
        orig_has_yaml = parser_mod._HAS_YAML
        parser_mod._HAS_YAML = False
        try:
            result = TextParser.parse(b"a: b", "yaml")
            assert result == {}
        finally:
            parser_mod._HAS_YAML = orig_has_yaml


class TestParseSII:
    def test_basic(self):
        data = b'Name="Hello"\nValue="42"\n'
        result = TextParser.parse(data, "sii")
        assert result == {"Name": "Hello", "Value": "42"}

    def test_empty_value(self):
        data = b'Key=""\n'
        result = TextParser.parse(data, "sii")
        assert result == {"Key": ""}

    def test_skips_non_matching_lines(self):
        data = b'Good="yes"\nsome random text\nAnother="no"\n'
        result = TextParser.parse(data, "sii")
        assert result == {"Good": "yes", "Another": "no"}


class TestParseTSV:
    def test_basic(self):
        data = b"MAIN.PRIVATE_GAME\tPrivate Game\nMAIN.PUBLIC_GAME\tPublic Game\n"
        result = TextParser.parse(data, "tsv")
        assert result == {"MAIN.PRIVATE_GAME": "Private Game", "MAIN.PUBLIC_GAME": "Public Game"}

    def test_value_with_tabs_and_spaces(self):
        data = b"KEY\tHello World  \nKEY2\tValue2\n"
        result = TextParser.parse(data, "tsv")
        assert result == {"KEY": "Hello World", "KEY2": "Value2"}

    def test_skips_comments(self):
        data = b"# comment\nKEY\tValue\n# another\n"
        result = TextParser.parse(data, "tsv")
        assert result == {"KEY": "Value"}


class TestGuessFormat:
    def test_known_extensions(self):
        assert TextParser.guess_format_from_path(Path("a.json")) == "json"
        assert TextParser.guess_format_from_path(Path("a.lang")) == "lang"
        assert TextParser.guess_format_from_path(Path("a.txt")) == "txt"
        assert TextParser.guess_format_from_path(Path("a.ini")) == "ini"
        assert TextParser.guess_format_from_path(Path("a.xml")) == "xml"
        assert TextParser.guess_format_from_path(Path("a.yaml")) == "yaml"
        assert TextParser.guess_format_from_path(Path("a.yml")) == "yaml"
        assert TextParser.guess_format_from_path(Path("a.sii")) == "sii"
        assert TextParser.guess_format_from_path(Path("a.tsv")) == "tsv"

    def test_unknown_extension_defaults_to_txt(self):
        assert TextParser.guess_format_from_path(Path("a.dat")) == "txt"


class TestUnsupportedFormat:
    def test_raises_valueerror(self):
        with pytest.raises(ValueError, match="不支持的格式"):
            TextParser.parse(b"data", "binary")
