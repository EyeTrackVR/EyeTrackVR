import threading


def debounce(wait_seconds):
    def decorator(function):
        def _debounce(*args, **kwargs):
            def call_function():
                _debounce._timer = None
                return function(*args, **kwargs)

            if _debounce.timer is not None:
                _debounce.timer.cancel()

            # we reset the timer for each call, no matter the arguments
            _debounce.timer = threading.Timer(wait_seconds, call_function)
            _debounce.timer.start()

        _debounce.timer = None
        return _debounce

    return decorator
