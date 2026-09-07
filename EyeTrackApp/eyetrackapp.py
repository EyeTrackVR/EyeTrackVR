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
import shutil
import subprocess
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from camera_widget import CameraWidget
from camera_enum import (
    discover_etvr_mdns_sources,
    discover_etvr_serial_cameras,
    format_uvc_named_source,
    is_uvc_named_source,
    list_uvc_cameras,
)
from config import EyeTrackConfig
from eye import EyeId
from localization import init_localization, tr
from settings.VRCFTModuleSettings import VRCFTSettingsWidget
from settings.general_settings_widget import SettingsWidget
from settings.algo_settings_widget import AlgoSettingsWidget
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage
from utils.logging_utils import setup_logging
from utils.misc_utils import is_nt, is_macos, resource_path
from utils.tooltips import attach_tooltip
from utils.version_utils import compare_app_versions



APP_VERSION = "EyeTrackApp 0.3.0 BETA 9"
setup_logging(APP_VERSION)
logger = logging.getLogger(__name__)
winmm = None

if is_nt:
    from winotify import Notification
    from ctypes import windll, c_int

    try:
        windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

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


def _check_for_updates_bg(config) -> None:
    """Fetch latest GitHub release on a daemon thread; notifies if outdated."""
    try:
        if not config.settings.gui_update_check:
            return
        response = requests.get(
            "https://api.github.com/repos/EyeTrackVR/EyeTrackVR/releases/latest",
            timeout=(3, 10),
        )
        response.raise_for_status()
        latestversion = response.json()["name"]
        version_comparison = compare_app_versions(APP_VERSION, latestversion)
        if version_comparison == 0:
            logger.info("App is the latest version: %s", latestversion)
        elif version_comparison is not None and version_comparison < 0:
            logger.warning(
                "You have app version %s installed. Please update to %s for the newest features.",
                APP_VERSION,
                latestversion,
            )
            try:
                if is_nt:
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
                elif sys.platform.startswith("linux"):
                    notify_send = shutil.which("notify-send")
                    if notify_send is None:
                        logger.info(
                            "Desktop update notifications unavailable: "
                            "notify-send is not installed."
                        )
                        return
                    subprocess.Popen(
                        [
                            notify_send,
                            "--app-name=EyeTrackApp",
                            f"--icon={resource_path('Images/logo.png')}",
                            "EyeTrackVR: New Update Available!",
                            f"Please update to {latestversion}",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.info("Desktop update notification failed: %s", exc)
        elif version_comparison is not None:
            logger.info(
                "Installed app version %s is newer than published release %s; "
                "no update notification shown.",
                APP_VERSION,
                latestversion,
            )
        else:
            logger.info(
                "Could not compare installed version %r with release %r; "
                "no update notification shown.",
                APP_VERSION,
                latestversion,
            )
    except (requests.RequestException, KeyError, ValueError):
        logger.info("Could not check for updates. Please try again later.", exc_info=True)


def main():
    config: EyeTrackConfig = EyeTrackConfig.load()
    config.save()

    # Load the UI language before any widgets are built. tkinter fixes widget
    # text at creation time, so the language must be resolved up front; changing
    # it in Settings persists the choice and prompts a restart.
    init_localization(getattr(config.settings, "gui_language", "en"))

    cancellation_event = threading.Event()
    # Ensure we always have a local reference, even if OpenVR autostart is disabled
    openvr_service = None

    # Wire up the OpenVR service so the app can register for SteamVR
    # auto-launch and shut down when SteamVR closes. We always register the
    # config listener (when OpenVR is importable and we're not on macOS) so
    # that toggling the option on at runtime works even if it started off.
    if not is_macos:
        try:
            from OVR.OpenVRService import openvr_service as _openvr_service
        except Exception as e:
            logger.warning(f"OpenVR support unavailable: {e}")
            _openvr_service = None

        if _openvr_service is not None:
            openvr_service = _openvr_service
            openvr_service.autostart_enabled = bool(config.settings.gui_openvr_autostart)
            config.register_listener_callback(openvr_service.on_config_update)
            # Re-assert auto-launch registration at startup; self-heals the case
            # where it was enabled while SteamVR was closed.
            if config.settings.gui_openvr_autostart:
                openvr_service.ensure_registered()

    osc_queue: queue.Queue[OSCMessage] = queue.Queue(maxsize=10)

    def _next_smartcal_selected() -> bool:
        """Smart Calib is the calibration for NEXT and only for NEXT.

        It is tied to the tracker, not to a setting: NEXT gaze is an end-to-end
        model output that the (warp + affine) fit polishes, while every other
        tracker calibrates pupil pixels through cal_osc's ellipse fit. Feeding
        either one the other's calibration produces nothing usable, so there is
        no opt-out here and no opt-in for the rest. gui_NEXT_BSB is the retired
        stereo-tracker flag, honored for configs that predate the migration."""
        return bool(config.settings.gui_NEXT) or bool(config.settings.gui_NEXT_BSB)

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
    def _osc_recalibrate(osc_message: OSCMessage):
        """Route the in-VR recalibrate trigger the same way as the GUI's
        Start Calibration button: Smart Calib for NEXT, the overlay spiral for
        other trackers, classic on-screen sampling when overlay calibration is
        disabled. The old per-eye classic-only handler silently never completed
        for NEXT users."""
        if not isinstance(osc_message.data, bool) or not osc_message.data:
            return
        use_smartcal = _next_smartcal_selected()
        if config.settings.gui_use_overlay_cal:
            from osc_calibrate_filter import (
                next_smartcal_overlay,
                overlay_ellipse_calibrate,
            )

            eps = [
                eye.ransac for eye in eyes
                if eye.started() and getattr(eye, "ransac", None) is not None
            ]
            if not eps:
                return
            if use_smartcal:
                next_smartcal_overlay(eps, config.settings, config)
            else:
                config.settings.calib_mode = "classic"
                config.save()
                overlay_ellipse_calibrate(eps, config.settings, config)
            return
        if use_smartcal:
            logger.warning(
                "OSC recalibrate ignored: NEXT Smart Calib requires the SteamVR "
                "overlay. Enable 'Use SteamVR Overlay for Calibration' in "
                "General Settings, or switch to another tracker for the classic "
                "on-screen calibration."
            )
            return
        for eye in eyes:
            if eye.started():
                eye.recalibrate_eyes()

    osc_manager.register_listeners(
        config.settings.gui_osc_recalibrate_address,
        [_osc_recalibrate],
    )

    osc_manager.start()

    from data_collection import DataCollectionWindow

    class AppUI:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title(APP_VERSION)
            self._dpi_scale = 1.0
            if is_nt:
                try:
                    import tkinter.font as tkfont
                    dpi = windll.user32.GetDpiForSystem()
                    self._dpi_scale = dpi / 96.0
                    self.root.tk.call("tk", "scaling", dpi / 72.0)
                    logger.info(f"System DPI: {dpi}, scale: {self._dpi_scale:.2f}x")
                except Exception as e:
                    logger.warning(f"DPI scaling failed: {e}")
            try:
                if is_nt:
                    self.root.iconbitmap(resource_path("Images/logo.ico"))
                else:
                    # .ico iconbitmap raises TclError on Linux/macOS; use the
                    # PNG via iconphoto (default=True covers child Toplevels).
                    self._icon_photo = tk.PhotoImage(
                        file=resource_path("Images/logo.png")
                    )
                    self.root.iconphoto(True, self._icon_photo)
            except Exception:
                pass
            sv_ttk.set_theme("dark")
            if is_nt and self._dpi_scale > 1.05:
                try:
                    import tkinter.font as tkfont
                    for name in tkfont.names(root=self.root):
                        try:
                            f = tkfont.nametofont(name, root=self.root)
                            size = f.cget("size")
                            if size != 0:
                                f.configure(size=round(size * self._dpi_scale))
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"Font scaling failed: {e}")
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
            nav.pack(fill="x", padx=16, pady=(16, 4))
            self._nav_buttons = {}
            for page_id, label in (
                ("tracking", tr("nav.tracking")),
                ("settings", tr("nav.settings")),
                ("algo", tr("nav.algo")),
                ("vrcft", tr("nav.vrcft")),
            ):
                btn = ttk.Button(
                    nav, text=label, command=lambda p=page_id: self.show_page(p)
                )
                btn.pack(side="left", padx=4)
                self._nav_buttons[page_id] = btn

            self.content = ttk.Frame(self.root)
            self.content.pack(fill="both", expand=True, padx=8, pady=(0, 16))

            self.tracking_tab = ttk.Frame(self.content)
            self.settings_frame = settings[0].build(self.content)
            self.algo_frame = settings[1].build(self.content, eye_widgets=eyes, dpi_scale=self._dpi_scale)
            self.vrcft_frame = settings[2].build(self.content)

            # "Having Issues?" popup: floats over the current page, same pattern
            # as the Advanced Algo Settings popup.
            self._issues_popup_visible = False
            self._issues_popup = tk.Toplevel(self.root)
            self._issues_popup.title(tr("issues.title"))
            self._issues_popup.withdraw()
            self._issues_popup.resizable(False, False)
            self._issues_popup.protocol("WM_DELETE_WINDOW", self._on_issues_popup_close)
            apply_theme_to_titlebar(self._issues_popup)

            self._data_collection_popup = DataCollectionWindow(self.root, eyes)

            _issues_hdr_font = ("Segoe UI", 12, "bold")
            _hdr_bg = self._issues_popup.cget("background")
            _issues_content = ttk.Frame(self._issues_popup, padding=16)
            _issues_content.pack(fill="both", expand=True)
            issues_wrap = 400

            tk.Label(
                _issues_content,
                text=tr("issues.header_issues"),
                font=_issues_hdr_font,
                bg=_hdr_bg,
                fg="#e8e8e8",
            ).pack(anchor="w", pady=(0, 6))
            ttk.Label(
                _issues_content,
                text=tr("issues.body_issues"),
                wraplength=issues_wrap,
                justify="left",
            ).pack(anchor="w", pady=(0, 16))
            tk.Label(
                _issues_content,
                text=tr("issues.header_improve"),
                font=_issues_hdr_font,
                bg=_hdr_bg,
                fg="#e8e8e8",
            ).pack(anchor="w", pady=(0, 6))
            ttk.Label(
                _issues_content,
                text=tr("issues.body_improve"),
                wraplength=issues_wrap,
                justify="left",
            ).pack(anchor="w", pady=(0, 16))
            issues_btn_row = ttk.Frame(_issues_content)
            issues_btn_row.pack(anchor="w", pady=(0, 8))

            def _launch_data_collection():
                self._on_issues_popup_close()
                self._toggle_data_collection_popup()

            def _open_discord():
                webbrowser.open("https://discord.gg/kkXYbVykZX")

            ttk.Button(
                issues_btn_row,
                text=tr("issues.data_collection_btn"),
                command=_launch_data_collection,
                style="Accent.TButton",
            ).pack(side="left", padx=(0, 8))
            ttk.Button(issues_btn_row, text=tr("issues.discord_btn"), command=_open_discord).pack(side="left")

            _issues_close_row = ttk.Frame(self._issues_popup)
            _issues_close_row.pack(fill="x", padx=16, pady=(0, 16))
            ttk.Button(
                _issues_close_row, text=tr("issues.close_btn"), command=self._on_issues_popup_close
            ).pack(side="right")

            tracking_outer = ttk.Frame(self.tracking_tab)
            tracking_outer.pack(fill="both", expand=True)
            tracking_sidebar = ttk.Frame(tracking_outer, width=round(300 * self._dpi_scale))
            tracking_sidebar.pack_propagate(False)
            tracking_sidebar.pack(side="left", fill="y", padx=(0, 16))
            sidebar_inner = ttk.Frame(tracking_sidebar, padding=16)
            sidebar_inner.pack(fill="both", expand=True)
            tracking_main = ttk.Frame(tracking_outer)
            tracking_main.pack(side="left", fill="both", expand=True)

            _sidebar_hdr_font = ("Segoe UI", round(10 * self._dpi_scale), "bold")
            _setup_type_outer = ttk.Frame(sidebar_inner)
            _setup_type_outer.pack(fill="x", pady=(0, 24))
            ttk.Label(_setup_type_outer, text=tr("tracking.setup_type"), font=_sidebar_hdr_font).pack(anchor="w", pady=(0, 4))
            setup_type = ttk.Frame(_setup_type_outer)
            setup_type.pack(fill="x")
            etvr_radio = ttk.Radiobutton(
                setup_type,
                text=tr("tracking.setup_etvr"),
                variable=self.mode_var,
                value="etvr",
                command=self.on_mode_change,
            )
            etvr_radio.pack(anchor="w", pady=4)
            attach_tooltip(
                etvr_radio,
                tr("tracking.setup_etvr_tip"),
            )
            bsb_radio = ttk.Radiobutton(
                setup_type,
                text=tr("tracking.setup_bigscreen"),
                variable=self.mode_var,
                value="bigscreen",
                command=self.on_mode_change,
            )
            bsb_radio.pack(anchor="w", pady=4)
            attach_tooltip(
                bsb_radio,
                tr("tracking.setup_bigscreen_tip"),
            )

            _tracking_controls_outer = ttk.Frame(sidebar_inner)
            _tracking_controls_outer.pack(fill="x", pady=(0, 24))
            ttk.Label(_tracking_controls_outer, text=tr("tracking.camera_settings"), font=_sidebar_hdr_font).pack(anchor="w", pady=(0, 4))
            tracking_controls = ttk.Frame(_tracking_controls_outer)
            tracking_controls.pack(fill="x")
            left_initial = config.left_eye.capture_source
            right_initial = config.right_eye.capture_source
            self.left_camera_var = tk.StringVar(
                value="" if left_initial is None or left_initial == "" else str(left_initial)
            )
            self.right_camera_var = tk.StringVar(
                value="" if right_initial is None or right_initial == "" else str(right_initial)
            )
            self.left_camera_label = ttk.Label(
                tracking_controls, text=tr("tracking.left_source")
            )
            self.left_camera_label.pack(anchor="w", pady=(0, 2))
            # Combobox (not Entry) so Scan can populate a dropdown of detected
            # UVC cameras while still letting the user type a COM port / URL /
            # index by hand. Picked dropdown entries are written as
            # ``uvc:<name>@<address>`` strings, which the capture thread
            # re-resolves to a live cv2 index every loop.
            self.left_camera_entry = ttk.Combobox(
                tracking_controls, textvariable=self.left_camera_var, values=(), foreground="#e0e0e0"
            )
            self.left_camera_entry.pack(fill="x", pady=(0, 8))
            attach_tooltip(
                self.left_camera_entry,
                tr("tracking.left_source_tip"),
            )
            self.right_camera_label = ttk.Label(
                tracking_controls, text=tr("tracking.right_source")
            )
            self.right_camera_entry = ttk.Combobox(
                tracking_controls, textvariable=self.right_camera_var, values=(), foreground="#e0e0e0"
            )
            self.right_camera_label.pack(anchor="w", pady=(0, 2))
            self.right_camera_entry.pack(fill="x", pady=(0, 8))
            attach_tooltip(
                self.right_camera_entry,
                tr("tracking.right_source_tip"),
            )
            # Picking a value from the dropdown auto-connects (matches what
            # users expect after running Scan). Typed input intentionally does
            # NOT auto-connect; that's what the Connect button is for, and
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
            scan_btn = ttk.Button(
                camera_button_row, text=tr("tracking.scan_btn"), width=8, command=self.scan_sources
            )
            scan_btn.pack(side="left", padx=(0, 4))
            attach_tooltip(
                scan_btn,
                tr("tracking.scan_btn_tip"),
            )
            connect_btn = ttk.Button(
                camera_button_row,
                text=tr("tracking.connect_btn"),
                command=self.apply_camera_inputs,
                style="Accent.TButton",
            )
            connect_btn.pack(side="left", fill="x", expand=True)
            attach_tooltip(
                connect_btn,
                tr("tracking.connect_btn_tip"),
            )

            status_group = ttk.LabelFrame(sidebar_inner, text=tr("tracking.status_frame"), padding=8)
            status_group.pack(fill="both", expand=True)
            self.mode_label_var = tk.StringVar(value="")
            self.status_var = tk.StringVar(value=tr("status.ready"))
            ttk.Label(
                status_group,
                textvariable=self.status_var,
                wraplength=240,
                justify="left",
                anchor="w",
            ).pack(anchor="w", fill="x")
            ttk.Label(
                status_group,
                textvariable=self.mode_label_var,
                wraplength=240,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))

            # Global mode toggle: flips both eyes between Tracking and
            # Cropping at once. Per-eye buttons used to live inside each
            # camera widget; users always wanted them paired.
            mode_row = ttk.Frame(tracking_main)
            mode_row.pack(fill="x", pady=(0, 32))
            mode_inner = ttk.Frame(mode_row)
            mode_inner.pack(anchor="center")
            self._global_tracking_btn = ttk.Button(
                mode_inner,
                text=tr("tracking.tracking_mode_btn"),
                command=self._on_global_tracking_mode,
            )
            self._global_tracking_btn.pack(side="left", padx=8)
            attach_tooltip(
                self._global_tracking_btn,
                tr("tracking.tracking_mode_btn_tip"),
            )
            self._global_roi_btn = ttk.Button(
                mode_inner,
                text=tr("tracking.cropping_mode_btn"),
                command=self._on_global_roi_mode,
            )
            self._global_roi_btn.pack(side="left", padx=8)
            attach_tooltip(
                self._global_roi_btn,
                tr("tracking.cropping_mode_btn_tip"),
            )

            # Eye selector shown below the mode buttons only while in crop mode.
            self._crop_active_eye = "left"
            self._crop_eye_row = ttk.Frame(mode_row)
            _crop_inner = ttk.Frame(self._crop_eye_row)
            _crop_inner.pack(anchor="center", pady=(12, 0))
            self._crop_left_btn = ttk.Button(
                _crop_inner,
                text=tr("tracking.left_eye_btn"),
                command=lambda: self._on_crop_eye_select("left"),
                style="Accent.TButton",
            )
            self._crop_left_btn.pack(side="left", padx=4)
            self._crop_right_btn = ttk.Button(
                _crop_inner,
                text=tr("tracking.right_eye_btn"),
                command=lambda: self._on_crop_eye_select("right"),
            )
            self._crop_right_btn.pack(side="left", padx=4)

            self._sync_global_mode_buttons()

            self.tracking_eyes_row = ttk.Frame(tracking_main)
            # anchor="center": keeps both eye panels as a unit in the middle of
            # tracking_main rather than stretching them edge-to-edge.
            self.tracking_eyes_row.pack(anchor="center")
            self.left_frame = eyes[1].build(
                self.tracking_eyes_row, show_camera_controls=False, dpi_scale=self._dpi_scale
            )
            self.right_frame = eyes[0].build(
                self.tracking_eyes_row, show_camera_controls=False, dpi_scale=self._dpi_scale
            )
            self.left_frame.pack(side="left", fill="y", padx=(0, 8))
            self.right_frame.pack(side="left", fill="y", padx=(8, 0))

            # Global calibration / recenter row. Replaces the per-eye buttons
            # that used to live in each camera widget; left/right always need
            # to calibrate together, and two pairs of buttons made it ambiguous
            # which eye's state was being toggled.
            # fill="x" on the outer frame so the inner button group can center
            # within the full tracking_main width. Tight top padding keeps the
            # buttons close to the visualization above.
            self._tracking_actions = ttk.Frame(tracking_main)
            self._tracking_actions.pack(fill="x", pady=(40, 0))
            actions_inner = ttk.Frame(self._tracking_actions)
            actions_inner.pack(anchor="center")
            self._calibration_btn_text = tk.StringVar(value=tr("tracking.start_calibration"))
            self._global_calibration_btn = ttk.Button(
                actions_inner,
                textvariable=self._calibration_btn_text,
                command=self._on_global_calibration_toggle,
                style="Accent.TButton",
            )
            self._global_calibration_btn.pack(side="left", padx=(0, 8))
            attach_tooltip(
                self._global_calibration_btn, tr("tracking.start_calibration_tip")
            )
            ttk.Button(
                actions_inner,
                text=tr("tracking.recenter_btn"),
                command=self._on_global_recenter,
            ).pack(side="left", padx=8)
            # Escape hatch for a bad NEXT Smart Calib fit: clears the saved
            # transform so the raw model gaze flows again. Only shown while the
            # NEXT tracker is active AND a fitted transform exists (see
            # _sync_next_smartcal_reset_button). The calibration itself runs
            # from the main Start Calibration button.
            self._next_smartcal_reset_btn = ttk.Button(
                actions_inner,
                text=tr("tracking.next_smartcal_reset_btn"),
                command=self._on_next_smartcal_reset,
            )
            attach_tooltip(
                self._next_smartcal_reset_btn,
                tr("tracking.next_smartcal_reset_btn_tip"),
            )
            self._next_smartcal_reset_visible = False
            bottom = ttk.Frame(self.root)
            bottom.pack(fill="x", padx=8, pady=4)
            ttk.Button(bottom, text=tr("tracking.gui_off_btn"), command=self.gui_off).pack(side="left")
            ttk.Button(
                bottom, text=tr("issues.title"), command=self._toggle_issues_popup
            ).pack(side="left", padx=(10, 0))
            ttk.Button(
                bottom, text=tr("tracking.contribute_data_btn"), command=self._toggle_data_collection_popup
            ).pack(side="left", padx=(10, 0))
            self.focus_label = ttk.Label(bottom, text=tr("tracking.interface_paused"))
            self.focus_label.pack(side="left", padx=12)
            self.focus_label.pack_forget()

            # Settings-only actions, shown only while a settings page is active.
            self._settings_actions_row = ttk.Frame(bottom)
            tk.Button(
                self._settings_actions_row,
                text=tr("tracking.delete_config_btn"),
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
                text=tr("tracking.reset_settings_btn"),
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
            config.register_listener_callback(self._on_vrcft_output_config_update)
            self._sync_vrcft_nav_visibility()
            self.on_mode_change()
            self.show_page("tracking")
            self._apply_initial_window_geometry()
            self._tick()

        def _vrcft_module_settings_enabled(self) -> bool:
            """The module settings only apply to the VRCFT UE (v2) output."""
            return bool(config.settings.gui_osc_vrcft_v2)

        def _sync_vrcft_nav_visibility(self) -> None:
            button = self._nav_buttons.get("vrcft")
            if button is None:
                return

            if self._vrcft_module_settings_enabled():
                if not button.winfo_manager():
                    # VRCFT is the final navigation item, so repacking it keeps
                    # the original tab order.
                    button.pack(side="left", padx=4)
            else:
                button.pack_forget()
                if self.current_page == "vrcft":
                    self.show_page("settings")

        def _on_vrcft_output_config_update(self, data: dict) -> None:
            if "gui_osc_vrcft_v2" not in data:
                return
            # Settings updates normally arrive on Tk's thread. Scheduling the
            # UI mutation also keeps this safe if a future caller updates the
            # output mode from a worker.
            try:
                self.root.after_idle(self._sync_vrcft_nav_visibility)
            except tk.TclError:
                pass

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
            # Leave enough room for the fixed sidebar and both eye panels at
            # common 1440p Windows scaling; 880 clipped the right-eye panel on
            # some 27-inch displays. Do not keep enlarging the default-width
            # floor above 125% DPI, though, or it becomes excessive on 4K. The
            # requested size can still grow it when content genuinely needs it.
            self.root.update_idletasks()
            s = self._dpi_scale
            width_scale = min(s, 1.25)
            min_w, min_h = round(1120 * width_scale), round(660 * s)
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
            # parsing; otherwise it'd fall through to the "looks like a URL?"
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
                self.left_camera_label.configure(text=tr("tracking.source_uvc_index"))
                self.right_camera_label.configure(text=tr("tracking.right_same_source"))
            else:
                self.right_camera_entry.state(["!disabled"])
                self.left_camera_label.configure(text=tr("tracking.left_source"))
                self.right_camera_label.configure(text=tr("tracking.right_source"))
            # Persist so the next launch reopens in the same mode rather than
            # falling back to ETVR (which then reuses the BSB-era right_eye
            # source, the same camera as the left).
            if getattr(config.settings, "gui_setup_mode", None) != mode:
                config.settings.gui_setup_mode = mode
                config.save()

            # Auto-pick the matching model variant for the setup mode, unless the
            # user has manually chosen one (then we leave their choice alone).
            # Routed through config.update so the settings combobox stays in sync.
            if not getattr(config.settings, "gui_model_variant_user_set", False):
                default_variant = "BSB" if is_bigscreen else "ETVR"
                if getattr(config.settings, "gui_model_variant", None) != default_variant:
                    config.update({"gui_model_variant": default_variant}, save=True)

        def scan_sources(self):
            self.status_var.set(tr("status.scanning"))

            def _scan():
                # Results dict: None means that source is still in-flight.
                results: dict[str, list | None] = {
                    "uvc": None,
                    "mdns": None,
                    "serial": None,
                }

                def _apply_partial():
                    uvc_cams = results["uvc"] or []
                    mdns_values = results["mdns"] or []
                    serial_pairs = results["serial"] or []

                    name_totals: dict[str, int] = {}
                    for c in uvc_cams:
                        name_totals[c["name"]] = name_totals.get(c["name"], 0) + 1
                    seen: dict[str, int] = {}
                    source_map: dict[str, str] = {}
                    uvc_display_values: list[str] = []
                    for c in uvc_cams:
                        n = c["name"]
                        seen[n] = seen.get(n, 0) + 1
                        label = n if name_totals[n] == 1 else f"{n} ({seen[n]})"
                        source_map[label] = format_uvc_named_source(n, c["address"])
                        uvc_display_values.append(label)

                    # When UVC scan is still in flight, preserve the previous UVC
                    # entries. Without this, mDNS/serial returning first empties
                    # source_map of UVC entries, and any navigation that triggers
                    # apply_camera_inputs will see _source_display_map without the
                    # friendly labels, causing _normalize_camera_input to treat
                    # "Camera (1)" as a URL and corrupt the saved config.
                    if results["uvc"] is None:
                        for k, v in self._source_display_map.items():
                            if is_uvc_named_source(v) and k not in source_map:
                                source_map[k] = v
                                uvc_display_values.append(k)

                    for v in mdns_values:
                        source_map[v] = v

                    serial_display_values: list[str] = []
                    for lbl, device in serial_pairs:
                        display_label = lbl if lbl not in source_map else f"{lbl} [serial]"
                        source_map[display_label] = device
                        serial_display_values.append(display_label)

                    # mDNS → serial → UVC ordering in the dropdown (network
                    # trackers are the primary source; UVC is fallback).
                    values = [""] + mdns_values + serial_display_values + uvc_display_values

                    self._source_display_map = source_map
                    self.left_camera_entry.configure(values=values)
                    self.right_camera_entry.configure(values=values)
                    encoded_to_label = {v: k for k, v in source_map.items()}
                    for var in (self.left_camera_var, self.right_camera_var):
                        cur = var.get()
                        if cur in encoded_to_label:
                            var.set(encoded_to_label[cur])

                    pending = [k.upper() for k, v in results.items() if v is None]
                    if pending:
                        ready_parts = []
                        if results["uvc"] is not None:
                            ready_parts.append(f"UVC: {', '.join(uvc_display_values) or tr('status.scan_none')}")
                        if results["mdns"] is not None:
                            ready_parts.append(f"mDNS: {', '.join(mdns_values) or tr('status.scan_none')}")
                        if results["serial"] is not None:
                            ready_parts.append(f"Serial: {', '.join(serial_display_values) or tr('status.scan_none')}")
                        prefix = " | ".join(ready_parts) + (" | " if ready_parts else "")
                        self.status_var.set(
                            tr("status.scan_pending", prefix=prefix, pending=", ".join(pending))
                        )
                    else:
                        uvc_hint = ", ".join(uvc_display_values) or tr("status.scan_none")
                        mdns_hint = ", ".join(mdns_values) or tr("status.scan_none")
                        serial_hint = ", ".join(serial_display_values) or tr("status.scan_none")
                        self.status_var.set(
                            tr("status.scan_detected", mdns=mdns_hint, serial=serial_hint, uvc=uvc_hint)
                        )

                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = {
                        pool.submit(list_uvc_cameras): "uvc",
                        pool.submit(discover_etvr_mdns_sources): "mdns",
                        pool.submit(discover_etvr_serial_cameras): "serial",
                    }
                    for fut in as_completed(futures):
                        key = futures[fut]
                        try:
                            results[key] = fut.result()
                        except Exception:
                            results[key] = []
                        self.root.after(0, _apply_partial)

            threading.Thread(target=_scan, daemon=True).start()

        def _camera_tracking_state_key(self, left_source, right_source):
            # Use explicit None checks: UVC index 0 is a valid source but is falsy in Python,
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
                    eyes[0].camera.is_split = False
                    eyes[1].detach_shared_capture_event()
                    if shared:
                        eyes[0].camera.set_extra_output_queues([eyes[1].capture_queue])
                        eyes[0].camera.is_split = self.mode_var.get() == "bigscreen"
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
                self.mode_label_var.set(tr("status.mode_dual"))
                self.status_var.set(tr("status.tracking_both"))
            elif has_left:
                if not eyes[1].started():
                    eyes[0].camera.set_extra_output_queues([])
                    eyes[1].detach_shared_capture_event()
                    eyes[0].stop()
                    eyes[1].start()
                config.settings.tracker_single_eye = 1
                config.eye_display_id = EyeId.LEFT
                self.mode_label_var.set(tr("status.mode_single_left"))
                self.status_var.set(tr("status.tracking_left"))
            elif has_right:
                if not eyes[0].started():
                    eyes[0].camera.set_extra_output_queues([])
                    eyes[1].detach_shared_capture_event()
                    eyes[1].stop()
                    eyes[0].start()
                config.settings.tracker_single_eye = 2
                config.eye_display_id = EyeId.RIGHT
                self.mode_label_var.set(tr("status.mode_single_right"))
                self.status_var.set(tr("status.tracking_right"))
            else:
                eyes[0].stop()
                eyes[1].stop()
                config.settings.tracker_single_eye = 0
                config.eye_display_id = EyeId.BOTH
                self.mode_label_var.set(tr("status.mode_none"))
                self.status_var.set(tr("status.enter_source"))

            config.save()
            self._sync_timer_resolution()

        def show_page(self, page_name: str):
            """Switch tabs. Heavy work (camera thread joins, config apply) is deferred so the UI can redraw first."""
            if page_name == "vrcft" and not self._vrcft_module_settings_enabled():
                page_name = "settings"
            self._nav_teardown_seq += 1
            seq = self._nav_teardown_seq
            self.current_page = page_name
            for frame in [
                self.tracking_tab,
                self.settings_frame,
                self.algo_frame,
                self.vrcft_frame,
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

        def _toggle_issues_popup(self):
            if self._issues_popup_visible:
                self._on_issues_popup_close()
            else:
                self._show_issues_popup()

        def _toggle_data_collection_popup(self):
            self._data_collection_popup.show()

        def _show_issues_popup(self):
            popup = self._issues_popup
            popup.transient(self.root)
            popup.update_idletasks()
            mw = self.root.winfo_width()
            mh = self.root.winfo_height()
            mx = self.root.winfo_rootx()
            my = self.root.winfo_rooty()
            pw = popup.winfo_reqwidth()
            ph = popup.winfo_reqheight()
            x = mx + max(0, (mw - pw) // 2)
            y = my + max(0, (mh - ph) // 2)
            popup.geometry(f"+{x}+{y}")
            popup.deiconify()
            popup.lift()
            popup.focus_set()
            self._issues_popup_visible = True

        def _on_issues_popup_close(self):
            self._issues_popup_visible = False
            try:
                self._issues_popup.withdraw()
            except tk.TclError:
                pass

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
            ttk.Label(dialog, text=tr("tracking.gui_disabled_msg")).pack(padx=12, pady=8)

            def enable_gui():
                config.settings.gui_disable_gui = False
                config.save()
                logger.info("GUI enabled")
                dialog.destroy()
                self.root.deiconify()

            ttk.Button(dialog, text=tr("tracking.enable_gui_btn"), command=enable_gui).pack(
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
            # NEXT calibrates via the Smart Calib overlay dot sequence; the
            # ellipse spiral would collect nothing, because the NEXT path never
            # feeds cal_osc. Every other tracker gets the spiral.
            use_smartcal = _next_smartcal_selected()
            if config.settings.gui_use_overlay_cal:
                if use_smartcal:
                    self._on_next_smartcal()
                else:
                    self._on_ellipse_calibration()
                return
            if use_smartcal:
                # No on-screen equivalent exists for the NEXT smart calibration,
                # and the classic sampler would never finish (cal_osc is never
                # fed by the NEXT path).
                logger.warning(
                    "NEXT Smart Calib requires the SteamVR overlay. Enable "
                    "'Use SteamVR Overlay for Calibration' in General Settings, "
                    "or switch to another tracker for the classic on-screen "
                    "calibration."
                )
                return
            # Classic on-screen calibration toggle: stop if running, start if not.
            if self._any_eye_calibrating():
                for eye in eyes:
                    rs = getattr(eye, "ransac", None)
                    if rs is not None:
                        rs.calibration_start_time = None
            else:
                for eye in eyes:
                    if eye.started():
                        eye.recalibrate_eyes()

        def _show_tracking_frames(self):
            self.left_frame.pack_forget()
            self.right_frame.pack_forget()
            self.left_frame.pack(side="left", fill="y", padx=(0, 8))
            self.right_frame.pack(side="left", fill="y", padx=(8, 0))

        def _show_crop_frames(self, eye_name: str):
            self.left_frame.pack_forget()
            self.right_frame.pack_forget()
            if eye_name == "left":
                self.left_frame.pack(side="left", fill="y")
            else:
                self.right_frame.pack(side="left", fill="y")

        def _on_crop_eye_select(self, eye_name: str):
            self._crop_active_eye = eye_name
            self._crop_left_btn.configure(
                style="Accent.TButton" if eye_name == "left" else "TButton"
            )
            self._crop_right_btn.configure(
                style="Accent.TButton" if eye_name == "right" else "TButton"
            )
            if eye_name == "left":
                eyes[0]._set_tracking_mode()
                eyes[1]._set_roi_mode()
            else:
                eyes[1]._set_tracking_mode()
                eyes[0]._set_roi_mode()
            self._show_crop_frames(eye_name)

        def _on_global_tracking_mode(self):
            for eye in eyes:
                eye._set_tracking_mode()
            self._show_tracking_frames()
            self._sync_global_mode_buttons()

        def _on_global_roi_mode(self):
            active = self._crop_active_eye
            if active == "left":
                eyes[0]._set_tracking_mode()
                eyes[1]._set_roi_mode()
            else:
                eyes[1]._set_tracking_mode()
                eyes[0]._set_roi_mode()
            self._show_crop_frames(active)
            self._sync_global_mode_buttons()

        def _sync_global_mode_buttons(self):
            in_roi = any(getattr(e, "in_roi_mode", False) for e in eyes)
            next_tracker = bool(config.settings.gui_NEXT) or bool(
                config.settings.gui_NEXT_BSB
            )

            # NEXT consumes the uncropped camera frame, in both the regular
            # ETVR setup and Bigscreen Beyond setup.  Cropping is therefore not
            # applicable.  Also leave crop mode if NEXT was selected while the
            # user was already editing an ROI, so no hidden state remains
            # active after the button disappears.
            if next_tracker and in_roi:
                for eye in eyes:
                    eye._set_tracking_mode()
                self._show_tracking_frames()
                in_roi = False

            if next_tracker:
                self._global_roi_btn.pack_forget()
            elif not self._global_roi_btn.winfo_manager():
                self._global_roi_btn.pack(side="left", padx=8)

            if hasattr(self, "_tracking_actions"):
                if in_roi:
                    self._tracking_actions.pack_forget()
                else:
                    self._tracking_actions.pack(fill="x", pady=(40, 0))
            if hasattr(self, "_crop_eye_row"):
                if in_roi:
                    self._crop_eye_row.pack(fill="x")
                else:
                    self._crop_eye_row.pack_forget()
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

        def _on_ellipse_calibration(self):
            from osc_calibrate_filter import overlay_ellipse_calibrate
            eps = [
                eye.ransac for eye in eyes
                if eye.started() and getattr(eye, "ransac", None) is not None
            ]
            if not eps:
                return
            config.settings.calib_mode = "classic"
            config.save()
            overlay_ellipse_calibrate(eps, config.settings, config)

        def _on_next_smartcal(self):
            from osc_calibrate_filter import next_smartcal_overlay
            eps = [
                eye.ransac for eye in eyes
                if eye.started() and getattr(eye, "ransac", None) is not None
            ]
            if not eps:
                return
            next_smartcal_overlay(eps, config.settings, config)

        def _on_next_smartcal_reset(self):
            from osc_calibrate_filter import reset_next_smartcal
            eps = [
                eye.ransac for eye in eyes
                if eye.started() and getattr(eye, "ransac", None) is not None
            ]
            if not eps:
                return
            reset_next_smartcal(eps, config)

        def _sync_next_smartcal_reset_button(self):
            # The reset escape hatch is only meaningful when a fitted transform
            # is actually saved; keeping it hidden otherwise avoids cluttering
            # the action row for fresh installs.
            # Lid/brow anchors count too: a run whose gaze fit was rejected can
            # still have calibrated those, and Reset clears all of it.
            has_fit = any(
                getattr(eye, field, None) is not None
                for eye in (config.left_eye, config.right_eye)
                for field in (
                    "next_smartcal_w",
                    "next_smartcal_lid_neutral",
                    "next_smartcal_brow_neutral",
                )
            )
            show = (
                (bool(config.settings.gui_NEXT) or bool(config.settings.gui_NEXT_BSB))
                and has_fit
                and any(e.started() for e in eyes)
            )
            if show == self._next_smartcal_reset_visible:
                return
            self._next_smartcal_reset_visible = show
            if show:
                self._next_smartcal_reset_btn.pack(side="left", padx=8)
            else:
                self._next_smartcal_reset_btn.pack_forget()

        def _sync_global_calibration_button(self):
            text = (
                tr("tracking.stop_calibration")
                if self._any_eye_calibrating()
                else tr("tracking.start_calibration")
            )
            if self._calibration_btn_text.get() != text:
                self._calibration_btn_text.set(text)

        def _tick(self):
            if openvr_service is not None and openvr_service.poll_quit_event():
                logger.info("SteamVR quit, shutting down EyeTrackApp")
                self.shutdown()
                return

            try:
                has_focus = self.root.focus_displayof() is not None
            except KeyError:
                has_focus = True
            interval = 33
            if has_focus:
                if self.focus_paused:
                    self.focus_paused = False
                    self.focus_label.pack_forget()
                if self.current_page == "tracking":
                    self._sync_global_mode_buttons()
                    for eye in eyes:
                        if eye.started():
                            eye.render_tick()
                    self._sync_global_calibration_button()
                    self._sync_next_smartcal_reset_button()
            else:
                if not self.focus_paused:
                    self.focus_paused = True
                    self.focus_label.pack(side="left", padx=12)
                interval = 100

            # Run settings validation + debounce-save regardless of focus so
            # changes made while the SteamVR overlay has focus still apply
            # within ~650 ms without requiring a page switch.
            for setting in settings:
                if setting.started():
                    setting.render_tick()

            self.root.after(interval, self._tick)

        def shutdown(self):
            logger.info("Exiting EyeTrackApp")
            # Signal every eye before joining any of them.  A dead HTTP camera
            # can leave FFmpeg inside its native open timeout, and the old
            # sequential five-second joins made Tk look hung (up to ten seconds
            # for two eyes).  Normal camera restarts still use stop()'s longer
            # orderly wait; final process shutdown gets one small shared budget.
            for eye in eyes:
                eye.request_stop()
            shutdown_deadline = time.monotonic() + 0.5
            for eye in eyes:
                eye.stop(
                    join_timeout=max(0.0, shutdown_deadline - time.monotonic()),
                    warn_if_alive=False,
                )
            cancellation_event.set()
            osc_manager.shutdown()
            if getattr(self, "_timer_high_res", False):
                set_timer_resolution(False)
            self.root.destroy()
            os._exit(0)

    app = AppUI()
    if (not is_macos) and (openvr_service is not None):
        openvr_service.window = app
    threading.Thread(
        target=_check_for_updates_bg, args=(config,), daemon=True, name="UpdateCheck"
    ).start()
    # Populate the UVC dropdowns at launch so the user sees the current
    # cameras without having to click "Scan". after(0) defers it until the
    # event loop is running; scan_sources itself does the enumeration on a
    # background thread.
    app.root.after(0, app.scan_sources)
    app.root.mainloop()


if __name__ == "__main__":
    main()
