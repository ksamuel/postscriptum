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

The two functions will be called. Hooks from code not using postscriptum will be preserved by default for exceptions and atexit.  Hooks from code not using postscriptum for signals are replaced. They can be restored using watch.restore_handlers().

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
- **previous_exception_handler**: the callable that was the exception handler
                                 before we called setup()

For ``on_terminate`` handlers:

- **signal**: the number representing the signal that was sent to terminate the program
- **signal_frame**: the frame state at the moment the signal arrived
- **previous_signal_handler**: the signal handler that was set before we called setup()
- **recommended_exit_code**: the polite exit code to use when exiting after this signal

For ``on_quit`` handlers:

- **exit_code**: the code passed to ``SystemExit``/``sys.exit``.

For ``on_finish`` handlers:

- The contex is empty if the program ends cleanly, otherwise,
  it will contain the same entries as one of the contexts above.

Currently, postscriptum does not provide hooks for

- ``sys.unraisablehook``
- exception occuring in other threads (``threading.excepthook`` from 3.8 will allow us to do that later)
- unhandled exception errors in unawaited asyncio (not sure we should do something though)

.. warning::
    You must be very careful about the code you put in handlers. If you mess up in there,
    it may give you no error message!

    Test your function without being a handler, then hook it up.

"""

# TODO: test
# TODO: more doc
# TODO: remove handlers
# TODO: provide testing infrastructure
# TODO: ensure the exit prevention workflow for all hooks
# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio ?


import sys
import os
import time
import atexit
import signal

from functools import wraps
from contextlib import ContextDecorator

from typing import *
from typing import Callable, Iterable  # * does't include those
from types import TracebackType

from ordered_set import OrderedSet

from postscriptum.types import SignalType, EventWatcherHandlerType
from postscriptum.system_exit import catch_system_exit
from postscriptum.excepthook import (
    register_exception_handler,
    restore_previous_exception_handler,
)
from postscriptum.signals import (
    register_signals_handler,
    restore_previous_signals_handlers,
)
from postscriptum.exceptions import ExitFromSignal

PROCESS_TERMINATING_SIGNAL = ("SIGINT", "SIGQUIT", "SIGTERM", "SIGBREAK")


# TODO: e2e on decorators
# TODO: deal on_terminate should offer (exit=true)
# TODO: add on_signals
# TODO: tests __init__
# TODO: turn terminate handler into on
# TODO: coveragage
# TODO: setup tox to test python 3.6, 7, 8, pypy3.6
# TODO: test on azur cloud
# TODO: check we can do the ctrl + c confirm
# TODO: create an "examples" directory
# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio


class EventWatcher:
    """
        A registry containing/attaching handlers to the various exit scenarios

    """

    def __init__(
        self,
        call_previous_exception_handler: bool = True,
        exit_after_terminate_handlers: bool = True,
    ):

        self.exit_after_terminate_handlers = exit_after_terminate_handlers
        self.call_previous_exception_handlers = call_previous_exception_handler

        # Always called
        self.finish_handlers: OrderedSet[EventWatcherHandlerType] = OrderedSet()

        # Called on SIGINT (so Ctrl + C), SIGTERM, SIGQUIT and SIGBREAK
        self.terminate_handlers: OrderedSet[EventWatcherHandlerType] = OrderedSet()

        # Call when there is an unhandled exception
        self.crash_handlers: OrderedSet[EventWatcherHandlerType] = OrderedSet()

        # Call on sys.exit and manual raise of SystemExit
        self.quit_handlers: OrderedSet[EventWatcherHandlerType] = OrderedSet()

        # A set of already called handlers to avoid
        # duplicate calls
        self._called_handlers: OrderedSet[EventWatcherHandlerType] = OrderedSet()

        # We use this to avoid registering handlers twice
        self._started = False

    @property
    def started(self) -> bool:
        """ Make the public property read only """
        return self._started

    def on_terminate(self, func=None):
        return self._create_handler_decorator(
            func, self.terminate_handlers.add, "on_terminate"
        )

    def on_quit(self, func=None):
        return self._create_handler_decorator(func, self.quit_handlers.add, "on_quit")

    def on_finish(self, func=None):
        return self._create_handler_decorator(
            func, self.finish_handlers.add, "on_finish"
        )

    def on_crash(self, func=None):
        return self._create_handler_decorator(func, self.crash_handlers.add, "on_crash")

    def start(self):

        if self.started:
            self.stop()
            raise RuntimeError(
                "Event handlers are already registered, call stop() before "
                "calling start() again."
            )

        self._called_handlers = set()

        register_exception_handler(
            self._call_crash_handlers,
            call_previous_handler=self.call_previous_exception_handlers,
        )

        register_signals_handler(
            self._call_terminate_handlers, PROCESS_TERMINATING_SIGNAL
        )

        atexit.register(self._call_finish_handlers)

        self._started = True

    def stop(self,):

        restore_previous_exception_handler()
        restore_previous_signals_handlers(PROCESS_TERMINATING_SIGNAL)

        atexit.unregister(self._call_finish_handlers)

        self._started = False

    def _create_handler_decorator(self, func, add_handler: Callable, name: str):
        """ Utility method to create the on_* decorators for each type of event
        """
        if func is not None:
            raise ValueError(
                f"{name} must be called before being used as a decorator. Add parenthesis: {name}()"
            )

        def decorator(func):
            self.add_handler(func)
            return func

        return decorator

    def _call_handler(self, handler: EventWatcherHandlerType, context: dict):
        if handler not in self._called_handlers:
            self._called_handlers.add(handler)
            return handler(context)
        return None

    def _call_finish_handlers(self, context: dict = None):
        for handler in self.finish_handlers:
            self._call_handler(handler, context or {})
        self._called_handlers = set()

    def _call_crash_handlers(
        self,
        type: Type[Exception],
        value: Exception,
        traceback,
        previous_handler: Callable,
    ):
        context: Dict[str, Any] = {}
        context["exception_type"] = type
        context["exception_value"] = value
        context["exception_traceback"] = traceback
        context["previous_exception_handler"] = previous_handler

        for handler in self.crash_handlers:
            self._call_handler(handler, context)

        self._call_finish_handlers(context)

    def _call_terminate_handlers(self, sig, frame, previous_handler):
        recommended_exit_code = 128 + sig
        context = {}
        context["signal"] = sig
        context["signal_frame"] = frame
        context["previous_signal_handler"] = previous_handler
        context["recommended_exit_code"] = recommended_exit_code

        for handler in self.terminate_handlers:
            self._call_handler(handler, context)

        # TODO: check that a custom exit will trigger finish anyway
        if self.exit_after_terminate_handlers:
            self._call_finish_handlers(context)
            raise ExitFromSignal(recommended_exit_code)

        self._called_handlers = set()

    def _call_quit_handlers(
        self, type_: Type[SystemExit], exception: SystemExit, traceback: TracebackType
    ):
        context = {}
        context["exit_code"] = exception.code
        exit = True
        for handler in self.quit_handlers:
            exit &= not self._call_handler(handler, context)
        self._call_finish_handlers(context)
        return exit

    def __call__(self) -> catch_system_exit:

        return catch_system_exit(
            self._call_quit_handlers, self.start, lambda *args, **kwargs: self.stop()
        )
