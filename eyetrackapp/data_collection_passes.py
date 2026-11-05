"""The overlay passes of a data collection session: where each dot goes and
how the overlay is driven through them.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import logging
import os
import queue
import random
import socket as _socket
import struct
import time

import cv2

from data_collection_tts import prompt_text, say
from localization import tr

DATA_COLLECTION_VERSION = "v6"

logger = logging.getLogger(__name__)

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


class OverlayPassesMixin:
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
