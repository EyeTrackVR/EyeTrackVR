"""
EyeTrackVR's panel in the SteamVR dashboard: recenter, calibrate, a gaze marker and the
per-game foveated rendering switch, without taking the headset off.

Runs inside the SteamVR companion process (ovr/dfr_monitor.py), which already holds an
OpenVR session. The app sends what to show as one JSON "state" message (labels already
translated, see DfrController.dashboard_state); a click goes back as an "action"
message and the app does the work. This side only draws and hit-tests, so it never
needs the app's settings, models or cameras.

  app -> here  {"type": "state", "labels": {...}, "game": "...", "note": "...", "dfr_supported": true,
                "dfr": {"available": true, "enabled": false, "mode": "balanced", "key": "steam.app.1"}}
  here -> app  {"type": "action", "name": "recenter" | "recalibrate"}
               {"type": "action", "name": "dfr_enabled", "key": "steam.app.1", "value": true}
               {"type": "action", "name": "dfr_mode", "key": "steam.app.1", "value": "maximum"}
               {"type": "action", "name": "dfr_invert_y", "key": "steam.app.1", "value": true}

The gaze marker is handled here alone: a ring in the headset where EyeTrackVR says the
user is looking, read from the gaze shared memory. It shows whether gaze reaches VR and
lines up, in any game, whatever that game does with it.
"""

import ctypes
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

OVERLAY_KEY = "etvr.dashboard"
OVERLAY_NAME = "EyeTrackVR"
WIDTH, HEIGHT = 1000, 560
WIDTH_METERS = 2.0
QUALITIES = ("maximum", "balanced", "minimum", "debug")

MARKER_KEY = "etvr.gaze_marker"
MARKER_PIXELS = 256
MARKER_DISTANCE_M = 1.5
MARKER_WIDTH_M = 0.09  # about 3.5 degrees across
MARKER_STALE_S = 0.5  # hide it when the app stops publishing

BACKGROUND = (28, 28, 30, 255)
PANEL = (44, 44, 48, 255)
TEXT = (235, 235, 240, 255)
MUTED = (160, 160, 168, 255)
BUTTON = (62, 62, 70, 255)
BUTTON_ACTIVE = (0, 120, 212, 255)
BUTTON_DISABLED = (52, 52, 57, 255)
TEXT_DISABLED = (110, 110, 118, 255)

DEFAULT_LABELS = {
    "recenter": "Recenter",
    "calibrate": "Calibrate",
    "gaze_marker": "Gaze marker",
    "dfr_title": "Foveated rendering",
    "dfr_on": "On for this game",
    "dfr_off": "Off for this game",
    "flip_vertical": "Flip vertical",
    "quality_maximum": "Maximum",
    "quality_balanced": "Balanced",
    "quality_minimum": "Minimum",
    "quality_debug": "Debug view",
}


@dataclass(frozen=True)
class Button:
    name: str  # action name
    rect: tuple[int, int, int, int]  # left, top, right, bottom, in panel pixels (top-left origin)
    label: str
    enabled: bool = True
    active: bool = False
    value: object = None


def _row(names: int, top: int, bottom: int, left: int = 40, gap: int = 16) -> list[tuple[int, int, int, int]]:
    width = (WIDTH - 2 * left - gap * (names - 1)) // names
    return [(left + i * (width + gap), top, left + i * (width + gap) + width, bottom) for i in range(names)]


def layout(state: dict) -> list[Button]:
    """The buttons for a state. Shared by drawing and hit-testing, so they can't disagree.
    ``state["marker"]`` is this side's own gaze marker switch."""
    labels = {**DEFAULT_LABELS, **(state.get("labels") or {})}
    dfr = state.get("dfr") or {}
    available = bool(dfr.get("available"))
    enabled = bool(dfr.get("enabled"))
    marker = bool(state.get("marker"))
    top = _row(3, 100, 190)
    buttons = [
        Button("recenter", top[0], labels["recenter"]),
        Button("recalibrate", top[1], labels["calibrate"]),
        Button("gaze_marker", top[2], labels["gaze_marker"], active=marker, value=not marker),
    ]
    if not state.get("dfr_supported", True):
        return buttons  # per-game foveated rendering is Windows-only
    buttons += [
        Button(
            "dfr_enabled",
            (40, 350, 650, 430),
            labels["dfr_on"] if enabled else labels["dfr_off"],
            enabled=available,
            active=available and enabled,
            value=not enabled,
        ),
        # Some engines (Unity) render upside down; the Debug view shows whether to flip.
        Button(
            "dfr_invert_y",
            (666, 350, 960, 430),
            labels["flip_vertical"],
            enabled=available and enabled,
            active=available and enabled and bool(dfr.get("invert_y")),
            value=not dfr.get("invert_y"),
        ),
    ]
    for rect, quality in zip(_row(len(QUALITIES), 450, 520), QUALITIES):
        buttons.append(
            Button(
                "dfr_mode",
                rect,
                labels[f"quality_{quality}"],
                enabled=available and enabled,
                active=available and enabled and dfr.get("mode") == quality,
                value=quality,
            )
        )
    return buttons


def hit(buttons: list[Button], x: float, y: float) -> Button | None:
    """The enabled button under a panel pixel (top-left origin), if any."""
    for button in buttons:
        left, top, right, bottom = button.rect
        if button.enabled and left <= x < right and top <= y < bottom:
            return button
    return None


def action_for(button: Button, state: dict) -> dict:
    message = {"type": "action", "name": button.name}
    if button.name.startswith("dfr_"):
        message.update(key=str((state.get("dfr") or {}).get("key") or ""), value=button.value)
    return message


# ---------------------------------------------------------------- drawing


def _bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _font_files(text: str) -> list[str]:
    """Fonts to try, most suitable first. The bundled font has no CJK glyphs, so text
    with any goes to a system font."""
    bundled = [
        _bundle_dir() / "tools" / "assets" / "OpenSans-Regular.ttf",
        _bundle_dir().parent / "overlay" / "dist" / "windows" / "assets" / "OpenSans-Regular.ttf",
    ]
    if sys.platform == "win32":
        fonts = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts"
        latin = [fonts / "segoeui.ttf"]
        wide = [fonts / "YuGothM.ttc", fonts / "meiryo.ttc", fonts / "msyh.ttc", fonts / "msgothic.ttc"]
    else:
        latin = [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        wide = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
        ]
    needs_wide = any(ord(char) >= 0x2E80 for char in text)
    order = wide + latin + bundled if needs_wide else latin + bundled + wide
    return [str(path) for path in order if path.is_file()]


_fonts: dict = {}


def _font(text: str, size: int):
    from PIL import ImageFont

    for path in _font_files(text):
        key = (path, size)
        if key not in _fonts:
            try:
                _fonts[key] = ImageFont.truetype(path, size)
            except OSError:
                _fonts[key] = None
        if _fonts[key] is not None:
            return _fonts[key]
    return ImageFont.load_default()


def _fit(draw, text: str, size: int, max_width: int):
    """The largest font up to ``size`` that keeps the text inside ``max_width``."""
    while size > 14:
        font = _font(text, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 2
    return _font(text, size)


def _draw_switch(draw, button: Button) -> None:
    """An on/off switch with its label: the knob's side and the track colour show the
    state at a glance, where a button's wording alone did not."""
    left, top, right, bottom = button.rect
    middle = (top + bottom) // 2
    track = (left, middle - 30, left + 116, middle + 30)
    colour = BUTTON_ACTIVE if button.active else BUTTON if button.enabled else BUTTON_DISABLED
    draw.rounded_rectangle(track, radius=30, fill=colour)
    knob_x = track[2] - 30 if button.active else track[0] + 30
    knob = TEXT if button.enabled else TEXT_DISABLED
    draw.ellipse((knob_x - 22, middle - 22, knob_x + 22, middle + 22), fill=knob)
    font = _fit(draw, button.label, 30, right - track[2] - 28)
    box = draw.textbbox((0, 0), button.label, font=font)
    draw.text(
        (track[2] + 20, middle - (box[3] + box[1]) / 2),
        button.label,
        font=font,
        fill=TEXT if button.enabled else TEXT_DISABLED,
    )


def render(state: dict):
    """The panel as an RGBA PIL image."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    labels = {**DEFAULT_LABELS, **(state.get("labels") or {})}
    draw.text((40, 30), OVERLAY_NAME, font=_font(OVERLAY_NAME, 40), fill=TEXT)

    supported = state.get("dfr_supported", True)
    if supported:
        draw.rounded_rectangle((24, 222, WIDTH - 24, HEIGHT - 20), radius=18, fill=PANEL)
        draw.text((40, 240), labels["dfr_title"], font=_fit(draw, labels["dfr_title"], 30, 920), fill=TEXT)
    game = str(state.get("game") or "") if supported else ""
    if game:
        draw.text((40, 284), game, font=_fit(draw, game, 26, 920), fill=TEXT)
    note = str(state.get("note") or "") if supported else ""  # why this game has no switch
    if note:
        draw.text((40, 318), note, font=_fit(draw, note, 20, 920), fill=MUTED)

    for button in layout(state):
        left, top, right, bottom = button.rect
        if button.name == "dfr_enabled":
            _draw_switch(draw, button)
            continue
        fill = BUTTON_ACTIVE if button.active else BUTTON if button.enabled else BUTTON_DISABLED
        draw.rounded_rectangle(button.rect, radius=14, fill=fill)
        font = _fit(draw, button.label, 30, right - left - 24)
        width = draw.textlength(button.label, font=font)
        box = draw.textbbox((0, 0), button.label, font=font)
        draw.text(
            ((left + right - width) / 2, (top + bottom - (box[3] + box[1])) / 2),
            button.label,
            font=font,
            fill=TEXT if button.enabled else TEXT_DISABLED,
        )
    return image


def render_marker():
    """The gaze marker: a ring with a centre dot, see-through in between."""
    from PIL import Image, ImageDraw

    size = MARKER_PIXELS
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, size - 10, size - 10), outline=(0, 0, 0, 200), width=26)
    draw.ellipse((16, 16, size - 16, size - 16), outline=(0, 230, 120, 255), width=14)
    centre = size // 2
    draw.ellipse((centre - 14, centre - 14, centre + 14, centre + 14), fill=(0, 230, 120, 255), outline=(0, 0, 0, 200))
    return image


def _raw(image):
    pixels = image.tobytes()
    return (ctypes.c_ubyte * len(pixels)).from_buffer_copy(pixels)


# ---------------------------------------------------------------- gaze marker


def gaze_direction(sample: dict | None) -> tuple[float, float, float] | None:
    """Unit gaze direction in head space (+X right, +Y up, -Z forward) from a gaze shared
    memory sample: the combined gaze, else the mean of the eyes that are valid."""
    from osc.gaze_shared_memory import FLAG_GAZE_VALID

    if not sample:
        return None
    eyes = sample.get("eyes") or []
    valid = [eye.direction for eye in eyes if eye.flags & FLAG_GAZE_VALID]
    if len(eyes) >= 3 and eyes[2].flags & FLAG_GAZE_VALID:
        valid = [eyes[2].direction]
    if not valid:
        return None
    x, y, z = (sum(axis) / len(valid) for axis in zip(*valid))
    length = math.sqrt(x * x + y * y + z * z)
    if not math.isfinite(length) or length < 1e-6 or z >= 0:
        return None  # nonsense, or looking backwards
    return x / length, y / length, z / length


def marker_transform(direction: tuple[float, float, float], distance: float = MARKER_DISTANCE_M):
    """Rows of the head-relative 3x4 matrix that puts the marker ``distance`` metres along
    ``direction``, facing the eyes."""
    dx, dy, dz = direction
    back = (-dx, -dy, -dz)  # the marker's +Z: from it toward the viewer
    # right = up x back, with world up (0, 1, 0); never degenerate for a forward gaze
    rx, ry, rz = back[2], 0.0, -back[0]
    length = math.sqrt(rx * rx + rz * rz) or 1.0
    rx, rz = rx / length, rz / length
    ux, uy, uz = back[1] * rz - back[2] * ry, back[2] * rx - back[0] * rz, back[0] * ry - back[1] * rx
    return (
        (rx, ux, back[0], dx * distance),
        (ry, uy, back[1], dy * distance),
        (rz, uz, back[2], dz * distance),
    )


def _read_gaze_sample() -> dict | None:
    from ovr.gaze_selftest import read_gaze_block

    return read_gaze_block().sample


class GazeMarker:
    """A ring in the headset at the published gaze direction."""

    def __init__(self, openvr, read_sample=_read_gaze_sample, clock=time.monotonic):
        self.openvr = openvr
        self.overlay = openvr.VROverlay()
        self.read_sample = read_sample
        self.clock = clock
        self.handle = self.overlay.createOverlay(MARKER_KEY, "EyeTrackVR gaze marker")
        self.overlay.setOverlayWidthInMeters(self.handle, MARKER_WIDTH_M)
        self.overlay.setOverlayRaw(self.handle, _raw(render_marker()), MARKER_PIXELS, MARKER_PIXELS, 4)
        self.visible = False
        self._count = None
        self._changed_at = -1e9

    def update(self) -> None:
        """Move the marker to the newest gaze sample; hide it when there is none."""
        sample = self.read_sample()
        now = self.clock()
        if sample and sample.get("sample_count") != self._count:
            self._count, self._changed_at = sample.get("sample_count"), now
        direction = gaze_direction(sample) if now - self._changed_at <= MARKER_STALE_S else None
        if direction is None:
            self._show(False)
            return
        matrix = self.openvr.HmdMatrix34_t()
        for row, values in enumerate(marker_transform(direction)):
            for column, value in enumerate(values):
                matrix.m[row][column] = value
        self.overlay.setOverlayTransformTrackedDeviceRelative(
            self.handle, self.openvr.k_unTrackedDeviceIndex_Hmd, matrix
        )
        self._show(True)

    def _show(self, visible: bool) -> None:
        if visible != self.visible:
            (self.overlay.showOverlay if visible else self.overlay.hideOverlay)(self.handle)
            self.visible = visible

    def close(self) -> None:
        try:
            self.overlay.destroyOverlay(self.handle)
        except Exception:
            pass


# ---------------------------------------------------------------- overlay


class Dashboard:
    """The dashboard overlay. ``emit`` sends a message to the app."""

    def __init__(self, openvr, emit, icon_path: str = "", read_sample=_read_gaze_sample):
        self.openvr = openvr
        self.emit = emit
        self.overlay = openvr.VROverlay()
        self.state: dict = {}
        self.marker: GazeMarker | None = None
        self._read_sample = read_sample
        self._drawn: dict | None = None
        self._event = openvr.VREvent_t()
        self.handle, thumbnail = self.overlay.createDashboardOverlay(OVERLAY_KEY, OVERLAY_NAME)
        self.overlay.setOverlayWidthInMeters(self.handle, WIDTH_METERS)
        self.overlay.setOverlayInputMethod(self.handle, openvr.VROverlayInputMethod_Mouse)
        scale = openvr.HmdVector2_t()
        scale.v[0], scale.v[1] = float(WIDTH), float(HEIGHT)
        self.overlay.setOverlayMouseScale(self.handle, scale)
        if icon_path and os.path.isfile(icon_path):
            try:
                self.overlay.setOverlayFromFile(thumbnail, icon_path)
            except Exception:
                pass  # the tab just shows its name

    @property
    def marker_on(self) -> bool:
        return self.marker is not None

    def set_state(self, state: dict) -> None:
        self.state = state if isinstance(state, dict) else {}

    def _view(self) -> dict:
        return {**self.state, "marker": self.marker_on}

    def poll(self) -> None:
        """Handle clicks, move the gaze marker and redraw if what is shown changed.
        Call often (every frame or so while the marker is on)."""
        while True:
            has_event, event = self.overlay.pollNextOverlayEvent(self.handle, self._event)
            if not has_event:
                break
            if event.eventType == self.openvr.VREvent_MouseButtonDown:
                view = self._view()
                # Mouse events have their origin at the bottom left; the panel's is top left.
                button = hit(layout(view), event.data.mouse.x, HEIGHT - event.data.mouse.y)
                if button is None:
                    continue
                if button.name == "gaze_marker":
                    self._set_marker(bool(button.value))
                else:
                    self.emit(action_for(button, view))
        if self.marker is not None:
            self.marker.update()
        view = self._view()
        if view != self._drawn:
            self.overlay.setOverlayRaw(self.handle, _raw(render(view)), WIDTH, HEIGHT, 4)
            self._drawn = view

    def _set_marker(self, on: bool) -> None:
        if on and self.marker is None:
            self.marker = GazeMarker(self.openvr, self._read_sample)
        elif not on and self.marker is not None:
            self.marker.close()
            self.marker = None

    def close(self) -> None:
        self._set_marker(False)
        try:
            self.overlay.destroyOverlay(self.handle)
        except Exception:
            pass
