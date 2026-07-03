"""Lightweight hover tooltips that work under sv-ttk dark.

Tk ships no built-in tooltip widget, and stdlib's ``idlelib.tooltip.Hovertip``
uses a hardcoded light background that looks broken on a dark theme. This
module is small enough to live inline rather than pulling in another dep.

Design choices that fix the macOS/Aqua flicker we hit with a naïve approach:

* **One Toplevel per Tooltip, reused.** Built lazily on first hover, then kept
  around hidden between showings. Re-creating it on every Enter caused the
  visible flicker: Aqua maps the new window at (0,0), processes layout,
  applies overrideredirect, then jumps it into place. Reuse skips all that.
* **``-alpha 0`` until placed.** Even with ``withdraw()`` + ``deiconify()``,
  the first ``deiconify`` on macOS occasionally shows one frame at the old
  geometry before settling. Setting alpha to 0, positioning, then alpha to 1
  guarantees the user only ever sees the final placement.
* **Hide via ``withdraw``.** Destroying the Toplevel each time is slow and
  leaves a brief ghost on Aqua. ``withdraw`` is immediate.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


# Style applied to the inner label. Configured once on first use against
# whichever root the first tooltip is attached to; ttk styles are tied to a
# Tk interpreter, not a specific widget, so this is safe to share.
_STYLE_NAME = "Tooltip.TLabel"
_BG = "#1f1f1f"
_FG = "#e6e6e6"
_BORDER = "#3a3a3a"

# Set to True after we've configured the shared ttk style on the interpreter.
_STYLE_READY = False


def _ensure_style(widget: tk.Misc) -> None:
    global _STYLE_READY
    if _STYLE_READY:
        return
    try:
        style = ttk.Style(widget)
        style.configure(
            _STYLE_NAME,
            background=_BG,
            foreground=_FG,
            padding=(8, 4),
        )
        _STYLE_READY = True
    except tk.TclError:
        # Style call can fail during shutdown; tooltips just won't show.
        pass


class Tooltip:
    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        delay_ms: int = 400,
        wrap_length: int = 320,
    ):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wrap_length = wrap_length
        self._tip: tk.Toplevel | None = None
        self._label: ttk.Label | None = None
        self._after_id: str | None = None
        # Track whether the tip is currently mapped so we don't re-deiconify
        # mid-hover (which can cause Aqua to bounce the window briefly).
        self._visible = False
        # Last cursor screen position seen for this widget. We position the
        # tooltip near the cursor (not the widget origin) so it tracks where
        # the user is actually looking.
        self._last_x_root = 0
        self._last_y_root = 0
        # ``add="+"`` so tooltip bindings don't clobber existing handlers on
        # the same widget (e.g. a custom <Enter> on a button for visual flair).
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")

    def update_text(self, text: str) -> None:
        self.text = text
        if self._label is not None:
            try:
                self._label.configure(text=text)
            except tk.TclError:
                pass

    def _on_enter(self, event=None) -> None:
        if event is not None:
            self._last_x_root = event.x_root
            self._last_y_root = event.y_root
        self._cancel_pending()
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show)
        except tk.TclError:
            self._after_id = None

    def _on_motion(self, event) -> None:
        # While the tooltip is *not* yet visible we track the cursor so it
        # appears near where the user is hovering. Once visible we leave it
        # alone: sliding the tooltip around feels jittery and is also how
        # we get into <Enter>/<Leave> ping-pong.
        if self._visible:
            return
        self._last_x_root = event.x_root
        self._last_y_root = event.y_root

    def _on_leave(self, _event=None) -> None:
        self._cancel_pending()
        self._hide()

    def _on_destroy(self, _event=None) -> None:
        self._cancel_pending()
        tip = self._tip
        self._tip = None
        self._label = None
        self._visible = False
        if tip is None:
            return
        try:
            tip.destroy()
        except tk.TclError:
            pass

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _ensure_tip(self) -> tk.Toplevel | None:
        """Build the Toplevel + label once, then reuse them for every show."""
        if self._tip is not None:
            return self._tip
        try:
            if not self.widget.winfo_exists():
                return None
        except tk.TclError:
            return None
        _ensure_style(self.widget)
        try:
            tip = tk.Toplevel(self.widget)
        except tk.TclError:
            return None
        tip.withdraw()
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        # ``-alpha 0`` keeps the window invisible during the first deiconify
        # so position changes never flash to the user. We flip it to 1 once
        # geometry is in place. If the platform doesn't support alpha (rare
        # under modern Tk) we just skip the trick; withdraw/deiconify alone
        # works well enough on those platforms.
        self._alpha_supported = True
        try:
            tip.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            self._alpha_supported = False
        tip.configure(bg=_BORDER)
        # 1px outer border in #3a3a3a around the body.
        inner = tk.Frame(tip, bg=_BG, padx=0, pady=0)
        inner.pack(padx=1, pady=1)
        label = ttk.Label(
            inner,
            text=self.text,
            style=_STYLE_NAME,
            wraplength=self.wrap_length,
            justify="left",
        )
        label.pack()
        self._tip = tip
        self._label = label
        return tip

    def _show(self) -> None:
        self._after_id = None
        if self._visible:
            return
        tip = self._ensure_tip()
        if tip is None or self._label is None:
            return
        try:
            self._label.configure(text=self.text)
        except tk.TclError:
            return

        # Make sure size info is current before placing the window.
        try:
            tip.update_idletasks()
        except tk.TclError:
            return

        x = self._last_x_root + 14
        y = self._last_y_root + 18
        try:
            screen_w = tip.winfo_screenwidth()
            screen_h = tip.winfo_screenheight()
            tip_w = tip.winfo_reqwidth()
            tip_h = tip.winfo_reqheight()
            if x + tip_w > screen_w - 8:
                x = max(8, self._last_x_root - tip_w - 14)
            if y + tip_h > screen_h - 8:
                y = max(8, self._last_y_root - tip_h - 14)
        except tk.TclError:
            pass

        try:
            tip.wm_geometry(f"+{int(x)}+{int(y)}")
            tip.deiconify()
            if self._alpha_supported:
                tip.wm_attributes("-alpha", 1.0)
        except tk.TclError:
            return
        self._visible = True

    def _hide(self) -> None:
        if not self._visible:
            return
        tip = self._tip
        self._visible = False
        if tip is None:
            return
        try:
            # Re-arm the alpha gate so the next show doesn't flash old contents.
            if self._alpha_supported:
                tip.wm_attributes("-alpha", 0.0)
            tip.withdraw()
        except tk.TclError:
            pass


def attach_tooltip(widget: tk.Widget, text: str, **kwargs) -> Tooltip:
    """Attach a hover tooltip to ``widget``. Returns the Tooltip instance so
    callers can later update text via ``.update_text()`` if needed."""
    return Tooltip(widget, text, **kwargs)
