# -*- coding: utf-8 -*-
"""MCP 服务器入口：暴露工具供 AI Agent 调用。

工具：
  - scan_game_directory   : 扫描目录，返回可翻译文件清单
  - translate_game        : 完整汉化流程（扫描 → 翻译 → 回写 → 报告）
  - dry_run_translate     : 预览翻译效果，不修改任何文件
  - list_steam_games      : 列出 Steam 库中包含可翻译文件的游戏
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from .translator import TranslConfig, TranslationCache, Translator
from .scanner import TranslatableFile, scan_directory
from .parser import TextParser
from .writer import GameWriter
from .reporter import ReportGenerator, FileResult
from .steam import discover_steam_games

mcp = FastMCP("game-translator-mcp")


class ScanResult(BaseModel):
    total_files: int
    total_entries: int
    files: list[dict[str, Any]]


class TranslateResult(BaseModel):
    total_files: int
    success: int
    skipped: int
    failed: int
    total_entries: int
    translated_entries: int
    output_dir: str
    report: str


# ============================================================
# 工具 1：scan_game_directory
# ============================================================
@mcp.tool()
async def scan_game_directory(
    directory: str,
    extensions: Optional[list[str]] = None,
    max_size_mb: Optional[float] = None,
) -> str:
    """扫描游戏目录，返回所有可翻译文件清单及文本量估算。

    Args:
        directory: 游戏安装目录或包含语言文件的目录路径
        extensions: 额外要扫描的文件扩展名列表（不含点号），默认扫描所有支持格式
        max_size_mb: 允许的最大文件大小（MB），超过则跳过（默认 10；部分游戏明文文件可能更大，可自行调高）
    Returns:
        JSON 字符串，包含文件列表、格式分布、总条目数
    """
    base = Path(directory).resolve()
    if not base.exists():
        return json.dumps({"error": f"目录不存在: {base}"}, ensure_ascii=False, indent=2)

    files = scan_directory(base, extensions=extensions,
                           max_size_bytes=int(max_size_mb * 1024 * 1024) if max_size_mb is not None else None)
    fmt_counts: dict[str, int] = {}
    total_entries = 0
    file_list = []
    for f in files:
        fmt_counts[f.format] = fmt_counts.get(f.format, 0) + 1
        try:
            entries = TextParser.parse(f.raw_data, f.format)
            n = len(entries)
        except Exception:
            n = f.line_count
        total_entries += n
        file_list.append({
            "path": str(f.path),
            "format": f.format,
            "lines": f.line_count,
            "entries_estimated": n,
        })

    result = ScanResult(
        total_files=len(files),
        total_entries=total_entries,
        files=file_list,
    )
    return result.model_dump_json(indent=2, ensure_ascii=False)


# ============================================================
# 工具 2：translate_game
# ============================================================
@mcp.tool()
async def translate_game(
    directory: str,
    modid: str = "game",
    batch_size: int = 15,
    force_retranslate: bool = False,
    backup: bool = True,
    game_name: str = "",
    max_size_mb: Optional[float] = None,
) -> str:
    """执行完整汉化流程：扫描 → 翻译 → 回写 → 生成报告。

    Args:
        directory: 游戏目录或模组 jar 包路径
        modid: 模组/游戏标识，用于缓存 key（默认 "game"）
        batch_size: 每批翻译条目数
        force_retranslate: 强制重新翻译（忽略缓存）
        backup: 回写前是否备份原文件
        game_name: 游戏名称，用于报告标题
        max_size_mb: 允许的最大文件大小（MB），超过则跳过（默认 10）
    Returns:
        汉化报告 JSON 字符串
    """
    target = Path(directory).resolve()
    if not target.exists():
        return json.dumps({"error": f"路径不存在: {target}"}, ensure_ascii=False, indent=2)

    try:
        import os
        from pydantic_settings import SettingsConfigDict
        config = TranslConfig(
            model_config=SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore"),
        )
        cache_path = Path.cwd() / "translator_cache.json"
        cache = TranslationCache(cache_path)
        translator = Translator(config, cache)
        writer = GameWriter(Path(config.output_dir), source_root=Path(target))
        reporter = ReportGenerator()

        files = scan_directory(target, max_size_bytes=int(max_size_mb * 1024 * 1024) if max_size_mb is not None else None)
        results: list[FileResult] = []
        total_entries = 0
        translated_entries = 0

        for f in files:
            try:
                entries = TextParser.parse(f.raw_data, f.format)
                if not entries:
                    results.append(FileResult(
                        path=str(f.path), format=f.format, status="skipped",
                        message="文件无有效文本条目",
                    ))
                    continue

                if not force_retranslate:
                    rel = f.path.relative_to(target) if f.path.is_relative_to(target) else f.path.name
                    existing = writer.output_root / rel
                    if existing.exists():
                        results.append(FileResult(
                            path=str(f.path), format=f.format, status="skipped",
                            entries_total=len(entries), message="已有汉化输出，跳过",
                        ))
                        translated_entries += len(entries)
                        continue

                translated = translator.translate_batch(modid, entries)
                out_path = writer.write(f, translated, f.format, backup=backup)
                n = len(translated)
                total_entries += len(entries)
                translated_entries += n
                results.append(FileResult(
                    path=str(f.path), format=f.format, status="success",
                    entries_total=len(entries), entries_translated=n,
                    message=f"已写入：{out_path}",
                ))
            except Exception as e:
                results.append(FileResult(
                    path=str(f.path), format=f.format, status="failed",
                    message=str(e),
                ))

        report_text = reporter.generate(results, game_name or target.name)
        summary = {
            "total_files": len(files),
            "success": sum(1 for r in results if r.status == "success"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "total_entries": total_entries,
            "translated_entries": translated_entries,
            "output_dir": str(writer.output_root),
            "report": report_text,
        }
        return json.dumps(summary, ensure_ascii=False, indent=2)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================
# 工具 3：preview_translate_game（零成本预览，不调 AI API）
# ============================================================
@mcp.tool()
async def preview_translate_game(directory: str, max_size_mb: Optional[float] = None) -> str:
    """（零成本）预览汉化范围：列出将被处理的文件、每种格式数量、总条目数与预估翻译量。

    只做扫描与解析，**不调用任何 AI 翻译 API、不消耗 token、不写文件**，
    用于在真正执行汉化前评估工作量与费用。

    Args:
        directory: 游戏目录或语言文件目录
        max_size_mb: 允许的最大文件大小（MB），超过则跳过（默认 10）
    Returns:
        JSON：文件清单 + 格式分布 + 总条目数 + 预估字符量/估算 token
    """
    base = Path(directory).resolve()
    if not base.exists():
        return json.dumps({"error": f"目录不存在: {base}"}, ensure_ascii=False, indent=2)

    files = scan_directory(base, max_size_bytes=int(max_size_mb * 1024 * 1024) if max_size_mb is not None else None)
    fmt_counts: dict[str, int] = {}
    total_entries = 0
    total_chars = 0
    file_list = []
    for f in files:
        fmt_counts[f.format] = fmt_counts.get(f.format, 0) + 1
        try:
            entries = TextParser.parse(f.raw_data, f.format)
            n = len(entries)
            total_chars += sum(len(v) for v in entries.values())
        except Exception:
            n = 0
        total_entries += n
        file_list.append({
            "path": str(f.path),
            "format": f.format,
            "entries_estimated": n,
        })

    # 粗略估算：英文约 4 字符/token，中文约 1 字符/token；给出量级参考
    est_tokens = max(1, round(total_chars / 4))
    summary = {
        "directory": str(base),
        "total_files": len(files),
        "total_entries": total_entries,
        "total_source_chars": total_chars,
        "estimated_tokens_rough": est_tokens,
        "formats": fmt_counts,
        "files": file_list,
        "note": "这是未调用 AI 的预览估算；实际 token 消耗以执行时供应商计费为准。",
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


# ============================================================
# 工具 3：dry_run_translate
# ============================================================
@mcp.tool()
async def dry_run_translate(
    directory: str,
    modid: str = "game",
    limit: int = 50,
    max_size_mb: Optional[float] = None,
) -> str:
    """预览翻译效果：解析文件但不实际修改任何内容，输出翻译预览。

    Args:
        directory: 游戏目录路径
        modid: 模组标识
        limit: 最多预览的条目数
        max_size_mb: 允许的最大文件大小（MB），超过则跳过（默认 10）
    Returns:
        JSON 预览结果，包含原文和翻译对比
    """
    target = Path(directory).resolve()
    if not target.exists():
        return json.dumps({"error": f"目录不存在: {target}"}, ensure_ascii=False, indent=2)

    try:
        config = TranslConfig()
        cache_path = Path.cwd() / "translator_cache.json"
        cache = TranslationCache(cache_path)
        translator = Translator(config, cache)

        files = scan_directory(target, max_size_bytes=int(max_size_mb * 1024 * 1024) if max_size_mb is not None else None)
        previews: list[dict] = []
        remaining = limit

        for f in files:
            if remaining <= 0:
                break
            try:
                entries = TextParser.parse(f.raw_data, f.format)
                sample = dict(list(entries.items())[:min(remaining, 20)])
                if sample:
                    translated = translator.translate_batch(modid, sample)
                    previews.append({
                        "file": str(f.path),
                        "format": f.format,
                        "samples": translated,
                    })
                    remaining -= len(sample)
            except Exception:
                continue

        return json.dumps({
            "preview_count": len(previews),
            "total_files_scanned": len(files),
            "samples": previews,
        }, ensure_ascii=False, indent=2)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================
# 工具 4：list_steam_games
# ============================================================
@mcp.tool()
async def list_steam_games() -> str:
    """列出 Steam 库中已安装且包含可翻译文件的游戏。"""
    games = discover_steam_games()
    return json.dumps({
        "game_count": len(games),
        "games": games,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    from .cli import cli_main
    cli_main()
