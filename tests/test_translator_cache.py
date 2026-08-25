# -*- coding: utf-8 -*-
"""translator.py 缓存机制单元测试（不依赖真实 API）。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from game_translator_mcp.translator import TranslationCache, TranslConfig


class TestTranslationCache:
    def test_hash_deterministic(self):
        h1 = TranslationCache._hash_key("mod", "key", "value")
        h2 = TranslationCache._hash_key("mod", "key", "value")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        h1 = TranslationCache._hash_key("mod", "key", "value1")
        h2 = TranslationCache._hash_key("mod", "key", "value2")
        assert h1 != h2

    def test_persist_and_reload(self, tmp_path: Path):
        cache_file = tmp_path / "cache.json"
        cache = TranslationCache(cache_file)
        cache.set("mod", "k1", "v1", "翻译一")
        cache.set("mod", "k2", "v2", "翻译二")
        del cache

        cache2 = TranslationCache(cache_file)
        assert cache2.get("mod", "k1", "v1") == "翻译一"
        assert cache2.get("mod", "k2", "v2") == "翻译二"
        assert cache2.get("mod", "k1", "wrong") is None

    def test_get_miss_returns_none(self, tmp_path: Path):
        cache = TranslationCache(tmp_path / "empty.json")
        assert cache.get("mod", "key", "val") is None

    def test_corrupted_cache_file_ignored(self, tmp_path: Path):
        cache_file = tmp_path / "bad.json"
        cache_file.write_text("not valid json {{{")
        cache = TranslationCache(cache_file)
        assert cache.get("mod", "key", "val") is None

    def test_flush_writes_to_disk(self, tmp_path: Path):
        cache_file = tmp_path / "flush.json"
        cache = TranslationCache(cache_file)
        cache.set("m", "k", "v", "t")
        cache.flush()
        loaded = json.loads(cache_file.read_text())
        assert loaded[TranslationCache._hash_key("m", "k", "v")] == "t"


class TestTranslConfig:
    def test_defaults(self):
        cfg = TranslConfig()
        assert cfg.dashscope_api_key == ""
        assert cfg.deepseek_api_key == ""
        assert cfg.qwen_model == "qwen-plus"
        assert cfg.batch_size == 15
        assert cfg.use_deepseek_fallback is True
        assert cfg.agnes_api_key == ""
        assert "apihub.agnes-ai.com" in cfg.agnes_base_url
        assert cfg.agnes_model == "agnes-2.5-flash"

    def test_from_env(self, monkeypatch: pytest.FixtureRequest):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
        cfg = TranslConfig()
        assert cfg.dashscope_api_key == "sk-test"
        assert cfg.deepseek_api_key == "ds-test"

    def test_agnes_from_env(self, monkeypatch: pytest.FixtureRequest):
        monkeypatch.setenv("AGNES_API_KEY", "ag-test")
        monkeypatch.setenv("AGNES_BASE_URL", "https://example.com/v1")
        monkeypatch.setenv("AGNES_MODEL", "custom-model")
        cfg = TranslConfig()
        assert cfg.agnes_api_key == "ag-test"
        assert cfg.agnes_base_url == "https://example.com/v1"
        assert cfg.agnes_model == "custom-model"

    def test_batch_size_override(self, monkeypatch: pytest.FixtureRequest):
        monkeypatch.setenv("BATCH_SIZE", "30")
        cfg = TranslConfig()
        assert cfg.batch_size == 30
