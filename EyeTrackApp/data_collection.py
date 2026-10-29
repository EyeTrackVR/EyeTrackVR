import os
import time
import shutil
import queue
import string
import random
import zipfile
import threading
import subprocess
import platform
import socket as _socket
import struct
import logging
import json
import cv2
import tkinter as tk

from localization import tr, tr_english, get_active_language
from utils.overlay_launch import overlay_executable, overlay_command
from frame_eye import is_steam_frame, models_paused_for_recording

DATA_COLLECTION_VERSION = "v6"

logger = logging.getLogger(__name__)

speech_lock = threading.Lock()


def speak(text, lang="en", fallback=None):
    """Speak ``text`` (language ``lang``) on a background thread; returns an
    Event set when done. ``fallback`` (English) is spoken instead when the
    system has no voice for ``lang``."""
    done_event = threading.Event()
    threading.Thread(
        target=_speak_platform_specific,
        args=(text, lang, fallback or text, done_event),
        daemon=True,
    ).start()
    return done_event


def say(key):
    """Speak a ``data_collection_prompts`` line in the app's UI language."""
    full = f"data_collection_prompts.{key}"
    return speak(tr(full), get_active_language(), tr_english(full))


def prompt_text(key):
    """A ``data_collection_prompts`` line in the app's UI language."""
    return tr(f"data_collection_prompts.{key}")


def _run_tts_command(command, timeout, stdin_text=None, env=None):
    import shutil

    if shutil.which(command[0]) is None:
        return False
    try:
        if stdin_text is None:
            result = subprocess.run(
                command, check=False, timeout=timeout, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return result.returncode == 0
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        try:
            proc.communicate(input=stdin_text.encode("utf-8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False


# espeak voice names where they differ from the UI language code.
_ESPEAK_VOICES = {"zh": "cmn"}


def _bundled_espeak():
    """``(executable, env)`` for the espeak-ng the Steam Frame build ships in
    Tools/tts/ (the headset has no TTS engine of its own), or None."""
    from utils.misc_utils import resource_path

    tts = resource_path("Tools/tts")
    exe = os.path.join(tts, "espeak-ng")
    if not os.access(exe, os.X_OK):
        return None
    env = dict(os.environ, ESPEAK_DATA_PATH=tts, LD_LIBRARY_PATH=os.path.join(tts, "lib"))
    return exe, env


def _speak_linux(text, lang, fallback):
    """Speak with the bundled espeak-ng, else the first system TTS engine
    found. False when there is none."""
    bundled = _bundled_espeak()
    if bundled is not None:
        exe, env = bundled
        if _run_tts_command([exe, "-v", _ESPEAK_VOICES.get(lang, lang), text], timeout=20, env=env):
            return True
        if lang != "en" and _run_tts_command([exe, "-v", "en", fallback], timeout=20, env=env):
            return True
    if lang != "en":
        voice = _ESPEAK_VOICES.get(lang, lang)
        for command in (
            ["spd-say", "--wait", "-l", lang, text],
            ["espeak-ng", "-v", voice, text],
            ["espeak", "-v", voice, text],
        ):
            if _run_tts_command(command, timeout=20):
                return True
        text = fallback  # no voice for this language: say it in English
    linux_tts_commands = (
        ["spd-say", "--wait", text],
        ["espeak-ng", text],
        ["espeak", text],
    )
    for command in linux_tts_commands:
        if _run_tts_command(command, timeout=20):
            return True
    return _run_tts_command(["festival", "--tts"], timeout=20, stdin_text=text)


def _reading_seconds(text):
    """About how long ``text`` takes to say, used to pace a prompt that could
    not be spoken: the overlay card then stays up as long as the voice would
    have, instead of the next step starting before it can be read."""
    # Words for spaced scripts, characters for Chinese and Japanese.
    return min(8.0, 0.6 + max(0.4 * len(text.split()), 0.06 * len(text)))


# The text travels in environment variables, never inside the script, so quotes
# or non-ASCII characters in a translation cannot break the command. Picks an
# installed voice for the language; without one, speaks the English fallback.
_WINDOWS_TTS = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$t = $env:ETVR_TTS_TEXT; "
    "function Pick($c) { $s.GetInstalledVoices() | Where-Object { $_.Enabled -and "
    "$_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $c } | Select-Object -First 1 }; "
    "$v = Pick $env:ETVR_TTS_LANG; "
    "if (-not $v -and $env:ETVR_TTS_LANG -ne 'en') { $t = $env:ETVR_TTS_FALLBACK; $v = Pick 'en' }; "
    "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
    "$s.Speak($t)"
)


def _speak_platform_specific(text, lang, fallback, done_event):
    try:
        with speech_lock:
            system = platform.system().lower()
            if system == "darwin":
                subprocess.run(
                    ["say", text], check=False, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            elif system == "windows":
                env = dict(os.environ, ETVR_TTS_TEXT=text, ETVR_TTS_LANG=lang or "en", ETVR_TTS_FALLBACK=fallback)
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", _WINDOWS_TTS],
                    env=env,
                    check=False,
                    timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            elif system == "linux":
                if not _speak_linux(text, lang or "en", fallback):
                    time.sleep(_reading_seconds(text))
    except Exception:
        pass
    finally:
        done_event.set()


def get_best_codec():
    system = platform.system().lower()
    if system == "windows":
        codecs_to_try = [("XVID", "avi"), ("avc1", "mp4"), ("DIVX", "avi"), ("MJPG", "avi")]
    elif platform.machine().lower() in ("aarch64", "arm64"):
        # OpenCV's aarch64 ffmpeg maps H.264 to the V4L2 hardware encoder
        # (h264_v4l2m2m). On a Steam Frame, merely opening it segfaults inside
        # avcodec_open2 and takes the whole app down, so even this probe must
        # never try it. XVID is software MPEG-4, as on Windows.
        codecs_to_try = [("XVID", "avi"), ("MJPG", "avi")]
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


# (dot_code, label, prompt key). The English label names the saved snapshots
# and timestamp entries (training labels: never translate it); the prompt key
# picks what is spoken and shown, from lang/*.toml [data_collection_prompts].
PROMPT_DATA = [
    (1, "Look left", "look_left"),
    (1, "Look left and squint", "look_left_squint"),
    (2, "Look right", "look_right"),
    (2, "Look right and squint", "look_right_squint"),
    (3, "Look up", "look_up"),
    (3, "Look up and squint", "look_up_squint"),
    (4, "Look down", "look_down"),
    (4, "Look down and squint", "look_down_squint"),
    (6, "Look top-left", "look_top_left"),
    (5, "Look top-right", "look_top_right"),
    (8, "Look bottom-left", "look_bottom_left"),
    (7, "Look bottom-right", "look_bottom_right"),
    (0, "Look straight", "look_straight"),
    (0, "Look straight and squint", "look_straight_squint"),
    (None, "Close your eyes", "close_eyes"),
    (None, "Squeeze your eyes shut", "squeeze_shut"),
    (0, "Widen your eyes and look straight", "widen_straight"),
    (1, "Widen your eyes and look left", "widen_left"),
    (2, "Widen your eyes and look right", "widen_right"),
    (0, "Raise eyebrows fully and look forward", "brows_up_full"),
    (0, "Raise eyebrows halfway and look forward", "brows_up_half"),
    (0, "Lower eyebrows fully and look forward", "brows_down_full"),
    (0, "Lower eyebrows halfway and look forward", "brows_down_half"),
    (None, "Close your eyes and look in random direction", "close_random"),
    (None, "Look in a full circle starting now", "full_circle"),
]

OVERLAY_PASSES = [
    # (overlay_cmd, label_prefix, prompt key, n_jitter). The prompt key selects
    # both the spoken line ("pass_<key>") and the overlay card ("panel_<key>").
    # gaze/squint/widen: bumped to 20 so the full 22-point grid gets sampled
    # (evenly-spaced skip picks 20 of 22, preserving outer+intermediate+center coverage).
    (100, "gaze", "gaze", 20),
    (101, "squint", "squint", 20),
    (102, "widen", "widen", 20),
    (105, "brows_dn_full", "brows_dn_full", 4),
    (103, "brows_up_full", "brows_up_full", 4),
    (106, "brows_dn_half", "brows_dn_half", 4),
    (104, "brows_up_half", "brows_up_half", 4),
]

# Maps DC_POS index (sent by overlay as signal 0–8) to label name.
# Order matches C++ DC_POS: clockwise outer ring, then center.
OVERLAY_POINT_NAMES = {
    0: "upper_left",
    1: "up",
    2: "upper_right",
    3: "right",
    4: "lower_right",
    5: "down",
    6: "lower_left",
    7: "left",
    8: "center",
}

# Jitter grid base positions ordered as a smooth snake path.
#
# Layout with 22 points for broad radial coverage. The gaze LABEL
# for each point is its coordinate, and the deployed model was under-reaching
# (only ~±0.6 at full gaze) because this dense grid formed most of the gaze
# supervision and previously topped out at ±0.60, *narrower* than the overlay's
# ±0.786 fixed ring. Relocating (not adding) these points to the edge shifts the
# dense label mass outward so the model learns to use its full range, at zero
# extra capture time. Each dot is a saccade target (appear→shrink→hold), so the
# larger adjacent jumps are fine (no smooth-pursuit constraint).
#   Outer ring:   cardinals at ±0.85; corners near ±0.60 per axis
#                 (all jittered points are limited to radius 0.88)
#   Intermediate: ±0.35–0.49 band
#   Near-center:  ±0.17–0.25 cluster (still bridges the center prompts outward)
# Center itself stays well covered by the straight/blink/closed/hshift prompts,
# so this grid deliberately spends its points on the mid+outer field instead.
_JITTER_GRID_BASE = [
    # ── left outer column (bottom → top) ──────────────────────────────
    (-0.60, -0.60),  # equal-eccentricity outer bottom-left
    (-0.85, -0.26),  # outer left mid-low
    (-0.43, -0.46),  # intermediate lower-left
    (-0.36, 0.00),  # intermediate left-center
    (-0.85, 0.33),  # outer left mid-high
    (-0.43, 0.46),  # intermediate upper-left
    (-0.60, 0.60),  # equal-eccentricity outer top-left
    # ── cross to top-center, spiral inward ────────────────────────────
    (0.00, 0.85),  # outer top-center
    (0.00, 0.39),  # intermediate upper-center
    (-0.26, 0.16),  # near-center upper-left
    (-0.17, -0.23),  # near-center lower-left
    (0.00, -0.39),  # intermediate lower-center
    # ── bottom-center, spiral outward right ───────────────────────────
    (0.00, -0.85),  # outer bottom-center
    (0.43, -0.46),  # intermediate lower-right
    (0.26, -0.16),  # near-center lower-right
    (0.36, 0.00),  # intermediate right-center
    (0.17, 0.23),  # near-center upper-right
    (0.43, 0.46),  # intermediate upper-right
    # ── right outer column (top → bottom) ─────────────────────────────
    (0.60, 0.60),  # equal-eccentricity outer top-right
    (0.85, 0.33),  # outer right mid-high
    (0.85, -0.26),  # outer right mid-low
    (0.60, -0.60),  # equal-eccentricity outer bottom-right
]

# The HMD FOV is rectangular per axis but the lens-visible corner is generally
# rounded, especially through native OpenXR runtimes. Keep randomized targets
# within the same radial eccentricity as the fixed ring cardinals. Returned
# coordinates are written into each filename, so training labels remain exact.
# One millith inside 0.88 so three-decimal filename/command rounding cannot
# push a point just back outside the intended boundary.
_JITTER_MAX_RADIUS = 0.879


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
        r2 = x * x + y * y
        if r2 > _JITTER_MAX_RADIUS * _JITTER_MAX_RADIUS:
            scale = _JITTER_MAX_RADIUS / (r2**0.5)
            x *= scale
            y *= scale
        all_pos.append((round(x, 3), round(y, 3)))
    if n >= len(all_pos):
        return all_pos
    step = len(all_pos) / n
    return [all_pos[int(i * step)] for i in range(n)]


# ── Blink-at-dot pass ─────────────────────────────────────────────────────────
# The user fixates a pinned dot and blinks repeatedly with a relaxed brow.
# Burst captures sample every phase of the blink sweep including the mid blink frames
# that held-pose prompts never produce and that the model otherwise confuses
# with lowered eyebrows (the blink -> eyebrow-wobble artifact). Training reads
# these from the "blinkdot_x{±f}_y{±f}" label: gaze = dot coords, brow anchored
# neutral, squeeze anchored 0, eyelid unsupervised (aperture unknown mid-sweep).
#
# Mid-eccentricity base positions (jittered per session): far corners + blinking
# is an awkward combo users do badly, and four spread positions are enough for
# the decorrelation this pass exists for.
_BLINKDOT_BASE = [(-0.45, 0.35), (0.45, 0.35), (0.45, -0.35), (-0.45, -0.35)]
_BLINKDOT_JITTER = 0.12
BLINKDOT_BURST_FRAMES = 15  # per position
BLINKDOT_BURST_INTERVAL = 0.2  # ~3 s of blinking per position

# ── Closed-eye roam pass ──────────────────────────────────────────────────────
# Eyes held shut while the user moves face/brows/cheeks around: diversifies
# closed-lid appearance so "closed" is recognized under any facial pose. Only
# the eyelid label is trusted in training ("closed_roam"); brow/squeeze/gaze
# are all changing or unobservable and get zero weight.
CLOSED_ROAM_FRAMES = 25
CLOSED_ROAM_INTERVAL = 0.2


def _blinkdot_positions(session_seed):
    rng = random.Random(f"{session_seed}:blinkdot")
    out = []
    for bx, by in _BLINKDOT_BASE:
        x = max(-1.0, min(1.0, bx + rng.uniform(-_BLINKDOT_JITTER, _BLINKDOT_JITTER)))
        y = max(-1.0, min(1.0, by + rng.uniform(-_BLINKDOT_JITTER, _BLINKDOT_JITTER)))
        out.append((round(x, 3), round(y, 3)))
    return out


OVERLAY_PORT = 2112
OVERLAY_CMD_PORT = 2113

# Overlay command codes used by the passes below (see modes.cpp InteractiveMode).
OVERLAY_CMD_PIN_DOT = 113  # >iff x y: persistent dot at (x, y); overlay acks 21
OVERLAY_CMD_UNPIN = 114  # hide the pinned dot
OVERLAY_SIG_PINNED = 21
OVERLAY_CMD_TEXT = 50  # >i + UTF-8: instruction card ("title\nsubtitle")


def _overlay_text(cmd_sock, text):
    """Show ``text`` on the overlay's instruction card. Sent BEFORE the matching
    voice prompt starts so the card is up while it is being read, not after;
    the overlay keeps it when the pass/target command follows."""
    cmd_sock.sendto(struct.pack(">i", OVERLAY_CMD_TEXT) + text.encode("utf-8"), ("127.0.0.1", OVERLAY_CMD_PORT))


def _drain_udp_socket(sock):
    """Discard datagrams already buffered in ``sock``'s receive queue.

    Called at the start of each overlay pass so a stale signal left over from
    the previous pass's end-of-pass handshake (a late or duplicated ``19``)
    isn't misread by the next pass's phase-1 loop. Reading a stale ``19`` there
    breaks phase 1 immediately with ``phase1_done=False``, which makes the pass
    skip its entire jittered-grid capture (phase 2). When several passes skip
    like this the whole session races through in seconds and ends with the
    "you are done" prompt far too early (the reported bug). The skip is
    timing-dependent and shows up more in bigscreen, where ``drain_to_video``
    copies frames for two queues off the one shared camera and so widens the
    window in which packets pile up unread between passes."""
    sock.setblocking(False)
    try:
        while True:
            try:
                sock.recvfrom(64)
            except (BlockingIOError, _socket.error):
                break
    finally:
        sock.setblocking(True)
        sock.settimeout(1.0)


class _SessionRecorder:
    """Writes every captured frame of a recording into its eye's full-session
    video on a thread of its own, and keeps the newest frame per eye for the
    labeled snapshots.

    The capture passes used to drain the camera queues themselves, between
    blocking waits on the overlay socket of up to a second. The queues hold 10
    frames (about 0.1 s at the Steam Frame's 90 fps), so most of a pass's video
    was dropped, and each snapshot was the oldest frame left in the queue rather
    than one taken when the dot settled."""

    POLL = 0.002

    def __init__(self, queues, prepare, write):
        self._queues = queues
        self._prepare = prepare  # (j, frame) -> frame for eye j's video and snapshots
        self._write = write  # (j, frame) -> None, never raises
        self._cond = threading.Condition()
        self._latest = [None] * len(queues)  # (frame, frame_number, serial) per eye
        self._serial = [0] * len(queues)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="capture-recorder", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        """Write out what is still queued, then end the thread."""
        self._stop.set()
        self._thread.join(timeout=10.0)

    def _drain_once(self):
        got = False
        for j, q in enumerate(self._queues):
            while True:
                try:
                    frame_data = q.get_nowait()
                except queue.Empty:
                    break
                got = True
                try:
                    frame = self._prepare(j, frame_data[0])
                except Exception:
                    logger.exception("Dropped an unusable capture frame for eye index %d", j)
                    continue
                self._write(j, frame)
                with self._cond:
                    self._serial[j] += 1
                    self._latest[j] = (frame, frame_data[1], self._serial[j])
                    self._cond.notify_all()
        return got

    def _run(self):
        while not self._stop.is_set():
            if not self._drain_once():
                self._stop.wait(self.POLL)
        self._drain_once()
        with self._cond:
            self._cond.notify_all()

    def next_frame(self, j, timeout):
        """``(frame, frame_number)`` of a frame eye ``j`` delivered after this
        call (the newest one by the time this thread wakes), so a snapshot shows
        the eye after the prompt, not before it. Raises queue.Empty when none
        arrives within ``timeout`` seconds."""
        deadline = time.monotonic() + timeout
        with self._cond:
            seen = self._serial[j]
            while self._serial[j] == seen:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._stop.is_set():
                    raise queue.Empty
                self._cond.wait(remaining)
            frame, frame_number, _ = self._latest[j]
        return frame.copy(), frame_number


def _apply_theme_to_titlebar(root: tk.Toplevel) -> None:
    from contributions.native import decorate

    decorate(root)


class DataCollectionWindow:
    def __init__(self, parent, eyes):
        self.parent = parent
        self.eyes = eyes
        self.session_running = False
        self.session_cancel = threading.Event()
        self.gui_queue = queue.Queue()
        self.active_queues = []
        # Parallel to active_queues: the eye widget each queue belongs to and
        # the camera it was attached to. Only started eyes get a queue, so
        # index j here is NOT an index into self.eyes ([RIGHT, LEFT]).
        self.active_eyes = []
        self._attached_queues = []
        self.active_eye_labels = []
        # Working folder of the recording in progress (AVI + PNGs); removed
        # when the recording is cancelled or fails.
        self._session_output_dir = None
        self._video_writer_sizes = []
        self._recorder = None
        self._latest_capture = None
        self.use_overlay_var = tk.BooleanVar(master=parent, value=True)
        self._contributions = None
        self.window = None

    def _create_window(self):
        from contributions.window import ContributionWindow

        self._contributions = ContributionWindow(self.parent, capture_controller=self)
        self.window = self._contributions.window
        self._status_var = self._contributions.capture_status
        self._start_btn = self._contributions.record_button
        self._stop_btn = self._contributions.stop_record_button
        self.window.withdraw()
        self._poll_gui_queue()

    def show(self):
        if self._contributions is None:
            try:
                self._create_window()
            except (OSError, ValueError):
                from tkinter import messagebox

                messagebox.showerror(
                    "Contributions",
                    "Could not open private contribution storage. Check access to your user data folder.",
                    parent=self.parent,
                )
                return
        self.window.deiconify()
        self.window.update_idletasks()
        width, height = self.window.winfo_width(), self.window.winfo_height()
        x = self.parent.winfo_rootx() + max(0, (self.parent.winfo_width() - width) // 2)
        y = self.parent.winfo_rooty() + max(0, (self.parent.winfo_height() - height) // 2)
        x = max(0, min(x, self.window.winfo_screenwidth() - width))
        y = max(0, min(y, self.window.winfo_screenheight() - height - 60))
        self.window.geometry(f"+{x}+{y}")
        self.window.lift()
        self.window.focus_set()

    def close(self):
        if self._contributions is not None:
            self._contributions.close()

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
        if self.session_running or self._contributions.busy:
            return
        self._latest_capture = None
        self._contributions.clear_capture()
        self._use_overlay = self.use_overlay_var.get()

        self.active_queues = []
        self.active_eyes = []
        self._attached_queues = []
        self.active_eye_labels = []

        for eye in self.eyes:
            if eye.started():
                q = queue.Queue(maxsize=10)
                camera = eye._effective_camera()
                camera.add_extra_output_queue(q)
                self._attached_queues.append((camera, q))
                self.active_queues.append(q)
                self.active_eyes.append(eye)
                self.active_eye_labels.append("Left" if eye.eye_id.name == "LEFT" else "Right")

        if not self.active_queues:
            self._status_var.set(tr("data_collection.status_no_cameras"))
            return

        self.session_running = True
        self.session_cancel.clear()
        if is_steam_frame():
            # The Frame's CPU can't run the tracking models and record both
            # eyes at 90 fps: pause tracking until the recording ends.
            models_paused_for_recording.set()
            logger.info("Tracking paused while data collection records")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._status_var.set(tr("data_collection.status_starting"))
        self._contributions.capture_started()
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _stop_collection(self):
        self.session_cancel.set()

    def _capture_worker(self):
        try:
            self._run_collection()
        except Exception:
            logger.exception("Capture could not finish")
            self.session_cancel.set()
            self.gui_queue.put(("status", "Recording could not finish. Please try again."))
            self._discard_session_output()
            self._cleanup_session()

    def _run_collection(self):
        # Re-roll on the (unlikely) clash instead of wiping a folder an
        # earlier session left behind: this session only ever deletes the
        # folder it created.
        while True:
            seed = "".join(random.choices(string.ascii_letters + string.digits, k=9))
            output_dir = os.path.join(os.getcwd(), f"{DATA_COLLECTION_VERSION}_{seed}_ETVR_Output")
            if not os.path.exists(output_dir):
                break

        use_overlay = self._use_overlay

        os.makedirs(output_dir)
        self._session_output_dir = output_dir

        # Camera setup is metadata only. NEXT and these captures use raw frames.
        with open(os.path.join(output_dir, "capture_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "schema": "etvr-capture-v1",
                    "image_coordinate_frame": "raw_camera",
                    "eyes": [
                        {
                            "eye": "Left" if eye.eye_id.name == "LEFT" else "Right",
                            "camera_rotation_degrees": int(eye.config.rotation_angle),
                        }
                        for eye in self.eyes
                        if eye.started()
                    ],
                    "dilation_reference": {
                        "target_type": "illumination_phase_only",
                        "backdrop_gray_8bit": {"dim": 24, "bright": 208},
                        "adaptation_seconds": 3,
                        "frames_per_phase": 12,
                    },
                },
                f,
                indent=2,
            )

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
        first_fps = [0.0] * n
        deadline = time.time() + 10
        while any(f is None for f in first_frames) and time.time() < deadline:
            if self.session_cancel.is_set():
                break
            for i in range(n):
                if first_frames[i] is None and not self.active_queues[i].empty():
                    try:
                        frame_data = self.active_queues[i].get_nowait()
                        first_frames[i] = self._prepare_frame(i, frame_data[0])
                        first_fps[i] = float(frame_data[2] or 0.0) if len(frame_data) > 2 else 0.0
                    except queue.Empty:
                        pass
            time.sleep(0.05)

        if any(f is None for f in first_frames) and not self.session_cancel.is_set():
            self.gui_queue.put(("status", tr("data_collection.status_no_frames")))
            self._discard_session_output()
            self._cleanup_session()
            return
        if self.session_cancel.is_set():
            # Stopped during warm-up: a missing first frame would otherwise
            # crash the VideoWriter setup below.
            self.gui_queue.put(("status", tr("data_collection.status_cancelled")))
            self._discard_session_output()
            self._cleanup_session()
            return

        fourcc, _, container = get_best_codec()
        video_writers = []
        # Lock each writer's frame size so we can conform later frames to it.
        # cv2.VideoWriter.write() raises "Unknown C++ exception from OpenCV
        # code" if handed a frame of a different size, and UVC cams under USB
        # bandwidth pressure (especially at 90 fps) do intermittently deliver a
        # differently-sized frame, which previously crashed the capture pass.
        self._video_writer_sizes = []
        for i in range(n):
            h, w = first_frames[i].shape[:2]
            is_color = len(first_frames[i].shape) == 3 and first_frames[i].shape[2] == 3
            fn = os.path.join(
                output_dir, f"{DATA_COLLECTION_VERSION}_{seed}_full_session_{self.active_eye_labels[i]}.{container}"
            )
            # The container's nominal rate: the camera's measured rate (the
            # Steam Frame runs 60-90 fps in a game), else the old fixed 60.
            fps = round(first_fps[i]) if 10 <= first_fps[i] <= 240 else 60
            vw = cv2.VideoWriter(fn, fourcc, fps, (w, h), is_color)
            video_writers.append(vw)
            self._video_writer_sizes.append((w, h))

        recorder = _SessionRecorder(
            self.active_queues,
            self._prepare_frame,
            lambda j, frame: self._write_video_frame(video_writers[j], j, frame),
        )
        self._recorder = recorder
        recorder.start()

        def drain_to_video():
            """The pacing hook every pass still calls between waits. Frames are
            written by the recorder thread, so there is nothing to do here."""

        overlay_proc = None
        udp_sock = None
        cmd_sock = None
        send_cmd = None

        if use_overlay:
            # Tools/ on Windows, Tools/linux/ on Linux (the native runtime folder).
            try:
                overlay_exe = overlay_executable()
            except FileNotFoundError:
                overlay_exe = None

            if overlay_exe is None:
                self.gui_queue.put(("status", tr("data_collection.status_overlay_not_found")))
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
                        _overlay_text(_sock, text)

                    # Widen the capture gaze range beyond the overlay's
                    # conservative defaults (fov.h: coverage 0.70, lateral 30°,
                    # up 15°, down 35°) so the dots sit closer to the edge of
                    # comfortable eye rotation and we collect more eccentric gaze
                    # labels (the model was under-reaching at ~±0.6). These are
                    # the "moderate" caps that remain inside what the eye can reach
                    # without a head turn, so targets stay reliably fixatable
                    # (unreachable dots would mislabel training samples). The
                    # overlay parses these flags for any mode; no rebuild needed.
                    # NOTE: v6 collection therefore defines full gaze at a wider
                    # angle than v5 (1.0 = 36° vs 30° lateral). The per-user app
                    # calibration absorbs that global-scale difference; the ring/
                    # keyword LABELS are version-gated in the trainer (dataset.py)
                    # so v5 captures keep their original scale.
                    overlay_proc = subprocess.Popen(
                        overlay_command(
                            "interactive",
                            "--coverage=0.80",
                            "--max-deg=36",
                            "--max-deg-up=20",
                            "--max-deg-down=40",
                            executable=overlay_exe,
                        ),
                        cwd=os.path.dirname(overlay_exe),
                    )

                    self.gui_queue.put(("status", tr("data_collection.status_waiting_overlay")))
                    ready = False
                    ov_deadline = time.time() + 15
                    while time.time() < ov_deadline and not self.session_cancel.is_set():
                        drain_to_video()
                        try:
                            data, _ = udp_sock.recvfrom(16)
                            (val,) = struct.unpack(">i", data[:4])
                            if val == 255:
                                ready = True
                                break
                        except _socket.timeout:
                            pass

                    if not ready:
                        self.gui_queue.put(("status", tr("data_collection.status_overlay_no_response")))
                        use_overlay = False
                    else:
                        self.gui_queue.put(("status", tr("data_collection.status_overlay_connected")))
                except Exception as e:
                    self.gui_queue.put(("status", tr("data_collection.status_overlay_failed", error=e)))
                    use_overlay = False

        prompts_to_run = [
            (dot_code, label, key) for dot_code, label, key in PROMPT_DATA if not (use_overlay and dot_code is not None)
        ]
        total_prompts = len(prompts_to_run)

        try:
            for capture_count, (dot_code, label, key) in enumerate(prompts_to_run):
                if self.session_cancel.is_set():
                    break

                self.gui_queue.put(
                    (
                        "status",
                        tr(
                            "data_collection.status_speaking",
                            text=prompt_text(key),
                            current=capture_count + 1,
                            total=total_prompts,
                        ),
                    )
                )
                self.gui_queue.put(("progress", (capture_count + 1, total_prompts)))

                if use_overlay:
                    send_text(prompt_text(key))
                speech_done = say(key)
                while not speech_done.is_set():
                    if self.session_cancel.is_set():
                        break
                    drain_to_video()
                    time.sleep(0.01)

                if not self.session_cancel.is_set():
                    speech_done = say("now")
                    t0 = time.time()
                    while (time.time() - t0 < 2.0) or not speech_done.is_set():
                        if self.session_cancel.is_set():
                            break
                        drain_to_video()
                        time.sleep(0.01)

                if self.session_cancel.is_set():
                    break

                self.gui_queue.put(("status", tr("data_collection.status_capturing")))

                prompt_frames = [None] * n
                frame_numbers = [None] * n
                for j in range(n):
                    try:
                        prompt_frames[j], frame_numbers[j] = recorder.next_frame(j, timeout=5.0)
                    except queue.Empty:
                        pass

                for j in range(n):
                    if frame_numbers[j] is not None:
                        with open(timestamp_files[j], "a") as f:
                            f.write(f"{frame_numbers[j]} #{label}#\n")

                clean = label.lower().replace(" ", "_")
                for j in range(n):
                    if prompt_frames[j] is not None:
                        img_fn = os.path.join(
                            output_dir,
                            f"{DATA_COLLECTION_VERSION}_{seed}_{self.active_eye_labels[j]}_{capture_count + 1:02d}_{clean}.png",
                        )
                        cv2.imwrite(img_fn, prompt_frames[j])

                if use_overlay:
                    send_cmd(98)
                speech_done = say("captured")
                while not speech_done.is_set():
                    if self.session_cancel.is_set():
                        break
                    drain_to_video()
                    time.sleep(0.01)

            base_idx = len(prompts_to_run)
            if use_overlay and not self.session_cancel.is_set():
                base_idx = self._run_overlay_passes(
                    seed,
                    output_dir,
                    n,
                    video_writers,
                    timestamp_files,
                    drain_to_video,
                    base_idx,
                    udp_sock,
                    send_cmd,
                    cmd_sock,
                )
            if use_overlay and not self.session_cancel.is_set():
                base_idx = self._run_headset_shift_pass(
                    seed,
                    output_dir,
                    n,
                    video_writers,
                    timestamp_files,
                    drain_to_video,
                    base_idx,
                    udp_sock,
                    cmd_sock,
                )
            if use_overlay and not self.session_cancel.is_set():
                base_idx = self._run_dilation_reference_pass(
                    seed,
                    output_dir,
                    n,
                    video_writers,
                    timestamp_files,
                    drain_to_video,
                    base_idx,
                    udp_sock,
                    cmd_sock,
                )
            # Blink-at-dot: mid-blink frames with a held-neutral brow (the
            # anti-"blink wiggles eyebrow" pass). Overlay pins the dot; without
            # the overlay a center-gaze TTS variant runs instead.
            if not self.session_cancel.is_set():
                if use_overlay:
                    base_idx = self._run_blinkdot_pass(
                        seed,
                        output_dir,
                        n,
                        video_writers,
                        timestamp_files,
                        drain_to_video,
                        base_idx,
                        udp_sock,
                        send_cmd,
                        cmd_sock,
                    )
                else:
                    base_idx = self._run_blink_pass_no_overlay(
                        seed,
                        output_dir,
                        n,
                        video_writers,
                        timestamp_files,
                        drain_to_video,
                        base_idx,
                    )
            # Closed-eye roam: closed-lid appearance under a moving face/brow.
            if not self.session_cancel.is_set():
                base_idx = self._run_closed_roam_pass(
                    seed,
                    output_dir,
                    n,
                    video_writers,
                    timestamp_files,
                    drain_to_video,
                    base_idx,
                    use_overlay,
                    cmd_sock,
                )

        except Exception as e:
            self.session_cancel.set()
            logger.exception("Data collection aborted by an unexpected error")
            self.gui_queue.put(("status", tr("data_collection.status_error", error=e)))
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

            recorder.stop()
            self._recorder = None
            for vw in video_writers:
                vw.release()

            if not self.session_cancel.is_set():
                zip_name = _zip_output(seed, output_dir)
                self.gui_queue.put(("capture_ready", os.path.abspath(zip_name)))
                # The ZIP sits beside the folder in cwd, so this only drops
                # the working copy.
                self._discard_session_output()
                say("done").wait()
                self.gui_queue.put(("status", tr("data_collection.status_done", path=zip_name)))
            else:
                # Cancelled or failed: nothing is handed on, so don't leave
                # the full AVI and PNGs behind in cwd.
                self._discard_session_output()
                self.gui_queue.put(("status", tr("data_collection.status_cancelled")))

            self._cleanup_session()

    def _prepare_frame(self, j, frame):
        """Eye ``j``'s image from a captured frame: its half of a bigscreen
        frame, and BGR rather than BGRA."""
        if self.active_eyes[j].settings.gui_setup_mode == "bigscreen":
            mid = frame.shape[1] // 2
            frame = frame[:, :mid] if self.active_eyes[j].eye_id.name == "LEFT" else frame[:, mid:]
        if len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame

    def _write_video_frame(self, writer, j, frame):
        """Write a frame to the full-session VideoWriter, conformed so the write
        can't throw. cv2.VideoWriter.write() raises "Unknown C++ exception from
        OpenCV code" when the frame size differs from the writer's locked
        (w, h), which happens when the camera briefly renegotiates resolution
        under USB-bandwidth pressure (common at 90 fps), and is also unhappy
        with the non-contiguous views the bigscreen split (frame[:, mid:])
        produces. Resize to the locked size and/or make contiguous, and swallow
        any residual write failure so one bad frame never aborts the pass."""
        try:
            w, h = self._video_writer_sizes[j]
            fh, fw = frame.shape[:2]
            if (fw, fh) != (w, h):
                frame = cv2.resize(frame, (w, h))
            elif not frame.flags["C_CONTIGUOUS"]:
                frame = frame.copy()
            writer.write(frame)
        except Exception:
            logger.exception("Dropped a full-session video frame for eye index %d", j)

    def _do_overlay_capture(self, seed, output_dir, n, video_writers, timestamp_files, label, idx, image_dir=None):
        frames = [None] * n
        frame_nums = [None] * n
        for j in range(n):
            try:
                frames[j], frame_nums[j] = self._recorder.next_frame(j, timeout=5.0)
            except queue.Empty:
                pass
            except Exception:
                # A transient grab/split/write failure for one eye must not drop
                # the whole pass. Log the traceback (this is the only place the
                # real cause of an aborted session would surface) and skip just
                # this eye's capture for this point.
                logger.exception(
                    "Overlay capture failed for eye index %d (label=%s); skipping this frame",
                    j,
                    label,
                )

        for j in range(n):
            if frame_nums[j] is not None:
                with open(timestamp_files[j], "a") as f:
                    f.write(f"{frame_nums[j]} #{label}#\n")

        for j in range(n):
            if frames[j] is not None:
                img_fn = os.path.join(
                    image_dir or output_dir,
                    f"{DATA_COLLECTION_VERSION}_{seed}_{self.active_eye_labels[j]}_{idx + 1:02d}_{label}.png",
                )
                cv2.imwrite(img_fn, frames[j])

    def _run_overlay_passes(
        self,
        seed,
        output_dir,
        n,
        video_writers,
        timestamp_files,
        drain_to_video,
        base_idx,
        udp_sock,
        send_cmd,
        cmd_sock,
    ):
        overlay_idx = base_idx
        total_passes = len(OVERLAY_PASSES)

        for pass_num, (pass_cmd, label_prefix, key, n_jitter) in enumerate(OVERLAY_PASSES):
            if self.session_cancel.is_set():
                break

            # Isolate each pass: a transient error (frame grab, socket, codec)
            # in one pass must NOT abort the whole multi-minute session. Before
            # this, any exception here propagated to _run_collection's handler,
            # which silently played "you are done" mid-run, e.g. completing
            # gaze + squint then stopping before the widen/eyebrow passes. Log
            # the full traceback and move on to the next pass instead.
            try:
                self.gui_queue.put(
                    (
                        "status",
                        tr(
                            "data_collection.status_overlay_pass",
                            current=pass_num + 1,
                            total=total_passes,
                            text=prompt_text(f"pass_{key}"),
                        ),
                    )
                )
                self.gui_queue.put(("progress", (pass_num + 1, total_passes)))
                # Card first, then the voice: the overlay keeps this text when
                # the pass command below starts the dots.
                _overlay_text(cmd_sock, prompt_text(f"panel_{key}"))
                done = say(f"pass_{key}")
                while not done.is_set():
                    if self.session_cancel.is_set():
                        return overlay_idx
                    drain_to_video()
                    time.sleep(0.01)

                # Clear any datagrams buffered while we were speaking (e.g. a
                # leftover end-of-pass `19` from the previous pass). Otherwise
                # phase 1 below reads that stale signal first, breaks with
                # phase1_done=False, and silently skips this pass's capture.
                _drain_udp_socket(udp_sock)
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
                    (value,) = struct.unpack(">i", data[:4])
                    if 0 <= value <= 8:
                        label = f"{label_prefix}_{OVERLAY_POINT_NAMES[value]}"
                        self._do_overlay_capture(
                            seed, output_dir, n, video_writers, timestamp_files, label, overlay_idx
                        )
                        overlay_idx += 1
                    elif value == 10:  # overlay entered jittered-grid phase
                        phase1_done = True
                        break
                    elif value == 19:  # safety fallback
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
                        self._do_overlay_capture(
                            seed, output_dir, n, video_writers, timestamp_files, label, overlay_idx
                        )
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
            except Exception:
                logger.exception(
                    "Overlay pass %d/%d (%s) failed; skipping to the next pass",
                    pass_num + 1,
                    total_passes,
                    label_prefix,
                )
                self.gui_queue.put(
                    (
                        "status",
                        tr(
                            "data_collection.status_pass_errored",
                            current=pass_num + 1,
                            total=total_passes,
                            label=label_prefix,
                        ),
                    )
                )
                continue

        return overlay_idx

    def _burst_capture(
        self, seed, output_dir, n, video_writers, timestamp_files, drain_to_video, label, idx, frames, interval
    ):
        """Capture `frames` snapshots ~`interval` seconds apart under one label.
        Returns the next free capture index. Mirrors the headset-shift pass's
        cadence (drain, wait, drain, capture) so full-session video keeps
        flowing between snapshots."""
        for _ in range(frames):
            if self.session_cancel.is_set():
                break
            drain_to_video()
            time.sleep(max(interval - 0.02, 0.0))
            drain_to_video()
            self._do_overlay_capture(seed, output_dir, n, video_writers, timestamp_files, label, idx)
            idx += 1
        return idx

    def _run_blinkdot_pass(
        self,
        seed,
        output_dir,
        n,
        video_writers,
        timestamp_files,
        drain_to_video,
        base_idx,
        udp_sock,
        send_cmd,
        cmd_sock,
    ):
        """Blink-at-dot: pin the overlay dot at 4 jittered positions; the user
        blinks repeatedly at each while holding a neutral brow (burst capture).
        Falls back gracefully if the overlay exe predates cmd 113 (no ack 21):
        the pass is skipped rather than capturing dot-less mislabeled gaze."""
        overlay_idx = base_idx
        self.gui_queue.put(("status", tr("data_collection.status_blinkdot")))

        _overlay_text(cmd_sock, prompt_text("blinkdot_panel"))
        speech_done = say("blinkdot")
        while not speech_done.is_set():
            if self.session_cancel.is_set():
                return overlay_idx
            drain_to_video()
            time.sleep(0.01)

        for gx, gy in _blinkdot_positions(seed):
            if self.session_cancel.is_set():
                break
            _drain_udp_socket(udp_sock)
            cmd_sock.sendto(struct.pack(">iff", OVERLAY_CMD_PIN_DOT, gx, gy), ("127.0.0.1", OVERLAY_CMD_PORT))

            # Wait for the pin ack (21). An old overlay exe ignores 113 and
            # never acks so skip the pass instead of labeling gaze at a dot the
            # user cannot see.
            pinned = False
            deadline = time.time() + 2.0
            while time.time() < deadline and not self.session_cancel.is_set():
                drain_to_video()
                try:
                    data, _ = udp_sock.recvfrom(16)
                except _socket.timeout:
                    continue
                if len(data) >= 4 and struct.unpack(">i", data[:4])[0] == OVERLAY_SIG_PINNED:
                    pinned = True
                    break
            if not pinned:
                logger.warning("Blinkdot pass: no pin ack from overlay (old exe?); skipping pass.")
                self.gui_queue.put(("status", tr("data_collection.status_blinkdot_skipped")))
                return overlay_idx

            # Give the dot its appear/shrink animation + the user a beat to
            # acquire it and start blinking.
            t0 = time.time()
            while time.time() - t0 < 1.2:
                if self.session_cancel.is_set():
                    break
                drain_to_video()
                time.sleep(0.01)

            label = f"blinkdot_x{gx:+.3f}_y{gy:+.3f}"
            overlay_idx = self._burst_capture(
                seed,
                output_dir,
                n,
                video_writers,
                timestamp_files,
                drain_to_video,
                label,
                overlay_idx,
                BLINKDOT_BURST_FRAMES,
                BLINKDOT_BURST_INTERVAL,
            )

        cmd_sock.sendto(struct.pack(">i", OVERLAY_CMD_UNPIN), ("127.0.0.1", OVERLAY_CMD_PORT))
        send_cmd(98)  # clear overlay text
        return overlay_idx

    def _run_blink_pass_no_overlay(self, seed, output_dir, n, video_writers, timestamp_files, drain_to_video, base_idx):
        """No-overlay blink burst: fixate straight ahead and blink repeatedly.
        Center-gaze-only version of the blinkdot pass (label carries 0,0)."""
        self.gui_queue.put(("status", tr("data_collection.status_blinkdot")))
        speech_done = say("blink_no_overlay")
        while not speech_done.is_set():
            if self.session_cancel.is_set():
                return base_idx
            drain_to_video()
            time.sleep(0.01)
        return self._burst_capture(
            seed,
            output_dir,
            n,
            video_writers,
            timestamp_files,
            drain_to_video,
            "blinkdot_x+0.000_y+0.000",
            base_idx,
            BLINKDOT_BURST_FRAMES * 2,
            BLINKDOT_BURST_INTERVAL,
        )

    def _run_closed_roam_pass(
        self, seed, output_dir, n, video_writers, timestamp_files, drain_to_video, base_idx, use_overlay, cmd_sock
    ):
        """Closed-eye roam: eyes shut, move face/brows/cheeks around (burst).
        Works with or without the overlay (TTS carries the instruction)."""
        self.gui_queue.put(("status", tr("data_collection.status_closed_roam")))
        if use_overlay and cmd_sock is not None:
            _overlay_text(cmd_sock, prompt_text("closed_roam_panel"))
        speech_done = say("closed_roam")
        while not speech_done.is_set():
            if self.session_cancel.is_set():
                return base_idx
            drain_to_video()
            time.sleep(0.01)

        t0 = time.time()
        while time.time() - t0 < 0.5:
            if self.session_cancel.is_set():
                return base_idx
            drain_to_video()
            time.sleep(0.01)

        base_idx = self._burst_capture(
            seed,
            output_dir,
            n,
            video_writers,
            timestamp_files,
            drain_to_video,
            "closed_roam",
            base_idx,
            CLOSED_ROAM_FRAMES,
            CLOSED_ROAM_INTERVAL,
        )

        if use_overlay and cmd_sock is not None:
            cmd_sock.sendto(struct.pack(">i", 98), ("127.0.0.1", OVERLAY_CMD_PORT))
        return base_idx

    def _run_headset_shift_pass(
        self, seed, output_dir, n, video_writers, timestamp_files, drain_to_video, base_idx, udp_sock, cmd_sock
    ):
        overlay_idx = base_idx
        self.gui_queue.put(("status", tr("data_collection.status_headset_shift")))

        cmd_sock.sendto(struct.pack(">i", 120), ("127.0.0.1", OVERLAY_CMD_PORT))
        _overlay_text(cmd_sock, prompt_text("headset_shift_panel"))
        speech_done = say("headset_shift")

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
            self._do_overlay_capture(seed, output_dir, n, video_writers, timestamp_files, "hshift_center", overlay_idx)
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
            (val,) = struct.unpack(">i", data[:4])
            if val == 19:
                break

        return overlay_idx

    def _run_dilation_reference_pass(
        self, seed, output_dir, n, video_writers, timestamp_files, drain_to_video, base_idx, udp_sock, cmd_sock
    ):
        """Collect fixation-matched dim/bright references, not diameter labels."""
        image_dir = os.path.join(output_dir, "DILATION_REFERENCE")

        def command(value, message=None):
            payload = struct.pack(">i", value)
            if message is not None:
                payload += message.encode("utf-8")
            cmd_sock.sendto(payload, ("127.0.0.1", OVERLAY_CMD_PORT))

        def wait_brightness_ack():
            deadline = time.time() + 2.5
            while time.time() < deadline and not self.session_cancel.is_set():
                drain_to_video()
                try:
                    data, _ = udp_sock.recvfrom(16)
                except _socket.timeout:
                    continue
                if len(data) >= 4 and struct.unpack(">i", data[:4])[0] == 22:
                    return True
            return False

        try:
            command(120)  # Center fixation target.
            command(OVERLAY_CMD_TEXT, prompt_text("center_dot_panel"))
            for code, phase in ((130, "dim"), (131, "bright")):
                if self.session_cancel.is_set():
                    break
                command(code)
                if not wait_brightness_ack():
                    logger.warning("Overlay does not support dilation illumination; skipping reference pass")
                    break
                os.makedirs(image_dir, exist_ok=True)
                until = time.time() + 3.0
                while time.time() < until and not self.session_cancel.is_set():
                    drain_to_video()
                    time.sleep(0.01)
                for _ in range(12):
                    if self.session_cancel.is_set():
                        break
                    drain_to_video()
                    time.sleep(0.18)
                    self._do_overlay_capture(
                        seed,
                        output_dir,
                        n,
                        video_writers,
                        timestamp_files,
                        f"dilation_{phase}",
                        base_idx,
                        image_dir=image_dir,
                    )
                    base_idx += 1
        finally:
            command(132)  # Restore neutral illumination for subsequent passes.
            command(121)
        return base_idx

    def _discard_session_output(self):
        """Remove this session's working folder. Only the path _run_collection
        created is touched, never the finished ZIP next to it."""
        output_dir, self._session_output_dir = self._session_output_dir, None
        if output_dir:
            shutil.rmtree(output_dir, ignore_errors=True)

    def _cleanup_session(self):
        # Detach exactly the queues _start_collection attached, from the camera
        # each was attached to. Indexing self.eyes by queue position missed the
        # left eye's queue when it ran alone, leaving the camera copying every
        # frame into an orphan queue for each later recording.
        attached, self._attached_queues = self._attached_queues, []
        for camera, q in attached:
            try:
                camera.remove_extra_output_queue(q)
            except Exception:
                logger.exception("Could not detach capture output queue")
        self.active_queues = []
        self.active_eyes = []
        if models_paused_for_recording.is_set():
            models_paused_for_recording.clear()
            logger.info("Tracking resumed after data collection")
        self.gui_queue.put(("session_done", None))

    def _poll_gui_queue(self):
        while not self.gui_queue.empty():
            try:
                msg_type, data = self.gui_queue.get_nowait()
                if msg_type == "status":
                    self._status_var.set(data)
                elif msg_type == "progress":
                    self._contributions.capture_progress_update(*data)
                elif msg_type == "capture_ready":
                    if not self.session_cancel.is_set():
                        self._latest_capture = data
                elif msg_type == "session_done":
                    self.session_running = False
                    if self.session_cancel.is_set():
                        self._latest_capture = None
                    self._contributions.capture_stopped(self._latest_capture)
            except queue.Empty:
                break
        self.window.after(50, self._poll_gui_queue)
