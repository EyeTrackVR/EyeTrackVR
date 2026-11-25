"""The output visualizer places its static geometry once and moves only the
gaze dot, ring and bars per frame."""

import gc
import tkinter as tk

import pytest

from eye import EyeInfo
from eye_processor import EyeInfoOrigin
from output_viz import OutputVisualizer

MOVING = {"ring", "dot", "blink_bar", "brow_bar"}


@pytest.fixture
def _collect_tk_on_main_thread():
    """Torn down after root's cached value is dropped: the destroyed Tk sits in a
    reference cycle, and a Tk finalised by a later test's thread aborts the process
    (Tcl_AsyncDelete)."""
    yield
    gc.collect()


@pytest.fixture
def root(_collect_tk_on_main_thread):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No desktop display available")
    root.withdraw()
    yield root
    root.destroy()


def _info(x=0.1, y=-0.2, blink=0.6, origin=EyeInfoOrigin.HSRAC):
    return EyeInfo(origin, x, y, 0.4, blink, 0.0, eyebrow=0.5)


def test_static_items_are_placed_once(root):
    viz = OutputVisualizer(root, 200)
    viz.draw(_info())
    ids = viz._item_ids
    pad, G = viz.pad, viz.gaze
    assert viz.canvas.coords(ids["panel"]) == [pad, pad, pad + G, pad + G]
    assert viz.canvas.coords(ids["bg"]) == [0, 0, viz.width, viz.height]

    names = {item: name for name, item in ids.items()}
    touched = []
    real_coords = viz.canvas.coords

    def coords(item, *args):
        if args:
            touched.append(names[item])
        return real_coords(item, *args)

    viz.canvas.coords = coords
    viz.draw(_info(x=-0.3, blink=0.1))
    viz.draw(_info(origin=EyeInfoOrigin.FAILURE))
    assert set(touched) == MOVING


def _dot_centre(viz):
    x0, y0, x1, y1 = viz.canvas.coords(viz._item_ids["dot"])
    return (x0 + x1) / 2, (y0 + y1) / 2


def test_next_gaze_fills_the_panel_at_the_gaze_limit(root):
    viz = OutputVisualizer(root, 200)
    centre = viz.pad + viz.gaze // 2
    viz.draw(_info(x=0.0, y=0.0, origin=EyeInfoOrigin.NEXT))
    assert _dot_centre(viz) == pytest.approx((centre, centre), abs=1.5)
    # Half of the gaze limit sits about halfway to the edge, not on it
    # (the classic trackers' 2.75 magnification pinned 0.36 to the edge).
    viz.draw(_info(x=0.5, y=0.0, origin=EyeInfoOrigin.NEXT))
    half_way = centre - _dot_centre(viz)[0]
    viz.draw(_info(x=1.0, y=0.0, origin=EyeInfoOrigin.NEXT))
    full = centre - _dot_centre(viz)[0]
    assert 0.4 * full < half_way < 0.6 * full
    viz.draw(_info(x=0.5, y=0.0, origin=EyeInfoOrigin.HSRAC))
    assert centre - _dot_centre(viz)[0] > 1.5 * half_way
