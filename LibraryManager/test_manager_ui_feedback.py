"""Regression tests for Manager task-completion feedback."""
from __future__ import annotations

import unittest

from manager_ui_feedback import build_import_completion_summary


class ImportCompletionSummaryTests(unittest.TestCase):
    def test_summary_reports_verified_copy_counts_and_archive_behavior(self):
        summary, detail = build_import_completion_summary({
            "copied_files": 7,
            "copied_bytes": 4096,
            "copy_integrity": "SHA256_VERIFIED",
            "source_files_modified": False,
            "source_files_moved": False,
            "source_files_deleted": False,
            "registry": {
                "selected_sources": 2,
                "registered_files": 7,
                "already_registered": 1,
                "registered_by_format": {
                    "AUDIO": 4,
                    "SFZ": 1,
                    "ARCHIVE": 2,
                },
                "sfz_dependencies_found": 12,
                "sfz_dependencies_blocked": 0,
                "errors": [],
            },
        })
        self.assertEqual(summary["copied_files"], 7)
        self.assertEqual(summary["audio_files"], 4)
        self.assertEqual(summary["sfz_files"], 1)
        self.assertEqual(summary["archives"], 2)
        self.assertEqual(summary["copy_integrity"], "SHA256_VERIFIED")
        self.assertIn("автоматическая распаковка не выполняется", detail)
        self.assertIn("не изменялись, не перемещались и не удалялись", detail)

    def test_summary_does_not_claim_successful_sfz_resolution_when_blocked(self):
        summary, detail = build_import_completion_summary({
            "copied_files": 1,
            "copied_bytes": 100,
            "copy_integrity": "SHA256_VERIFIED",
            "registry": {
                "selected_sources": 1,
                "registered_files": 1,
                "registered_by_format": {"SFZ": 1},
                "sfz_dependencies_found": 2,
                "sfz_dependencies_blocked": 3,
                "errors": [{"path": "bank.sfz", "error": "missing sample"}],
            },
        })
        self.assertEqual(summary["sfz_dependencies_blocked"], 3)
        self.assertEqual(summary["errors"], 1)
        self.assertIn("не разрешено зависимостей — 3", detail)
        self.assertIn("Предупреждений импорта: 1", detail)


if __name__ == "__main__":
    unittest.main()
