"""The app's own message and yes/no dialogs (ui_dialog.py), used instead of native
alerts, which crash the app on macOS."""

import pytest

import ui_dialog


@pytest.fixture
def root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No desktop display available")
    root.withdraw()
    yield root
    root.destroy()


def _dialog(root):
    return next(w for w in root.winfo_children() if w.winfo_class() == "Toplevel")


def _buttons(widget):
    found = []
    for child in widget.winfo_children():
        if child.winfo_class() == "TButton":
            found.append(child)
        found += _buttons(child)
    return found


def _answer_with(root, act):
    root.after(150, lambda: act(_dialog(root)))

    def give_up():  # a dialog the test failed to close must not hang the suite
        for window in root.winfo_children():
            if window.winfo_class() == "Toplevel":
                window.destroy()

    root.after(5000, give_up)


def test_yes_and_no(root):
    _answer_with(root, lambda d: _buttons(d)[-1].invoke())  # the right-hand button
    assert ui_dialog.ask_yes_no(root, "Reset settings", "Reset these settings?") is True
    _answer_with(root, lambda d: _buttons(d)[0].invoke())
    assert ui_dialog.ask_yes_no(root, "Reset settings", "Reset these settings?") is False


def test_escape_and_closing_the_window_mean_no(root):
    _answer_with(root, lambda d: d.event_generate("<Escape>"))
    assert ui_dialog.ask_yes_no(root, "Delete config", "Delete?") is False
    # The window manager's close button runs the protocol handler (a Tcl command name).
    _answer_with(root, lambda d: d.tk.call(d.protocol("WM_DELETE_WINDOW")))
    assert ui_dialog.ask_yes_no(root, "Delete config", "Delete?") is False


def test_message_has_one_button_and_closes(root):
    def check(dialog):
        buttons = _buttons(dialog)
        assert [str(b.cget("text")) for b in buttons] == [ui_dialog.tr("dialog.ok")]
        buttons[0].invoke()

    _answer_with(root, check)
    assert ui_dialog.show_info(root, "EyeTrackVR", "Restart to apply.") is None
    assert not [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]


def test_return_answers_no_on_a_destructive_question(root):
    # What Return does (window.answer_default, bound to <Return>); a simulated key
    # press only reaches a window that has the focus, which CI displays don't give.
    def press_return(dialog):
        assert dialog.bind("<Return>")
        dialog.answer_default()

    _answer_with(root, press_return)
    assert ui_dialog.ask_yes_no(root, "Delete config", "Delete?", destructive=True) is False
    _answer_with(root, press_return)
    assert ui_dialog.ask_yes_no(root, "Restart", "Restart now?") is True
