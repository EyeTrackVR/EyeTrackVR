from datetime import datetime, timedelta
import os
import sys
import time
from typing import Iterable

import tkinter as tk
from tkinter import messagebox, ttk
from colorama import Fore
from threading import Event
from eye import EyeId
from config import (
    BACKUP_CONFIG_FILE_NAME,
    CONFIG_FILE_NAME,
    EyeTrackConfig,
    EyeTrackSettingsConfig,
)
from utils.logging_utils import open_logs


class BaseSettingsWidget:
    _SHOW_ADVANCED_TEXT = "Show Advanced  ▾"  # ▾
    _HIDE_ADVANCED_TEXT = "Hide Advanced  ▴"  # ▴

    def __init__(
        self, widget_id: EyeId, main_config: EyeTrackConfig, settings_modules: Iterable
    ):
        self.widget_id = widget_id
        self.main_config = main_config
        self.config = main_config.settings
        self.last_error_printout = datetime.now() - timedelta(seconds=20)
        self.error_printout_timeout = 2
        self.reset_button_key = f"RESET_SETTINGS{widget_id}"
        self.is_saving = False
        self.initialized_modules = self._initialize_modules(
            settings_modules=settings_modules, widget_id=widget_id
        )
        self.cancellation_event = Event()
        self.cancellation_event.set()
        self.frame = None
        self._settings_render_interval_s = 0.2
        self._last_settings_render_mono = 0.0
        self._pending_validated: dict | None = None
        self._config_save_after_id = None
        self._advanced_visible = False
        self._advanced_section = None
        self._advanced_toggle_row = None
        self._advanced_toggle_btn = None

    def started(self):
        return not self.cancellation_event.is_set()

    def start(self):
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()

    def flush_pending_save(self) -> None:
        """Cancel debounce timer, merge pending edits with current UI, and save immediately.
        Call when leaving a settings tab so changes are not lost to throttling or after()."""
        if self._config_save_after_id is not None and self.frame is not None:
            try:
                self.frame.winfo_toplevel().after_cancel(self._config_save_after_id)
            except tk.TclError:
                pass
        self._config_save_after_id = None

        if self.frame is None:
            self._pending_validated = None
            return

        values = self._collect_values()
        validated_data: dict = {}
        errors = []
        for module in self.initialized_modules:
            module_validated_data = module.validate(values)
            if module_validated_data.changes:
                validated_data.update(module_validated_data.changes)
            if module_validated_data.errors:
                errors.append(module_validated_data.errors)

        merged = {**(self._pending_validated or {}), **validated_data}
        self._pending_validated = None

        if errors:
            self._handle_errors(errors)
            return
        if merged:
            self.is_saving = True
            self._update_and_save_config(merged)

    def stop(self):
        if self.cancellation_event.is_set():
            return
        self.flush_pending_save()
        self.cancellation_event.set()

    def _update_and_save_config(self, validated_data: dict):
        self.main_config.update(validated_data, save=True)
        self.is_saving = False

    def _cancel_debounced_settings_save(self):
        if self._config_save_after_id is not None and self.frame is not None:
            try:
                self.frame.winfo_toplevel().after_cancel(self._config_save_after_id)
            except tk.TclError:
                pass
        self._config_save_after_id = None
        self._pending_validated = None

    def _schedule_debounced_settings_save(self, validated_data: dict):
        self._pending_validated = {**(self._pending_validated or {}), **validated_data}
        if self.frame is None:
            return
        top = self.frame.winfo_toplevel()
        if self._config_save_after_id is not None:
            top.after_cancel(self._config_save_after_id)

        def _flush():
            self._config_save_after_id = None
            pending = self._pending_validated
            self._pending_validated = None
            if pending:
                self.is_saving = True
                self._update_and_save_config(pending)

        self._config_save_after_id = top.after(450, _flush)

    def _handle_errors(self, errors):
        now = datetime.now()
        elapsed_seconds = (datetime.now() - self.last_error_printout).seconds
        if elapsed_seconds > self.error_printout_timeout:
            self.last_error_printout = now
            messages = [
                f"{Fore.RED}[ERROR]{Fore.RESET} {error['msg']} \n"
                for module_errors in errors
                for error in module_errors
            ]
            print("".join(messages))

    def _collect_values(self):
        values = {}
        for module in self.initialized_modules:
            values.update(module.get_values_map())
        return values

    def render_tick(self):
        now = time.monotonic()
        if now - self._last_settings_render_mono < self._settings_render_interval_s:
            return
        self._last_settings_render_mono = now

        values = self._collect_values()
        validated_data, errors = {}, []
        for module in self.initialized_modules:
            module_validated_data = module.validate(values)
            if module_validated_data.changes:
                validated_data.update(module_validated_data.changes)
            if module_validated_data.errors:
                errors.append(module_validated_data.errors)
        if errors:
            self._cancel_debounced_settings_save()
            self._handle_errors(errors)
        elif validated_data:
            self._schedule_debounced_settings_save(validated_data)

    def _initialize_modules(self, settings_modules, widget_id):
        return [
            module(config=self.config, settings=self.main_config, widget_id=widget_id)
            for module in settings_modules
        ]

    def build(self, parent) -> ttk.Frame:
        self.frame = ttk.Frame(parent)
        self._build_module_sections()
        # Reset/Delete buttons live in the persistent bottom row (see eyetrackapp.AppUI).
        return self.frame

    def advanced_module_types(self) -> tuple:
        """Module classes returned here are hidden behind the Advanced toggle."""
        return ()

    def _build_module_sections(self):
        advanced_types = tuple(self.advanced_module_types())
        advanced_modules = []
        for module in self.initialized_modules:
            if advanced_types and isinstance(module, advanced_types):
                advanced_modules.append(module)
                continue
            self._build_module_section(module)
        if advanced_modules:
            self._build_advanced_section(advanced_modules)

    def _build_module_section(self, module, title=None):
        section = ttk.LabelFrame(
            self.frame,
            text=title or module.__class__.__name__.replace("Module", ""),
        )
        section.pack(fill="x", padx=8, pady=6, anchor="n")
        module.build(section)
        return section

    def _build_advanced_section(self, advanced_modules):
        self._advanced_toggle_row = ttk.Frame(self.frame)
        self._advanced_toggle_row.pack(fill="x", padx=8, pady=(2, 0))
        self._advanced_toggle_btn = ttk.Button(
            self._advanced_toggle_row,
            text=self._SHOW_ADVANCED_TEXT,
            command=self._toggle_advanced,
        )
        self._advanced_toggle_btn.pack(side="left")

        # Build eagerly so tk_vars exist for validation/save while hidden.
        # Each contributor gets its own Frame to isolate grid placements.
        self._advanced_section = ttk.LabelFrame(self.frame, text="Advanced")
        advanced_set = set(id(m) for m in advanced_modules)
        for module in self.initialized_modules:
            if id(module) in advanced_set:
                continue
            if hasattr(module, "build_advanced"):
                sub = ttk.Frame(self._advanced_section)
                sub.pack(fill="x", padx=2, pady=2, anchor="n")
                module.build_advanced(sub)
        for module in advanced_modules:
            sub = ttk.Frame(self._advanced_section)
            sub.pack(fill="x", padx=2, pady=2, anchor="n")
            module.build(sub)

        diagnostics_row = ttk.Frame(self._advanced_section)
        diagnostics_row.pack(fill="x", padx=8, pady=(6, 4), anchor="w")
        ttk.Button(
            diagnostics_row, text="Open Logs", command=open_logs
        ).pack(side="left")

        self._advanced_visible = False

    def _toggle_advanced(self):
        if self._advanced_section is None or self._advanced_toggle_btn is None:
            return
        if self._advanced_visible:
            self._advanced_section.pack_forget()
            self._advanced_toggle_btn.config(text=self._SHOW_ADVANCED_TEXT)
        else:
            self._advanced_section.pack(
                fill="x",
                padx=8,
                pady=6,
                anchor="n",
                after=self._advanced_toggle_row,
            )
            self._advanced_toggle_btn.config(text=self._HIDE_ADVANCED_TEXT)
        self._advanced_visible = not self._advanced_visible

    def _build_action_buttons(self):
        button_row = ttk.Frame(self.frame)
        button_row.pack(fill="x", padx=10, pady=(6, 10))
        tk.Button(
            button_row,
            text="Reset settings to default",
            command=self.reset_config,
            font=("Segoe UI", 9),
            fg="#000000",
            bg="#d9a3a3",
            activebackground="#c99393",
            activeforeground="#000000",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            border=0,
            highlightthickness=0,
        ).pack(side="left")
        tk.Button(
            button_row,
            text="Delete config",
            command=self.delete_config,
            font=("Segoe UI", 9),
            fg="#ffffff",
            bg="#a33a3a",
            activebackground="#8a2a2a",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            border=0,
            highlightthickness=0,
        ).pack(side="left", padx=(8, 0))
        return button_row

    def delete_config(self):
        """Wipe the on-disk config (main + backup) and exit. Next launch will
        start from defaults. We exit rather than re-init the in-memory config
        because the running app holds references to the existing settings
        objects in every module, so a hot-swap would leave stale state
        scattered across the process."""
        parent = self.frame.winfo_toplevel() if self.frame is not None else None
        confirmed = messagebox.askyesno(
            "Delete config",
            "Delete the config file and quit?\n\n"
            "All saved settings, calibrations, and camera sources will be lost. "
            "The app will close; relaunch it to start fresh.",
            parent=parent,
            icon="warning",
        )
        if not confirmed:
            return

        # Cancel any pending debounced save so we don't race a write against
        # the delete we're about to do.
        self._cancel_debounced_settings_save()
        self.is_saving = True

        removed = []
        for path in (CONFIG_FILE_NAME, BACKUP_CONFIG_FILE_NAME):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    removed.append(path)
            except OSError as e:
                print(f"{Fore.RED}[ERROR]{Fore.RESET} Could not delete {path}: {e}")
        print(
            f"{Fore.GREEN}[INFO]{Fore.RESET} Deleted config file(s): "
            f"{', '.join(removed) if removed else 'none found'}"
        )

        # Hand off to the main window's shutdown sequence so camera threads,
        # OSC, etc. unwind cleanly. The root's WM_DELETE_WINDOW protocol is
        # bound to AppUI.shutdown() which stops eye threads, the OSC server,
        # and calls os._exit(0) — sys.exit() would hang here because those
        # threads are non-daemon.
        if parent is not None:
            try:
                shutdown_cb = parent.protocol("WM_DELETE_WINDOW")
                if shutdown_cb:
                    parent.tk.call(shutdown_cb)
                    return
                parent.destroy()
            except tk.TclError:
                pass
        os._exit(0)

    def reset_config(self):
        default_values = {}
        base_settings = EyeTrackSettingsConfig()
        print(f"\033[92m[INFO] Resetting config to defaults\033[0m")
        for module in self.initialized_modules:
            for key in module.get_key_for_panel_defaults():
                default_val = getattr(base_settings, key)
                widget_key = getattr(module, key)
                default_values[key] = default_val
                if widget_key in module.tk_vars:
                    module.tk_vars[widget_key].set(default_val)
        print(f"\033[92m[INFO] Config reset, saving\033[0m")
        self._cancel_debounced_settings_save()
        self.is_saving = True
        self._update_and_save_config(default_values)
