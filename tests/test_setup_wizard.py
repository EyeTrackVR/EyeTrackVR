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

    # Rotation: the eye's Rotation slider follows, or it would write its old value back.
    saves.clear()
    left_eye.rotation_var = _Var(0)
    adapter.set_rotation("left", 90)
    assert config.left_eye.rotation_angle == 90 and adapter.get_rotation("left") == 90
    assert left_eye.rotation_var.get() == 90
    assert left_eye.cartesian_needs_update is True
    assert saves

    adapter.mark_done()
    assert config.settings.gui_setup_wizard_done is True


def test_adapter_reads_one_picture_and_removes_its_tap():
    config = EyeTrackConfig()
    app = _fake_app(config)
    eye = _Eye(config.left_eye)
    other = queue.Queue()
    eye.camera._extra_output_queues = [other]
    adapter = sw.AppAdapter(app, config, [_Eye(config.right_eye), eye])
    pictures = []
    adapter.request_frame("left", pictures.append)
    tap = eye.camera._extra_output_queues[-1]
    assert tap is not other
    app.root.run_pending()  # nothing yet
    assert pictures == []
    picture = np.zeros((480, 640, 3), np.uint8)
    tap.put((picture, 1, 30.0, 0.0))
    app.root.run_pending()
    assert len(pictures) == 1 and pictures[0] is picture
    assert eye.camera._extra_output_queues == [other]


def test_adapter_picture_request_gives_up():
    config = EyeTrackConfig()
    app = _fake_app(config)
    eye = _Eye(config.left_eye)
    adapter = sw.AppAdapter(app, config, [_Eye(config.right_eye), eye])
    pictures = []
    adapter.request_frame("left", pictures.append)
    for _ in range(100):
        app.root.run_pending()
    assert pictures == [None]
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
        self.picture_requests = []
        self.states = {side: "none" for side in sw.SIDES}
        self.configs = {side: types.SimpleNamespace(rotation_angle=0) for side in sw.SIDES}

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

    def request_frame(self, side, callback):
        self.picture_requests.append((side, callback))

    def get_rotation(self, side):
        return self.configs[side].rotation_angle

    def set_rotation(self, side, degrees):
        self.calls.append(("set_rotation", side, degrees))
        self.configs[side].rotation_angle = degrees

    def show_tracking_page(self):
        self.calls.append(("show_tracking_page",))
        if self.show_page:
            self.show_page("tracking")

    def mark_done(self):
        self.calls.append(("mark_done",))

    # Foveated rendering step
    foveation = True
    installable = True
    installed = (False, False)
    install_result = None

    def foveation_on(self):
        return self.foveation

    def set_foveation(self, on):
        self.calls.append(("set_foveation", on))
        self.foveation = on

    def dfr_installable(self):
        return self.installable

    def dfr_installed(self):
        return self.installed

    def install_dfr(self, progress):
        self.calls.append(("install_dfr",))
        progress("system_files")
        if self.install_result is None:
            self.installed = (True, True)
        return self.install_result

    def finish_dfr_install(self):
        self.calls.append(("finish_dfr_install",))


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
    assert w.step == sw.STEP_ROTATE
    assert _text(w.title_label) == sw.tr("wizard.rotate_title")
    assert _shown(w.rotate_cols["left"]) and _shown(w.rotate_cols["right"])
    assert not _shown(w.rotate_none)
    # A camera without a picture yet never blocks the way on.
    assert not _disabled(w.next_btn)

    w.next()  # no check or calibration step
    assert w.step == sw.STEP_FOVEATION
    w.next()
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
    w.next()  # rotation
    w.next()  # foveated rendering
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
    w.next()  # rotation
    w.next()  # foveated rendering
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
    # Only the eye in use is shown to turn.
    assert _shown(w.rotate_cols["left"]) and not _shown(w.rotate_cols["right"])
    w.next()  # rotation
    assert w.step == sw.STEP_FOVEATION
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


@pytest.mark.parametrize(
    "angle, choice", [(0, 0), (90, 90), (180.0, 180), (270, 270), (360, 0), (-90, 270), (45, None), ("x", None)]
)
def test_rotation_choice(angle, choice):
    assert sw.rotation_choice(angle) == choice


def test_preview_turns_the_picture_like_the_tracker():
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    # A wide picture with a white mark in its top-left corner.
    image = np.zeros((40, 80, 3), dtype=np.uint8)
    image[:4, :4] = 255
    for degrees in sw.ROTATIONS:
        shown = sw.preview_image(image, "etvr", "left", degrees, 80)
        # The tracker's own turn (eye_processor: cv2.getRotationMatrix2D, counter-clockwise).
        turned = np.rot90(image, k=degrees // 90)
        assert shown.shape[:2] == turned.shape[:2]
        mark = np.argwhere(turned[:, :, 0] == 255).mean(axis=0)
        assert np.allclose(np.argwhere(shown[:, :, 0] > 127).mean(axis=0), mark, atol=1.5)
    matrix = cv2.getRotationMatrix2D((39.5, 39.5), 90, 1)
    square = np.zeros((80, 80), dtype=np.uint8)
    square[:4, :4] = 255
    assert np.argwhere(cv2.warpAffine(square, matrix, (80, 80)) > 127).mean(axis=0)[0] > 40  # top-left -> bottom-left
    assert np.argwhere(np.rot90(square)).mean(axis=0)[0] > 40
    # Bigscreen: each eye's half, fitted to the box.
    assert sw.preview_image(image, "bigscreen", "right", 90, 20).shape == (20, 20, 3)
    gray = np.zeros((10, 20), dtype=np.uint8)
    assert sw.preview_image(gray, "etvr", "left", 0, 20).shape == (10, 20, 3)


def test_rotation_step_sets_each_eye_and_shows_live_pictures(tk_root):
    np = pytest.importorskip("numpy")
    fake = FakeAdapter(sources=("COM3", "COM4"))
    fake.states.update(left="connecting", right="connecting")
    fake.configs["right"].rotation_angle = 45  # set with the Tracking page slider
    w = sw.SetupWizard(tk_root, fake)
    w.show_step(sw.STEP_ROTATE)
    assert _text(w.rotate_previews["left"]) == sw.tr("wizard.rotate_waiting")
    accent = {
        side: [d for d, b in w.rotate_buttons[side].items() if b.cget("style") == "Accent.TButton"] for side in sw.SIDES
    }
    assert accent == {"left": [0], "right": []}

    w.rotate_buttons["left"][270].invoke()
    assert fake.calls[-1] == ("set_rotation", "left", 270)
    assert [d for d, b in w.rotate_buttons["left"].items() if b.cget("style") == "Accent.TButton"] == [270]

    # One picture request per eye at a time; each answer asks for the next.
    assert [side for side, _cb in fake.picture_requests] == ["left", "right"]
    w._refresh_rotate()
    assert len(fake.picture_requests) == 2
    fake.picture_requests[0][1](np.zeros((40, 80, 3), dtype=np.uint8))
    assert _text(w.rotate_previews["left"]) == ""
    assert w.rotate_previews["left"].image is not None
    w._refresh_rotate()
    assert [side for side, _cb in fake.picture_requests[2:]] == ["left"]
    fake.picture_requests[1][1](None)  # no picture in time
    assert _text(w.rotate_previews["right"]) == sw.tr("wizard.rotate_waiting")

    # No camera chosen: nothing to turn.
    fake.states.update(left="none", right="none")
    w.show_step(sw.STEP_ROTATE)
    assert _shown(w.rotate_none)
    assert not _shown(w.rotate_cols["left"]) and not _shown(w.rotate_cols["right"])
    w.close()
    fake.picture_requests[-1][1](np.zeros((4, 4, 3), dtype=np.uint8))  # late: ignored


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
    w.set_rotation("left", 90)
    w._rebuild()
    w.pause()
    w.resume()
    w.skip()
    w.close()
    assert fake.calls.count(("mark_done",)) == 1


def test_closing_the_main_window_with_the_wizard_open(tk_root):
    import tkinter as tk

    root = tk.Toplevel(tk_root)  # stands in for the main window
    fake = FakeAdapter(sources=("COM3", None))
    fake.states["left"] = "connected"
    w = sw.SetupWizard(root, fake)
    w.next()  # language
    w.next()
    w.show_step(sw.STEP_ROTATE)
    root.destroy()
    # Late background results after the main window is gone must not raise.
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    fake.picture_requests[0][1](np.zeros((48, 64, 3), np.uint8))
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


def test_another_page_pauses_and_continue_setup_resumes_at_the_same_step(tk_root):
    win = _MainWindow(tk_root)
    win.show_page("wizard")
    w = win.wizard_page.wizard
    fake = win.adapters[0]
    w.next()  # language
    w.next()
    fake.scans[0]({"USB (COM3)": "COM3", "USB (COM4)": "COM4"}, True)
    w.swap()  # a choice to keep
    w.next()
    assert fake.calls[-1] == ("apply_sources", "COM4", "COM3")
    assert w.step == sw.STEP_ROTATE
    assert w._poll_id is not None  # the live pictures

    win.show_page("tracking")  # other code opening a page
    _assert_page_showing(win, "tracking", paused=True)
    assert w.is_open() and w.paused
    assert w._poll_id is None  # nothing polls a hidden page

    win.button.configure(command=lambda: win.show_page("wizard"))
    win.button.invoke()  # Continue setup
    assert win.wizard_page.wizard is w
    _assert_wizard_showing(win, w)
    assert w.step == sw.STEP_ROTATE
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
    win = _MainWindow(tk_root, sources=("COM3", None))
    win.show_page("wizard")
    w = win.wizard_page.wizard
    fake = win.adapters[0]
    w.next()  # language
    w.next()
    fake.states["left"] = "connected"
    w.show_step(sw.STEP_ROTATE)
    assert w._after_ids  # the scan watchdog and the picture poll
    win.top.destroy()
    assert not w.is_open()
    assert w._after_ids == set()  # no timer left to fire into destroyed widgets
    # Late background results and page switches after the window is gone must not raise.
    fake.scans[0]({LEFT_URL: LEFT_URL}, True)
    fake.picture_requests[0][1](np.zeros((48, 64, 3), np.uint8))
    w._on_scan_update(w._scan_gen, {}, True)
    w._poll()
    w.pause()
    w.resume()
    win.wizard_page.sync("tracking")
    tk_root.update()
    assert win.wizard_page.wizard is None


def test_foveation_step_installs_both_tools(tk_root, monkeypatch):
    fake = FakeAdapter()
    w = sw.SetupWizard(tk_root, fake)
    w.show_step(sw.STEP_FOVEATION)
    assert w.foveation_var.get() is True
    assert _shown(w.dfr_box) and _shown(w.dfr_install_btn) and not _disabled(w.dfr_install_btn)
    assert _text(w.dfr_status["PimaxMagic4All"]) == sw.tr("wizard.foveation_missing")
    assert _text(w.dfr_message) == sw.tr("wizard.foveation_hint")

    # The worker thread runs inline here; its result comes back through after(0).
    class Inline:
        def __init__(self, target, **_):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(sw.threading, "Thread", Inline)
    w.install_dfr()
    tk_root.update()
    assert ("install_dfr",) in fake.calls and fake.calls[-1] == ("finish_dfr_install",)
    assert _text(w.dfr_status["Quad-Views-Foveated"]) == sw.tr("wizard.foveation_installed")
    assert not _shown(w.dfr_install_btn) and not _shown(w.dfr_message)

    # Turning support off hides the install part and saves the setting.
    w.foveation_cb.invoke()
    assert fake.calls[-1] == ("set_foveation", False) and not _shown(w.dfr_box)
    w.close()


def test_foveation_step_reports_a_failed_install(tk_root, monkeypatch):
    fake = FakeAdapter()
    fake.install_result = "system_files_failed"
    w = sw.SetupWizard(tk_root, fake)
    w.show_step(sw.STEP_FOVEATION)

    class Inline:
        def __init__(self, target, **_):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(sw.threading, "Thread", Inline)
    w.install_dfr()
    tk_root.update()
    assert _text(w.dfr_message) == sw.tr("dfr.setup_system_files_failed")
    assert _shown(w.dfr_install_btn) and not _disabled(w.dfr_install_btn)
    assert ("finish_dfr_install",) not in fake.calls
    w.close()


def test_foveation_step_without_installs_only_has_the_switch(tk_root):
    fake = FakeAdapter()
    fake.installable = False  # Linux: the gaze outputs only
    w = sw.SetupWizard(tk_root, fake)
    w.show_step(sw.STEP_FOVEATION)
    assert _shown(w.foveation_cb) and not _shown(w.dfr_box)
    w.close()
