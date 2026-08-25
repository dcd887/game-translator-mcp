# -*- coding: utf-8 -*-
"""翻译模块：封装通义千问 / DeepSeek API 调用，支持批量翻译和本地缓存。

优先使用通义千问（阿里云百炼），备选 DeepSeek。
相同 (modid, key, value) 的条目通过 SHA-256 哈希缓存，避免重复消耗 token。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from openai import OpenAI


class TranslConfig(BaseSettings):
    """翻译配置。"""
    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    qwen_model: str = "qwen-plus"
    deepseek_model: str = "deepseek-chat"
    batch_size: int = 15
    output_dir: str = "translated_output"
    use_deepseek_fallback: bool = True
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


class TranslationCache(BaseModel):
    """基于 SHA-256 的本地缓存，持久化到 JSON 文件。"""

    cache_path: Path
    data: dict[str, str] = Field(default_factory=dict)

    def __init__(self, cache_path: Path | str) -> None:
        super().__init__(cache_path=Path(cache_path).resolve())
        self._load()

    def _load(self) -> None:
        if self.cache_path.exists():
            try:
                self.data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _hash_key(modid: str, key: str, value: str) -> str:
        raw = f"{modid}::{key}::{value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, modid: str, key: str, value: str) -> Optional[str]:
        h = self._hash_key(modid, key, value)
        return self.data.get(h)

    def set(self, modid: str, key: str, value: str, translation: str) -> None:
        h = self._hash_key(modid, key, value)
        self.data[h] = translation
        self._save()

    def flush(self) -> None:
        self._save()


SYSTEM_PROMPT = (
    "你是一位专业的游戏汉化工程师。"
    "请将以下游戏文本从英文翻译成简洁、自然的简体中文。\n"
    "只输出翻译结果，不要解释、不要额外文字。\n"
    "格式：每行一个，用英文冒号分隔 key 和翻译值。\n"
    "例如：item.stick:木棍\nblock.grass:草地"
)


class Translator:
    """调用 LLM API 进行批量翻译，带缓存。"""

    def __init__(self, config: TranslConfig, cache: TranslationCache) -> None:
        if not config.dashscope_api_key and not config.deepseek_api_key:
            raise ValueError(
                "未配置 API Key。请设置 DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY。"
            )
        self.config = config
        self.cache = cache
        self._client: Optional[OpenAI] = None
        self._fallback_client: Optional[OpenAI] = None
        self._init_clients()

    def _init_clients(self) -> None:
        if self.config.dashscope_api_key:
            self._client = OpenAI(
                api_key=self.config.dashscope_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        if self.config.deepseek_api_key:
            self._fallback_client = OpenAI(
                api_key=self.config.deepseek_api_key,
                base_url="https://api.deepseek.com/v1",
            )

    def _call_llm(
        self,
        modid: str,
        entries: dict[str, str],
    ) -> dict[str, str]:
        """调用 LLM 翻译一批条目。"""
        items = list(entries.items())
        prompt_lines = [f"{k}: {v}" for k, v in items]
        prompt = "\n".join(prompt_lines)

        system_msg = {"role": "system", "content": SYSTEM_PROMPT}
        user_msg = {"role": "user", "content": f"翻译以下 {len(items)} 条游戏文本：\n{prompt}"}

        client = self._client
        model = self.config.qwen_model
        if client is None and self._fallback_client is not None:
            client = self._fallback_client
            model = self.config.deepseek_model

        if client is None:
            raise RuntimeError("没有可用的 LLM 客户端")

        response = client.chat.completions.create(
            model=model,
            messages=[system_msg, user_msg],
            temperature=0.1,
        )
        text = response.choices[0].message.content or ""
        return self._parse_llm_response(text, items)

    @staticmethod
    def _parse_llm_response(text: str, items: list[tuple[str, str]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in text.strip().splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if key and val:
                result[key] = val
        # 若模型返回格式不匹配，按顺序映射
        if len(result) != len(items):
            values = [v for _, v in items]
            parsed = [r for r in result.values()]
            for i, v in enumerate(values):
                if v in parsed and i < len(parsed):
                    k = items[i][0]
                    if k not in result:
                        result[k] = parsed[i]
        return result

    def translate_batch(
        self,
        modid: str,
        entries: dict[str, str],
    ) -> dict[str, str]:
        """翻译一批条目，命中缓存则跳过。"""
        if not entries:
            return {}

        cached: dict[str, str] = {}
        missing: dict[str, str] = {}
        for k, v in entries.items():
            hit = self.cache.get(modid, k, v)
            if hit is not None:
                cached[k] = hit
            else:
                missing[k] = v

        if not missing:
            return cached

        results: dict[str, str] = {}
        items = list(missing.items())
        for i in range(0, len(items), self.config.batch_size):
            batch = dict(items[i:i + self.config.batch_size])
            translated = self._call_llm(modid, batch)
            for k, v in batch.items():
                t = translated.get(k)
                if t:
                    results[k] = t
                    self.cache.set(modid, k, v, t)

        results.update(cached)
        return results
