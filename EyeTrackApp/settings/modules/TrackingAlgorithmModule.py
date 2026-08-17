from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from utils.tooltips import attach_tooltip
from localization import tr


# Selectable model variants, shared by the NEXT and eyebrow models. Each maps
# to Models/NEXT_<VARIANT>.onnx and Models/Eyebrow_<VARIANT>.onnx. The "<BASE> LITE"
# options load the fp16 NEXT build (Models/NEXT_<BASE>.fp16.onnx).
_MODEL_VARIANTS = ("ETVR", "BSB", "TOBII", "ETVR LITE", "BSB LITE")


class TrackingAlgorithmValidationModel(BaseValidationModel):
    gui_DADDY: bool
    gui_HSF: bool
    gui_HSRAC: bool
    gui_AHSF: bool
    gui_LEAP: bool
    gui_RANSAC3D: bool
    gui_AHRAC: bool
    gui_NEXT: bool
    gui_model_variant: str
    gui_max_tracking_speed: int


class TrackingAlgorithmModule(BaseSettingsModule):
    _TRACKING_SPEED_MIN = 1
    _TRACKING_SPEED_MAX = 200

    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = TrackingAlgorithmValidationModel
        # Full EyeTrackConfig: needed to persist the manual-override flag and to
        # register a listener that keeps the model combobox synced with the
        # auto-shift performed when the setup mode changes.
        self._main_config = kwargs.get("settings")
        self.gui_DADDY = f"-DADDY{widget_id}-"
        self.gui_HSF = f"-HSF{widget_id}-"
        self.gui_HSRAC = f"-HSRAC{widget_id}-"
        self.gui_LEAP = f"-LEAP{widget_id}-"
        self.gui_AHSF = f"-AHSF{widget_id}-"
        self.gui_AHRAC = f"-gui_AHRAC{widget_id}-"
        self.gui_RANSAC3D = f"-RANSAC3D{widget_id}-"
        self.gui_NEXT = f"-NEXT{widget_id}-"
        self.gui_model_variant = f"-MODELVARIANT{widget_id}-"
        self.gui_max_tracking_speed = f"-MAXTRACKSPEED{widget_id}-"

        self._basic_entries = [
            ("LEAP", "leap", self.gui_LEAP, "gui_LEAP"),
            ("DADDY", "daddy", self.gui_DADDY, "gui_DADDY"),
            (tr("algo_tracking.next_alpha"), "next", self.gui_NEXT, "gui_NEXT"),
        ]
        self._advanced_entries = [
            ("AHRAC", "ahrac", self.gui_AHRAC, "gui_AHRAC"),
            ("RANSAC 3D", "ransac3d", self.gui_RANSAC3D, "gui_RANSAC3D"),
            ("ASHSF", "ahsf", self.gui_AHSF, "gui_AHSF"),
            ("HSRAC", "hsrac", self.gui_HSRAC, "gui_HSRAC"),
            ("HSF", "hsf", self.gui_HSF, "gui_HSF"),
        ]
        self._algo_entries = self._basic_entries + self._advanced_entries

    def build(self, parent):
        selected = "next"
        for _label, name, _key, config_field in self._algo_entries:
            if getattr(self.config, config_field, False):
                selected = name
                break
        self.selected_algo = tk.StringVar(value=selected)
        for _label, name, key, config_field in self._algo_entries:
            self.tk_vars[key] = tk.BooleanVar(
                value=bool(getattr(self.config, config_field, False))
            )
        # Radio buttons live in their own frame so their column widths are
        # independent of the slider row below (which would otherwise force
        # column 1 wide via the Scale widget, creating a gap between LEAP and AHRAC).
        radio_frame = ttk.Frame(parent)
        radio_frame.grid(row=0, column=0, columnspan=5, sticky="w")
        self._render_radio_grid(radio_frame, self._basic_entries, ncol=4)

        speed_var = tk.IntVar(
            value=int(getattr(self.config, "gui_max_tracking_speed", 60))
        )
        self.tk_vars[self.gui_max_tracking_speed] = speed_var
        self._add_slider_with_controls(
            parent,
            row=1,
            label=tr("algo_tracking.max_tracking_speed"),
            var=speed_var,
            min_v=self._TRACKING_SPEED_MIN,
            max_v=self._TRACKING_SPEED_MAX,
        )

        # Shared model variant selector, placed next to Max Tracking Speed.
        model_value = str(getattr(self.config, "gui_model_variant", "ETVR")).upper()
        if model_value not in _MODEL_VARIANTS:
            model_value = "ETVR"
        model_var = tk.StringVar(value=model_value)
        self.tk_vars[self.gui_model_variant] = model_var
        self._model_var = model_var
        model_frame = ttk.Frame(parent)
        model_frame.grid(row=1, column=5, sticky="w", padx=(12, 8), pady=2)
        model_lbl = ttk.Label(model_frame, text=tr("algo_tracking.model"))
        model_lbl.grid(row=0, column=0, sticky="w", padx=(0, 4))
        attach_tooltip(model_lbl, tr("algo_tracking.model_tip"))
        combo = ttk.Combobox(
            model_frame,
            textvariable=model_var,
            values=list(_MODEL_VARIANTS),
            state="readonly",
            width=8,
        )
        combo.grid(row=0, column=1, sticky="w")
        attach_tooltip(combo, tr("algo_tracking.model_tip"))
        self._model_combo = combo
        # A manual selection sticks: it stops the setup-mode auto-shift from
        # overriding the choice on future mode switches. <<ComboboxSelected>>
        # only fires on user interaction, not on programmatic .set() from the
        # sync listener below.
        combo.bind("<<ComboboxSelected>>", self._on_model_user_selected)

        # Keep the combobox in sync when the setup-mode auto-shift changes the
        # variant in config while this page is hidden (otherwise the stale tk var
        # would be saved back and revert the auto-shift on the next render tick).
        if self._main_config is not None:
            self._main_config.register_listener_callback(self._on_model_variant_synced)

    def _on_model_user_selected(self, _event=None):
        """Mark the variant as user-chosen so setup-mode changes stop overriding it."""
        if self._main_config is None:
            return
        if not getattr(self._main_config.settings, "gui_model_variant_user_set", False):
            self._main_config.settings.gui_model_variant_user_set = True
            try:
                self._main_config.save()
            except Exception:
                pass

    def _on_model_variant_synced(self, data: dict):
        """Reflect an externally-applied variant change (setup-mode auto-shift)
        back into the combobox so it doesn't get clobbered on the next save."""
        if "gui_model_variant" not in data:
            return
        var = getattr(self, "_model_var", None)
        if var is None:
            return
        value = str(data["gui_model_variant"]).upper()
        if value not in _MODEL_VARIANTS:
            value = "ETVR"
        try:
            if var.get() != value:
                var.set(value)
        except tk.TclError:
            pass

    def build_advanced(self, parent):
        ttk.Label(parent, text=tr("algo_tracking.advanced_heading")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 2)
        )
        self._render_radio_grid(
            parent, self._advanced_entries, ncol=3, row_offset=1
        )

    def _render_radio_grid(self, parent, entries, ncol, row_offset=0) -> dict:
        """Render radio buttons and return {name: (row, col)} for each entry."""
        positions = {}
        rows_per_column = (len(entries) + ncol - 1) // ncol
        for idx, (label, name, _key, _config_field) in enumerate(entries):
            row = (idx % rows_per_column) + row_offset
            col = idx // rows_per_column
            rb = ttk.Radiobutton(
                parent, text=label, variable=self.selected_algo, value=name
            )
            rb.grid(row=row, column=col, sticky="w", padx=8, pady=2)
            attach_tooltip(rb, tr(f"algo_tracking.{name}_tip"))
            positions[name] = (row, col)
        return positions

    def _add_slider_with_controls(self, parent, row, label, var, min_v, max_v):
        slider_length = 160
        value_label_var = tk.StringVar(value=str(int(var.get())))

        def sync(*_args):
            value_label_var.set(str(int(round(float(var.get())))))

        def bump(delta):
            next_val = int(round(float(var.get()))) + delta
            next_val = max(min_v, min(max_v, next_val))
            var.set(next_val)

        lbl = ttk.Label(parent, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(lbl, tr("algo_tracking.max_tracking_speed_tip"))
        ttk.Scale(
            parent,
            from_=min_v,
            to=max_v,
            variable=var,
            orient="horizontal",
            length=slider_length,
        ).grid(row=row, column=1, sticky="w", padx=8, pady=2)
        ttk.Button(parent, text="-", width=2, command=lambda: bump(-1)).grid(
            row=row, column=2, sticky="w", padx=(4, 2), pady=2
        )
        ttk.Label(parent, textvariable=value_label_var, width=6, anchor="center").grid(
            row=row, column=3, sticky="w", padx=2, pady=2
        )
        ttk.Button(parent, text="+", width=2, command=lambda: bump(1)).grid(
            row=row, column=4, sticky="w", padx=(2, 8), pady=2
        )
        var.trace_add("write", sync)

    def get_values_map(self) -> dict:
        values = super().get_values_map()
        selected = self.selected_algo.get()
        for _label, name, key, _config_field in self._algo_entries:
            values[key] = name == selected
            self.tk_vars[key].set(name == selected)
        return values
