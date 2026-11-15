"""The output visualizer places its static geometry once and moves only the
gaze dot, ring and bars per frame."""

import tkinter as tk

import pytest

from eye import EyeInfo
from eye_processor import EyeInfoOrigin
from output_viz import OutputVisualizer

MOVING = {"ring", "dot", "blink_bar", "brow_bar"}


@pytest.fixture
def root():
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
