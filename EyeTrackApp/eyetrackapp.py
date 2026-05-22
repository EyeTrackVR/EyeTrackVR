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
import time
import webbrowser
import tkinter as tk
from tkinter import ttk
import sv_ttk
import queue
import cv2
import requests
import threading
from camera_widget import CameraWidget
from camera_enum import (
    discover_etvr_mdns_sources,
    format_uvc_named_source,
    list_uvc_cameras,
)
from config import EyeTrackConfig
from eye import EyeId
from settings.VRCFTModuleSettings import VRCFTSettingsWidget
from settings.general_settings_widget import SettingsWidget
from settings.algo_settings_widget import AlgoSettingsWidget
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage
from utils.logging_utils import setup_logging
from utils.misc_utils import is_nt, is_macos, resource_path



APP_VERSION = "EyeTrackApp 0.3.0 BETA 3"
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
            initial_mode = getattr(config.settings, "gui_setup_mode", "etvr") or "etvr"
            if initial_mode not in ("etvr", "bigscreen"):
                initial_mode = "etvr"
            self.mode_var = tk.StringVar(value=initial_mode)
            self._last_camera_tracking_key = None
            self._timer_high_res = False
            self._nav_teardown_seq = 0
            # Maps the friendly display label shown in the camera dropdown to
            # the actual capture_source string we store/resolve (e.g.
            # ``"OBS Virtual Camera"`` → ``"uvc:OBS Virtual Camera@\\?\..."``).
            # Populated by scan_sources; consulted by _normalize_camera_input.
            self._source_display_map: dict[str, str] = {}

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
            # Combobox (not Entry) so Scan can populate a dropdown of detected
            # UVC cameras while still letting the user type a COM port / URL /
            # index by hand. Picked dropdown entries are written as
            # ``uvc:<name>@<address>`` strings, which the capture thread
            # re-resolves to a live cv2 index every loop.
            self.left_camera_entry = ttk.Combobox(
                tracking_controls, textvariable=self.left_camera_var, values=()
            )
            self.left_camera_entry.pack(fill="x", pady=(2, 8))
            self.right_camera_label = ttk.Label(
                tracking_controls, text="Right (UVC / COM port / URL):"
            )
            self.right_camera_entry = ttk.Combobox(
                tracking_controls, textvariable=self.right_camera_var, values=()
            )
            self.right_camera_label.pack(anchor="w")
            self.right_camera_entry.pack(fill="x", pady=(2, 8))
            # Picking a value from the dropdown auto-connects (matches what
            # users expect after running Scan). Typed input intentionally does
            # NOT auto-connect — that's what the Connect button is for, and
            # firing on every keystroke would thrash the capture thread.
            # <<ComboboxSelected>> only fires on dropdown selection, not edits.
            self.left_camera_entry.bind(
                "<<ComboboxSelected>>", lambda _e: self.apply_camera_inputs()
            )
            self.right_camera_entry.bind(
                "<<ComboboxSelected>>", lambda _e: self.apply_camera_inputs()
            )
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

            # Global mode toggle — flips both eyes between Tracking and
            # Cropping at once. Per-eye buttons used to live inside each
            # camera widget; users always wanted them paired.
            mode_row = ttk.Frame(tracking_main)
            mode_row.pack(fill="x", pady=(0, 4))
            mode_inner = ttk.Frame(mode_row)
            mode_inner.pack(anchor="center")
            self._global_tracking_btn = ttk.Button(
                mode_inner,
                text="Tracking Mode",
                command=self._on_global_tracking_mode,
            )
            self._global_tracking_btn.pack(side="left", padx=4)
            self._global_roi_btn = ttk.Button(
                mode_inner,
                text="Cropping Mode",
                command=self._on_global_roi_mode,
            )
            self._global_roi_btn.pack(side="left", padx=4)
            self._sync_global_mode_buttons()

            self.tracking_eyes_row = ttk.Frame(tracking_main)
            # fill="x" only (not "both", no expand): lets the action row below
            # sit snug against the visualization instead of being pushed to the
            # bottom of tracking_main by an expanding eyes row.
            self.tracking_eyes_row.pack(fill="x")
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

            # Global calibration / recenter row. Replaces the per-eye buttons
            # that used to live in each camera widget — left/right always need
            # to calibrate together, and two pairs of buttons made it ambiguous
            # which eye's state was being toggled.
            # fill="x" on the outer frame so the inner button group can center
            # within the full tracking_main width. Tight top padding keeps the
            # buttons close to the visualization above.
            tracking_actions = ttk.Frame(tracking_main)
            tracking_actions.pack(fill="x", pady=(2, 0))
            actions_inner = ttk.Frame(tracking_actions)
            actions_inner.pack(anchor="center")
            self._calibration_btn_text = tk.StringVar(value="Start Calibration")
            self._global_calibration_btn = ttk.Button(
                actions_inner,
                textvariable=self._calibration_btn_text,
                command=self._on_global_calibration_toggle,
            )
            self._global_calibration_btn.pack(side="left", padx=(0, 4))
            ttk.Button(
                actions_inner,
                text="Recenter Eyes",
                command=self._on_global_recenter,
            ).pack(side="left", padx=4)

            bottom = ttk.Frame(self.root)
            bottom.pack(fill="x", padx=8, pady=4)
            ttk.Button(bottom, text="GUI OFF", command=self.gui_off).pack(side="left")
            ttk.Button(
                bottom, text="Having Issues?", command=lambda: self.show_page("issues")
            ).pack(side="left", padx=(10, 0))
            self.focus_label = ttk.Label(bottom, text="- - -  Interface Paused  - - -")
            self.focus_label.pack(side="left", padx=12)
            self.focus_label.pack_forget()

            # Settings-only action buttons. Hosted in the same persistent
            # bottom row as GUI OFF / Having Issues but right-aligned and only
            # shown while a settings page is active (toggled in show_page).
            self._settings_actions_row = ttk.Frame(bottom)
            tk.Button(
                self._settings_actions_row,
                text="Delete config",
                command=self._active_settings_delete_config,
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
            ).pack(side="right", padx=(8, 0))
            tk.Button(
                self._settings_actions_row,
                text="Reset settings to default",
                command=self._active_settings_reset_config,
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
            ).pack(side="right")

            self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
            self.on_mode_change()
            self.show_page("tracking")
            self._apply_initial_window_geometry()
            self._tick()

        def _active_settings_widget(self):
            """Return the settings widget that owns the currently visible page,
            or None if the current page is not a settings page."""
            return {
                "settings": settings[0],
                "algo": settings[1],
                "vrcft": settings[2],
            }.get(self.current_page)

        def _active_settings_reset_config(self):
            widget = self._active_settings_widget()
            if widget is not None:
                widget.reset_config()

        def _active_settings_delete_config(self):
            widget = self._active_settings_widget()
            if widget is not None:
                widget.delete_config()

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
            # If the user picked (or typed) one of the friendly labels from
            # the scan dropdown, translate it back to the encoded
            # uvc:<name>@<address> capture-source string before any further
            # parsing — otherwise it'd fall through to the "looks like a URL?"
            # branch below and get http://-prefixed.
            mapped = self._source_display_map.get(value)
            if mapped is not None:
                value = mapped
            try:
                return int(value)
            except ValueError:
                lower_value = value.lower()
                if (
                    len(value) > 5
                    and "://" not in value
                    and not value.startswith(("COM", "/dev", "uvc:"))
                    and not lower_value.endswith((".mp4", ".avi", ".mkv", ".mov"))
                ):
                    return f"http://{value}/"
                return value

        def on_mode_change(self):
            mode = self.mode_var.get()
            is_bigscreen = mode == "bigscreen"
            if is_bigscreen:
                self.right_camera_entry.state(["disabled"])
                self.left_camera_label.configure(text="Source (UVC Index):")
                self.right_camera_label.configure(text="Right (same source):")
            else:
                self.right_camera_entry.state(["!disabled"])
                self.left_camera_label.configure(text="Left (UVC / COM port / URL):")
                self.right_camera_label.configure(text="Right (UVC / COM port / URL):")
            # Persist so the next launch reopens in the same mode rather than
            # falling back to ETVR (which then reuses the BSB-era right_eye
            # source — the same camera as the left).
            if getattr(config.settings, "gui_setup_mode", None) != mode:
                config.settings.gui_setup_mode = mode
                config.save()

        def scan_sources(self):
            self.status_var.set("Scanning UVC cameras and mDNS...")

            def _scan():
                cams = list_uvc_cameras()
                # Build friendly labels for the dropdown — just the camera
                # name, with a "(N)" suffix when two cameras share a name so
                # the user can still tell them apart. The encoded
                # uvc:<name>@<address> form stays internal; we map it back
                # from the label in _normalize_camera_input.
                name_totals: dict[str, int] = {}
                for c in cams:
                    name_totals[c["name"]] = name_totals.get(c["name"], 0) + 1
                seen: dict[str, int] = {}
                source_map: dict[str, str] = {}
                uvc_display_values: list[str] = []
                for c in cams:
                    n = c["name"]
                    seen[n] = seen.get(n, 0) + 1
                    label = n if name_totals[n] == 1 else f"{n} ({seen[n]})"
                    source_map[label] = format_uvc_named_source(n, c["address"])
                    uvc_display_values.append(label)
                # mDNS lookup is blocking; this whole _scan runs on a worker
                # thread already, so it's fine here. Network trackers go to the
                # *top* of the dropdown because they're typically the user's
                # primary capture source — UVC is the fallback / debug case.
                mdns_values = discover_etvr_mdns_sources()
                for v in mdns_values:
                    source_map[v] = v

                values = mdns_values + uvc_display_values

                uvc_hint = ", ".join(uvc_display_values) or "none"
                mdns_hint = ", ".join(mdns_values) or "none"

                def _apply():
                    self._source_display_map = source_map
                    self.left_camera_entry.configure(values=values)
                    self.right_camera_entry.configure(values=values)
                    # If the currently-shown text is an encoded uvc: form
                    # (e.g. just loaded from config at launch), rewrite it to
                    # the friendly label now that the scan knows the mapping.
                    encoded_to_label = {v: k for k, v in source_map.items()}
                    for var in (self.left_camera_var, self.right_camera_var):
                        cur = var.get()
                        if cur in encoded_to_label:
                            var.set(encoded_to_label[cur])
                    self.status_var.set(
                        f"Detected mDNS: {mdns_hint} | UVC: {uvc_hint}"
                    )

                self.root.after(0, _apply)

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
                        eyes[1]._shared_capture_source = eyes[0].camera
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

            if page_name in ("settings", "algo", "vrcft"):
                self._settings_actions_row.pack(side="right")
            else:
                self._settings_actions_row.pack_forget()

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
            # Keep eye trackers running while on a settings page so users can
            # see live effects of tweaks. Camera-config changes that require
            # a thread restart (capture_source, ROI, rotation, focal length)
            # are handled via on_config_update which soft-restarts only the
            # affected eye. Algo/filter toggles are read live by eye_processor
            # each iteration and apply without restart.
            self.apply_camera_inputs()
            settings[1].stop()
            settings[2].stop()
            settings[0].start()
            self._sync_timer_resolution()

        def _deferred_enter_algo(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            self.apply_camera_inputs()
            settings[0].stop()
            settings[2].stop()
            settings[1].start()
            self._sync_timer_resolution()

        def _deferred_enter_vrcft(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            self.apply_camera_inputs()
            settings[0].stop()
            settings[1].stop()
            settings[2].start()
            self._sync_timer_resolution()

        def _deferred_enter_issues(self, seq: int) -> None:
            if seq != self._nav_teardown_seq:
                return
            # Issues page has no live preview to maintain — stop trackers to
            # free the camera for unrelated diagnostics.
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

        def _any_eye_calibrating(self):
            for eye in eyes:
                rs = getattr(eye, "ransac", None)
                if rs is not None and rs.calibration_start_time is not None:
                    return True
            return False

        def _on_global_calibration_toggle(self):
            # Mirror the per-eye toggle: if anything is already calibrating,
            # stop all eyes; otherwise start calibration on every started eye.
            # Starting calibration on a stopped eye is a no-op so this is safe
            # to call regardless of capture state.
            if self._any_eye_calibrating():
                for eye in eyes:
                    rs = getattr(eye, "ransac", None)
                    if rs is not None:
                        rs.calibration_start_time = None
            else:
                for eye in eyes:
                    if eye.started():
                        eye.recalibrate_eyes()

        def _on_global_tracking_mode(self):
            for eye in eyes:
                eye._set_tracking_mode()
            self._sync_global_mode_buttons()

        def _on_global_roi_mode(self):
            for eye in eyes:
                eye._set_roi_mode()
            self._sync_global_mode_buttons()

        def _sync_global_mode_buttons(self):
            in_roi = any(getattr(e, "in_roi_mode", False) for e in eyes)
            self._global_roi_btn.configure(
                style="Accent.TButton" if in_roi else "TButton"
            )
            self._global_tracking_btn.configure(
                style="TButton" if in_roi else "Accent.TButton"
            )

        def _on_global_recenter(self):
            for eye in eyes:
                if eye.started():
                    eye.recenter_eyes()

        def _sync_global_calibration_button(self):
            text = (
                "Stop Calibration"
                if self._any_eye_calibrating()
                else "Start Calibration"
            )
            if self._calibration_btn_text.get() != text:
                self._calibration_btn_text.set(text)

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
                    self._sync_global_calibration_button()
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
    # Populate the UVC dropdowns at launch so the user sees the current
    # cameras without having to click "Scan". after(0) defers it until the
    # event loop is running; scan_sources itself does the enumeration on a
    # background thread.
    app.root.after(0, app.scan_sources)
    app.root.mainloop()


if __name__ == "__main__":
    main()
