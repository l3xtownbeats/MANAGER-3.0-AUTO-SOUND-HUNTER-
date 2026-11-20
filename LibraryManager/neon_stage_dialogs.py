"""NEON STAGE windows and modal dialogs for the Library Manager.

Presentation only: this module owns Tk widgets and never performs library,
audio, hashing, review, or file-operation work.
"""
from __future__ import annotations

import textwrap
import tkinter as tk
from tkinter import ttk
from typing import Any


def estimate_dialog_size(message: str, *, width: int = 560,
                         minimum_height: int = 176,
                         maximum_height: int = 520) -> tuple[int, int]:
    """Return a bounded size for readable themed message dialogs."""
    text = str(message or "")
    wrapped_lines = 0
    for line in text.splitlines() or [""]:
        wrapped_lines += max(1, len(textwrap.wrap(line, width=72)) or 1)
    height = max(minimum_height, 116 + wrapped_lines * 19)
    return width, min(maximum_height, height)


class NeonStageDialogs:
    """Build branded NEON STAGE windows and synchronous modal prompts."""

    def __init__(self, parent: tk.Misc, palette: dict[str, str]) -> None:
        self.parent = parent
        self.palette = dict(palette)

    def set_palette(self, palette: dict[str, str]) -> None:
        self.palette = dict(palette)

    def create_window(
        self,
        title: str,
        subtitle: str = "AUTO SOUND HUNTER MANAGER  /  NEON STAGE",
        geometry: str = "900x600",
        *,
        parent: tk.Misc | None = None,
        resizable: bool = True,
    ) -> tuple[tk.Toplevel, tk.Frame, tk.Frame]:
        """Create a fully framed secondary window.

        Returns (window, content_frame, footer_frame). Content and footer are
        already packed; callers only place their own functional widgets inside.
        """
        master = parent or self.parent
        p = self.palette
        window = tk.Toplevel(master)
        window.title(title)
        window.geometry(geometry)
        window.configure(bg=p["window_bg"])
        window.transient(master)
        window.resizable(resizable, resizable)

        shell = tk.Frame(
            window, bg=p["panel"], highlightbackground=p["control_border"],
            highlightthickness=1, bd=0,
        )
        shell.pack(fill="both", expand=True, padx=8, pady=8)

        rail = tk.Frame(shell, bg=p["window_bg"], height=4)
        rail.pack(fill="x")
        rail.pack_propagate(False)
        for color in (
            p["accent"], p["accent_glow"], p.get("accent_purple", p["accent"]),
            p.get("accent_magenta", p["accent"]),
        ):
            tk.Frame(rail, bg=color, height=4).pack(side="left", fill="both", expand=True)

        header = tk.Frame(
            shell, bg=p["panel_elevated"], padx=15, pady=10,
            highlightbackground=p["control_border"], highlightthickness=1,
        )
        header.pack(fill="x", padx=8, pady=(8, 0))
        title_block = tk.Frame(header, bg=p["panel_elevated"])
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_block, text="NEON STAGE  /  MANAGER WORKSPACE",
            bg=p["panel_elevated"], fg=p["accent_glow"],
            font=("Segoe UI", 7, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_block, text=title, bg=p["panel_elevated"],
            fg=p["text_primary"], font=("Segoe UI", 13, "bold"), anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            title_block, text=subtitle, bg=p["panel_elevated"],
            fg=p["text_secondary"], font=("Segoe UI", 8), anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        led = tk.Canvas(
            header, width=18, height=18, bg=p["panel_elevated"],
            highlightthickness=0, bd=0,
        )
        led.create_oval(4, 4, 14, 14, fill=p["led_on"], outline=p["accent_glow"], width=1)
        led.pack(side="right", padx=(10, 0), anchor="center")

        content = tk.Frame(shell, bg=p["panel"])
        content.pack(fill="both", expand=True, padx=8, pady=8)
        footer = tk.Frame(
            shell, bg=p["panel_elevated"], padx=12, pady=7,
            highlightbackground=p["control_border"], highlightthickness=1,
        )
        footer.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(
            footer, text="PPGU  •  SKIN-1  •  NEON STAGE",
            bg=p["panel_elevated"], fg=p["text_disabled"],
            font=("Consolas", 7), anchor="w",
        ).pack(side="left")
        return window, content, footer

    def _center(self, window: tk.Toplevel, parent: tk.Misc) -> None:
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
        except tk.TclError:
            x = max(0, (window.winfo_screenwidth() - width) // 2)
            y = max(0, (window.winfo_screenheight() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _modal_shell(
        self,
        title: str,
        subtitle: str,
        *,
        parent: tk.Misc | None = None,
        width: int = 560,
        height: int = 200,
    ) -> tuple[tk.Toplevel, tk.Frame, tk.Frame, tk.Misc]:
        master = parent or self.parent
        p = self.palette
        window, content, footer = self.create_window(
            title, subtitle, f"{width}x{height}", parent=master, resizable=False,
        )
        window.transient(master)
        # The modal is intentionally a compact console panel, not a system
        # MessageBox; all copy remains selectable and keyboard accessible.
        content.configure(padx=18, pady=16)
        return window, content, footer, master

    def _finish_modal(self, window: tk.Toplevel, master: tk.Misc) -> None:
        window.bind("<Escape>", lambda _event: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        self._center(window, master)
        try:
            window.grab_set()
        except tk.TclError:
            pass
        window.wait_window()

    def _message(self, title: str, message: str, level: str,
                 parent: tk.Misc | None = None) -> str:
        p = self.palette
        width, height = estimate_dialog_size(message)
        window, content, footer, master = self._modal_shell(
            title, f"SYSTEM {level}", parent=parent, width=width, height=height,
        )
        accent = {
            "INFO": p["accent_glow"],
            "WARNING": p["warning"],
            "ERROR": p["danger"],
            "CONFIRM": p["accent"],
        }.get(level, p["accent"])
        rail = tk.Frame(content, bg=p["panel"])
        rail.pack(fill="x", pady=(0, 12))
        tk.Frame(rail, bg=accent, width=4).pack(side="left", fill="y", padx=(0, 12))
        label = tk.Message(
            rail, text=str(message), width=width - 105,
            bg=p["panel"], fg=p["text_primary"],
            font=("Segoe UI", 9), justify="left", anchor="w",
        )
        label.pack(side="left", fill="both", expand=True, pady=4)
        result = {"button": "ok"}
        button = ttk.Button(
            footer, text="ПОНЯТНО", style="PPGU.DialogPrimary.TButton",
            command=window.destroy,
        )
        button.pack(side="right")
        button.focus_set()
        self._finish_modal(window, master)
        return result["button"]

    def showinfo(self, title: str, message: str, **kwargs: Any) -> str:
        return self._message(title, message, "INFO", kwargs.get("parent"))

    def showwarning(self, title: str, message: str, **kwargs: Any) -> str:
        return self._message(title, message, "WARNING", kwargs.get("parent"))

    def showerror(self, title: str, message: str, **kwargs: Any) -> str:
        return self._message(title, message, "ERROR", kwargs.get("parent"))

    def askyesno(self, title: str, message: str, **kwargs: Any) -> bool:
        p = self.palette
        width, height = estimate_dialog_size(message, minimum_height=204)
        window, content, footer, master = self._modal_shell(
            title, "CONFIRMATION REQUIRED", parent=kwargs.get("parent"),
            width=width, height=min(560, height + 20),
        )
        rail = tk.Frame(content, bg=p["panel"])
        rail.pack(fill="x", pady=(0, 12))
        tk.Frame(rail, bg=p["accent_glow"], width=4).pack(side="left", fill="y", padx=(0, 12))
        tk.Message(
            rail, text=str(message), width=width - 105,
            bg=p["panel"], fg=p["text_primary"],
            font=("Segoe UI", 9), justify="left", anchor="w",
        ).pack(side="left", fill="both", expand=True, pady=4)
        result = {"value": False}

        def finish(value: bool) -> None:
            result["value"] = value
            window.destroy()

        ttk.Button(
            footer, text="НЕТ", style="PPGU.DialogSecondary.TButton",
            command=lambda: finish(False),
        ).pack(side="right", padx=(8, 0))
        yes = ttk.Button(
            footer, text="ДА, ПРОДОЛЖИТЬ", style="PPGU.DialogPrimary.TButton",
            command=lambda: finish(True),
        )
        yes.pack(side="right")
        yes.focus_set()
        window.bind("<Return>", lambda _event: finish(True))
        self._finish_modal(window, master)
        return result["value"]

    def askstring(self, title: str, prompt: str, **kwargs: Any) -> str | None:
        p = self.palette
        initial = kwargs.get("initialvalue")
        show = kwargs.get("show")
        width, height = estimate_dialog_size(prompt, minimum_height=240)
        window, content, footer, master = self._modal_shell(
            title, "INPUT CONSOLE", parent=kwargs.get("parent"),
            width=width, height=min(580, height + 72),
        )
        tk.Message(
            content, text=str(prompt), width=width - 80,
            bg=p["panel"], fg=p["text_primary"],
            font=("Segoe UI", 9), justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 14))
        entry = tk.Entry(
            content, bg=p["control_bg"], fg=p["text_primary"],
            insertbackground=p["accent_glow"], selectbackground=p["control_face"],
            relief="flat", highlightthickness=1,
            highlightbackground=p["control_border"], highlightcolor=p["accent"],
            font=("Consolas", 10), show=show or "",
        )
        entry.pack(fill="x", ipady=8)
        if initial is not None:
            entry.insert(0, str(initial))
            entry.selection_range(0, "end")
        result: dict[str, str | None] = {"value": None}

        def finish(accepted: bool) -> None:
            result["value"] = entry.get() if accepted else None
            window.destroy()

        ttk.Button(
            footer, text="ОТМЕНА", style="PPGU.DialogSecondary.TButton",
            command=lambda: finish(False),
        ).pack(side="right", padx=(8, 0))
        accept = ttk.Button(
            footer, text="ПРИМЕНИТЬ", style="PPGU.DialogPrimary.TButton",
            command=lambda: finish(True),
        )
        accept.pack(side="right")
        accept.focus_set()
        window.bind("<Return>", lambda _event: finish(True))
        self._finish_modal(window, master)
        return result["value"]
