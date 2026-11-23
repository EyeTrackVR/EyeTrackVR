"""
"Foveated rendering in SteamVR games" section of General settings (Windows).

Until PimaxMagic4All is set up it shows one "Set up" button (ovr/dfr_setup.py). After
that: the SteamVR game in front and a per-game switch, quality and vertical flip,
backed by ovr/dfr.py. Live: it polls the controller, and changes apply to the running
game at once. Not a settings module, since its state is per game and changes are
applied immediately rather than through the validate-and-save cycle.
"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont

from localization import tr
from ovr import dfr, dfr_setup, quad_views
from utils.tooltips import attach_tooltip

POLL_MS = 500
LABEL_WIDTH = 9  # characters; lines up the Quality and Method boxes
QUALITY_ORDER = dfr.user_modes()  # release builds leave out the debug view


class DfrPanel:
    def __init__(self, controller: dfr.DfrController, config, enable_gaze=None):
        self.controller = controller
        self.config = config
        # Turns on the "Foveated rendering support" setting through its own checkbox, so
        # the settings tab doesn't write the old value back.
        self.enable_gaze = enable_gaze
        self.frame: ttk.Frame | None = None
        self._setup_step: str | None = None  # "download" / "system_files" while setup runs

    # ------------------------------------------------------------- build

    def build(self, parent, framed: bool = True) -> ttk.Frame:
        """The panel in its own titled box, or (framed=False) as plain rows for a
        section that already has the title."""
        self.frame = ttk.LabelFrame(parent, text=tr("dfr.section")) if framed else ttk.Frame(parent)
        bold = _bold_font(self.frame)

        # Game name, then one row per setting with the labels in one column. Rows that
        # don't apply to the current game are hidden rather than greyed out.
        self.game_label = ttk.Label(self.frame, text="", font=bold)

        self.switch_row = ttk.Frame(self.frame)
        self.enabled_var = tk.BooleanVar(value=False)
        self.enabled_cb = ttk.Checkbutton(
            self.switch_row, text=tr("dfr.enable_for_game"), variable=self.enabled_var, command=self._on_toggle
        )
        self.enabled_cb.pack(side="left")
        attach_tooltip(self.enabled_cb, tr("dfr.enable_for_game_tip"))

        self.quality_row = ttk.Frame(self.frame)
        ttk.Label(self.quality_row, text=tr("dfr.quality"), width=LABEL_WIDTH).pack(side="left")
        self._quality_labels = {key: tr(f"dfr.quality_{key}") for key in QUALITY_ORDER}
        self.quality_var = tk.StringVar(value=self._quality_labels[dfr.DEFAULT_MODE])
        self.quality_box = ttk.Combobox(
            self.quality_row,
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
            self.quality_row, text=tr("dfr.invert_y"), variable=self.invert_var, command=self._on_change
        )
        self.invert_cb.pack(side="left", padx=(16, 0))
        attach_tooltip(self.invert_cb, tr("dfr.invert_y_tip"))

        self.method_row = ttk.Frame(self.frame)
        method_label = ttk.Label(self.method_row, text=tr("dfr.method_label"), width=LABEL_WIDTH)
        method_label.pack(side="left")
        self._method_labels = {
            dfr.METHOD_INJECT: tr("dfr.method_inject"),
            dfr.METHOD_NATIVE: tr("dfr.method_native"),
            dfr.METHOD_OPENXR: tr("dfr.method_openxr"),
            dfr.METHOD_NONE: tr("dfr.method_none"),
        }
        self.method_var = tk.StringVar(value="")
        self.method_box = ttk.Combobox(self.method_row, textvariable=self.method_var, state="readonly", width=28)
        self.method_box.pack(side="left")
        self.method_box.bind("<<ComboboxSelected>>", self._on_method)
        attach_tooltip(self.method_box, tr("dfr.method_tip"))
        attach_tooltip(method_label, tr("dfr.method_tip"))

        self.status_label = ttk.Label(self.frame, text="", wraplength=560, justify="left")

        self.action_row = ttk.Frame(self.frame)
        self.setup_btn = ttk.Button(self.action_row, text=tr("dfr.set_up"), command=self._set_up)
        attach_tooltip(self.setup_btn, tr("dfr.set_up_tip"))
        self.retry_btn = ttk.Button(self.action_row, text=tr("dfr.retry"), command=self._retry)
        self.gaze_btn = ttk.Button(self.action_row, text=tr("dfr.turn_on_gaze"), command=self._turn_on_gaze)

        self.status_label.pack(fill="x", padx=8, pady=(6, 4))
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
                    if not quad_views.installed():
                        # PimaxMagic4All is ready either way; only OpenXR games miss out.
                        messagebox.showwarning(tr("dfr.section"), tr("dfr.setup_quad_views_failed"), parent=self.frame)
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
            return tr(
                {"download": "dfr.setup_downloading", "download_quad_views": "dfr.setup_downloading_quad_views"}.get(
                    self._setup_step, "dfr.setup_installing"
                )
            )
        text = dfr.status_text(status)
        if not status.quad_views and status.state not in dfr.SET_UP_STATES:
            text += ("" if text.endswith("。") else " ") + tr("dfr.quad_views_missing")
        return text

    def _show_rows(self, *rows) -> None:
        """Pack the visible rows above the status line, in this order."""
        wanted = [row for row, visible in rows if visible]
        if [row for row, _ in rows if row.winfo_manager() == "pack"] == wanted:
            return
        for row, _ in rows:
            row.pack_forget()
        for i, row in enumerate(wanted):
            row.pack(before=self.status_label, fill="x", padx=8, pady=(6 if i == 0 else 2, 2))

    def _refresh(self):
        status = self.controller.status()
        has_game = bool(status.game_key) and status.state not in dfr.SETUP_STATES
        usable = has_game and status.state not in dfr.NO_SWITCH_STATES
        self.game_label.configure(text=status.game_name if has_game else "")
        self._show_rows(
            (self.game_label, has_game),
            (self.switch_row, usable),
            (self.quality_row, usable),
            (self.method_row, has_game and status.state != dfr.BLOCKED),
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
        choices = self._method_choices(status)
        self.method_box.configure(values=list(choices))
        shown = next((text for text, method in choices.items() if method == status.method_choice), "")
        if self.method_var.get() != shown:
            self.method_var.set(shown)

        self.status_label.configure(text=self._status_text(status))

        busy = self._setup_step is not None
        # Quad-Views-Foveated alone can be added any time, game running or not.
        can_set_up = status.state in dfr.SET_UP_STATES or not status.quad_views
        self.setup_btn.configure(state="disabled" if busy else "normal")
        _show(self.setup_btn, can_set_up, side="left")
        _show(self.retry_btn, status.state == dfr.ATTACH_FAILED, side="left")
        _show(self.gaze_btn, status.state == dfr.GAZE_OFF and not self._gaze_on(), side="left")


def _bold_font(widget):
    """sv_ttk's strong body font (already DPI-scaled), else a bold TkDefaultFont."""
    try:
        return tkfont.nametofont("SunValleyBodyStrongFont", root=widget)
    except tk.TclError:
        font = tkfont.nametofont("TkDefaultFont", root=widget).copy()
        font.configure(weight="bold")
        return font


def _show(widget, visible: bool, **pack) -> None:
    # winfo_manager, not winfo_ismapped: the settings tab may be hidden.
    packed = widget.winfo_manager() == "pack"
    if visible and not packed:
        widget.pack(**pack)
    elif not visible and packed:
        widget.pack_forget()
