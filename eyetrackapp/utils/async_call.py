"""Run a function on its own thread and wait for or collect its result.

Copyright (c) 2026 EyeTrackVR <3
LICENSE: Babble Software Distribution License 1.0
"""

import threading


class AsyncCallTimeout(RuntimeError):
    pass


class AsyncCall(object):
    def __init__(self, fnc, callback=None):
        self.callable = fnc
        self.callback = callback

    def __call__(self, *args, **kwargs):
        self.thread = threading.Thread(target=self.run, name=self.callable.__name__, args=args, kwargs=kwargs)
        self.thread.start()
        return self

    def wait(self, timeout=None):
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise AsyncCallTimeout()
        else:
            return self.result

    def run(self, *args, **kwargs):
        self.result = self.callable(*args, **kwargs)
        if self.callback:
            self.callback(self.result)


class AsyncMethod(object):
    def __init__(self, fnc, callback=None):
        self.callable = fnc
        self.callback = callback

    def __call__(self, *args, **kwargs):
        return AsyncCall(self.callable, self.callback)(*args, **kwargs)


def Async(fnc=None, callback=None):
    if fnc is None:

        def add_async_callback(fnc):
            return AsyncMethod(fnc, callback)

        return add_async_callback
    else:
        return AsyncMethod(fnc, callback)
