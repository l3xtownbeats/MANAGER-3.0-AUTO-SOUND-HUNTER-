"""Custom volumetric NEON STAGE controls for the Library Manager.

Pure Tk Canvas rendering keeps the portable application dependency-free while
providing layered metallic faces, beveled edges and responsive neon lighting.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Mapping


def _blend_hex(first: str, second: str, amount: float) -> str:
    """Blend two #RRGGBB colors; amount=0 returns first, amount=1 returns second."""
    amount = max(0.0, min(1.0, float(amount)))
    a = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
    values = tuple(round(left + (right - left) * amount) for left, right in zip(a, b))
    return "#" + "".join(f"{value:02X}" for value in values)


def _bevel_points(left: float, top: float, right: float, bottom: float,
                  cut: float = 11.0) -> tuple[float, ...]:
    """Return a chamfered polygon suitable for a hard-surface button face."""
    cut = min(cut, max(3.0, (right - left) / 5.0), max(3.0, (bottom - top) / 3.0))
    return (
        left + cut, top, right - cut, top, right, top + cut,
        right, bottom - cut, right - cut, bottom, left + cut, bottom,
        left, bottom - cut, left, top + cut,
    )


def _scanline_span(points: tuple[float, ...], y: float) -> tuple[float, float] | None:
    """Find the polygon's horizontal span at y, used to clip gradient bands."""
    coords = list(zip(points[0::2], points[1::2]))
    intersections: list[float] = []
    for index, (x1, y1) in enumerate(coords):
        x2, y2 = coords[(index + 1) % len(coords)]
        if y1 == y2:
            continue
        if min(y1, y2) <= y < max(y1, y2):
            intersections.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    if len(intersections) < 2:
        return None
    return min(intersections), max(intersections)


class NeonStageRail(tk.Canvas):
    """A narrow multi-pass neon light rail for card tops and instrument panels."""

    def __init__(self, master, *, accent: str, height: int = 7) -> None:
        super().__init__(
            master, height=height, bd=0, highlightthickness=0,
            relief="flat", bg=master.cget("bg"),
        )
        self._accent = accent
        self.bind("<Configure>", self._draw)
        self.after_idle(self._draw)

    def _draw(self, _event=None) -> None:
        width = max(2, self.winfo_width())
        height = max(4, self.winfo_height())
        self.delete("all")
        glow = _blend_hex(self._accent, "#FFFFFF", 0.42)
        self.create_line(0, height - 1, width, height - 1,
                         fill=_blend_hex(self._accent, "#000000", 0.62), width=3)
        self.create_line(0, height // 2, width, height // 2,
                         fill=self._accent, width=3)
        self.create_line(0, 1, width, 1, fill=glow, width=1)


class NeonStageButton(tk.Canvas):
    """A keyboard-accessible 3D neon button with hover, press and disabled states."""

    def __init__(
        self,
        master,
        *,
        text: str,
        command: Callable[[], None],
        palette: Mapping[str, str],
        accent: str,
        height: int = 62,
        font: tuple = ("Segoe UI", 10, "bold"),
        state: str = "normal",
    ) -> None:
        super().__init__(
            master, height=height, width=260, bd=0, highlightthickness=0,
            relief="flat", bg=master.cget("bg"), takefocus=1,
        )
        self._text = text
        self._command = command
        self._palette = dict(palette)
        self._accent = accent
        self._height = height
        self._font = font
        self._state = state
        self._hover = False
        self._pressed = False
        self._ready = True
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", self._on_keyboard_activate)
        self.bind("<space>", self._on_keyboard_activate)
        self.after_idle(self._draw)

    def configure(self, cnf=None, **kwargs):
        """Support the state/text/command calls used by Tk widgets elsewhere."""
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
            cnf = None
        redraw = False
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self._pressed = False
            redraw = True
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            redraw = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        result = super().configure(cnf, **kwargs)
        if redraw and getattr(self, "_ready", False):
            self._draw()
        return result

    config = configure

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self.configure(cursor="hand2" if self._state == "normal" else "arrow")
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._pressed = False
        self.configure(cursor="arrow")
        self._draw()

    def _on_press(self, event) -> None:
        if self._state != "normal":
            return
        self.focus_set()
        self._pressed = True
        self._draw()

    def _on_release(self, event) -> None:
        if self._state != "normal":
            return
        activate = self._pressed and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._pressed = False
        self._draw()
        if activate and self._command:
            self._command()

    def _on_keyboard_activate(self, _event=None) -> str:
        if self._state == "normal" and self._command:
            self._command()
        return "break"

    def _draw(self, _event=None) -> None:
        if not getattr(self, "_ready", False):
            return
        width = max(120, self.winfo_width())
        height = max(44, self.winfo_height())
        self.delete("all")

        muted = self._state != "normal"
        accent = self._palette.get("text_disabled", "#788BA4") if muted else self._accent
        if self._hover and not muted:
            accent = _blend_hex(accent, "#FFFFFF", 0.20)
        face = self._palette.get("control_face", "#06112A")
        top_face = _blend_hex(face, accent, 0.28 if self._hover else 0.18)
        bottom_face = _blend_hex(face, "#000000", 0.54)
        left, right = 7.0, float(width - 7)
        shift = 3.0 if self._pressed and not muted else 0.0
        top, bottom = 5.0 + shift, float(height - 9 + shift)
        cut = 12.0
        points = _bevel_points(left, top, right, bottom, cut)
        shadow_points = _bevel_points(left + 1, top + 5, right + 1, bottom + 5, cut)
        self.create_polygon(
            shadow_points, fill=self._palette.get("shadow", "#00020A"),
            outline=_blend_hex(self._palette.get("shadow", "#00020A"), accent, 0.18),
            width=1,
        )
        self.create_polygon(
            points, fill=face, outline=_blend_hex(accent, "#FFFFFF", 0.20), width=2,
        )

        bands = 22
        for band in range(bands):
            y0 = top + 1 + (bottom - top - 2) * band / bands
            y1 = top + 1 + (bottom - top - 2) * (band + 1) / bands
            span = _scanline_span(points, (y0 + y1) / 2)
            if span is None:
                continue
            color = _blend_hex(top_face, bottom_face, band / max(1, bands - 1))
            self.create_rectangle(
                span[0] + 0.4, y0, span[1] - 0.4, y1 + 0.6,
                fill=color, outline=color,
            )

        outer_glow = _blend_hex(accent, "#FFFFFF", 0.38 if self._hover else 0.18)
        self.create_polygon(points, fill="", outline=accent, width=2)
        self.create_line(left + cut + 3, top + 2, right - cut - 3, top + 2,
                         fill=outer_glow, width=2)
        self.create_line(left + 2, top + cut, left + 2, bottom - cut,
                         fill=_blend_hex(accent, "#FFFFFF", 0.34), width=1)
        self.create_line(left + cut, bottom - 1, right - cut, bottom - 1,
                         fill=_blend_hex(accent, "#000000", 0.52), width=2)
        self.create_line(right - 1, top + cut, right - 1, bottom - cut,
                         fill=_blend_hex(accent, "#000000", 0.38), width=2)

        led_x = left + 22
        led_y = (top + bottom) / 2
        led_color = self._palette.get("text_disabled", "#788BA4") if muted else self._palette.get("accent_glow", "#00BFFF")
        if self._hover and not muted:
            led_color = "#FFFFFF"
        self.create_oval(led_x - 8, led_y - 8, led_x + 8, led_y + 8,
                         outline=_blend_hex(led_color, face, 0.28), width=2)
        self.create_oval(led_x - 4, led_y - 4, led_x + 4, led_y + 4,
                         fill=led_color, outline=led_color)
        self.create_oval(led_x - 2, led_y - 3, led_x + 1, led_y,
                         fill="#FFFFFF" if not muted else led_color, outline="")

        text_color = self._palette.get("text_disabled", "#788BA4") if muted else self._palette.get("text_primary", "#F3F7FF")
        shadow_text = _blend_hex(self._palette.get("shadow", "#00020A"), accent, 0.22)
        x = width / 2 + 5
        y = led_y + (1 if self._pressed else 0)
        self.create_text(x + 1, y + 2, text=self._text, fill=shadow_text,
                         font=self._font, anchor="center")
        self.create_text(x, y, text=self._text, fill=text_color,
                         font=self._font, anchor="center")
        if self._state == "disabled":
            self.create_polygon(points, fill="#000000", stipple="gray50", outline="")

