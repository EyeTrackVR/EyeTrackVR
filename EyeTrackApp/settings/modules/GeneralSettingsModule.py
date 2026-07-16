from config import EyeTrackSettingsConfig
from settings.modules.BaseModule import BaseSettingsModule, BaseValidationModel
import tkinter as tk
from tkinter import messagebox, ttk

from localization import available_languages, tr
from utils.tooltips import attach_tooltip


# Map each gui field name → its short catalog leaf under the ``settings_general``
# section. The label lives at ``settings_general.<leaf>`` and its tooltip at
# ``settings_general.<leaf>_tip``. Centralised so the build loop stays compact.
_LEAF = {
    "gui_flip_x_axis_left": "flip_x_left",
    "gui_flip_x_axis_right": "flip_x_right",
    "gui_flip_y_axis": "flip_y",
    "gui_outer_side_falloff": "outer_falloff",
    "gui_left_eye_dominant": "force_left_dominant",
    "gui_right_eye_dominant": "force_right_dominant",
    "gui_openvr_autostart": "start_stop_steamvr",
    "gui_use_gpu": "use_gpu",
    "gui_update_check": "check_updates",
    "gui_eye_dominant_diff_thresh": "eye_diff_threshold",
    "gui_use_overlay_cal": "use_overlay_cal",
    "gui_show_et_debug": "show_et_debug",
}


def _label(field: str) -> str:
    return tr(f"settings_general.{_LEAF[field]}")


def _tip(field: str) -> str:
    return tr(f"settings_general.{_LEAF[field]}_tip")


class GeneralSettingsValidationModel(BaseValidationModel):
    gui_flip_x_axis_left: bool
    gui_flip_x_axis_right: bool
    gui_flip_y_axis: bool
    gui_outer_side_falloff: bool
    gui_update_check: bool
    gui_right_eye_dominant: bool
    gui_left_eye_dominant: bool
    gui_eye_dominant_diff_thresh: float
    gui_openvr_autostart: bool
    gui_use_gpu: bool
    gui_show_et_debug: bool
    gui_use_overlay_cal: bool
    gui_language: str


class GeneralSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = GeneralSettingsValidationModel
        # Full EyeTrackConfig (passed as ``settings``). Used to persist the
        # language choice immediately on selection — the debounced render_tick
        # save can be lost because the restart messagebox blocks the Tk event
        # loop and shutdown() doesn't flush pending settings saves.
        self._main_config = kwargs.get("settings")
        self.gui_flip_x_axis_left = f"-FLIPXAXISLEFT{widget_id}-"
        self.gui_flip_x_axis_right = f"-FLIPXAXISRIGHT{widget_id}-"
        self.gui_flip_y_axis = f"-FLIPYAXIS{widget_id}-"
        self.gui_outer_side_falloff = f"-EYEFALLOFF{widget_id}-"
        self.gui_eye_dominant_diff_thresh = f"-DIFFTHRESH{widget_id}-"
        self.gui_left_eye_dominant = f"-LEFTEYEDOMINANT{widget_id}-"
        self.gui_right_eye_dominant = f"-RIGHTEYEDOMINANT{widget_id}-"
        self.gui_update_check = f"-UPDATECHECK{widget_id}-"
        self.gui_openvr_autostart = f"-OPENVRAUTOSTART{widget_id}-"
        self.gui_use_gpu = f"-USEGPU{widget_id}-"
        self.gui_show_et_debug = f"-SHOWETDEBUG{widget_id}-"
        self.gui_use_overlay_cal = f"-USEOVERLAYCAL{widget_id}-"
        self.gui_language = f"-LANGUAGE{widget_id}-"
        # Populated in build(): maps the dropdown's visible native name to the
        # locale code we persist, and back.
        self._lang_display_to_code: dict[str, str] = {}
        self._lang_code_to_display: dict[str, str] = {}


    def build(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        bool_pairs = [
            (
                (self.gui_flip_x_axis_left, self.config.gui_flip_x_axis_left),
                (self.gui_flip_x_axis_right, self.config.gui_flip_x_axis_right),
            ),
            (
                (self.gui_openvr_autostart, self.config.gui_openvr_autostart),
                (self.gui_use_gpu, self.config.gui_use_gpu),
            ),
            (
                (self.gui_flip_y_axis, self.config.gui_flip_y_axis),
                (self.gui_update_check, self.config.gui_update_check),
            ),
        ]

        # Map widget-key string → config attr so we can look up label + tooltip.
        key_to_attr = {
            self.gui_flip_x_axis_left: "gui_flip_x_axis_left",
            self.gui_flip_x_axis_right: "gui_flip_x_axis_right",
            self.gui_flip_y_axis: "gui_flip_y_axis",
            self.gui_openvr_autostart: "gui_openvr_autostart",
            self.gui_use_gpu: "gui_use_gpu",
            self.gui_update_check: "gui_update_check",
        }

        row = 0
        for left, right in bool_pairs:
            for col, field in enumerate((left, right)):
                if field is None:
                    continue
                key, default = field
                attr = key_to_attr[key]
                var = tk.BooleanVar(value=default)
                self.tk_vars[key] = var
                cb = ttk.Checkbutton(parent, text=_label(attr), variable=var)
                cb.grid(row=row, column=col, sticky="w", padx=8, pady=2)
                attach_tooltip(cb, _tip(attr))
            row += 1

        falloff_var = tk.BooleanVar(value=self.config.gui_outer_side_falloff)
        self.tk_vars[self.gui_outer_side_falloff] = falloff_var
        falloff_cb = ttk.Checkbutton(
            parent, text=_label("gui_outer_side_falloff"), variable=falloff_var
        )
        falloff_cb.grid(row=row, column=0, sticky="w", padx=8, pady=2)
        attach_tooltip(falloff_cb, _tip("gui_outer_side_falloff"))
        row += 1

        self._build_language_row(parent, row)

    def _build_language_row(self, parent, row):
        """Language selector. The tk var we register holds the locale *code*
        (what we persist); the combobox shows the native name. Changing it prompts
        a restart; see localization.init_localization()."""
        options = available_languages()
        self._lang_display_to_code = {o["native_name"]: o["code"] for o in options}
        self._lang_code_to_display = {o["code"]: o["native_name"] for o in options}

        current_code = self.config.gui_language or "en"
        current_display = self._lang_code_to_display.get(current_code, current_code)

        lang_row = ttk.Frame(parent)
        lang_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 2))
        lbl = ttk.Label(lang_row, text=tr("settings_general.language"))
        lbl.pack(side="left", padx=(0, 6))
        attach_tooltip(lbl, tr("settings_general.language_tip"))

        # Persisted value = code; kept in sync by the selection handler.
        code_var = tk.StringVar(value=current_code)
        self.tk_vars[self.gui_language] = code_var
        # Display value = native name (never read by the save pipeline).
        self._lang_display_var = tk.StringVar(value=current_display)
        combo = ttk.Combobox(
            lang_row,
            textvariable=self._lang_display_var,
            values=[o["native_name"] for o in options],
            state="readonly",
            width=16,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._on_language_selected)

    def _on_language_selected(self, _event=None):
        new_code = self._lang_display_to_code.get(self._lang_display_var.get(), "en")
        code_var = self.tk_vars.get(self.gui_language)
        if code_var is not None:
            code_var.set(new_code)
        if new_code == (self.config.gui_language or "en"):
            return
        # Persist right away. Selecting a language is a deliberate one-shot
        # action (and prompts a restart), so we don't wait for the debounced
        # render_tick save, which can be dropped if the app is closed before it
        # fires. update() also notifies listeners and writes to disk.
        if self._main_config is not None:
            self._main_config.update({"gui_language": new_code}, save=True)
        else:
            self.config.gui_language = new_code
        messagebox.showinfo(
            tr("settings_general.language_restart_title"),
            tr("settings_general.language_restart_note"),
        )

    def build_advanced(self, parent):
        fields = [
            (
                self.gui_use_overlay_cal,
                self.config.gui_use_overlay_cal,
                "gui_use_overlay_cal",
            ),
            (
                self.gui_left_eye_dominant,
                self.config.gui_left_eye_dominant,
                "gui_left_eye_dominant",
            ),
            (
                self.gui_right_eye_dominant,
                self.config.gui_right_eye_dominant,
                "gui_right_eye_dominant",
            ),
            (
                self.gui_show_et_debug,
                self.config.gui_show_et_debug,
                "gui_show_et_debug",
            ),
        ]
        for row, (key, default, attr) in enumerate(fields):
            var = tk.BooleanVar(value=default)
            self.tk_vars[key] = var
            cb = ttk.Checkbutton(parent, text=_label(attr), variable=var)
            cb.grid(row=row, column=0, sticky="w", padx=8, pady=2)
            attach_tooltip(cb, _tip(attr))

        diff_row = ttk.Frame(parent)
        diff_row.grid(row=len(fields), column=0, sticky="w", padx=8, pady=2)
        diff_lbl = ttk.Label(diff_row, text=_label("gui_eye_dominant_diff_thresh"))
        diff_lbl.pack(side="left", padx=(0, 6))
        attach_tooltip(diff_lbl, _tip("gui_eye_dominant_diff_thresh"))
        diff_var = tk.StringVar(value=str(self.config.gui_eye_dominant_diff_thresh))
        self.tk_vars[self.gui_eye_dominant_diff_thresh] = diff_var
        ttk.Entry(diff_row, textvariable=diff_var, width=12).pack(side="left")
