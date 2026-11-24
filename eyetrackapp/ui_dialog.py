"""Small themed message and yes/no dialogs, in place of tkinter.messagebox.

The native alerts tkinter.messagebox shows crash the app on macOS: OpenCV bundles
SDL2, which loads Apple's GameController UI framework, and that framework traps
while releasing the alert after it closes. These dialogs are plain Tk windows in
the app's own theme instead, so they also match the rest of the app.

Each call blocks until the dialog closes (like messagebox) and returns the answer.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from localization import tr

WRAP = 380


def ask_yes_no(parent, title: str, message: str, destructive: bool = False) -> bool:
    """Yes (True) or No (False); closing the window or Escape is No. ``destructive``
    makes No the default (Return) and leaves Yes unhighlighted, so a stray Return
    never deletes or resets anything."""
    buttons = ((tr("dialog.no"), False), (tr("dialog.yes"), True))
    return bool(_show(parent, title, message, buttons, default=0 if destructive else 1))


def show_info(parent, title: str, message: str) -> None:
    _show(parent, title, message, ((tr("dialog.ok"), True),))


# A warning or an error reads the same: the message says what happened.
show_warning = show_info
show_error = show_info


def _show(parent, title: str, message: str, buttons, default: int = -1) -> object:
    """``buttons``: (label, value) pairs, left to right. ``default`` (an index; the
    last by default) is highlighted and answers Return; the first is what Escape or
    closing the window answer."""
    default = default % len(buttons)
    master = _master(parent)
    window = tk.Toplevel(master)
    window.withdraw()
    window.title(title)
    window.resizable(False, False)
    try:
        window.transient(master.winfo_toplevel())
    except tk.TclError:
        pass
    result = {"value": buttons[0][1]}

    def answer(value):
        result["value"] = value
        window.destroy()

    body = ttk.Frame(window, padding=(20, 18, 20, 16))
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=message, wraplength=WRAP, justify="left").pack(anchor="w", fill="x")
    row = ttk.Frame(body)
    row.pack(anchor="e", pady=(16, 0))
    focus = None
    for index, (label, value) in enumerate(buttons):
        is_default = index == default
        button = ttk.Button(
            row,
            text=label,
            command=lambda v=value: answer(v),
            # Only a safe default stands out; a destructive question's No stays plain.
            style="Accent.TButton" if is_default and value is not False else "TButton",
        )
        button.pack(side="left", padx=(0 if index == 0 else 8, 0))
        if is_default:
            focus = button
    window.protocol("WM_DELETE_WINDOW", lambda: answer(buttons[0][1]))
    window.bind("<Escape>", lambda _e: answer(buttons[0][1]))
    # Return answers the default. Kept on the window too, so it can be checked
    # without relying on how each platform delivers a simulated key press.
    window.answer_default = lambda: answer(buttons[default][1])
    window.bind("<Return>", lambda _e: window.answer_default())

    _place(window, master)
    window.deiconify()
    try:
        from contributions.native import decorate

        decorate(window)  # app icon and, on Windows, a title bar in the theme
    except Exception:
        pass
    try:
        window.grab_set()
    except tk.TclError:
        pass  # another window holds the grab: still usable, just not modal
    try:
        window.focus_force()  # keys go to the dialog, not the window behind it
    except tk.TclError:
        pass
    if focus is not None:
        focus.focus_set()
    window.wait_window()
    return result["value"]


def _master(parent):
    if isinstance(parent, tk.Misc):
        return parent
    master = tk._get_default_root("show a dialog")
    return master


def _place(window, master) -> None:
    """Centred over the window it belongs to, kept on screen."""
    window.update_idletasks()
    width, height = window.winfo_reqwidth(), window.winfo_reqheight()
    top = master.winfo_toplevel()
    if top.winfo_viewable():
        x = top.winfo_rootx() + (top.winfo_width() - width) // 2
        y = top.winfo_rooty() + (top.winfo_height() - height) // 3
    else:
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 3
    x = max(0, min(x, window.winfo_screenwidth() - width))
    y = max(0, min(y, window.winfo_screenheight() - height - 40))
    window.geometry(f"+{x}+{y}")
