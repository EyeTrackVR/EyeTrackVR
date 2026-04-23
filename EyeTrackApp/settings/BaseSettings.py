from datetime import datetime, timedelta
from typing import Iterable

import tkinter as tk
from tkinter import ttk
from colorama import Fore
from threading import Event
from eye import EyeId
from config import EyeTrackConfig, EyeTrackSettingsConfig

class BaseSettingsWidget:
    def __init__(self, widget_id: EyeId, main_config: EyeTrackConfig, settings_modules: Iterable):
        self.widget_id = widget_id
        self.main_config = main_config
        self.config = main_config.settings
        self.last_error_printout = datetime.now() - timedelta(seconds=20)
        self.error_printout_timeout = 2
        self.reset_button_key = f"RESET_SETTINGS{widget_id}"
        self.is_saving = False
        self.initialized_modules = self._initialize_modules(settings_modules=settings_modules, widget_id=widget_id)
        self.cancellation_event = Event()
        self.cancellation_event.set()
        self.frame = None

    def started(self):
        return not self.cancellation_event.is_set()

    def start(self):
        if not self.cancellation_event.is_set():
            return
        self.cancellation_event.clear()

    def stop(self):
        if self.cancellation_event.is_set():
            return
        self.cancellation_event.set()

    def _update_and_save_config(self, validated_data: dict):
        self.main_config.update(validated_data, save=True)
        self.is_saving = False

    def _handle_errors(self, errors):
        now = datetime.now()
        elapsed_seconds = (datetime.now() - self.last_error_printout).seconds
        if elapsed_seconds > self.error_printout_timeout:
            self.last_error_printout = now
            messages = [f"{Fore.RED}[ERROR]{Fore.RESET} {error['msg']} \n" for module_errors in errors for error in module_errors]
            print("".join(messages))

    def _collect_values(self):
        values = {}
        for module in self.initialized_modules:
            values.update(module.get_values_map())
        return values

    def render_tick(self):
        values = self._collect_values()
        validated_data, errors = {}, []
        for module in self.initialized_modules:
            module_validated_data = module.validate(values)
            if module_validated_data.changes:
                validated_data.update(module_validated_data.changes)
            if module_validated_data.errors:
                errors.append(module_validated_data.errors)
        if not errors and validated_data and not self.is_saving:
            self.is_saving = True
            self._update_and_save_config(validated_data)
        if errors:
            self._handle_errors(errors)

    def _initialize_modules(self, settings_modules, widget_id):
        return [module(config=self.config, settings=self.main_config, widget_id=widget_id) for module in settings_modules]

    def build(self, parent) -> ttk.Frame:
        self.frame = ttk.Frame(parent)
        for module in self.initialized_modules:
            section = ttk.LabelFrame(self.frame, text=module.__class__.__name__.replace("Module", ""))
            section.pack(fill="x", padx=8, pady=6, anchor="n")
            module.build(section)

        tk.Button(
            self.frame,
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
        ).pack(anchor="w", padx=10, pady=(6, 10))
        return self.frame

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
        self._update_and_save_config(default_values)