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

import logging
import tkinter as tk
from tkinter import ttk
from queue import Empty

import cv2

from config import EyeTrackConfig
from eye import EyeId
from utils.img_utils import tk_photo_from_rgb
from localization import tr
from output_viz import OutputVisualizer

from settings.base_settings import BaseSettingsWidget
from settings.modules.advanced_tracking_algo_settings_module import (
    AdvancedTrackingAlgoSettingsModule,
)
from settings.modules.blink_algo_module import BlinkAlgoSettingsModule
from settings.modules.tracking_algorithm_module import TrackingAlgorithmModule
from ui_theme import color

logger = logging.getLogger(__name__)


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
        self._preview_viz: list[OutputVisualizer] = []
        self._preview_dim = 120
        self._dpi_scale = 1.0

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

    def advanced_title(self) -> str:
        return tr("algo_widget.advanced_popup_title")

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
        row.pack(padx=8, pady=(4, 6), anchor="center")

        self._preview_labels = []
        self._preview_photos = []
        self._preview_viz = []

        for eye in self._eye_widgets:
            col = ttk.Frame(row)
            col.pack(side="left", padx=8)
            label_text = tr("algo_widget.left_eye") if eye.eye_id == EyeId.LEFT else tr("algo_widget.right_eye")
            ttk.Label(col, text=label_text).pack(anchor="w", pady=(0, 2))
            pair = ttk.Frame(col)
            pair.pack(anchor="w")
            holder = tk.Frame(pair, width=dim, height=dim, bg=color("surface"), bd=0, highlightthickness=0)
            holder.pack(side="left")
            holder.pack_propagate(False)
            lbl = tk.Label(holder, bg=color("surface"), bd=0, highlightthickness=0)
            lbl.pack(fill="both", expand=True)
            # Same tracking output view as the main page, scaled down beside the preview.
            viz = OutputVisualizer(pair, dim, self._dpi_scale)
            viz.canvas.pack(side="left", anchor="n", padx=(6, 0))
            viz.hide()
            self._preview_labels.append(lbl)
            self._preview_photos.append(None)
            self._preview_viz.append(viz)

    def render_tick(self):
        super().render_tick()  # throttled settings validation (0.2 s)
        self._update_eye_previews()

    def _update_eye_previews(self):
        if not self._preview_labels:
            return
        dim = self._preview_dim
        for i, eye in enumerate(self._eye_widgets):
            lbl = self._preview_labels[i]
            frame = eye_info = None
            try:
                while True:
                    item = eye.image_queue.get_nowait()
                    frame = item[0]
                    eye_info = item[1] if len(item) > 1 else None
            except Empty:
                pass
            if frame is None:
                continue
            if eye_info is not None:
                try:
                    self._preview_viz[i].draw(eye_info)
                except Exception:
                    logger.debug("Preview overlay draw failed", exc_info=True)
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
                logger.debug("Preview update failed", exc_info=True)
