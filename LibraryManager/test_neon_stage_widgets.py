import unittest

from neon_stage_widgets import _blend_hex, _bevel_points, _scanline_span


class NeonStageWidgetGeometryTests(unittest.TestCase):
    def test_color_blend_endpoints(self):
        self.assertEqual(_blend_hex("#000000", "#FFFFFF", 0), "#000000")
        self.assertEqual(_blend_hex("#000000", "#FFFFFF", 1), "#FFFFFF")

    def test_color_blend_midpoint(self):
        self.assertEqual(_blend_hex("#000000", "#FFFFFF", 0.5), "#808080")

    def test_bevel_polygon_has_eight_corners(self):
        points = _bevel_points(0, 0, 100, 50)
        self.assertEqual(len(points), 16)

    def test_scanline_stays_inside_chamfered_face(self):
        points = _bevel_points(0, 0, 100, 50)
        span = _scanline_span(points, 1)
        self.assertIsNotNone(span)
        self.assertGreater(span[0], 0)
        self.assertLess(span[1], 100)

