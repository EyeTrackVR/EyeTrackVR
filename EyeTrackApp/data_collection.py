import os
import time
import queue
import string
import random
import zipfile
import threading
import subprocess
import webbrowser
import platform
import socket as _socket
import struct
import cv2
import tkinter as tk
from tkinter import ttk

DATA_COLLECTION_VERSION = "v4"

speech_lock = threading.Lock()

def speak(text):
    done_event = threading.Event()
    threading.Thread(
        target=_speak_platform_specific,
        args=(text, done_event),
        daemon=True,
    ).start()
    return done_event

def _run_tts_command(command, timeout, stdin_text=None):
    import shutil
    if shutil.which(command[0]) is None:
        return False
    try:
        if stdin_text is None:
            result = subprocess.run(command, check=False, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return result.returncode == 0
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            proc.communicate(input=stdin_text.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False

def _speak_linux(text):
    linux_tts_commands = (
        ["spd-say", "--wait", text],
        ["espeak-ng", text],
        ["espeak", text],
    )
    for command in linux_tts_commands:
        if _run_tts_command(command, timeout=20):
            return
    _run_tts_command(["festival", "--tts"], timeout=20, stdin_text=text)

def _speak_platform_specific(text, done_event):
    try:
        with speech_lock:
            system = platform.system().lower()
            if system == "darwin":
                subprocess.run(["say", text], check=False, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            elif system == "windows":
                ps_cmd = (
                    f'Add-Type -AssemblyName System.Speech; '
                    f'(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{text}");'
                )
                subprocess.run(["powershell", "-Command", ps_cmd], check=False, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            elif system == "linux":
                _speak_linux(text)
    except Exception:
        pass
    finally:
        done_event.set()

def get_best_codec():
    system = platform.system().lower()
    if system == "windows":
        codecs_to_try = [("XVID", "avi"), ("avc1", "mp4"), ("DIVX", "avi"), ("MJPG", "avi")]
    else:
        codecs_to_try = [("avc1", "mp4"), ("H264", "mp4"), ("XVID", "avi"), ("MJPG", "avi")]

    for codec, container in codecs_to_try:
        try:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            tmp = os.path.join(os.getcwd(), f"_tmp_test_{codec}.{container}")
            w = cv2.VideoWriter(tmp, fourcc, 30, (240, 240), False)
            ok = w.isOpened()
            w.release()
            if os.path.exists(tmp):
                os.remove(tmp)
            if ok:
                return fourcc, codec, container
        except Exception:
            pass

    return cv2.VideoWriter_fourcc(*"MJPG"), "MJPG", "avi"

def _zip_output(seed, output_dir):
    zip_name = f"{DATA_COLLECTION_VERSION}_{seed}_ETVR_User_Data_Output.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                fp = os.path.join(root, file)
                zf.write(fp, os.path.relpath(fp, start=os.path.dirname(output_dir)))
    return zip_name


PROMPT_DATA = [
    (1,    "Look left"),
    (1,    "Look left and squint"),
    (2,    "Look right"),
    (2,    "Look right and squint"),
    (3,    "Look up"),
    (3,    "Look up and squint"),
    (4,    "Look down"),
    (4,    "Look down and squint"),
    (6,    "Look top-left"),
    (5,    "Look top-right"),
    (8,    "Look bottom-left"),
    (7,    "Look bottom-right"),
    (0,    "Look straight"),
    (0,    "Look straight and squint"),
    (None, "Close your eyes"),
    (None, "Squeeze your eyes shut"),
    (0,    "Widen your eyes and look straight"),
    (1,    "Widen your eyes and look left"),
    (2,    "Widen your eyes and look right"),
    (0,    "Raise eyebrows fully and look forward"),
    (0,    "Raise eyebrows halfway and look forward"),
    (0,    "Lower eyebrows fully and look forward"),
    (0,    "Lower eyebrows halfway and look forward"),
    (None, "Close your eyes and look in random direction"),
    (None, "Look in a full circle starting now"),
]

OVERLAY_PASSES = [
    # (overlay_cmd, label_prefix, tts_text, n_jitter)
    # gaze/squint/widen: bumped to 20 so the full 22-point grid gets sampled
    # (evenly-spaced skip picks 20 of 22, preserving outer+intermediate+center coverage).
    (100, "gaze",          "Follow the dot as it moves",                20),
    (101, "squint",        "Squint and follow the dot",                 20),
    (102, "widen",         "Widen eyes and follow the dot",             20),
    (105, "brows_dn_full", "Lower eyebrows fully and follow the dot",    4),
    (103, "brows_up_full", "Raise eyebrows fully and follow the dot",    4),
    (106, "brows_dn_half", "Lower eyebrows halfway and follow the dot",  4),
    (104, "brows_up_half", "Raise eyebrows halfway and follow the dot",  4),
]

# Maps DC_POS index (sent by overlay as signal 0–8) to label name.
# Order matches C++ DC_POS: clockwise outer ring, then center.
OVERLAY_POINT_NAMES = {
    0: "upper_left",  1: "up",          2: "upper_right",
    3: "right",       4: "lower_right", 5: "down",
    6: "lower_left",  7: "left",        8: "center",
}

# Jitter grid base positions ordered as a smooth snake path.
#
# Layout (22 points):
#   Outer ring   — edges at ±0.60 x / ±0.50–0.65 y
#   Intermediate — ±0.25–0.35 band (fills the previous deadzone)
#   Near-center  — ±0.12–0.18 cluster (bridges center prompts to intermediate)
#
# Path: up the left outer column (with intermediate interspersed) → cross to
# top-center → spiral inward through the center cluster → bottom-center →
# outward through right intermediate → up the right outer column.
# Maximum adjacent jump ≈ 0.62.
_JITTER_GRID_BASE = [
    # ── left outer column (bottom → top) ──────────────────────────────
    (-0.60, -0.65),   # outer bottom-left
    (-0.60, -0.20),   # outer left mid-low
    (-0.30, -0.35),   # intermediate lower-left       ← new
    (-0.25,  0.00),   # intermediate left-center       ← new
    (-0.60,  0.25),   # outer left mid-high
    (-0.30,  0.35),   # intermediate upper-left        ← new
    (-0.60,  0.65),   # outer top-left
    # ── cross to top-center, spiral inward ────────────────────────────
    ( 0.00,  0.50),   # outer top-center
    ( 0.00,  0.30),   # intermediate upper-center      ← new
    (-0.18,  0.12),   # near-center upper-left         ← new
    (-0.12, -0.18),   # near-center lower-left         ← new
    ( 0.00, -0.30),   # intermediate lower-center      ← new
    # ── bottom-center, spiral outward right ───────────────────────────
    ( 0.00, -0.50),   # outer bottom-center
    ( 0.30, -0.35),   # intermediate lower-right       ← new
    ( 0.18, -0.12),   # near-center lower-right        ← new
    ( 0.25,  0.00),   # intermediate right-center      ← new
    ( 0.12,  0.18),   # near-center upper-right        ← new
    ( 0.30,  0.35),   # intermediate upper-right       ← new
    # ── right outer column (top → bottom) ─────────────────────────────
    ( 0.60,  0.65),   # outer top-right
    ( 0.60,  0.25),   # outer right mid-high
    ( 0.60, -0.20),   # outer right mid-low
    ( 0.60, -0.65),   # outer bottom-right
]

def _jittered_grid_positions(session_seed, pass_index, n=22, jitter=0.12):
    """Return n positions following the base path, each offset by a small random amount.
    Seeded by (session_seed, pass_index) so every pass type gets different offsets.
    When n < len(_JITTER_GRID_BASE), evenly-spaced points are taken to preserve
    spatial coverage across the full outer→intermediate→near-center range."""
    rng = random.Random(f"{session_seed}:{pass_index}")
    all_pos = []
    for bx, by in _JITTER_GRID_BASE:
        x = max(-1.0, min(1.0, bx + rng.uniform(-jitter, jitter)))
        y = max(-1.0, min(1.0, by + rng.uniform(-jitter, jitter)))
        all_pos.append((round(x, 3), round(y, 3)))
    if n >= len(all_pos):
        return all_pos
    step = len(all_pos) / n
    return [all_pos[int(i * step)] for i in range(n)]

OVERLAY_PORT     = 2112
OVERLAY_CMD_PORT = 2113

def _apply_theme_to_titlebar(root: tk.Toplevel) -> None:
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        root.update_idletasks()
        wid = root.winfo_id()
        user32 = ctypes.windll.user32
        ga_root = 2
        hwnd = user32.GetAncestor(wid, ga_root)
        if not hwnd:
            hwnd = user32.GetParent(wid)
        if not hwnd:
            return
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


class DataCollectionWindow:
    def __init__(self, parent, eyes):
        self.parent = parent
        self.eyes = eyes
        self.window = tk.Toplevel(parent)
        self.window.title("Data Collection")
        self.window.withdraw()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        
        try:
            from utils.misc_utils import resource_path
            self.window.after(100, lambda: self.window.iconbitmap(resource_path("Images/logo.ico")))
        except Exception:
            pass
        
        self.window.after(100, lambda: _apply_theme_to_titlebar(self.window))

        self.session_running = False
        self.session_cancel = threading.Event()
        self.gui_queue = queue.Queue()
        
        self.active_queues = []
        self.active_eye_labels = []

        self._build_ui()
        self._poll_gui_queue()

    def show(self):
        self.window.transient(self.parent)
        self.window.update_idletasks()
        mw = self.parent.winfo_width()
        mh = self.parent.winfo_height()
        mx = self.parent.winfo_rootx()
        my = self.parent.winfo_rooty()
        pw = self.window.winfo_reqwidth()
        ph = self.window.winfo_reqheight()
        x = mx + max(0, (mw - pw) // 2)
        y = my + max(0, (mh - ph) // 2)
        self.window.geometry(f"+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_set()

    def close(self):
        if self.session_running:
            self.session_cancel.set()
        try:
            self.window.withdraw()
        except tk.TclError:
            pass

    def _build_ui(self):
        _bg = self.window.cget("background")
        _content = ttk.Frame(self.window, padding=16)
        _content.pack(fill="both", expand=True)
        
        tk.Label(
            _content,
            text="Data Collection",
            font=("Segoe UI", 12, "bold"),
            bg=_bg,
            fg="#e8e8e8",
        ).pack(anchor="w", pady=(0, 6))

        ttk.Label(
            _content,
            text=(
                "Help us improve EyeTrackVR by contributing data. It takes only a few minutes. "
                "Your setup can work perfectly or poorly to make meaningful improvements!"
            ),
            wraplength=400,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        ttk.Label(
            _content,
            text="Please run in VR inside SteamVR and use the VR overlay. Then be sure to submit the .zip on the form! Thank you!",
            font=("Segoe UI", 10, "bold"),
            wraplength=400,
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        self.use_overlay_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            _content,
            text="Use Calibration Overlay Passes",
            variable=self.use_overlay_var,
        ).pack(anchor="w", pady=(0, 8))

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(
            _content,
            textvariable=self._status_var,
            wraplength=400,
            justify="left"
        ).pack(anchor="w", pady=(0, 8))

        btn_row = ttk.Frame(_content)
        btn_row.pack(fill="x", pady=(0, 8))

        self._start_btn = ttk.Button(
            btn_row,
            text="Start Collection",
            command=self._start_collection,
            style="Accent.TButton",
        )
        self._start_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ttk.Button(
            btn_row,
            text="Stop",
            command=self._stop_collection,
            state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(0, 8))

        ttk.Button(
            btn_row,
            text="Open Submissions Page",
            command=lambda: webbrowser.open("https://ask.eyetrackvr.dev/next-leap-data-collection"),
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            btn_row,
            text="Open Folder",
            command=self._open_folder,
        ).pack(side="left")

        _close_row = ttk.Frame(self.window)
        _close_row.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(
            _close_row, text="Close", command=self.close
        ).pack(side="right")

    def _open_folder(self):
        output_dir = os.path.join(os.getcwd())
        system = platform.system().lower()
        if system == "windows":
            os.startfile(output_dir)
        elif system == "darwin":
            subprocess.Popen(["open", output_dir])
        else:
            subprocess.Popen(["xdg-open", output_dir])

    def _start_collection(self):
        if self.session_running:
            return
        
        self.active_queues = []
        self.active_eye_labels = []
        
        for eye in self.eyes:
            if eye.started():
                q = queue.Queue(maxsize=10)
                eye._effective_camera().add_extra_output_queue(q)
                self.active_queues.append(q)
                self.active_eye_labels.append("Left" if eye.eye_id.name == "LEFT" else "Right")
                
        if not self.active_queues:
            self._status_var.set("Error: No active cameras running. Start tracking first.")
            return

        self.session_running = True
        self.session_cancel.clear()
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._status_var.set("Starting collection...")
        threading.Thread(target=self._run_collection, daemon=True).start()

    def _stop_collection(self):
        self.session_cancel.set()

    def _run_collection(self):
        seed = "".join(random.choices(string.ascii_letters + string.digits, k=9))
        output_dir = os.path.join(os.getcwd(), f"{DATA_COLLECTION_VERSION}_{seed}_ETVR_Output")
        
        use_overlay = self.use_overlay_var.get()

        if os.path.exists(output_dir):
            import shutil
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

        n = len(self.active_queues)
        timestamp_files = []
        for label in self.active_eye_labels:
            ts = os.path.join(output_dir, f"{DATA_COLLECTION_VERSION}_{seed}_{label}_timestamps.txt")
            with open(ts, "w") as f:
                f.write("# Format: <frame_number> <prompt_text>\n")
                f.write("# Version: " + DATA_COLLECTION_VERSION + "\n")
                f.write("# Recorded on: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write("# Seed: " + seed + "\n\n")
            timestamp_files.append(ts)

        first_frames = [None] * n
        deadline = time.time() + 10
        while any(f is None for f in first_frames) and time.time() < deadline:
            if self.session_cancel.is_set():
                break
            for i in range(n):
                if first_frames[i] is None and not self.active_queues[i].empty():
                    try:
                        frame_data = self.active_queues[i].get_nowait()
                        frame = frame_data[0]
                        if self.eyes[i].settings.gui_setup_mode == "bigscreen":
                            mid = frame.shape[1] // 2
                            if self.eyes[i].eye_id.name == "LEFT":
                                frame = frame[:, :mid]
                            else:
                                frame = frame[:, mid:]
                        first_frames[i] = frame
                    except queue.Empty:
                        pass
            time.sleep(0.05)

        if any(f is None for f in first_frames) and not self.session_cancel.is_set():
            self.gui_queue.put(("status", "Could not get frames from cameras. Are they connected?"))
            self._cleanup_session()
            return

        fourcc, _, container = get_best_codec()
        video_writers = []
        for i in range(n):
            h, w = first_frames[i].shape[:2]
            is_color = len(first_frames[i].shape) == 3 and first_frames[i].shape[2] == 3
            fn = os.path.join(output_dir, f"{DATA_COLLECTION_VERSION}_{seed}_full_session_{self.active_eye_labels[i]}.{container}")
            vw = cv2.VideoWriter(fn, fourcc, 60, (w, h), is_color)
            video_writers.append(vw)

        def drain_to_video():
            for j in range(n):
                while not self.active_queues[j].empty():
                    try:
                        frame_data = self.active_queues[j].get_nowait()
                        frame = frame_data[0]
                        if self.eyes[j].settings.gui_setup_mode == "bigscreen":
                            mid = frame.shape[1] // 2
                            if self.eyes[j].eye_id.name == "LEFT":
                                frame = frame[:, :mid]
                            else:
                                frame = frame[:, mid:]
                        
                        if len(frame.shape) == 3 and frame.shape[2] == 4:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                            
                        video_writers[j].write(frame)
                    except queue.Empty:
                        break

        overlay_proc = None
        udp_sock = None
        cmd_sock = None
        send_cmd = None

        if use_overlay:
            # Try to launch overlay
            try:
                from utils.misc_utils import resource_path
                overlay_exe = resource_path("Tools/EyeTrackVR-Overlay.exe")
            except Exception:
                overlay_exe = os.path.join(os.getcwd(), "Tools", "EyeTrackVR-Overlay.exe")
            
            if not os.path.isfile(overlay_exe):
                self.gui_queue.put(("status", "Overlay executable not found. Running without overlay."))
                use_overlay = False
            else:
                try:
                    udp_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                    udp_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
                    udp_sock.bind(("127.0.0.1", OVERLAY_PORT))
                    udp_sock.settimeout(1.0)
                    cmd_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)

                    def _send_cmd(val, _sock=cmd_sock):
                        _sock.sendto(struct.pack(">i", val), ("127.0.0.1", OVERLAY_CMD_PORT))
                    send_cmd = _send_cmd

                    def send_text(text, _sock=cmd_sock):
                        encoded = text.encode("utf-8")
                        _sock.sendto(struct.pack(">i", 50) + encoded, ("127.0.0.1", OVERLAY_CMD_PORT))

                    overlay_proc = subprocess.Popen(
                        [overlay_exe, "interactive"],
                        cwd=os.path.dirname(overlay_exe),
                    )

                    self.gui_queue.put(("status", "Waiting for overlay..."))
                    ready = False
                    ov_deadline = time.time() + 15
                    while time.time() < ov_deadline and not self.session_cancel.is_set():
                        drain_to_video()
                        try:
                            data, _ = udp_sock.recvfrom(16)
                            val, = struct.unpack(">i", data[:4])
                            if val == 255:
                                ready = True
                                break
                        except _socket.timeout:
                            pass

                    if not ready:
                        self.gui_queue.put(("status", "Overlay did not respond. Running without it."))
                        use_overlay = False
                    else:
                        self.gui_queue.put(("status", "Overlay connected."))
                except Exception as e:
                    self.gui_queue.put(("status", f"Overlay setup failed: {e}. Running without it."))
                    use_overlay = False

        prompts_to_run = [
            (dot_code, tts_text)
            for dot_code, tts_text in PROMPT_DATA
            if not (use_overlay and dot_code is not None)
        ]
        total_prompts = len(prompts_to_run)

        try:
            for capture_count, (dot_code, tts_text) in enumerate(prompts_to_run):
                if self.session_cancel.is_set():
                    break

                self.gui_queue.put(("status", f"Speaking: {tts_text} ({capture_count+1}/{total_prompts})"))

                if use_overlay:
                    send_text(tts_text)
                speech_done = speak(tts_text)
                while not speech_done.is_set():
                    if self.session_cancel.is_set():
                        break
                    drain_to_video()
                    time.sleep(0.01)

                if not self.session_cancel.is_set():
                    speech_done = speak("now")
                    t0 = time.time()
                    while (time.time() - t0 < 2.0) or not speech_done.is_set():
                        if self.session_cancel.is_set():
                            break
                        drain_to_video()
                        time.sleep(0.01)

                if self.session_cancel.is_set():
                    break

                self.gui_queue.put(("status", f"Capturing snapshot..."))

                prompt_frames = [None] * n
                frame_numbers = [None] * n
                for j in range(n):
                    try:
                        frame_data = self.active_queues[j].get(timeout=5.0)
                        frame, frame_num = frame_data[0], frame_data[1]
                        if self.eyes[j].settings.gui_setup_mode == "bigscreen":
                            mid = frame.shape[1] // 2
                            if self.eyes[j].eye_id.name == "LEFT":
                                frame = frame[:, :mid]
                            else:
                                frame = frame[:, mid:]
                        
                        if len(frame.shape) == 3 and frame.shape[2] == 4:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                            
                        prompt_frames[j] = frame.copy()
                        frame_numbers[j] = frame_num
                        video_writers[j].write(frame)
                    except queue.Empty:
                        pass

                for j in range(n):
                    if frame_numbers[j] is not None:
                        with open(timestamp_files[j], "a") as f:
                            f.write(f"{frame_numbers[j]} #{tts_text}#\n")

                clean = tts_text.lower().replace(" ", "_")
                for j in range(n):
                    if prompt_frames[j] is not None:
                        img_fn = os.path.join(
                            output_dir,
                            f"{DATA_COLLECTION_VERSION}_{seed}_{self.active_eye_labels[j]}_{capture_count + 1:02d}_{clean}.png",
                        )
                        cv2.imwrite(img_fn, prompt_frames[j])

                if use_overlay:
                    send_cmd(98)
                speech_done = speak("captured")
                while not speech_done.is_set():
                    if self.session_cancel.is_set():
                        break
                    drain_to_video()
                    time.sleep(0.01)

            base_idx = len(prompts_to_run)
            if use_overlay and not self.session_cancel.is_set():
                base_idx = self._run_overlay_passes(
                    seed, output_dir, n, video_writers,
                    timestamp_files, drain_to_video, base_idx,
                    udp_sock, send_cmd, cmd_sock,
                )
            if use_overlay and not self.session_cancel.is_set():
                self._run_headset_shift_pass(
                    seed, output_dir, n, video_writers,
                    timestamp_files, drain_to_video, base_idx,
                    udp_sock, cmd_sock,
                )

        except Exception as e:
            self.gui_queue.put(("status", f"Error during collection: {e}"))
        finally:
            if send_cmd is not None and cmd_sock is not None:
                try:
                    send_cmd(200)
                except Exception:
                    pass
            if cmd_sock is not None:
                cmd_sock.close()
            if udp_sock is not None:
                udp_sock.close()
            if overlay_proc is not None and overlay_proc.poll() is None:
                overlay_proc.terminate()
                try:
                    overlay_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    overlay_proc.kill()

            for vw in video_writers:
                vw.release()

            if not self.session_cancel.is_set():
                zip_name = _zip_output(seed, output_dir)
                try:
                    import shutil
                    shutil.rmtree(output_dir, ignore_errors=True)
                except Exception:
                    pass
                speak("you are done").wait()
                self.gui_queue.put(("status", f"Done! Saved to: {zip_name}"))
            else:
                self.gui_queue.put(("status", "Session cancelled."))

            self._cleanup_session()

    def _do_overlay_capture(self, seed, output_dir, n, video_writers, timestamp_files, label, idx):
        frames = [None] * n
        frame_nums = [None] * n
        for j in range(n):
            try:
                frame_data = self.active_queues[j].get(timeout=5.0)
                frame, fnum = frame_data[0], frame_data[1]
                if self.eyes[j].settings.gui_setup_mode == "bigscreen":
                    mid = frame.shape[1] // 2
                    if self.eyes[j].eye_id.name == "LEFT":
                        frame = frame[:, :mid]
                    else:
                        frame = frame[:, mid:]
                        
                if len(frame.shape) == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                frames[j] = frame.copy()
                frame_nums[j] = fnum
                video_writers[j].write(frame)
            except queue.Empty:
                pass

        for j in range(n):
            if frame_nums[j] is not None:
                with open(timestamp_files[j], "a") as f:
                    f.write(f"{frame_nums[j]} #{label}#\n")

        for j in range(n):
            if frames[j] is not None:
                img_fn = os.path.join(
                    output_dir,
                    f"{DATA_COLLECTION_VERSION}_{seed}_{self.active_eye_labels[j]}_{idx + 1:02d}_{label}.png",
                )
                cv2.imwrite(img_fn, frames[j])

    def _run_overlay_passes(self, seed, output_dir, n, video_writers, timestamp_files,
                             drain_to_video, base_idx, udp_sock, send_cmd, cmd_sock):
        overlay_idx = base_idx
        total_passes = len(OVERLAY_PASSES)

        for pass_num, (pass_cmd, label_prefix, tts_text, n_jitter) in enumerate(OVERLAY_PASSES):
            if self.session_cancel.is_set():
                break

            self.gui_queue.put(("status", f"Overlay Pass {pass_num + 1}/{total_passes}: {tts_text}"))
            done = speak(tts_text)
            while not done.is_set():
                if self.session_cancel.is_set():
                    return overlay_idx
                drain_to_video()
                time.sleep(0.01)

            send_cmd(pass_cmd)

            # Phase 1: receive fixed 9-point signals (0–8) from overlay
            phase1_done = False
            while not self.session_cancel.is_set():
                drain_to_video()
                try:
                    data, _ = udp_sock.recvfrom(16)
                except _socket.timeout:
                    continue
                if len(data) < 4:
                    continue
                value, = struct.unpack(">i", data[:4])
                if 0 <= value <= 8:
                    label = f"{label_prefix}_{OVERLAY_POINT_NAMES[value]}"
                    self._do_overlay_capture(seed, output_dir, n, video_writers,
                                             timestamp_files, label, overlay_idx)
                    overlay_idx += 1
                elif value == 10:   # overlay entered jittered-grid phase
                    phase1_done = True
                    break
                elif value == 19:   # safety fallback
                    break

            if not phase1_done or self.session_cancel.is_set():
                continue

            # Phase 2: drive jittered grid positions (count varies by pass type)
            for gx, gy in _jittered_grid_positions(seed, pass_num, n=n_jitter):
                if self.session_cancel.is_set():
                    break
                drain_to_video()
                cmd_sock.sendto(struct.pack(">iff", 111, gx, gy), ("127.0.0.1", OVERLAY_CMD_PORT))

                captured = False
                deadline = time.time() + 8.0
                while time.time() < deadline and not self.session_cancel.is_set():
                    drain_to_video()
                    try:
                        data, _ = udp_sock.recvfrom(16)
                    except _socket.timeout:
                        continue
                    if len(data) < 4:
                        continue
                    if struct.unpack(">i", data[:4])[0] == 20:
                        captured = True
                        break

                if captured and not self.session_cancel.is_set():
                    label = f"{label_prefix}_x{gx:+.3f}_y{gy:+.3f}"
                    self._do_overlay_capture(seed, output_dir, n, video_writers,
                                             timestamp_files, label, overlay_idx)
                    overlay_idx += 1

            if self.session_cancel.is_set():
                break

            # End jittered phase; overlay sends signal 19
            cmd_sock.sendto(struct.pack(">i", 119), ("127.0.0.1", OVERLAY_CMD_PORT))
            deadline = time.time() + 5.0
            while time.time() < deadline and not self.session_cancel.is_set():
                drain_to_video()
                try:
                    data, _ = udp_sock.recvfrom(16)
                except _socket.timeout:
                    continue
                if len(data) >= 4 and struct.unpack(">i", data[:4])[0] == 19:
                    break

        return overlay_idx

    def _run_headset_shift_pass(self, seed, output_dir, n, video_writers, timestamp_files,
                                 drain_to_video, base_idx, udp_sock, cmd_sock):
        overlay_idx = base_idx
        self.gui_queue.put(("status", "Headset Shift Pass: look at center dot and shift your headset around"))

        cmd_sock.sendto(struct.pack(">i", 120), ("127.0.0.1", OVERLAY_CMD_PORT))
        speech_done = speak("Look at the center dot and shift your headset around in all directions")

        # Wait for TTS to finish, then a 0.5s grace period before capturing
        while not speech_done.is_set():
            if self.session_cancel.is_set():
                return overlay_idx
            drain_to_video()
            time.sleep(0.01)

        t0 = time.time()
        while time.time() - t0 < 0.5:
            if self.session_cancel.is_set():
                return overlay_idx
            drain_to_video()
            time.sleep(0.01)

        # Capture 25 frames at ~5Hz (200ms apart) for 5 seconds of headset-shift data
        for _ in range(25):
            if self.session_cancel.is_set():
                break
            drain_to_video()
            time.sleep(0.18)
            drain_to_video()
            self._do_overlay_capture(seed, output_dir, n, video_writers,
                                     timestamp_files, "hshift_center", overlay_idx)
            overlay_idx += 1

        cmd_sock.sendto(struct.pack(">i", 121), ("127.0.0.1", OVERLAY_CMD_PORT))

        deadline = time.time() + 5.0
        while time.time() < deadline and not self.session_cancel.is_set():
            drain_to_video()
            try:
                data, _ = udp_sock.recvfrom(16)
            except _socket.timeout:
                continue
            if len(data) < 4:
                continue
            val, = struct.unpack(">i", data[:4])
            if val == 19:
                break

        return overlay_idx

    def _cleanup_session(self):
        for i, eye in enumerate(self.eyes):
            if eye.started() and i < len(self.active_queues):
                eye._effective_camera().remove_extra_output_queue(self.active_queues[i])
        self.active_queues = []
        self.gui_queue.put(("session_done", None))

    def _poll_gui_queue(self):
        while not self.gui_queue.empty():
            try:
                msg_type, data = self.gui_queue.get_nowait()
                if msg_type == "status":
                    self._status_var.set(data)
                elif msg_type == "session_done":
                    self.session_running = False
                    self._start_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")
            except queue.Empty:
                break
        self.window.after(50, self._poll_gui_queue)
