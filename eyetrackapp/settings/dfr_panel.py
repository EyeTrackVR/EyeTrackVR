"""
"Foveated rendering in SteamVR games" section of General settings (Windows).

Until PimaxMagic4All is set up it shows one "Set up" button (ovr/dfr_setup.py). After
that: the SteamVR game in front and a per-game switch, quality and vertical flip,
backed by ovr/dfr.py. Live: it polls the controller, and changes apply to the running
game at once. Not a settings module, since its state is per game and changes are
applied immediately rather than through the validate-and-save cycle.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from localization import tr
from ovr import dfr, dfr_setup
from utils.tooltips import attach_tooltip

POLL_MS = 500
QUALITY_ORDER = ("maximum", "balanced", "minimum", "debug")


class DfrPanel:
    def __init__(self, controller: dfr.DfrController, config, enable_gaze=None):
        self.controller = controller
        self.config = config
        # Turns on the "Foveated rendering gaze" setting through its own checkbox, so
        # the settings tab doesn't write the old value back.
        self.enable_gaze = enable_gaze
        self.frame: ttk.LabelFrame | None = None
        self._setup_step: str | None = None  # "download" / "system_files" while setup runs

    # ------------------------------------------------------------- build

    def build(self, parent) -> ttk.LabelFrame:
        self.frame = ttk.LabelFrame(parent, text=tr("dfr.section"))

        self.game_label = ttk.Label(self.frame, text="")

        self.switch_row = ttk.Frame(self.frame)
        self.enabled_var = tk.BooleanVar(value=False)
        self.enabled_cb = ttk.Checkbutton(
            self.switch_row, text=tr("dfr.enable_for_game"), variable=self.enabled_var, command=self._on_toggle
        )
        self.enabled_cb.pack(side="left")
        attach_tooltip(self.enabled_cb, tr("dfr.enable_for_game_tip"))
        ttk.Label(self.switch_row, text=tr("dfr.quality")).pack(side="left", padx=(16, 4))
        self._quality_labels = {key: tr(f"dfr.quality_{key}") for key in QUALITY_ORDER}
        self.quality_var = tk.StringVar(value=self._quality_labels[dfr.DEFAULT_MODE])
        self.quality_box = ttk.Combobox(
            self.switch_row,
            textvariable=self.quality_var,
            state="readonly",
            width=14,
            values=[self._quality_labels[k] for k in QUALITY_ORDER],
        )
        self.quality_box.pack(side="left")
        self.quality_box.bind("<<ComboboxSelected>>", self._on_change)
        attach_tooltip(self.quality_box, tr("dfr.quality_tip"))
        self.invert_var = tk.BooleanVar(value=False)
        self.invert_cb = ttk.Checkbutton(
            self.switch_row, text=tr("dfr.invert_y"), variable=self.invert_var, command=self._on_change
        )
        self.invert_cb.pack(side="left", padx=(16, 0))
        attach_tooltip(self.invert_cb, tr("dfr.invert_y_tip"))

        self.method_row = ttk.Frame(self.frame)
        method_label = ttk.Label(self.method_row, text=tr("dfr.method_label"))
        method_label.pack(side="left", padx=(0, 4))
        self._method_labels = {
            dfr.METHOD_INJECT: tr("dfr.method_inject"),
            dfr.METHOD_NATIVE: tr("dfr.method_native"),
            dfr.METHOD_OPENXR: tr("dfr.method_openxr"),
            dfr.METHOD_NONE: tr("dfr.method_none"),
        }
        self.method_var = tk.StringVar(value="")
        self.method_box = ttk.Combobox(self.method_row, textvariable=self.method_var, state="readonly", width=34)
        self.method_box.pack(side="left")
        self.method_box.bind("<<ComboboxSelected>>", self._on_method)
        attach_tooltip(self.method_box, tr("dfr.method_tip"))
        attach_tooltip(method_label, tr("dfr.method_tip"))

        self.status_label = ttk.Label(self.frame, text="", wraplength=620, justify="left")

        self.action_row = ttk.Frame(self.frame)
        self.setup_btn = ttk.Button(self.action_row, text=tr("dfr.set_up"), command=self._set_up)
        attach_tooltip(self.setup_btn, tr("dfr.set_up_tip"))
        self.browse_btn = ttk.Button(self.action_row, text=tr("dfr.browse"), command=self._browse)
        attach_tooltip(self.browse_btn, tr("dfr.browse_tip"))
        self.retry_btn = ttk.Button(self.action_row, text=tr("dfr.retry"), command=self._retry)
        self.gaze_btn = ttk.Button(self.action_row, text=tr("dfr.turn_on_gaze"), command=self._turn_on_gaze)

        self.game_label.pack(fill="x", padx=8, pady=(4, 2))
        self.switch_row.pack(fill="x", padx=8, pady=2)
        self.method_row.pack(fill="x", padx=8, pady=2)
        self.status_label.pack(fill="x", padx=8, pady=(2, 4))
        self.action_row.pack(fill="x", padx=8, pady=(0, 6))

        self.frame.after(0, self._poll)
        return self.frame

    # ------------------------------------------------------------- actions

    def _quality_key(self) -> str:
        label = self.quality_var.get()
        return next((k for k, v in self._quality_labels.items() if v == label), dfr.DEFAULT_MODE)

    def _gaze_on(self) -> bool:
        return bool(getattr(self.config.settings, "gui_foveation_gaze", False))

    def _turn_on_gaze(self):
        if self.enable_gaze is not None and not self._gaze_on():
            self.enable_gaze()
        self._refresh()

    def _on_toggle(self):
        status = self.controller.status()
        if status.game_key:
            if self.enabled_var.get():
                self._turn_on_gaze()  # the game needs the gaze before it is attached
            self.controller.set_game(status.game_key, enabled=self.enabled_var.get(), mode=self._quality_key())
        self._refresh()

    def _on_change(self, _event=None):
        status = self.controller.status()
        if status.game_key:
            self.controller.set_game(status.game_key, mode=self._quality_key(), invert_y=self.invert_var.get())
        self._refresh()

    def _method_choices(self, status) -> dict:
        """Combobox text -> method. "Automatic" names what was detected."""
        detected = self._method_labels.get(status.method, self._method_labels[dfr.METHOD_NONE])
        choices = {tr("dfr.method_auto", method=detected): dfr.METHOD_AUTO}
        choices.update({label: method for method, label in self._method_labels.items()})
        return choices

    def _on_method(self, _event=None):
        status = self.controller.status()
        method = self._method_choices(status).get(self.method_var.get())
        if status.game_key and method:
            self.controller.set_game(status.game_key, method=method)
        self._refresh()

    def _retry(self):
        self.controller.retry_attach()
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

    def _set_up(self):
        if self._setup_step is not None:
            return
        self._setup_step = "start"
        self._refresh()

        def progress(step):
            self._setup_step = step  # shown by the next poll

        def work():
            error = tool_dir = None
            try:
                tool_dir = dfr_setup.run(self.controller, progress)
            except dfr_setup.SetupError as e:
                error = e.reason
            except Exception:
                dfr_setup.logger.exception("DFR setup failed")
                error = dfr_setup.DOWNLOAD_FAILED

            def done():
                self._setup_step = None
                if error is None:
                    dfr_setup.finish(self.controller, tool_dir)
                    self._turn_on_gaze()
                else:
                    self.controller.recheck_setup()
                    messagebox.showwarning(tr("dfr.section"), tr(f"dfr.setup_{error}"), parent=self.frame)
                self._refresh()

            try:
                self.frame.after(0, done)
            except (tk.TclError, RuntimeError):
                pass  # window closed meanwhile

        threading.Thread(target=work, daemon=True, name="DfrSetup").start()

    # ------------------------------------------------------------- refresh

    def _poll(self):
        try:
            self._refresh()
            self.frame.after(POLL_MS, self._poll)
        except tk.TclError:
            pass  # window closed

    def _status_text(self, status: dfr.Status) -> str:
        if self._setup_step is not None:
            return tr("dfr.setup_downloading" if self._setup_step == "download" else "dfr.setup_installing")
        return dfr.status_text(status)

    def _refresh(self):
        status = self.controller.status()
        in_setup = status.state in dfr.SETUP_STATES
        has_game = bool(status.game_key)
        _show(self.game_label, not in_setup, before=self.status_label, fill="x", padx=8, pady=(4, 2))
        _show(self.switch_row, not in_setup, before=self.status_label, fill="x", padx=8, pady=2)
        _show(self.method_row, not in_setup, before=self.status_label, fill="x", padx=8, pady=2)
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
        if self.invert_var.get() != status.invert_y:
            self.invert_var.set(status.invert_y)
        usable = has_game and status.state not in dfr.NO_SWITCH_STATES
        choices = self._method_choices(status)
        self.method_box.configure(
            values=list(choices), state="readonly" if has_game and status.state != dfr.BLOCKED else "disabled"
        )
        shown = next((text for text, method in choices.items() if method == status.method_choice), "")
        if self.method_var.get() != shown:
            self.method_var.set(shown)
        self.enabled_cb.configure(state="normal" if usable else "disabled")
        self.quality_box.configure(state="readonly" if usable else "disabled")
        self.invert_cb.configure(state="normal" if usable else "disabled")

        self.status_label.configure(text=self._status_text(status))

        busy = self._setup_step is not None
        can_set_up = status.state in (dfr.TOOL_MISSING, dfr.NEEDS_SYSTEM_FILES)
        self.setup_btn.configure(state="disabled" if busy else "normal")
        self.browse_btn.configure(state="disabled" if busy else "normal")
        _show(self.setup_btn, can_set_up, side="left")
        _show(self.browse_btn, can_set_up, side="left", padx=(8, 0))
        _show(self.retry_btn, status.state == dfr.ATTACH_FAILED, side="left")
        _show(self.gaze_btn, status.state == dfr.GAZE_OFF and not self._gaze_on(), side="left")


def _show(widget, visible: bool, **pack) -> None:
    # winfo_manager, not winfo_ismapped: the settings tab may be hidden.
    packed = widget.winfo_manager() == "pack"
    if visible and not packed:
        widget.pack(**pack)
    elif not visible and packed:
        widget.pack_forget()
