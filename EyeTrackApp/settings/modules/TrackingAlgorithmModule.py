from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import ttk

from pydantic import Field
from typing_extensions import Annotated, Literal

from utils.tooltips import attach_tooltip
from localization import tr
from next_eye_coupling import DEFAULT_SYNC, SYNC_MAX
from next_eye_gaze import DOMINANT_EYES, GAZE_MODES
from next_model import (
    DEFAULT_MODEL_SIZE,
    EXPERIMENTAL_MODEL_SIZES,
    HMD_TYPES,
    MODEL_SIZES,
    split_variant,
)


# Selectable headsets, shared by the NEXT and eyebrow models. NEXT uses the
# headset's Hybrid family for ETVR/BSB/PSVR at the chosen model size.
# Independent eyebrow inference uses the headset only (PSVR falls back to ETVR).
_MODEL_VARIANTS = HMD_TYPES
# Dropdown text per stored headset. PSVR and Tobii share one model family.
_HEADSET_LABELS = {"ETVR": "ETVR", "BSB": "BSB", "PSVR": "PSVR/TOBII"}

# Left/right eyelid and eyebrow sync sliders: 0 = off .. SYNC_MAX = strongest.
SyncStrength = Annotated[int, Field(ge=0, le=SYNC_MAX)]


class TrackingAlgorithmValidationModel(BaseValidationModel):
    gui_DADDY: bool
    gui_HSF: bool
    gui_HSRAC: bool
    gui_AHSF: bool
    gui_LEAP: bool
    gui_RANSAC3D: bool
    gui_AHRAC: bool
    gui_NEXT: bool
    gui_NEXT_calib_lids_brows: bool
    gui_NEXT_lid_sync: SyncStrength
    gui_NEXT_brow_sync: SyncStrength
    gui_NEXT_gaze_mode: Literal[GAZE_MODES]
    gui_NEXT_dominant_eye: Literal[DOMINANT_EYES]
    gui_model_variant: str
    gui_model_size: str
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
        self.gui_NEXT_calib_lids_brows = f"-NEXTCALIBLIDSBROWS{widget_id}-"
        self.gui_NEXT_lid_sync = f"-NEXTLIDSYNC{widget_id}-"
        self.gui_NEXT_brow_sync = f"-NEXTBROWSYNC{widget_id}-"
        self.gui_NEXT_gaze_mode = f"-NEXTGAZEMODE{widget_id}-"
        self.gui_NEXT_dominant_eye = f"-NEXTDOMINANTEYE{widget_id}-"
        self.gui_model_variant = f"-MODELVARIANT{widget_id}-"
        self.gui_model_size = f"-MODELSIZE{widget_id}-"
        self.gui_max_tracking_speed = f"-MAXTRACKSPEED{widget_id}-"

        # Display order of the tracker radios: NEXT first (the default and the
        # one under active development), then LEAP, then DADDY.
        self._basic_entries = [
            ("NEXT", "next", self.gui_NEXT, "gui_NEXT"),
            ("LEAP", "leap", self.gui_LEAP, "gui_LEAP"),
            ("DADDY", "daddy", self.gui_DADDY, "gui_DADDY"),
        ]
        self._advanced_entries = [
            ("AHRAC", "ahrac", self.gui_AHRAC, "gui_AHRAC"),
            ("RANSAC 3D", "ransac3d", self.gui_RANSAC3D, "gui_RANSAC3D"),
            ("ASHSF", "ahsf", self.gui_AHSF, "gui_AHSF"),
            ("HSRAC", "hsrac", self.gui_HSRAC, "gui_HSRAC"),
            ("HSF", "hsf", self.gui_HSF, "gui_HSF"),
        ]
        self._algo_entries = self._basic_entries + self._advanced_entries

    def _selected_from(self, settings) -> str:
        for _label, name, _key, config_field in self._algo_entries:
            if getattr(settings, config_field, False):
                return name
        return "next"

    def reset_to_defaults(self, defaults):
        selected_algo = getattr(self, "selected_algo", None)
        if selected_algo is not None:
            selected_algo.set(self._selected_from(defaults))

    def build(self, parent):
        self.selected_algo = tk.StringVar(value=self._selected_from(self.config))
        for _label, name, key, config_field in self._algo_entries:
            self.tk_vars[key] = tk.BooleanVar(value=bool(getattr(self.config, config_field, False)))
        # Radio buttons live in their own frame so their column widths are
        # independent of the slider row below (which would otherwise force
        # column 1 wide via the Scale widget, creating a gap between LEAP and AHRAC).
        radio_frame = ttk.Frame(parent)
        radio_frame.grid(row=0, column=0, columnspan=5, sticky="w")
        self._render_radio_grid(radio_frame, self._basic_entries, ncol=4)

        speed_var = tk.IntVar(value=int(getattr(self.config, "gui_max_tracking_speed", 60)))
        self.tk_vars[self.gui_max_tracking_speed] = speed_var
        self._add_slider_with_controls(
            parent,
            row=1,
            label=tr("algo_tracking.max_tracking_speed"),
            var=speed_var,
            min_v=self._TRACKING_SPEED_MIN,
            max_v=self._TRACKING_SPEED_MAX,
            tip=tr("algo_tracking.max_tracking_speed_tip"),
        )

        # Directly under the speed slider: opt out of having NEXT Smart Calib
        # anchor this user's neutral eyelid / eyebrow readings.
        lids_brows_var = tk.BooleanVar(value=bool(getattr(self.config, "gui_NEXT_calib_lids_brows", True)))
        self.tk_vars[self.gui_NEXT_calib_lids_brows] = lids_brows_var
        lids_brows_cb = ttk.Checkbutton(
            parent,
            text=tr("algo_tracking.next_calib_lids_brows"),
            variable=lids_brows_var,
        )
        lids_brows_cb.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 4))
        attach_tooltip(lids_brows_cb, tr("algo_tracking.next_calib_lids_brows_tip"))

        # Left/right sync: one slider per channel, in the speed slider's grid.
        for row, field, label in (
            (3, "gui_NEXT_lid_sync", "next_lid_sync"),
            (4, "gui_NEXT_brow_sync", "next_brow_sync"),
        ):
            sync_var = tk.IntVar(value=int(getattr(self.config, field, DEFAULT_SYNC)))
            self.tk_vars[getattr(self, field)] = sync_var
            self._add_slider_with_controls(
                parent,
                row=row,
                label=tr(f"algo_tracking.{label}"),
                var=sync_var,
                min_v=0,
                max_v=SYNC_MAX,
                tip=tr(f"algo_tracking.{label}_tip"),
                step=5,
                zero_text=tr("algo_tracking.next_sync_off"),
            )

        # Per-eye gaze for strabismus / amblyopia (fused by default).
        self._build_gaze_mode(parent, row=5)

        # NEXT model: headset family plus a size slider (lightest -> best).
        model_frame = ttk.Frame(parent)
        model_frame.grid(row=6, column=0, columnspan=6, sticky="w", padx=8, pady=(2, 4))
        self._build_model_selector(model_frame)

        # Keep the combobox in sync when the setup-mode auto-shift changes the
        # variant in config while this page is hidden (otherwise the stale tk var
        # would be saved back and revert the auto-shift on the next render tick).
        if self._main_config is not None:
            self._main_config.register_listener_callback(self._on_model_variant_synced)

    def _build_gaze_mode(self, parent, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=6, sticky="w", padx=8, pady=(2, 4))
        for field, label, keys, default, width in (
            ("gui_NEXT_gaze_mode", "next_gaze_mode", GAZE_MODES, "fused", 12),
            ("gui_NEXT_dominant_eye", "next_dominant_eye", DOMINANT_EYES, "left", 7),
        ):
            stored = str(getattr(self.config, field, default) or default).lower()
            var = tk.StringVar(value=stored if stored in keys else default)
            self.tk_vars[getattr(self, field)] = var
            lbl = ttk.Label(frame, text=tr(f"algo_tracking.{label}"))
            lbl.pack(side="left", padx=(0 if field == "gui_NEXT_gaze_mode" else 16, 4))
            attach_tooltip(lbl, tr(f"algo_tracking.{label}_tip"))
            # The combobox shows labels; var keeps the stored key.
            labels = {key: tr(f"algo_tracking.{label}_{key}") for key in keys}
            label_var = tk.StringVar(value=labels[var.get()])
            combo = ttk.Combobox(
                frame, textvariable=label_var, values=list(labels.values()), state="readonly", width=width
            )
            combo.pack(side="left")
            attach_tooltip(combo, tr(f"algo_tracking.{label}_tip"))
            by_label = {text: key for key, text in labels.items()}
            combo.bind("<<ComboboxSelected>>", lambda _e, v=var, lv=label_var, m=by_label: v.set(m[lv.get()]))
            # Reset to defaults writes the key; keep the shown label in step.
            var.trace_add("write", lambda *_a, v=var, lv=label_var, t=labels, d=default: lv.set(t.get(v.get(), t[d])))

    def _build_model_selector(self, parent):
        hmd, legacy_size = split_variant(getattr(self.config, "gui_model_variant", "ETVR"))
        size = str(getattr(self.config, "gui_model_size", "") or legacy_size).upper()
        if size not in MODEL_SIZES:
            size = DEFAULT_MODEL_SIZE
        model_var = tk.StringVar(value=hmd)
        self.tk_vars[self.gui_model_variant] = model_var
        self._model_var = model_var
        size_var = tk.StringVar(value=size)
        self.tk_vars[self.gui_model_size] = size_var
        self._size_var = size_var

        hmd_lbl = ttk.Label(parent, text=tr("algo_tracking.headset"))
        hmd_lbl.grid(row=0, column=0, sticky="w", padx=(0, 4))
        attach_tooltip(hmd_lbl, tr("algo_tracking.headset_tip"))
        # The combobox shows labels; model_var keeps the stored headset key.
        label_var = tk.StringVar(value=_HEADSET_LABELS[hmd])
        combo = ttk.Combobox(
            parent,
            textvariable=label_var,
            values=[_HEADSET_LABELS[h] for h in _MODEL_VARIANTS],
            state="readonly",
            width=11,
        )
        combo.grid(row=0, column=1, sticky="w")
        attach_tooltip(combo, tr("algo_tracking.headset_tip"))
        self._model_combo = combo

        # A manual selection sticks: it stops the setup-mode auto-shift from
        # overriding the choice on future mode switches. <<ComboboxSelected>>
        # only fires on user interaction, not on programmatic .set() from the
        # sync listener below.
        def on_selected(event=None):
            model_var.set(split_variant(label_var.get())[0])
            self._on_model_user_selected(event)

        combo.bind("<<ComboboxSelected>>", on_selected)

        # Model size: one notch per MODEL_SIZES entry, lightest on the left and
        # the best (most compute) on the right.
        size_lbl = ttk.Label(parent, text=tr("algo_tracking.model_size"))
        size_lbl.grid(row=0, column=2, sticky="w", padx=(16, 4))
        attach_tooltip(size_lbl, tr("algo_tracking.model_size_tip"))
        ttk.Label(parent, text=tr("algo_tracking.model_size_lightest"), foreground="#888888").grid(
            row=0, column=3, sticky="e", padx=(0, 2)
        )
        index_var = tk.DoubleVar(value=MODEL_SIZES.index(size))
        scale = ttk.Scale(
            parent,
            from_=0,
            to=len(MODEL_SIZES) - 1,
            variable=index_var,
            orient="horizontal",
            length=140,
            command=lambda v: size_var.set(MODEL_SIZES[int(round(float(v)))]),
        )
        scale.grid(row=0, column=4, sticky="w")
        attach_tooltip(scale, tr("algo_tracking.model_size_tip"))
        ttk.Label(parent, text=tr("algo_tracking.model_size_best"), foreground="#888888").grid(
            row=0, column=5, sticky="w", padx=(2, 6)
        )
        value_lbl = ttk.Label(parent, width=8)
        value_lbl.grid(row=0, column=6, sticky="w")
        warning = ttk.Label(
            parent,
            text=tr("algo_tracking.model_size_wip"),
            foreground="#e0a030",
            wraplength=420,
        )
        warning.grid(row=1, column=2, columnspan=5, sticky="w", padx=(16, 0), pady=(2, 0))

        def refresh(*_args):
            value = str(size_var.get()).upper()
            if value not in MODEL_SIZES:
                value = DEFAULT_MODEL_SIZE
            idx = MODEL_SIZES.index(value)
            # Snap the slider to its notch (drags report fractional positions).
            if index_var.get() != idx:
                index_var.set(idx)
            value_lbl.configure(text=tr(f"algo_tracking.model_size_{value.lower()}"))
            label = _HEADSET_LABELS[split_variant(model_var.get())[0]]
            if label_var.get() != label:
                label_var.set(label)
            if value in EXPERIMENTAL_MODEL_SIZES:
                warning.grid()
            else:
                warning.grid_remove()

        size_var.trace_add("write", refresh)
        model_var.trace_add("write", refresh)
        refresh()

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
        value, _size = split_variant(data["gui_model_variant"])
        try:
            if var.get() != value:
                var.set(value)
        except tk.TclError:
            pass

    def build_advanced(self, parent):
        ttk.Label(parent, text=tr("algo_tracking.advanced_heading")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(2, 2)
        )
        self._render_radio_grid(parent, self._advanced_entries, ncol=3, row_offset=1)

    def _render_radio_grid(self, parent, entries, ncol, row_offset=0) -> dict:
        """Render radio buttons and return {name: (row, col)} for each entry."""
        positions = {}
        rows_per_column = (len(entries) + ncol - 1) // ncol
        for idx, (label, name, _key, _config_field) in enumerate(entries):
            row = (idx % rows_per_column) + row_offset
            col = idx // rows_per_column
            rb = ttk.Radiobutton(parent, text=label, variable=self.selected_algo, value=name)
            rb.grid(row=row, column=col, sticky="w", padx=8, pady=2)
            attach_tooltip(rb, tr(f"algo_tracking.{name}_tip"))
            positions[name] = (row, col)
        return positions

    def _add_slider_with_controls(self, parent, row, label, var, min_v, max_v, tip, step=1, zero_text=None):
        slider_length = 160

        def shown(value):
            value = int(round(float(value)))
            return zero_text if value == 0 and zero_text else str(value)

        value_label_var = tk.StringVar(value=shown(var.get()))

        def sync(*_args):
            value_label_var.set(shown(var.get()))

        def bump(delta):
            next_val = int(round(float(var.get()))) + delta
            next_val = max(min_v, min(max_v, next_val))
            var.set(next_val)

        lbl = ttk.Label(parent, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(lbl, tip)
        scale = ttk.Scale(
            parent,
            from_=min_v,
            to=max_v,
            variable=var,
            orient="horizontal",
            length=slider_length,
        )
        scale.grid(row=row, column=1, sticky="w", padx=8, pady=2)
        attach_tooltip(scale, tip)
        ttk.Button(parent, text="-", width=2, command=lambda: bump(-step)).grid(
            row=row, column=2, sticky="w", padx=(4, 2), pady=2
        )
        ttk.Label(parent, textvariable=value_label_var, width=6, anchor="center").grid(
            row=row, column=3, sticky="w", padx=2, pady=2
        )
        ttk.Button(parent, text="+", width=2, command=lambda: bump(step)).grid(
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
