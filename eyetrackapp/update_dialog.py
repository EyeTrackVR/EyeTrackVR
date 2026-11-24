"""
The "a new version is available" window, and the checks that open it.

One check runs at startup (if "Check For Updates" is on); General settings has a button
for another. The window offers to update in place where the build can (utils/updater.py),
the release page otherwise, and "Skip this version". Installing only ever starts from
the user's click.
"""

import logging
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

import ui_dialog

from localization import tr
from utils import updater

logger = logging.getLogger(__name__)

NOTES_MAX_CHARS = 4000

# Set by install(): what check_now() needs from the running app.
_app: dict = {}


def install(root, config, version: str, quit_app, style_window=None) -> None:
    """Remember the running app, for the startup check and General settings' button.
    ``quit_app`` closes the app (so the installer can replace it); ``style_window``
    themes a new Toplevel."""
    _app.update(root=root, config=config, version=version, quit_app=quit_app, style_window=style_window)


def check_at_startup() -> None:
    if _app and getattr(_app["config"].settings, "gui_update_check", True):
        _check(manual=False)


def check_now() -> None:
    """The user asked: also say so when there is nothing new, or it failed."""
    if _app:
        _check(manual=True)


def _check(manual: bool) -> None:
    root, settings, version = _app["root"], _app["config"].settings, _app["version"]
    prereleases = bool(getattr(settings, "gui_update_beta", False))
    # A manual check shows a version the user chose to skip again.
    skipped = "" if manual else str(getattr(settings, "gui_update_skip_version", "") or "")

    def work():
        update, failed = None, False
        try:
            update = updater.check(version, prereleases, skipped)
        except Exception:
            failed = True
            logger.info("Could not check for updates.", exc_info=True)

        def show():
            if update is not None:
                logger.info("Update available: %s (installed: %s)", update.version, version)
                UpdateWindow(root, update, _app["config"], _app["quit_app"], _app["style_window"]).show()
            elif manual and failed:
                ui_dialog.show_warning(root, tr("update.title"), tr("update.check_failed"))
            elif manual:
                ui_dialog.show_info(root, tr("update.title"), tr("update.up_to_date", version=version))
            else:
                logger.info("No newer release than %s.", version)

        try:
            root.after(0, show)
        except (tk.TclError, RuntimeError):
            pass  # the app closed meanwhile

    threading.Thread(target=work, daemon=True, name="UpdateCheck").start()


class UpdateWindow:
    def __init__(self, root, update: updater.Update, config, quit_app, style_window=None):
        self.root = root
        self.update = update
        self.config = config
        self.quit_app = quit_app
        self.style_window = style_window
        self.window: tk.Toplevel | None = None
        self._cancel = threading.Event()
        self._busy = False

    def show(self) -> None:
        win = self.window = tk.Toplevel(self.root)
        win.title(tr("update.title"))
        win.transient(self.root)
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._close)
        if self.style_window is not None:
            try:
                self.style_window(win)
            except Exception:
                logger.debug("Could not theme the update window", exc_info=True)

        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=tr("update.available", version=self.update.version), font=("", 12, "bold")).pack(
            anchor="w"
        )
        detail = tr("update.installed", version=_app.get("version", ""))
        if self.update.prerelease:
            detail += "  " + tr("update.prerelease_note")
        ttk.Label(body, text=detail, wraplength=460, justify="left").pack(anchor="w", pady=(2, 8))

        if self.update.notes:
            notes = tk.Text(body, width=64, height=10, wrap="word", relief="flat", borderwidth=0)
            notes.insert("1.0", self.update.notes[:NOTES_MAX_CHARS])
            notes.configure(state="disabled")
            notes.pack(fill="both", expand=True, pady=(0, 8))

        self.status = ttk.Label(body, text="", wraplength=460, justify="left")
        self.status.pack(anchor="w", fill="x")
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        self.install_btn = ttk.Button(buttons, text=tr("update.install"), command=self._install)
        if self.update.installable:
            self.install_btn.pack(side="left")
            self.status.configure(text=tr("update.install_hint"))
        self.page_btn = ttk.Button(buttons, text=tr("update.open_page"), command=self._open_page)
        self.page_btn.pack(side="left", padx=(0 if not self.update.installable else 8, 0))
        self.later_btn = ttk.Button(buttons, text=tr("update.later"), command=self._close)
        self.later_btn.pack(side="right")
        self.skip_btn = ttk.Button(buttons, text=tr("update.skip"), command=self._skip)
        self.skip_btn.pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------- actions

    def _open_page(self) -> None:
        webbrowser.open(self.update.page_url or updater.RELEASES_PAGE)

    def _skip(self) -> None:
        self.config.update({"gui_update_skip_version": self.update.version}, save=True)
        self._close()

    def _close(self) -> None:
        self._cancel.set()  # stops a download in progress
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    def _ui(self, callback) -> None:
        """Run on the Tk thread, unless the window is gone."""

        def run():
            if self.window is not None:
                callback()

        try:
            self.root.after(0, run)
        except (tk.TclError, RuntimeError):
            pass

    def _install(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._cancel.clear()
        self.install_btn.configure(state="disabled")
        self.skip_btn.configure(state="disabled")
        self.later_btn.configure(text=tr("update.cancel"))
        self.progress.pack(fill="x", pady=(6, 0), after=self.status)
        self.status.configure(text=tr("update.downloading", percent=0))
        last = [-1]

        def progress(done, total):
            percent = int(done * 100 / total) if total else 0
            if percent != last[0]:  # one UI update per percent, not per chunk
                last[0] = percent
                self._ui(lambda: self._show_progress(percent))

        def work():
            try:
                path = updater.download_installer(self.update, progress=progress, cancel=self._cancel)
            except updater.Cancelled:
                return
            except updater.UpdateError as e:
                logger.warning("Update download failed: %s", e)
                self._ui(self._failed)
                return
            self._ui(lambda: self._run_installer(path))

        threading.Thread(target=work, daemon=True, name="UpdateDownload").start()

    def _show_progress(self, percent: int) -> None:
        self.progress.configure(value=percent)
        self.status.configure(text=tr("update.downloading", percent=percent))

    def _failed(self) -> None:
        self._busy = False
        self.progress.pack_forget()
        self.status.configure(text=tr("update.download_failed"))
        self.install_btn.configure(state="normal")
        self.skip_btn.configure(state="normal")
        self.later_btn.configure(text=tr("update.later"))

    def _run_installer(self, path) -> None:
        self.status.configure(text=tr("update.installing"))
        try:
            updater.launch_installer(path)
        except OSError as e:  # e.g. the UAC prompt was declined
            logger.warning("Could not start the installer: %s", e)
            self._failed()
            return
        logger.info("Installer started for %s; closing the app.", self.update.version)
        self.quit_app()
