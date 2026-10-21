"""Tk contribution management. Worker threads communicate only through a queue."""
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import requests

from .client import ContributionClient, Paused, save, outside_git
from .verification import verify_in_app


class ContributionWindow:
    def __init__(self, parent, client=None, capture_controller=None):
        self.client = client or ContributionClient()
        self.capture_controller = capture_controller
        self.capture_active = False
        self._capture_path = None
        self._capture_receipt = None
        self.window = tk.Toplevel(parent)
        self.window.title("EyeTrackVR — Contributions")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.config = None
        self.rows = {}
        self.hmd = tk.StringVar()
        self.agree = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Checking upload availability…")
        self.availability = tk.StringVar(value="Connecting…")
        self.selection = tk.StringVar(value="Your recording will be attached automatically after capture.")
        self.capture_status = tk.StringVar(value="Ready when you are. Start tracking, put on your headset, and follow the guide.")
        self.step = 0
        self._last_progress = 0
        self._consent_dialog = None
        self._build_ui()
        self.show_step(0)
        self._load_bundled_notice()
        self.refresh_history()
        self.window.update_idletasks()
        # Keep the footer on screen even on a laptop or a scaled desktop.
        width = min(900, max(560, self.window.winfo_screenwidth() - 100))
        height = min(760, max(480, self.window.winfo_screenheight() - 140))
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(min(640, width), min(520, height))
        from .native import decorate
        self.window.after(50, lambda: decorate(self.window))
        self._poll_job = self.window.after(50, self.poll)
        self.run(lambda: ("config", self.client.config()))

    def _build_ui(self):
        from .native import asset
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        header = ttk.Frame(self.window, padding=(24, 18, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        try:
            self._logo = tk.PhotoImage(file=str(asset("logo.png")))
            ratio = max(1, (self._logo.width() + 47) // 48)
            self._logo = self._logo.subsample(ratio)
            ttk.Label(header, image=self._logo).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        except tk.TclError:
            pass
        ttk.Label(header, text="Contribute to EyeTrackVR", font=("Segoe UI", 18, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(header, textvariable=self.availability).grid(row=1, column=1, sticky="w", pady=(4, 0))
        self.retry = ttk.Button(header, text="Refresh", command=lambda: self.run(lambda: ("config", self.client.config())))
        self.retry.grid(row=0, column=2, rowspan=2, padx=(12, 0))

        self.tabs = ttk.Notebook(self.window)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=24)
        new = ttk.Frame(self.tabs, padding=(12, 14))
        history = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(new, text="Record & contribute")
        self.tabs.add(history, text="Your contributions")
        new.columnconfigure(0, weight=1)
        new.rowconfigure(1, weight=1)

        steps = ttk.Frame(new)
        steps.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.step_labels = []
        for index, title in enumerate(("1  Setup", "2  Capture", "3  Agreement", "4  Upload")):
            steps.columnconfigure(index, weight=1)
            label = ttk.Label(steps, text=title, anchor="center", padding=8)
            label.grid(row=0, column=index, sticky="ew")
            self.step_labels.append(label)
        self.pages = []
        for _ in range(4):
            page = ttk.Frame(new)
            page.grid(row=1, column=0, sticky="nsew")
            self.pages.append(page)

        # Recording details scroll on smaller displays; navigation/footer stay fixed.
        viewport = self.pages[0]
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, highlightthickness=0,
                           background=ttk.Style(self.window).lookup("TFrame", "background") or "#202020")
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll.set)
        recording = ttk.Frame(canvas)
        content_id = canvas.create_window((0, 0), window=recording, anchor="nw")
        recording.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(content_id, width=e.width))
        def scroll_recording(event):
            if self.step == 0 and str(event.widget).startswith(str(recording)):
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        self.window.bind("<MouseWheel>", scroll_recording, add="+")
        ttk.Label(recording, text="Help improve eye tracking", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(8, 12))
        self.intro = ttk.Label(recording, text="One guided session, from recording to upload. We attach the recording you make here automatically. Nothing is uploaded until you agree and choose to send it.", wraplength=640, justify="left")
        self.intro.pack(fill="x", pady=(0, 20))
        ttk.Label(recording, text="Before you begin", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        self.instructions = ttk.Label(recording, text="1. Start tracking and check that your cameras are working.\n2. Put on your headset and open SteamVR.\n3. Follow the voice prompts and the targets in VR.", wraplength=640, justify="left")
        self.instructions.pack(fill="x", pady=(0, 18))
        self.overlay = ttk.Checkbutton(recording, text="Use the VR calibration overlay (recommended)",
            variable=self.capture_controller.use_overlay_var if self.capture_controller else tk.BooleanVar(master=self.window, value=True))
        self.overlay.pack(anchor="w", pady=(0, 16))
        ttk.Label(recording, text="What HMD?", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 6))
        self.hmd_entry = ttk.Entry(recording, textvariable=self.hmd)
        self.hmd_entry.pack(fill="x")
        ttk.Label(recording, text="Type your headset model in your own words. No account or email is required.").pack(anchor="w", pady=8)
        ttk.Button(recording, text="Read the collection agreement first", command=self.preview_agreement).pack(anchor="w", pady=12)

        capture = self.pages[1]
        ttk.Label(capture, text="Follow the guided capture", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(16, 12))
        self.capture_instructions = ttk.Label(capture, text="Keep your headset on and follow the voice prompts and targets. When the session finishes, your recording will appear in the next step automatically.", wraplength=640, justify="left")
        self.capture_instructions.pack(fill="x", pady=(0, 20))
        self.capture_status_label = ttk.Label(capture, textvariable=self.capture_status, wraplength=640, font=("Segoe UI", 11), justify="left")
        self.capture_status_label.pack(fill="x", pady=16)
        self.capture_progress = ttk.Progressbar(capture, mode="indeterminate")
        self.capture_progress.pack(fill="x", pady=12)
        controls = ttk.Frame(capture)
        controls.pack(fill="x", pady=12)
        self.record_button = ttk.Button(controls, text="Start guided capture", command=self.start_capture)
        self.record_button.pack(side="left")
        self.stop_record_button = ttk.Button(controls, text="Stop recording", command=self.stop_capture, state="disabled")
        self.stop_record_button.pack(side="left", padx=10)

        agreement = self.pages[2]
        agreement.columnconfigure(0, weight=1)
        agreement.rowconfigure(2, weight=1)
        ttk.Label(agreement, text="Read the collection agreement", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        self.terms_summary = ttk.Label(agreement, text="Fovea Labs LLC · Adults 18+ · Raw recordings stay private · Trained models may be released", wraplength=640)
        self.terms_summary.grid(row=1, column=0, sticky="ew", pady=(6, 12))
        self.file_label = ttk.Label(agreement, textvariable=self.selection, wraplength=640)
        self.file_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        agreement.rowconfigure(2, weight=0)
        agreement.rowconfigure(3, weight=1)
        notice_panel = ttk.Frame(agreement)
        notice_panel.grid(row=3, column=0, sticky="nsew")
        notice_panel.columnconfigure(0, weight=1)
        notice_panel.rowconfigure(0, weight=1)
        self.notice = tk.Text(notice_panel, height=10, wrap="word", font=("Segoe UI", 10),
                                  background="#20242b", foreground="#f1f4f8",
                                  selectbackground="#365b80", relief="flat", borderwidth=0,
                                  padx=16, pady=14, spacing1=4, spacing3=8, takefocus=True)
        self.notice.grid(row=0, column=0, sticky="nsew")
        notice_scroll = ttk.Scrollbar(notice_panel, orient="vertical", command=self.notice.yview)
        notice_scroll.grid(row=0, column=1, sticky="ns")
        self.notice.configure(yscrollcommand=notice_scroll.set)
        self.notice.configure(state="disabled")
        self.notice_version = tk.StringVar()
        ttk.Label(agreement, textvariable=self.notice_version).grid(row=4, column=0, sticky="w", pady=(6, 8))
        self.consent = ttk.Checkbutton(agreement, variable=self.agree,
            text="I am 18+, these are my own recordings,\nand I agree to this collection agreement.",
            command=self.update_navigation)
        self.consent.grid(row=5, column=0, sticky="ew")

        transfer = self.pages[3]
        self.transfer_title = ttk.Label(transfer, text="Ready to upload securely", font=("Segoe UI", 16, "bold"))
        self.transfer_title.pack(anchor="w", pady=(24, 12))
        self.transfer_hint = ttk.Label(transfer, text="EyeTrackVR encrypts your recording before sending it. Verification stays inside the app.", wraplength=640)
        self.transfer_hint.pack(fill="x", pady=(0, 24))
        self.progress = ttk.Progressbar(transfer, maximum=100)
        self.progress.pack(fill="x", pady=12)
        self.pause = ttk.Button(transfer, text="Pause upload", command=self.cancel.set, state="disabled")
        self.pause.pack(anchor="w", pady=12)
        self.new_session_button = ttk.Button(transfer, text="Record another session", command=self.new_session)
        self.new_session_button.pack(anchor="w", pady=8)
        ttk.Label(transfer, text="If your connection drops, use Your contributions → Resume.\nYour exact encrypted upload is kept on this computer.", wraplength=640).pack(anchor="w", pady=16)

        navigation = ttk.Frame(new, padding=(0, 14, 0, 0))
        navigation.grid(row=2, column=0, sticky="ew")
        self.back = ttk.Button(navigation, text="Back", command=self.go_back)
        self.back.pack(side="left")
        self.upload = ttk.Button(navigation, text="Verify and upload", command=self.start_upload)
        self.next = ttk.Button(navigation, text="Continue to capture", command=self.continue_flow)
        self.next.pack(side="right")
        self.upload.pack(side="right")

        history.columnconfigure(0, weight=1)
        history.rowconfigure(1, weight=1)
        ttk.Label(history, text="Resume an upload or withdraw a contribution", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.history = ttk.Treeview(history, columns=("hmd", "state", "size"), show="headings", height=6, selectmode="browse")
        for key, title in (("hmd", "HMD"), ("state", "Last known status"), ("size", "Size")):
            self.history.heading(key, text=title)
            self.history.column(key, width=130, minwidth=80)
        self.history.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(history, orient="vertical", command=self.history.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.history.configure(yscrollcommand=scrollbar.set)
        actions = ttk.Frame(history)
        actions.grid(row=2, column=0, sticky="ew", pady=12)
        self.resume_button = ttk.Button(actions, text="Resume / refresh", command=self.resume)
        self.resume_button.grid(row=0, column=0, padx=(0, 8), pady=4)
        self.withdraw_button = ttk.Button(actions, text="Withdraw", command=self.withdraw)
        self.withdraw_button.grid(row=0, column=1, padx=(0, 8), pady=4)
        self.export_button = ttk.Button(actions, text="Save receipt…", command=self.export_receipt)
        self.export_button.grid(row=1, column=0, padx=(0, 8), pady=4)
        self.import_button = ttk.Button(actions, text="Restore receipt…", command=self.import_receipt)
        self.import_button.grid(row=1, column=1, padx=(0, 8), pady=4)
        self.receipt_help = ttk.Label(history,
            text="Keep your private receipts for withdrawal. A receipt backup does not include the encrypted resume file.\n\n"
                 "Lost your receipt? Contact support@fovea-labs.com. Include your submission ID and upload date/time if available. "
                 "Never email or share the private receipt itself.",
            wraplength=620, justify="left")
        self.receipt_help.grid(row=3, column=0, sticky="ew", pady=8)

        footer = ttk.Frame(self.window, padding=(24, 12, 24, 18))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status, wraplength=620, justify="left")
        self.status_label.grid(row=0, column=0, sticky="ew")
        ttk.Button(footer, text="Close", command=self.close).grid(row=0, column=1, padx=(12, 0))
        ttk.Label(footer, text="Privacy contact: support@fovea-labs.com").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.window.bind("<Configure>", self._resize_wrap, add="+")

    def _resize_wrap(self, event):
        if event.widget is self.window:
            for widget in (self.intro, self.instructions, self.capture_instructions, self.capture_status_label, self.file_label, self.terms_summary, self.transfer_hint, self.receipt_help):
                widget.configure(wraplength=max(280, event.width - 130))
            self.status_label.configure(wraplength=max(240, event.width - 160))

    def _load_bundled_notice(self):
        try:
            self.show_notice(json.loads(Path(__file__).with_name("notice.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.notice.configure(state="normal")
            self.notice.insert("1.0", "The agreement could not be loaded. Refresh to retrieve it before uploading.")
            self.notice.configure(state="disabled")

    def show_step(self, step):
        self.step = max(0, min(3, step))
        self.pages[self.step].tkraise()
        for index, label in enumerate(self.step_labels):
            label.configure(font=("Segoe UI", 10, "bold" if index == self.step else "normal"))
        self.next.pack_forget()
        self.upload.pack_forget()
        if self.step == 0:
            self.next.configure(text="Continue to capture")
            self.next.pack(side="right")
        elif self.step == 1 and self._capture_path:
            self.next.configure(text="Continue to agreement")
            self.next.pack(side="right")
        elif self.step == 2:
            self.upload.pack(side="right")
        self.update_navigation()

    def update_navigation(self):
        blocked = self.busy or self.capture_active
        eligible = self._capture_path is not None and self._capture_receipt is None
        self.upload.configure(state="normal" if not blocked and eligible and self.config and self.config["enabled"] and self.agree.get() else "disabled")
        self.next.configure(state="disabled" if blocked else "normal")
        self.back.configure(state="disabled" if blocked or self.step == 0 else "normal")
        self.record_button.configure(state="normal" if not blocked and self.capture_controller else "disabled")
        self.stop_record_button.configure(state="normal" if self.capture_active else "disabled")

    def go_back(self):
        if self.busy or self.capture_active:
            return
        self.show_step(0 if self.step == 2 and self._capture_path is None else self.step - 1)

    def preview_agreement(self):
        self.show_step(2)
        self.status.set("You can read the agreement now. Complete a guided capture before uploading.")

    def continue_flow(self):
        if self.step == 0:
            if not self.hmd.get().strip():
                self.status.set("Enter your HMD before starting the guided capture.")
                self.hmd_entry.focus_set()
                return
            self.show_step(1)
            self.status.set("Start the guided capture when your cameras and headset are ready.")
        elif self.step == 1:
            self.to_agreement()

    def to_agreement(self):
        if self._capture_path is None or not self._capture_path.is_file():
            self.status.set("Complete the guided capture first. Its recording will attach automatically.")
            return
        self.agree.set(False)
        self.show_step(2)
        self.notice.yview_moveto(0)
        self.status.set("Your new recording is attached. Read the agreement, then agree to verify and upload.")

    def clear_capture(self):
        self._capture_path = None
        self._capture_receipt = None
        self.selection.set("Your recording will be attached automatically after capture.")
        self.agree.set(False)
        self.update_navigation()

    def start_capture(self):
        if self.busy or self.capture_active or not self.capture_controller:
            return
        if not self.hmd.get().strip():
            self.show_step(0)
            self.status.set("Enter your HMD before recording.")
            return
        self.capture_controller._start_collection()
        if not self.capture_active:
            self.status.set(self.capture_status.get())

    def new_session(self):
        if self.busy or self.capture_active:
            return
        self.clear_capture()
        self.capture_status.set("Ready when you are. Follow the guide to make a new recording.")
        self.show_step(0)
        self.status.set("Start a new guided capture. Earlier submissions stay in Your contributions.")

    def stop_capture(self):
        if self.capture_controller:
            self.capture_controller._stop_collection()
            self.status.set("Stopping capture. An unfinished session will not be attached.")

    def capture_started(self):
        self.clear_capture()
        self.capture_active = True
        self.show_step(1)
        self.capture_progress.start(15)
        self.set_busy(self.busy)
        self.status.set("Recording in progress. Follow the guide in your headset.")

    def capture_stopped(self, path):
        self.capture_active = False
        self.capture_progress.stop()
        if path is not None and Path(path).is_file():
            self._capture_path = Path(path).resolve()
            self._capture_receipt = None
            self.selection.set("Automatically attached: your new recording" +
                               f" · {self._capture_path.stat().st_size / 1024**2:.1f} MiB")
            self.agree.set(False)
            self.tabs.select(0)
            self.show_step(2)
            self.status.set("Capture complete. Your recording is attached. Review the agreement before uploading.")
        else:
            self.clear_capture()
            self.show_step(1)
            self.status.set("Capture did not finish. Start again when you are ready; nothing will be uploaded.")
        self.set_busy(self.busy)

    def show_notice(self, terms):
        self.notice.configure(state="normal")
        self.notice.delete("1.0", "end")
        self.notice.insert("1.0", terms["text"])
        self.notice.configure(state="disabled")
        self.agree.set(False)
        self.notice_version.set("Agreement version: " + terms["version"])
        self.notice.yview_moveto(0)

    def set_busy(self, busy):
        self.busy = busy
        blocked = busy or self.capture_active
        for widget in (self.hmd_entry, self.overlay, self.consent, self.resume_button,
                       self.withdraw_button, self.export_button, self.import_button, self.new_session_button):
            widget.configure(state="disabled" if blocked else "normal")
        self.retry.configure(state="disabled" if blocked else "normal")
        self.back.configure(state="disabled" if busy or self.step == 0 else "normal")
        self.update_navigation()
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
                self.events.put(("error", "Connection interrupted. Your receipt and encrypted upload are saved; use Resume."))
            except ValueError as error:
                self.events.put(("error", str(error)))
            except Exception:
                self.events.put(("error", "The operation could not finish. Your private receipt is retained. Check the app dependencies and try Resume."))
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
        if not self.config or not self.config["enabled"] or not self.agree.get():
            self.status.set("Review and agree to the collection terms first.")
            return
        if self.capture_active or self._capture_path is None or self._capture_receipt is not None:
            self.status.set("Complete a new capture, or resume the existing submission from Your contributions.")
            return
        # Snapshot all Tk values on its owning thread.
        source, hmd, terms = self._capture_path, self.hmd.get(), dict(self.config["terms"]["dataset"])
        self.agree.set(False)
        def upload():
            sid = self.client.prepare(source, hmd, terms, self.cancel, self.report_progress)
            self.events.put(("prepared", sid))
            return ("status", self.client.resume(sid, verify_in_app, self.request_consent,
                                                self.cancel, self.report_progress))
        self.show_step(3)
        self.transfer_title.configure(text="Uploading your recording")
        self.run(upload)

    def selected(self):
        selected = self.history.selection()
        if not selected:
            self.status.set("Select a contribution first.")
            return None
        return selected[0]

    def resume(self):
        sid = self.selected()
        if sid:
            self.tabs.select(0)
            self.show_step(3)
            self.run(lambda: ("status", self.client.resume(sid, verify_in_app, self.request_consent,
                                                          self.cancel, self.report_progress)))

    def withdraw(self):
        sid = self.selected()
        if sid and messagebox.askyesno("Withdraw contribution", "Stop future use of this contribution and request deletion?\n"
                                      "Hosted downloads will be blocked immediately after confirmation by the service.", parent=self.window):
            self.run(lambda: ("status", self.client.withdraw(sid)))

    def export_receipt(self):
        sid = self.selected()
        if not sid:
            return
        path = filedialog.asksaveasfilename(parent=self.window, title="Save private withdrawal receipt",
                initialfile=sid + ".receipt.json", defaultextension=".json", filetypes=[("Private receipt", "*.json")])
        if path:
            try:
                # This backup contains a capability. Never place it in Git or share it publicly.
                save(outside_git(path), self.client.read(sid))
                self.status.set("Private receipt saved. It permits withdrawal; keep it secure. Resume data stays on this computer.")
            except (ValueError, OSError):
                self.status.set("Could not save the private receipt. Choose a private location outside Git.")

    def import_receipt(self):
        path = filedialog.askopenfilename(parent=self.window, title="Restore private withdrawal receipt",
                                          filetypes=[("Private receipt", "*.json")])
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
            self.status.set("Receipt restored. Withdrawal is available; upload resume also requires the original encrypted payload.")
        except (ValueError, OSError, TypeError):
            self.status.set("Could not restore this receipt. Use an EyeTrackVR receipt for this service.")

    def refresh_history(self, select=None):
        select = select or (self.history.selection() or [None])[0]
        self.history.delete(*self.history.get_children())
        self.rows = {r["id"]: r for r in self.client.receipts()}
        for sid, record in self.rows.items():
            self.history.insert("", "end", iid=sid, values=(record.get("hmd", ""), record.get("state", "prepared"),
                               f'{record["size"] / 1024**2:.1f} MiB'))
        if select in self.rows:
            self.history.selection_set(select)

    def ask_updated_consent(self, terms, event, result):
        dialog = tk.Toplevel(self.window)
        dialog.title("Updated contribution terms")
        dialog.transient(self.window)
        dialog.grab_set()
        text = ScrolledText(dialog, wrap="word", width=80, height=22)
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", terms["text"])
        text.configure(state="disabled")
        accepted = tk.BooleanVar(value=False)
        from .native import decorate
        dialog.after(50, lambda: decorate(dialog))
        text.configure(background="#20242b", foreground="#f1f4f8", padx=14, pady=12)
        ttk.Checkbutton(dialog, text="I am 18+, these are my recordings, and I agree to these terms.",
                        variable=accepted).pack(padx=12)
        def finish(value):
            result.append(value)
            event.set()
            dialog.destroy()
        ttk.Button(dialog, text="Continue", command=lambda: finish(True) if accepted.get() else None).pack(pady=12)
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
                    self.status.set(text + (f" {done / 1024**2:.1f} / {total / 1024**2:.1f} MiB" if total else ""))
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
                            self.availability.set("Unable to connect · Agreement available offline · Refresh to retry")
                        self.transfer_title.configure(text="Upload paused")
                    elif value[0] == "config":
                        self.config = value[1]
                        self.show_notice(self.config["terms"]["dataset"])
                        self.availability.set("Uploads enabled · Encrypted transfer" if self.config["enabled"] else "Uploads paused · Agreement available to read")
                        self.set_busy(False)
                        self.status.set("Enter your HMD, then continue to the guided capture." if self.config["enabled"] else
                                        "Collection is currently closed. Saved receipts remain available for withdrawal.")
                    else:
                        self.transfer_title.configure(text="Upload complete" if value[1] in {"pending", "approved"} else "Contribution updated")
                        self.status.set({"pending": "Uploaded successfully. Awaiting private maintainer review.",
                                         "approved": "Contribution approved.", "withdrawn": "Withdrawn. Hosted downloads are blocked; cleanup is scheduled.",
                                         "cancelled": "Local preparation cancelled; no hosted submission was found."}.get(value[1], "Status: " + value[1]))
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self._poll_job = self.window.after(50, self.poll)

    def close(self):
        if self.capture_active:
            self.stop_capture()
            self.status.set("Stopping recording safely. Close again when it has stopped.")
            return
        if self.busy:
            self.cancel.set()
            self.status.set("Pausing safely. Your receipt and encrypted payload will be kept; close once paused.")
            return
        if self.capture_controller:
            # EyeTrackVR owns one reusable dialog for the lifetime of the app.
            self.window.withdraw()
        else:
            self.window.after_cancel(self._poll_job)
            self.window.destroy()
