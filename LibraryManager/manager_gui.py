#!/usr/bin/env python3
"""Portable Tkinter front end for POP PUNK GUITAR Library Manager.

Uses only Python's standard library plus the existing LibraryManager modules.
All file operations remain review-gated by library_operations.py.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path

from app_paths import resolve_runtime_paths, resource_file

from unified_manager import AUDIO_EXT, run_manager, quick_scan, resolve_samples_root
from source_import import import_sources_to_library
from pattern_clip_extractor import extract_pattern_occurrences
from other_audit import audit_other_library, route_approved_to_other, copy_unsupported_to_other
from cleanup_audit import audit_all_import_sources, cleanup_sources_from_audit
from finalization import finalize_library as finalize_library_audit
from manifest_review import review_manifest
from task_journal import TaskJournal
from plugin_asset_catalog import MODE_ORDER, build_plugin_asset_catalog, browser_assets_for_mode
from performance_manifest import build_performance_manifest
from pattern_song_manager import open_pattern_song_manager
from chromatic_pitch_map import build_chromatic_pitch_map, chromatic_note_table
from library_structure import write_library_structure, TECHNIQUES
from library_operations import (
    cleanup_original_sources,
    distribute_assets_transactional,
    distribution_plan,
    auto_distribute_approved,
)
from ppgu_theme import NEON_STAGE_THEME, configure_neon_stage_ttk
from neon_stage_widgets import VstPanel, NeonActionButton, NeonBadge
from neon_stage_dialogs import NeonStageDialogs
from manager_ui_feedback import build_import_completion_summary

APP_VERSION = "3.0.0"
BUNDLE_DIR, MANAGER_DIR, PORTABLE_MODE = resolve_runtime_paths(__file__)
# The application can live anywhere. The input library is selected independently.
DEFAULT_SAMPLES = ""
STAGING_ROOT = MANAGER_DIR / "staging"
MANAGER_DIR.mkdir(parents=True, exist_ok=True)
STAGING_ROOT.mkdir(parents=True, exist_ok=True)


class LibraryManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.dialogs = NeonStageDialogs(root, NEON_STAGE_THEME["palette"])
        self.root.title(f"POP PUNK GUITAR LIBRARY MANAGER {APP_VERSION}")
        self.root.geometry("980x680")
        self.root.minsize(760, 520)
        self._settings_path = MANAGER_DIR / "manager_settings.json"
        self._saved_settings = self._load_saved_settings()
        self.samples_root = tk.StringVar(value=self._saved_settings.get("samples_root", DEFAULT_SAMPLES))
        self.analyze_audio = tk.BooleanVar(value=self._saved_settings.get("analyze_audio", True))
        self.guitar_confirmed = tk.BooleanVar(
            value=self._saved_settings.get("guitar_source_confirmed", False)
        )
        self.status = tk.StringVar(value="Готов. Выберите Samples или непосредственно Import Sample Guitar.")
        # Worker threads must never call Tkinter methods. They only enqueue events;
        # the Tk main thread drains this queue in _poll_worker_events().
        self._worker_events = queue.Queue()
        self._job_running = False
        self._worker_thread = None
        self._cancel_event = threading.Event()
        self._action_buttons = []
        self._cancel_button = None
        self._task_journal = TaskJournal(MANAGER_DIR / 'reports' / 'task_history.jsonl')
        self._active_task_id = None
        self._active_task_title = None
        self._progress_stage = 0
        self._progress_stage_total = 0
        self._build()
        self.root.after(100, self._poll_worker_events)
        if not self.samples_root.get().strip():
            self.root.after(350, self._prompt_for_library_root)
        if PORTABLE_MODE and MANAGER_DIR != (BUNDLE_DIR / "UserData").resolve():
            self._write(
                "PORTABLE: папка приложения недоступна для записи; "
                f"пользовательские данные вынесены в резервный каталог: {MANAGER_DIR}"
            )
        elif PORTABLE_MODE:
            self._write(
                "PORTABLE: приложение можно хранить в любой доступной папке. "
                f"Пользовательские данные: {MANAGER_DIR}"
            )

    def _build(self) -> None:
        """Build the real, dense NEON STAGE Manager workspace with two main actions."""
        palette = NEON_STAGE_THEME["palette"]
        bg = "#01040D"
        panel = "#061225"
        panel_alt = "#0A1B34"
        inset = "#020A18"
        text = "#F4F8FF"
        muted = "#AFC2DC"
        dim = "#7086A5"
        cyan = "#00C8FF"
        blue = "#087DFF"
        purple = "#7A23D4"
        magenta = "#F12BCB"
        green = "#58EF9A"
        amber = "#FFC857"
        red = "#FF597C"

        self.root.title(f"POP PUNK GUITAR  •  NEON STAGE DEFAULT / SKIN-1  •  MANAGER {APP_VERSION}")
        self.root.geometry("1500x940")
        self.root.minsize(1160, 760)
        self.root.configure(bg=bg)

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        configure_neon_stage_ttk(style, palette)
        style.configure(
            "PPGU.Neon.Horizontal.TProgressbar",
            troughcolor="#000817", background=cyan,
            bordercolor="#2869A4", lightcolor="#A7F2FF",
            darkcolor=blue, thickness=13,
        )

        # Secondary operations remain discoverable from menus. The main work
        # surface itself exposes exactly two primary workflow actions.
        menu_bar = tk.Menu(
            self.root, tearoff=0, bg="#061225", fg=text,
            activebackground="#123D6A", activeforeground="#FFFFFF",
            bd=1, relief="raised",
        )
        self.root.configure(menu=menu_bar)

        def add_menu(label: str, commands: list[tuple[str, object]]) -> None:
            submenu = tk.Menu(
                menu_bar, tearoff=0, bg="#061225", fg=text,
                activebackground="#123D6A", activeforeground=cyan,
                bd=1, relief="raised",
            )
            for item_label, command in commands:
                if item_label == "---":
                    submenu.add_separator()
                else:
                    submenu.add_command(label=item_label, command=command)
            menu_bar.add_cascade(label=label, menu=submenu)

        add_menu("ПРОЕКТ", [
            ("Выбрать папку Samples / Import Sample Guitar…", self.choose_samples),
            ("---", None),
            ("Открыть отчёты", self.open_reports),
            ("Открыть staging", self.open_staging),
            ("Инструкция", self.open_user_guide),
        ])
        add_menu("IMPORT SAMPLE GUITAR", [
            ("Добавить выбранные файлы / одну или несколько библиотек…", self.import_guitar),
            ("Выбрать папку Samples / Import Sample Guitar…", self.choose_samples),
        ])
        add_menu("SCAN HUNTING", [
            ("ЗАПУСТИТЬ ПОЛНЫЙ SCAN HUNTING", self.scan_hunting),
            ("---", None),
            ("Быстрый файловый обход (без анализа)", self.quick_scan_only),
            ("Глубокая инвентаризация / SHA-256 / SFZ (без аудио)", self.deep_scan_only),
            ("Аудит OTHER", self.audit_other),
            ("Направить одобренные материалы в OTHER", self.distribute_other),
            ("---", None),
            ("Открыть REVIEW QUEUE", self.open_review_queue),
            ("Прослушать WAV", self.preview_audio),
            ("Остановить прослушивание", self.stop_preview),
            ("История задач", self.show_task_history),
            ("---", None),
            ("Собрать каталог ассетов PPGU / VST3", self.build_plugin_catalog),
            ("Открыть Sample Browser", self.open_plugin_browser),
            ("Pattern Song Manager", self.open_pattern_song_library),
            ("12-нотная карта AutoChords", self.open_chromatic_pitch_map),
            ("Распределить одобренные ассеты", self.distribute),
            ("---", None),
            ("Проверить staging и FACTORY", self.finalize_library),
            ("Аудит исходников перед очисткой", self.audit_cleanup),
            ("Очистить исходники (двойное подтверждение)", self.cleanup),
        ])
        settings_menu = tk.Menu(
            menu_bar, tearoff=0, bg="#061225", fg=text,
            activebackground="#123D6A", activeforeground=cyan,
            selectcolor=blue, bd=1, relief="raised",
        )
        settings_menu.add_checkbutton(
            label="Полный аудиоанализ и извлечение кандидатов (рекомендуется)",
            variable=self.analyze_audio, command=self._save_settings_from_ui,
        )
        settings_menu.add_checkbutton(
            label="Источник уже отфильтрован как гитарный",
            variable=self.guitar_confirmed, command=self._save_settings_from_ui,
        )
        menu_bar.add_cascade(label="НАСТРОЙКИ", menu=settings_menu)

        # The outer chassis uses raised/sunken nested frames to create real
        # depth. Panels and controls below are live Tk widgets.
        outer = tk.Frame(
            self.root, bg="#6E86A8", bd=2, relief="raised",
            highlightthickness=1, highlightbackground="#D7E7FF",
        )
        outer.pack(fill="both", expand=True, padx=8, pady=8)
        deck = tk.Frame(outer, bg=bg, bd=2, relief="sunken")
        deck.pack(fill="both", expand=True, padx=3, pady=3)

        # Top identity rail: real app status plus the approved product language.
        top = VstPanel(
            deck, "PPGU  /  POP PUNK GUITAR ULTIMATE",
            tag="LIBRARY MANAGER 3.0  •  NEON STAGE DEFAULT  •  SKIN-1",
            accent=cyan,
        )
        top.pack(fill="x", padx=7, pady=(7, 6))
        top_row = tk.Frame(top.body, bg=inset)
        top_row.pack(fill="x")
        brand = tk.Frame(top_row, bg=inset)
        brand.pack(side="left", fill="x", expand=True)
        tk.Label(
            brand, text="AUTO SOUND HUNTER",
            bg=inset, fg="#FFFFFF", font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand, text="GUITAR LIBRARY CONTROL SURFACE",
            bg=inset, fg=cyan, font=("Consolas", 8, "bold"),
        ).pack(anchor="w", pady=(1, 0))
        self._operation_badge = NeonBadge(
            top_row, "IDLE  /  READY", color=green,
        )
        self._operation_badge.pack(side="right", padx=(8, 0), pady=5)
        NeonBadge(top_row, "ORIGINALS SAFE", color=cyan).pack(
            side="right", padx=4, pady=5,
        )
        NeonBadge(top_row, f"VER. {APP_VERSION}", color="#A9C8FF").pack(
            side="right", padx=4, pady=5,
        )

        workspace = tk.Frame(deck, bg=bg)
        workspace.pack(fill="both", expand=True, padx=7, pady=(0, 6))

        # LEFT RACK — source location, import guarantees and destination map.
        left = tk.Frame(workspace, bg=bg, width=250)
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)

        source_panel = VstPanel(
            left, "SOURCE LIBRARY", tag="INPUT", accent=cyan,
        )
        source_panel.pack(fill="x", pady=(0, 7))
        tk.Label(
            source_panel.body, text="ACTIVE LIBRARY ROOT",
            bg=inset, fg=cyan, font=("Segoe UI", 7, "bold"),
        ).pack(anchor="w", pady=(1, 4))
        self.samples_entry = tk.Entry(
            source_panel.body, textvariable=self.samples_root,
            bg="#000817", fg=text, insertbackground=cyan,
            relief="sunken", bd=2, highlightthickness=1,
            highlightbackground="#174B80", highlightcolor=cyan,
            font=("Consolas", 8), readonlybackground="#000817",
            state="readonly",
        )
        self.samples_entry.pack(fill="x", ipady=5)
        self._change_root_button = NeonActionButton(
            source_panel.body, "CHANGE LIBRARY ROOT",
            self.choose_samples, subtitle="SELECT SOURCE FOLDER",
            icon="folder", accent=cyan, variant="secondary",
            width=220, height=43,
        )
        self._change_root_button.pack(fill="x", pady=(7, 3))

        safety_panel = VstPanel(
            left, "IMPORT SAFETY", tag="READ ONLY SOURCE", accent=green,
        )
        safety_panel.pack(fill="x", pady=(0, 7))
        for title, detail, color in (
            ("COPY ONLY", "Original libraries stay in place", green),
            ("SHA-256", "Imported copies are verified", cyan),
            ("ARCHIVES", "Indexed intact; not auto-extracted", amber),
        ):
            line = tk.Frame(
                safety_panel.body, bg="#06182E",
                highlightbackground="#1B426B", highlightthickness=1,
                padx=7, pady=6,
            )
            line.pack(fill="x", pady=3)
            tk.Label(
                line, text="●", bg="#06182E", fg=color,
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left", padx=(0, 7))
            copy = tk.Frame(line, bg="#06182E")
            copy.pack(side="left", fill="x", expand=True)
            tk.Label(
                copy, text=title, bg="#06182E", fg=color,
                font=("Consolas", 8, "bold"),
            ).pack(anchor="w")
            tk.Label(
                copy, text=detail, bg="#06182E", fg=muted,
                font=("Segoe UI", 7), justify="left", anchor="w",
                wraplength=172,
            ).pack(anchor="w", pady=(1, 0))

        route_panel = VstPanel(
            left, "OUTPUT ROUTING", tag="REVIEW GATED", accent=magenta,
        )
        route_panel.pack(fill="both", expand=True)
        for number, title, caption, color in (
            ("01", "PATTERN", "Rhythm structures / chord events", cyan),
            ("02", "MELODY", "Single-note candidates / phrases", blue),
            ("03", "REVIEW QUEUE", "Human musical and source review", amber),
            ("04", "FACTORY", "Only reviewed + licensed + verified", green),
            ("05", "OTHER", "Unsupported / non-factory material", purple),
        ):
            row = tk.Frame(
                route_panel.body, bg="#041020",
                highlightbackground="#17375C", highlightthickness=1,
                padx=6, pady=5,
            )
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=number, bg="#041020", fg=color,
                font=("Consolas", 8, "bold"), width=3,
            ).pack(side="left", anchor="n")
            block = tk.Frame(row, bg="#041020")
            block.pack(side="left", fill="x", expand=True)
            tk.Label(
                block, text=title, bg="#041020", fg=text,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w")
            tk.Label(
                block, text=caption, bg="#041020", fg=dim,
                font=("Segoe UI", 6), justify="left", anchor="w",
                wraplength=175,
            ).pack(anchor="w")

        # CENTER RACK — approved PPGU artwork, two real actions and pipeline map.
        center = tk.Frame(workspace, bg=bg)
        center.pack(side="left", fill="both", expand=True, padx=(0, 6))

        hero_panel = VstPanel(
            center, "NEON STAGE  /  SIGNAL FORGE",
            tag="PPGU ARTWORK  •  DEFAULT SKIN-1", accent=cyan,
        )
        hero_panel.pack(fill="x", pady=(0, 7))
        self._banner_photo = None
        try:
            banner_path = resource_file(
                "ppgu_skin/assets/manager_banner.png.b64",
                module_file=__file__, bundle_dir=BUNDLE_DIR,
            )
            banner_data = banner_path.read_text(encoding="ascii").strip()
            self._banner_photo = tk.PhotoImage(
                master=self.root, data=banner_data,
            ).zoom(2, 2)
            tk.Label(
                hero_panel.body, image=self._banner_photo,
                bg="#000817", bd=0, padx=0, pady=0,
            ).pack(fill="x", expand=True)
        except (OSError, tk.TclError, ValueError) as exc:
            # A damaged artwork file must never prevent core library work.
            fallback = tk.Canvas(
                hero_panel.body, height=136, bg="#000817",
                highlightthickness=1, highlightbackground="#174B80",
            )
            fallback.pack(fill="x")
            fallback.create_text(
                18, 28, text="PPGU  /  NEON STAGE",
                anchor="w", fill=cyan, font=("Segoe UI", 20, "bold"),
            )
            fallback.create_text(
                18, 66, text="POP PUNK GUITAR LIBRARY MANAGER",
                anchor="w", fill=text, font=("Consolas", 11, "bold"),
            )
            fallback.create_text(
                18, 98, text=f"Artwork fallback active: {type(exc).__name__}",
                anchor="w", fill=amber, font=("Segoe UI", 8),
            )

        # SIX PRIMARY WORKFLOWS — the exact approved Manager navigation surface.
        # Each control invokes an existing, real operation; no decorative/fake actions.
        actions_panel = VstPanel(
            center, "NEON STAGE  /  MAIN CONTROL",
            tag="SIX CORE WORKFLOWS  •  LIVE ACTIONS", accent=cyan,
        )
        actions_panel.pack(fill="x", pady=(0, 7))
        action_grid = tk.Frame(actions_panel.body, bg=inset)
        action_grid.pack(fill="x")
        action_grid.grid_columnconfigure(0, weight=1, uniform="main-actions")
        action_grid.grid_columnconfigure(1, weight=1, uniform="main-actions")

        primary_actions = (
            ("01", "IMPORT GUITAR", "COPY SOURCE  /  SHA-256 VERIFY",
             self.import_guitar, "folder", cyan, "primary"),
            ("02", "SCAN LIBRARY", "FAST INVENTORY  /  FILESYSTEM",
             self.quick_scan_only, "scan", blue, "secondary"),
            ("03", "START HUNTING", "FULL SCAN  /  AUDIO  /  CANDIDATES",
             self.scan_hunting, "scan", magenta, "magenta"),
            ("04", "REVIEW QUEUE", "HUMAN REVIEW  /  PENDING CANDIDATES",
             self.open_review_queue, "queue", amber, "secondary"),
            ("05", "BUILD LIBRARY", "DISTRIBUTE ONLY ELIGIBLE APPROVED ASSETS",
             self.distribute, "reports", green, "secondary"),
            ("06", "VERIFY / RECOVERY", "AUDIT STAGING  /  FACTORY INTEGRITY",
             self.finalize_library, "reports", purple, "secondary"),
        )
        self._action_buttons = []
        for index, (number, title, subtitle, command, icon, accent, variant) in enumerate(primary_actions):
            card = tk.Frame(
                action_grid, bg="#06152B",
                highlightbackground="#24517D", highlightthickness=1,
                bd=0, padx=7, pady=6,
            )
            card.grid(
                row=index // 2, column=index % 2, sticky="nsew",
                padx=(0, 4) if index % 2 == 0 else (4, 0),
                pady=4,
            )
            rail = tk.Frame(card, bg="#06152B")
            rail.pack(fill="x", pady=(0, 3))
            tk.Label(
                rail, text=number, bg="#06152B", fg=accent,
                font=("Consolas", 8, "bold"),
            ).pack(side="left")
            tk.Label(
                rail, text=title, bg="#06152B", fg=text,
                font=("Segoe UI", 8, "bold"),
            ).pack(side="left", padx=(8, 0))
            button = NeonActionButton(
                card, title, command,
                subtitle=subtitle, icon=icon, accent=accent,
                variant=variant, width=390, height=65,
            )
            button.pack(fill="x")
            self._action_buttons.append(button)

        # PROCESS MAP — informational only; live completion is reported by the task monitor.
        pipeline_panel = VstPanel(
            center, "SIGNAL PATH  /  LIBRARY BUILD PIPELINE",
            tag="REAL TASK EVENTS ONLY", accent=purple,
        )
        pipeline_panel.pack(fill="both", expand=True)
        pipeline = tk.Frame(pipeline_panel.body, bg=inset)
        pipeline.pack(fill="both", expand=True)
        stages = (
            ("01", "IMPORT", "Verified copy", cyan),
            ("02", "SCAN", "File inventory", blue),
            ("03", "HUNT", "Audio + SFZ", purple),
            ("04", "EXTRACT", "Candidates", magenta),
            ("05", "REVIEW", "Human gate", amber),
            ("06", "BUILD", "Approved only", green),
        )
        for index, (number, title, caption, color) in enumerate(stages):
            cell = tk.Frame(
                pipeline, bg="#07162B",
                highlightbackground="#1C4778", highlightthickness=1,
                padx=5, pady=7,
            )
            cell.grid(row=0, column=index, sticky="nsew", padx=2, pady=2)
            pipeline.grid_columnconfigure(index, weight=1, uniform="pipeline")
            tk.Label(
                cell, text=number, bg="#07162B", fg=color,
                font=("Consolas", 9, "bold"),
            ).pack(anchor="w")
            tk.Label(
                cell, text=title, bg="#07162B", fg=text,
                font=("Segoe UI", 7, "bold"), justify="left",
                wraplength=100,
            ).pack(anchor="w", pady=(3, 2))
            tk.Label(
                cell, text=caption, bg="#07162B", fg=dim,
                font=("Segoe UI", 6), justify="left", wraplength=100,
            ).pack(anchor="w")
        tk.Label(
            pipeline_panel.body,
            text="PIPELINE MAP ONLY — NO STAGE IS MARKED COMPLETE UNTIL A REAL TASK REPORTS IT.",
            bg=inset, fg=dim, font=("Consolas", 6, "bold"),
        ).pack(anchor="w", pady=(5, 0))

        # RIGHT RACK — live task state and the review gate; no simulated meters.
        right = tk.Frame(workspace, bg=bg, width=290)
        right.pack(side="left", fill="y")
        right.pack_propagate(False)

        monitor_panel = VstPanel(
            right, "TASK MONITOR", tag="LIVE", accent=cyan,
        )
        monitor_panel.pack(fill="x", pady=(0, 7))
        monitor_header = tk.Frame(monitor_panel.body, bg=inset)
        monitor_header.pack(fill="x")
        self._progress_title = tk.StringVar(value="READY  /  ОЖИДАНИЕ")
        self._progress_detail = tk.StringVar(
            value="Выберите одну из двух основных операций."
        )
        tk.Label(
            monitor_header, textvariable=self._progress_title,
            bg=inset, fg=cyan, font=("Consolas", 8, "bold"),
            justify="left", anchor="w", wraplength=242,
        ).pack(fill="x", anchor="w")
        self._progress_bar = ttk.Progressbar(
            monitor_panel.body, mode="indeterminate", maximum=100,
            style="PPGU.Neon.Horizontal.TProgressbar",
        )
        self._progress_bar.pack(fill="x", pady=(9, 7))
        tk.Label(
            monitor_panel.body, textvariable=self._progress_detail,
            bg=inset, fg=muted, font=("Segoe UI", 7),
            justify="left", anchor="w", wraplength=246,
        ).pack(fill="x")
        self._cancel_button = NeonActionButton(
            monitor_panel.body, "CANCEL TASK", self.cancel_job,
            subtitle="SAFE STOP  /  KEEP ORIGINALS",
            icon="cancel", accent=red, variant="secondary",
            width=230, height=46,
        )
        self._cancel_button.pack(fill="x", pady=(9, 3))
        self._cancel_button.configure(state="disabled")

        review_panel = VstPanel(
            right, "REVIEW & DISTRIBUTION GATE",
            tag="NO AUTO-APPROVAL", accent=amber,
        )
        review_panel.pack(fill="both", expand=True)
        for title, detail in (
            ("REVIEWED", "Musical and structural review"),
            ("LICENSE APPROVED", "Distribution permission checked"),
            ("VERIFIED", "Integrity and provenance confirmed"),
        ):
            gate = tk.Frame(
                review_panel.body, bg="#08182C",
                highlightbackground="#4B4560", highlightthickness=1,
                padx=7, pady=6,
            )
            gate.pack(fill="x", pady=3)
            tk.Label(
                gate, text="◆", bg="#08182C", fg=amber,
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left", padx=(0, 7))
            labels = tk.Frame(gate, bg="#08182C")
            labels.pack(side="left", fill="x", expand=True)
            tk.Label(
                labels, text=title, bg="#08182C", fg=text,
                font=("Consolas", 7, "bold"),
            ).pack(anchor="w")
            tk.Label(
                labels, text=detail, bg="#08182C", fg=dim,
                font=("Segoe UI", 6), wraplength=195,
                justify="left", anchor="w",
            ).pack(anchor="w")
            tk.Label(
                gate, text="REQUIRED", bg="#08182C", fg=amber,
                font=("Consolas", 6, "bold"),
            ).pack(side="right", padx=(4, 0))
        self._review_button = NeonActionButton(
            review_panel.body, "OPEN REVIEW QUEUE",
            self.open_review_queue, subtitle="INSPECT AND ACCEPT CANDIDATES",
            icon="queue", accent=cyan, variant="secondary",
            width=230, height=45,
        )
        self._review_button.pack(fill="x", pady=(8, 4))
        self._reports_button = NeonActionButton(
            review_panel.body, "OPEN REPORTS",
            self.open_reports, subtitle="TASK HISTORY  /  AUDIT FILES",
            icon="reports", accent=purple, variant="secondary",
            width=230, height=42,
        )
        self._reports_button.pack(fill="x", pady=(2, 3))

        # OPERATION LOG — actual messages from worker/main-thread activity.
        log_panel = VstPanel(
            deck, "OPERATION LOG  /  SYSTEM CONSOLE",
            tag="CTRL+A SELECT  •  CTRL+C COPY", accent=blue,
        )
        log_panel.pack(fill="both", expand=True, padx=7, pady=(0, 6))
        log_frame = tk.Frame(log_panel.body, bg="#000817")
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(
            log_frame, wrap="word", height=6, font=("Consolas", 8),
            bg="#000817", fg="#9DEFFF", insertbackground=cyan,
            selectbackground="#164C87", relief="sunken", bd=2,
            padx=9, pady=7, borderwidth=2, highlightthickness=1,
            highlightbackground="#174B80", exportselection=True, undo=False,
        )
        log_scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log.yview,
        )
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        self.log.bind("<Control-a>", self.select_log_all)
        self.log.bind("<Control-A>", self.select_log_all)
        self.log.bind("<Control-c>", self.copy_log_selection)
        self.log.bind("<Control-C>", self.copy_log_selection)
        self.log.bind("<Button-3>", self.show_log_context_menu)
        self.log.configure(state="disabled")

        footer = tk.Frame(
            deck, bg="#07172C", bd=2, relief="sunken",
            highlightbackground="#2B6395", highlightthickness=1,
            padx=9, pady=5,
        )
        footer.pack(fill="x", padx=7, pady=(0, 7))
        tk.Label(
            footer, textvariable=self.status, bg="#07172C",
            fg=text, font=("Segoe UI", 8), anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            footer, text="NEON STAGE DEFAULT  •  SKIN-1",
            bg="#07172C", fg=cyan, font=("Consolas", 7, "bold"),
        ).pack(side="right", padx=(8, 0))

        self._write(
            "Manager 3.0 / NEON STAGE DEFAULT загружен.\n"
            "Главный экран: две основные операции — IMPORT SAMPLE GUITAR и START SCAN HUNTING.\n"
            "Графические панели и 3D-кнопки интерактивны; все статусы поступают от реальных операций.\n"
            "IMPORT создаёт проверенные копии; исходные файлы не перемещаются и не удаляются.\n"
            "FACTORY требует REVIEWED + LICENSE_APPROVED + VERIFIED.\n"
        )

    def _copy_log_text(self, value: str) -> None:
        if not value:
            self.status.set("Нечего копировать.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()
        self.status.set(f"Скопировано в буфер обмена: {len(value)} символов.")

    def copy_log_selection(self, event=None):
        try:
            value = self.log.get("sel.first", "sel.last")
        except tk.TclError:
            self.status.set("Сначала выделите нужные строки журнала.")
            return "break" if event else None
        self._copy_log_text(value)
        return "break" if event else None

    def copy_log_all(self):
        self._copy_log_text(self.log.get("1.0", "end-1c"))

    def select_log_all(self, event=None):
        self.log.tag_add("sel", "1.0", "end-1c")
        self.log.mark_set("insert", "1.0")
        self.log.see("insert")
        return "break"

    def show_log_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Копировать выделенное", command=self.copy_log_selection)
        menu.add_command(label="Копировать весь журнал", command=self.copy_log_all)
        menu.add_command(label="Выделить всё", command=self.select_log_all)
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()

    def _write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _load_saved_settings(self) -> dict:
        """Restore the library path and safe UI preferences from the user-data folder."""
        try:
            settings = json.loads(self._settings_path.read_text(encoding="utf-8"))
            if not isinstance(settings, dict):
                return {}
            value = settings.get("samples_root", "")
            samples_root = (
                value if isinstance(value, str) and value.strip()
                and Path(value).expanduser().is_dir() else DEFAULT_SAMPLES
            )
            analyze_audio = settings.get("analyze_audio", True)
            guitar_confirmed = settings.get("guitar_source_confirmed", False)
            return {
                "samples_root": samples_root,
                "analyze_audio": analyze_audio if type(analyze_audio) is bool else True,
                "guitar_source_confirmed": (
                    guitar_confirmed if type(guitar_confirmed) is bool else False
                ),
            }
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def _save_settings(self) -> None:
        """Persist the selected library atomically in UserData / LocalAppData."""
        import os
        import tempfile

        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "samples_root": self.samples_root.get().strip(),
            "analyze_audio": bool(self.analyze_audio.get()),
            "guitar_source_confirmed": bool(self.guitar_confirmed.get()),
            "app_version": APP_VERSION,
        }
        fd, temporary = tempfile.mkstemp(
            prefix="manager_settings-", suffix=".tmp",
            dir=self._settings_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._settings_path)
        except Exception:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _save_settings_from_ui(self) -> None:
        """Persist settings-menu changes without interrupting the current session."""
        try:
            self._save_settings()
        except OSError as exc:
            self._write(f"[ПРЕДУПРЕЖДЕНИЕ] Не удалось сохранить настройки: {exc}")
            self.dialogs.showwarning(
                "Настройки Manager",
                f"Изменения применены в этой сессии, но не сохранены на диск.\n{exc}",
                parent=self.root,
            )

    def _prompt_for_library_root(self) -> None:
        selected = filedialog.askdirectory(
            title="Выберите папку Samples или Import Sample Guitar",
        )
        if not selected:
            self.status.set(
                "Выберите папку библиотеки через меню ПРОЕКТ перед запуском сканирования."
            )
            return
        self.samples_root.set(selected)
        try:
            self._save_settings()
            self.status.set("Папка библиотеки сохранена.")
            self._write(f"Путь Samples сохранён: {selected}")
        except OSError as exc:
            self.dialogs.showwarning(
                "Настройки",
                f"Папка выбрана на этот запуск, но путь не удалось сохранить: {exc}",
            )

    def _samples(self) -> Path:
        """Resolve and log the exact Samples/Import Sample Guitar paths."""
        if not self.samples_root.get().strip():
            self._prompt_for_library_root()
        if not self.samples_root.get().strip():
            raise ValueError("Сначала выберите папку Samples или Import Sample Guitar.")
        selected = Path(self.samples_root.get()).expanduser()
        resolved = resolve_samples_root(selected)
        incoming = next(
            p for p in resolved.iterdir()
            if p.is_dir() and p.name.strip().casefold() == "import sample guitar"
        )
        self._write(f"Путь Samples: {resolved}")
        self._write(f"Путь входной библиотеки: {incoming.resolve()}")
        return resolved

    def choose_samples(self) -> None:
        selected = filedialog.askdirectory(
            title="Выберите Samples ИЛИ непосредственно Import Sample Guitar"
        )
        if selected:
            self.samples_root.set(selected)
            try:
                self._save_settings()
            except OSError as exc:
                self.dialogs.showwarning(
                    "Настройки",
                    f"Папка выбрана на этот запуск, но путь не удалось сохранить: {exc}",
                )

    def _background(self, title: str, work) -> None:
        """Run work off the UI thread and deliver all UI updates via a queue."""
        if self._job_running:
            self._write(f"[ОТКАЗ] Уже выполняется другая операция: {title}")
            self.status.set("Дождитесь завершения текущей операции.")
            return

        self._job_running = True
        self._cancel_event.clear()
        self._progress_stage = 0
        self._progress_stage_total = 0
        self._progress_title.set("RUNNING  /  " + title.upper())
        self._progress_detail.set("Запуск рабочего процесса…")
        self._progress_bar.configure(mode="indeterminate", value=0)
        self._progress_bar.start(12)
        self._active_task_title = title
        task_id = self._task_journal.start(
            title, details={"samples_root": self.samples_root.get(), "manager_version": APP_VERSION}
        )
        self._active_task_id = task_id
        self._cancel_button.configure(state="normal")
        self.status.set(title + " — запуск…")
        for button in self._action_buttons:
            button.configure(state="disabled")
        self._write(f"[ЗАДАЧА] Запуск фонового потока: {title}")

        def runner():
            try:
                result = work()
                if self._cancel_event.is_set():
                    self._task_journal.cancel(task_id, title)
                    self._worker_events.put(("cancelled", title, result))
                else:
                    self._task_journal.finish(task_id, title, result=result)
                    self._worker_events.put(("finish", title, result))
            except Exception as exc:
                if self._cancel_event.is_set():
                    self._task_journal.cancel(task_id, title, f"{type(exc).__name__}: {exc}")
                    self._worker_events.put(("cancelled", title, {"error": f"{type(exc).__name__}: {exc}"}))
                else:
                    self._task_journal.fail(task_id, title, f"{type(exc).__name__}: {exc}")
                    self._worker_events.put(("error", title, f"{type(exc).__name__}: {exc}", traceback.format_exc()))

        worker = threading.Thread(target=runner, name="LibraryManagerWorker", daemon=True)
        self._worker_thread = worker
        try:
            worker.start()
        except Exception as exc:
            self._task_journal.fail(task_id, title, f"{type(exc).__name__}: {exc}")
            self._job_running = False
            self._worker_thread = None
            self._progress_bar.stop()
            self._progress_title.set("ERROR  /  ОШИБКА")
            self._progress_detail.set(f"{type(exc).__name__}: {exc}")
            for button in self._action_buttons:
                button.configure(state="normal")
            details = traceback.format_exc()
            self._error(title, exc, details)

    def _queue_progress(self, message: str) -> None:
        """Persist worker progress and forward it to the Tk main thread."""
        task_id = self._active_task_id
        task = self._active_task_title
        if task_id and task:
            self._task_journal.progress(task_id, task, message)
        self._worker_events.put(("progress", message))

    def _poll_worker_events(self) -> None:
        """Process worker events only on Tk's main thread."""
        try:
            while True:
                event = self._worker_events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._progress(event[1])
                elif kind == "finish":
                    _, title, result = event
                    self._job_running = False
                    self._worker_thread = None
                    self._progress_bar.stop()
                    self._progress_bar.configure(mode="determinate", value=100)
                    self._progress_title.set("COMPLETE  /  ЗАВЕРШЕНО")
                    self._cancel_button.configure(state="disabled")
                    for button in self._action_buttons:
                        button.configure(state="normal")
                    self._finish(title, result)
                elif kind == "cancelled":
                    _, title, result = event
                    self._job_running = False
                    self._worker_thread = None
                    self._progress_bar.stop()
                    self._progress_title.set("CANCELLED  /  ОСТАНОВЛЕНО")
                    self._progress_detail.set("Безопасная остановка. Исходники сохранены; частичные отчёты оставлены.")
                    self._cancel_button.configure(state="disabled")
                    for button in self._action_buttons:
                        button.configure(state="normal")
                    self._write("[ОСТАНОВЛЕНО] " + json.dumps(result, ensure_ascii=False, indent=2, default=str))
                    self.status.set(title + ": остановлено; частичные отчёты сохранены")
                elif kind == "error":
                    _, title, error_text, details = event
                    self._job_running = False
                    self._worker_thread = None
                    self._progress_bar.stop()
                    self._progress_title.set("ERROR  /  ОШИБКА")
                    self._progress_detail.set(error_text)
                    self._cancel_button.configure(state="disabled")
                    for button in self._action_buttons:
                        button.configure(state="normal")
                    self._write(f"[ОШИБКА] {error_text}")
                    self._write(details)
                    self.status.set(title + ": ошибка")
                    self.dialogs.showerror("Ошибка", error_text)
        except queue.Empty:
            pass
        finally:
            try:
                self.root.after(100, self._poll_worker_events)
            except tk.TclError:
                # Window is already closing.
                pass

    def _finish(self, title: str, result) -> None:
        """Write a compact result card; full machine reports stay in report files."""
        if "IMPORT GUITAR" in str(title).upper():
            import_summary, import_detail = build_import_completion_summary(
                result if isinstance(result, dict) else {}
            )
            self._write("[ИТОГ IMPORT GUITAR] " + json.dumps(
                import_summary, ensure_ascii=False, default=str, separators=(",", ":")
            ))
            self._write(import_detail)
            self._progress_title.set("IMPORT COMPLETE  /  ИМПОРТ ЗАВЕРШЁН")
            self._progress_detail.set(
                f"Копий SHA-256: {import_summary['copied_files']}  •  "
                f"зарегистрировано: {import_summary['registered_files']}  •  "
                f"уже было: {import_summary['already_registered']}  •  "
                f"архивов в инвентаризации: {import_summary['archives']}  •  "
                f"ошибок: {import_summary['errors']}"
            )
            warning = bool(
                import_summary["errors"] or import_summary["sfz_dependencies_blocked"]
            )
            self.status.set(
                title + (": завершено с предупреждениями" if warning else ": завершено")
            )
            return

        def select_fields(value, fields):
            if not isinstance(value, dict):
                return value
            return {key: value[key] for key in fields if key in value}

        summary = {}
        if isinstance(result, dict):
            summary["quick_scan"] = select_fields(
                result.get("quick_scan"),
                ("files_found", "directories_scanned", "elapsed_seconds", "report_directory"),
            )
            summary["deep_analysis"] = select_fields(
                result.get("deep_analysis"),
                ("files_scanned", "wav_files", "sfz_files", "audio_files_analyzed",
                 "mode_candidates_total", "errors", "report_directory", "workers"),
            )
            summary["physical_extraction"] = select_fields(
                result.get("physical_extraction"),
                ("long_recording_region_wav_count", "pattern_instrument_wav_count",
                 "chord_and_power_chord_wav_count", "sample_mode_wav_count",
                 "melody_mode_single_note_bindings", "melody_mode_phrase_wav_count",
                 "total_new_wav_candidates", "manifest_count_in_staging", "review_status",
                 "license_status"),
            )
            extraction = result.get("physical_extraction") or {}
            summary["physical_extraction_failures"] = len(
                extraction.get("failures", []) if isinstance(extraction, dict) else []
            )
            summary["factory_distribution"] = select_fields(
                result.get("factory_distribution"),
                ("status", "manifests_seen", "ready_count", "already_present_count",
                 "copied_count", "journal_path", "finalization_error"),
            )
            summary["other_routing"] = select_fields(
                result.get("other_routing"),
                ("status", "candidates_seen", "copied_count", "already_present_count",
                 "error_count"),
            )
            summary["plugin_asset_catalog"] = select_fields(
                result.get("plugin_asset_catalog"),
                ("asset_count", "playable_asset_count", "candidate_count", "status"),
            )
            summary["performance_manifest"] = select_fields(
                result.get("performance_manifest"),
                ("asset_binding_count", "event_count", "runtime_status"),
            )
            structure = result.get("library_structure") or {}
            summary["library_structure"] = select_fields(
                structure.get("summary"),
                ("unique_asset_count", "mode_assignment_count",
                 "runtime_ready_assignment_count", "pattern_structure_verified_count",
                 "melody_structure_verified_count"),
            )
            summary["source_files_modified"] = result.get("source_files_modified", False)
            summary["source_files_moved_or_deleted"] = result.get("source_files_moved_or_deleted", False)

        self._write("[ИТОГ SCAN HUNTING] " + json.dumps(
            summary or result, ensure_ascii=False, default=str, separators=(",", ":")
        ))
        factory = result.get("factory_distribution", {}) if isinstance(result, dict) else {}
        other = result.get("other_routing", {}) if isinstance(result, dict) else {}
        candidates = result.get("physical_extraction", {}) if isinstance(result, dict) else {}
        extraction_failures = (
            len(candidates.get("failures", [])) if isinstance(candidates, dict) else 0
        )
        analysis = result.get("deep_analysis", {}) if isinstance(result, dict) else {}
        analysis_errors = analysis.get("errors", 0) if isinstance(analysis, dict) else 0
        if isinstance(analysis_errors, list):
            analysis_errors = len(analysis_errors)
        try:
            analysis_errors = int(analysis_errors or 0)
        except (TypeError, ValueError):
            analysis_errors = 1
        warning_count = extraction_failures + analysis_errors + int(other.get("error_count", 0) or 0)
        self._progress_title.set(
            "COMPLETE WITH WARNINGS  /  ЗАВЕРШЕНО С ПРЕДУПРЕЖДЕНИЯМИ"
            if warning_count else "COMPLETE  /  ЗАВЕРШЕНО"
        )
        self._progress_bar.stop()
        self._progress_bar.configure(mode="determinate", value=100)
        self._progress_detail.set(
            f"Кандидатов WAV: {candidates.get('total_new_wav_candidates', 0)}  •  "
            f"FACTORY: {factory.get('copied_count', 0)} новых / "
            f"{factory.get('already_present_count', 0)} уже проверено  •  "
            f"OTHER: {other.get('copied_count', 0)} копий / "
            f"{other.get('error_count', 0)} ошибок  •  "
            f"сбоев извлечения: {extraction_failures}  •  ошибок анализа: {analysis_errors}"
        )
        self.status.set(
            title + (": завершено с предупреждениями" if warning_count else ": завершено")
        )

    def _error(self, title: str, exc: Exception, details: str) -> None:
        self._write(details)
        self.status.set(title + ": ошибка")
        self.dialogs.showerror("Ошибка", f"{type(exc).__name__}: {exc}")

    def cancel_job(self) -> None:
        if self._job_running:
            self._cancel_event.set()
            self._cancel_button.configure(state="disabled")
            self.status.set("Остановка запрошена — завершаю текущий безопасный блок…")
            self._write("[ОТМЕНА] Запрошена остановка. Исходные файлы не затрагиваются.")

    def _prepare_import_target(self) -> Path | None:
        """Create/resolve the active Samples folder and its incoming destination."""
        chosen = self.samples_root.get().strip()
        if not chosen:
            chosen = filedialog.askdirectory(
                title="Выберите или создайте папку Samples для библиотеки Manager",
            )
            if not chosen:
                return None

        selected = Path(chosen).expanduser().resolve()
        if not selected.is_dir():
            raise NotADirectoryError(f"Выбранный каталог Samples не существует: {selected}")

        if selected.name.strip().casefold() == "import sample guitar":
            samples = selected.parent
            incoming = selected
        else:
            samples = selected
            children = [
                item for item in samples.iterdir()
                if item.is_dir() and item.name.strip().casefold() == "import sample guitar"
            ]
            if len(children) > 1:
                raise RuntimeError(
                    "В выбранной папке найдено несколько Import Sample Guitar. "
                    "Выберите нужную входную папку напрямую."
                )
            incoming = children[0] if children else samples / "Import Sample Guitar"

        incoming.mkdir(parents=True, exist_ok=True)
        (samples / "FACTORY").mkdir(parents=True, exist_ok=True)
        (samples / "OTHER").mkdir(parents=True, exist_ok=True)
        self.samples_root.set(str(samples))
        self._save_settings()
        self._write(f"Целевая папка импорта: {incoming}")
        return incoming

    def import_guitar(self) -> None:
        """Copy selected source libraries into Import Sample Guitar, preserving originals."""
        try:
            incoming = self._prepare_import_target()
        except Exception as exc:
            self.dialogs.showerror("IMPORT GUITAR — папка библиотеки", str(exc), parent=self.root)
            return
        if incoming is None:
            self.status.set("IMPORT GUITAR: папка Samples не выбрана.")
            return

        selected = list(filedialog.askopenfilenames(
            title="IMPORT GUITAR — выберите аудио, SFZ или архивы",
            filetypes=[
                ("Поддерживаемые материалы", "*.wav *.wave *.aif *.aiff *.flac *.ogg *.oga *.mp3 *.m4a *.aac *.wma *.opus *.sfz *.zip *.7z *.rar"),
                ("Все файлы", "*.*"),
            ],
        ))
        while self.dialogs.askyesno(
            "IMPORT GUITAR",
            "Добавить целую папку библиотеки? Можно добавить несколько папок подряд.",
            parent=self.root,
        ):
            folder = filedialog.askdirectory(title="Выберите папку исходной гитарной библиотеки")
            if not folder:
                break
            selected.append(folder)
        if not selected:
            self.status.set("IMPORT GUITAR: источники не выбраны.")
            return

        if not self.dialogs.askyesno(
            "Подтверждение импорта",
            f"Менеджер создаст проверенные копии выбранных файлов в:\n{incoming}\n\n"
            "Оригиналы останутся на прежнем месте и не будут изменены, перемещены или удалены. "
            "Для копирования требуется дополнительное место на диске. "
            "После импорта копии будут доступны SCAN HUNTING. Архивы сохраняются целиком и "
            "учитываются как архивы; Manager не распаковывает ZIP / 7Z / RAR автоматически. "
            "Продолжить?",
            parent=self.root,
        ):
            self.status.set("IMPORT GUITAR: копирование отменено.")
            return

        registry = MANAGER_DIR / "reports" / "import_registry.json"

        def work():
            return import_sources_to_library(
                selected,
                incoming,
                registry,
                progress=self._queue_progress,
                cancel_event=self._cancel_event,
            )

        self._write("=== IMPORT GUITAR ===")
        self._write(f"Выбрано источников: {len(selected)}. Будут созданы SHA-256-проверенные копии; оригиналы останутся нетронутыми.")
        self._background("IMPORT GUITAR — копирование и регистрация источников", work)

    def quick_scan_only(self) -> None:
        """Run only the fast filesystem inventory; never start deep analysis."""
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return

        def work():
            def report_progress(message: str) -> None:
                self._queue_progress(message)
            return quick_scan(
                samples, progress=report_progress, cancel_event=self._cancel_event,
            )

        self._write("=== БЫСТРОЕ СКАНИРОВАНИЕ ===")
        self._write("Только обход Import Sample Guitar и чтение файловой метаинформации. SHA-256, декодирование и анализ не запускаются.")
        self._background("Быстрое сканирование", work)

    def deep_scan_only(self) -> None:
        """Run full file inventory/hash cache without acoustic decoding or extraction."""
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return

        def work():
            def report_progress(message: str) -> None:
                self._queue_progress(message)

            report_progress("ЭТАП 1/2: быстрый filesystem scan без SHA-256 и декодирования.")
            quick_result = quick_scan(
                samples, progress=report_progress, cancel_event=self._cancel_event,
            )
            if self._cancel_event.is_set():
                raise RuntimeError("Глубокий анализ остановлен после быстрого сканирования.")
            report_progress("ЭТАП 2/2: глубокая инвентаризация, SHA-256 cache, форматы и SFZ. Аудио не декодируется.")
            deep_result = run_manager(
                samples,
                analyze_audio=False,
                guitar_source_confirmed=False,
                write_virtual=False,
                progress=report_progress,
                cancel_event=self._cancel_event,
                workers=1,
            )
            return {
                "quick_scan": quick_result,
                "deep_inventory": deep_result,
                "acoustic_analysis_performed": False,
                "physical_extraction_performed": False,
                "workers": 1,
                "source_files_modified": False,
            }

        self._write("=== БЫСТРЫЙ ГЛУБОКИЙ АНАЛИЗ ===")
        self._write("Проверка форматов, размеров, SHA-256/кэша, точных дубликатов и SFZ. Без pitch/YIN, акустического декодирования и извлечения WAV.")
        self._write("На первом проходе SHA-256 читает аудиофайлы; последующие проходы используют кэш неизменённых файлов.")
        self._background("Быстрый глубокий анализ", work)

    def scan_hunting(self) -> None:
        """Run the complete scan, analysis, extraction and catalogue preparation flow."""
        self._write("=== SCAN HUNTING: ПОЛНЫЙ ПРОХОД Import Sample Guitar ===")
        self._write("Запускаются все рабочие этапы существующего полного конвейера. Быстрый и глубокий scan, аудиоанализ, поиск и извлечение выполняются одной последовательностью.")
        self.scan()

    def scan(self) -> None:
        """Run the complete preparation pipeline after the fast scan."""
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        analyze_audio = self.analyze_audio.get()
        guitar_confirmed = self.guitar_confirmed.get()
        if analyze_audio and not guitar_confirmed:
            guitar_confirmed = self.dialogs.askyesno(
                "Подтверждение гитарного источника",
                "Подтверждаете, что выбранная библиотека предназначена для гитарного плагина "
                "и уже очищена от Piano / Bell / Drum материалов?\n\n"
                "При ответе «Нет» Manager всё равно завершит инвентаризацию и акустический анализ, "
                "но не будет запускать гитарное извлечение Pattern / Chord / Sample / Melody.",
            )
            if guitar_confirmed:
                self.guitar_confirmed.set(True)
                try:
                    self._save_settings()
                except OSError as exc:
                    self._write(f"[ПРЕДУПРЕЖДЕНИЕ] Не удалось сохранить подтверждение источника: {exc}")

        def work():
            def report_progress(message: str) -> None:
                self._queue_progress(message)

            report_progress("ЭТАП 1/8: быстрое сканирование структуры — только файловая метаинформация.")
            quick_result = quick_scan(
                samples, progress=report_progress, cancel_event=self._cancel_event,
            )
            if self._cancel_event.is_set():
                raise RuntimeError("Полный цикл остановлен после быстрого сканирования.")
            report_progress("ЭТАП 2/8: глубокая инвентаризация, SHA-256 cache, форматы, дубликаты и SFZ.")
            analysis_result = run_manager(
                samples,
                analyze_audio=analyze_audio,
                guitar_source_confirmed=guitar_confirmed,
                write_virtual=bool(analyze_audio and guitar_confirmed),
                progress=report_progress,
                cancel_event=self._cancel_event,
                workers=1,
            )

            mode_counts = analysis_result.get("mode_candidate_counts", {})
            mode_report_path = Path(analysis_result["report_directory"]) / "mode_sorting_report.json"
            report_progress(
                "КЛАССИФИКАЦИЯ ПО 10 КАТЕГОРИЯМ ПОДГОТОВКИ БИБЛИОТЕКИ ДЛЯ VST3: "
                + "; ".join(f"{name}: {count}" for name, count in mode_counts.items())
                + f". Отчёт: {mode_report_path}"
            )

            extracted_region = 0
            extracted_pattern = 0
            extracted_chord = 0
            extracted_sample = 0
            extracted_melody_notes = 0
            extracted_melody = 0
            extraction_failures = []
            report_file = Path(analysis_result["report_directory"]) / "unified_audio_analysis.json"
            if analyze_audio and guitar_confirmed and report_file.is_file():
                records = json.loads(report_file.read_text(encoding="utf-8"))
                from pattern_clip_extractor import extract_pattern_occurrences
                from sample_melody_pipeline import prepare_sample_and_melody
                from virtual_sample_extractor import extract_virtual_ranges

                report_progress("ЭТАП 3/8: извлечение реальных WAV-отрывков из длинных гитарных записей.")
                for record in records:
                    if self._cancel_event.is_set():
                        raise RuntimeError("Извлечение остановлено; уже созданные staging-кандидаты сохранены.")
                    virtual = record.get("virtual_extraction")
                    if not isinstance(virtual, dict) or not virtual.get("candidates"):
                        continue
                    try:
                        candidates = virtual.get("candidates") or []
                        for offset in range(0, len(candidates), 1000):
                            if self._cancel_event.is_set():
                                raise RuntimeError("Извлечение длинных отрывков остановлено.")
                            chunk_report = {
                                **virtual,
                                "candidates": candidates[offset:offset + 1000],
                            }
                            clips = extract_virtual_ranges(
                                chunk_report, STAGING_ROOT,
                                max_clips=1000,
                                cancel_event=self._cancel_event,
                                progress=report_progress,
                            )
                            extracted_region += len(clips)
                    except Exception as exc:
                        if self._cancel_event.is_set():
                            raise
                        extraction_failures.append({
                            "source_path": record.get("source_path"),
                            "stage": "LONG_RECORDING_RANGE_EXTRACTION",
                            "error": f"{type(exc).__name__}: {exc}",
                        })

                report_progress("ЭТАП 4/8: извлечение WAV повторяющихся ритм-паттернов.")
                for record in records:
                    if self._cancel_event.is_set():
                        raise RuntimeError("Извлечение остановлено; созданные staging-кандидаты сохранены.")
                    pattern_data = (record.get("pattern_analysis") or {}).get("pattern_analysis", {})
                    if not pattern_data.get("patterns"):
                        continue
                    try:
                        source_report = {
                            "source": record["source_path"],
                            "source_sha256": record["source_sha256"],
                        }
                        patterns = pattern_data.get("patterns") or []
                        # Split large candidate sets into bounded chunks. This
                        # removes the old global 500-asset ceiling without
                        # building one enormous in-memory extraction batch.
                        for pattern in patterns:
                            occurrences = pattern.get("occurrences") or []
                            for offset in range(0, len(occurrences), 10000):
                                if self._cancel_event.is_set():
                                    raise RuntimeError("Извлечение Pattern остановлено.")
                                chunk_pattern = {
                                    **pattern,
                                    "occurrences": occurrences[offset:offset + 10000],
                                }
                                chunk_analysis = {"patterns": [chunk_pattern]}
                                clips = extract_pattern_occurrences({
                                    **source_report,
                                    "pattern_analysis": chunk_analysis,
                                }, STAGING_ROOT, max_clips=10000,
                                    cancel_event=self._cancel_event)
                                extracted_pattern += len(clips)
                    except Exception as exc:
                        if self._cancel_event.is_set():
                            raise
                        extraction_failures.append({
                            "source_path": record.get("source_path"),
                            "stage": "PATTERN_EXTRACTION",
                            "error": f"{type(exc).__name__}: {exc}",
                        })

                report_progress("ЭТАП 5/8: извлечение аккордовых и Power Chord WAV-кандидатов для категории SAMPLE MODE библиотеки VST3 и AutoChords внутри PATTERN.")
                from chord_clip_extractor import extract_chord_samples
                for record in records:
                    if self._cancel_event.is_set():
                        raise RuntimeError("Извлечение аккордов остановлено; созданные staging-кандидаты сохранены.")
                    chord_data = record.get("chord_analysis") or {}
                    if not chord_data.get("chord_candidates"):
                        continue
                    try:
                        candidates = chord_data.get("chord_candidates") or []
                        for offset in range(0, len(candidates), 5000):
                            if self._cancel_event.is_set():
                                raise RuntimeError("Извлечение Chord остановлено.")
                            chunk_report = {
                                **chord_data,
                                "chord_candidates": candidates[offset:offset + 5000],
                            }
                            clips = extract_chord_samples(
                                chunk_report, STAGING_ROOT, max_clips=5000,
                                cancel_event=self._cancel_event,
                            )
                            extracted_chord += len(clips)
                    except Exception as exc:
                        if self._cancel_event.is_set():
                            raise
                        extraction_failures.append({
                            "source_path": record.get("source_path"),
                            "stage": "CHORD_SAMPLE_EXTRACTION",
                            "error": f"{type(exc).__name__}: {exc}",
                        })

                report_progress("ЭТАП 6/8: извлечение одиночных нот для категорий SAMPLE MODE и MELODY MODE библиотеки VST3; дополнительные фразы для категории MELODY MODE.")
                for record in records:
                    if self._cancel_event.is_set():
                        raise RuntimeError("Извлечение остановлено; созданные staging-кандидаты сохранены.")
                    source = Path(record.get("source_path", ""))
                    if source.suffix.lower() not in AUDIO_EXT:
                        continue
                    try:
                        pitch_events = record.get("pitch_candidates") or []
                        # This engine processes the full per-source event list;
                        # note WAVs are shared by Sample and Melody assignments.
                        source_asset_budget = max(1, len(pitch_events) * 2)
                        result = prepare_sample_and_melody(
                            source, STAGING_ROOT,
                            max_note_events=max(1, len(pitch_events) or 500),
                            max_assets=source_asset_budget,
                            pitch_candidates=record.get("pitch_candidates"),
                            expected_source_sha256=record.get("source_sha256"),
                            source_metadata=record.get("filename_metadata"),
                            cancel_event=self._cancel_event,
                        )
                        extracted_sample += result["sample_mode_count"]
                        extracted_melody_notes += result.get("melody_note_mode_count", 0)
                        extracted_melody += result["melody_mode_count"]
                        if result["sample_mode_count"] + result["melody_mode_count"] == 0:
                            extraction_failures.append({
                                "source_path": str(source),
                                "stage": "SAMPLE_MELODY_EXTRACTION",
                                "error": "Не обнаружены надёжные кандидаты pitch-events; WAV не создан.",
                            })
                    except Exception as exc:
                        if self._cancel_event.is_set():
                            raise
                        extraction_failures.append({
                            "source_path": str(source),
                            "stage": "SAMPLE_MELODY_EXTRACTION",
                            "error": f"{type(exc).__name__}: {exc}",
                        })
            elif analyze_audio and not guitar_confirmed:
                extraction_failures.append({
                    "stage": "EXTRACTION_GATE",
                    "error": "Физическое извлечение пропущено: оператор не подтвердил гитарный источник.",
                })

            report_progress(
                "ИТОГ ИЗВЛЕЧЕНИЯ: длинные отрывки=" + str(extracted_region)
                + "; Pattern WAV=" + str(extracted_pattern)
                + "; Chord WAV=" + str(extracted_chord)
                + "; Sample WAV=" + str(extracted_sample)
                + "; Melody WAV=" + str(extracted_melody)
                + "; ошибок=" + str(len(extraction_failures))
            )
            if self._cancel_event.is_set():
                raise RuntimeError("Полный цикл остановлен до финализации; исходные файлы не изменены.")

            report_progress("ЭТАП 7/8: распределение проверенных кандидатов в FACTORY по музыкальным категориям. Только REVIEWED + LICENSE_APPROVED + SHA-256 VERIFIED.")
            factory_distribution_result = auto_distribute_approved(
                samples, STAGING_ROOT,
                approve=True,
                journal_path=samples / "FACTORY" / "LibraryManagerReports" / "operations.jsonl",
                cancel_event=self._cancel_event,
                progress=report_progress,
            )
            if self._cancel_event.is_set():
                raise RuntimeError("Полный цикл остановлен во время распределения FACTORY; уже проверенные копии сохранены, исходники не затронуты.")
            finalization_result = factory_distribution_result.get("finalization")
            if finalization_result is None:
                report_progress("Дополнительный аудит staging / FACTORY после незавершённого шага распределения.")
                finalization_result = finalize_library_audit(
                    samples, STAGING_ROOT,
                    progress=report_progress,
                    cancel_event=self._cancel_event,
                )

            report_progress("ЭТАП 8/8: копирование объективно неподдерживаемых файлов в OTHER и сборка каталога VST3.")
            other_routing_result = copy_unsupported_to_other(
                samples, progress=report_progress, cancel_event=self._cancel_event,
            )
            if self._cancel_event.is_set():
                raise RuntimeError("Полный цикл остановлен на этапе OTHER; исходные файлы сохранены.")
            catalog_path = Path(analysis_result["report_directory"]) / "plugin_asset_catalog.json"
            catalog_result = build_plugin_asset_catalog(
                STAGING_ROOT,
                catalog_path,
                mode_report_path=mode_report_path if mode_report_path.is_file() else None,
                pattern_engine_manifest_path=(
                    Path(analysis_result["report_directory"]) / "pattern_engine_manifest.json"
                ),
            )
            report_progress("ГРУППИРОВКА SESSION GUITARIST: разделяю PATTERN performances / note zones и отдельные MELODY notes / phrases без дублирования WAV.")
            chromatic_path = Path(analysis_result["report_directory"]) / "chromatic_pitch_map.json"
            chromatic_map = build_chromatic_pitch_map(json.loads(catalog_path.read_text(encoding="utf-8")))
            chromatic_path.write_text(
                json.dumps(chromatic_map, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            performance_path = Path(analysis_result["report_directory"]) / "performance_manifest.json"
            performance_result = build_performance_manifest(
                catalog_path, performance_path, chromatic_pitch_map=chromatic_map,
            )
            structure_path = Path(analysis_result["report_directory"]) / "plugin_library_structure.json"
            coverage_path = Path(analysis_result["report_directory"]) / "plugin_library_coverage.json"
            structure_result = write_library_structure(
                catalog_path, structure_path, coverage_path,
            )
            if structure_result.get("validation_errors"):
                raise RuntimeError(
                    "PATTERN / MELODY library structure invalid: "
                    + "; ".join(structure_result["validation_errors"])
                )
            report_progress(
                f"FACTORY distribution: {factory_distribution_result.get('copied_count', 0)} new, "
                f"{factory_distribution_result.get('already_present_count', 0)} verified existing. "
                f"OTHER: {other_routing_result.get('copied_count', 0)} unsupported copies. "
                f"PATTERN structure verified: {structure_result['summary'].get('pattern_structure_verified_count', 0)}; "
                f"MELODY structure verified: {structure_result['summary'].get('melody_structure_verified_count', 0)}."
            )
            report_progress(
                f"Каталог VST3: {catalog_result['asset_count']} staged assets, "
                f"{catalog_result['playable_asset_count']} runtime-ready, "
                f"{catalog_result['candidate_count']} analysis candidates. "
                f"Performance Manifest: {performance_result['asset_binding_count']} bindings, "
                f"{performance_result['event_count']} reviewed events. "
                f"Library structure: {structure_path}; coverage: {coverage_path}; "
                f"chromatic map: {chromatic_path}."
            )
            return {
                "quick_scan": quick_result,
                "deep_analysis": analysis_result,
                "physical_extraction": {
                    "long_recording_region_wav_count": extracted_region,
                    "pattern_instrument_wav_count": extracted_pattern,
                    "chord_and_power_chord_wav_count": extracted_chord,
                    "sample_mode_wav_count": extracted_sample,
                    "melody_mode_single_note_bindings": extracted_melody_notes,
                    "melody_mode_phrase_wav_count": extracted_melody,
                    "total_new_wav_candidates": extracted_region + extracted_pattern + extracted_chord + extracted_sample + extracted_melody,
                    "extraction_batching": "CHUNKED_PER_ENGINE_NO_GLOBAL_500_ASSET_CAP",
                    "manifest_count_in_staging": finalization_result["staging"]["manifests_checked"],
                    "failures": extraction_failures,
                    "review_status": "NEEDS_MUSICAL_REVIEW",
                    "license_status": "UNREVIEWED",
                },
                "finalization": finalization_result,
                "factory_distribution": factory_distribution_result,
                "other_routing": other_routing_result,
                "plugin_asset_catalog": catalog_result,
                "performance_manifest": performance_result,
                "library_structure": structure_result,
                "chromatic_pitch_map": {
                    "path": str(chromatic_path),
                    "pitch_class_count": len(chromatic_map["pitch_classes"]),
                    "midi_key_count": chromatic_map["coverage"]["midi_key_count"],
                    "exact_sample_count": chromatic_map["coverage"]["exact_approved_sample_count"],
                    "fallback_proposal_count": chromatic_map["coverage"]["fallback_proposal_count"],
                    "missing_source_count": chromatic_map["coverage"]["missing_source_count"],
                    "runtime_status": chromatic_map["runtime_status"],
                },
                "source_files_modified": False,
                "source_files_moved_or_deleted": False,
            }

        self._write("=== ПОЛНЫЙ ЦИКЛ ПОДГОТОВКИ БИБЛИОТЕКИ ===")
        self._write("Полный цикл: SCAN → аудиоанализ / сортировка → извлечение WAV → Factory review-gated distribution → OTHER unsupported copies → финальный каталог.")
        self._write("В FACTORY попадают только ранее вручную REVIEWED + LICENSE_APPROVED материалы с подтверждёнными SHA-256 и границами. Неподтверждённые аудио остаются в staging/Import для проверки; только неподдерживаемые типы копируются в OTHER.")
        self._write(f"Акустический анализ: {'ВКЛЮЧЁН' if analyze_audio else 'ВЫКЛЮЧЕН'}")
        self._write(f"Гитарный источник подтверждён: {'ДА' if guitar_confirmed else 'НЕТ'}")
        self._background("SCAN HUNTING — полный проход и анализ Import Sample Guitar", work)

    def _progress(self, message: str) -> None:
        """Render bounded live status/progress updates on Tk's main thread."""
        self._write("[ВЫПОЛНЯЕТСЯ] " + message)
        if self._active_task_id:
            try:
                self._task_journal.progress(self._active_task_id, self._active_task_title or "Background task", message)
            except OSError as exc:
                self._write(f"[ПРЕДУПРЕЖДЕНИЕ] Не удалось записать историю: {exc}")

        self.status.set(message)
        self._progress_title.set("RUNNING  /  " + (self._active_task_title or "SCAN HUNTING").upper())
        self._progress_detail.set(message)

        stage = re.search(r"(?:ЭТАП|STAGE)\s*(\d+)\s*/\s*(\d+)", message, re.IGNORECASE)
        if stage:
            self._progress_stage = int(stage.group(1))
            self._progress_stage_total = max(1, int(stage.group(2)))
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate")
            self._progress_bar["value"] = 100.0 * self._progress_stage / self._progress_stage_total
            self._progress_detail.set(
                f"Этап {self._progress_stage}/{self._progress_stage_total}  •  {message}"
            )
            return

        ratio = re.search(
            r"(?:Обработка|проверено манифестов|проверено неподдерживаемых файлов|"
            r"обработано|проверено файлов|быстрый обход)[^0-9]*(\d[\d, ]*)\s*/\s*(\d[\d, ]*)",
            message, re.IGNORECASE,
        )
        if ratio:
            done = int(re.sub(r"\D", "", ratio.group(1)) or "0")
            total = max(1, int(re.sub(r"\D", "", ratio.group(2)) or "1"))
            fraction = max(0.0, min(1.0, done / total))
            overall = (
                ((self._progress_stage - 1 + fraction) / self._progress_stage_total) * 100.0
                if self._progress_stage_total else fraction * 100.0
            )
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate")
            self._progress_bar["value"] = overall
            self._progress_detail.set(
                f"Обработано {done:,} / {total:,}  •  {fraction:.0%} текущего этапа  •  {message}"
            )

    def show_task_history(self) -> None:
        """Display last known task states from the durable journal."""
        try:
            states = self._task_journal.latest_states()
            if not states:
                self._write("История задач пока пуста.")
                return
            self._write("=== ИСТОРИЯ ЗАДАЧ ===")
            for task_id, state in list(states.items())[-100:]:
                self._write(
                    f"{state.get('last_timestamp_utc')} | {state.get('task')} | "
                    f"{state.get('last_event')} | id={task_id}"
                )
            self._write(f"Полный журнал: {self._task_journal.path}")
        except OSError as exc:
            self.dialogs.showerror("История задач", str(exc))

    def preview_audio(self) -> None:
        selected = filedialog.askopenfilename(
            title="Выберите WAV для предпрослушивания",
            filetypes=[("WAV audio", "*.wav *.wave")],
        )
        if not selected:
            return
        try:
            import winsound
            winsound.PlaySound(selected, winsound.SND_FILENAME | winsound.SND_ASYNC)
            self._write("Предпрослушивание: " + selected)
            self.status.set("Воспроизведение WAV")
        except Exception as exc:
            self.dialogs.showerror("Предпрослушивание", f"Не удалось воспроизвести WAV: {exc}")

    def stop_preview(self) -> None:
        try:
            import winsound
            winsound.PlaySound(None, 0)
            self.status.set("Воспроизведение остановлено")
        except Exception as exc:
            self.dialogs.showerror("Предпрослушивание", str(exc))

    def build_plugin_catalog(self) -> None:
        """Build a validated plugin catalog from existing staged WAV manifests."""
        reports_root = MANAGER_DIR / "reports"
        mode_reports = sorted(
            reports_root.glob("run_*/mode_sorting_report.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        pattern_manifests = sorted(
            reports_root.glob("run_*/pattern_engine_manifest.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output = reports_root / f"plugin_asset_catalog_{stamp}.json"

        def work():
            catalog_result = build_plugin_asset_catalog(
                STAGING_ROOT,
                output,
                mode_report_path=mode_reports[0] if mode_reports else None,
                pattern_engine_manifest_path=pattern_manifests[0] if pattern_manifests else None,
            )
            chromatic_output = output.with_name(output.stem.replace(
                "plugin_asset_catalog", "chromatic_pitch_map"
            ) + ".json")
            chromatic_map = build_chromatic_pitch_map(json.loads(output.read_text(encoding="utf-8")))
            performance_output = output.with_name(output.stem.replace(
                "plugin_asset_catalog", "performance_manifest"
            ) + ".json")
            performance_result = build_performance_manifest(
                output, performance_output, chromatic_pitch_map=chromatic_map
            )
            structure_output = output.with_name(output.stem.replace(
                "plugin_asset_catalog", "plugin_library_structure"
            ) + ".json")
            coverage_output = output.with_name(output.stem.replace(
                "plugin_asset_catalog", "plugin_library_coverage"
            ) + ".json")
            structure_result = write_library_structure(output, structure_output, coverage_output)
            chromatic_output.write_text(json.dumps(chromatic_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return {
                "plugin_asset_catalog": catalog_result,
                "performance_manifest": performance_result,
                "library_structure": structure_result,
                "chromatic_pitch_map": {
                    "path": str(chromatic_output),
                    "pitch_class_count": len(chromatic_map["pitch_classes"]),
                    "midi_key_count": chromatic_map["coverage"]["midi_key_count"],
                    "exact_sample_count": chromatic_map["coverage"]["exact_approved_sample_count"],
                    "fallback_proposal_count": chromatic_map["coverage"]["fallback_proposal_count"],
                    "missing_source_count": chromatic_map["coverage"]["missing_source_count"],
                    "runtime_status": chromatic_map["runtime_status"],
                },
            }

        self._write("=== СБОРКА КАТАЛОГА ДЛЯ VST3 ===")
        self._write("Проверяются SHA-256 источников и WAV-кандидатов, source offsets, статусы review/license и 10 категорий назначения ассетов для VST3. Непроверенные WAV не становятся playable.")
        self._background("Сборка каталога VST3", work)

    def open_chromatic_pitch_map(self) -> None:
        """Show the 12-tone data map used by AutoChords inside the VST3 PATTERN mode."""
        sharp = "  ".join(item["canonical_name"] for item in chromatic_note_table(spelling="sharp"))
        flat = "  ".join(item["canonical_name"] for item in chromatic_note_table(spelling="flat"))
        self.dialogs.showinfo(
            "PPGU — 12-нотная карта для AutoChords внутри PATTERN",
            "Все 12 хроматических высот сохраняются и доступны для исполнения.\n\n"
            f"Диезы: {sharp}\n\nБемоли: {flat}\n\n"
            "Энгармонические названия объединяются в один pitch class: C# = Db, D# = Eb, F# = Gb и т. д.\n"
            "E и F — разные ноты.\n\n"
             "В VST3 AutoChords открывается внутри PATTERN и использует ту же карту высот. Названия-дубликаты объединяются, "
            "но хроматические ноты не удаляются. Непроверенные WAV и fallback не допускаются автоматически."
        )

    def open_pattern_song_library(self) -> None:
        """Edit song-grouped Pattern Instrument metadata; WAV sources remain untouched."""
        path = MANAGER_DIR / "reports" / "pattern_song_library.json"
        open_pattern_song_manager(self.root, path, dialogs=self.dialogs)

    def open_plugin_browser(self) -> None:
        """Browse the latest plugin catalog and audition staged WAV candidates."""
        reports_root = MANAGER_DIR / "reports"
        catalogs = sorted(
            reports_root.rglob("plugin_asset_catalog*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not catalogs:
            self.dialogs.showinfo(
                "Sample Browser",
                "Каталог ассетов для VST3 ещё не создан. Сначала выполните START HUNTING "
                "или выберите «Собрать каталог ассетов PPGU» в меню BUILD LIBRARY.",
            )
            return
        catalog_path = catalogs[0]
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.dialogs.showerror("Sample Browser", f"Не удалось прочитать каталог: {exc}")
            return

        window, window_content, window_footer = self.dialogs.create_window(
            "Sample Browser  /  подготовленные категории библиотеки",
            "VST3 ASSET CATALOG  •  REVIEW / LICENSE / PLAYBACK STATUS",
            "1120x650",
        )
        frame = ttk.Frame(window_content, padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="Категория назначения для VST3:").pack(side="left")
        mode_var = tk.StringVar(value=MODE_ORDER[0])
        mode_box = ttk.Combobox(
            top, textvariable=mode_var, values=list(MODE_ORDER),
            state="readonly", width=24,
        )
        mode_box.pack(side="left", padx=8)
        ttk.Label(
            top,
            text=f"Каталог: {catalog_path.name} • статус: {catalog.get('status', 'UNKNOWN')}",
        ).pack(side="left", padx=8)

        columns = ("kind", "review", "license", "duration", "asset")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column, label, width in (
            ("kind", "Тип / кандидат", 220),
            ("review", "Музыкальная проверка", 180),
            ("license", "Лицензия", 150),
            ("duration", "Длительность, сек", 120),
            ("asset", "WAV / ID", 360),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True, pady=(8, 6))
        tree.tag_configure("candidate", foreground=NEON_STAGE_THEME["palette"]["warning"])
        tree.tag_configure("staged", foreground=NEON_STAGE_THEME["palette"]["accent"])
        tree.tag_configure("playable", foreground=NEON_STAGE_THEME["palette"]["success"])
        tree.tag_configure("pattern_instrument", foreground=NEON_STAGE_THEME["palette"]["accent_purple"])

        details = tk.Text(
            frame, height=7, wrap="word", font=("Consolas", 9),
            bg=NEON_STAGE_THEME["palette"]["lowlight"],
            fg=NEON_STAGE_THEME["palette"]["lcd_text"],
            insertbackground=NEON_STAGE_THEME["palette"]["accent_glow"],
            selectbackground=NEON_STAGE_THEME["palette"]["control_face"],
            relief="flat", highlightthickness=1,
            highlightbackground=NEON_STAGE_THEME["palette"]["control_border"],
        )
        details.pack(fill="x")
        item_records = {}

        def refresh_mode(*_args):
            tree.delete(*tree.get_children())
            item_records.clear()
            selected_mode = next(
                (item for item in catalog.get("modes", []) if item.get("mode") == mode_var.get()),
                {},
            )
            for candidate in selected_mode.get("candidates", []):
                values = (
                    candidate.get("candidate_type", "ANALYSIS_CANDIDATE"),
                    candidate.get("review_status", "NEEDS_MUSICAL_REVIEW"),
                    candidate.get("license_status", "UNREVIEWED"),
                    "",
                    str(candidate.get("candidate_id") or candidate.get("source_path") or "analysis only"),
                )
                row_id = tree.insert("", "end", values=values, tags=("candidate",))
                item_records[row_id] = candidate
            for asset in browser_assets_for_mode(catalog, mode_var.get()):
                is_pattern_instrument = asset.get("playable_in_pattern_instrument") is not None
                asset_kind = "PATTERN INSTRUMENT" if is_pattern_instrument else asset.get("kind", "STAGED_WAV")
                values = (
                    asset_kind,
                    asset.get("review_status", "NEEDS_MUSICAL_REVIEW"),
                    asset.get("license_status", "UNREVIEWED"),
                    asset.get("duration_seconds", ""),
                    asset.get("asset_id", ""),
                )
                if is_pattern_instrument:
                    row_tag = "pattern_instrument"
                else:
                    row_tag = "playable" if asset.get("playable") else "staged"
                row_id = tree.insert("", "end", values=values, tags=(row_tag,))
                item_records[row_id] = asset
            details.delete("1.0", "end")
            details.insert("end", json.dumps({
                "plugin_target_category": selected_mode.get("mode"),
                "status": selected_mode.get("status"),
                "assets": selected_mode.get("asset_count", 0),
                "playable_assets": selected_mode.get("playable_asset_count", 0),
                "analysis_candidates": selected_mode.get("candidate_count", 0),
                "pattern_instrument_assets": (
                    len(catalog.get("pattern_instrument_assets", []))
                    if mode_var.get() == "PATTERN MODE" else 0
                ),
                "description": selected_mode.get("description", ""),
            }, ensure_ascii=False, indent=2))

        def show_selected(_event=None):
            selection = tree.selection()
            if not selection:
                return
            details.delete("1.0", "end")
            details.insert("end", json.dumps(item_records[selection[0]], ensure_ascii=False, indent=2))

        def preview_selected():
            selection = tree.selection()
            if not selection:
                self.dialogs.showinfo("Предпрослушивание", "Выберите WAV-кандидат.", parent=window)
                return
            record = item_records[selection[0]]
            relative = record.get("asset_file")
            if not relative:
                self.dialogs.showinfo(
                    "Предпрослушивание",
                    "Это аналитический кандидат без извлечённого WAV. Сначала выполните извлечение.",
                    parent=window,
                )
                return
            audio = (catalog_path.parent / relative).resolve()
            try:
                audio.relative_to(STAGING_ROOT.resolve())
            except ValueError:
                self.dialogs.showerror("Предпрослушивание", "Путь WAV выходит за пределы staging.", parent=window)
                return
            if not audio.is_file() or audio.suffix.lower() not in {".wav", ".wave"}:
                self.dialogs.showerror("Предпрослушивание", f"WAV не найден: {audio}", parent=window)
                return
            try:
                import winsound
                winsound.PlaySound(None, 0)
                winsound.PlaySound(str(audio), winsound.SND_FILENAME | winsound.SND_ASYNC)
                self.status.set("Предпрослушивание staging WAV-кандидата")
                self._write(f"[SAMPLE BROWSER] Предпрослушивание: {audio}")
            except Exception as exc:
                self.dialogs.showerror("Предпрослушивание", str(exc), parent=window)

        mode_box.bind("<<ComboboxSelected>>", refresh_mode)
        tree.bind("<<TreeviewSelect>>", show_selected)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Прослушать выбранный WAV", command=preview_selected).pack(side="left")
        ttk.Button(buttons, text="Остановить", command=self.stop_preview).pack(side="left", padx=6)
        ttk.Button(buttons, text="Обновить", command=refresh_mode).pack(side="left", padx=6)
        ttk.Label(
            frame,
            text="Playable допускается только при REVIEWED + LICENSE_APPROVED и подтверждённой целостности. "
                 "Все остальные записи остаются кандидатами.",
        ).pack(anchor="w", pady=(6, 0))
        refresh_mode()
        ttk.Label(
            window_footer,
            text="PLAYABLE = REVIEWED + LICENSE_APPROVED + VERIFIED",
        ).pack(side="left")
        ttk.Button(
            window_footer, text="ЗАКРЫТЬ",
            style="PPGU.DialogSecondary.TButton", command=window.destroy,
        ).pack(side="right")

    def audit_other(self) -> None:
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        report_dir = MANAGER_DIR / "reports" / ("other_audit_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S"))
        self._background("Аудит OTHER", lambda: audit_other_library(samples, report_dir))

    def distribute_other(self) -> None:
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        decision_file = filedialog.askopenfilename(
            title="Выберите вручную проверенный other_decisions.json",
            initialdir=str(samples / "OTHER"),
            filetypes=[("OTHER decisions", "*.json")],
        )
        if not decision_file:
            return
        try:
            plan = route_approved_to_other(samples, Path(decision_file), approve=False)
        except Exception as exc:
            self.dialogs.showerror("План OTHER", str(exc))
            return
        preview = "\n".join(f'{item["source_path"]} → {item["destination_path"]} ({item["reason"]})' for item in plan["entries"])
        self._write("ПЛАН OTHER (без изменений):\n" + (preview or "Нет явно одобренных записей."))
        if not plan["entries"]:
            return
        if not self.dialogs.askyesno("Подтверждение копирования в OTHER",
                                   f"Будет скопировано файлов: {len(plan['entries'])}.\nSHA-256 проверяется; оригиналы останутся на месте. Продолжить?"):
            return
        self._background("Копирование в OTHER", lambda: route_approved_to_other(
            samples, Path(decision_file), approve=True))

    def extract_patterns(self) -> None:
        report_path = filedialog.askopenfilename(
            title="Выберите unified_audio_analysis.json из отчёта анализа",
            initialdir=str(MANAGER_DIR / "reports"),
            filetypes=[("Audio analysis report", "unified_audio_analysis.json"), ("JSON", "*.json")],
        )
        if not report_path:
            return
        try:
            records = json.loads(Path(report_path).read_text(encoding="utf-8"))
            if not isinstance(records, list):
                raise ValueError("Ожидается список аудио-отчётов.")
            eligible = [
                item for item in records
                if (item.get("pattern_analysis") or {}).get("pattern_analysis", {}).get("patterns")
            ]
            if not eligible:
                self.dialogs.showinfo("Паттерны не найдены",
                                    "В отчёте нет повторяющихся ритмических кандидатов для извлечения.")
                return
            total = sum(
                len(item["pattern_analysis"]["pattern_analysis"]["patterns"])
                for item in eligible
            )
            if not self.dialogs.askyesno(
                "Физическое извлечение WAV",
                f"Найдено исходных файлов с кандидатами: {len(eligible)}.\n"
                f"Кандидатов паттернов: {total}.\n"
                "Будут созданы отдельные WAV-фрагменты в LibraryManager/staging/clips "
                "и JSON-манифесты в staging/manifests.\n"
                "Все фрагменты останутся NEEDS_MUSICAL_REVIEW и UNREVIEWED.\n"
                "Продолжить?"
            ):
                return
        except Exception as exc:
            self.dialogs.showerror("Отчёт анализа", str(exc))
            return

        def work():
            extracted = []
            failures = []
            for item in eligible:
                pattern_report = {
                    "source": item["source_path"],
                    "source_sha256": item["source_sha256"],
                    "pattern_analysis": (item.get("pattern_analysis") or {}).get("pattern_analysis", {}),
                }
                try:
                    extracted.extend(extract_pattern_occurrences(pattern_report, STAGING_ROOT))
                except Exception as exc:
                    failures.append({
                        "source_path": item.get("source_path"),
                        "error": f"{type(exc).__name__}: {exc}",
                    })
            return {
                "extracted_count": len(extracted),
                "assets": extracted,
                "failures": failures,
                "review_required": True,
                "license_review_required": True,
            }
        self._background("Извлечение ритм-паттернов", work)

    def open_review_queue(self) -> None:
        """List staged WAV manifests awaiting independent musical/license review."""
        manifests = sorted((STAGING_ROOT / "manifests").glob("*.json"))
        rows = []
        for path in manifests:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                rows.append((
                    path, str(record.get("kind", "UNKNOWN")),
                    str(record.get("review_status", "NEEDS_MUSICAL_REVIEW")),
                    str(record.get("license_status", "UNREVIEWED")),
                    str(record.get("duration_seconds", "")),
                ))
            except (OSError, json.JSONDecodeError):
                rows.append((path, "INVALID_MANIFEST", "ERROR", "ERROR", ""))

        window, window_content, window_footer = self.dialogs.create_window(
            "REVIEW QUEUE  /  ручная проверка Staging",
            "HUMAN REVIEW CONSOLE  •  ORIGINAL / DERIVED WAV / LICENSE",
            "960x460",
        )
        frame = ttk.Frame(window_content, padding=10)
        frame.pack(fill="both", expand=True)
        columns = ("kind", "review", "license", "duration", "manifest")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column, label, width in (
            ("kind", "Тип", 150), ("review", "Музыкальный статус", 190),
            ("license", "Лицензия", 150), ("duration", "Длительность, сек", 120),
            ("manifest", "Манифест", 340),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        paths = {}
        for path, kind, review, license_status, duration in rows:
            tree_id = tree.insert("", "end", values=(kind, review, license_status, duration, path.name))
            paths[tree_id] = path

        ttk.Label(frame, text=f"Манифестов: {len(rows)}. Музыкальная проверка и лицензия подтверждаются отдельно.").pack(anchor="w", pady=6)

        def selected_manifest() -> Path | None:
            selection = tree.selection()
            if not selection:
                self.dialogs.showinfo("Очередь проверки", "Сначала выберите WAV-манифест.", parent=window)
                return None
            return paths[selection[0]]

        def audio_path_for(manifest: Path, field: str, *, require_staging: bool) -> Path:
            record = json.loads(manifest.read_text(encoding="utf-8"))
            raw = Path(str(record.get(field, ""))).expanduser()
            audio = raw if raw.is_absolute() else (manifest.parent / raw)
            audio = audio.resolve()
            if not audio.is_file() or audio.suffix.lower() not in {".wav", ".wave"}:
                raise ValueError(f"Файл {field} отсутствует или не является WAV: {audio}")
            if require_staging:
                try:
                    audio.relative_to(STAGING_ROOT.resolve())
                except ValueError as exc:
                    raise ValueError("Производный WAV должен находиться внутри LibraryManager/staging.") from exc
            return audio

        def play_selected(field: str) -> None:
            manifest = selected_manifest()
            if manifest is None:
                return
            try:
                audio = audio_path_for(manifest, field, require_staging=(field == "derived_path"))
                import winsound
                winsound.PlaySound(None, 0)
                winsound.PlaySound(str(audio), winsound.SND_FILENAME | winsound.SND_ASYNC)
                self._write(f"Предпрослушивание {field}: {audio}")
                self.status.set("Воспроизведение WAV-кандидата" if field == "derived_path" else "Воспроизведение оригинала")
            except Exception as exc:
                self.dialogs.showerror("Предпрослушивание", str(exc), parent=window)

        def stop_selected_preview() -> None:
            try:
                import winsound
                winsound.PlaySound(None, 0)
                self.status.set("Воспроизведение остановлено")
            except Exception as exc:
                self.dialogs.showerror("Предпрослушивание", str(exc), parent=window)

        def review_selected() -> None:
            selected_path = selected_manifest()
            if selected_path is None:
                return
            window.destroy()
            self.review_candidate(str(selected_path))

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(4, 0))
        ttk.Button(controls, text="▶ Прослушать фрагмент", command=lambda: play_selected("derived_path")).pack(side="left", padx=3)
        ttk.Button(controls, text="▶ Прослушать оригинал", command=lambda: play_selected("source_path")).pack(side="left", padx=3)
        ttk.Button(controls, text="■ Стоп", command=stop_selected_preview).pack(side="left", padx=3)
        ttk.Button(controls, text="Проверить выбранный WAV", command=review_selected).pack(side="right", padx=3)
        tree.bind("<Double-1>", lambda _event: play_selected("derived_path"))
        if not rows:
            self._write("Очередь ручной проверки пуста: staging/manifests не содержит JSON-манифестов.")
        ttk.Label(
            window_footer,
            text=f"STAGING MANIFESTS  /  {len(rows)} RECORDS  /  REVIEW IS MANUAL",
        ).pack(side="left")
        ttk.Button(
            window_footer, text="ЗАКРЫТЬ",
            style="PPGU.DialogSecondary.TButton", command=window.destroy,
        ).pack(side="right")

    def review_candidate(self, selected_path: str | None = None) -> None:
        """Collect explicit musical and license decisions for one staged WAV."""
        selected = selected_path or filedialog.askopenfilename(
            title="Выберите WAV-манифест для музыкальной и лицензионной проверки",
            initialdir=str(STAGING_ROOT / "manifests"),
            filetypes=[("Staging manifests", "*.json")],
        )
        if not selected:
            return
        from factory_curator import INSTRUMENTS, ROLES, STYLES, TONES

        def ask_value(title: str, prompt: str, values: set[str]) -> str | None:
            return self.dialogs.askstring(
                title, prompt + "\n\nДопустимые значения:\n" + ", ".join(sorted(values)),
                parent=self.root,
            )

        style = ask_value("Стиль", "Укажите подтверждённый стиль:", STYLES)
        if style is None:
            return
        instrument = ask_value("Инструмент", "Укажите подтверждённое семейство инструмента:", INSTRUMENTS)
        if instrument is None:
            return
        role = ask_value("Тип материала", "Укажите подтверждённую роль материала:", ROLES)
        if role is None:
            return
        tone = ask_value("Характер звучания", "Укажите подтверждённый тип звучания:", TONES)
        if tone is None:
            return
        notes = self.dialogs.askstring(
            "Музыкальная проверка",
            "Что прослушано и проверено? Укажите границы, характер партии и возможные ограничения:",
            parent=self.root,
        )
        if notes is None:
            return
        evidence = self.dialogs.askstring(
            "Лицензионное основание",
            "Укажите лицензию/источник и основание, разрешающее включение производного WAV в распространяемую FACTORY-библиотеку:",
            parent=self.root,
        )
        if evidence is None:
            return
        mode_text = self.dialogs.askstring(
            "Категории назначения библиотеки для VST3",
            "Укажите только подтверждённые категории подготовленной библиотеки через запятую. "
            "Это не режимы Manager; музыкальные режимы плагина — MELODY и PATTERN. "
            "Можно оставить пустым, если назначение пока неизвестно.\n\n"
            + ", ".join(MODE_ORDER),
            parent=self.root,
        )
        if mode_text is None:
            return
        selected_modes = [item.strip().upper() for item in mode_text.split(",") if item.strip()]
        invalid_modes = [item for item in selected_modes if item not in MODE_ORDER]
        if invalid_modes:
            self.dialogs.showerror(
                "Категории библиотеки VST3",
                "Неизвестные разделы: " + ", ".join(invalid_modes)
                + "\nДопустимые значения: " + ", ".join(MODE_ORDER),
                parent=self.root,
            )
            return
        if not self.dialogs.askyesno(
            "Подтверждение REVIEWED",
            "Подтверждаете, что лично прослушали WAV, проверили музыкальное содержимое и границы, "
            "а также корректность выбранных категорий назначения для библиотеки VST3?",
            parent=self.root,
        ):
            return
        mapping_text = self.dialogs.askstring(
            "Подтверждённая музыкальная привязка",
            "Введите только подтверждённые данные из прослушивания: "
            "MIDI:60, CHORD:C или NOTES:60,62,64. "
            "Оставьте пустым, если нота/аккорд/последовательность не подтверждены.",
            parent=self.root,
        )
        if mapping_text is None:
            return
        confirmed_midi_note = None
        confirmed_chord_name = None
        confirmed_note_sequence = []
        token = mapping_text.strip()
        try:
            if token.upper().startswith("MIDI:"):
                confirmed_midi_note = int(token.split(":", 1)[1].strip())
                if not 0 <= confirmed_midi_note <= 127:
                    raise ValueError
            elif token.upper().startswith("CHORD:"):
                confirmed_chord_name = token.split(":", 1)[1].strip()
                if not confirmed_chord_name or len(confirmed_chord_name) > 24:
                    raise ValueError
            elif token.upper().startswith("NOTES:"):
                confirmed_note_sequence = [
                    int(item.strip()) for item in token.split(":", 1)[1].split(",") if item.strip()
                ]
                if len(confirmed_note_sequence) < 2 or any(
                    note < 0 or note > 127 for note in confirmed_note_sequence
                ):
                    raise ValueError
            elif token:
                raise ValueError
        except ValueError:
            self.dialogs.showerror(
                "Музыкальная привязка",
                "Формат: MIDI:60, CHORD:C или NOTES:60,62,64. "
                "MIDI-ноты должны быть в диапазоне 0–127.",
                parent=self.root,
            )
            return
        technique_text = self.dialogs.askstring(
            "Подтверждённые техники",
            "Введите только прослушанные и подтверждённые техники через запятую.\n"
            + ", ".join(TECHNIQUES) + "\nОставьте пустым, если техника не подтверждена.",
            parent=self.root,
        )
        if technique_text is None:
            return
        confirmed_techniques = [
            item.strip().upper().replace(" ", "_").replace("-", "_")
            for item in technique_text.split(",") if item.strip()
        ]
        velocity_layer = self.dialogs.askstring(
            "Velocity layer",
            "Подтверждённый слой: LOW, MEDIUM, HIGH или UNKNOWN.",
            initialvalue="UNKNOWN", parent=self.root,
        )
        if velocity_layer is None:
            return
        velocity_layer = velocity_layer.strip().upper()
        advanced_text = self.dialogs.askstring(
            "Структура Pattern / Melody",
            "Необязательно: вставьте JSON с подтверждёнными событиями Pattern/Melody. "
            "Если данных нет — оставьте {}.\n"
            "Pattern: pattern_performance_review {loop_start_sample, loop_end_sample, tempo_bpm, "
            "time_signature, attack_events, beat_grid, technique_events, harmonic_events, "
            "cycle_integrity_verified:true, musical_review_verified:true}.\n"
            "Melody: confirmed_melody_events [{midi_note,start_beats,duration_beats,velocity}, ...], "
            "melody_phrase_boundaries [0,4], melody_mapping_verified:true.\n"
            "Также допустимы velocity_min и velocity_max.",
            initialvalue="{}", parent=self.root,
        )
        if advanced_text is None:
            return
        try:
            advanced_metadata = json.loads(advanced_text or "{}")
            if not isinstance(advanced_metadata, dict):
                raise ValueError("Нужен JSON-объект.")
        except (json.JSONDecodeError, ValueError) as exc:
            self.dialogs.showerror("Структура Pattern / Melody", f"Некорректный JSON: {exc}", parent=self.root)
            return

        if not self.dialogs.askyesno(
            "Подтверждение LICENSE_APPROVED",
            "Подтверждаете, что указанное лицензионное основание действительно разрешает распространение этого материала?",
            parent=self.root,
        ):
            return

        def work():
            return review_manifest(
                Path(selected), STAGING_ROOT,
                style_family=style.strip().upper(),
                instrument_family=instrument.strip().upper(),
                asset_role=role.strip().upper(),
                tone_family=tone.strip().upper(),
                musical_review_notes=notes,
                license_evidence=evidence,
                approve_musical_review=True,
                approve_license=True,
                mode_assignments=selected_modes,
                confirmed_midi_note=confirmed_midi_note,
                confirmed_chord_name=confirmed_chord_name,
                confirmed_note_sequence=confirmed_note_sequence,
                confirmed_techniques=confirmed_techniques,
                confirmed_velocity_layer=velocity_layer,
                advanced_metadata=advanced_metadata,
            )
        self._background("Музыкальная и лицензионная проверка WAV", work)

    def finalize_library(self) -> None:
        """Audit staging and distributed Factory without moving or copying assets."""
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        def progress(message: str) -> None:
            self._queue_progress(message)
        self._background(
            "Финализация библиотеки",
            lambda: finalize_library_audit(
                samples, STAGING_ROOT,
                progress=progress,
                cancel_event=self._cancel_event,
            ),
        )

    def distribute(self) -> None:
        """Automatically distribute all independently verified approved assets."""
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        manifests_dir = STAGING_ROOT / "manifests"
        manifest_count = len(list(manifests_dir.glob("*.json"))) if manifests_dir.is_dir() else 0
        if manifest_count == 0:
            self.dialogs.showinfo("FACTORY", "В staging пока нет манифестов для распределения.")
            return
        if not self.dialogs.askyesno(
            "Автоматическое распределение FACTORY",
            f"Менеджер автоматически проверит все {manifest_count} манифестов.\n"
            "Будут скопированы только кандидаты с подтверждённой музыкальной проверкой, "
            "разрешённой лицензией, целыми SHA-256 и корректными PCM WAV/границами.\n"
            "Повреждённые, недоступные и неподтверждённые записи будут внесены в отчёт, "
            "а обработка продолжится со следующими. Каждый WAV копируется отдельной транзакцией.\n"
            "Оригиналы не перемещаются и не удаляются. Продолжить?",
        ):
            self.status.set("Автоматическое распределение отменено")
            return

        def work():
            return auto_distribute_approved(
                samples, STAGING_ROOT, approve=True,
                journal_path=samples / "FACTORY" / "LibraryManagerReports" / "operations.jsonl",
                cancel_event=self._cancel_event,
                progress=self._queue_progress,
            )

        self._background("Автоматическое распределение FACTORY", work)

    def audit_cleanup(self) -> None:
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        report_path = MANAGER_DIR / "reports" / ("cleanup_audit_" + __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        self._background("Полный аудит Import", lambda: audit_all_import_sources(
            samples, STAGING_ROOT, report_path))

    def cleanup(self) -> None:
        try:
            samples = self._samples()
        except Exception as exc:
            self.dialogs.showerror("Папка Samples", str(exc))
            return
        audit_path = filedialog.askopenfilename(
            title="Выберите полный cleanup_audit_*.json",
            initialdir=str(MANAGER_DIR / "reports"),
            filetypes=[("Cleanup audit", "cleanup_audit_*.json"), ("JSON", "*.json")],
        )
        if not audit_path:
            return
        try:
            audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
            summary = audit["summary"]
            if summary.get("blocked_sources") or summary.get("errors") or summary.get("eligible_for_cleanup") != summary.get("source_files_scanned"):
                self.dialogs.showwarning(
                    "Очистка заблокирована",
                    "Не все исходники имеют полностью проверенные производные копии. "
                    "Сначала устраните блокировки в отчёте. Ни один файл не удалён."
                )
                return
        except Exception as exc:
            self.dialogs.showerror("Отчёт очистки", str(exc))
            return
        if not self.dialogs.askyesno(
            "Удаление оригиналов — подтверждение 1/2",
            f"Аудит охватил все {summary['source_files_scanned']} исходных файлов. "
            "Все зависимости имеют проверенные копии. Удалить оригиналы из Import?"
        ):
            return
        if not self.dialogs.askyesno(
            "Удаление оригиналов — подтверждение 2/2",
            "Подтверждаете окончательное удаление всех исходников? "
            "Перед удалением аудит и SHA-256 будут проверены повторно."
        ):
            return
        self._background("Очистка исходников", lambda: cleanup_sources_from_audit(
            samples, STAGING_ROOT, Path(audit_path), approve=True,
            confirm_all_dependents_accounted_for=True,
            journal_path=samples / "LibraryManagerReports" / "cleanup.jsonl"))

    def open_user_guide(self) -> None:
        """Open the numbered Russian quick-start guide in the default browser."""
        guide = resource_file(
            "PORTABLE_USER_GUIDE_RU.md", module_file=__file__, bundle_dir=BUNDLE_DIR
        )
        if not guide.is_file():
            self.dialogs.showinfo("Инструкция", "Файл PORTABLE_USER_GUIDE_RU.md не найден рядом с приложением.")
            return
        try:
            import os
            os.startfile(str(guide))
        except Exception as exc:
            self.dialogs.showerror("Инструкция", str(exc))

    def open_reports(self) -> None:
        path = MANAGER_DIR / "reports"
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    def open_staging(self) -> None:
        STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        self._open_path(STAGING_ROOT)

    @staticmethod
    def _open_path(path: Path) -> None:
        import os
        import subprocess
        if os.name == "nt":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])


def main() -> int:
    root = tk.Tk()
    LibraryManagerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
