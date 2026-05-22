from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk


class TrackingAlgorithmValidationModel(BaseValidationModel):
    gui_DADDY: bool
    gui_HSF: bool
    gui_HSRAC: bool
    gui_AHSF: bool
    gui_LEAP: bool
    gui_RANSAC3D: bool
    gui_AHSFRAC: bool


class TrackingAlgorithmModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = TrackingAlgorithmValidationModel
        self.gui_DADDY = f"-DADDY{widget_id}-"
        self.gui_HSF = f"-HSF{widget_id}-"
        self.gui_HSRAC = f"-HSRAC{widget_id}-"
        self.gui_LEAP = f"-LEAP{widget_id}-"
        self.gui_AHSF = f"-AHSF{widget_id}-"
        self.gui_AHSFRAC = f"-gui_AHSFRAC{widget_id}-"
        self.gui_RANSAC3D = f"-RANSAC3D{widget_id}-"

        # Algos shown in the main Tracking Algorithm section.
        self._basic_entries = [
            ("LEAP", "leap", self.gui_LEAP, "gui_LEAP"),
            ("ASHSFRAC", "ahsfrac", self.gui_AHSFRAC, "gui_AHSFRAC"),
            ("DADDY", "daddy", self.gui_DADDY, "gui_DADDY"),
            ("RANSAC 3D", "ransac3d", self.gui_RANSAC3D, "gui_RANSAC3D"),
        ]
        # Legacy/advanced algos surfaced under the Advanced toggle.
        self._advanced_entries = [
            ("ASHSF", "ahsf", self.gui_AHSF, "gui_AHSF"),
            ("HSRAC", "hsrac", self.gui_HSRAC, "gui_HSRAC"),
            ("HSF", "hsf", self.gui_HSF, "gui_HSF"),
        ]
        self._algo_entries = self._basic_entries + self._advanced_entries

    def build(self, parent):
        selected = "leap"
        for _label, name, _key, config_field in self._algo_entries:
            if getattr(self.config, config_field, False):
                selected = name
                break
        self.selected_algo = tk.StringVar(value=selected)
        for _label, name, key, config_field in self._algo_entries:
            self.tk_vars[key] = tk.BooleanVar(
                value=bool(getattr(self.config, config_field, False))
            )
        self._render_radio_grid(parent, self._basic_entries, ncol=4)

    def build_advanced(self, parent):
        ttk.Label(parent, text="Tracking Algorithm (advanced)").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 2)
        )
        self._render_radio_grid(
            parent, self._advanced_entries, ncol=3, row_offset=1
        )

    def _render_radio_grid(self, parent, entries, ncol, row_offset=0):
        rows_per_column = (len(entries) + ncol - 1) // ncol
        for idx, (label, name, _key, _config_field) in enumerate(entries):
            row = (idx % rows_per_column) + row_offset
            col = idx // rows_per_column
            ttk.Radiobutton(
                parent, text=label, variable=self.selected_algo, value=name
            ).grid(row=row, column=col, sticky="w", padx=8, pady=2)

    def get_values_map(self) -> dict:
        values = super().get_values_map()
        selected = self.selected_algo.get()
        for _label, name, key, _config_field in self._algo_entries:
            values[key] = name == selected
            self.tk_vars[key].set(name == selected)
        return values
