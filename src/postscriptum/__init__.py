"""Postscriptum: an intuitive and unified API to run code when Python exit

Postscriptum wraps ``atexit.register``, ``sys.excepthook`` and ``signal.signal`` to lets you do:

::

    import postscriptum
    watch = postscriptum.setup() # do this before creating a thread or a process

    @watch.on_finish() # don't forget the parenthesis !
    def _(context):
        print("When the program finishes, no matter the reason.")

    @watch.on_terminate()
    def _(context):  # context contains the signal that lead to termination
        print("When the user terminates the program. E.G: Ctrl + C, kill -9, etc.")

    @watch.on_crash()
    def _(context): # context contains the exception and traceback
        print("When there is an unhandled exception")

All those functions will be called automatically at the proper moment. The handler for ``on_finish`` will be called even if another handler has been called.

If the same function is used for several events:

::

    @watch.on_finish()
    @watch.on_terminate()
    def t(context):
        print('woot!')

It will be called only once.

If several functions are used as handlers for the same event:

::

    @watch.on_terminate()
    def _(context):
        print('one!')

    @watch.on_terminate()
    def _(context):
        print('two!')

The two functions will be called. Hooks from code not using postscriptum will be preserved by default for exceptions and atexit.  Hooks from code not using postscriptum for signals are replaced. They can be restored using watch.restore_hooks().

You can also react to ``sys.exit()`` and manual raise of ``SystemExit``:

::

    @watch.on_quit()
    def _(context):  # context contains the exit code
        print('Why me ?')

BUT for this you MUST use the watcher as a decorator:

::

    @watch()
    def main():
        do_stuff()

    main()

Or as a context manager:

::

    with watch():
        do_stuff()


All decorators are stackable. If you use other decorators than the ones from postcriptum, put postcriptum decorators at the top:

::

    @watch.on_quit()
    @other_decorator()
    def handler(context):
        pass

Alternatively, you can add the handler imperatively:

::

    @other_decorator()
    def handler(context):
        pass

``watch.add_quit_handler(handler)``. All ``on_*`` method have their imperative equivalent.

The context is a dictionary that can contain:

For ``on_crash`` handlers:

- **exception_type**: the class of the exception that lead to the crash
- **exception_value**: the value of the exception that lead to the crash
- **exception_traceback**: the traceback at the moment of the crash
- **previous_exception_hook**: the callable that was the exception hook before we called setup()

For ``on_terminate`` handlers:

- **signal**: the number representing the signal that was sent to terminate the program
- **signal_frame**: the frame state at the moment the signal arrived
- **previous_signal_hook**: the signal handler that was set before we called setup()
- **recommended_exit_code**: the polite exit code to use when exiting after this signal

For ``on_quit`` handlers:

- **exit_code**: the code passed to ``SystemExit``/``sys.exit``.

For ``on_finish`` handlers:

- The contex is empty if the program ends cleanly, otherwise,
  it will contain the same entries as one of the contexts above.

Currently, postscriptum does not provide a hook for

- ``sys.unraisablehook``
- exception occuring in other threads (``threading.excepthook`` from 3.8 will allow us to do that later)
- unhandled exception errors in unawaited asyncio (not sure we should do something though)

.. warning::
    You must be very careful about the code you put in handlers. If you mess up in there,
    it may give you no error message!

    Test your function without being a hook, then hook it up.


"""

# TODO: test
# TODO: more doc
# TODO: provide testing infrastructure
# TODO: ensure the exit prevention workflow for all hooks
# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio ?

__version__ = "0.2"

import sys
import os
import time
import atexit
import signal

from functools import wraps
from contextlib import ContextDecorator

from typing import *

from postscriptum.register import (
    PROCESS_ENDING_SIGNALS,
    register_except_hook,
    restore_except_hook,
    register_signal_hook,
    restore_signal_hooks,
)
from postscriptum.exceptions import ExitFromSignal

# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio


class ExitWatcher:
    """
        A registry containing/attaching hooks to the various exit scenarios

    """

    def __init__(
        self,
        call_previous_exception_hook: bool = True,
        signals_to_catch: Iterable[str] = PROCESS_ENDING_SIGNALS,
        terminate_handlers: Iterable[Callable] = (),
        exit_handlers: Iterable[Callable] = (),
        finish_handlers: Iterable[Callable] = (),
        crash_handlers: Iterable[Callable] = (),
        quit_handlers: Iterable[Callable] = (),
    ):

        self.call_previous_exception_hook = call_previous_exception_hook
        self.signals_to_catch = signals_to_catch

        # Always called
        self._finish_handlers = list(finish_handlers)

        # Called on external signals and Ctrl + C
        self._terminate_handlers = list(terminate_handlers)

        # Call when there is an unhandled exception
        self._crash_handlers = list(crash_handlers)

        # Call on sys.exit and manual raise of SystemExit
        self._quit_handlers = list(quit_handlers)

        # A set of already called handlers to avoid
        # duplicate calls
        self._called_handlers: Set[Callable] = set()

        # We use this to avoid registering hooks twice
        self._hooks_registered = False

    def _create_handler_decorator(self, func, handlers: list, name: str):
        if func is not None:
            raise ValueError(
                f"{name} must be called before being used as a decorator. Add parenthesis: {name}()"
            )

        def decorator(func):
            if func not in handlers:
                handlers.append(func)
            return func

        return decorator

    def add_quit_handler(self, func):
        self._quit_handlers.append(func)

    def add_finish_handler(self, func):
        self._finish_handlers.append(func)

    def add_terminate_handler(self, func):
        self._terminate_handlers.append(func)

    def add_crash_handler(self, func):
        self._crash_handlers.append(func)

    def on_quit(self, func=None):
        return self._create_handler_decorator(func, self._quit_handlers, "on_quit")

    def on_finish(self, func=None):
        return self._create_handler_decorator(func, self._finish_handlers, "on_finish")

    def on_terminate(self, func=None):
        return self._create_handler_decorator(
            func, self._terminate_handlers, "on_terminate"
        )

    def on_crash(self, func=None):
        return self._create_handler_decorator(func, self._crash_handlers, "on_crash")

    def register_hooks(self):

        if self._hooks_registered:
            self.restore_hooks()
            raise RuntimeError(
                "Hooks already registered, call restore_hooks() before calling register_hooks() again."
            )
        register_except_hook(
            self._except_hook, call_previous_hook=self.call_previous_exception_hook
        )
        register_signal_hook(self._signal_hook, signals=self.signals_to_catch)
        atexit.register(self._call_finish_handlers)

        self._hooks_registered = True

    def restore_hooks(self):
        restore_except_hook()
        restore_signal_hooks()
        atexit.unregister(self._call_finish_handlers)
        self._hooks_registered = False

    def _call_handler(self, handler: Callable, context: dict):
        if handler not in self._called_handlers:
            self._called_handlers.add(handler)
            return handler(context)
        return None

    def _call_finish_handlers(self, context: dict = None):
        for handler in self._finish_handlers:
            self._call_handler(handler, context or {})

    def _except_hook(
        self, type: Type[Exception], value: Exception, traceback, old_hook: Callable
    ):
        context = {}
        context["exception_type"] = type
        context["exception_value"] = value
        context["exception_traceback"] = traceback
        context["previous_exception_hook"] = old_hook

        for handler in self._crash_handlers:
            self._call_handler(handler, context)

        self._call_finish_handlers(context)

    def _signal_hook(self, code, frame, previous_hook):
        recommended_exit_code = 128 + code
        context = {}
        context["signal"] = code
        context["signal_frame"] = frame
        context["previous_signal_hook"] = previous_hook
        context["recommended_exit_code"] = recommended_exit_code

        exit = True
        for handler in self._terminate_handlers:
            exit &= not self._call_handler(handler, context)

        self._call_finish_handlers(context)

        if exit:
            raise ExitFromSignal(recommended_exit_code)

    def _call_quit_handlers(self, exception: SystemExit):
        context = {}
        context["exit_code"] = exception.code
        exit = True
        for handler in self._quit_handlers:
            exit &= not self._call_handler(handler, context)
        self._call_finish_handlers(context)
        return exit

    def __call__(self, func=None):
        """ Return an object that can be used to catch SystemExit

            The object can be used both as a context manager and a decorator.
        """

        if func is not None:
            raise ValueError(
                f"This object must be called before being used as a "
                "decorator: add parenthesis. E.G: if you have this object in "
                "a variabled 'watch', do @watch() and not @watch."
            )

        class Decorator(ContextDecorator):
            def __enter__(s):
                pass

            def __exit__(s, exception_type, exception_value, traceback):
                received_signal = isinstance(exception_value, ExitFromSignal)
                received_quit = isinstance(exception_value, SystemExit)
                if received_quit and not received_signal:
                    return not self._call_quit_handlers(exception_value)

        return Decorator()


def setup(*args, **kwargs):
    hook = ExitWatcher(*args, **kwargs)
    hook.register_hooks()
    return hook
