"""First-run setup wizard (eyetrackapp/setup_wizard.py): pure helpers, the
auto-open rule, the real-app adapter, the wizard driven by a fake adapter, and
WizardPage putting it in place of the main window's pages."""

import json
import os
import queue
import re
import tomllib
import types
from pathlib import Path

import numpy as np
import pytest

import setup_wizard as sw
from config import EyeTrackConfig
from frame_eye import FRAME_LEFT_SOURCE, FRAME_RIGHT_SOURCE

APP_DIR = Path(__file__).resolve().parents[1] / "eyetrackapp"
LANG_EN = APP_DIR / "lang" / "en.toml"
# The wizard's English strings before they are merged into lang/en.toml [wizard].
STRINGS_ENV = "ETVR_WIZARD_STRINGS"


def _en_catalog():
    with open(LANG_EN, "rb") as file:
        return tomllib.load(file)


def _wizard_strings():
    """{"wizard.<key>": text}: lang/en.toml's [wizard] table, else the JSON named by
    ETVR_WIZARD_STRINGS, else None."""
    table = _en_catalog().get("wizard")
    if isinstance(table, dict) and table:
        return {f"wizard.{key}": value for key, value in table.items()}
    path = os.environ.get(STRINGS_ENV)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    return None


def _lookup(catalog, key):
    node = catalog
    for part in key.split("."):
        node = node[part]
    return node


def _strict_tr():
    """tr() that fails loudly on a missing key or placeholder (when the strings exist)."""
    en = _en_catalog()
    wizard = _wizard_strings()

    def tr(key, **fmt):
        if key.startswith("wizard."):
            if wizard is None:
                return key
            text = wizard[key]
        else:
            text = _lookup(en, key)
        return text.format(**fmt) if fmt else text

    return tr


def _keys_used(path):
    return set(re.findall(r'\btr\(\s*"([a-z_]+\.[a-z0-9_]+)"', Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _config(left=None, right=None, done=False):
    config = EyeTrackConfig()
    config.left_eye.capture_source = left
    config.right_eye.capture_source = right
    config.settings.gui_setup_wizard_done = done
    return config


def test_setting_defaults_to_not_done():
    assert EyeTrackConfig().settings.gui_setup_wizard_done is False


@pytest.mark.parametrize(
    ("left", "right", "done", "action"),
    [
        (None, None, False, "open"),  # new user
        ("", "", False, "open"),
        (0, None, False, "mark_done"),  # UVC index 0 is a real source
        (None, "COM5", False, "mark_done"),  # upgrading user
        (None, None, True, "none"),
        ("COM5", None, True, "none"),
    ],
)
def test_first_run_action(left, right, done, action):
    config = _config(left, right, done)
    assert sw.first_run_action(config) == action
    assert sw.should_auto_open(config) is (action == "open")


class _FakeRoot:
    def __init__(self):
        self.scheduled = []

    def after(self, ms, fn):
        self.scheduled.append((ms, fn))
        return f"after#{len(self.scheduled)}"

    def run_pending(self):
        pending, self.scheduled = self.scheduled, []
        for _ms, fn in pending:
            fn()


def test_first_run_check_opens_for_new_user(monkeypatch):
    config = _config()
    monkeypatch.setattr(EyeTrackConfig, "save", lambda self: pytest.fail("nothing to save for a new user yet"))
    root = _FakeRoot()
    opened = []
    # Right away: the window first shows on the wizard page, not the Tracking page.
    assert sw.run_first_run_check(root, config, lambda: opened.append(True)) == "open"
    assert opened == [True]
    assert root.scheduled == []
    assert config.settings.gui_setup_wizard_done is False


def test_first_run_check_can_defer_the_open():
    root = _FakeRoot()
    opened = []
    assert sw.run_first_run_check(root, _config(), lambda: opened.append(True), delay_ms=700) == "open"
    assert opened == []
    assert [ms for ms, _fn in root.scheduled] == [700]
    root.run_pending()
    assert opened == [True]


def test_first_run_check_marks_existing_user_done_silently(monkeypatch):
    config = _config(left="http://ETVR-Left.local/")
    saves = []
    monkeypatch.setattr(EyeTrackConfig, "save", lambda self: saves.append(True))
    root = _FakeRoot()
    assert sw.run_first_run_check(root, config, lambda: pytest.fail("must not open")) == "mark_done"
    assert config.settings.gui_setup_wizard_done is True
    assert saves == [True]
    assert root.scheduled == []
    # Next launch: nothing at all.
    assert sw.run_first_run_check(root, config, lambda: pytest.fail("must not open")) == "none"
    assert root.scheduled == []


def test_first_run_check_survives_a_failing_opener():
    root = _FakeRoot()
    sw.run_first_run_check(root, _config(), lambda: 1 / 0)  # logged, not raised
    sw.run_first_run_check(root, _config(), lambda: 1 / 0, delay_ms=700)
    root.run_pending()


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("uvc:USB Camera@\\\\?\\usb#1", "uvc"),
        ("0", "uvc"),
        ("COM5", "serial"),
        ("/dev/ttyUSB0", "serial"),
        ("http://ETVR-Left.local/", "network"),
        (FRAME_LEFT_SOURCE, "frame"),
        ("clip.mp4", "other"),
    ],
)
def test_source_kind(value, kind):
    assert sw.source_kind(value) == kind


def test_sources_from_scan_orders_network_serial_then_webcams():
    found = sw.sources_from_scan(
        {
            "Integrated Webcam": "uvc:Integrated Webcam@a",
            "http://ETVR-Left.local/": "http://ETVR-Left.local/",
            "USB Serial (COM5)": "COM5",
            "": "ignored",
        }
    )
    assert [s.kind for s in found] == ["network", "serial", "uvc"]
    assert found[1] == sw.Source("USB Serial (COM5)", "COM5", "serial")


@pytest.mark.parametrize(
    ("label", "hint"),
    [
        ("http://ETVR-Left.local/", "left"),
        ("http://ETVR-Right.local/", "right"),
        ("Bright Camera", None),  # "right" inside a word is not a side
        ("Left Right Cam", None),
        ("USB Camera", None),
    ],
)
def test_side_hint(label, hint):
    assert sw.side_hint(sw.Source(label, label, "other")) == hint


def _src(label, value=None):
    value = label if value is None else value
    return sw.Source(label, value, sw.source_kind(value))


def test_proposed_assignment_frame_uses_the_built_in_pair():
    assert sw.proposed_assignment("frame", []) == sw.Assignment(FRAME_LEFT_SOURCE, FRAME_RIGHT_SOURCE, True)


def test_proposed_assignment_bigscreen_prefers_the_headset_camera():
    sources = [_src("Integrated Webcam", "uvc:Integrated Webcam@a"), _src("Bigscreen Bigeye", "uvc:Bigscreen Bigeye@b")]
    assert sw.proposed_assignment("bigscreen", sources) == sw.Assignment(
        "uvc:Bigscreen Bigeye@b", "uvc:Bigscreen Bigeye@b", True
    )
    # A lone unknown camera is offered, but as a guess.
    only = [_src("USB Camera", "uvc:USB Camera@a")]
    assert sw.proposed_assignment("bigscreen", only) == sw.Assignment("uvc:USB Camera@a", "uvc:USB Camera@a", False)
    assert sw.proposed_assignment("bigscreen", sources[:1] + [_src("Other", "uvc:Other@c")]).left is None


def test_proposed_assignment_etvr():
    left, right = "http://ETVR-Left.local/", "http://ETVR-Right.local/"
    webcam = _src("Integrated Webcam", "uvc:Integrated Webcam@a")
    # Named trackers: certain, whatever the order and extra webcams.
    assert sw.proposed_assignment("etvr", [_src(right), webcam, _src(left)]) == sw.Assignment(left, right, True)
    # Two unnamed trackers: a guess in scan order; the webcam is left out.
    two = [_src("USB (COM3)", "COM3"), _src("USB (COM4)", "COM4"), webcam]
    assert sw.proposed_assignment("etvr", two) == sw.Assignment("COM3", "COM4", False)
    # One named tracker goes to its side.
    assert sw.proposed_assignment("etvr", [_src(right)]) == sw.Assignment(None, right, True)
    assert sw.proposed_assignment("etvr", [webcam]) == sw.Assignment("uvc:Integrated Webcam@a", None, False)
    # Three unnamed cameras: no idea.
    three = [_src(f"Cam {i}", f"uvc:Cam {i}@{i}") for i in range(3)]
    assert sw.proposed_assignment("etvr", three) == sw.Assignment(None, None, False)
    assert sw.proposed_assignment("etvr", []) == sw.Assignment(None, None, False)


def _settings(**overrides):
    values = dict(gui_NEXT=True, gui_NEXT_BSB=False, gui_LEAP=False, gui_DADDY=False, gui_use_overlay_cal=True)
    values.update(overrides)
    return types.SimpleNamespace(**values)


def test_tracker_needs_crop():
    assert sw.tracker_needs_crop(_settings()) is False
    assert sw.tracker_needs_crop(_settings(gui_NEXT=False, gui_NEXT_BSB=True)) is False
    assert sw.tracker_needs_crop(_settings(gui_NEXT=False, gui_LEAP=True)) is True
    # The real default tracker is NEXT.
    assert sw.tracker_needs_crop(EyeTrackConfig().settings) is False


def test_crop_missing():
    eye = EyeTrackConfig().left_eye
    assert sw.crop_missing(eye) is False  # 240x240 default
    eye.roi_window_w = 0
    assert sw.crop_missing(eye) is True


def test_full_frame_roi():
    assert sw.full_frame_roi((480, 640, 3)) == (0, 0, 640, 480)
    assert sw.full_frame_roi((240, 240)) == (0, 0, 240, 240)
    assert sw.full_frame_roi((400, 801, 3), "bigscreen", "left") == (0, 0, 400, 400)
    assert sw.full_frame_roi((400, 801, 3), "bigscreen", "right") == (400, 0, 401, 400)
    with pytest.raises(ValueError):
        sw.full_frame_roi((0, 640))


def test_psvr_runs_in_bigscreen_mode():
    assert sw.app_mode("psvr") == "bigscreen"
    assert [sw.app_mode(m) for m in ("etvr", "bigscreen", "frame")] == ["etvr", "bigscreen", "frame"]
    assert sw.HEADSET_MODEL_VARIANT == {"etvr": "ETVR", "bigscreen": "BSB", "psvr": "PSVR"}


def test_language_label():
    assert sw.language_label({"code": "en", "name": "English", "native_name": "English"}) == "English"
    assert sw.language_label({"code": "de", "name": "German", "native_name": "Deutsch"}) == "Deutsch (German)"
    assert sw.language_label({"code": "xx"}) == "xx"


def test_tracker_name():
    assert sw.tracker_name(_settings()) == "NEXT"
    assert sw.tracker_name(_settings(gui_NEXT=False, gui_LEAP=True)) == "LEAP"
    assert sw.tracker_name(_settings(gui_NEXT=False, gui_NEXT_BSB=True)) == "NEXT"


def test_source_label():
    assert sw.source_label("uvc:USB Camera@\\\\?\\usb#1") == "USB Camera"
    assert sw.source_label("COM5") == "COM5"
    assert sw.source_label(0) == "0"


# ---------------------------------------------------------------------------
# Strings
# ---------------------------------------------------------------------------


def test_every_key_has_an_english_string():
    used = _keys_used(APP_DIR / "setup_wizard.py") | {
        key for key in _keys_used(APP_DIR / "eyetrackapp.py") if key.startswith("wizard.")
    }
    wizard_keys = {key for key in used if key.startswith("wizard.")}
    assert len(wizard_keys) > 40
    # Keys borrowed from the rest of the app must already exist.
    en = _en_catalog()
    for key in used - wizard_keys:
        assert isinstance(_lookup(en, key), str), key
    strings = _wizard_strings()
    if strings is None:
        pytest.skip(f"no [wizard] table in lang/en.toml yet and {STRINGS_ENV} is not set")
    missing = sorted(wizard_keys - set(strings))
    assert not missing, missing
    unused = sorted(set(strings) - wizard_keys)
    assert not unused, unused


def test_strings_use_named_placeholders_only():
    strings = _wizard_strings()
    if strings is None:
        pytest.skip(f"no [wizard] table in lang/en.toml yet and {STRINGS_ENV} is not set")
    for key, text in strings.items():
        assert "{}" not in text and not re.search(r"\{\d", text), key


# ---------------------------------------------------------------------------
# AppAdapter over a stand-in AppUI
# ---------------------------------------------------------------------------


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Camera:
    def __init__(self):
        self._extra_output_queues = []
        self.camera_status = types.SimpleNamespace(name="CONNECTED")

    def set_extra_output_queues(self, queues):
        self._extra_output_queues = list(queues)


class _Eye:
    def __init__(self, cfg, started=True):
        self.config = cfg
        self._started = started
        self.camera = _Camera()
        self.xy0 = self.xy1 = self.cr = self.ca = self.roi_size = "old"
        self.in_roi_mode = False

    def started(self):
        return self._started

    def _effective_camera(self):
        return self.camera

    def _effective_camera_status(self):
        return self.camera.camera_status


def _fake_app(config):
    calls = []
    app = types.SimpleNamespace(
        root=_FakeRoot(),
        mode_var=_Var("etvr"),
        left_camera_var=_Var(),
        right_camera_var=_Var(),
        _source_display_map={"USB Camera": "uvc:USB Camera@a"},
        _dpi_scale=1.5,
        calls=calls,
    )
    app.on_mode_change = lambda: calls.append(("on_mode_change", app.mode_var.get()))
    app.scan_sources = lambda on_update=None: calls.append(("scan_sources", on_update))
    app.apply_camera_inputs = lambda: calls.append(
        ("apply_camera_inputs", app.left_camera_var.get(), app.right_camera_var.get())
    )
    app.show_page = lambda page: calls.append(("show_page", page))
    app._on_global_roi_mode = lambda: calls.append(("roi_mode",))
    app._on_global_tracking_mode = lambda: calls.append(("tracking_mode",))
    return app


def test_adapter_routes_through_the_main_window(monkeypatch):
    config = EyeTrackConfig()
    saves = []
    monkeypatch.setattr(EyeTrackConfig, "save", lambda self: saves.append(True))
    app = _fake_app(config)
    right_eye, left_eye = _Eye(config.right_eye), _Eye(config.left_eye, started=False)
    adapter = sw.AppAdapter(app, config, [right_eye, left_eye])
    assert adapter.dpi_scale == 1.5

    adapter.set_mode("etvr")  # unchanged: the selector is not touched
    adapter.set_mode("bigscreen")
    assert app.calls == [("on_mode_change", "bigscreen")]
    assert config.settings.gui_model_variant == "BSB"
    assert adapter.get_mode() == "bigscreen"
    # PSVR2 / other commercial: Bigscreen mode (one picture, both eyes) with the
    # PSVR model, kept as a manual choice so the setup mode won't undo it.
    adapter.set_mode("psvr")
    assert app.mode_var.get() == "bigscreen" and len(app.calls) == 1
    assert config.settings.gui_model_variant == "PSVR"
    assert config.settings.gui_model_variant_user_set is True
    assert adapter.get_mode() == "psvr"
    adapter.set_mode("etvr")
    assert app.calls[-1] == ("on_mode_change", "etvr")
    assert config.settings.gui_model_variant == "ETVR"
    assert config.settings.gui_model_variant_user_set is False
    assert "psvr" in adapter.modes()

    # Languages: saved and switched in memory; the window was built in English.
    app.ui_language = "en"
    monkeypatch.setattr("localization.init_localization", lambda code: app.calls.append(("init_localization", code)))
    assert adapter.get_language() == "en" and not adapter.language_needs_restart()
    assert any(lang["code"] == "en" for lang in adapter.languages())
    adapter.set_language("de")
    assert config.settings.gui_language == "de"
    assert app.calls[-1] == ("init_localization", "de")
    assert adapter.language_needs_restart()

    callback = object()
    adapter.scan(callback)
    assert app.calls[-1] == ("scan_sources", callback)

    # A scanned source shows its friendly label in the main window; typed text stays as is.
    adapter.apply_sources("uvc:USB Camera@a", "192.168.1.20")
    assert app.calls[-1] == ("apply_camera_inputs", "USB Camera", "192.168.1.20")
    adapter.apply_sources(0, None)
    assert app.calls[-1] == ("apply_camera_inputs", "0", "")

    config.left_eye.capture_source = None
    config.right_eye.capture_source = "COM5"
    assert adapter.eye_state("left") == "none"
    assert adapter.eye_state("right") == "connected"
    right_eye.camera.camera_status = types.SimpleNamespace(name="DISCONNECTED")
    assert adapter.eye_state("right") == "disconnected"
    config.left_eye.capture_source = "COM6"
    assert adapter.eye_state("left") == "connecting"  # set but not started yet
    assert adapter.any_eye_running() is True

    adapter.set_roi("left", (0, 0, 640, 480))
    assert (config.left_eye.roi_window_w, config.left_eye.roi_window_h) == (640, 480)
    assert left_eye.xy0 is None and left_eye.roi_size is None
    assert saves

    adapter.open_crop_mode()
    assert app.calls[-2:] == [("show_page", "tracking"), ("roi_mode",)]
    adapter.leave_crop_mode()  # neither eye is cropping: nothing to do
    assert app.calls[-1] == ("roi_mode",)
    left_eye.in_roi_mode = True
    adapter.leave_crop_mode()
    assert app.calls[-1] == ("tracking_mode",)

    adapter.mark_done()
    assert config.settings.gui_setup_wizard_done is True


def test_adapter_reads_one_frame_shape_and_removes_its_tap():
    config = EyeTrackConfig()
    app = _fake_app(config)
    eye = _Eye(config.left_eye)
    other = queue.Queue()
    eye.camera._extra_output_queues = [other]
    adapter = sw.AppAdapter(app, config, [_Eye(config.right_eye), eye])
    shapes = []
    adapter.request_frame_shape("left", shapes.append)
    tap = eye.camera._extra_output_queues[-1]
    assert tap is not other
    app.root.run_pending()  # nothing yet
    assert shapes == []
    tap.put((np.zeros((480, 640, 3), np.uint8), 1, 30.0, 0.0))
    app.root.run_pending()
    assert shapes == [(480, 640, 3)]
    assert eye.camera._extra_output_queues == [other]


def test_adapter_frame_shape_gives_up():
    config = EyeTrackConfig()
    app = _fake_app(config)
    eye = _Eye(config.left_eye)
    adapter = sw.AppAdapter(app, config, [_Eye(config.right_eye), eye])
    shapes = []
    adapter.request_frame_shape("left", shapes.append)
    for _ in range(100):
        app.root.run_pending()
    assert shapes == [None]
    assert eye.camera._extra_output_queues == []


# ---------------------------------------------------------------------------
# The wizard, driven by a fake adapter
# ---------------------------------------------------------------------------


LANGUAGES = [
    {"code": "en", "name": "English", "native_name": "English"},
    {"code": "de", "name": "German", "native_name": "Deutsch"},
]


class FakeAdapter:
    def __init__(
        self, modes=("etvr", "bigscreen", "psvr"), mode="etvr", sources=(None, None), settings=None, show_page=None
    ):
        self._modes = list(modes)
        self.mode = mode
        self.language = "en"
        self.ui_language = "en"
        self.sources = list(sources)
        self.settings = settings or _settings()
        self.dpi_scale = 1.0
        # The main window's show_page, when a test has one (see _MainWindow).
        self.show_page = show_page
        self.calls = []
        self.scans = []
        self.frame_requests = []
        self.states = {side: "none" for side in sw.SIDES}
        self.configs = {
            side: types.SimpleNamespace(roi_window_x=0, roi_window_y=0, roi_window_w=240, roi_window_h=240)
            for side in sw.SIDES
        }

    def languages(self):
        return LANGUAGES

    def get_language(self):
        return self.language

    def set_language(self, code):
        self.calls.append(("set_language", code))
        self.language = code

    def language_needs_restart(self):
        return self.language != self.ui_language

    def modes(self):
        return self._modes

    def get_mode(self):
        return self.mode

    def set_mode(self, mode):
        self.calls.append(("set_mode", mode))
        self.mode = mode

    def scan(self, on_update):
        self.scans.append(on_update)

    def current_sources(self):
        return tuple(self.sources)

    def apply_sources(self, left, right):
        self.calls.append(("apply_sources", left, right))
        self.sources = [left or None, right or None]
        for side, value in zip(sw.SIDES, self.sources):
            self.states[side] = "connecting" if value else "none"

    def eye_config(self, side):
        return self.configs[side]

    def eye_state(self, side):
        return self.states[side]

    def any_eye_running(self):
        return any(state != "none" for state in self.states.values())

    def request_frame_shape(self, side, callback):
        self.frame_requests.append((side, callback))

    def set_roi(self, side, roi):
        self.calls.append(("set_roi", side, roi))
        cfg = self.configs[side]
        cfg.roi_window_x, cfg.roi_window_y, cfg.roi_window_w, cfg.roi_window_h = roi

    def open_crop_mode(self):
        self.calls.append(("open_crop_mode",))
        if self.show_page:
            self.show_page("tracking")

    def leave_crop_mode(self):
        self.calls.append(("leave_crop_mode",))

    def show_tracking_page(self):
        self.calls.append(("show_tracking_page",))
        if self.show_page:
            self.show_page("tracking")

    def mark_done(self):
        self.calls.append(("mark_done",))


@pytest.fixture(scope="module")
def _shared_root():
    # One interpreter for the module: creating many in one process occasionally
    # fails to find Tcl's own library files on this Windows Python build.
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
        root.withdraw()
        import sv_ttk

        sv_ttk.set_theme("dark")  # the app's theme; also defines Accent.TButton
    except tk.TclError as exc:
        pytest.skip(f"needs a display ({exc})")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def tk_root(_shared_root, monkeypatch):
    monkeypatch.setattr(sw, "tr", _strict_tr())
    yield _shared_root
    for child in _shared_root.winfo_children():
        child.destroy()


def _text(widget):
    return str(widget.cget("text"))


def _disabled(widget):
    return widget.instate(["disabled"])


def _shown(widget):
    return bool(widget.winfo_manager())


LEFT_URL, RIGHT_URL = "http://ETVR-Left.local/", "http://ETVR-Right.local/"


def test_full_etvr_walkthrough(tk_root):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    assert w.is_open()
    assert w.step == sw.STEP_LANGUAGE
    assert _text(w.step_label) == sw.tr("wizard.step_of", current=1, total=sw.STEP_COUNT)
    assert w.frame.master is tk_root and not _shown(w.frame)  # WizardPage packs it
    assert set(w.language_radios) == {"en", "de"} and w.language_var.get() == "en"
    assert _disabled(w.back_btn)

    w.next()
    assert w.step == sw.STEP_HEADSET
    assert set(w.mode_radios) == {"etvr", "bigscreen", "psvr"}
    assert [_text(w.mode_radios[m]) for m in ("etvr", "bigscreen", "psvr")] == [
        sw.tr("wizard.mode_etvr"),
        sw.tr("wizard.mode_bigscreen"),
        sw.tr("wizard.mode_psvr"),
    ]
    w.next()
    assert fake.calls[-1] == ("set_mode", "etvr")
    assert w.step == sw.STEP_CAMERAS
    # The scan starts by itself, with Rescan disabled while it runs.
    assert len(fake.scans) == 1
    assert _text(w.cam_status) == sw.tr("wizard.cameras_searching")
    assert _disabled(w.rescan_btn)
    assert _disabled(w.next_btn)  # nothing chosen yet

    fake.scans[0]({LEFT_URL: LEFT_URL}, False)  # partial: no autofill yet
    assert w.left_var.get() == ""
    fake.scans[0]({RIGHT_URL: RIGHT_URL, LEFT_URL: LEFT_URL, "Webcam": "uvc:Webcam@a"}, True)
    assert (w.left_var.get(), w.right_var.get()) == (LEFT_URL, RIGHT_URL)
    assert not _disabled(w.rescan_btn)
    assert not _disabled(w.next_btn)
    assert not _shown(w.cam_guess)  # the names made it certain
    assert sw.tr("wizard.cameras_not_used") in w.left_combo.cget("values")

    w.swap()
    assert (w.left_var.get(), w.right_var.get()) == (RIGHT_URL, LEFT_URL)
    w.swap()

    w.next()
    assert fake.calls[-1] == ("apply_sources", LEFT_URL, RIGHT_URL)
    assert w.step == sw.STEP_CHECK
    fake.states.update(left="connected", right="disconnected")
    w._refresh_check()
    assert _text(w.check_status["left"]) == sw.tr("wizard.check_connected")
    assert _text(w.check_status["right"]) == sw.tr("wizard.check_disconnected")
    assert _shown(w.check_hint)
    # NEXT: no crop controls and nothing to say about cropping.
    assert _text(w.crop_text) == ""
    assert not _shown(w.crop_buttons)
    # An eye that isn't working never blocks the way on.
    assert not _disabled(w.next_btn)

    w.next()  # no calibration step: straight to the end
    assert w.step == sw.STEP_DONE
    summary = _text(w.done_summary)
    assert sw.tr("wizard.mode_etvr") in summary
    assert sw.tr("wizard.done_left", camera=LEFT_URL) in summary
    assert not _shown(w.done_restart)
    assert _text(w.next_btn) == sw.tr("wizard.finish_btn")

    w.next()
    assert fake.calls[-2:] == [("mark_done",), ("show_tracking_page",)]
    assert not w.is_open()
    w.next()  # closed: no-op


def test_two_unnamed_cameras_are_a_guess_and_choices_are_kept(tk_root):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    fake.scans[0]({"USB (COM3)": "COM3", "USB (COM4)": "COM4"}, True)
    assert (w.left_var.get(), w.right_var.get()) == ("USB (COM3)", "USB (COM4)")
    assert _shown(w.cam_guess)
    w.swap()
    assert not _shown(w.cam_guess)
    # The user's choice survives a rescan.
    w.rescan()
    fake.scans[1]({"USB (COM3)": "COM3", "USB (COM4)": "COM4", LEFT_URL: LEFT_URL}, True)
    assert (w.left_var.get(), w.right_var.get()) == ("USB (COM4)", "USB (COM3)")
    w.next()
    assert fake.calls[-1] == ("apply_sources", "COM4", "COM3")
    w.close()


def test_existing_sources_prefill_and_manual_entry(tk_root):
    fake = FakeAdapter(sources=("COM5", None))
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    assert w.left_var.get() == "COM5"
    # The scan skips ports in use, so COM5 is not found, but stays selectable.
    fake.scans[0]({RIGHT_URL: RIGHT_URL}, True)
    assert w.left_var.get() == "COM5"
    assert "COM5" in w.left_combo.cget("values")
    w.right_var.set("192.168.1.20")
    w.next()
    assert fake.calls[-1] == ("apply_sources", "COM5", "192.168.1.20")
    w.back()
    w.right_var.set(sw.tr("wizard.cameras_not_used"))
    w.next()
    assert fake.calls[-1] == ("apply_sources", "COM5", "")
    w.close()


def test_nothing_found_is_not_a_dead_end(tk_root):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    fake.scans[0]({}, True)
    assert _text(w.cam_status) == sw.tr("wizard.cameras_none_found")
    assert _text(w.cam_help) == sw.tr("wizard.cameras_help_etvr")
    assert _shown(w.cam_help)
    assert not _disabled(w.rescan_btn)
    assert not _disabled(w.skip_btn)
    w.rescan_btn.invoke()
    assert len(fake.scans) == 2
    # A late result from the first scan is ignored.
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    assert w.left_var.get() == ""
    assert _text(w.cam_status) == sw.tr("wizard.cameras_searching")
    fake.scans[1]({LEFT_URL: LEFT_URL}, True)
    assert w.left_var.get() == LEFT_URL
    w.close()


def test_bigscreen_uses_one_camera_for_both_eyes(tk_root):
    fake = FakeAdapter(mode="bigscreen")
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    assert w.mode_var.get() == "bigscreen"
    w.next()
    assert not _shown(w.right_combo)
    assert _text(w.left_label) == sw.tr("wizard.cameras_one")
    fake.scans[0]({"Integrated Webcam": "uvc:Integrated Webcam@a", "Bigscreen Bigeye": "uvc:Bigscreen Bigeye@b"}, True)
    assert w.left_var.get() == "Bigscreen Bigeye"
    w.next()
    assert fake.calls[-1] == ("apply_sources", "uvc:Bigscreen Bigeye@b", "uvc:Bigscreen Bigeye@b")
    w.next()
    assert sw.tr("wizard.done_camera", camera="Bigscreen Bigeye") in _text(w.done_summary)
    w.close()


def test_psvr_uses_one_camera_like_the_bigscreen(tk_root):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.mode_var.set("psvr")
    w.next()
    assert fake.calls[-1] == ("set_mode", "psvr")
    assert w.step == sw.STEP_CAMERAS
    assert not _shown(w.right_combo)
    assert _text(w.left_label) == sw.tr("wizard.cameras_one")
    fake.scans[0]({"USB Camera": "uvc:USB Camera@a"}, True)
    assert w.left_var.get() == "USB Camera"  # the only camera: a guess
    w.next()
    assert fake.calls[-1] == ("apply_sources", "uvc:USB Camera@a", "uvc:USB Camera@a")
    w.next()
    summary = _text(w.done_summary)
    assert sw.tr("wizard.done_headset", headset=sw.tr("wizard.mode_psvr")) in summary
    assert sw.tr("wizard.done_camera", camera="USB Camera") in summary
    w.close()


def test_one_eye_only_can_move_on(tk_root):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    assert (w.left_var.get(), w.right_var.get()) == (LEFT_URL, "")
    assert not _disabled(w.next_btn)
    w.next()
    assert fake.calls[-1] == ("apply_sources", LEFT_URL, "")
    fake.states["left"] = "disconnected"
    w._refresh_check()
    assert _text(w.check_status["right"]) == sw.tr("wizard.check_not_used")
    assert not _disabled(w.next_btn)
    w.next()
    assert w.step == sw.STEP_DONE
    w.close()


def test_picking_a_language_retexts_the_wizard(tk_root, monkeypatch):
    catalogs = {"en": sw.tr, "de": lambda key, **fmt: "DE:" + key}
    active = ["en"]
    monkeypatch.setattr(sw, "tr", lambda key, **fmt: catalogs[active[0]](key, **fmt))
    fake = FakeAdapter()
    real_set_language = fake.set_language

    def set_language(code):
        real_set_language(code)
        active[0] = code

    fake.set_language = set_language
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.mode_var.set("bigscreen")
    w.back()
    w.language_radios["de"].invoke()
    assert fake.calls[-1] == ("set_language", "de")
    tk_root.update()  # the rebuild runs once the click is done
    assert _text(w.title_label) == "DE:wizard.language_title"
    assert w.step == sw.STEP_LANGUAGE and w.language_var.get() == "de"
    assert w.mode_var.get() == "bigscreen"  # choices survive
    w.language_radios["de"].invoke()  # already chosen: nothing to do
    assert fake.calls.count(("set_language", "de")) == 1
    w.show_step(sw.STEP_DONE)
    assert _shown(w.done_restart)  # the rest of the window follows on restart
    w.close()


def test_steam_frame_needs_no_scan(tk_root):
    fake = FakeAdapter(modes=("etvr", "bigscreen", "frame"), mode="frame")
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    assert fake.calls[-1] == ("set_mode", "frame")
    assert fake.scans == []
    assert not _shown(w.cam_grid)
    assert not _disabled(w.next_btn)
    w.next()
    assert fake.calls[-1] == ("apply_sources", FRAME_LEFT_SOURCE, FRAME_RIGHT_SOURCE)
    w.close()


def test_switching_headset_on_the_way_back(tk_root):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    w.back()
    assert w.step == sw.STEP_HEADSET
    w.mode_var.set("bigscreen")
    w.next()
    assert fake.calls[-1] == ("set_mode", "bigscreen")
    assert len(fake.scans) == 2  # a fresh scan for the new headset
    w.close()


def test_crop_controls_for_trackers_that_need_one(tk_root):
    fake = FakeAdapter(sources=("COM3", "COM4"), settings=_settings(gui_NEXT=False, gui_LEAP=True))
    fake.states.update(left="connected", right="connected")
    fake.configs["left"].roi_window_w = 0
    w = sw.SetupWizard(tk_root, fake)
    w.show_step(sw.STEP_CHECK)
    assert _text(w.crop_text) == sw.tr("wizard.crop_missing")
    assert _shown(w.crop_full_btn) and _shown(w.crop_adjust_btn)

    w.crop_full_btn.invoke()
    assert [side for side, _cb in fake.frame_requests] == ["left"]  # only the eye without a crop
    assert _disabled(w.crop_full_btn)
    assert _text(w.crop_result) == sw.tr("wizard.crop_waiting")
    fake.frame_requests[0][1]((480, 640, 3))
    assert fake.calls[-1] == ("set_roi", "left", (0, 0, 640, 480))
    assert _text(w.crop_result) == sw.tr("wizard.crop_full_done")
    # Now every eye has a crop: only the adjust button is left.
    assert _text(w.crop_text) == sw.tr("wizard.crop_set")
    assert not _shown(w.crop_full_btn) and _shown(w.crop_adjust_btn)

    # Before leaving for the Tracking page, the way back is spelled out.
    assert _shown(w.crop_where)
    assert sw.tr("wizard.continue_btn") in _text(w.crop_where)
    w.crop_adjust_btn.invoke()
    assert fake.calls[-1] == ("open_crop_mode",)

    # No picture in time: say so, and allow another try.
    fake.configs["right"].roi_window_h = 0
    w._refresh_check()
    w.crop_full_btn.invoke()
    fake.frame_requests[-1][1](None)
    assert _text(w.crop_result) == sw.tr("wizard.crop_no_picture")
    assert not _disabled(w.crop_full_btn)
    w.close()


def test_skip_marks_done_on_every_step(tk_root):
    for step in range(sw.STEP_COUNT):
        fake = FakeAdapter()
        w = sw.SetupWizard(tk_root, fake)
        w.show_step(step)
        assert _shown(w.skip_btn) and not _disabled(w.skip_btn)
        w.skip_btn.invoke()
        assert fake.calls[-2:] == [("mark_done",), ("show_tracking_page",)]
        assert not w.is_open()
    # Results that arrive after closing are ignored.
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.next()  # language
    w.next()
    w.skip()
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    w.rescan()
    w.back()
    w.use_full_frame()
    w._rebuild()
    w.pause()
    w.resume()
    w.skip()
    w.close()
    assert fake.calls.count(("mark_done",)) == 1


def test_closing_the_main_window_with_the_wizard_open(tk_root):
    import tkinter as tk

    root = tk.Toplevel(tk_root)  # stands in for the main window
    fake = FakeAdapter(sources=("COM3", None), settings=_settings(gui_NEXT=False, gui_LEAP=True))
    fake.states["left"] = "connected"
    fake.configs["left"].roi_window_w = 0
    w = sw.SetupWizard(root, fake)
    w.next()  # language
    w.next()
    w.show_step(sw.STEP_CHECK)
    w.crop_full_btn.invoke()
    root.destroy()
    # Late background results after the main window is gone must not raise.
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    fake.frame_requests[0][1]((480, 640, 3))
    w._on_scan_update(w._scan_gen, {}, True)
    w._poll()
    assert not w.is_open()
    w.close()


# ---------------------------------------------------------------------------
# WizardPage: the wizard in place of the main window's pages
# ---------------------------------------------------------------------------


class _MainWindow:
    """AppUI's page switching (show_page in eyetrackapp.py), reduced to what WizardPage relies on."""

    def __init__(self, root, **adapter_kw):
        import tkinter as tk
        from tkinter import ttk

        self.top = tk.Toplevel(root)
        self.nav = ttk.Frame(self.top)
        self.nav.pack(fill="x", padx=16, pady=(16, 4))
        ttk.Button(self.nav, text="Tracking").pack(side="left")
        self.content = ttk.Frame(self.top)
        self.content.pack(fill="both", expand=True, padx=8, pady=(0, 16))
        self.pages = {"tracking": ttk.Frame(self.content), "settings": ttk.Frame(self.content)}
        # The "Setup wizard" button under Scan/Connect.
        self.button = ttk.Button(self.pages["tracking"], text=sw.tr("wizard.open_btn"))
        self.button.pack()
        self.adapters = []
        self._adapter_kw = adapter_kw
        self.wizard_page = sw.WizardPage(self.content, self.nav, self.button, self._new_adapter)
        self.current_page = None
        self.show_page("tracking")

    def _new_adapter(self):
        adapter = FakeAdapter(show_page=self.show_page, **self._adapter_kw)
        self.adapters.append(adapter)
        return adapter

    def show_page(self, page_name):
        self.current_page = page_name
        for frame in self.pages.values():
            frame.pack_forget()
        if not self.wizard_page.sync(page_name):
            page_name = self.current_page = "tracking"
        if page_name in self.pages:
            self.pages[page_name].pack(fill="both", expand=True)

    def showing(self):
        return self.content.pack_slaves()

    def nav_shown(self):
        # Back in its place above the pages.
        return _shown(self.nav) and self.top.pack_slaves() == [self.nav, self.content]


def _assert_wizard_showing(win, wizard):
    assert win.current_page == "wizard"
    assert win.showing() == [wizard.frame]
    assert not _shown(win.nav)
    assert win.wizard_page.visible and not win.wizard_page.paused


def _assert_page_showing(win, page, paused):
    assert win.current_page == page
    assert win.showing() == [win.pages[page]]
    assert win.nav_shown()
    assert not win.wizard_page.visible
    assert win.wizard_page.paused is paused
    assert _text(win.button) == sw.tr("wizard.continue_btn" if paused else "wizard.open_btn")
    assert str(win.button.cget("style")) == ("Accent.TButton" if paused else "TButton")


def test_wizard_page_takes_over_the_window(tk_root):
    win = _MainWindow(tk_root)
    _assert_page_showing(win, "tracking", paused=False)
    win.show_page("wizard")  # the Setup wizard button
    w = win.wizard_page.wizard
    _assert_wizard_showing(win, w)
    assert w.step == sw.STEP_LANGUAGE
    # Showing it again changes nothing.
    win.show_page("wizard")
    assert win.wizard_page.wizard is w
    _assert_wizard_showing(win, w)


def test_first_run_opens_on_the_wizard_page(tk_root, monkeypatch):
    monkeypatch.setattr(EyeTrackConfig, "save", lambda self: None)
    win = _MainWindow(tk_root)
    assert sw.run_first_run_check(win.top, _config(), lambda: win.show_page("wizard")) == "open"
    _assert_wizard_showing(win, win.wizard_page.wizard)
    # An existing user stays on the Tracking page.
    win2 = _MainWindow(tk_root)
    assert sw.run_first_run_check(win2.top, _config(left="COM3"), lambda: win2.show_page("wizard")) == "mark_done"
    _assert_page_showing(win2, "tracking", paused=False)


def test_crop_pauses_and_continue_setup_resumes_at_the_same_step(tk_root):
    win = _MainWindow(tk_root, settings=_settings(gui_NEXT=False, gui_LEAP=True))
    win.show_page("wizard")
    w = win.wizard_page.wizard
    fake = win.adapters[0]
    w.next()  # language
    w.next()
    fake.scans[0]({"USB (COM3)": "COM3", "USB (COM4)": "COM4"}, True)
    w.swap()  # a choice to keep
    w.next()
    assert fake.calls[-1] == ("apply_sources", "COM4", "COM3")
    assert w.step == sw.STEP_CHECK
    assert _shown(w.crop_adjust_btn)

    w.crop_adjust_btn.invoke()
    assert fake.calls[-1] == ("open_crop_mode",)
    # The Tracking page in cropping mode, with the navigation back.
    _assert_page_showing(win, "tracking", paused=True)
    assert w.is_open() and w.paused
    assert w._poll_id is None  # nothing polls a hidden page

    win.button.configure(command=lambda: win.show_page("wizard"))
    win.button.invoke()  # Continue setup
    assert win.wizard_page.wizard is w
    _assert_wizard_showing(win, w)
    assert w.step == sw.STEP_CHECK
    assert fake.calls[-1] == ("leave_crop_mode",)
    assert (w.left_var.get(), w.right_var.get()) == ("USB (COM4)", "USB (COM3)")
    assert w._poll_id is not None
    assert len(win.adapters) == 1

    # Back to the cameras: still the user's choice, and no new scan.
    w.back()
    assert (w.left_var.get(), w.right_var.get()) == ("USB (COM4)", "USB (COM3)")
    assert len(fake.scans) == 1


def test_skip_and_finish_give_the_window_back(tk_root):
    for finish in (False, True):
        win = _MainWindow(tk_root)
        win.show_page("wizard")
        w = win.wizard_page.wizard
        fake = win.adapters[0]
        if finish:
            w.show_step(sw.STEP_DONE)
            w.next()
        else:
            w.skip_btn.invoke()
        assert fake.calls[-2:] == [("mark_done",), ("show_tracking_page",)]
        assert not w.is_open()
        _assert_page_showing(win, "tracking", paused=False)
        assert win.wizard_page.wizard is None
        # The button starts over at step 1.
        win.show_page("wizard")
        assert win.wizard_page.wizard is not w
        assert win.wizard_page.wizard.step == sw.STEP_LANGUAGE
        assert len(win.adapters) == 2
        _assert_wizard_showing(win, win.wizard_page.wizard)


def test_another_page_opened_while_the_wizard_shows(tk_root):
    win = _MainWindow(tk_root)
    win.show_page("wizard")
    w = win.wizard_page.wizard
    w.next()  # language
    w.next()
    win.show_page("settings")  # e.g. a settings deep link
    _assert_page_showing(win, "settings", paused=True)
    win.show_page("tracking")
    _assert_page_showing(win, "tracking", paused=True)
    win.show_page("wizard")
    _assert_wizard_showing(win, w)
    assert w.step == sw.STEP_CAMERAS


def test_a_wizard_that_cannot_open_leaves_the_navigation(tk_root):
    win = _MainWindow(tk_root)
    win.wizard_page._make_adapter = lambda: 1 / 0
    win.show_page("wizard")
    _assert_page_showing(win, "tracking", paused=False)


def test_closing_the_main_window_on_the_wizard_page(tk_root):
    win = _MainWindow(tk_root, sources=("COM3", None), settings=_settings(gui_NEXT=False, gui_LEAP=True))
    win.show_page("wizard")
    w = win.wizard_page.wizard
    fake = win.adapters[0]
    w.next()  # language
    w.next()
    fake.states["left"] = "connected"
    fake.configs["left"].roi_window_w = 0
    w.show_step(sw.STEP_CHECK)
    w.crop_full_btn.invoke()
    assert w._after_ids  # the scan watchdog and the poll
    win.top.destroy()
    assert not w.is_open()
    assert w._after_ids == set()  # no timer left to fire into destroyed widgets
    # Late background results and page switches after the window is gone must not raise.
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    fake.frame_requests[0][1]((480, 640, 3))
    w._on_scan_update(w._scan_gen, {}, True)
    w._poll()
    w.pause()
    w.resume()
    win.wizard_page.sync("tracking")
    tk_root.update()
    assert win.wizard_page.wizard is None
