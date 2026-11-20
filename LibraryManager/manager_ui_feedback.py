"""Human-readable completion summaries for Manager UI tasks.

Pure formatting helpers: no Tk dependency and no file-system side effects.
"""
from __future__ import annotations

from typing import Any


def build_import_completion_summary(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return a compact, truthful summary for a completed IMPORT GUITAR task."""
    if not isinstance(result, dict):
        result = {}

    registry = result.get("registry")
    if not isinstance(registry, dict):
        registry = {}
    groups = registry.get("registered_by_format")
    if not isinstance(groups, dict):
        groups = {}

    errors = registry.get("errors")
    if not isinstance(errors, list):
        errors = []

    summary = {
        "operation": "IMPORT_GUITAR",
        "selected_sources": registry.get("selected_sources", 0),
        "copied_files": result.get("copied_files", 0),
        "copied_bytes": result.get("copied_bytes", 0),
        "registered_files": registry.get("registered_files", 0),
        "already_registered": registry.get("already_registered", 0),
        "audio_files": groups.get("AUDIO", 0),
        "sfz_files": groups.get("SFZ", 0),
        "archives": groups.get("ARCHIVE", 0),
        "other_review_required": groups.get("OTHER_REVIEW_REQUIRED", 0),
        "sfz_dependencies_found": registry.get("sfz_dependencies_found", 0),
        "sfz_dependencies_blocked": registry.get("sfz_dependencies_blocked", 0),
        "errors": len(errors),
        "copy_integrity": result.get("copy_integrity", "UNKNOWN"),
        "source_files_modified": result.get("source_files_modified", False),
        "source_files_moved": result.get("source_files_moved", False),
        "source_files_deleted": result.get("source_files_deleted", False),
    }

    size = max(0, int(summary["copied_bytes"] or 0))
    size_text = f"{size:,} bytes"
    lines = [
        f"Источников выбрано: {summary['selected_sources']}.",
        f"Скопировано и проверено: {summary['copied_files']} файлов ({size_text}).",
        (
            f"В реестр добавлено: {summary['registered_files']}; "
            f"уже было зарегистрировано: {summary['already_registered']}."
        ),
        (
            f"Аудио: {summary['audio_files']}; SFZ: {summary['sfz_files']}; "
            f"архивы: {summary['archives']}; прочие: {summary['other_review_required']}."
        ),
        f"Целостность копирования: {summary['copy_integrity']}.",
    ]
    if summary["archives"]:
        lines.append(
            "Архивы сохранены как исходные файлы и учтены в инвентаризации; "
            "автоматическая распаковка не выполняется."
        )
    if summary["sfz_dependencies_blocked"]:
        lines.append(
            f"SFZ: не разрешено зависимостей — {summary['sfz_dependencies_blocked']}; "
            "проверьте пути sample= / #include в отчёте."
        )
    if summary["errors"]:
        lines.append(f"Предупреждений импорта: {summary['errors']}; подробности записаны в реестр.")
    if (
        summary["source_files_modified"]
        or summary["source_files_moved"]
        or summary["source_files_deleted"]
    ):
        lines.append("ВНИМАНИЕ: отчёт импорта не подтверждает сохранность оригиналов.")
    else:
        lines.append("Исходные файлы не изменялись, не перемещались и не удалялись.")
    return summary, "  •  ".join(lines)
