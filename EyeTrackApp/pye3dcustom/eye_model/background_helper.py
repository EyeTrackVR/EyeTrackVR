"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2020 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""

import logging
import multiprocessing as mp
import queue
import signal
import time
from ctypes import c_bool
from logging import Handler
from logging.handlers import QueueHandler, QueueListener
import traceback
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)
WorkerSetupResult = TypeVar("WorkerSetupResult")
WorkerFunctionResult = TypeVar("WorkerFunctionResult")


class BackgroundProcess:
    class StoppedError(Exception):
        """Interaction with a BackgroundProcess that was stopped."""

    class NothingToReceiveError(Exception):
        """Trying to receive data from BackgroundProcess without sending input first."""

    class MultipleSendError(Exception):
        """Trying to send data without first receiving previous output."""

    def __init__(
        self,
        setup: Callable[..., WorkerSetupResult],
        function: Callable[[WorkerSetupResult], WorkerFunctionResult],
        cleanup: Callable[[WorkerSetupResult], None],
        setup_args: Optional[Tuple] = None,
        setup_kwargs: Optional[Dict] = None,
        log_handlers: Iterable[Handler] = (),
    ):
        self._running = True

        self._task_queue = mp.Queue(maxsize=500)  # TODO: figure out good value

        logging_queue = mp.Queue()
        self._log_listener = QueueListener(logging_queue, *log_handlers)
        self._log_listener.start()

        self._should_terminate_flag = mp.Value(c_bool, 0)

        self._process = mp.Process(
            name="Pye3D Background Process",
            daemon=True,
            target=BackgroundProcess._worker,
            kwargs=dict(
                setup=setup,
                function=function,
                cleanup=cleanup,
                task_queue=self._task_queue,
                should_terminate_flag=self._should_terminate_flag,
                logging_queue=logging_queue,
                setup_args=setup_args if setup_args else (),
                setup_kwargs=setup_kwargs if setup_kwargs else {},
            ),
        )
        self._process.start()

    @property
    def running(self) -> bool:
        """Whether background task is running (not necessarily doing work)."""
        return self._running and self._process.is_alive()

    def send(self, *args: Tuple[Any], **kwargs: Dict[Any, Any]):
        """Send data to background process for processing.
        Raises StoppedError when called on a stopped process.
        """

        if not self.running:
            logger.error("Background process was closed previously!")
            raise BackgroundProcess.StoppedError()

        try:
            self._task_queue.put_nowait({"args": args, "kwargs": kwargs})
        except queue.Full:
            logger.debug(f"Dropping task! args: {args}, kwargs: {kwargs}")

    def cancel(self, timeout=-1):
        """Stop process as soon as current task is finished."""

        self._should_terminate_flag.value = 1
        if self.running:
            self._task_queue.close()
            self._task_queue.cancel_join_thread()
            self._task_queue.join_thread()
            self._process.join(timeout)
        self._running = False
        self._log_listener.stop()

    @staticmethod
    def _install_sigint_interception():
        def interrupt_handler(sig, frame):
            import traceback

            trace = traceback.format_stack(f=frame)
            logger.debug(f"Caught (and dropping) signal {sig} in:\n" + "".join(trace))

        signal.signal(signal.SIGINT, interrupt_handler)

    @staticmethod
    def _worker(
        setup: Callable[..., WorkerSetupResult],
        function: Callable[[WorkerSetupResult], Any],
        cleanup: Callable[[WorkerSetupResult], None],
        task_queue: mp.Queue,
        should_terminate_flag: mp.Value,
        logging_queue: mp.Queue,
        setup_args: Tuple,
        setup_kwargs: Dict,
    ):
        log_queue_handler = QueueHandler(logging_queue)
        logger = logging.getLogger()
        logger.setLevel(logging.NOTSET)
        logger.addHandler(log_queue_handler)

        # Intercept SIGINT (ctrl-c), do required cleanup in foreground process!
        BackgroundProcess._install_sigint_interception()

        setup_result: WorkerSetupResult = setup(*setup_args, **setup_kwargs)

        while not should_terminate_flag.value:
            try:
                params = task_queue.get(block=True, timeout=0.1)
                args = params["args"]
                kwargs = params["kwargs"]
            except queue.Empty:
                continue
            # except EOFError:
            #     logger.info("Pipe was closed from foreground process .")
            #     break

            try:
                t0 = time.perf_counter()
                function(setup_result, *args, **kwargs)
                t1 = time.perf_counter()
                # logger.debug(f"Finished background calculation in {(t1 - t0):.2}s")
            except Exception as e:
                logger.error(
                    f"Error executing background process with parameters {params}:\n{e}"
                )
                logger.debug(traceback.format_exc())
                break
        else:
            logger.info("Background process received termination signal.")

        cleanup(setup_result)

        logger.info("Stopping background process.")
        logger.removeHandler(log_queue_handler)
