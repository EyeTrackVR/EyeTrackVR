"""
"Foveated rendering in SteamVR games" section of General settings (Windows).

Shows the SteamVR game in front and a per-game switch + quality, backed by
ovr/dfr.py. Live: it polls the controller, and changes apply to the running game
at once. Not a settings module, since its state is per game and changes are applied
immediately rather than through the validate-and-save cycle.
"""

import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from localization import tr
from ovr import dfr
from utils.tooltips import attach_tooltip

POLL_MS = 500
TOOL_URL = "https://github.com/mbucchia/PimaxMagic4All/releases"
QUALITY_ORDER = ("maximum", "balanced", "minimum", "debug")


class DfrPanel:
    def __init__(self, controller: dfr.DfrController, config):
        self.controller = controller
        self.config = config
        self.frame: ttk.LabelFrame | None = None
        self._installing = False

    # ------------------------------------------------------------- build

    def build(self, parent) -> ttk.LabelFrame:
        self.frame = ttk.LabelFrame(parent, text=tr("dfr.section"))

        game_row = ttk.Frame(self.frame)
        game_row.pack(fill="x", padx=8, pady=(4, 2))
        self.game_label = ttk.Label(game_row, text="")
        self.game_label.pack(side="left")

        switch_row = ttk.Frame(self.frame)
        switch_row.pack(fill="x", padx=8, pady=2)
        self.enabled_var = tk.BooleanVar(value=False)
        self.enabled_cb = ttk.Checkbutton(
            switch_row, text=tr("dfr.enable_for_game"), variable=self.enabled_var, command=self._on_toggle
        )
        self.enabled_cb.pack(side="left")
        attach_tooltip(self.enabled_cb, tr("dfr.enable_for_game_tip"))
        ttk.Label(switch_row, text=tr("dfr.quality")).pack(side="left", padx=(16, 4))
        self._quality_labels = {key: tr(f"dfr.quality_{key}") for key in QUALITY_ORDER}
        self.quality_var = tk.StringVar(value=self._quality_labels[dfr.DEFAULT_MODE])
        self.quality_box = ttk.Combobox(
            switch_row,
            textvariable=self.quality_var,
            state="readonly",
            width=14,
            values=[self._quality_labels[k] for k in QUALITY_ORDER],
        )
        self.quality_box.pack(side="left")
        self.quality_box.bind("<<ComboboxSelected>>", self._on_quality)
        attach_tooltip(self.quality_box, tr("dfr.quality_tip"))

        self.status_label = ttk.Label(self.frame, text="", wraplength=620, justify="left")
        self.status_label.pack(fill="x", padx=8, pady=(2, 4))

        tool_row = ttk.Frame(self.frame)
        tool_row.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Label(tool_row, text=tr("dfr.tool_folder")).pack(side="left")
        self.tool_label = ttk.Label(tool_row, text="")
        self.tool_label.pack(side="left", padx=(4, 8))
        browse = ttk.Button(tool_row, text=tr("dfr.browse"), command=self._browse)
        browse.pack(side="left")
        attach_tooltip(browse, tr("dfr.browse_tip"))
        self.install_btn = ttk.Button(tool_row, text=tr("dfr.install_system_files"), command=self._install)
        attach_tooltip(self.install_btn, tr("dfr.install_system_files_tip"))
        self.get_btn = ttk.Button(tool_row, text=tr("dfr.get_tool"), command=lambda: webbrowser.open(TOOL_URL))

        self.frame.after(0, self._poll)
        return self.frame

    # ------------------------------------------------------------- actions

    def _quality_key(self) -> str:
        label = self.quality_var.get()
        return next((k for k, v in self._quality_labels.items() if v == label), dfr.DEFAULT_MODE)

    def _on_toggle(self):
        status = self.controller.status()
        if status.game_key:
            self.controller.set_game(status.game_key, enabled=self.enabled_var.get(), mode=self._quality_key())
        self._refresh()

    def _on_quality(self, _event=None):
        status = self.controller.status()
        if status.game_key:
            self.controller.set_game(status.game_key, mode=self._quality_key())
        self._refresh()

    def _browse(self):
        start = self.controller.tool_dir() or os.path.expanduser("~")
        path = filedialog.askdirectory(parent=self.frame, initialdir=start, title=tr("dfr.browse_title"))
        if path:
            self.controller.set_tool_dir(os.path.normpath(path))
            missing = dfr.tool_missing_files(self.controller.tool_dir())
            if missing:
                messagebox.showwarning(
                    tr("dfr.section"), tr("dfr.tool_incomplete", files=", ".join(missing)), parent=self.frame
                )
            self._refresh()

    def _install(self):
        if self._installing:
            return
        if dfr._vrserver_running():
            messagebox.showinfo(tr("dfr.section"), tr("dfr.close_steamvr_first"), parent=self.frame)
            return
        tool_dir = self.controller.tool_dir()
        self._installing = True
        self.install_btn.configure(state="disabled")

        def work():
            ok = dfr.install_system_files(tool_dir)
            self.controller._next_system_check = 0.0

            def done():
                self._installing = False
                self.install_btn.configure(state="normal")
                if not ok:
                    messagebox.showwarning(tr("dfr.section"), tr("dfr.install_failed"), parent=self.frame)
                self._refresh()

            try:
                self.frame.after(0, done)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True, name="DfrInstall").start()

    # ------------------------------------------------------------- refresh

    def _poll(self):
        try:
            self._refresh()
            self.frame.after(POLL_MS, self._poll)
        except tk.TclError:
            pass  # window closed

    def _refresh(self):
        status = self.controller.status()
        has_game = bool(status.game_key)
        self.game_label.configure(
            text=tr("dfr.current_game", name=status.game_name)
            if has_game
            else tr("dfr.no_game")
            if status.steamvr
            else tr("dfr.steamvr_off")
        )
        # Mirror the saved per-game choice. Clicks call set_game on this same Tk thread
        # before the next poll, so this never undoes what the user just did.
        if self.enabled_var.get() != status.enabled:
            self.enabled_var.set(status.enabled)
        quality = self._quality_labels.get(status.mode, self._quality_labels[dfr.DEFAULT_MODE])
        if self.quality_var.get() != quality:
            self.quality_var.set(quality)
        usable = has_game and status.state not in (dfr.BLOCKED,)
        self.enabled_cb.configure(state="normal" if usable else "disabled")
        self.quality_box.configure(state="readonly" if usable else "disabled")

        text = tr(f"dfr.state_{status.state}", reason=status.detail)
        if not getattr(self.config.settings, "gui_foveation_gaze", False):
            text += " " + tr("dfr.gaze_off_hint")
        self.status_label.configure(text=text)

        tool_dir = status.tool_dir or self.controller.tool_dir()
        self.tool_label.configure(text=tool_dir or tr("dfr.tool_not_set"))
        missing = bool(dfr.tool_missing_files(tool_dir))
        _show(self.get_btn, missing)
        _show(self.install_btn, status.state == dfr.NEEDS_SYSTEM_FILES)


def _show(widget, visible: bool) -> None:
    # winfo_manager, not winfo_ismapped: the settings tab may be hidden.
    packed = widget.winfo_manager() == "pack"
    if visible and not packed:
        widget.pack(side="left", padx=(8, 0))
    elif not visible and packed:
        widget.pack_forget()
