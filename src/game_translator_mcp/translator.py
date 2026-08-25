# -*- coding: utf-8 -*-
"""翻译模块：支持任意 OpenAI 兼容供应商的批量翻译 + 本地缓存。

核心设计：**不绑定任何特定供应商**。所有配置均从环境变量 / `.env` 读取，
完全由使用者自己提供 API Key、base_url 和模型名，项目在任何环境均可本地跑通。
每种供应商都是一个"别名"，别名只是对通用 OpenAI 兼容参数的预填（可被覆盖）。

优先级：custom（通用）> agnes > dashscope > deepseek。用户配置了哪个，就用哪个。

配置项（环境变量 / `.env`，见 `.env.example`）：
  - 通用（最灵活，推荐）：TRANSLATOR_API_KEY / TRANSLATOR_BASE_URL / TRANSLATOR_MODEL
  - agnes ai：AGNES_API_KEY / AGNES_BASE_URL / AGNES_MODEL
  - 通义千问：DASHSCOPE_API_KEY / QWEN_MODEL
  - DeepSeek（fallback）：DEEPSEEK_API_KEY / DEEPSEEK_MODEL

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
    """翻译配置：通用 OpenAI 兼容 + 各供应商别名。

    每种别名的 base_url/model 都给了默认值，仅在有对应 key 时才生效。
    若用户显式配置了通用项（custom），则以通用项为准。
    """
    # 通用 OpenAI 兼容配置（最灵活，优先）
    translator_api_key: str = ""
    translator_base_url: str = ""
    translator_model: str = ""
    # agnes ai 别名
    agnes_api_key: str = ""
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_model: str = "agnes-2.5-flash"
    # 通义千问 别名
    dashscope_api_key: str = ""
    qwen_model: str = "qwen-plus"
    # DeepSeek 别名（做 fallback）
    deepseek_api_key: str = ""
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
    """调用 LLM API 进行批量翻译，带缓存。

    供应商完全取决于用户配置的环境变量：自定义(custom) > agnes > dashscope > deepseek。
    不会强制使用任何一家。
    """

    def __init__(self, config: TranslConfig, cache: TranslationCache) -> None:
        self.config = config
        self.cache = cache
        self._primary: Optional[tuple[OpenAI, str]] = None   # (client, model)
        self._fallback: Optional[tuple[OpenAI, str]] = None  # (client, model)
        self._init_clients()
        if not self._primary:
            raise ValueError(
                "未配置可用的 API Key。请通过 `.env` 或环境变量至少设置一个供应商：\n"
                "  TRANSLATOR_API_KEY/BASE_URL/MODEL（通用，推荐）\n"
                "  AGNES_API_KEY / DASHSCOPE_API_KEY / DEEPSEEK_API_KEY"
            )

    def _init_clients(self) -> None:
        c = self.config

        # 通用 OpenAI 兼容配置优先（用户自定义供应商）
        if c.translator_api_key:
            self._primary = (
                OpenAI(api_key=c.translator_api_key, base_url=c.translator_base_url),
                c.translator_model,
            )
        elif c.agnes_api_key:
            self._primary = (
                OpenAI(api_key=c.agnes_api_key, base_url=c.agnes_base_url),
                c.agnes_model,
            )
        elif c.dashscope_api_key:
            self._primary = (
                OpenAI(api_key=c.dashscope_api_key,
                       base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
                c.qwen_model,
            )

        # DeepSeek 作为可选 fallback
        if c.use_deepseek_fallback and c.deepseek_api_key:
            self._fallback = (
                OpenAI(api_key=c.deepseek_api_key,
                       base_url="https://api.deepseek.com/v1"),
                c.deepseek_model,
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

        client, model = self._primary
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

        # 按「输出顺序」补齐所有未被键匹配命中的条目。模型常无法原样回显
        # 键（尤其嵌入 token 键如 rpy/srt/ass 的 \x02ETS1\x02），
        # 但输出行的顺序与请求一致，用顺序位置对齐更稳健。
        ordered = [
            line.partition(":")[2].strip()
            for line in text.splitlines()
            if ":" in line and line.partition(":")[2].strip()
        ]
        slot = 0
        for k, _ in items:
            if k in result:
                continue
            while slot < len(ordered) and not ordered[slot]:
                slot += 1
            if slot < len(ordered):
                result[k] = ordered[slot]
                slot += 1
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
