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

from localization import tr
from utils.overlay_launch import OverlaySession
from frame_eye import is_steam_frame, models_paused_for_recording
from data_collection_tts import prompt_text, say
from data_collection_passes import (
    DATA_COLLECTION_VERSION,
    OVERLAY_CMD_PORT,
    OverlayPassesMixin,
    _overlay_text,
)

logger = logging.getLogger(__name__)


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
            logger.debug("Codec probe failed for %s", codec, exc_info=True)

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


class DataCollectionWindow(OverlayPassesMixin):
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

        overlay = None
        udp_sock = None
        cmd_sock = None
        send_cmd = None

        if use_overlay:
            try:
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
                overlay = OverlaySession(
                    "interactive",
                    "--coverage=0.80",
                    "--max-deg=36",
                    "--max-deg-up=20",
                    "--max-deg-down=40",
                ).start()
                udp_sock = overlay.sock
                udp_sock.settimeout(1.0)
                cmd_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)

                def _send_cmd(val, _sock=cmd_sock):
                    _sock.sendto(struct.pack(">i", val), ("127.0.0.1", OVERLAY_CMD_PORT))

                send_cmd = _send_cmd

                def send_text(text, _sock=cmd_sock):
                    _overlay_text(_sock, text)

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
                        if overlay.process.poll() is not None:
                            break

                if not ready:
                    self.gui_queue.put(("status", tr("data_collection.status_overlay_no_response")))
                    use_overlay = False
                else:
                    self.gui_queue.put(("status", tr("data_collection.status_overlay_connected")))
            except FileNotFoundError:
                self.gui_queue.put(("status", tr("data_collection.status_overlay_not_found")))
                use_overlay = False
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
                    overlay.finish()
                except OSError as e:
                    logger.warning("Could not ask the overlay to quit: %s", e)
            if cmd_sock is not None:
                cmd_sock.close()
            if overlay is not None:
                overlay.close()

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
