"""
------------------------------------------------------------------------------------------------------

                                               ,@@@@@@
                                            @@@@@@@@@@@            @@@
                                          @@@@@@@@@@@@      @@@@@@@@@@@
                                        @@@@@@@@@@@@@   @@@@@@@@@@@@@@
                                      @@@@@@@/         ,@@@@@@@@@@@@@
                                         /@@@@@@@@@@@@@@@  @@@@@@@@
                                    @@@@@@@@@@@@@@@@@@@@@@@@ @@@@@
                                @@@@@@@@                @@@@@
                              ,@@@                        @@@@&
                                             @@@@@@.       @@@@
                                   @@@     @@@@@@@@@/      @@@@@
                                   ,@@@.     @@@@@@((@     @@@@(
                                   //@@@        ,,  @@@@  @@@@@
                                   @@@(                @@@@@@@
                                   @@@  @          @@@@@@@@#
                                       @@@@@@@@@@@@@@@@@
                                      @@@@@@@@@@@@@(

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
------------------------------------------------------------------------------------------------------
"""

import logging
import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk
import sv_ttk
import queue
import cv2
import requests
import threading
from camera_widget import CameraWidget
from config import EyeTrackConfig
from eye import EyeId
from settings.VRCFTModuleSettings import VRCFTSettingsWidget
from settings.general_settings_widget import SettingsWidget
from settings.algo_settings_widget import AlgoSettingsWidget
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage
from utils.logging_utils import setup_logging
from utils.misc_utils import is_nt, is_macos, resource_path



APP_VERSION = "EyeTrackApp 0.3.0 BETA 1"
setup_logging(APP_VERSION)
logger = logging.getLogger(__name__)
winmm = None

if is_nt:
    from winotify import Notification
    from ctypes import windll, c_int

    try:
        winmm = windll.winmm
    except OSError:
        logger.warning("Failed to load winmm.dll")


# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
WINDOW_NAME = "EyeTrackApp"

_pywinstyles_mod = None


def apply_theme_to_titlebar(win: tk.Misc) -> None:
    """Match the Windows 10/11 caption bar to sv-ttk dark or light (requires pywinstyles on Windows)."""
    global _pywinstyles_mod
    if not is_nt:
        return
    if _pywinstyles_mod is False:
        return
    if _pywinstyles_mod is None:
        try:
            import pywinstyles as _pws

            _pywinstyles_mod = _pws
        except ImportError:
            _pywinstyles_mod = False
            logger.warning("pywinstyles not installed; title bar theme skipped.")
            return

    is_dark = sv_ttk.get_theme() == "dark"
    version = sys.getwindowsversion()

    if version.major == 10 and version.build >= 22000:
        header = "#1c1c1c" if is_dark else "#fafafa"
        _pywinstyles_mod.change_header_color(win, header)
    elif version.major == 10:
        _pywinstyles_mod.apply_style(win, "dark" if is_dark else "normal")
        win.wm_attributes("-alpha", 0.99)
        win.wm_attributes("-alpha", 1)


def set_timer_resolution(enabled):
    if winmm is not None:
        if enabled:
            rc = c_int(winmm.timeBeginPeriod(1))
            if rc.value != 0:
                # TIMEERR_NOCANDO = 97
                logger.warning("Failed to set timer resolution: %s", rc.value)
        else:
            winmm.timeEndPeriod(1)


def main():
    # Get Configuration
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    cancellation_event = threading.Event()
    # Ensure we always have a local reference, even if OpenVR autostart is disabled
    openvr_service = None

    # Start openvr service if autostart with openvr option is enabled
    # Allow the app to be closed when SteamVR closes
    if config.settings.gui_openvr_autostart and not is_macos:
        from OVR.OpenVRService import openvr_service as _openvr_service, OpenVRException

        try:
            _openvr_service.initialize()
        except OpenVRException:
            pass
        # keep a local reference only if import succeeded
        openvr_service = _openvr_service
        config.register_listener_callback(openvr_service.on_config_update)

    # Check to see if we can connect to our video source first. If not, bring up camera finding
    # dialog.
    try:
        if config.settings.gui_update_check:
            response = requests.get(
                "https://api.github.com/repos/EyeTrackVR/EyeTrackVR/releases/latest",
                timeout=(3, 10),
            )
            response.raise_for_status()
            latestversion = response.json()["name"]

            if (
                APP_VERSION == latestversion
            ):  # GitHub release name matches the local application version.
                logger.info("App is the latest version: %s", latestversion)
            else:
                logger.warning(
                    "You have app version %s installed. Please update to %s for the newest features.",
                    APP_VERSION,
                    latestversion,
                )
                try:
                    if is_nt:
                        # icon = cwd + "\Images\logo.ico"
                        icon = resource_path("Images/logo.ico")
                        toast = Notification(
                            app_id="EyeTrackApp",
                            title="New Update Available!",
                            msg=f"Please update to {latestversion}",
                            icon=r"{}".format(icon),
                        )
                        toast.add_actions(
                            label="Download Page",
                            launch="https://github.com/EyeTrackVR/EyeTrackVR/releases/latest",
                        )
                        toast.show()
                except Exception:
                    logger.info("Toast notifications not supported", exc_info=True)
    except (requests.RequestException, KeyError, ValueError):
        logger.info("Could not check for updates. Please try again later.", exc_info=True)

    osc_queue: queue.Queue[OSCMessage] = queue.Queue(maxsize=10)

    eyes = [
        CameraWidget(EyeId.RIGHT, config, osc_queue),
        CameraWidget(EyeId.LEFT, config, osc_queue),
    ]

    settings = [
        SettingsWidget(EyeId.SETTINGS, config),
        AlgoSettingsWidget(EyeId.ALGOSETTINGS, config),
        VRCFTSettingsWidget(EyeId.VRCFTMODULESETTINGS, config, osc_queue),
    ]

    osc_manager = OSCManager(
        osc_message_in_queue=osc_queue,
        config=config,
    )
    config.register_listener_callback(osc_manager.update)
    config.register_listener_callback(eyes[0].on_config_update)
    config.register_listener_callback(eyes[1].on_config_update)

    osc_manager.register_listeners(
        config.settings.gui_osc_recenter_address,
        [
            eyes[0].osc_recenter_eyes,
            eyes[1].osc_recenter_eyes,
        ],
    )
    osc_manager.register_listeners(
        config.settings.gui_osc_recalibrate_address,
        [
            eyes[0].osc_recalibrate_eyes,
            eyes[1].osc_recalibrate_eyes,
        ],
    )

    osc_manager.start()

    class AppUI:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title(APP_VERSION)
            try:
                self.root.iconbitmap(resource_path("Images/logo.ico"))
            except Exception:
                pass
            sv_ttk.set_theme("dark")
            apply_theme_to_titlebar(self.root)
            self.focus_paused = False
            self.current_page = "tracking"
            self.mode_var = tk.StringVar(value="etvr")
            self._last_camera_tracking_key = None
            self._timer_high_res = False
            self._nav_teardown_seq = 0

            nav = ttk.Frame(self.root)
            nav.pack(fill="x", padx=8, pady=(8, 4))
            self._nav_buttons = {}
            for page_id, label in (
                ("tracking", "Tracking"),
                ("settings", "Settings"),
                ("algo", "Algo Settings"),
                ("vrcft", "VRCFT Module Settings"),
            ):
                btn = ttk.Button(
                    nav, text=label, command=lambda p=page_id: self.show_page(p)
                )
                btn.pack(side="left", padx=4)
                self._nav_buttons[page_id] = btn

            self.content = ttk.Frame(self.root)
            self.content.pack(fill="both", expand=True, padx=8, pady=8)

            self.tracking_tab = ttk.Frame(self.content)
            self.settings_frame = settings[0].build(self.content)
            self.algo_frame = settings[1].build(self.content)
            self.vrcft_frame = settings[2].build(self.content)

            self.issues_frame = ttk.Frame(self.content)
            issues_wrap = 720
            _issues_hdr_font = ("Segoe UI", 14, "bold")
            _hdr_bg = self.root.cget("background")
            tk.Label(
                self.issues_frame,
                text="Having tracking issues?",
                font=_issues_hdr_font,
                bg=_hdr_bg,
                fg="#e8e8e8",
            ).pack(anchor="w", padx=12, pady=(12, 6))
            ttk.Label(
                self.issues_frame,
                text=(
                    "Please ensure your cameras are well lit, focused, rotated and cropped correctly. "
                    "Please ask in our discord for assistance if needed. We are here to help!"
                ),
                wraplength=issues_wrap,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 16))
            tk.Label(
                self.issues_frame,
                text="Improve your experience",
                font=_issues_hdr_font,
                bg=_hdr_bg,
                fg="#e8e8e8",
            ).pack(anchor="w", padx=12, pady=(0, 6))
            ttk.Label(
                self.issues_frame,
                text=(
                    "Please consider contributing data to our training to improve future models for much better "
                    "tracking and features. It only takes a few minutes. Every submission helps and we really want "
                    "data on setups that work poorly, as well as ones that work well. Thank you!"
                ),
                wraplength=issues_wrap,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 16))
            issues_btn_row = ttk.Frame(self.issues_frame)
            issues_btn_row.pack(anchor="w", padx=12, pady=8)

            def _open_data_submission():
                webbrowser.open(
                    "https://github.com/RedHawk989/ETVR-Data-Collection/releases/latest"
                )

            def _open_discord():
                webbrowser.open("https://discord.gg/kkXYbVykZX")

            ttk.Button(
                issues_btn_row,
                text="Data Submission App",
                command=_open_data_submission,
                style="Accent.TButton",
            ).pack(side="left", padx=(0, 8))
            ttk.Button(issues_btn_row, text="Discord", command=_open_discord).pack(
                side="left"
            )

            tracking_outer = ttk.Frame(self.tracking_tab, padding=4)
            tracking_outer.pack(fill="both", expand=True)
            tracking_sidebar = ttk.Frame(tracking_outer, width=220)
            tracking_sidebar.pack_propagate(False)
            tracking_sidebar.pack(side="left", fill="y", padx=(0, 8))
            tracking_main = ttk.Frame(tracking_outer)
            tracking_main.pack(side="left", fill="both", expand=True)

            setup_type = ttk.LabelFrame(tracking_sidebar, text="Setup Type", padding=8)
            setup_type.pack(fill="x", pady=(0, 8))
            ttk.Radiobutton(
                setup_type,
                text="ETVR Setup",
                variable=self.mode_var,
                value="etvr",
                command=self.on_mode_change,
            ).pack(anchor="w")
            ttk.Radiobutton(
                setup_type,
                text="Bigscreen Beyond",
                variable=self.mode_var,
                value="bigscreen",
                command=self.on_mode_change,
            ).pack(anchor="w")

            tracking_controls = ttk.LabelFrame(
                tracking_sidebar, text="Camera Settings", padding=8
            )
            tracking_controls.pack(fill="x", pady=(0, 8))
            left_initial = config.left_eye.capture_source
            right_initial = config.right_eye.capture_source
            self.left_camera_var = tk.StringVar(
                value="" if left_initial is None or left_initial == "" else str(left_initial)
            )
            self.right_camera_var = tk.StringVar(
                value="" if right_initial is None or right_initial == "" else str(right_initial)
            )
            self.left_camera_label = ttk.Label(
                tracking_controls, text="Left (UVC / COM port / URL):"
            )
            self.left_camera_label.pack(anchor="w")
            ttk.Entry(tracking_controls, textvariable=self.left_camera_var).pack(
                fill="x", pady=(2, 8)
            )
            self.right_camera_label = ttk.Label(
                tracking_controls, text="Right (UVC / COM port / URL):"
            )
            self.right_camera_entry = ttk.Entry(
                tracking_controls, textvariable=self.right_camera_var
            )
            self.right_camera_label.pack(anchor="w")
            self.right_camera_entry.pack(fill="x", pady=(2, 8))
            camera_button_row = ttk.Frame(tracking_controls)
            camera_button_row.pack(fill="x")
            ttk.Button(
                camera_button_row, text="Scan", width=8, command=self.scan_sources
            ).pack(side="left", padx=(0, 4))
            ttk.Button(
                camera_button_row,
                text="Connect",
                command=self.apply_camera_inputs,
                style="Accent.TButton",
            ).pack(side="left", fill="x", expand=True)

            status_group = ttk.LabelFrame(tracking_sidebar, text="Status", padding=8)
            status_group.pack(fill="both", expand=True)
            self.mode_label_var = tk.StringVar(value="")
            self.status_var = tk.StringVar(value="Ready.")
            ttk.Label(
                status_group,
                textvariable=self.status_var,
                wraplength=190,
                justify="left",
                anchor="w",
            ).pack(anchor="w", fill="x")
            ttk.Label(
                status_group,
                textvariable=self.mode_label_var,
                wraplength=190,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))

            self.tracking_eyes_row = ttk.Frame(tracking_main)
            self.tracking_eyes_row.pack(fill="both", expand=True)
            self.left_frame = eyes[1].build(
                self.tracking_eyes_row, show_camera_controls=False
            )
            self.right_frame = eyes[0].build(
                self.tracking_eyes_row, show_camera_controls=False
            )
            # Hug the natural widget width (tracking image is 300 px + small paddings) and
            # pool any slack on the right of the row. Expanding here stretched each panel
            # to half of tracking_main, leaving a wide empty gutter after the status row.
            self.left_frame.pack(side="left", fill="y", padx=(0, 4))
            self.right_frame.pack(side="left", fill="y", padx=(4, 0))

            bottom = ttk.Frame(self.root)
            bottom.pack(fill="x", padx=8, pady=4)
            ttk.Button(bottom, text="GUI OFF", command=self.gui_off).pack(side="left")
            ttk.Button(
                bottom, text="Having Issues?", command=lambda: self.show_page("issues")
            ).pack(side="left", padx=(10, 0))
            self.focus_label = ttk.Label(bottom, text="- - -  Interface Paused  - - -")
            self.focus_label.pack(side="left", padx=12)
            self.focus_label.pack_forget()

            self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
            self.on_mode_change()
            self.show_page("tracking")
            self._apply_initial_window_geometry()
            self._tick()

        def _sync_nav_buttons(self):
            """Highlight the current page with Sun Valley accent (blue) vs default TButton."""
            for page_id, btn in self._nav_buttons.items():
                btn.configure(
                    style="Accent.TButton"
                    if page_id == self.current_page
                    else "TButton"
                )

        def _apply_initial_window_geometry(self):
            # Tracking tab packs two full camera panels; still set a floor so the window opens usable.
            self.root.update_idletasks()
            min_w, min_h = 920, 660
            w = max(self.root.winfo_reqwidth(), min_w)
            h = max(self.root.winfo_reqheight(), min_h)
            self.root.geometry(f"{w}x{h}")

        def set_openvr_autostart(self, value):
            for module in settings[0].initialized_modules:
                if hasattr(module, "gui_openvr_autostart"):
                    module.tk_vars[getattr(module, "gui_openvr_autostart")].set(
                        bool(value)
                    )

        def _normalize_camera_input(self, raw_value: str):
            value = (raw_value or "").strip()
            if value == "":
                return None
            try:
                return int(value)
            except ValueError:
                lower_value = value.lower()
                if (
                    len(value) > 5
                    and "://" not in value
                    and not value.startswith(("COM", "/dev"))
                    and not lower_value.endswith((".mp4", ".avi", ".mkv", ".mov"))
                ):
                    return f"http://{value}/"
                return value

        def on_mode_change(self):
            is_bigscreen = self.mode_var.get() == "bigscreen"
            if is_bigscreen:
                self.right_camera_entry.state(["disabled"])
                self.left_camera_label.configure(text="Source (UVC Index):")
                self.right_camera_label.configure(text="Right (same source):")
            else:
                self.right_camera_entry.state(["!disabled"])
                self.left_camera_label.configure(text="Left (UVC / COM port / URL):")
                self.right_camera_label.configure(text="Right (UVC / COM port / URL):")

        def scan_sources(self):
            self.status_var.set("Scanning camera indices...")

            def _scan():
                found = []
                for i in range(10):
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        found.append(i)
                    cap.release()
                listing = ", ".join(str(i) for i in found) if found else "none"
                self.root.after(
                    0,
                    lambda: self.status_var.set(f"Available camera indices: {listing}"),
                )

            threading.Thread(target=_scan, daemon=True).start()

        def _camera_tracking_state_key(self, left_source, right_source):
            # Use explicit None checks — UVC index 0 is a valid source but is falsy in Python,
            # so `not left_source` would mis-classify it as "no source" and skip starting trackers.
            has_left = left_source is not None and left_source != ""
            has_right = right_source is not None and right_source != ""
            if not has_left and not has_right:
                return ("none",)
            if has_left and not has_right:
                return ("left", left_source)
            if has_right and not has_left:
                return ("right", right_source)
            return ("dual", left_source, right_source, left_source == right_source)

        def _sync_timer_resolution(self):
            active = any(e.started() for e in eyes)
            if active:
                if not self._timer_high_res:
                    set_timer_resolution(True)
                    self._timer_high_res = True
            else:
                if self._timer_high_res:
                    set_timer_resolution(False)
                    self._timer_high_res = False

        def apply_camera_inputs(self):
            left_source = self._normalize_camera_input(self.left_camera_var.get())
            if self.mode_var.get() == "bigscreen":
                right_source = left_source
                self.right_camera_var.set(
                    "" if left_source is None else str(left_source)
                )
            else:
                right_source = self._normalize_camera_input(self.right_camera_var.get())
            config.left_eye.capture_source = left_source
            config.right_eye.capture_source = right_source

            new_key = self._camera_tracking_state_key(left_source, right_source)
            if new_key != self._last_camera_tracking_key:
                eyes[1].stop()
                eyes[0].stop()
                self._last_camera_tracking_key = new_key

            # UVC index 0 is falsy but valid; check for explicit "set" rather than truthiness.
            has_left = left_source is not None and left_source != ""
            has_right = right_source is not None and right_source != ""

            if has_left and has_right:
                shared = left_source == right_source
                already_running = eyes[0].started() and eyes[1].started()
                if not already_running:
                    eyes[0].camera.set_extra_output_queues([])
                    eyes[1].detach_shared_capture_event()
                    if shared:
                        eyes[0].camera.set_extra_output_queues([eyes[1].capture_queue])
                        eyes[1].capture_event = eyes[0].capture_event
                        eyes[1].ransac.capture_event = eyes[0].capture_event
                        eyes[1].uses_shared_capture_event = True
                        eyes[0].start()
                        eyes[1].start(run_camera_thread=False)
                    else:
                        eyes[0].start()
                        eyes[1].start()
                config.settings.tracker_single_eye = 0
                config.eye_display_id = EyeId.BOTH
                self.mode_label_var.set("Mode: Dual-eye tracking")
                self.status_var.set("Tracking both eyes.")
            elif has_left:
                if not eyes[1].started():
                    eyes[0].camera.set_extra_output_queues([])
                    eyes[1].detach_shared_capture_event()
                    eyes[0].stop()
                    eyes[1].start()
                config.settings.tracker_single_eye = 1
                config.eye_display_id = EyeId.LEFT
                self.mode_label_var.set("Mode: Single-eye (left)")
                self.status_var.set("Tracking left eye only.")
            elif has_right:
                if not eyes[0].started():
                    eyes[0].camera.set_extra_output_queues([])
                    eyes[1].detach_shared_capture_event()
                    eyes[1].stop()
                    eyes[0].start()
                config.settings.tracker_single_eye = 2
                config.eye_display_id = EyeId.RIGHT
                self.mode_label_var.set("Mode: Single-eye (right)")
                self.status_var.set("Tracking right eye only.")
            else:
                eyes[0].stop()
                eyes[1].stop()
                config.settings.tracker_single_eye = 0
                config.eye_display_id = EyeId.BOTH
                self.mode_label_var.set("Mode: No active camera")
                self.status_var.set("Enter at least one camera source.")

            config.save()
            self._sync_timer_resolution()

        def show_page(self, page_name: str):
            """Switch tabs. Heavy work (camera thread joins, config apply) is deferred so the UI can redraw first."""
            self._nav_teardown_seq += 1
            seq = self._nav_teardown_seq
            self.current_page = page_name
            for frame in [
                self.tracking_tab,
                self.settings_frame,
                self.algo_frame,
                self.vrcft_frame,
                self.issues_frame,
            ]:
                frame.pack_forget()

            if page_name == "tracking":
                self.tracking_tab.pack(fill="both", expand=True)
                self._sync_nav_buttons()
                self.root.update_idletasks()
                self.root.after(0, lambda s=seq: self._deferred_enter_tracking(s))
            elif page_name == "settings":
                self.settings_frame.pack(fill="both", expand=True)
                self._sync_nav_buttons()
                self.root.update_idletasks()
                self.root.after(0, lambda s=seq: self._deferred_enter_settings(s))
            elif page_name == "algo":
                self.algo_frame.pack(fill="both", expand=True)
                self._sync_nav_buttons()
                self.root.update_idletasks()
                self.root.after(0, lambda s=seq: self._deferred_enter_algo(s))
            elif page_name == "vrcft":
                self.vrcft_frame.pack(fill="both", expand=True)
                self._sync_nav_buttons()
                self.root.update_idletasks()
                self.root.after(0, lambda s=seq: self._deferred_enter_vrcft(s))
            elif page_name == "issues":
                self.issues_frame.pack(fill="both", expand=True)
                self._sync_nav_buttons()
                self.root.update_idletasks()
                self.root.after(0, lambda s=seq: self._deferred_enter_issues(s))

        def _deferred_enter_tracking(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            settings[0].stop()
            settings[1].stop()
            settings[2].stop()
            self.apply_camera_inputs()
            self._sync_timer_resolution()

        def _deferred_enter_settings(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            eyes[0].stop()
            eyes[1].stop()
            settings[1].stop()
            settings[2].stop()
            settings[0].start()
            self._sync_timer_resolution()

        def _deferred_enter_algo(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            eyes[0].stop()
            eyes[1].stop()
            settings[0].stop()
            settings[2].stop()
            settings[1].start()
            self._sync_timer_resolution()

        def _deferred_enter_vrcft(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            eyes[0].stop()
            eyes[1].stop()
            settings[0].stop()
            settings[1].stop()
            settings[2].start()
            self._sync_timer_resolution()

        def _deferred_enter_issues(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            eyes[0].stop()
            eyes[1].stop()
            settings[0].stop()
            settings[1].stop()
            settings[2].stop()
            self._sync_timer_resolution()

        def gui_off(self):
            config.settings.gui_disable_gui = True
            settings[0].stop()
            settings[1].stop()
            settings[2].stop()
            config.save()
            self.root.withdraw()
            dialog = tk.Toplevel()
            dialog.title("ETVR")
            apply_theme_to_titlebar(dialog)
            ttk.Label(dialog, text="GUI Disabled!").pack(padx=12, pady=8)

            def enable_gui():
                config.settings.gui_disable_gui = False
                config.save()
                logger.info("GUI enabled")
                dialog.destroy()
                self.root.deiconify()

            ttk.Button(dialog, text="Enable GUI", command=enable_gui).pack(
                padx=12, pady=(0, 8)
            )
            dialog.protocol("WM_DELETE_WINDOW", enable_gui)

        def _tick(self):
            has_focus = self.root.focus_displayof() is not None
            interval = 33
            if has_focus:
                if self.focus_paused:
                    self.focus_paused = False
                    self.focus_label.pack_forget()
                if self.current_page == "tracking":
                    for eye in eyes:
                        if eye.started():
                            eye.render_tick()
                for setting in settings:
                    if setting.started():
                        setting.render_tick()
            else:
                if not self.focus_paused:
                    self.focus_paused = True
                    self.focus_label.pack(side="left", padx=12)
                interval = 100

            self.root.after(interval, self._tick)

        def shutdown(self):
            logger.info("Exiting EyeTrackApp")
            for eye in eyes:
                eye.stop()
            cancellation_event.set()
            osc_manager.shutdown()
            if getattr(self, "_timer_high_res", False):
                set_timer_resolution(False)
            self.root.destroy()
            os._exit(0)

    app = AppUI()
    if (not is_macos) and (openvr_service is not None):
        openvr_service.window = app
    app.root.mainloop()


if __name__ == "__main__":
    main()
