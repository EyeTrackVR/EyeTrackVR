"""Bug report window: a written description plus app logs, encrypted end to end.

Reports use the service's separate "issue" kind: their own consent notice,
90-day retention, quotas and receipt folder (issue_home), apart from dataset
contributions. Worker threads communicate only through a queue."""

from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk

import requests

from .client import ContributionClient, Paused, issue_home
from .window import ACCENT, FONT_HEADING, FONT_TITLE, MUTED, NOTICE_STYLE, render_notice, setup_styles, style_notice

MAX_DESCRIPTION = 20000
# Only the newest part of each log is attached; issue_bundle caps the report at 8 MiB.
LOG_TAIL_BYTES = 3 * 1024**2
# Short checkbox labels; ticking them gives the two numbered confirmations at the top of the notice.
ISSUE_CONSENTS = (
    "I'm an adult (18+), I removed other people's personal information, and I accept the bug report notice.",
    "I consent to my report being transferred to and stored in the United States.",
)
DESCRIPTION_TEMPLATE = "What happened?\n\nWhat did you expect?\n\nSteps to reproduce:\n1. "


def previous_log(current):
    """The most recent log from an earlier session (the one that crashed, if any)."""
    from utils.logging_utils import LOG_NAME_PREFIX, log_directory

    logs = sorted(log_directory().glob(f"{LOG_NAME_PREFIX}-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    current = Path(current).resolve() if current else None
    return next((path for path in logs if path.resolve() != current), None)


def write_tail(source, destination, limit=LOG_TAIL_BYTES):
    """Copy the last `limit` bytes of a log as clean UTF-8 text."""
    with Path(source).open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        data = stream.read()
    text = data.decode("utf-8", errors="replace").replace("\x00", "")
    if size > limit:
        # Drop the partial first line and say the log was cut.
        text = f"[showing the last {limit // 1024**2} MiB of {size / 1024**2:.1f} MiB]\n" + text.split("\n", 1)[-1]
    # Bytes, not text mode: Windows would turn the log's CRLF into CR CR LF.
    Path(destination).write_bytes(text.encode("utf-8"))


class ReportWindow:
    def __init__(self, parent, details=None, client=None):
        self.parent = parent
        self.details = details
        self._client = client
        self.window = tk.Toplevel(parent)
        self.window.title("EyeTrackVR Bug Report")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.config = None
        # Two separate consents: the notice, then the transfer to the United States.
        self.agree = tk.BooleanVar(value=False)
        self.agree_transfer = tk.BooleanVar(value=False)
        self.include_log = tk.BooleanVar(value=True)
        self.include_previous = tk.BooleanVar(value=False)
        self.include_details = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Connecting to the report service…")
        self.sent_id = tk.StringVar()
        self._last_progress = 0
        # (fingerprint, id) of a report prepared in this window but not yet delivered.
        self._pending = None
        self._build_ui()
        self.window.update_idletasks()
        width = min(720, max(560, self.window.winfo_screenwidth() - 100))
        height = min(760, max(480, self.window.winfo_screenheight() - 140))
        # The smallest height that fits every fixed row with both text boxes at their minimum.
        needed = min(self.window.winfo_reqheight() + 40, self.window.winfo_screenheight() - 80)
        height = max(height, needed)
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(min(560, width), min(max(480, needed), height))
        from .native import decorate

        self.window.after(50, lambda: decorate(self.window))
        self._poll_job = self.window.after(50, self.poll)
        self.load_config()

    @property
    def client(self):
        # Created on first use so opening the window never blocks on the receipt folder.
        if self._client is None:
            self._client = ContributionClient(directory=issue_home())
        return self._client

    def _build_ui(self):
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        setup_styles(self.window)
        # The form: only the description (and the notice, when opened) grow; everything else keeps
        # its natural size and the window's minimum size always fits it (see __init__).
        body = self.form = ttk.Frame(self.window, padding=(20, 16, 20, 8))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)
        ttk.Label(body, text="Report a bug", font=FONT_TITLE).grid(row=0, column=0, sticky="w")
        self.intro = ttk.Label(
            body,
            wraplength=640,
            justify="left",
            style="Muted.TLabel",
            foreground=MUTED,
            text=(
                "Your report and logs are encrypted on this computer and only the EyeTrackVR developers can read them."
            ),
        )
        self.intro.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        ttk.Label(body, text="What went wrong?", font=FONT_HEADING).grid(row=2, column=0, sticky="w", pady=(0, 6))
        description_panel = ttk.Frame(body)
        description_panel.grid(row=3, column=0, sticky="nsew")
        description_panel.columnconfigure(0, weight=1)
        description_panel.rowconfigure(0, weight=1)
        self.description = tk.Text(
            description_panel,
            height=5,
            wrap="word",
            font=NOTICE_STYLE["font"],
            undo=True,
            background="#20242b",
            foreground="#f1f4f8",
            insertbackground="#f1f4f8",
            relief="flat",
            padx=12,
            pady=10,
        )
        self.description.grid(row=0, column=0, sticky="nsew")
        description_scroll = ttk.Scrollbar(description_panel, orient="vertical", command=self.description.yview)
        description_scroll.grid(row=0, column=1, sticky="ns")
        self.description.configure(yscrollcommand=description_scroll.set)
        self.description.insert("1.0", DESCRIPTION_TEMPLATE)
        self.description.bind("<<Modified>>", self._description_changed)

        attachments = ttk.Frame(body)
        attachments.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.log_check = ttk.Checkbutton(attachments, variable=self.include_log, text="Attach this session's app log")
        self.log_check.grid(row=0, column=0, sticky="w")
        self.previous_check = ttk.Checkbutton(
            attachments,
            variable=self.include_previous,
            text="Attach the previous session's log (use this if the app crashed)",
        )
        self.previous_check.grid(row=1, column=0, sticky="w")
        self.details_check = ttk.Checkbutton(
            attachments,
            variable=self.include_details,
            text="Include app details (version, OS, tracker and model settings)",
        )
        self.details_check.grid(row=2, column=0, sticky="w")
        self.attach_hint = ttk.Label(
            body,
            style="Small.TLabel",
            foreground=MUTED,
            wraplength=640,
            justify="left",
            text=(
                "Home folder paths, IP and email addresses, and tokens are removed from logs before encryption. "
                "Do not include passwords or anyone else's personal information."
            ),
        )
        self.attach_hint.grid(row=5, column=0, sticky="ew", pady=(4, 12))

        # A layered notice: a short summary with the full notice one click away.
        summary = ttk.Frame(body)
        summary.grid(row=6, column=0, sticky="ew")
        summary.columnconfigure(0, weight=1)
        self.notice_summary = ttk.Label(
            summary,
            wraplength=500,
            justify="left",
            text=(
                "Fovea Labs LLC (United States) keeps reports for up to 90 days to fix bugs and give support. "
                "They are never used as eye-tracking training data or posted publicly."
            ),
        )
        self.notice_summary.grid(row=0, column=0, sticky="w")
        self.notice_toggle = ttk.Button(summary, text="Read the full notice", command=self.toggle_notice)
        self.notice_toggle.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.notice_panel = ttk.Frame(body)
        self.notice_panel.grid(row=7, column=0, sticky="nsew", pady=(8, 0))
        self.notice_panel.columnconfigure(0, weight=1)
        self.notice_panel.rowconfigure(0, weight=1)
        self.notice = tk.Text(self.notice_panel, height=6, takefocus=True, **NOTICE_STYLE)
        style_notice(self.notice)
        self.notice.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.notice_panel, orient="vertical", command=self.notice.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.notice.configure(yscrollcommand=scroll.set)
        self._set_notice("The notice loads from the report service…")
        self.notice_panel.grid_remove()
        self.consent = ttk.Checkbutton(
            body, variable=self.agree, command=self.update_buttons, text=ISSUE_CONSENTS[0], style="Consent.TCheckbutton"
        )
        self.consent.grid(row=8, column=0, sticky="ew", pady=(12, 0))
        self.consent_transfer = ttk.Checkbutton(
            body,
            variable=self.agree_transfer,
            command=self.update_buttons,
            text=ISSUE_CONSENTS[1],
            style="Consent.TCheckbutton",
        )
        self.consent_transfer.grid(row=9, column=0, sticky="ew", pady=(4, 0))
        # Says why Send report is unavailable.
        self.send_hint = ttk.Label(body, style="Muted.TLabel", foreground=MUTED)
        self.send_hint.grid(row=10, column=0, sticky="w", pady=(4, 0))
        self.progress = ttk.Progressbar(body, maximum=100)
        self.progress.grid(row=11, column=0, sticky="ew", pady=(8, 0))

        # Shown instead of the form once a report is delivered.
        self.sent_panel = ttk.Frame(self.window, padding=(20, 40, 20, 8))
        self.sent_panel.grid(row=0, column=0, sticky="nsew")
        self.sent_panel.columnconfigure(1, weight=1)
        ttk.Label(self.sent_panel, text="✓", style="Mark.TLabel", foreground=ACCENT).grid(
            row=0, column=0, rowspan=2, sticky="n", padx=(0, 16)
        )
        self.sent_title = ttk.Label(self.sent_panel, text="Report sent", font=FONT_TITLE)
        self.sent_title.grid(row=0, column=1, sticky="w", pady=(6, 6))
        self.sent_text = ttk.Label(self.sent_panel, wraplength=520, justify="left")
        self.sent_text.grid(row=1, column=1, sticky="ew")
        id_row = ttk.Frame(self.sent_panel)
        id_row.grid(row=2, column=1, sticky="w", pady=(18, 0))
        ttk.Label(id_row, text="Report ID", style="Muted.TLabel", foreground=MUTED).pack(side="left")
        self.id_label = ttk.Label(id_row, textvariable=self.sent_id, font=FONT_HEADING)
        self.id_label.pack(side="left", padx=(10, 14))
        self.copy_button = ttk.Button(id_row, text="Copy report ID", command=self.copy_id)
        self.copy_button.pack(side="left")
        ttk.Button(self.sent_panel, text="Write another report", command=self.new_report).grid(
            row=3, column=1, sticky="w", pady=(24, 0)
        )
        self.sent_panel.grid_remove()

        # The status line is only for errors and live progress; it hides itself when empty.
        footer = ttk.Frame(self.window, padding=(20, 8, 20, 16))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status, wraplength=440, justify="left")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.status.trace_add(
            "write", lambda *_: self.status_label.grid() if self.status.get() else self.status_label.grid_remove()
        )
        self.send_button = ttk.Button(footer, text="Send report", style="Accent.TButton", command=self.send)
        self.send_button.grid(row=0, column=1, padx=(12, 0))
        ttk.Button(footer, text="Close", command=self.close).grid(row=0, column=2, padx=(8, 0))
        self.window.bind("<Configure>", self._resize_wrap, add="+")
        self.update_buttons()

    def _resize_wrap(self, event):
        if event.widget is self.window:
            for widget in (self.intro, self.attach_hint):
                widget.configure(wraplength=max(280, event.width - 60))
            self.notice_summary.configure(wraplength=max(240, event.width - 240))
            self.sent_text.configure(wraplength=max(240, event.width - 140))
            self.status_label.configure(wraplength=max(240, event.width - 260))
            ttk.Style(self.window).configure("Consent.TCheckbutton", wraplength=max(280, event.width - 90))

    def toggle_notice(self):
        """Open or close the full notice; while open it shares the spare height with the description."""
        if self.notice_panel.winfo_ismapped():
            self.notice_panel.grid_remove()
            self.form.rowconfigure(7, weight=0)
            self.notice_toggle.configure(text="Read the full notice")
        else:
            self.notice_panel.grid()
            self.form.rowconfigure(7, weight=2)
            self.notice_toggle.configure(text="Hide the notice")
            self.notice.yview_moveto(0)

    def new_report(self):
        """Back to an empty form after a report was sent."""
        self.sent_panel.grid_remove()
        self.form.grid()
        self.send_button.grid()
        self.description.configure(state="normal")
        self.description.delete("1.0", "end")
        self.description.insert("1.0", DESCRIPTION_TEMPLATE)
        self.progress.configure(value=0)
        self.sent_id.set("")
        self.status.set("")
        self.update_buttons()

    def _set_notice(self, text):
        self.notice.configure(state="normal")
        self.notice.delete("1.0", "end")
        self.notice.insert("1.0", text, "body")
        self.notice.configure(state="disabled")

    def _description_changed(self, _event=None):
        self.description.edit_modified(False)
        self.update_buttons()

    def description_text(self):
        return self.description.get("1.0", "end-1c").strip()

    def update_buttons(self):
        text = self.description_text()
        ready = (
            not self.busy
            and self.config is not None
            and self.config["enabled"]
            and self.consented()
            and 0 < len(text) <= MAX_DESCRIPTION
        )
        self.send_button.configure(state="normal" if ready else "disabled")
        if not text:
            hint = "Describe the problem to continue"
        elif not self.consented():
            hint = "Tick both boxes to send the report"
        else:
            hint = ""
        self.send_hint.configure(text=hint)
        # The progress bar only appears while sending or once a report went out.
        if self.busy or float(self.progress.cget("value")) > 0:
            self.progress.grid()
        else:
            self.progress.grid_remove()
        for widget in (self.log_check, self.previous_check, self.details_check, self.consent, self.consent_transfer):
            widget.configure(state="disabled" if self.busy else "normal")
        self.description.configure(state="disabled" if self.busy else "normal")

    def consented(self):
        return self.agree.get() and self.agree_transfer.get()

    def load_config(self):
        self.run(lambda: ("config", self.client.config()))

    def run(self, operation):
        if self.busy:
            return
        self.cancel.clear()
        self.busy = True
        self.update_buttons()

        def worker():
            try:
                with self.client.exclusive():
                    self.events.put(("done", operation()))
            except Paused as error:
                self.events.put(("error", str(error)))
            except requests.RequestException:
                self.events.put(
                    (
                        "error",
                        "Could not reach the report service. Check your connection and press "
                        "Send report again; your encrypted report is kept.",
                    )
                )
            except ValueError as error:
                self.events.put(("error", str(error)))
            except Exception:
                self.events.put(("error", "The report could not be sent. Please ping prohurtz on Discord."))

        threading.Thread(target=worker, daemon=True).start()

    def report_progress(self, text, done, total):
        current = time.monotonic()
        if current - self._last_progress > 0.1 or done == total:
            self.events.put(("progress", (text, done, total)))
            self._last_progress = current

    def _discard_unsent(self, keep=None):
        """Cancel undelivered reports this one replaces, so stale ciphertext doesn't pile up."""
        for record in self.client.receipts():
            if record["id"] != keep and record.get("state") in {"prepared", "uploading"}:
                try:
                    self.client.withdraw(record["id"])
                except (ValueError, OSError, requests.RequestException):
                    pass

    def send(self):
        if self.config is None or not self.consented():
            return
        # Snapshot every Tk value on the Tk thread.
        description = self.description_text()
        if self.include_details.get() and self.details is not None:
            try:
                description += "\n\n--- App details ---\n" + self.details()
            except Exception:
                pass
        description = description[:MAX_DESCRIPTION]
        logs = []
        from utils.logging_utils import current_log_path

        current = current_log_path()
        if self.include_log.get() and current and Path(current).is_file():
            logs.append(current)
        if self.include_previous.get():
            earlier = previous_log(current)
            if earlier is not None:
                logs.append(earlier)
        terms = dict(self.config["terms"]["issue"])
        self.agree.set(False)
        self.agree_transfer.set(False)
        from .verification import verify_in_app

        # Retrying an unchanged report resumes its exact ciphertext; an edited one is re-made.
        fingerprint = (description, tuple(str(path) for path in logs), terms["version"])
        pending = self._pending[1] if self._pending and self._pending[0] == fingerprint else None

        def upload():
            sid = pending
            if sid is None:
                self._discard_unsent()
                with tempfile.TemporaryDirectory(prefix="logs-", dir=self.client.directory) as tmp:
                    tails = []
                    for index, path in enumerate(logs):
                        tail = Path(tmp) / f"log-{index + 1}.txt"
                        write_tail(path, tail)
                        tails.append(tail)
                    sid = self.client.prepare_issue(description, tails, terms, self.cancel, self.report_progress)
                self._pending = (fingerprint, sid)
            return (
                "sent",
                sid,
                self.client.resume(sid, verify_in_app, lambda _terms: False, self.cancel, self.report_progress),
            )

        self.status.set("Encrypting your report…")
        self.run(upload)

    def copy_id(self):
        sid = getattr(self, "_sent_sid", None)
        if sid:
            self.window.clipboard_clear()
            self.window.clipboard_append(sid)
            self.copy_button.configure(text="Copied")
            self.window.after(
                1500, lambda: self.copy_button.winfo_exists() and self.copy_button.configure(text="Copy report ID")
            )

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
                    self.status.set(text + (f" {round(100 * done / total)}%" if total else ""))
                    continue
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.busy = False
                if kind == "error":
                    self.progress.configure(value=0)
                    self.status.set(value)
                    if self.config is None:
                        self._set_notice(
                            "The report service could not be reached, so the notice is unavailable. "
                            "Close and reopen this window to try again."
                        )
                elif value[0] == "config":
                    self.config = value[1]
                    render_notice(self.notice, self.config["terms"]["issue"]["text"], title=False)
                    full = self.config.get("issue_quota_full")
                    if not self.config["enabled"]:
                        self.status.set("Bug reports are closed right now. Please ping prohurtz on Discord.")
                    elif full:
                        from .client import ISSUE_QUOTA_MESSAGES

                        self.status.set(ISSUE_QUOTA_MESSAGES[full])
                    else:
                        self.status.set("")
                elif value[0] == "sent":
                    _, sid, state = value
                    self._sent_sid = sid
                    self._pending = None
                    self.progress.configure(value=100)
                    self.status.set("")
                    delivered = state in {"pending", "approved"}
                    self.sent_title.configure(text="Report sent" if delivered else "Report status: " + state)
                    self.sent_text.configure(
                        text=(
                            "Thank you! The EyeTrackVR developers can now read your report. If you follow up on "
                            "Discord or by email, mention the report ID so we can find it."
                            if delivered
                            else "The report service gave this status for your report. Mention the report ID if you contact us."
                        )
                    )
                    self.sent_id.set(sid[:8])
                    self.form.grid_remove()
                    self.send_button.grid_remove()
                    self.sent_panel.grid()
                    self.description.configure(state="normal")
                    self.description.delete("1.0", "end")
                self.update_buttons()
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self._poll_job = self.window.after(50, self.poll)

    def show(self):
        self.window.deiconify()
        self.window.update_idletasks()
        width, height = self.window.winfo_width(), self.window.winfo_height()
        x = self.parent.winfo_rootx() + max(0, (self.parent.winfo_width() - width) // 2)
        y = self.parent.winfo_rooty() + max(0, (self.parent.winfo_height() - height) // 2)
        x = max(0, min(x, self.window.winfo_screenwidth() - width))
        y = max(0, min(y, self.window.winfo_screenheight() - height - 60))
        self.window.geometry(f"+{x}+{y}")
        self.window.lift()
        self.description.focus_set()
        if self.config is None and not self.busy:
            self.load_config()

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set("Stopping safely. Your encrypted report is kept and sends next time.")
            return
        self.window.withdraw()
