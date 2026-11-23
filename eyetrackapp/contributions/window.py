"""Tk contribution management. Worker threads communicate only through a queue."""

import json
from pathlib import Path
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import requests

from localization import tr, tr_english

from .bundles import MAX_HMD, clean_hmd
from .client import QUOTA_MESSAGES, ContributionClient, Paused, save, outside_git
from .verification import verify_in_app

# Suggestions only: free text stays allowed, and maintainers bin every submission themselves.
HMD_SUGGESTIONS = (
    "Valve Index",
    "HTC Vive",
    "HTC Vive Pro / Pro 2",
    "Bigscreen Beyond",
    "Bigscreen Beyond 2 / 2e",
    "Meta Quest 2",
    "Meta Quest 3",
    "Meta Quest 3S",
    "Meta Quest Pro",
    "Pimax Crystal",
    "Pico 4",
    "Varjo Aero",
    "HP Reverb G2",
    "PlayStation VR2",
    "Shiftall MeganeX",
    "Somnium VR1",
)
# How long to wait before re-checking an unreachable upload service.
_CONFIG_RETRY_MS = 15000
# Short checkbox labels (language keys). Ticking them gives the two numbered confirmations at the
# top of the notice, whose full wording is what the recorded notice version and hash cover.
DATASET_CONSENTS = ("contributions.consent_agreement", "contributions.consent_sensitive")


def dataset_consents():
    """The checkbox labels in the active language; read at use time, after the language loads."""
    return tuple(tr(key) for key in DATASET_CONSENTS)


# One type scale for both windows. Pixel sizes match the Sun Valley theme's own -14 px body
# font, so text drawn by Tk widgets and by the theme comes out the same size.
FONT_TITLE = ("Segoe UI", -20, "bold")
FONT_HEADING = ("Segoe UI", -15, "bold")
FONT_BODY = ("Segoe UI", -14)
FONT_SMALL = ("Segoe UI", -12)
MUTED = "#8a93a0"
ACCENT = "#57c8ff"
DANGER = "#ff8f8f"
# A section lead-in such as "Who we are." or "How long we keep it." at the start of a paragraph.
SECTION = re.compile(r"([A-Z][A-Za-z' ]{1,40}?)\.\s+(.+)", re.S)
NOTICE_STYLE = {
    "background": "#20242b",
    "foreground": "#d9dfe7",
    "selectbackground": "#365b80",
    "relief": "flat",
    "borderwidth": 0,
    "highlightthickness": 0,
    "wrap": "word",
    "font": ("Segoe UI", -15),
    "padx": 20,
    "pady": 16,
    "spacing2": 3,
    "cursor": "arrow",
}
# Longest readable line in pixels; wider notices get a right margin instead.
NOTICE_LINE = 720


def style_notice(text):
    """Tags for render_notice. A right margin (not padx, which would grow the widget) caps the line length."""

    def margins(event=None):
        right = max(0, (event.width if event else 0) - NOTICE_LINE - 2 * NOTICE_STYLE["padx"])
        for tag in ("title", "heading", "body"):
            text.tag_configure(tag, rmargin=right)
        text.tag_configure("item", lmargin1=4, lmargin2=24, rmargin=right)

    text.tag_configure("title", font=FONT_TITLE, foreground="#ffffff", spacing3=8)
    text.tag_configure("heading", font=FONT_HEADING, foreground="#ffffff", spacing1=14, spacing3=2)
    text.tag_configure("body", spacing3=6)
    text.tag_configure("item", spacing3=4)
    margins()
    text.bind("<Configure>", margins, add="+")


def render_notice(text, notice, title=True):
    """Show a notice with section lead-ins as headings. The wording is unchanged; the notice's
    own title line is left out (title=False) where the page already has a title."""
    text.configure(state="normal")
    text.delete("1.0", "end")
    paragraphs = notice.strip().split("\n\n")
    for index, paragraph in enumerate(paragraphs):
        # Only a short first line followed by the notice proper counts as its title.
        if (
            index == 0
            and len(paragraphs) > 1
            and "\n" not in paragraph
            and not paragraph.endswith(".")
            and len(paragraph) <= 80
        ):
            if title:
                text.insert("end", paragraph + "\n", "title")
            continue
        section = SECTION.match(paragraph)
        if section and len(section[1].split()) <= 5:
            text.insert("end", section[1] + "\n", "heading")
            paragraph = section[2]
        for line in paragraph.split("\n"):
            if line.startswith("- "):
                text.insert("end", "•  " + line[2:] + "\n", "item")
            else:
                text.insert("end", line + "\n", "item" if re.match(r"\d+\. ", line) else "body")
    text.configure(state="disabled")
    text.yview_moveto(0)


def version_label(version):
    """'dataset-2026-10-24-v2' -> 'Agreement v2 · 24 Oct 2026'."""
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})-v(\d+)$", version)
    if not match:
        return tr("contributions.agreement_version_other", version=version)
    months = tr("contributions.months").split()
    if len(months) != 12:
        months = tr_english("contributions.months").split()
    year, month, day, number = match.groups()
    return tr("contributions.agreement_version", number=number, day=int(day), month=months[int(month) - 1], year=year)


def setup_styles(window):
    """Styles shared by both contribution windows."""
    style = ttk.Style(window)
    style.configure("Consent.TCheckbutton", wraplength=600)
    # Other long checkbox labels: translations can be much longer than the English text.
    style.configure("Wrap.TCheckbutton", wraplength=600)
    style.configure("Danger.TButton", foreground=DANGER)
    style.map("Danger.TButton", foreground=[("disabled", "#5f6670")])
    style.configure("Contrib.TNotebook.Tab", font=FONT_BODY, padding=(14, 6))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Small.TLabel", foreground=MUTED, font=FONT_SMALL)
    style.configure("Mark.TLabel", foreground=ACCENT, font=("Segoe UI", -40, "bold"))


def load_logo(path, size, background):
    """The logo is a white mark on an opaque black square; draw the mark on the window background."""
    try:
        from PIL import Image, ImageTk

        mark = Image.open(path).convert("L").resize((size, size), Image.LANCZOS)
        image = Image.new("RGB", (size, size), background)
        image.paste((255, 255, 255), (0, 0), mark)
        return ImageTk.PhotoImage(image)
    except Exception:
        return None


class ContributionWindow:
    """The contribution flow in its own window, or, given ``on_hide``, as a frame
    inside ``parent`` (EyeTrackVR's main window shows it as a page). ``on_hide``
    then runs when the user closes it; the frame is kept for the next visit."""

    def __init__(self, parent, client=None, capture_controller=None, on_hide=None):
        self.client = client or ContributionClient()
        self.capture_controller = capture_controller
        self.capture_active = False
        self._capture_path = None
        self._capture_receipt = None
        self._upload_sid = None
        self._on_hide = on_hide
        self.embedded = on_hide is not None
        if self.embedded:
            self.window = ttk.Frame(parent)
        else:
            self.window = tk.Toplevel(parent)
            self.window.title(tr("contributions.window_title"))
            self.window.transient(parent)
            self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.config = None
        self.rows = {}
        self.hmd = tk.StringVar()
        # Two separate consents: the agreement, then sensitive data and the US transfer.
        self.agree = tk.BooleanVar(value=False)
        self.agree_sensitive = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value=tr("contributions.status_checking"))
        self.availability = tk.StringVar(value=tr("contributions.availability_connecting"))
        self.selection = tk.StringVar(value=tr("contributions.selection_pending"))
        self.capture_status = tk.StringVar(value=tr("contributions.capture_ready"))
        self.step = 0
        self._last_progress = 0
        self._consent_dialog = None
        self._build_ui()
        self.show_step(0)
        self._load_bundled_notice()
        self.refresh_history()
        if not self.embedded:
            self._size_window()
        self._poll_job = self.window.after(50, self.poll)
        self.run(lambda: ("config", self.client.config()))

    def _size_window(self):
        self.window.update_idletasks()
        # Keep the footer on screen even on a laptop or a scaled desktop.
        width = min(900, max(560, self.window.winfo_screenwidth() - 100))
        height = min(760, max(480, self.window.winfo_screenheight() - 140))
        # The smallest height that still fits the agreement's header, consents, navigation
        # and a seven-line notice, so the page never needs to scroll as a whole.
        # Tk sizes the notebook for its tallest tab and page, so swap in the agreement page's height.
        new, history = self._tab_frames
        page_heights = [page.winfo_reqheight() for page in self.pages]
        tallest_tab = max(new.winfo_reqheight(), history.winfo_reqheight())
        needed = (
            self.window.winfo_reqheight()
            - tallest_tab
            + new.winfo_reqheight()
            - max(page_heights)
            + page_heights[2]
            + 24
        )
        height = max(height, min(needed, self.window.winfo_screenheight() - 80))
        # Translated button labels can be wider than the English ones: keep the whole row of history
        # buttons on screen (Resume upload and Refresh status take turns in its first slot).
        shown = self.resume_button if self.resume_button.winfo_manager() else self.refresh_button
        wider = max(self.resume_button.winfo_reqwidth(), self.refresh_button.winfo_reqwidth())
        buttons = self._history_actions.winfo_reqwidth() - shown.winfo_reqwidth() + wider + 90
        min_width = min(max(680, buttons), self.window.winfo_screenwidth() - 40)
        width = max(width, min_width)
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(min(min_width, width), min(max(520, needed), height))
        from .native import decorate

        self.window.after(50, lambda: decorate(self.window))

    def _build_ui(self):
        from .native import asset

        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        setup_styles(self.window)
        header = ttk.Frame(self.window, padding=(24, 16, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        background = ttk.Style(self.window).lookup("TFrame", "background") or "#1c1c1c"
        self._logo = load_logo(asset("logo.png"), 40, background)
        if self._logo:
            ttk.Label(header, image=self._logo).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ttk.Label(header, text=tr("contributions.header_title"), font=FONT_TITLE).grid(row=0, column=1, sticky="w")
        self.availability_label = ttk.Label(
            header, textvariable=self.availability, style="Muted.TLabel", foreground=MUTED, wraplength=640
        )
        self.availability_label.grid(row=1, column=1, sticky="w")

        self.tabs = ttk.Notebook(self.window, style="Contrib.TNotebook")
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=24)
        new = ttk.Frame(self.tabs, padding=(12, 14))
        history = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(new, text=tr("contributions.tab_record"))
        self.tabs.add(history, text=tr("contributions.tab_history"))
        self._tab_frames = (new, history)
        new.columnconfigure(0, weight=1)
        new.rowconfigure(1, weight=1)

        steps = ttk.Frame(new)
        steps.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.step_labels = []
        for index, title in enumerate(tr(key) for key in self.STEP_NAMES):
            steps.columnconfigure(index, weight=1)
            label = ttk.Label(steps, text=title, anchor="center", padding=6, font=FONT_BODY)
            label.grid(row=0, column=index, sticky="ew")
            self.step_labels.append(label)
        self.pages = []
        for _ in range(4):
            page = ttk.Frame(new)
            page.grid(row=1, column=0, sticky="nsew")
            self.pages.append(page)

        # Every page shares one look: a title, short text, natural-height rows and the primary
        # action in the accent colour. Controls that can't be used are hidden, not disabled.
        recording = self.pages[0]
        ttk.Label(recording, text=tr("contributions.setup_title"), font=FONT_TITLE).pack(anchor="w", pady=(8, 8))
        self.intro = ttk.Label(recording, wraplength=640, justify="left", text=tr("contributions.setup_intro"))
        self.intro.pack(fill="x", pady=(0, 20))
        ttk.Label(recording, text=tr("contributions.setup_before"), font=FONT_HEADING).pack(anchor="w", pady=(0, 6))
        self.instructions = ttk.Label(recording, wraplength=640, justify="left", text=tr("contributions.setup_steps"))
        self.instructions.pack(fill="x", pady=(0, 12))
        self.overlay = ttk.Checkbutton(
            recording,
            text=tr("contributions.use_overlay"),
            style="Wrap.TCheckbutton",
            variable=self.capture_controller.use_overlay_var
            if self.capture_controller
            else tk.BooleanVar(master=self.window, value=True),
        )
        self.overlay.pack(anchor="w", pady=(0, 20))
        ttk.Label(recording, text=tr("contributions.hmd_question"), font=FONT_HEADING).pack(anchor="w", pady=(0, 6))
        self.hmd_entry = ttk.Combobox(recording, textvariable=self.hmd, values=HMD_SUGGESTIONS, width=32)
        self.hmd_entry.pack(anchor="w")
        self.hmd_hint = ttk.Label(recording, wraplength=640, justify="left", style="Muted.TLabel", foreground=MUTED)
        self.hmd_hint.pack(anchor="w", pady=6)
        self.hmd.trace_add("write", lambda *_: self.update_hmd_hint())
        self.update_hmd_hint()

        capture = self.pages[1]
        ttk.Label(capture, text=tr("contributions.capture_title"), font=FONT_TITLE).pack(anchor="w", pady=(8, 8))
        self.capture_instructions = ttk.Label(
            capture, wraplength=640, justify="left", text=tr("contributions.capture_text")
        )
        self.capture_instructions.pack(fill="x", pady=(0, 20))
        self.capture_status_label = ttk.Label(
            capture, textvariable=self.capture_status, wraplength=640, font=FONT_HEADING, justify="left"
        )
        self.capture_status_label.pack(fill="x", pady=(0, 12))
        # Progress and its caption are shown only while recording (see capture_started).
        self.capture_progress = ttk.Progressbar(capture, mode="indeterminate", maximum=100)
        self.capture_detail = ttk.Label(capture, style="Muted.TLabel", foreground=MUTED, wraplength=640)
        controls = ttk.Frame(capture)
        controls.pack(fill="x", pady=(8, 0))
        self._capture_controls = controls
        self.record_button = ttk.Button(
            controls, text=tr("contributions.start_capture_btn"), style="Accent.TButton", command=self.start_capture
        )
        self.record_button.pack(side="left")
        self.stop_record_button = ttk.Button(
            controls, text=tr("contributions.stop_capture_btn"), style="Danger.TButton", command=self.stop_capture
        )

        # Only the notice scrolls. The header stays at the top, the consents and navigation
        # at the bottom, and the window's minimum size always fits them (see __init__).
        agreement = self.pages[2]
        agreement.columnconfigure(0, weight=1)
        agreement.rowconfigure(3, weight=1)
        ttk.Label(agreement, text=tr("contributions.agreement_title"), font=FONT_TITLE).grid(
            row=0, column=0, sticky="w"
        )
        self.terms_summary = ttk.Label(
            agreement, wraplength=640, justify="left", text=tr("contributions.agreement_summary")
        )
        self.terms_summary.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        details = ttk.Frame(agreement)
        details.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        details.columnconfigure(0, weight=1)
        self.file_label = ttk.Label(
            details, textvariable=self.selection, wraplength=420, style="Small.TLabel", foreground=MUTED
        )
        self.file_label.grid(row=0, column=0, sticky="w")
        self.notice_version = tk.StringVar()
        ttk.Label(details, textvariable=self.notice_version, style="Small.TLabel", foreground=MUTED).grid(
            row=0, column=1, sticky="e"
        )
        notice_panel = ttk.Frame(agreement)
        notice_panel.grid(row=3, column=0, sticky="nsew")
        notice_panel.columnconfigure(0, weight=1)
        notice_panel.rowconfigure(0, weight=1)
        # Seven lines is the minimum height; the notice takes all remaining height.
        self.notice = tk.Text(notice_panel, height=7, takefocus=True, **NOTICE_STYLE)
        style_notice(self.notice)
        self.notice.grid(row=0, column=0, sticky="nsew")
        notice_scroll = ttk.Scrollbar(notice_panel, orient="vertical", command=self.notice.yview)
        notice_scroll.grid(row=0, column=1, sticky="ns")
        self.notice.configure(yscrollcommand=notice_scroll.set)
        self.notice.configure(state="disabled")
        consents = ttk.Frame(agreement)
        consents.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        consents.columnconfigure(0, weight=1)
        consent_labels = dataset_consents()
        self.consent = ttk.Checkbutton(
            consents,
            variable=self.agree,
            text=consent_labels[0],
            style="Consent.TCheckbutton",
            command=self.update_navigation,
        )
        self.consent.grid(row=0, column=0, sticky="ew")
        self.consent_sensitive = ttk.Checkbutton(
            consents,
            variable=self.agree_sensitive,
            text=consent_labels[1],
            style="Consent.TCheckbutton",
            command=self.update_navigation,
        )
        self.consent_sensitive.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        # Rows keep their natural height; the empty last row takes any spare space.
        transfer = self.pages[3]
        transfer.columnconfigure(1, weight=1)
        transfer.rowconfigure(6, weight=1)
        # A check mark beside the title once the upload is complete.
        self.transfer_mark = ttk.Label(transfer, text="✓", style="Mark.TLabel", foreground=ACCENT)
        self.transfer_mark.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 14), pady=(4, 0))
        self.transfer_title = ttk.Label(transfer, font=FONT_TITLE)
        self.transfer_title.grid(row=0, column=1, sticky="w", pady=(8, 8))
        self.transfer_hint = ttk.Label(transfer, wraplength=640, justify="left")
        self.transfer_hint.grid(row=1, column=1, sticky="ew", pady=(0, 16))
        self.progress = ttk.Progressbar(transfer, maximum=100)
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.progress_detail = ttk.Label(transfer, style="Muted.TLabel", foreground=MUTED, wraplength=640)
        self.progress_detail.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 16))
        # Only the buttons that apply are shown (see update_navigation): Pause while busy,
        # Resume when paused, and the receipt backup, which is primary once the upload is done.
        actions = ttk.Frame(transfer)
        actions.grid(row=4, column=0, columnspan=2, sticky="w")
        self.pause = ttk.Button(
            actions, text=tr("contributions.pause_upload_btn"), command=self.cancel.set, state="disabled"
        )
        self.pause.grid(row=0, column=0, padx=(0, 8))
        self.resume_upload_button = ttk.Button(
            actions,
            text=tr("contributions.resume_upload_btn"),
            style="Accent.TButton",
            command=lambda: self.resume(self.upload_receipt),
        )
        self.resume_upload_button.grid(row=0, column=1, padx=(0, 8))
        self.backup_button = ttk.Button(
            actions,
            text=tr("contributions.backup_receipt_btn"),
            state="disabled",
            command=lambda: self.export_receipt(self.upload_receipt),
        )
        self.backup_button.grid(row=0, column=2, padx=(0, 8))
        self.new_session_button = ttk.Button(
            actions, text=tr("contributions.new_session_btn"), command=self.new_session
        )
        self.new_session_button.grid(row=0, column=3)
        self.transfer_note = ttk.Label(
            transfer,
            wraplength=640,
            justify="left",
            style="Muted.TLabel",
            foreground=MUTED,
            text=tr("contributions.transfer_note"),
        )
        self.transfer_note.grid(row=5, column=0, columnspan=2, sticky="w", pady=(16, 0))
        self.set_upload_state("ready")

        navigation = ttk.Frame(new, padding=(0, 14, 0, 0))
        navigation.grid(row=2, column=0, sticky="ew")
        self.back = ttk.Button(navigation, text=tr("contributions.back_btn"), command=self.go_back)
        self.back.pack(side="left")
        self.upload = ttk.Button(
            navigation, text=tr("contributions.verify_upload_btn"), style="Accent.TButton", command=self.start_upload
        )
        # Says why Verify and upload is unavailable on the agreement step.
        self.upload_hint = ttk.Label(
            navigation, style="Muted.TLabel", foreground=MUTED, wraplength=360, justify="right"
        )
        self.next = ttk.Button(
            navigation,
            text=tr("contributions.continue_capture_btn"),
            style="Accent.TButton",
            command=self.continue_flow,
        )
        self.next.pack(side="right")
        self.upload.pack(side="right")

        history.columnconfigure(0, weight=1)
        history.rowconfigure(1, weight=1)
        heading = ttk.Frame(history)
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(heading, text=tr("contributions.history_title"), font=FONT_TITLE).pack(anchor="w")
        self.history_intro = ttk.Label(
            heading,
            text=tr("contributions.history_intro"),
            style="Muted.TLabel",
            foreground=MUTED,
            wraplength=640,
            justify="left",
        )
        self.history_intro.pack(anchor="w", pady=(4, 0))
        self.history = ttk.Treeview(
            history, columns=("prepared", "hmd", "state", "size", "id"), show="headings", height=6, selectmode="browse"
        )
        for key, title, width in (
            ("prepared", "contributions.column_recorded", 90),
            ("hmd", "contributions.column_headset", 150),
            ("state", "contributions.column_status", 120),
            ("size", "contributions.column_size", 70),
            ("id", "contributions.column_id", 90),
        ):
            self.history.heading(key, text=tr(title))
            self.history.column(key, width=width, minwidth=60)
        self.history.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(history, orient="vertical", command=self.history.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.history.configure(yscrollcommand=scrollbar.set)
        self.history.bind("<<TreeviewSelect>>", lambda _: self.update_history_buttons())
        self.history_empty = ttk.Label(
            self.history,
            style="Muted.TLabel",
            foreground=MUTED,
            wraplength=560,
            justify="center",
            text=tr("contributions.history_empty"),
        )
        # Left: actions on the selected contribution (only the ones that apply are shown).
        # Right: receipt files.
        actions = self._history_actions = ttk.Frame(history)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        actions.columnconfigure(4, weight=1)
        self.resume_button = ttk.Button(
            actions, text=tr("contributions.resume_upload_btn"), style="Accent.TButton", command=self.resume
        )
        self.resume_button.grid(row=0, column=0, padx=(0, 8))
        self.refresh_button = ttk.Button(
            actions, text=tr("contributions.refresh_status_btn"), command=self.refresh_status
        )
        self.refresh_button.grid(row=0, column=1, padx=(0, 8))
        self.copy_button = ttk.Button(actions, text=tr("contributions.copy_id_btn"), command=self.copy_id)
        self.copy_button.grid(row=0, column=2, padx=(0, 8))
        self.withdraw_button = ttk.Button(
            actions, text=tr("contributions.withdraw_btn"), style="Danger.TButton", command=self.withdraw
        )
        self.withdraw_button.grid(row=0, column=3, padx=(0, 8))
        self.export_button = ttk.Button(actions, text=tr("contributions.save_receipt_btn"), command=self.export_receipt)
        self.export_button.grid(row=0, column=5, padx=(0, 8))
        self.import_button = ttk.Button(
            actions, text=tr("contributions.restore_receipt_btn"), command=self.import_receipt
        )
        self.import_button.grid(row=0, column=6)
        self.receipt_help = ttk.Label(
            history,
            wraplength=620,
            justify="left",
            style="Muted.TLabel",
            foreground=MUTED,
            text=tr("contributions.receipt_help"),
        )
        self.receipt_help.grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)

        # The status line is only for errors and live progress; it hides itself when empty.
        footer = ttk.Frame(self.window, padding=(24, 10, 24, 14))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status, wraplength=620, justify="left")
        self.status_label.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.status.trace_add(
            "write", lambda *_: self.status_label.grid() if self.status.get() else self.status_label.grid_remove()
        )
        ttk.Label(footer, text=tr("contributions.privacy_contact"), style="Small.TLabel", foreground=MUTED).grid(
            row=1, column=0, sticky="w"
        )
        ttk.Button(footer, text=tr("contributions.close_btn"), command=self.close).grid(
            row=0, column=1, rowspan=2, padx=(12, 0)
        )
        self.window.bind("<Configure>", self._resize_wrap, add="+")

    def _resize_wrap(self, event):
        if event.widget is self.window:
            for widget in (
                self.intro,
                self.instructions,
                self.hmd_hint,
                self.capture_instructions,
                self.capture_status_label,
                self.terms_summary,
                self.transfer_note,
                self.receipt_help,
                self.history_intro,
                self.progress_detail,
                self.capture_detail,
            ):
                widget.configure(wraplength=max(280, event.width - 130))
            # Sits beside the completion check mark.
            self.transfer_hint.configure(wraplength=max(240, event.width - 200))
            # Shares its row with the version label.
            self.file_label.configure(wraplength=max(200, event.width // 2 - 60))
            self.status_label.configure(wraplength=max(240, event.width - 160))
            # Beside the logo.
            self.availability_label.configure(wraplength=max(240, event.width - 120))
            # Shares the navigation row with Back and Verify and upload.
            self.upload_hint.configure(wraplength=max(160, event.width - 420))
            self.history_empty.configure(wraplength=max(240, event.width - 160))
            style = ttk.Style(self.window)
            style.configure("Consent.TCheckbutton", wraplength=max(280, event.width - 160))
            style.configure("Wrap.TCheckbutton", wraplength=max(280, event.width - 160))

    def update_hmd_hint(self):
        text = self.hmd.get()
        try:
            cleaned = clean_hmd(text)
        except ValueError:
            cleaned = None
        if not text.strip():
            hint = tr("contributions.hmd_hint_empty")
        elif cleaned is None:
            hint = tr("contributions.hmd_hint_too_long", max=MAX_HMD, count=len(text.strip()))
        else:
            hint = tr("contributions.hmd_hint_ok", count=len(cleaned), max=MAX_HMD)
        self.hmd_hint.configure(text=hint)

    def _load_bundled_notice(self):
        try:
            self.show_notice(json.loads(Path(__file__).with_name("notice.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.notice.configure(state="normal")
            self.notice.insert("1.0", tr("contributions.notice_unavailable"))
            self.notice.configure(state="disabled")

    # Language keys, translated where shown.
    STEP_NAMES = (
        "contributions.step_setup",
        "contributions.step_capture",
        "contributions.step_agreement",
        "contributions.step_upload",
    )

    def update_steps(self):
        # Finished steps get a check mark in the accent colour, the current one is bold, later ones are muted.
        complete = self.step == 3 and self.upload_state == "complete"
        names = [tr(key) for key in self.STEP_NAMES]
        for index, (label, name) in enumerate(zip(self.step_labels, names)):
            if index < self.step or complete:
                label.configure(text="✓  " + name, foreground=ACCENT, font=FONT_BODY)
            elif index == self.step:
                label.configure(text=f"{index + 1}  {name}", foreground="", font=FONT_HEADING)
            else:
                label.configure(text=f"{index + 1}  {name}", foreground=MUTED, font=FONT_BODY)

    def show_step(self, step):
        self.step = max(0, min(3, step))
        self.pages[self.step].tkraise()
        self.update_steps()
        self.next.pack_forget()
        self.upload.pack_forget()
        self.upload_hint.pack_forget()
        if self.step == 0:
            self.next.configure(text=tr("contributions.continue_capture_btn"))
            self.next.pack(side="right")
        elif self.step == 1 and self._capture_path:
            self.next.configure(text=tr("contributions.continue_agreement_btn"))
            self.next.pack(side="right")
        elif self.step == 2:
            self.upload.pack(side="right")
            self.upload_hint.pack(side="right", padx=12)
        self.update_navigation()

    def update_navigation(self):
        blocked = self.busy or self.capture_active
        eligible = self._capture_path is not None and self._capture_receipt is None
        self.upload.configure(
            state="normal"
            if not blocked and eligible and self.config and self.config["enabled"] and self.consented()
            else "disabled"
        )
        if not self.consented():
            hint = tr("contributions.hint_tick_both")
        elif not self.config:
            hint = tr("contributions.hint_waiting_service")
        elif not self.config["enabled"]:
            hint = tr("contributions.hint_uploads_closed")
        else:
            hint = ""
        self.upload_hint.configure(text=hint)
        self.next.configure(state="disabled" if blocked else "normal")
        self.back.configure(state="disabled" if blocked else "normal")
        if self.step == 0:
            self.back.pack_forget()
        else:
            self.back.pack(side="left")
        self.record_button.configure(state="normal" if not blocked and self.capture_controller else "disabled")
        self.stop_record_button.configure(state="normal" if self.capture_active else "disabled")
        # While recording only Stop is shown; otherwise only Start.
        self.record_button.pack_forget()
        self.stop_record_button.pack_forget()
        (self.stop_record_button if self.capture_active else self.record_button).pack(side="left")
        has_receipt = self.upload_receipt in self.rows
        paused = self.upload_state == "paused" and has_receipt
        self.backup_button.configure(
            state="normal" if not blocked and has_receipt else "disabled",
            style="TButton" if paused else "Accent.TButton",
        )
        self.resume_upload_button.configure(state="disabled" if blocked else "normal")
        for button, shown in (
            (self.pause, self.busy),
            (self.resume_upload_button, paused and not self.busy),
            (self.backup_button, has_receipt and not self.busy),
            (self.new_session_button, not self.busy),
            (self.progress, self.upload_state == "uploading"),
            (self.progress_detail, self.upload_state == "uploading"),
            (self.transfer_note, self.upload_state == "uploading"),
            (self.transfer_mark, self.upload_state == "complete"),
        ):
            if shown:
                button.grid()
            else:
                button.grid_remove()
        self.update_steps()

    def go_back(self):
        if self.busy or self.capture_active:
            return
        self.show_step(0 if self.step == 2 and self._capture_path is None else self.step - 1)

    def continue_flow(self):
        if self.step == 0:
            try:
                clean_hmd(self.hmd.get())
            except ValueError:
                self.status.set(tr("contributions.status_enter_hmd", max=MAX_HMD))
                self.hmd_entry.focus_set()
                return
            self.show_step(1)
            self.status.set("")
        elif self.step == 1:
            self.to_agreement()

    def to_agreement(self):
        if self._capture_path is None or not self._capture_path.is_file():
            self.status.set(tr("contributions.status_capture_first"))
            return
        self.reset_consent()
        self.show_step(2)
        self.notice.yview_moveto(0)
        self.status.set("")

    def clear_capture(self):
        self._capture_path = None
        self._capture_receipt = None
        self.selection.set(tr("contributions.selection_pending"))
        self.reset_consent()
        self.update_navigation()

    def start_capture(self):
        if self.busy or self.capture_active or not self.capture_controller:
            return
        if not self.hmd.get().strip():
            self.show_step(0)
            self.status.set(tr("contributions.status_enter_hmd_record"))
            return
        self.capture_controller._start_collection()
        if not self.capture_active:
            self.status.set(self.capture_status.get())

    def new_session(self):
        if self.busy or self.capture_active:
            return
        self.clear_capture()
        self._upload_sid = None
        self.set_upload_state("ready")
        self.capture_status.set(tr("contributions.capture_ready"))
        self.show_step(0)
        self.status.set("")

    def stop_capture(self):
        if self.capture_controller:
            self.capture_controller._stop_collection()
            self.status.set(tr("contributions.status_stopping_capture"))

    def capture_started(self):
        self.clear_capture()
        self.capture_active = True
        self.show_step(1)
        # Indeterminate until the capture engine reports its first target.
        self.capture_progress.configure(mode="indeterminate", value=0)
        self.capture_progress.pack(fill="x", before=self._capture_controls)
        self.capture_detail.configure(text=tr("contributions.capture_starting"))
        self.capture_detail.pack(anchor="w", pady=(6, 8), before=self._capture_controls)
        self.capture_progress.start(15)
        self.set_busy(self.busy)
        self.status.set("")

    def capture_progress_update(self, current, total):
        """Called by the capture engine as each target or pass starts (current is 1-based)."""
        if not self.capture_active or not total:
            return
        self.capture_progress.stop()
        self.capture_progress.configure(mode="determinate", value=100 * current / total)
        self.capture_detail.configure(
            text=tr("contributions.capture_step", current=current, total=total, percent=round(100 * current / total))
        )

    def capture_stopped(self, path):
        self.capture_active = False
        self.capture_progress.stop()
        self.capture_progress.pack_forget()
        self.capture_detail.pack_forget()
        if path is not None and Path(path).is_file():
            self._capture_path = Path(path).resolve()
            self._capture_receipt = None
            self.selection.set(
                tr("contributions.selection_attached", size=f"{self._capture_path.stat().st_size / 1024**2:.1f}")
            )
            self.reset_consent()
            self.tabs.select(0)
            self.show_step(2)
            self.status.set("")
        else:
            self.clear_capture()
            self.show_step(1)
            self.status.set(tr("contributions.status_capture_unfinished"))
        self.set_busy(self.busy)

    def consented(self):
        return self.agree.get() and self.agree_sensitive.get()

    def reset_consent(self):
        self.agree.set(False)
        self.agree_sensitive.set(False)
        self.update_navigation()

    def show_notice(self, terms):
        render_notice(self.notice, terms["text"], title=False)
        self.reset_consent()
        self.notice_version.set(version_label(terms["version"]))

    def set_busy(self, busy):
        self.busy = busy
        blocked = busy or self.capture_active
        for widget in (
            self.hmd_entry,
            self.overlay,
            self.consent,
            self.consent_sensitive,
            self.export_button,
            self.import_button,
            self.new_session_button,
        ):
            widget.configure(state="disabled" if blocked else "normal")
        self.update_navigation()
        self.update_history_buttons()
        self.pause.configure(state="normal" if busy else "disabled")

    def run(self, operation):
        if self.busy or self.capture_active:
            return
        self.cancel.clear()
        self.set_busy(True)

        def worker():
            try:
                with self.client.exclusive():
                    self.events.put(("done", operation()))
            except Paused as error:
                self.events.put(("error", str(error)))
            except requests.RequestException:
                self.events.put(("error", tr("contributions.error_connection")))
            except ValueError as error:
                self.events.put(("error", str(error)))
            except Exception:
                self.events.put(("error", tr("contributions.error_operation")))

        threading.Thread(target=worker, daemon=True).start()

    def report_progress(self, text, done, total):
        current = time.monotonic()
        if current - self._last_progress > 0.1 or done == total:
            self.events.put(("progress", (text, done, total)))
            self._last_progress = current

    def request_consent(self, terms):
        answer = threading.Event()
        result = []
        self.events.put(("consent", (terms, answer, result)))
        while not answer.wait(0.2):
            if self.cancel.is_set():
                return False
        return bool(result and result[0])

    def start_upload(self):
        if not self.config or not self.config["enabled"] or not self.consented():
            self.status.set(tr("contributions.status_agree_first"))
            return
        if self.capture_active or self._capture_path is None or self._capture_receipt is not None:
            self.status.set(tr("contributions.status_new_capture"))
            return
        # Snapshot all Tk values on its owning thread.
        source, hmd, terms = self._capture_path, self.hmd.get(), dict(self.config["terms"]["dataset"])
        self.reset_consent()

        def upload():
            sid = self.client.prepare(source, hmd, terms, self.cancel, self.report_progress)
            self.events.put(("prepared", sid))
            return (
                "status",
                self.client.resume(sid, verify_in_app, self.request_consent, self.cancel, self.report_progress),
            )

        self._upload_sid = None
        self.show_step(3)
        self.set_upload_state("uploading")
        self.run(upload)

    # (title, text) language keys of the Upload page for each state.
    UPLOAD_STATES = {
        "ready": ("contributions.upload_ready_title", "contributions.upload_encrypted_text"),
        "uploading": ("contributions.upload_uploading_title", "contributions.upload_encrypted_text"),
        "paused": ("contributions.upload_paused_title", "contributions.upload_paused_text"),
        "complete": ("contributions.upload_complete_title", "contributions.upload_complete_text"),
        "updated": ("contributions.upload_updated_title", "contributions.upload_updated_text"),
    }

    def set_upload_state(self, state):
        """Title, text and buttons of the Upload page for ready/uploading/paused/complete/updated."""
        self.upload_state = state
        title, hint = self.UPLOAD_STATES[state]
        self.transfer_title.configure(text=tr(title))
        self.transfer_hint.configure(text=tr(hint))
        if hasattr(self, "upload"):
            self.update_navigation()

    @property
    def upload_receipt(self):
        """The submission the Upload page acts on: a resumed one, or this session's capture."""
        return self._upload_sid or self._capture_receipt

    def selected(self):
        selected = self.history.selection()
        if not selected:
            self.status.set(tr("contributions.status_select_first"))
            return None
        return selected[0]

    def resume(self, sid=None):
        sid = sid or self.selected()
        if sid:
            self._upload_sid = sid
            self.tabs.select(0)
            self.show_step(3)
            self.set_upload_state("uploading")
            self.run(
                lambda: (
                    "status",
                    self.client.resume(sid, verify_in_app, self.request_consent, self.cancel, self.report_progress),
                )
            )

    def copy_id(self):
        sid = self.selected()
        if sid:
            self.window.clipboard_clear()
            self.window.clipboard_append(sid)
            self.status.set(tr("contributions.status_id_copied"))

    def withdraw(self):
        sid = self.selected()
        if sid and messagebox.askyesno(
            tr("contributions.withdraw_title"),
            tr("contributions.withdraw_question"),
            parent=self.window,
        ):
            self.run(lambda: ("withdrawn", self.client.withdraw(sid)))

    def export_receipt(self, sid=None):
        sid = sid or self.selected()
        if not sid:
            return
        path = filedialog.asksaveasfilename(
            parent=self.window,
            title=tr("contributions.save_receipt_title"),
            initialfile=sid + ".receipt.json",
            defaultextension=".json",
            filetypes=[(tr("contributions.receipt_filetype"), "*.json")],
        )
        if path:
            try:
                # This backup contains a capability. Never place it in Git or share it publicly.
                save(outside_git(path), self.client.read(sid))
                self.status.set(tr("contributions.status_receipt_saved"))
            except (ValueError, OSError):
                self.status.set(tr("contributions.status_receipt_save_failed"))

    def import_receipt(self):
        path = filedialog.askopenfilename(
            parent=self.window,
            title=tr("contributions.restore_receipt_title"),
            filetypes=[(tr("contributions.receipt_filetype"), "*.json")],
        )
        if not path:
            return
        try:
            if Path(path).stat().st_size > 32768:
                raise ValueError("Invalid receipt")
            record = json.loads(Path(path).read_text(encoding="utf-8"))
            self.client.validate(record)
            receipt, _ = self.client.paths(record["id"])
            if receipt.exists():
                raise ValueError("This receipt is already stored on this computer")
            save(receipt, record)
            self.refresh_history(record["id"])
            self.status.set(tr("contributions.status_receipt_restored"))
        except (ValueError, OSError, TypeError):
            self.status.set(tr("contributions.status_receipt_restore_failed"))

    def refresh_history(self, select=None):
        select = select or (self.history.selection() or [None])[0]
        self.history.delete(*self.history.get_children())
        self.rows = {r["id"]: r for r in self.client.receipts() if r.get("kind") == "dataset"}
        for sid, record in self.rows.items():
            state = record.get("state", "prepared")
            self.history.insert(
                "",
                "end",
                iid=sid,
                values=(
                    record.get("prepared", ""),
                    record.get("hmd", ""),
                    tr(self.STATUS_WORDS[state]) if state in self.STATUS_WORDS else state.capitalize(),
                    f"{record['size'] / 1024**2:.1f} MiB",
                    sid[:8],
                ),
            )
        if select in self.rows:
            self.history.selection_set(select)
        if self.rows:
            self.history_empty.place_forget()
        else:
            self.history_empty.place(relx=0.5, rely=0.5, anchor="center")
        self.update_history_buttons()

    # Receipt state -> language key of the word shown in the Status column.
    STATUS_WORDS = {
        "prepared": "contributions.state_prepared",
        "uploading": "contributions.state_uploading",
        "pending": "contributions.state_pending",
        "approved": "contributions.state_approved",
        "rejected": "contributions.state_rejected",
        "withdrawn": "contributions.state_withdrawn",
        "cancelled": "contributions.state_cancelled",
    }
    # Receipt states whose upload has finished one way or another.
    FINISHED = {"pending", "approved", "rejected", "withdrawn", "cancelled"}

    def update_history_buttons(self):
        # Actions on one contribution need a selection; receipt import/export does not.
        # Resume upload appears only for an unfinished upload, Refresh status only for a finished one.
        sid = (self.history.selection() or [None])[0]
        record = self.rows.get(sid)
        free = not (self.busy or self.capture_active)
        finished = record is not None and record.get("state") in self.FINISHED
        for button, shown in (
            (self.resume_button, record is not None and not finished),
            (self.refresh_button, finished or record is None),
        ):
            if shown:
                button.grid()
            else:
                button.grid_remove()
        for button in (self.resume_button, self.refresh_button, self.withdraw_button, self.copy_button):
            button.configure(state="normal" if record and free else "disabled")
        if record and record.get("state") == "withdrawn":
            self.withdraw_button.configure(state="disabled")

    def refresh_status(self):
        """Ask the service for a finished contribution's status and stay on this tab."""
        sid = self.selected()
        if sid:
            self.run(
                lambda: (
                    "refreshed",
                    self.client.resume(sid, verify_in_app, self.request_consent, self.cancel, self.report_progress),
                )
            )

    def ask_updated_consent(self, terms, event, result):
        dialog = tk.Toplevel(self.window)
        dialog.title(tr("contributions.updated_terms_title"))
        dialog.transient(self.window.winfo_toplevel())
        dialog.grab_set()
        accepted = [tk.BooleanVar(value=False), tk.BooleanVar(value=False)]
        from .native import decorate

        dialog.after(50, lambda: decorate(dialog))

        def finish(value):
            result.append(value)
            event.set()
            dialog.destroy()

        # Packed bottom-up first so the consents and button keep their space; only the text scrolls.
        ttk.Button(
            dialog,
            text=tr("contributions.continue_btn"),
            command=lambda: finish(True) if all(v.get() for v in accepted) else None,
        ).pack(side="bottom", pady=12)
        for variable, label in reversed(list(zip(accepted, dataset_consents()))):
            ttk.Checkbutton(dialog, text=label, variable=variable, style="Consent.TCheckbutton").pack(
                side="bottom", fill="x", padx=16, pady=(0, 6)
            )
        text = ScrolledText(dialog, width=80, height=22, **NOTICE_STYLE)
        style_notice(text)
        text.pack(fill="both", expand=True, padx=12, pady=12)
        render_notice(text, terms["text"])
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    text, done, total = value
                    if total:
                        self.progress.stop()
                        self.progress.configure(mode="determinate", value=100 * done / total)
                    elif str(self.progress.cget("mode")) != "indeterminate":
                        self.progress.configure(mode="indeterminate")
                        self.progress.start(15)
                    # Live progress sits under the bar; it is shown in the footer only off the Upload page.
                    detail = (
                        tr(
                            "contributions.progress_detail",
                            text=text.rstrip(".…。 "),
                            done=f"{done / 1024**2:.1f}",
                            total=f"{total / 1024**2:.1f}",
                            percent=round(100 * done / total),
                        )
                        if total
                        else text
                    )
                    self.progress_detail.configure(text=detail)
                    self.status.set("" if self.step == 3 and self.tabs.index("current") == 0 else detail)
                elif kind == "prepared":
                    self._capture_receipt = value
                    self.refresh_history(value)
                    self.update_navigation()
                elif kind == "consent":
                    self.ask_updated_consent(*value)
                elif kind in {"done", "error"}:
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.set_busy(False)
                    self.refresh_history()
                    if kind == "error":
                        self.status.set(value)
                        if self.config is None:
                            # The two refusals that ask for an EyeTrackVR update (compared as
                            # translated text, so this works in every language).
                            update_required = value in (
                                tr("contributions_service.key_unverified"),
                                tr("contributions_service.http_400"),
                            )
                            self.availability.set(
                                tr("contributions.availability_update")
                                if update_required
                                else tr("contributions.availability_offline")
                            )
                            # No manual refresh: retry the service check in the background.
                            self.window.after(_CONFIG_RETRY_MS, self._retry_config)
                        if self.upload_receipt:
                            self.set_upload_state("paused")
                    elif value[0] == "config":
                        self.config = value[1]
                        self.show_notice(self.config["terms"]["dataset"])
                        self.availability.set("" if self.config["enabled"] else tr("contributions.availability_paused"))
                        self.set_busy(False)
                        self.status.set("" if self.config["enabled"] else tr("contributions.status_collection_closed"))
                        full = self.config.get("quota_full") if self.config["enabled"] else None
                        if full:
                            # Warn before a long capture; an upload prepared now waits locally for Resume.
                            self.availability.set(
                                tr("contributions.availability_full")
                                if full == "lifetime_quota"
                                else tr("contributions.availability_daily_limit")
                            )
                            self.status.set(
                                QUOTA_MESSAGES[full]
                                if full == "lifetime_quota"
                                else tr("contributions.status_daily_limit")
                            )
                    elif value[0] == "refreshed":
                        # The table shows the new status.
                        self.status.set("")
                    elif value[0] == "withdrawn":
                        self.status.set(
                            tr("contributions.status_withdrawn")
                            if value[1] == "withdrawn"
                            else tr("contributions.status_local_cancelled")
                        )
                    else:
                        # The Upload page title and text describe the outcome.
                        self.set_upload_state("complete" if value[1] in {"pending", "approved"} else "updated")
                        self.status.set("")
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self._poll_job = self.window.after(50, self.poll)

    def _retry_config(self):
        if self.config is not None or not self.window.winfo_exists():
            return
        if self.busy or self.capture_active:
            self.window.after(_CONFIG_RETRY_MS, self._retry_config)
            return
        self.run(lambda: ("config", self.client.config()))

    def close(self):
        if self.capture_active:
            self.stop_capture()
            self.status.set(tr("contributions.status_stopping_recording"))
            return
        if self.busy:
            self.cancel.set()
            self.status.set(tr("contributions.status_pausing"))
            return
        if self.embedded:
            # EyeTrackVR's page: it hides the frame and keeps it for the next visit.
            self._on_hide()
        elif self.capture_controller:
            # EyeTrackVR owns one reusable dialog for the lifetime of the app.
            self.window.withdraw()
        else:
            self.window.after_cancel(self._poll_job)
            self.window.destroy()
