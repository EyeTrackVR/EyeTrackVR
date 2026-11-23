"""The app's colours, dark (the default) or light (Settings > Light mode).

sv_ttk themes the ttk widgets; plain Tk widgets, canvases and text boxes take
their colours from here so they match it. The mode is chosen once at startup,
before any window is built (the setting asks for a restart), so modules may
read colours when they build their widgets.

The base colours are sv_ttk's own (sv_ttk/theme/dark.tcl and light.tcl).
"""

from __future__ import annotations

DARK = {
    # sv_ttk's dark theme
    "bg": "#18171c",
    "fg": "#ebe9f0",
    "accent": "#b5a0ee",
    # Text that matters less than the rest.
    "muted": "#9a98a2",
    # Raised areas on the page (camera pictures, visualizers) and their edges.
    "surface": "#211f27",
    "panel": "#2a2731",
    "border": "#3d3a47",
    "grid": "#36333f",
    # The visualizers: eyelid bar in the accent, eyebrow bar a quieter shade of it.
    "brow": "#8a78cf",
    "gaze_dot": "#f4f2ff",
    "fail_bg": "#3a2428",
    "fail_fg": "#ff9aaa",
    # Manual eyelid tuning: the blink and wide-eye points, and the live reading.
    "blink_point": "#ff8a8a",
    "blink_zone": "#4a2a32",
    "wide_point": "#8ae0a0",
    "wide_zone": "#24402e",
    "live": "#ffd84a",
    "off_scale": "#1d1b22",
    # Tooltips and long text (agreements, bug reports).
    "tooltip_bg": "#24222a",
    "tooltip_fg": "#ebe9f0",
    "tooltip_border": "#3d3a47",
    "text_bg": "#211f27",
    "text_fg": "#dcd9e3",
    "text_select": "#4b3d8f",
    "heading": "#ffffff",
    "danger": "#ff8f8f",
}

LIGHT = {
    # sv_ttk's light theme
    "bg": "#faf9f7",
    "fg": "#1f1d26",
    "accent": "#6750c8",
    "muted": "#6b6873",
    "surface": "#efedf2",
    "panel": "#ffffff",
    "border": "#cfcbd8",
    "grid": "#e2dfe8",
    "brow": "#9a88e0",
    "gaze_dot": "#2b2540",
    "fail_bg": "#fbe4e6",
    "fail_fg": "#b3261e",
    "blink_point": "#c62828",
    "blink_zone": "#f6d9dc",
    "wide_point": "#2e7d32",
    "wide_zone": "#d8efdb",
    "live": "#b07d00",
    "off_scale": "#e7e4ec",
    "tooltip_bg": "#ffffff",
    "tooltip_fg": "#1f1d26",
    "tooltip_border": "#cfcbd8",
    "text_bg": "#ffffff",
    "text_fg": "#1f1d26",
    "text_select": "#d6ccf5",
    "heading": "#1f1d26",
    "danger": "#c62828",
}

_palette = DARK


def set_light(light: bool) -> str:
    """Choose the mode (at startup, before building windows). Returns the sv_ttk theme name."""
    global _palette
    _palette = LIGHT if light else DARK
    return "light" if light else "dark"


def is_light() -> bool:
    return _palette is LIGHT


def color(name: str) -> str:
    return _palette[name]


def logo_tile(path, size: int, background=None, padding: float = 0.14, radius: float = 0.24):
    """The logo as a ``size`` square RGBA PIL image: its own colours (a white mark with
    violet highlights) on a rounded square in the dark theme's background, inset by
    ``padding`` of the size, with no border. On the dark theme the square is the page
    colour; on the light one it frames the logo instead of the logo being inverted.

    ``background`` fills the corners outside the square (an RGB tuple or "#rrggbb");
    None leaves them transparent."""
    from PIL import Image, ImageDraw

    scale = 4  # draw large, then downsample: smooth corners and edges
    big = size * scale
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0) if background is None else background)
    shape = Image.new("L", (big, big), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, big - 1, big - 1), radius=round(big * radius), fill=255)
    tile.paste(DARK["bg"], (0, 0), shape)
    inner = big - 2 * round(big * padding)
    logo = Image.open(path).convert("RGB").resize((inner, inner), Image.LANCZOS)
    # The logo's square is black: weight its pixels by brightness so the square drops
    # out and only the mark (and its violet tint) lands on the tile.
    offset = (big - inner) // 2
    tile.paste(logo, (offset, offset), logo.convert("L"))
    return tile.resize((size, size), Image.LANCZOS)
