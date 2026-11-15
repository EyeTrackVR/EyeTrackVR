"""
First-run setup wizard: language -> headset -> cameras -> check -> done.

The helpers at the top are Tk-free so they can be unit tested. SetupWizard is a
page of the main window (WizardPage puts it in place of the other pages) that
drives the app through a narrow adapter: AppAdapter wraps the real AppUI
(eyetrackapp.py) and reuses its own code paths (the setup mode selector, Scan,
Connect and cropping mode), and tests pass a fake with the same methods.
Calibration is left to the Tracking page (or the SteamVR dashboard) after setup.

Every background result reaches the wizard on the Tk thread and is ignored once
the wizard is closed; nothing here blocks the Tk thread on camera or network I/O.
"""

from __future__ import annotations

import logging
import queue
import re
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk

from frame_eye import FRAME_LEFT_SOURCE, FRAME_RIGHT_SOURCE, is_frame_capture_source, is_steam_frame
from localization import tr

logger = logging.getLogger(__name__)

STEP_LANGUAGE, STEP_HEADSET, STEP_CAMERAS, STEP_CHECK, STEP_DONE = range(5)
STEP_COUNT = 5
SIDES = ("left", "right")

# Wizard headset choices that are not main-window setup modes: a PSVR2 (or
# other commercial headset) shows both eyes in one camera picture like the
# Bigscreen Beyond, so it runs in Bigscreen mode with the PSVR NEXT model.
_HEADSET_APP_MODE = {"psvr": "bigscreen"}
# The NEXT model family each headset choice selects (gui_model_variant).
HEADSET_MODEL_VARIANT = {"etvr": "ETVR", "bigscreen": "BSB", "psvr": "PSVR"}

# A scan that never reports back must not leave Rescan disabled for good.
_SCAN_WATCHDOG_MS = 20000
_POLL_MS = 500
_FRAME_WAIT_MS = 5000

# Tracker flags in the order the bug report lists them.
_TRACKERS = ("NEXT", "LEAP", "DADDY", "AHRAC", "RANSAC3D", "AHSF", "HSRAC", "HSF")
_SIDE_RES = {side: re.compile(rf"(?<![a-z]){side}(?![a-z])") for side in SIDES}
_BIGSCREEN_RE = re.compile(r"bigeye|bigscreen|beyond")
_KIND_ORDER = {"network": 0, "serial": 1, "uvc": 2, "frame": 3, "other": 4}


# ---------------------------------------------------------------------------
# Tk-free logic
# ---------------------------------------------------------------------------


def _is_set(source) -> bool:
    # UVC index 0 is a real source.
    return source is not None and str(source).strip() != ""


def has_capture_source(config) -> bool:
    return any(_is_set(getattr(eye, "capture_source", None)) for eye in (config.left_eye, config.right_eye))


def first_run_action(config) -> str:
    """Returns "open" for a new user, "mark_done" for someone upgrading with
    cameras already set up (they never see the wizard unasked), else "none"."""
    if getattr(config.settings, "gui_setup_wizard_done", False):
        return "none"
    if has_capture_source(config):
        return "mark_done"
    return "open"


def should_auto_open(config) -> bool:
    return first_run_action(config) == "open"


def run_first_run_check(root, config, open_wizard, delay_ms: int | None = None) -> str:
    """Call once at startup, before the first page applies the camera fields
    (that writes capture sources to config). Opens the wizard (right away by
    default, so the window first shows on the wizard page; after delay_ms when
    given), or quietly marks an existing setup as done."""
    action = first_run_action(config)
    if action == "mark_done":
        config.settings.gui_setup_wizard_done = True
        try:
            config.save()
        except Exception:
            logger.warning("Could not save the setup wizard state", exc_info=True)
    elif action == "open":

        def _open():
            try:
                open_wizard()
            except Exception:
                logger.exception("Could not open the setup wizard")

        if delay_ms is None:
            _open()
        else:
            try:
                root.after(delay_ms, _open)
            except tk.TclError:
                pass
    return action


@dataclass(frozen=True)
class Source:
    label: str  # what the user sees
    value: str  # the capture source string the app stores
    kind: str  # "network", "serial", "uvc", "frame" or "other"


def source_kind(value) -> str:
    text = str(value).strip()
    if text.startswith("uvc:") or text.isdigit():
        return "uvc"
    if text.upper().startswith("COM") or text.startswith("/dev"):
        return "serial"
    if is_frame_capture_source(text):
        return "frame"
    if "://" in text:
        return "network"
    return "other"


def sources_from_scan(source_map: dict) -> list[Source]:
    """The scan's {label: capture source}, network trackers first, then serial,
    then webcams (the order of the main window's dropdown)."""
    found = [Source(str(label), str(value), source_kind(value)) for label, value in source_map.items() if label]
    return sorted(found, key=lambda s: _KIND_ORDER[s.kind])


def side_hint(source: Source) -> str | None:
    """The side the name says (ETVR-Left.local -> "left"), else None."""
    text = f"{source.label} {source.value}".lower()
    hits = [side for side in SIDES if _SIDE_RES[side].search(text)]
    return hits[0] if len(hits) == 1 else None


@dataclass(frozen=True)
class Assignment:
    left: str | None
    right: str | None
    sure: bool  # False: a guess the user should check


def proposed_assignment(mode: str, sources: list[Source]) -> Assignment:
    """Which found source goes to which eye, when that can be told."""
    if mode == "frame":
        return Assignment(FRAME_LEFT_SOURCE, FRAME_RIGHT_SOURCE, True)
    if not sources:
        return Assignment(None, None, False)
    if mode == "bigscreen":
        # One camera sees both eyes.
        named = [s for s in sources if _BIGSCREEN_RE.search(s.label.lower())]
        if len(named) == 1:
            return Assignment(named[0].value, named[0].value, True)
        if len(sources) == 1:
            return Assignment(sources[0].value, sources[0].value, False)
        return Assignment(None, None, False)
    lefts = [s for s in sources if side_hint(s) == "left"]
    rights = [s for s in sources if side_hint(s) == "right"]
    if len(lefts) == 1 and len(rights) == 1:
        return Assignment(lefts[0].value, rights[0].value, True)
    # EyeTrackVR trackers (network/serial) over any other webcam on the PC.
    pool = [s for s in sources if s.kind in ("network", "serial")] or list(sources)
    if len(pool) == 2:
        first, second = pool
        if side_hint(first) == "right" or side_hint(second) == "left":
            first, second = second, first
        return Assignment(first.value, second.value, False)
    if len(pool) == 1:
        only = pool[0]
        if side_hint(only) == "right":
            return Assignment(None, only.value, True)
        return Assignment(only.value, None, side_hint(only) == "left")
    return Assignment(
        lefts[0].value if len(lefts) == 1 else None,
        rights[0].value if len(rights) == 1 else None,
        False,
    )


def app_mode(headset: str) -> str:
    """The main window's setup mode for a wizard headset choice."""
    return _HEADSET_APP_MODE.get(headset, headset)


def tracker_needs_crop(settings) -> bool:
    """NEXT runs on the raw frame; every other tracker needs an eye crop."""
    return not (bool(getattr(settings, "gui_NEXT", False)) or bool(getattr(settings, "gui_NEXT_BSB", False)))


def crop_missing(eye_config) -> bool:
    # The tracker waits for a crop while either side is 0 (eye_processor.run).
    return eye_config.roi_window_w <= 0 or eye_config.roi_window_h <= 0


def full_frame_roi(shape, mode: str = "etvr", side: str = "left") -> tuple[int, int, int, int]:
    """(x, y, w, h) covering the whole picture; in Bigscreen mode this eye's half,
    as the Bigscreen auto-crop does."""
    height, width = int(shape[0]), int(shape[1])
    if height <= 0 or width <= 0:
        raise ValueError(f"empty frame {shape!r}")
    if mode == "bigscreen":
        half = width // 2
        return (0, 0, half, height) if side == "left" else (half, 0, width - half, height)
    return (0, 0, width, height)


def tracker_name(settings) -> str:
    if getattr(settings, "gui_NEXT_BSB", False):
        return "NEXT"
    for name in _TRACKERS:
        if getattr(settings, "gui_" + name, False):
            return name
    return "NEXT"


def source_label(value) -> str:
    """A short name for a stored capture source (the camera name for uvc:Name@Address)."""
    text = str(value)
    if text.startswith("uvc:"):
        from camera_enum import parse_uvc_named_source

        name, _address = parse_uvc_named_source(text)
        return name or text
    return text


def _mode_texts(mode: str) -> tuple[str, str]:
    if mode == "bigscreen":
        return tr("wizard.mode_bigscreen"), tr("wizard.mode_bigscreen_desc")
    if mode == "psvr":
        return tr("wizard.mode_psvr"), tr("wizard.mode_psvr_desc")
    if mode == "frame":
        return tr("tracking.setup_frame"), tr("wizard.mode_frame_desc")
    return tr("wizard.mode_etvr"), tr("wizard.mode_etvr_desc")


def language_label(language: dict) -> str:
    """The native name, with the English name beside it when they differ."""
    native = language.get("native_name") or language.get("code", "")
    english = language.get("name") or ""
    return native if not english or english == native else f"{native} ({english})"


# ---------------------------------------------------------------------------
# Adapter over the real main window
# ---------------------------------------------------------------------------


class AppAdapter:
    """What the wizard needs from AppUI, routed through AppUI's own methods."""

    def __init__(self, app, config, eyes):
        self.app = app
        self.config = config
        # eyes is [right, left], as in eyetrackapp.main().
        self._eyes = {"left": eyes[1], "right": eyes[0]}

    @property
    def settings(self):
        return self.config.settings

    @property
    def dpi_scale(self) -> float:
        return float(getattr(self.app, "_dpi_scale", 1.0) or 1.0)

    def languages(self) -> list[dict]:
        from localization import available_languages

        return available_languages()

    def get_language(self) -> str:
        return getattr(self.settings, "gui_language", None) or "en"

    def set_language(self, code: str) -> None:
        """Save the language and switch the text catalog, so the wizard can be
        rebuilt in it. The rest of the window keeps its text until a restart."""
        from localization import init_localization

        if self.get_language() != code:
            self.config.update({"gui_language": code}, save=True)
        init_localization(code)

    def language_needs_restart(self) -> bool:
        """The main window was built in another language than the saved one."""
        return getattr(self.app, "ui_language", self.get_language()) != self.get_language()

    def modes(self) -> list[str]:
        # Steam Frame is only offered on the headset itself (as in the main window).
        return ["etvr", "bigscreen", "psvr"] + (["frame"] if is_steam_frame() else [])

    def get_mode(self) -> str:
        mode = self.app.mode_var.get()
        variant = str(getattr(self.settings, "gui_model_variant", "") or "").upper()
        if mode == "bigscreen" and variant.startswith("PSVR"):
            return "psvr"
        return mode

    def set_mode(self, mode: str) -> None:
        target = app_mode(mode)
        if self.app.mode_var.get() != target:
            self.app.mode_var.set(target)
            self.app.on_mode_change()
        variant = HEADSET_MODEL_VARIANT.get(mode)
        if variant is None:
            return
        # The headset picked here is the model choice. PSVR is never picked by
        # the setup mode on its own, so it is kept as a manual choice;
        # ETVR/BSB go back to following the setup mode.
        settings = self.settings
        settings.gui_model_variant_user_set = mode == "psvr"
        if getattr(settings, "gui_model_variant", None) != variant:
            self.config.update({"gui_model_variant": variant}, save=True)
        else:
            self.config.save()

    def scan(self, on_update) -> None:
        self.app.scan_sources(on_update=on_update)

    def current_sources(self) -> tuple:
        return self.config.left_eye.capture_source, self.config.right_eye.capture_source

    def apply_sources(self, left, right) -> None:
        # Show the scan's friendly label in the main window where there is one.
        labels = {value: label for label, value in self.app._source_display_map.items()}
        for var, value in ((self.app.left_camera_var, left), (self.app.right_camera_var, right)):
            text = "" if not _is_set(value) else str(value)
            var.set(labels.get(text, text))
        self.app.apply_camera_inputs()

    def eye_config(self, side: str):
        return self._eyes[side].config

    def eye_state(self, side: str) -> str:
        eye = self._eyes[side]
        if not _is_set(eye.config.capture_source):
            return "none"
        if not eye.started():
            return "connecting"
        status = eye._effective_camera_status()
        return {"CONNECTED": "connected", "DISCONNECTED": "disconnected"}.get(status.name, "connecting")

    def any_eye_running(self) -> bool:
        return any(eye.started() for eye in self._eyes.values())

    def request_frame_shape(self, side: str, callback) -> None:
        """callback((h, w, ...)) with the next picture's shape, or callback(None)
        after a few seconds without one. Taps the camera like cropping mode does."""
        camera = self._eyes[side]._effective_camera()
        tap: queue.Queue = queue.Queue(maxsize=1)
        camera.set_extra_output_queues([*camera._extra_output_queues, tap])
        root = self.app.root
        remaining = [_FRAME_WAIT_MS // 100]

        def _untap():
            camera.set_extra_output_queues([q for q in camera._extra_output_queues if q is not tap])

        def _poll():
            try:
                image = tap.get_nowait()[0]
            except queue.Empty:
                remaining[0] -= 1
                if remaining[0] > 0:
                    try:
                        root.after(100, _poll)
                        return
                    except tk.TclError:
                        _untap()
                        return
                _untap()
                callback(None)
                return
            _untap()
            callback(tuple(image.shape))

        try:
            root.after(100, _poll)
        except tk.TclError:
            _untap()

    def set_roi(self, side: str, roi) -> None:
        eye = self._eyes[side]
        cfg = eye.config
        cfg.roi_window_x, cfg.roi_window_y, cfg.roi_window_w, cfg.roi_window_h = (int(v) for v in roi)
        # The crop box redraws from config the next time cropping mode opens.
        for attr in ("xy0", "xy1", "cr", "ca", "roi_size"):
            setattr(eye, attr, None)
        self.config.save()

    def open_crop_mode(self) -> None:
        # Leaving the wizard page pauses the wizard (WizardPage.sync).
        self.app.show_page("tracking")
        self.app._on_global_roi_mode()

    def leave_crop_mode(self) -> None:
        # Tracking waits while an eye is in cropping mode; the crop box is saved
        # on every mouse release, so switching back keeps it.
        if any(getattr(eye, "in_roi_mode", False) for eye in self._eyes.values()):
            self.app._on_global_tracking_mode()

    def show_tracking_page(self) -> None:
        self.app.show_page("tracking")

    def mark_done(self) -> None:
        self.config.settings.gui_setup_wizard_done = True
        self.config.save()


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


class SetupWizard:
    MUTED = "#9a9a9a"
    # The content column: a comfortable reading width, centred on wide windows.
    COLUMN_WIDTH = 680
    PADDING = 24
    MIN_WRAP = 200

    def __init__(self, parent, adapter):
        """Builds the page into parent (not packed: WizardPage shows and hides it)."""
        self.adapter = adapter
        self.parent = parent
        self.step = STEP_LANGUAGE
        # Hidden without ending setup; resume() shows the same step again.
        self.paused = False
        self._closed = False
        self._after_ids: set[str] = set()
        self._scan_gen = 0
        self._scanning = False
        self._scanned_mode: str | None = None
        self._found: list[Source] = []
        self._label_to_value: dict[str, str] = {}
        self._autofilled: tuple[str, str] | None = None
        self._guessed = False
        self._crop_busy = 0
        self._crop_state = None
        scale = getattr(adapter, "dpi_scale", 1.0) or 1.0
        self._padding = round(self.PADDING * scale)
        self._column_width = round(self.COLUMN_WIDTH * scale)
        self._wrap = self._column_width - 2 * self._padding
        # (label, share of the column, pixels taken beside it): rewrapped on resize.
        self._wrapped: list[tuple[ttk.Label, float, int]] = []

        self.frame = ttk.Frame(parent)
        # Also gone when the main window closes: late results must then do nothing.
        self.frame.bind("<Destroy>", self._on_destroy, add="+")
        self.frame.bind("<Configure>", self._on_resize, add="+")

        self._title_font = self._font("SunValleySubtitleFont", 1.5, bold=True)
        self._bold_font = self._font("SunValleyBodyStrongFont", 1.0, bold=True)
        self._small_font = self._font("SunValleyCaptionFont", 0.9)
        self._poll_id = None

        self._build()
        self.show_step(STEP_LANGUAGE)

    # -- helpers ----------------------------------------------------------

    def _font(self, name: str, factor: float, bold: bool = False):
        """sv_ttk's named font (the one its labels use, already DPI-scaled by the
        app), else a scaled copy of TkDefaultFont."""
        try:
            return tkfont.nametofont(name, root=self.frame)
        except tk.TclError:
            pass
        base = tkfont.nametofont("TkDefaultFont", root=self.frame)
        size = int(base.cget("size")) or 10
        font = base.copy()
        # Negative Tk font sizes are pixels; keep the sign.
        font.configure(
            size=(-1 if size < 0 else 1) * max(7, round(abs(size) * factor)),
            weight="bold" if bold else "normal",
        )
        return font

    def _wrap_for(self, share: float, beside: int) -> int:
        return max(self.MIN_WRAP, round(self._wrap * share) - beside)

    def _label(self, parent, text="", muted=False, small=False, bold=False, share=1.0, beside=0, **kw):
        """A label that wraps to the column (share of it, minus what sits beside it)."""
        options = {"text": text, "wraplength": self._wrap_for(share, beside), "justify": "left"}
        if muted:
            options["foreground"] = self.MUTED
        if small:
            options["font"] = self._small_font
        if bold:
            options["font"] = self._bold_font
        options.update(kw)
        label = ttk.Label(parent, **options)
        self._wrapped.append((label, share, beside))
        return label

    def _on_resize(self, event) -> None:
        if event.widget is not self.frame or self._closed:
            return
        width = max(1, min(self._column_width, event.width))
        wrap = max(self.MIN_WRAP, width - 2 * self._padding)
        try:
            self._column.place_configure(width=width)
            if wrap != self._wrap:
                self._wrap = wrap
                for label, share, beside in self._wrapped:
                    label.configure(wraplength=self._wrap_for(share, beside))
        except tk.TclError:
            pass

    def _after(self, ms, fn):
        if self._closed:
            return None

        def _run():
            self._after_ids.discard(after_id)
            if self._closed:
                return
            try:
                fn()
            except tk.TclError:
                # The page went away between scheduling and running.
                pass

        try:
            after_id = self.frame.after(ms, _run)
        except tk.TclError:
            return None
        self._after_ids.add(after_id)
        return after_id

    def _cancel_poll(self) -> None:
        if self._poll_id is None:
            return
        self._after_ids.discard(self._poll_id)
        try:
            self.frame.after_cancel(self._poll_id)
        except tk.TclError:
            pass
        self._poll_id = None

    def _cancel_timers(self) -> None:
        for after_id in list(self._after_ids):
            try:
                self.frame.after_cancel(after_id)
            except tk.TclError:
                pass
        self._after_ids.clear()
        self._poll_id = None

    def _on_destroy(self, event) -> None:
        if event.widget is self.frame:
            self._closed = True
            # Their Tcl commands go with the frame; a timer left behind would
            # fire into nothing.
            self._cancel_timers()

    def is_open(self) -> bool:
        if self._closed:
            return False
        try:
            return bool(self.frame.winfo_exists())
        except tk.TclError:
            return False

    def pause(self) -> None:
        """The page was hidden without ending setup (cropping on the Tracking
        page, or another page opened): keep the step and the choices."""
        if self._closed or self.paused:
            return
        self.paused = True
        self._cancel_poll()

    def resume(self) -> None:
        """Shown again after pause(): the same step, with its state read afresh."""
        if self._closed or not self.paused:
            return
        self.paused = False
        try:
            self.adapter.leave_crop_mode()
        except Exception:
            logger.warning("Could not leave cropping mode", exc_info=True)
        self.show_step(self.step)

    # -- layout -----------------------------------------------------------

    def _build(self):
        # Fixed width, full height: the footer stays put at the bottom of the
        # page, so Skip/Back/Next never move or drop out of view between steps.
        outer = self._column = ttk.Frame(self.frame, padding=self._padding)
        outer.place(relx=0.5, y=0, anchor="n", relheight=1.0, width=self._column_width)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        self._label(header, tr("wizard.title"), muted=True, small=True, share=0.6).pack(side="left", anchor="w")
        self.step_label = self._label(header, muted=True, small=True, share=0.35)
        self.step_label.pack(side="right", anchor="e")
        self.title_label = ttk.Label(outer, font=self._title_font)
        self.title_label.pack(anchor="w", pady=(2, 12))

        footer = ttk.Frame(outer)
        footer.pack(side="bottom", fill="x")
        ttk.Separator(outer).pack(side="bottom", fill="x", pady=(12, 12))
        self.skip_btn = ttk.Button(footer, text=tr("wizard.skip_btn"), command=self.skip)
        self.skip_btn.pack(side="left")
        self.next_btn = ttk.Button(footer, text=tr("wizard.next_btn"), command=self.next, style="Accent.TButton")
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(footer, text=tr("wizard.back_btn"), command=self.back)
        self.back_btn.pack(side="right", padx=(0, 8))

        self.body = ttk.Frame(outer)
        self.body.pack(fill="both", expand=True)
        self.pages = {
            STEP_LANGUAGE: self._build_language(self.body),
            STEP_HEADSET: self._build_headset(self.body),
            STEP_CAMERAS: self._build_cameras(self.body),
            STEP_CHECK: self._build_check(self.body),
            STEP_DONE: self._build_done(self.body),
        }

    def _build_language(self, parent):
        # Every language in plain sight (not a dropdown), each in its own name.
        page = ttk.Frame(parent)
        self._label(page, tr("wizard.language_intro")).pack(anchor="w", pady=(0, 10))
        try:
            languages = list(self.adapter.languages())
        except Exception:
            logger.warning("Could not list the languages", exc_info=True)
            languages = []
        if not any(lang.get("code") == "en" for lang in languages):
            languages.insert(0, {"code": "en", "name": "English", "native_name": "English"})
        codes = [lang["code"] for lang in languages]
        current = self.adapter.get_language()
        self._language = current if current in codes else "en"
        self.language_var = tk.StringVar(value=self._language)
        self.language_radios = {}
        for lang in languages:
            radio = ttk.Radiobutton(
                page,
                text=language_label(lang),
                variable=self.language_var,
                value=lang["code"],
                command=self._on_language_pick,
            )
            radio.pack(anchor="w", pady=(6, 0))
            self.language_radios[lang["code"]] = radio
        return page

    def _build_headset(self, parent):
        page = ttk.Frame(parent)
        self._label(page, tr("wizard.headset_intro")).pack(anchor="w", pady=(0, 10))
        modes = list(self.adapter.modes())
        current = self.adapter.get_mode()
        self.mode_var = tk.StringVar(value=current if current in modes else modes[0])
        self.mode_radios = {}
        for mode in modes:
            name, desc = _mode_texts(mode)
            radio = ttk.Radiobutton(page, text=name, variable=self.mode_var, value=mode)
            radio.pack(anchor="w", pady=(6, 0))
            self._label(page, desc, muted=True, small=True, beside=28).pack(anchor="w", padx=(28, 0))
            self.mode_radios[mode] = radio
        return page

    def _build_cameras(self, parent):
        page = ttk.Frame(parent)
        self.cam_intro = self._label(page)
        self.cam_intro.pack(anchor="w", pady=(0, 8))

        status_row = ttk.Frame(page)
        status_row.pack(fill="x", pady=(0, 6))
        self.rescan_btn = ttk.Button(status_row, text=tr("wizard.cameras_rescan_btn"), command=self.rescan)
        self.rescan_btn.pack(side="right")
        self.cam_status = self._label(status_row, share=0.75)
        self.cam_status.pack(side="left", anchor="w")
        self.cam_help = self._label(page, muted=True, small=True)

        self.cam_grid = ttk.Frame(page)
        self.cam_grid.columnconfigure(1, weight=1)
        self.left_label = ttk.Label(self.cam_grid, text=tr("wizard.cameras_left"))
        self.left_label.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.left_var = tk.StringVar()
        self.left_combo = ttk.Combobox(self.cam_grid, textvariable=self.left_var, width=40)
        self.left_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.right_label = ttk.Label(self.cam_grid, text=tr("wizard.cameras_right"))
        self.right_label.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.right_var = tk.StringVar()
        self.right_combo = ttk.Combobox(self.cam_grid, textvariable=self.right_var, width=40)
        self.right_combo.grid(row=1, column=1, sticky="ew", pady=4)
        self.swap_btn = ttk.Button(self.cam_grid, text=tr("wizard.cameras_swap_btn"), command=self.swap)
        self.swap_btn.grid(row=0, column=2, rowspan=2, sticky="ns", padx=(8, 0), pady=4)
        for var in (self.left_var, self.right_var):
            var.trace_add("write", lambda *_a: self._sync_buttons())

        self.cam_guess = self._label(page, tr("wizard.cameras_guess"), small=True)
        self.cam_manual = self._label(page, tr("wizard.cameras_manual_hint"), muted=True, small=True)
        return page

    def _build_check(self, parent):
        page = ttk.Frame(parent)
        self._label(page, tr("wizard.check_intro")).pack(anchor="w", pady=(0, 10))
        rows = ttk.Frame(page)
        rows.pack(fill="x")
        rows.columnconfigure(1, weight=1)
        self.check_status = {}
        for row, (side, text) in enumerate(
            (("left", tr("wizard.check_left_eye")), ("right", tr("wizard.check_right_eye")))
        ):
            ttk.Label(rows, text=text, font=self._bold_font).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=3)
            label = self._label(rows, share=0.75)
            label.grid(row=row, column=1, sticky="w", pady=3)
            self.check_status[side] = label
        self.check_hint = self._label(page, tr("wizard.check_not_connecting_hint"), muted=True, small=True)
        self.check_hint.pack(anchor="w", pady=(6, 0))

        self.crop_box = ttk.Frame(page)
        self.crop_box.pack(fill="x", pady=(16, 0))
        self.crop_text = self._label(self.crop_box)
        self.crop_text.pack(anchor="w")
        self.crop_buttons = ttk.Frame(self.crop_box)
        button_row = ttk.Frame(self.crop_buttons)
        button_row.pack(anchor="w")
        self.crop_full_btn = ttk.Button(
            button_row, text=tr("wizard.crop_full_btn"), command=self.use_full_frame, style="Accent.TButton"
        )
        self.crop_adjust_btn = ttk.Button(button_row, text=tr("wizard.crop_adjust_btn"), command=self.open_crop)
        # Said before the page goes away, with the way back.
        self.crop_where = self._label(
            self.crop_buttons, tr("wizard.crop_adjust_where", resume=tr("wizard.continue_btn")), muted=True, small=True
        )
        self.crop_where.pack(anchor="w", pady=(6, 0))
        self.crop_result = self._label(self.crop_box, muted=True, small=True)
        return page

    def _build_done(self, parent):
        page = ttk.Frame(parent)
        self.done_summary = self._label(page)
        self.done_summary.pack(anchor="w", pady=(0, 12))
        self._label(
            page,
            tr(
                "wizard.done_where",
                recenter=tr("tracking.recenter_btn"),
                calibrate=tr("tracking.start_calibration"),
            ),
        ).pack(anchor="w", pady=(0, 8))
        self._label(page, tr("wizard.done_reopen", button=tr("wizard.open_btn")), muted=True, small=True).pack(
            anchor="w"
        )
        self.done_restart = self._label(page, tr("wizard.done_restart_language"), bold=True)
        return page

    # -- step 1: language -------------------------------------------------

    def _on_language_pick(self) -> None:
        code = self.language_var.get()
        if self._closed or code == self._language:
            return
        old_not_used = tr("wizard.cameras_not_used")
        try:
            self.adapter.set_language(code)
        except Exception:
            logger.warning("Could not change the language", exc_info=True)
            self.language_var.set(self._language)
            return
        self._language = code
        # Re-text the page in the new language once the click has finished
        # (the radio button that was clicked is rebuilt too).
        self._after(0, lambda: self._rebuild(old_not_used))

    def _rebuild(self, old_not_used: str = "") -> None:
        """Build the page again in the current language, keeping the choices."""
        if self._closed:
            return
        not_used = tr("wizard.cameras_not_used")
        mode = self.mode_var.get()
        cameras = [not_used if v == old_not_used else v for v in (self.left_var.get(), self.right_var.get())]
        self._cancel_poll()
        self._column.destroy()
        self._wrapped = []
        self._build()
        width = self.frame.winfo_width()
        if width > 1:
            self._column.place_configure(width=max(1, min(self._column_width, width)))
        if mode in self.mode_radios:
            self.mode_var.set(mode)
        self.left_var.set(cameras[0])
        self.right_var.set(cameras[1])
        self._refresh_choices()
        self._crop_state = None
        self.show_step(self.step)

    # -- navigation -------------------------------------------------------

    def show_step(self, step: int) -> None:
        self.step = step
        for page in self.pages.values():
            page.pack_forget()
        self.pages[step].pack(fill="both", expand=True)
        titles = {
            STEP_LANGUAGE: tr("wizard.language_title"),
            STEP_HEADSET: tr("wizard.headset_title"),
            STEP_CAMERAS: tr("wizard.cameras_title"),
            STEP_CHECK: tr("wizard.check_title"),
            STEP_DONE: tr("wizard.done_title"),
        }
        self.title_label.configure(text=titles[step])
        self.step_label.configure(text=tr("wizard.step_of", current=step + 1, total=STEP_COUNT))
        if step == STEP_CAMERAS:
            self._enter_cameras()
        elif step == STEP_CHECK:
            self._crop_state = None
            self.crop_result.pack_forget()
            self._refresh_check()
        elif step == STEP_DONE:
            self._refresh_done()
        if step == STEP_CHECK and self._poll_id is None and not self.paused:
            self._poll_id = self._after(_POLL_MS, self._poll)
        self._sync_buttons()

    def next(self) -> None:
        if self._closed:
            return
        if self.step == STEP_HEADSET:
            self.adapter.set_mode(self.mode_var.get())
        elif self.step == STEP_CAMERAS:
            if not self._can_apply_cameras():
                return
            self.adapter.apply_sources(*self.selected_sources())
        elif self.step == STEP_DONE:
            self.finish()
            return
        self.show_step(self.step + 1)

    def back(self) -> None:
        if not self._closed and self.step > STEP_LANGUAGE:
            self.show_step(self.step - 1)

    def skip(self) -> None:
        """Skip setup: never open by itself again."""
        self._end()

    def finish(self) -> None:
        self._end()

    def _end(self) -> None:
        """Mark setup done and hand the window back to the Tracking page."""
        if self._closed:
            return
        self._mark_done()
        self.close()
        try:
            self.adapter.show_tracking_page()
        except Exception:
            logger.warning("Could not show the tracking page", exc_info=True)

    def _mark_done(self) -> None:
        try:
            self.adapter.mark_done()
        except Exception:
            logger.warning("Could not save the setup wizard state", exc_info=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_timers()
        try:
            self.frame.destroy()
        except tk.TclError:
            pass

    def _sync_buttons(self) -> None:
        if self._closed:
            return
        try:
            self.back_btn.state(["!disabled"] if self.step > STEP_LANGUAGE else ["disabled"])
            text = tr("wizard.finish_btn") if self.step == STEP_DONE else tr("wizard.next_btn")
            self.next_btn.configure(text=text)
            ok = self.step != STEP_CAMERAS or self._can_apply_cameras()
            self.next_btn.state(["!disabled"] if ok else ["disabled"])
        except tk.TclError:
            pass

    # -- step 3: cameras --------------------------------------------------

    def _headset(self) -> str:
        """The headset choice ("etvr", "bigscreen", "psvr" or "frame")."""
        return self.mode_var.get()

    def _mode(self) -> str:
        """The main window's setup mode for it (PSVR runs in Bigscreen mode)."""
        return app_mode(self.mode_var.get())

    def _enter_cameras(self) -> None:
        mode = self._mode()
        frame = mode == "frame"
        intro = {
            "etvr": tr("wizard.cameras_intro_etvr"),
            "bigscreen": tr("wizard.cameras_intro_bigscreen"),
            "frame": tr("wizard.cameras_intro_frame"),
        }[mode]
        self.cam_intro.configure(text=intro)
        for widget in (self.cam_grid, self.cam_guess, self.cam_manual, self.cam_help):
            widget.pack_forget()
        if frame:
            self.cam_status.configure(text="")
            self.rescan_btn.pack_forget()
            return
        if not self.rescan_btn.winfo_manager():
            self.rescan_btn.pack(side="right")
        self.cam_grid.pack(fill="x", pady=(4, 0))
        self.cam_manual.pack(anchor="w", pady=(6, 0))
        bigscreen = mode == "bigscreen"
        self.left_label.configure(text=tr("wizard.cameras_one") if bigscreen else tr("wizard.cameras_left"))
        if bigscreen:
            self.right_label.grid_remove()
            self.right_combo.grid_remove()
            self.swap_btn.grid_remove()
        else:
            self.right_label.grid()
            self.right_combo.grid()
            self.swap_btn.grid()
        if self._scanned_mode != mode:
            self._scanned_mode = mode
            self._autofilled = None
            self._guessed = False
            # A different headset: forget a scan still running for the old one.
            self._scan_gen += 1
            self._scanning = False
            left, right = self.adapter.current_sources()
            self.left_var.set(self._label_for(left))
            self.right_var.set("" if bigscreen else self._label_for(right))
            self.rescan()
        else:
            self._refresh_cam_status()

    def _label_for(self, value) -> str:
        if not _is_set(value):
            return ""
        value = str(value)
        for label, mapped in self._label_to_value.items():
            if mapped == value:
                return label
        label = source_label(value)
        if label in self._label_to_value and self._label_to_value[label] != value:
            label = value
        self._label_to_value[label] = value
        return label

    def value_for(self, text: str) -> str:
        text = (text or "").strip()
        if text == tr("wizard.cameras_not_used"):
            return ""
        return self._label_to_value.get(text, text)

    def selected_sources(self) -> tuple[str, str]:
        mode = self._mode()
        if mode == "frame":
            assignment = proposed_assignment("frame", [])
            return assignment.left, assignment.right
        left = self.value_for(self.left_var.get())
        if mode == "bigscreen":
            return left, left
        return left, self.value_for(self.right_var.get())

    def _can_apply_cameras(self) -> bool:
        if self._mode() == "frame":
            return True
        return any(_is_set(v) for v in self.selected_sources())

    def rescan(self) -> None:
        if self._closed or self._scanning or self._mode() == "frame":
            return
        self._scan_gen += 1
        gen = self._scan_gen
        self._scanning = True
        self._refresh_cam_status()

        def _update(source_map, done):
            self._on_scan_update(gen, source_map, done)

        try:
            self.adapter.scan(_update)
        except Exception:
            logger.exception("Camera scan failed")
            self._on_scan_update(gen, {}, True)
            return
        self._after(_SCAN_WATCHDOG_MS, lambda: self._on_scan_update(gen, None, True))

    def _on_scan_update(self, gen, source_map, done) -> None:
        """Runs on the Tk thread; ignored once the wizard is closed or a newer scan started."""
        if self._closed or gen != self._scan_gen:
            return
        try:
            if source_map is not None:
                self._found = sources_from_scan(source_map)
                for source in self._found:
                    self._label_to_value[source.label] = source.value
                self._refresh_choices()
            if done and self._scanning:
                self._scanning = False
                self._autofill()
            self._refresh_cam_status()
            self._sync_buttons()
        except tk.TclError:
            pass

    def _refresh_choices(self) -> None:
        labels = [s.label for s in self._found]
        # Keep a source that is set but was not found (the scan skips ports in use).
        for value in self.adapter.current_sources():
            label = self._label_for(value)
            if label and label not in labels:
                labels.append(label)
        labels.append(tr("wizard.cameras_not_used"))
        self.left_combo.configure(values=labels)
        self.right_combo.configure(values=labels)

    def _autofill(self) -> None:
        current = (self.left_var.get().strip(), self.right_var.get().strip())
        # Never overwrite a choice the user made.
        if current != ("", "") and current != self._autofilled:
            return
        assignment = proposed_assignment(self._mode(), self._found)
        if assignment.left is None and assignment.right is None:
            self._guessed = False
            return
        left = self._label_for(assignment.left)
        right = "" if self._mode() == "bigscreen" else self._label_for(assignment.right)
        self.left_var.set(left)
        self.right_var.set(right)
        self._autofilled = (left, right)
        self._guessed = not assignment.sure

    def _refresh_cam_status(self) -> None:
        self.cam_help.pack_forget()
        self.cam_guess.pack_forget()
        if self._scanning:
            self.cam_status.configure(text=tr("wizard.cameras_searching"))
            self.rescan_btn.state(["disabled"])
            return
        self.rescan_btn.state(["!disabled"])
        if not self._found:
            self.cam_status.configure(text=tr("wizard.cameras_none_found"))
            help_key = self._mode() == "bigscreen"
            self.cam_help.configure(
                text=tr("wizard.cameras_help_bigscreen") if help_key else tr("wizard.cameras_help_etvr")
            )
            self.cam_help.pack(anchor="w", pady=(0, 8), before=self.cam_grid)
            return
        self.cam_status.configure(text=tr("wizard.cameras_found", count=len(self._found)))
        if self._guessed and (self.left_var.get().strip(), self.right_var.get().strip()) == self._autofilled:
            self.cam_guess.pack(anchor="w", pady=(6, 0), before=self.cam_manual)

    def swap(self) -> None:
        left, right = self.left_var.get(), self.right_var.get()
        self.left_var.set(right)
        self.right_var.set(left)
        self._guessed = False
        self._refresh_cam_status()

    # -- step 4: check ----------------------------------------------------

    def _poll(self) -> None:
        self._poll_id = None
        if self._closed or self.paused:
            return
        if self.step != STEP_CHECK:
            return
        self._refresh_check()
        self._poll_id = self._after(_POLL_MS, self._poll)

    def _active_sides(self) -> list[str]:
        return [side for side in SIDES if self.adapter.eye_state(side) != "none"]

    def _refresh_check(self) -> None:
        texts = {
            "none": tr("wizard.check_not_used"),
            "connecting": tr("wizard.check_connecting"),
            "connected": tr("wizard.check_connected"),
            "disconnected": tr("wizard.check_disconnected"),
        }
        states = {side: self.adapter.eye_state(side) for side in SIDES}
        for side, state in states.items():
            text = texts.get(state, texts["connecting"])
            if self.check_status[side].cget("text") != text:
                self.check_status[side].configure(text=text)
        trouble = any(state == "disconnected" for state in states.values())
        if trouble != bool(self.check_hint.winfo_manager()):
            if trouble:
                self.check_hint.pack(anchor="w", pady=(6, 0), before=self.crop_box)
            else:
                self.check_hint.pack_forget()

        active = [side for side, state in states.items() if state != "none"]
        if not tracker_needs_crop(self.adapter.settings):
            crop_state = "none_needed"
        elif not active:
            crop_state = "no_camera"
        elif any(crop_missing(self.adapter.eye_config(side)) for side in active):
            crop_state = "missing"
        else:
            crop_state = "set"
        if crop_state == self._crop_state:
            return
        self._crop_state = crop_state
        self.crop_buttons.pack_forget()
        self.crop_full_btn.pack_forget()
        self.crop_adjust_btn.pack_forget()
        text = {
            "none_needed": "",
            "no_camera": "",
            "missing": tr("wizard.crop_missing"),
            "set": tr("wizard.crop_set"),
        }[crop_state]
        self.crop_text.configure(text=text)
        if crop_state == "missing":
            self.crop_full_btn.pack(side="left", padx=(0, 8))
            self.crop_adjust_btn.pack(side="left")
        elif crop_state == "set":
            self.crop_adjust_btn.pack(side="left")
        if crop_state in ("missing", "set"):
            # Above the result line when that is showing.
            before = {"before": self.crop_result} if self.crop_result.winfo_manager() else {}
            self.crop_buttons.pack(anchor="w", fill="x", pady=(8, 0), **before)
        self._sync_crop_busy()

    def _sync_crop_busy(self) -> None:
        self.crop_full_btn.state(["disabled"] if self._crop_busy else ["!disabled"])

    def _show_crop_result(self, text: str) -> None:
        self.crop_result.configure(text=text)
        if not self.crop_result.winfo_manager():
            self.crop_result.pack(anchor="w", pady=(6, 0))

    def use_full_frame(self) -> None:
        """Set each active eye's crop to the whole picture so tracking can start."""
        if self._closed or self._crop_busy:
            return
        mode = self._mode()
        sides = [s for s in self._active_sides() if crop_missing(self.adapter.eye_config(s))]
        if not sides:
            return
        self._crop_busy = len(sides)
        self._sync_crop_busy()
        self._show_crop_result(tr("wizard.crop_waiting"))
        failed = []

        def _got(side, shape):
            if self._closed:
                return
            try:
                if shape is None:
                    failed.append(side)
                else:
                    self.adapter.set_roi(side, full_frame_roi(shape, mode, side))
            except Exception:
                logger.warning("Could not set the full-frame crop", exc_info=True)
                failed.append(side)
            self._crop_busy -= 1
            if self._crop_busy:
                return
            try:
                self._sync_crop_busy()
                self._show_crop_result(tr("wizard.crop_no_picture") if failed else tr("wizard.crop_full_done"))
                self._refresh_check()
            except tk.TclError:
                pass

        for side in sides:
            try:
                self.adapter.request_frame_shape(side, lambda shape, s=side: _got(s, shape))
            except Exception:
                logger.warning("Could not read a picture from the %s camera", side, exc_info=True)
                _got(side, None)

    def open_crop(self) -> None:
        """Cropping is done on the Tracking page: the app pauses this page and
        the Continue setup button brings it back at this step (WizardPage)."""
        if self._closed:
            return
        try:
            self.adapter.open_crop_mode()
        except Exception:
            logger.warning("Could not open cropping mode", exc_info=True)

    # -- step 5: done -----------------------------------------------------

    def _refresh_done(self) -> None:
        mode = self._mode()
        left, right = self.adapter.current_sources()
        not_used = tr("wizard.cameras_not_used")

        def name(value):
            return self._label_for(value) or not_used

        lines = [tr("wizard.done_headset", headset=_mode_texts(self._headset())[0])]
        if mode == "bigscreen":
            lines.append(tr("wizard.done_camera", camera=name(left)))
        elif mode != "frame":
            lines.append(tr("wizard.done_left", camera=name(left)))
            lines.append(tr("wizard.done_right", camera=name(right)))
        lines.append(tr("wizard.done_tracker", tracker=tracker_name(self.adapter.settings)))
        self.done_summary.configure(text="\n".join(lines))
        try:
            restart = bool(self.adapter.language_needs_restart())
        except Exception:
            restart = False
        if restart:
            self.done_restart.pack(anchor="w", pady=(12, 0))
        else:
            self.done_restart.pack_forget()


# ---------------------------------------------------------------------------
# The wizard as a page of the main window
# ---------------------------------------------------------------------------


class WizardPage:
    """The setup wizard in place of the main window's other pages.

    AppUI.show_page() calls sync() on every page switch. While the wizard shows,
    it fills the page area and the navigation bar is hidden, so its own buttons
    are the way out: Skip setup and Finish end it and return to the Tracking
    page. Any other page switch (Adjust the crop, or other code opening a
    page) pauses it: it keeps its step and choices, the
    navigation comes back, and the Tracking page's wizard button reads
    "Continue setup" until show_page("wizard") resumes it.
    """

    PAGE = "wizard"

    def __init__(self, content, nav_bar, button, make_adapter):
        self.content = content  # the frame the pages are packed into
        self.nav_bar = nav_bar  # packed before content
        self.button = button  # the Tracking page's wizard button, or None
        self._make_adapter = make_adapter
        self._nav_pack: dict = {}
        self.wizard: SetupWizard | None = None

    def _live(self) -> SetupWizard | None:
        if self.wizard is not None and not self.wizard.is_open():
            self.wizard = None
        return self.wizard

    @property
    def visible(self) -> bool:
        wizard = self._live()
        return wizard is not None and bool(wizard.frame.winfo_manager())

    @property
    def paused(self) -> bool:
        wizard = self._live()
        return wizard is not None and wizard.paused

    def sync(self, page: str) -> bool:
        """Show the wizard (a paused one at its step, else a new one at step 1)
        when page is "wizard", else hide and pause it. Call after the other pages
        are hidden. False when the wizard was asked for but could not be shown
        (the caller then shows another page)."""
        wizard = self._live()
        show = page == self.PAGE
        if show and wizard is None:
            try:
                wizard = self.wizard = SetupWizard(self.content, self._make_adapter())
            except Exception:
                logger.exception("Could not open the setup wizard")
                self.sync("")  # navigation back
                return False
        try:
            if show:
                if self.nav_bar.winfo_manager():
                    self._nav_pack = {k: v for k, v in self.nav_bar.pack_info().items() if k != "in"}
                    self.nav_bar.pack_forget()
                wizard.frame.pack(fill="both", expand=True)
                wizard.resume()
            else:
                if wizard is not None and wizard.frame.winfo_manager():
                    wizard.frame.pack_forget()
                    wizard.pause()
                if not self.nav_bar.winfo_manager():
                    self.nav_bar.pack(**self._nav_pack, before=self.content)
            self._sync_button()
        except tk.TclError:
            # The main window is going away.
            pass
        return True

    def _sync_button(self) -> None:
        if self.button is None:
            return
        paused = self.paused
        self.button.configure(
            text=tr("wizard.continue_btn") if paused else tr("wizard.open_btn"),
            # Stands out while setup waits to be continued.
            style="Accent.TButton" if paused else "TButton",
        )
