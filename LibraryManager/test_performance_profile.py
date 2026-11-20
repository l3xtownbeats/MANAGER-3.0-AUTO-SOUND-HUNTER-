from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from performance_profile import (
    AUDIO_ANALYSIS_SAMPLE_LIMIT,
    CPU_LIMIT_PERCENT,
    HASH_READ_BLOCK_BYTES,
    MAX_CONCURRENT_FILES,
    PROCESS_MEMORY_LIMIT_GB,
    recommended_scan_workers,
    resolve_fast_cache_dir,
)


class PerformanceProfileTests(unittest.TestCase):
    def test_target_profile_is_bounded_for_four_logical_processors(self):
        self.assertEqual(recommended_scan_workers(logical_processors=4), 2)
        self.assertEqual(recommended_scan_workers(logical_processors=2), 1)
        self.assertEqual(recommended_scan_workers(requested=2, logical_processors=2), 2)
        self.assertEqual(recommended_scan_workers(requested=8, logical_processors=8), 2)
        self.assertEqual(MAX_CONCURRENT_FILES, 2)

    def test_user_resource_budgets_are_recorded(self):
        self.assertEqual(CPU_LIMIT_PERCENT, 70)
        self.assertEqual(PROCESS_MEMORY_LIMIT_GB, 5)
        self.assertEqual(HASH_READ_BLOCK_BYTES, 4 * 1024 * 1024)
        self.assertEqual(AUDIO_ANALYSIS_SAMPLE_LIMIT, 90_000)

    def test_fallback_cache_folder_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "reports"
            result = resolve_fast_cache_dir(root)
            self.assertEqual(result, root.resolve())
            self.assertTrue(root.is_dir())


if __name__ == "__main__":
    unittest.main()
