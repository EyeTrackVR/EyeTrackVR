"""Main-window pages scroll once the window is too short for them."""

from types import SimpleNamespace

import pytest

import scroll_page
from scroll_page import ScrollPage


@pytest.fixture
def root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No desktop display available")
    yield root
    root.destroy()


def _page(root, content_height):
    from tkinter import ttk

    page = ScrollPage(root)
    page.pack(fill="both", expand=True)
    ttk.Frame(page.body, width=300, height=content_height).pack(fill="both", expand=True)
    return page


def _settle(root):
    for _ in range(5):
        root.update()


def test_a_page_that_fits_fills_the_window_without_a_scrollbar(root):
    root.geometry("400x300")
    page = _page(root, 100)
    _settle(root)
    assert not page.overflowing
    # Fill/expand still work: the content gets the whole page height.
    assert page.body.winfo_height() == page.canvas.winfo_height()
    page.scroll(5)
    assert page.canvas.yview()[0] == 0.0


def test_a_tall_page_scrolls_and_stops_when_the_window_grows(root):
    # Small sizes: a CI display may be no taller than 768 px, and a window can't
    # grow past the screen.
    root.geometry("400x200")
    page = _page(root, 450)
    _settle(root)
    assert page.overflowing
    page.scroll(5)
    assert page.canvas.yview()[0] > 0.0
    root.geometry("400x600")
    _settle(root)
    assert not page.overflowing
    assert page.canvas.yview()[0] == 0.0  # back to the top


def test_the_page_asks_for_its_contents_width_but_not_its_height(root):
    # The window sizes itself to the widest page; the window's height decides
    # how much shows, so the bottom bar is never pushed out of view.
    page = _page(root, 800)
    _settle(root)
    assert page.canvas.winfo_reqwidth() >= 300
    assert page.winfo_reqheight() < 800


def test_the_wheel_scrolls_the_page_under_the_pointer_but_not_a_dropdown(root):
    from tkinter import ttk

    root.geometry("400x200")
    page = _page(root, 800)
    inner = ttk.Label(page.body, text="x")
    inner.pack()
    combo = ttk.Combobox(page.body)
    combo.pack()
    _settle(root)
    scroll_page._on_wheel(SimpleNamespace(widget=inner, delta=-120, num=None))
    assert page.canvas.yview()[0] > 0.0
    before = page.canvas.yview()
    scroll_page._on_wheel(SimpleNamespace(widget=combo, delta=-120, num=None))
    assert page.canvas.yview() == before
    scroll_page._on_wheel(SimpleNamespace(widget="popdown", delta=-120, num=None))  # Tk's own windows
    assert page.canvas.yview() == before


@pytest.mark.parametrize(
    "event, units",
    [
        (SimpleNamespace(num=4, delta=0), -1),
        (SimpleNamespace(num=5, delta=0), 1),
        (SimpleNamespace(num=None, delta=120), -1),
        (SimpleNamespace(num=None, delta=-120), 1),
        (SimpleNamespace(num=None, delta=0), 0),
    ],
)
def test_wheel_direction(event, units):
    assert scroll_page._wheel_units(event) == units
