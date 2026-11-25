"""Tk roots for the GUI tests (a helper module, not collected by pytest).

CI runs the Linux suite under xvfb-run; elsewhere, a machine without a desktop
display skips these tests instead of failing them. One root serves a whole test
module: Windows' Python occasionally fails to find Tcl's library files when a
process creates many interpreters.

Use it with ``from tests.tk_support import tk_module_root, tk_root  # noqa: F401``."""

import time

import pytest


def new_root(withdraw=True):
    """A Tk root, or a skip when there is no display."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"needs a desktop display ({exc})")
    if withdraw:
        root.withdraw()
    return root


def clear(root):
    """Remove what a test left on ``root``: its windows and its pending ``after`` calls."""
    for after_id in root.tk.splitlist(root.tk.call("after", "info")):
        # Tcl-level cancel: the widget that scheduled it still owns (and later deletes) the command.
        root.tk.call("after", "cancel", after_id)
    for child in root.winfo_children():
        child.destroy()


def drain(root, condition, timeout=4.0):
    """Run Tk's event loop until ``condition()`` holds (workers report back through it)."""
    until = time.monotonic() + timeout
    while not condition() and time.monotonic() < until:
        root.update()
        time.sleep(0.01)
    assert condition()


def destroy(root):
    import tkinter as tk

    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture(scope="module")
def tk_module_root():
    root = new_root()
    yield root
    destroy(root)


@pytest.fixture
def tk_root(tk_module_root):
    """The module's withdrawn root, emptied after each test."""
    yield tk_module_root
    clear(tk_module_root)
