"""
EyeTrackVR's panel in the SteamVR dashboard: recenter, calibrate, a gaze marker and the
per-game foveated rendering switch, without taking the headset off.

Runs inside the SteamVR companion process (ovr/dfr_monitor.py), which already holds an
OpenVR session. The app sends what to show as one JSON "state" message (labels already
translated, see DfrController.dashboard_state); a click goes back as an "action"
message and the app does the work. This side only draws and hit-tests, so it never
needs the app's settings, models or cameras.

  app -> here  {"type": "state", "labels": {...}, "game": "...", "note": "...", "dfr_supported": true,
                "qualities": ["maximum", "balanced", "minimum"],
                "dfr": {"available": true, "enabled": false, "mode": "balanced", "key": "steam.app.1"}}
  here -> app  {"type": "action", "name": "recenter" | "recalibrate"}
               {"type": "action", "name": "dfr_enabled", "key": "steam.app.1", "value": true}
               {"type": "action", "name": "dfr_mode", "key": "steam.app.1", "value": "maximum"}

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

# The app's dark theme (ui_theme.DARK; the headset has no light mode).
BACKGROUND = (24, 23, 28, 255)  # #18171c
PANEL = (33, 31, 39, 255)  # #211f27
BORDER = (61, 58, 71, 255)  # #3d3a47
TEXT = (235, 233, 240, 255)  # #ebe9f0
MUTED = (154, 152, 162, 255)  # #9a98a2
BUTTON = (42, 39, 49, 255)  # #2a2731
BUTTON_ACTIVE = (181, 160, 238, 255)  # the accent, #b5a0ee
TEXT_ON_ACTIVE = BACKGROUND  # dark text on the accent, as on the app's accent buttons
BUTTON_DISABLED = (29, 28, 34, 255)
BORDER_DISABLED = (40, 38, 46, 255)
TEXT_DISABLED = (82, 80, 86, 255)  # #525056
# Drawn this many times larger, then scaled down: smooth rounded shapes in the headset.
SUPERSAMPLE = 2

DEFAULT_LABELS = {
    "recenter": "Recenter",
    "calibrate": "Calibrate",
    "gaze_marker": "Gaze marker",
    "dfr_title": "Foveated rendering",
    "dfr_on": "On for this game",
    "dfr_off": "Off for this game",
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
        # The game's on/off switch, across the row. (Flip vertical is set in the
        # app's foveated rendering settings, not here.)
        Button(
            "dfr_enabled",
            (40, 350, 960, 430),
            labels["dfr_on"] if enabled else labels["dfr_off"],
            enabled=available,
            active=available and enabled,
            value=not enabled,
        ),
    ]
    # The app lists the qualities to offer (release builds have no debug view).
    qualities = [q for q in (state.get("qualities") or QUALITIES) if q in QUALITIES]
    for rect, quality in zip(_row(len(qualities), 450, 520), qualities):
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


def _logo_path() -> Path:
    return _bundle_dir() / "assets" / "images" / "logo.png"


def _button_colours(button: Button) -> tuple:
    """(fill, outline, text) for a button's state."""
    if button.active:
        return BUTTON_ACTIVE, BUTTON_ACTIVE, TEXT_ON_ACTIVE
    if button.enabled:
        return BUTTON, BORDER, TEXT
    return BUTTON_DISABLED, BORDER_DISABLED, TEXT_DISABLED


def _draw_switch(draw, button: Button, k: int) -> None:
    """An on/off switch with its label: the knob's side and the track colour show the
    state at a glance, where a button's wording alone did not."""
    left, top, right, bottom = (v * k for v in button.rect)
    middle = (top + bottom) // 2
    track = (left, middle - 30 * k, left + 116 * k, middle + 30 * k)
    if button.active:
        draw.rounded_rectangle(track, radius=30 * k, fill=BUTTON_ACTIVE)
        knob = BACKGROUND
    else:
        fill, outline, _ = _button_colours(button)
        draw.rounded_rectangle(track, radius=30 * k, fill=fill, outline=outline, width=2 * k)
        knob = MUTED if button.enabled else TEXT_DISABLED
    knob_x = track[2] - 30 * k if button.active else track[0] + 30 * k
    draw.ellipse((knob_x - 21 * k, middle - 21 * k, knob_x + 21 * k, middle + 21 * k), fill=knob)
    font = _fit(draw, button.label, 30 * k, right - track[2] - 28 * k)
    box = draw.textbbox((0, 0), button.label, font=font)
    draw.text(
        (track[2] + 20 * k, middle - (box[3] + box[1]) / 2),
        button.label,
        font=font,
        fill=TEXT if button.enabled else TEXT_DISABLED,
    )


def _header(image, draw, k: int) -> None:
    """The logo on its tile (the page colour, so only the mark shows) and the name."""
    size = 64 * k
    try:
        from ui_theme import logo_tile

        # Little padding: the tile is the panel colour, so only the mark shows.
        image.alpha_composite(logo_tile(_logo_path(), size, padding=0.04), (32 * k, 20 * k))
        x = 108 * k
    except Exception:
        x = 40 * k  # no logo file: the name alone
    font = _font(OVERLAY_NAME, 40 * k)
    box = draw.textbbox((0, 0), OVERLAY_NAME, font=font)
    draw.text((x, 52 * k - (box[3] + box[1]) / 2), OVERLAY_NAME, font=font, fill=TEXT)


def render(state: dict):
    """The panel as an RGBA PIL image (WIDTH x HEIGHT)."""
    from PIL import Image, ImageDraw

    k = SUPERSAMPLE
    image = Image.new("RGBA", (WIDTH * k, HEIGHT * k), BACKGROUND)
    draw = ImageDraw.Draw(image)
    labels = {**DEFAULT_LABELS, **(state.get("labels") or {})}
    _header(image, draw, k)

    supported = state.get("dfr_supported", True)
    if supported:
        draw.rounded_rectangle(
            (24 * k, 222 * k, (WIDTH - 24) * k, (HEIGHT - 20) * k),
            radius=22 * k,
            fill=PANEL,
            outline=BORDER,
            width=2 * k,
        )
        title = labels["dfr_title"]
        draw.text((40 * k, 238 * k), title, font=_fit(draw, title, 30 * k, 920 * k), fill=TEXT)
    game = str(state.get("game") or "") if supported else ""
    if game:
        draw.text((40 * k, 282 * k), game, font=_fit(draw, game, 24 * k, 920 * k), fill=MUTED)
    note = str(state.get("note") or "") if supported else ""  # why this game has no switch
    if note:
        draw.text((40 * k, 316 * k), note, font=_fit(draw, note, 20 * k, 920 * k), fill=MUTED)

    for button in layout(state):
        if button.name == "dfr_enabled":
            _draw_switch(draw, button, k)
            continue
        left, top, right, bottom = (v * k for v in button.rect)
        fill, outline, text = _button_colours(button)
        draw.rounded_rectangle((left, top, right, bottom), radius=16 * k, fill=fill, outline=outline, width=2 * k)
        font = _fit(draw, button.label, 30 * k, right - left - 24 * k)
        width = draw.textlength(button.label, font=font)
        box = draw.textbbox((0, 0), button.label, font=font)
        draw.text(
            ((left + right - width) / 2, (top + bottom - (box[3] + box[1])) / 2),
            button.label,
            font=font,
            fill=text,
        )
    return image.resize((WIDTH, HEIGHT), Image.LANCZOS)


def render_icon(size: int = 256):
    """The dashboard tab's thumbnail: the logo on its rounded tile, corners clear."""
    from ui_theme import logo_tile

    return logo_tile(_logo_path(), size)


def render_marker():
    """The gaze marker: an accent ring with a centre dot, see-through in between. A dark
    halo keeps both visible over bright and dark scenes alike."""
    from PIL import Image, ImageDraw

    k = 4  # drawn larger and scaled down for smooth edges
    size = MARKER_PIXELS * k
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    halo = BACKGROUND[:3] + (190,)
    draw.ellipse((12 * k, 12 * k, size - 12 * k, size - 12 * k), outline=halo, width=24 * k)
    draw.ellipse((18 * k, 18 * k, size - 18 * k, size - 18 * k), outline=BUTTON_ACTIVE, width=12 * k)
    centre = size // 2
    draw.ellipse((centre - 18 * k, centre - 18 * k, centre + 18 * k, centre + 18 * k), fill=halo)
    draw.ellipse((centre - 12 * k, centre - 12 * k, centre + 12 * k, centre + 12 * k), fill=BUTTON_ACTIVE)
    return image.resize((MARKER_PIXELS, MARKER_PIXELS), Image.LANCZOS)


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
        try:
            # The tab icon: the logo on its rounded tile, as in the app.
            icon = render_icon()
            self.overlay.setOverlayRaw(thumbnail, _raw(icon), icon.width, icon.height, 4)
        except Exception:
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
