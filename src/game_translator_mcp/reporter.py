# -*- coding: utf-8 -*-
"""汉化报告生成器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileResult:
    path: str
    format: str
    status: str               # "success" | "skipped" | "failed" | "unsupported"
    entries_total: int = 0
    entries_translated: int = 0
    message: str = ""


class ReportGenerator:
    def generate(self, results: list[FileResult], target_name: str = "") -> str:
        ok = [r for r in results if r.status == "success"]
        skipped = [r for r in results if r.status == "skipped"]
        failed = [r for r in results if r.status == "failed"]
        unsupported = [r for r in results if r.status == "unsupported"]

        lines = [
            f"{'='*50}",
            f"  汉化报告 — {target_name or '游戏目录'}",
            f"{'='*50}",
            f"总文件数：{len(results)}",
            f"  ✅ 成功：{len(ok)}",
            f"  ⏭️  跳过：{len(skipped)}",
            f"  ❌ 失败：{len(failed)}",
            f"  🚫 不支持：{len(unsupported)}",
            "",
        ]

        total_entries = sum(r.entries_total for r in results)
        translated_entries = sum(r.entries_translated for r in results)
        lines.append(f"  总词条数：{total_entries}")
        lines.append(f"  已翻译：  {translated_entries}")
        lines.append("")

        if ok:
            lines.append("── 成功文件 ──")
            for r in ok:
                lines.append(f"  ✅ {r.path}  ({r.format}) {r.entries_translated} 条")
            lines.append("")

        if skipped:
            lines.append("── 跳过文件 ──")
            for r in skipped:
                lines.append(f"  ⏭️  {r.path}  — {r.message}")
            lines.append("")

        if failed:
            lines.append("── 失败文件 ──")
            for r in failed:
                lines.append(f"  ❌ {r.path}  — {r.message}")
            lines.append("")

        if unsupported:
            lines.append("── 不支持格式 ──")
            for r in unsupported:
                lines.append(f"  🚫 {r.path}  — {r.message}")

        return "\n".join(lines)
