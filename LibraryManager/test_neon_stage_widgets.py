"""Pure contract tests for the 3D NEON STAGE widget layer."""
from __future__ import annotations

import unittest

from neon_stage_widgets import NEON, _mix


class NeonStageWidgetTests(unittest.TestCase):
    def test_blend_returns_valid_hex_and_endpoints(self):
        self.assertEqual(_mix("#000000", "#FFFFFF", 0.0), "#000000")
        self.assertEqual(_mix("#000000", "#FFFFFF", 1.0), "#ffffff")
        self.assertRegex(_mix("#102030", "#90A0B0", 0.5), r"^#[0-9a-f]{6}$")

    def test_palette_contains_all_material_and_status_tokens(self):
        for token in (
            "bg", "panel", "panel_inner", "metal_light", "metal",
            "metal_shadow", "blue", "cyan", "blue_dark", "purple",
            "magenta", "text", "muted", "dim", "green", "red",
        ):
            self.assertIn(token, NEON)
            self.assertRegex(NEON[token], r"^#[0-9A-Fa-f]{6}$")

    def test_button_material_variants_are_distinct(self):
        self.assertNotEqual(_mix("#18569A", "#041126", 0.3),
                            _mix("#38204C", "#090A18", 0.3))


if __name__ == "__main__":
    unittest.main()
