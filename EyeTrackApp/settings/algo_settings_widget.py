"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import tkinter as tk
from tkinter import ttk
from queue import Empty

import cv2

from config import EyeTrackConfig
from eye import EyeId
from utils.img_utils import tk_photo_from_rgb
from utils.logging_utils import open_logs
from localization import tr

from settings.BaseSettings import BaseSettingsWidget
from settings.modules.AdvancedTrackingAlgoSettingsModule import (
    AdvancedTrackingAlgoSettingsModule,
)
from settings.modules.BlinkAlgoModule import BlinkAlgoSettingsModule
from settings.modules.TrackingAlgorithmModule import TrackingAlgorithmModule


class AlgoSettingsWidget(BaseSettingsWidget):
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig):
        settings_modules = [
            TrackingAlgorithmModule,
            BlinkAlgoSettingsModule,
            AdvancedTrackingAlgoSettingsModule,
        ]
        super().__init__(widget_id, main_config, settings_modules)
        self._eye_widgets = []
        self._preview_labels: list[tk.Label] = []
        self._preview_photos: list = []
        self._preview_dim = 120
        self._dpi_scale = 1.0
        self._advanced_popup: tk.Toplevel | None = None

    def advanced_module_types(self) -> tuple:
        return (AdvancedTrackingAlgoSettingsModule,)

    def build(self, parent, eye_widgets=None, dpi_scale=1.0) -> ttk.Frame:
        # Sort so Left Eye always appears first (left column).
        self._eye_widgets = sorted(
            eye_widgets or [],
            key=lambda e: 0 if e.eye_id == EyeId.LEFT else 1,
        )
        self._dpi_scale = dpi_scale
        self._preview_dim = round(120 * dpi_scale)

        self.frame = ttk.Frame(parent)
        self._build_module_sections()
        self._wire_leap_lid_auto_check()

        if self._eye_widgets:
            self._build_eye_preview_section()

        return self.frame

    # ------------------------------------------------------------------
    # Advanced popup: overrides BaseSettingsWidget's inline expand
    # ------------------------------------------------------------------

    def _build_advanced_section(self, advanced_modules):
        """Replace the inline advanced panel with a floating popup window."""
        self._advanced_toggle_row = ttk.Frame(self.frame)
        self._advanced_toggle_row.pack(fill="x", padx=8, pady=(2, 0))
        self._advanced_toggle_btn = ttk.Button(
            self._advanced_toggle_row,
            text=self._SHOW_ADVANCED_TEXT,
            command=self._toggle_advanced,
        )
        self._advanced_toggle_btn.pack(side="left")

        # Create the Toplevel now (hidden) so all tk_vars are registered
        # eagerly and remain available for validation while the popup is closed.
        self._advanced_popup = tk.Toplevel(self.frame)
        self._advanced_popup.title(tr("algo_widget.advanced_popup_title"))
        self._advanced_popup.withdraw()
        self._advanced_popup.resizable(False, False)
        self._advanced_popup.protocol("WM_DELETE_WINDOW", self._on_advanced_popup_close)

        self._advanced_section = ttk.LabelFrame(self._advanced_popup, text=tr("algo_widget.advanced"))
        self._advanced_section.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        advanced_set = set(id(m) for m in advanced_modules)
        for module in self.initialized_modules:
            if id(module) in advanced_set:
                continue
            if hasattr(module, "build_advanced"):
                sub = ttk.Frame(self._advanced_section)
                sub.pack(fill="x", padx=2, pady=2, anchor="n")
                module.build_advanced(sub)
        for module in advanced_modules:
            sub = ttk.Frame(self._advanced_section)
            sub.pack(fill="x", padx=2, pady=2, anchor="n")
            module.build(sub)

        diagnostics_row = ttk.Frame(self._advanced_section)
        diagnostics_row.pack(fill="x", padx=8, pady=(6, 4), anchor="w")
        ttk.Button(diagnostics_row, text=tr("algo_widget.open_logs"), command=open_logs).pack(side="left")

        btn_row = ttk.Frame(self._advanced_popup)
        btn_row.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(btn_row, text=tr("algo_widget.close"), command=self._on_advanced_popup_close).pack(side="right")

        self._advanced_visible = False

    def _toggle_advanced(self):
        if self._advanced_popup is None or self._advanced_toggle_btn is None:
            return
        if self._advanced_visible:
            self._on_advanced_popup_close()
        else:
            self._advanced_visible = True
            self._advanced_toggle_btn.config(text=self._HIDE_ADVANCED_TEXT)
            self._show_advanced_popup()

    def _show_advanced_popup(self):
        popup = self._advanced_popup
        main_win = self.frame.winfo_toplevel()
        popup.transient(main_win)
        popup.update_idletasks()
        # Center over the main window.
        mw = main_win.winfo_width()
        mh = main_win.winfo_height()
        mx = main_win.winfo_rootx()
        my = main_win.winfo_rooty()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        x = mx + max(0, (mw - pw) // 2)
        y = my + max(0, (mh - ph) // 2)
        popup.geometry(f"+{x}+{y}")
        popup.deiconify()
        popup.lift()
        popup.focus_set()

    def _on_advanced_popup_close(self):
        self._advanced_visible = False
        if self._advanced_toggle_btn is not None:
            try:
                self._advanced_toggle_btn.config(text=self._SHOW_ADVANCED_TEXT)
            except tk.TclError:
                pass
        if self._advanced_popup is not None:
            try:
                self._advanced_popup.withdraw()
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # LEAP → LEAP Lid auto-check wiring
    # ------------------------------------------------------------------

    def _wire_leap_lid_auto_check(self):
        """When the user switches *to* LEAP, auto-check LEAP Lid Blink Algo.
        Never forces it off; the user can still uncheck it manually."""
        algo_mod = next((m for m in self.initialized_modules if isinstance(m, TrackingAlgorithmModule)), None)
        blink_mod = next((m for m in self.initialized_modules if isinstance(m, BlinkAlgoSettingsModule)), None)
        if algo_mod is None or blink_mod is None:
            return
        leap_lid_var = blink_mod.tk_vars.get(blink_mod.gui_LEAP_lid)
        if leap_lid_var is None:
            return

        prev = [algo_mod.selected_algo.get()]

        def _on_algo_change(*_):
            current = algo_mod.selected_algo.get()
            if current == "leap" and prev[0] != "leap":
                leap_lid_var.set(True)
            prev[0] = current

        algo_mod.selected_algo.trace_add("write", _on_algo_change)

    # ------------------------------------------------------------------
    # Eye preview section
    # ------------------------------------------------------------------

    def _build_eye_preview_section(self):
        dim = self._preview_dim
        section = ttk.LabelFrame(self.frame, text=tr("algo_widget.eye_preview"))
        section.pack(fill="x", padx=8, pady=6, anchor="n")
        row = ttk.Frame(section)
        row.pack(padx=8, pady=(4, 6), anchor="w")

        self._preview_labels = []
        self._preview_photos = []

        for eye in self._eye_widgets:
            col = ttk.Frame(row)
            col.pack(side="left", padx=(0, 12))
            label_text = tr("algo_widget.left_eye") if eye.eye_id == EyeId.LEFT else tr("algo_widget.right_eye")
            ttk.Label(col, text=label_text).pack(pady=(0, 2))
            holder = tk.Frame(col, width=dim, height=dim, bg="#1e1f23", bd=0, highlightthickness=0)
            holder.pack()
            holder.pack_propagate(False)
            lbl = tk.Label(holder, bg="#1e1f23", bd=0, highlightthickness=0)
            lbl.pack(fill="both", expand=True)
            self._preview_labels.append(lbl)
            self._preview_photos.append(None)

    def render_tick(self):
        super().render_tick()  # throttled settings validation (0.2 s)
        self._update_eye_previews()

    def _update_eye_previews(self):
        if not self._preview_labels:
            return
        dim = self._preview_dim
        for i, eye in enumerate(self._eye_widgets):
            lbl = self._preview_labels[i]
            frame = None
            try:
                while True:
                    item = eye.image_queue.get_nowait()
                    frame = item[0]
            except Empty:
                pass
            if frame is None:
                continue
            try:
                if frame.ndim == 2:
                    half_w = frame.shape[1] // 2
                    eye_img = frame[:, :half_w]
                else:
                    eye_img = frame

                interp = cv2.INTER_AREA if eye_img.shape[0] > dim else cv2.INTER_LINEAR
                preview = cv2.resize(eye_img, (dim, dim), interpolation=interp)

                if preview.ndim == 2:
                    rgb = cv2.cvtColor(preview, cv2.COLOR_GRAY2RGB)
                elif preview.shape[2] == 3:
                    rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
                else:
                    rgb = cv2.cvtColor(preview, cv2.COLOR_BGRA2RGB)

                photo = tk_photo_from_rgb(rgb, lbl)
                self._preview_photos[i] = photo
                lbl.configure(image=photo)
            except Exception:
                pass
