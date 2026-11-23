"""
"Foveated rendering" section of General settings.

One switch, "Foveated rendering support" (gui_foveation_gaze, on by default): it
shares gaze with foveated rendering (port 9020 and the gaze shared memory, the SteamVR
driver and the OpenXR layer; osc/foveation_gaze_sender.py). On Windows the per-game
panel (settings/dfr_panel.py) sits under it and is hidden while the switch is off.
"""

import sys
import tkinter as tk
from tkinter import ttk

from localization import tr
from settings.modules.base_module import BaseSettingsModule, BaseValidationModel
from utils.tooltips import attach_tooltip


class FoveationValidationModel(BaseValidationModel):
    gui_foveation_gaze: bool


class FoveationSettingsModule(BaseSettingsModule):
    def __init__(self, config, widget_id, **kwargs):
        super().__init__(config=config, widget_id=widget_id, **kwargs)
        self.validation_model = FoveationValidationModel
        self.main_config = kwargs.get("settings")
        self.gui_foveation_gaze = f"-FOVEATION{widget_id}-"
        self.panel = None

    def build(self, parent):
        var = tk.BooleanVar(value=bool(self.config.gui_foveation_gaze))
        self.tk_vars[self.gui_foveation_gaze] = var
        switch = ttk.Checkbutton(parent, text=tr("dfr.support"), variable=var)
        switch.pack(anchor="w", padx=8, pady=(6, 2))
        attach_tooltip(switch, tr("dfr.support_tip"))
        if sys.platform != "win32" or self.main_config is None:
            return

        from ovr.dfr import dfr_controller
        from settings.dfr_panel import DfrPanel

        # Ticked through the variable: the next render_tick saves it, where a direct
        # config write would be undone by it.
        self.panel = DfrPanel(dfr_controller, self.main_config, lambda: var.set(True))
        body = self.panel.build(parent, framed=False)

        def sync(*_):
            if var.get():
                if body.winfo_manager() != "pack":
                    # Inset: sv_ttk draws the section border inside the box.
                    body.pack(fill="x", padx=2, pady=(0, 2))
            else:
                body.pack_forget()

        var.trace_add("write", sync)
        sync()
