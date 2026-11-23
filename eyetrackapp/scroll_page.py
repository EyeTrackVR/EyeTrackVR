"""A main-window page that scrolls when it is taller than the window.

Build the page's content into ``ScrollPage.body``. While the content fits, the
body fills the page exactly as a plain frame would (fill/expand keep working)
and no scrollbar shows; once the window is too short for it, a vertical
scrollbar appears and the mouse wheel scrolls it.

The page asks for its content's width, so the window still sizes itself to the
widest page (eyetrackapp's _grow_to_fit), but only a small height: the window's
height then decides, and the bottom bar is never pushed out of view.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

_MIN_HEIGHT = 120
# Widgets that use the wheel themselves: scrolling the page under them as well
# would move two things at once.
_OWN_WHEEL = {"TCombobox", "TSpinbox", "Spinbox", "TScale", "Scale", "Text", "Listbox"}


class ScrollPage(ttk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        background = ttk.Style(self).lookup("TFrame", "background")
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, height=_MIN_HEIGHT, yscrollincrement=24)
        if background:
            self.canvas.configure(background=background)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._asked_width = None
        self.body = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._sync, add="+")
        self.canvas.bind("<Configure>", self._sync, add="+")
        _install_wheel(self.winfo_toplevel())

    @property
    def overflowing(self) -> bool:
        return bool(self.scrollbar.winfo_manager())

    def _sync(self, _event=None) -> None:
        try:
            width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
            need_w, need_h = self.body.winfo_reqwidth(), self.body.winfo_reqheight()
            # Ask for the content's width (the window grows to the widest page),
            # but only a small height (the window's height decides).
            if need_w != self._asked_width:
                self._asked_width = need_w
                self.canvas.configure(width=need_w)
            if width <= 1 or height <= 1:
                return
            full = max(height, need_h)
            self.canvas.itemconfigure(self._window, width=width, height=full)
            self.canvas.configure(scrollregion=(0, 0, width, full))
            overflow = need_h > height
            if overflow and not self.overflowing:
                self.scrollbar.pack(side="right", fill="y", before=self.canvas)
            elif not overflow and self.overflowing:
                self.scrollbar.pack_forget()
                self.canvas.yview_moveto(0)
        except tk.TclError:
            pass  # the window is going away

    def scroll(self, units: int) -> None:
        if self.overflowing:
            self.canvas.yview_scroll(units, "units")


def _page_under(widget) -> ScrollPage | None:
    while isinstance(widget, tk.Misc):
        if isinstance(widget, ScrollPage):
            return widget
        if widget.winfo_class() in _OWN_WHEEL:
            return None
        widget = widget.master
    return None


def _wheel_units(event) -> int:
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    delta = getattr(event, "delta", 0) or 0
    if not delta:
        return 0
    # Windows sends multiples of 120 per notch; macOS sends small steps, many of them.
    steps = max(1, abs(delta) // 120) if sys.platform == "win32" else 1
    return -steps if delta > 0 else steps


def _on_wheel(event) -> None:
    try:
        # A string for Tk's own internal windows (a combobox's list): not a page.
        page = _page_under(event.widget)
    except tk.TclError:
        return
    if page is not None:
        units = _wheel_units(event)
        if units:
            page.scroll(units)


def _install_wheel(top) -> None:
    """One wheel binding per window, finding the page under the pointer."""
    if getattr(top, "_scroll_page_wheel", False):
        return
    top._scroll_page_wheel = True
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        top.bind_all(sequence, _on_wheel, add="+")
