"""Reusable 3D NEON STAGE controls for the Library Manager desktop UI.

Tkinter-native drawing only: no image-backed mockup, external widget toolkit,
or side effects. Buttons are real interactive controls.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

NEON = {
    "bg": "#01040D",
    "panel": "#061225",
    "panel_inner": "#020A18",
    "metal_light": "#AFC4DF",
    "metal": "#536A8A",
    "metal_shadow": "#111E33",
    "blue": "#087DFF",
    "cyan": "#00C8FF",
    "blue_dark": "#063B80",
    "purple": "#7A23D4",
    "magenta": "#F12BCB",
    "text": "#F4F8FF",
    "muted": "#AFC2DC",
    "dim": "#7086A5",
    "green": "#58EF9A",
    "red": "#FF597C",
}


def _mix(a: str, b: str, amount: float) -> str:
    """Linear RGB blend between two #RRGGBB colors."""
    amount = max(0.0, min(1.0, float(amount)))
    av = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    bv = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(
        f"{round(x + (y - x) * amount):02x}" for x, y in zip(av, bv)
    )


class VstPanel(tk.Frame):
    """A layered metal bezel panel with a gradient title rail and recessed body."""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        *,
        tag: str = "",
        accent: str = NEON["cyan"],
        palette: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        self._palette = dict(NEON)
        if palette:
            self._palette.update(palette)
        self._accent = accent
        super().__init__(master, bg=self._palette["metal_shadow"], bd=0, **kwargs)

        self.rim = tk.Frame(
            self, bg=self._palette["metal"], bd=1, relief="raised",
        )
        self.rim.pack(fill="both", expand=True, padx=1, pady=1)

        self.inner = tk.Frame(
            self.rim, bg=self._palette["panel_inner"],
            bd=2, relief="sunken", highlightthickness=1,
            highlightbackground=self._palette["metal_light"],
        )
        self.inner.pack(fill="both", expand=True, padx=2, pady=2)

        self.top_glow = tk.Frame(self.inner, bg=accent, height=2)
        self.top_glow.pack(fill="x")
        self.header = tk.Canvas(
            self.inner, height=34, bg=self._palette["panel"],
            highlightthickness=0, bd=0,
        )
        self.header.pack(fill="x")
        self.header.bind("<Configure>", self._draw_header)
        self._title = str(title)
        self._tag = str(tag)

        self.separator = tk.Frame(self.inner, bg=self._palette["metal"], height=1)
        self.separator.pack(fill="x")
        self.body = tk.Frame(
            self.inner, bg=self._palette["panel_inner"],
            bd=0, highlightthickness=0,
        )
        self.body.pack(fill="both", expand=True, padx=8, pady=8)
        self.bottom_glow = tk.Frame(self.inner, bg=self._palette["metal_shadow"], height=2)
        self.bottom_glow.pack(fill="x", side="bottom")

    def _draw_header(self, _event=None) -> None:
        c = self.header
        c.delete("all")
        w = max(80, c.winfo_width())
        h = max(28, c.winfo_height())
        top, bottom = "#1C3658", "#030A17"
        steps = max(1, h)
        for y in range(steps):
            c.create_line(0, y, w, y, fill=_mix(top, bottom, y / max(1, steps - 1)))
        c.create_line(1, 1, w - 2, 1, fill="#D8E9FF", width=1)
        c.create_line(1, h - 2, w - 2, h - 2, fill="#00030A", width=2)
        c.create_rectangle(7, 8, 11, h - 8, fill=self._accent, outline="")
        c.create_line(14, 6, 14, h - 6, fill="#244F83", width=1)
        c.create_text(
            23, h / 2, text=self._title, anchor="w",
            fill=self._palette["text"], font=("Segoe UI", 9, "bold"),
        )
        if self._tag:
            c.create_text(
                w - 12, h / 2, text=self._tag, anchor="e",
                fill=self._accent, font=("Consolas", 7, "bold"),
            )
        c.create_line(0, h - 1, w, h - 1, fill=self._accent, width=1)


class NeonActionButton(tk.Frame):
    """A clickable, beveled 3D button drawn on Canvas.

    Supports .configure(state='disabled'|'normal') so it can replace ttk.Button
    in the existing task lifecycle without changing worker or cancellation code.
    """

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        subtitle: str = "",
        icon: str = "none",
        accent: str = NEON["cyan"],
        variant: str = "primary",
        width: int = 260,
        height: int = 66,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=NEON["panel_inner"], bd=0, **kwargs)
        self.text = str(text)
        self.subtitle = str(subtitle)
        self.command = command
        self.icon = icon
        self.accent = accent
        self.variant = variant
        self._state = "normal"
        self._hover = False
        self._pressed = False
        self.canvas = tk.Canvas(
            self, width=width, height=height, bg=NEON["panel_inner"],
            highlightthickness=0, bd=0, relief="flat",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._draw)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<KeyPress-Return>", self._on_key)
        self.canvas.bind("<KeyPress-space>", self._on_key)
        self.canvas.configure(takefocus=True, cursor="hand2")
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        if state is not None:
            self._state = str(state)
            self._pressed = False
            self._draw()
        return super().configure(cnf, **kwargs)

    config = configure

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        if self._state == "normal":
            self.canvas.configure(cursor="hand2")
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None) -> None:
        if self._state != "normal":
            return
        self._pressed = True
        self.canvas.focus_set()
        self._draw()

    def _on_release(self, event=None) -> None:
        activate = (
            self._state == "normal" and self._pressed and event is not None
            and 0 <= event.x <= self.canvas.winfo_width()
            and 0 <= event.y <= self.canvas.winfo_height()
        )
        self._pressed = False
        self._draw()
        if activate and callable(self.command):
            self.command()

    def _on_key(self, _event=None) -> str:
        if self._state == "normal" and callable(self.command):
            self.command()
        return "break"

    def _draw_icon(self, c: tk.Canvas, x: float, y: float, accent: str) -> None:
        if self.icon == "folder":
            c.create_polygon(
                x - 13, y - 7, x - 3, y - 7, x + 1, y - 3,
                x + 14, y - 3, x + 14, y + 10, x - 13, y + 10,
                fill="#0B2D56", outline=accent, width=1.5,
            )
            c.create_line(x - 12, y - 2, x + 12, y - 2, fill="#BFEFFF", width=1)
        elif self.icon == "scan":
            c.create_oval(x - 13, y - 13, x + 13, y + 13, outline=accent, width=1.4)
            c.create_oval(x - 7, y - 7, x + 7, y + 7, outline="#78E9FF", width=1)
            c.create_line(x, y, x + 10, y - 9, fill="#FFFFFF", width=2)
            c.create_line(x, y, x + 13, y, fill=accent, width=1)
            c.create_oval(x - 2, y - 2, x + 2, y + 2, fill=accent, outline="")
        elif self.icon == "cancel":
            c.create_line(x - 8, y - 8, x + 8, y + 8, fill="#FFFFFF", width=2)
            c.create_line(x - 8, y + 8, x + 8, y - 8, fill="#FFFFFF", width=2)
        elif self.icon == "queue":
            for offset in (-8, 0, 8):
                c.create_rectangle(x - 10, y + offset - 2, x + 10, y + offset + 2,
                                   outline=accent, fill="#0A2444")
        elif self.icon == "reports":
            c.create_rectangle(x - 10, y - 12, x + 9, y + 12,
                               fill="#0A2444", outline=accent, width=1.4)
            for offset in (-5, 1, 7):
                c.create_line(x - 6, y + offset, x + 5, y + offset,
                              fill="#BFEFFF", width=1)

    def _draw(self, _event=None) -> None:
        c = self.canvas
        c.delete("all")
        w = max(120, c.winfo_width())
        h = max(36, c.winfo_height())
        disabled = self._state != "normal"
        accent = "#56647A" if disabled else self.accent
        if self.variant == "magenta" and not disabled:
            face_top, face_bottom = "#38204C", "#090A18"
        elif self.variant == "secondary" and not disabled:
            face_top, face_bottom = "#213752", "#080E1B"
        elif disabled:
            face_top, face_bottom = "#283448", "#0B111C"
        else:
            face_top, face_bottom = "#18569A", "#041126"
        if self._hover and not disabled:
            face_top = _mix(face_top, accent, 0.18)
        if self._pressed:
            face_top, face_bottom = face_bottom, face_top

        # Outer shadow and silver chassis bevel.
        c.create_polygon(
            3, 7, w - 3, 7, w - 1, h - 3, 5, h - 1,
            fill="#000207", outline="#000207",
        )
        c.create_polygon(
            2, 3, w - 4, 3, w - 1, h - 7, 5, h - 3,
            fill="#6F86A6", outline="#C4D6EF", width=1,
        )
        c.create_polygon(
            5, 5, w - 7, 5, w - 5, h - 10, 8, h - 6,
            fill="#08152A", outline="#244D80", width=1,
        )
        # Recessed face gradient.
        top, bottom = 8, h - 11
        for y in range(top, max(top + 1, bottom)):
            color = _mix(face_top, face_bottom, (y - top) / max(1, bottom - top - 1))
            c.create_line(8, y, w - 8, y, fill=color)
        c.create_rectangle(8, top, w - 8, bottom, outline=accent, width=1)
        c.create_line(11, top + 2, w - 11, top + 2, fill="#E5F8FF", width=1)
        c.create_line(11, bottom - 1, w - 11, bottom - 1, fill="#00030B", width=2)
        c.create_line(8, top + 6, 8, bottom - 5, fill=_mix(accent, "#FFFFFF", 0.4), width=2)
        c.create_line(w - 9, top + 6, w - 9, bottom - 5, fill="#02040B", width=2)

        icon_x = 33 if self.icon != "none" else 18
        icon_y = h / 2 - (5 if self.subtitle else 0)
        if self.icon != "none":
            self._draw_icon(c, icon_x, icon_y, accent)
        text_x = 59 if self.icon != "none" else w / 2
        anchor = "w" if self.icon != "none" else "center"
        if self.subtitle:
            c.create_text(
                text_x, h / 2 - 7, text=self.text, anchor=anchor,
                fill="#F5FAFF" if not disabled else "#9BA8B9",
                font=("Segoe UI", 9, "bold"),
            )
            c.create_text(
                text_x, h / 2 + 11, text=self.subtitle, anchor=anchor,
                fill="#C8DDF5" if not disabled else "#78879C",
                font=("Segoe UI", 7),
            )
        else:
            c.create_text(
                text_x, h / 2, text=self.text, anchor=anchor,
                fill="#F5FAFF" if not disabled else "#9BA8B9",
                font=("Segoe UI", 8, "bold"),
            )


class NeonBadge(tk.Frame):
    """Small inset status badge with an LED and a truthful text label."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        *,
        color: str = NEON["cyan"],
        palette: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        self._palette = dict(NEON)
        if palette:
            self._palette.update(palette)
        super().__init__(
            master, bg=self._palette["panel_inner"],
            highlightbackground=self._palette["metal"], highlightthickness=1,
            bd=0, padx=7, pady=4, **kwargs,
        )
        self.dot = tk.Canvas(
            self, width=13, height=13, bg=self._palette["panel_inner"],
            highlightthickness=0, bd=0,
        )
        self.dot.pack(side="left", padx=(0, 5))
        self.dot.create_oval(2, 2, 11, 11, fill=color, outline="#EAF8FF", width=1)
        self.label = tk.Label(
            self, text=text, bg=self._palette["panel_inner"],
            fg=color, font=("Consolas", 7, "bold"),
        )
        self.label.pack(side="left")

    def set_text(self, text: str, *, color: str | None = None) -> None:
        self.label.configure(text=text)
        if color:
            self.label.configure(fg=color)
            self.dot.delete("all")
            self.dot.create_oval(2, 2, 11, 11, fill=color, outline="#EAF8FF", width=1)
