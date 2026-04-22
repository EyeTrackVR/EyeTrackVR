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

import os
import tkinter as tk
from tkinter import ttk
import sv_ttk
import queue
import cv2
import requests
import threading
import base64
from camera_widget import CameraWidget
from config import EyeTrackConfig
from eye import EyeId
from settings.VRCFTModuleSettings import VRCFTSettingsWidget
from settings.general_settings_widget import SettingsWidget
from settings.algo_settings_widget import AlgoSettingsWidget
from osc.osc import OSCManager
from osc.OSCMessage import OSCMessage
from utils.misc_utils import is_nt, is_macos, resource_path


winmm = None

if is_nt:
    from winotify import Notification
    from ctypes import windll, c_int
    try:
        winmm = windll.winmm
    except OSError:
        print("\033[91m[WARN] Failed to load winmm.dll\033[0m")
os.system("color")  # init ANSI color


# Random environment variable to speed up webcam opening on the MSMF backend.
# https://github.com/opencv/opencv/issues/17687
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
WINDOW_NAME = "EyeTrackApp"



appversion = "EyeTrackApp 0.2.5.6"

def timerResolution(toggle):
    if winmm != None:
        if toggle:
            rc = c_int(winmm.timeBeginPeriod(1))
            if rc.value != 0:
                # TIMEERR_NOCANDO = 97
                print(f"\033[93m[WARN] Failed to set timer resolution: {rc.value}\033[0m")
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
            response = requests.get("https://api.github.com/repos/EyeTrackVR/EyeTrackVR/releases/latest")
            latestversion = response.json()["name"]

            if (
                appversion == latestversion
            ):  # If what we scraped and hardcoded versions are same, assume we are up to date.
                print(f"\033[92m[INFO] App is the latest version! [{latestversion}]\033[0m")
            else:
                print(
                    f"\033[93m[INFO] You have app version [{appversion}] installed. Please update to [{latestversion}] for the newest features.\033[0m"
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
                except Exception as e:
                    print("[INFO] Toast notifications not supported")
    except:
        print("\033[91m[INFO] Could not check for updates. Please try again later.\033[0m")

    timerResolution(True)

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
            self.root.title(appversion)
            try:
                self.root.iconbitmap(resource_path("Images/logo.ico"))
            except Exception:
                pass
            sv_ttk.set_theme("dark")
            self.focus_paused = False
            self.current_page = "tracking"
            self.preview_left_photo = None
            self.preview_right_photo = None
            self.mode_var = tk.StringVar(value="etvr")
            self.preview_labels = []
            self.preview_eye_order = []
            self.preview_blank_photos = []

            nav = ttk.Frame(self.root)
            nav.pack(fill="x", padx=8, pady=(8, 4))
            ttk.Button(nav, text="Tracking", command=lambda: self.show_page("tracking")).pack(side="left", padx=4)
            ttk.Button(nav, text="Settings", command=lambda: self.show_page("settings")).pack(side="left", padx=4)
            ttk.Button(nav, text="Algo Settings", command=lambda: self.show_page("algo")).pack(side="left", padx=4)
            ttk.Button(nav, text="VRCFT Module Settings", command=lambda: self.show_page("vrcft")).pack(side="left", padx=4)

            self.content = ttk.Frame(self.root)
            self.content.pack(fill="both", expand=True, padx=8, pady=8)

            self.tracking_tab = ttk.Frame(self.content)
            self.settings_frame = settings[0].build(self.content)
            self.algo_frame = settings[1].build(self.content)
            self.vrcft_frame = settings[2].build(self.content)

            tracking_outer = ttk.Frame(self.tracking_tab, padding=8)
            tracking_outer.pack(fill="both", expand=True)
            tracking_sidebar = ttk.Frame(tracking_outer, width=220)
            tracking_sidebar.pack_propagate(False)
            tracking_sidebar.pack(side="left", fill="y", padx=(0, 12))
            tracking_main = ttk.Frame(tracking_outer)
            tracking_main.pack(side="left", fill="both", expand=True)

            setup_type = ttk.LabelFrame(tracking_sidebar, text="Setup Type", padding=8)
            setup_type.pack(fill="x", pady=(0, 8))
            ttk.Radiobutton(setup_type, text="ETVR Setup", variable=self.mode_var, value="etvr", command=self.on_mode_change).pack(
                anchor="w"
            )
            ttk.Radiobutton(
                setup_type, text="Bigscreen Beyond", variable=self.mode_var, value="bigscreen", command=self.on_mode_change
            ).pack(anchor="w")

            tracking_controls = ttk.LabelFrame(tracking_sidebar, text="Camera Settings", padding=8)
            tracking_controls.pack(fill="x", pady=(0, 8))
            self.left_camera_var = tk.StringVar(value=str(config.left_eye.capture_source or ""))
            self.right_camera_var = tk.StringVar(value=str(config.right_eye.capture_source or ""))
            self.left_camera_label = ttk.Label(tracking_controls, text="Left (UVC / COM port / URL):")
            self.left_camera_label.pack(anchor="w")
            ttk.Entry(tracking_controls, textvariable=self.left_camera_var).pack(fill="x", pady=(2, 8))
            self.right_camera_label = ttk.Label(tracking_controls, text="Right (UVC / COM port / URL):")
            self.right_camera_entry = ttk.Entry(tracking_controls, textvariable=self.right_camera_var)
            self.right_camera_label.pack(anchor="w")
            self.right_camera_entry.pack(fill="x", pady=(2, 8))
            camera_button_row = ttk.Frame(tracking_controls)
            camera_button_row.pack(fill="x")
            ttk.Button(camera_button_row, text="Scan", width=8, command=self.scan_sources).pack(side="left", padx=(0, 4))
            ttk.Button(camera_button_row, text="Connect", command=self.apply_camera_inputs).pack(side="left", fill="x", expand=True)

            status_group = ttk.LabelFrame(tracking_sidebar, text="Status", padding=8)
            status_group.pack(fill="both", expand=True)
            self.mode_label_var = tk.StringVar(value="")
            self.status_var = tk.StringVar(value="Ready.")
            ttk.Label(status_group, textvariable=self.status_var, wraplength=190, justify="left", anchor="w").pack(
                anchor="w", fill="x"
            )
            ttk.Label(status_group, textvariable=self.mode_label_var, wraplength=190, justify="left").pack(anchor="w", pady=(6, 0))

            self.preview_content = ttk.LabelFrame(tracking_main, text="Camera Previews", padding=6)
            self.preview_content.pack(fill="x", expand=False, anchor="n")
            self.preview_row = ttk.Frame(self.preview_content)
            self.preview_row.pack(fill="x", expand=False)
            self._setup_preview_panes(2)

            self.hidden_eyes_container = ttk.Frame(self.tracking_tab)
            self.left_frame = eyes[1].build(self.hidden_eyes_container, show_camera_controls=False)
            self.right_frame = eyes[0].build(self.hidden_eyes_container, show_camera_controls=False)

            bottom = ttk.Frame(self.root)
            bottom.pack(fill="x", padx=8, pady=4)
            ttk.Button(bottom, text="GUI OFF", command=self.gui_off).pack(side="left")
            self.focus_label = ttk.Label(bottom, text="- - -  Interface Paused  - - -")
            self.focus_label.pack(side="left", padx=12)
            self.focus_label.pack_forget()

            self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
            self.on_mode_change()
            self.apply_camera_inputs()
            self.show_page("tracking")
            self._apply_initial_window_geometry()
            self._tick()

        def _apply_initial_window_geometry(self):
            # Tracking hides full camera UIs in an unpacked container, so winfo_req* stays small
            # while other tabs size naturally. Nudge the default window to a comfortable minimum.
            self.root.update_idletasks()
            min_w, min_h = 920, 580
            w = max(self.root.winfo_reqwidth(), min_w)
            h = max(self.root.winfo_reqheight(), min_h)
            self.root.geometry(f"{w}x{h}")

        def set_openvr_autostart(self, value):
            for module in settings[0].initialized_modules:
                if hasattr(module, "gui_openvr_autostart"):
                    module.tk_vars[getattr(module, "gui_openvr_autostart")].set(bool(value))

        def _normalize_camera_input(self, raw_value: str):
            value = (raw_value or "").strip()
            if value == "":
                return None
            try:
                return int(value)
            except ValueError:
                if len(value) > 5 and "http" not in value and ".mp4" not in value and "/dev" not in value:
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

        def _setup_preview_panes(self, count):
            for child in self.preview_row.winfo_children():
                child.destroy()
            self.preview_labels = []
            self.preview_blank_photos = []
            if count == 2:
                titles = ["Left Eye", "Right Eye"]
            else:
                titles = ["Left Eye"] if self.preview_eye_order and self.preview_eye_order[0] == EyeId.LEFT else ["Right Eye"]
            for idx in range(count):
                pane = ttk.Frame(self.preview_row)
                pane.pack(side="left", fill="both", expand=True, padx=6, pady=2, anchor="n")
                ttk.Label(pane, text=titles[idx]).pack(pady=(0, 4))
                blank = tk.PhotoImage(width=72, height=72)
                self.preview_blank_photos.append(blank)
                label = tk.Label(pane, image=blank, bg="#1c1c1c", relief="flat", bd=0)
                label.image = blank
                label.pack()
                self.preview_labels.append(label)

        def scan_sources(self):
            self.status_var.set("Scanning camera indices...")

            def _scan():
                found = []
                for i in range(10):
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        ok, _ = cap.read()
                        if ok:
                            found.append(i)
                    cap.release()
                listing = ", ".join(str(i) for i in found) if found else "none"
                self.root.after(0, lambda: self.status_var.set(f"Available camera indices: {listing}"))

            threading.Thread(target=_scan, daemon=True).start()

        def apply_camera_inputs(self):
            left_source = self._normalize_camera_input(self.left_camera_var.get())
            if self.mode_var.get() == "bigscreen":
                right_source = left_source
                self.right_camera_var.set("" if left_source is None else str(left_source))
            else:
                right_source = self._normalize_camera_input(self.right_camera_var.get())
            config.left_eye.capture_source = left_source
            config.right_eye.capture_source = right_source

            if left_source and right_source:
                eyes[0].start()
                eyes[1].start()
                self.preview_eye_order = [EyeId.LEFT, EyeId.RIGHT]
                self._setup_preview_panes(2)
                config.settings.tracker_single_eye = 0
                config.eye_display_id = EyeId.BOTH
                self.mode_label_var.set("Mode: Dual-eye tracking")
                self.status_var.set("Tracking both eyes.")
            elif left_source:
                eyes[0].stop()
                eyes[1].start()
                self.preview_eye_order = [EyeId.LEFT]
                self._setup_preview_panes(1)
                config.settings.tracker_single_eye = 1
                config.eye_display_id = EyeId.LEFT
                self.mode_label_var.set("Mode: Single-eye (left)")
                self.status_var.set("Tracking left eye only.")
            elif right_source:
                eyes[1].stop()
                eyes[0].start()
                self.preview_eye_order = [EyeId.RIGHT]
                self._setup_preview_panes(1)
                config.settings.tracker_single_eye = 2
                config.eye_display_id = EyeId.RIGHT
                self.mode_label_var.set("Mode: Single-eye (right)")
                self.status_var.set("Tracking right eye only.")
            else:
                eyes[0].stop()
                eyes[1].stop()
                self.preview_eye_order = [EyeId.LEFT, EyeId.RIGHT]
                self._setup_preview_panes(2)
                config.settings.tracker_single_eye = 0
                config.eye_display_id = EyeId.BOTH
                self.mode_label_var.set("Mode: No active camera")
                self.status_var.set("Enter at least one camera source.")

            config.save()

        def show_page(self, page_name: str):
            self.current_page = page_name
            for frame in [self.tracking_tab, self.settings_frame, self.algo_frame, self.vrcft_frame]:
                frame.pack_forget()

            if page_name == "tracking":
                self.tracking_tab.pack(fill="both", expand=True)
                settings[0].stop()
                settings[1].stop()
                settings[2].stop()
                self.apply_camera_inputs()
            elif page_name == "settings":
                self.settings_frame.pack(fill="both", expand=True)
                eyes[0].stop()
                eyes[1].stop()
                settings[1].stop()
                settings[2].stop()
                settings[0].start()
            elif page_name == "algo":
                self.algo_frame.pack(fill="both", expand=True)
                eyes[0].stop()
                eyes[1].stop()
                settings[0].stop()
                settings[2].stop()
                settings[1].start()
            elif page_name == "vrcft":
                self.vrcft_frame.pack(fill="both", expand=True)
                eyes[0].stop()
                eyes[1].stop()
                settings[0].stop()
                settings[1].stop()
                settings[2].start()

        def _update_previews(self):
            photos = []
            for idx, eye_id in enumerate(self.preview_eye_order):
                if idx >= len(self.preview_labels):
                    break
                widget = eyes[1] if eye_id == EyeId.LEFT else eyes[0]
                if widget.preview_ppm_bytes:
                    encoded = base64.b64encode(widget.preview_ppm_bytes).decode("ascii")
                    photo = tk.PhotoImage(data=encoded, format="PPM")
                    self.preview_labels[idx].configure(image=photo)
                    self.preview_labels[idx].image = photo
                    photos.append(photo)
                else:
                    self.preview_labels[idx].configure(image="")
                    self.preview_labels[idx].image = None
            if photos:
                self.preview_left_photo = photos[0]
                self.preview_right_photo = photos[-1]

        def gui_off(self):
            config.settings.gui_disable_gui = True
            settings[0].stop(); settings[1].stop(); settings[2].stop()
            config.save()
            self.root.withdraw()
            dialog = tk.Toplevel()
            dialog.title("ETVR")
            ttk.Label(dialog, text="GUI Disabled!").pack(padx=12, pady=8)

            def enable_gui():
                config.settings.gui_disable_gui = False
                config.save()
                print("GUI Enabled")
                dialog.destroy()
                self.root.deiconify()

            ttk.Button(dialog, text="Enable GUI", command=enable_gui).pack(padx=12, pady=(0, 8))
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
                    self._update_previews()
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
            print("\033[94m[INFO] Exiting EyeTrackApp\033[0m")
            for eye in eyes:
                eye.stop()
            cancellation_event.set()
            osc_manager.shutdown()
            timerResolution(False)
            self.root.destroy()
            os._exit(0)

    app = AppUI()
    app.show_page("tracking")
    if (not is_macos) and (openvr_service is not None):
        openvr_service.window = app
    app.root.mainloop()




if __name__ == "__main__":
    main()