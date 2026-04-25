import logging
import sys
import threading
from datetime import datetime
from pathlib import Path


LOG_DIR_NAME = "logs"
LOG_RETENTION_COUNT = 3
LOG_NAME_PREFIX = "eyetrackapp"


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


def setup_logging(app_name: str = "EyeTrackApp") -> Path:
    try:
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except ImportError:
        pass

    log_dir = _app_root() / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{LOG_NAME_PREFIX}-{datetime.now():%Y%m%d-%H%M%S}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColorFormatter("[%(levelname)s] %(message)s"))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
        )
    )

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.captureWarnings(True)
    _install_exception_hooks(root_logger)
    _prune_old_logs(log_dir)

    logging.getLogger(__name__).info("%s logging to %s", app_name, log_path)
    return log_path
