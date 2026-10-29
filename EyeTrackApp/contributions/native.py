"""Shared icon and native window chrome for contribution windows."""

from pathlib import Path
import sys


def asset(name):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "Images" / name


def dark_titlebar(hwnd):
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
    dwm.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    for attribute, value in ((20, 1), (35, 0x202020), (36, 0xEEEEEE)):
        color = ctypes.c_int(value)
        dwm(wintypes.HWND(hwnd), attribute, ctypes.byref(color), ctypes.sizeof(color))


def decorate(window):
    try:
        if sys.platform == "win32":
            window.iconbitmap(str(asset("logo.ico")))
            import ctypes
            from ctypes import wintypes

            ancestor = ctypes.windll.user32.GetAncestor
            ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
            ancestor.restype = wintypes.HWND
            window.update_idletasks()
            dark_titlebar(ancestor(window.winfo_id(), 2))
        else:
            import tkinter as tk

            window._brand_icon = tk.PhotoImage(file=str(asset("logo.png")))
            window.iconphoto(False, window._brand_icon)
    except (OSError, RuntimeError, __import__("tkinter").TclError):
        pass
