import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path


LOG_DIR_NAME = "logs"
LOG_RETENTION_COUNT = 3
LOG_NAME_PREFIX = "eyetrackapp"

_current_log_path: Path | None = None


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = self.COLORS.get(record.levelno)
        if not color:
            return message
        return f"{color}{message}{self.RESET}"


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _prune_old_logs(log_dir: Path) -> None:
    logs = sorted(
        log_dir.glob(f"{LOG_NAME_PREFIX}-*.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_log in logs[LOG_RETENTION_COUNT:]:
        try:
            old_log.unlink()
        except OSError:
            logging.getLogger(__name__).debug(
                "Could not remove old log file: %s", old_log, exc_info=True
            )


def _install_exception_hooks(logger: logging.Logger) -> None:
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        def handle_thread_exception(args):
            logger.critical(
                "Unhandled thread exception in %s",
                args.thread.name if args.thread else "unknown thread",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = handle_thread_exception


def _has_usable_console_stream() -> bool:
    """False when PyInstaller windowed builds leave sys.stderr/stdout as None,
    which would crash StreamHandler on every emit."""
    stream = sys.stderr or sys.stdout
    if stream is None:
        return False
    return hasattr(stream, "write")


def setup_logging(app_name: str = "EyeTrackApp") -> Path:
    global _current_log_path
    try:
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except Exception:
        pass

    log_dir = _app_root() / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{LOG_NAME_PREFIX}-{datetime.now():%Y%m%d-%H%M%S}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    if _has_usable_console_stream():
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ColorFormatter("[%(levelname)s] %(message)s"))
        root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
        )
    )

    root_logger.addHandler(file_handler)

    logging.captureWarnings(True)
    _install_exception_hooks(root_logger)
    _prune_old_logs(log_dir)

    # comtypes floods the log with dozens of DEBUG lines per DirectShow enumeration
    # (one line per COM interface Release). Cap it at WARNING so the log stays readable.
    logging.getLogger("comtypes").setLevel(logging.WARNING)

    _current_log_path = log_path
    logging.getLogger(__name__).info("%s logging to %s", app_name, log_path)
    return log_path


def current_log_path() -> Path | None:
    return _current_log_path


def log_directory() -> Path:
    log_dir = _app_root() / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def open_logs() -> None:
    """Reveal the current log in the OS file manager (or open the log
    directory on Linux, where xdg-open has no reveal-in-folder equivalent)."""
    log_dir = log_directory()
    current = current_log_path()

    if sys.platform.startswith("win"):
        try:
            if current is not None and current.exists():
                subprocess.Popen(
                    ["explorer", "/select,", str(current)], close_fds=True
                )
            else:
                os.startfile(str(log_dir))  # type: ignore[attr-defined]
            return
        except OSError:
            logging.getLogger(__name__).warning(
                "Failed to open log folder with Explorer", exc_info=True
            )

    if sys.platform == "darwin":
        try:
            if current is not None and current.exists():
                subprocess.Popen(["open", "-R", str(current)], close_fds=True)
            else:
                subprocess.Popen(["open", str(log_dir)], close_fds=True)
            return
        except OSError:
            logging.getLogger(__name__).warning(
                "Failed to open log folder with `open`", exc_info=True
            )

    try:
        subprocess.Popen(["xdg-open", str(log_dir)], close_fds=True)
    except OSError:
        logging.getLogger(__name__).warning(
            "Failed to open log folder with xdg-open", exc_info=True
        )
