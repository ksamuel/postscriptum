"""Postscriptum: an unified API to run code when Python exits

Postscriptum wraps ``atexit.register``, ``sys.excepthook`` and
``signal.signal`` to lets you do:

::

    from postscriptum import EventWatcher
    watch = EventWatcher() # do this before creating a thread or a process

    @watch.on_finish() # don't forget the parenthesis !
    def _(context):
        print("When the program finishes, no matter the reason.")

    @watch.on_terminate()
    def _(context):  # context contains the signal that lead to termination
        print("When the user terminates the program. E.G: Ctrl + C")

    @watch.on_crash()
    def _(context): # context contains the exception and traceback
        print("When there is an unhandled exception")

    watch.start()

All those functions will be called automatically at the proper moment.
The handler for ``on_finish`` will be called even if another handler
has been called.

If the same function is used for several events:

::

    @watch.on_finish()
    @watch.on_terminate()
    def t(context):
        print('woot!')

It will be called only once, on the earliest event.

If several functions are used as handlers for the same event:

::

    @watch.on_terminate()
    def _(context):
        print('one!')

    @watch.on_terminate()
    def _(context):
        print('two!')

The two functions will be called. Hooks from code not using postscriptum will
be preserved by default for exceptions and atexit.  Hooks from code not using
postscriptum for signals are replaced. They can be restored
using watch.restore_handlers().

You can also react to ``sys.exit()`` and manual raise of ``SystemExit``:

::

    @watch.on_quit()
    def _(context):  # context contains the exit code
        print('Why me ?')

BUT for this you MUST use the watcher as a decorator:

::

    @watch()
    def do_stuff():
        ...

    do_stuff()

Or as a context manager:

::

    with watch():
        do_stuff()

In that case, don't call ``watch.start()``, it is done for you.


All decorators are stackable. If you use other decorators than the ones
from postcriptum, put postcriptum decorators at the top:

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

``watch.add_quit_handler(handler)``. All ``on_*`` method have their
imperative equivalent.

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
- **previous_signal_handler**: the signal handler that was set before
  we called setup()
- **recommended_exit_code**: the polite exit code to use when exiting
  after this signal

For ``on_quit`` handlers:

- **exit_code**: the code passed to ``SystemExit``/``sys.exit``.

For ``on_finish`` handlers:

- The contex is empty if the program ends cleanly, otherwise,
  it will contain the same entries as one of the contexts above.

Currently, postscriptum does not provide hooks for

- ``sys.unraisablehook``
- exception occuring in other threads (``threading.excepthook`` from 3.8
  will allow us to do that later)
- unhandled exception errors in unawaited asyncio (not sure we should do
  something though)

.. warning::
    You must be very careful about the code you put in handlers. If you mess
    up in there, it may give you no error message!

    Test your function without being a handler, then hook it up.

"""

import atexit
import signal

from functools import wraps

from typing import Set, Type
from types import TracebackType, FrameType

from ordered_set import OrderedSet

from postscriptum.types import (
    SignalHandlerType,
    ExceptionHandlerType,
    TerminateHandlerType,
    QuitHandlerType,
    CrashHandlerType,
    FinishHandlerType,
    EventWatcherHandlerType,
    TerminateHandlerContextType,
    CrashHandlerContextType,
    QuitHandlerContextType,
    EventWatcherHandlerContextType,
)

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
from postscriptum.utils import create_handler_decorator

PROCESS_TERMINATING_SIGNAL = ("SIGINT", "SIGQUIT", "SIGTERM", "SIGBREAK")

# TODO: test if one can call sys.exit() in a terminate handler
# TODO: test if on can reraise from a quit handler
# TODO: check if one can avoid exciting from an exception handler and then exit manually
# TODO: test with several handlers
# TODO: test if context is passed to finish
# TODO: improve error messages
# TODO: e2e on decorators
# TODO: test on azur cloud
# TODO: create an "examples" directory
# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio
# TODO: more doc
# TODO: write docstrings


class EventWatcher:
    """
        A registry containing/attaching handlers to the various exit scenarios

    """

    # TODO: rename hold_exit_on_quit
    # TODO: rename hold_exit_on_crash
    # TODO: rename hold_exit_on_terminate
    def __init__(
        self,
        call_previous_exception_handler: bool = True,
        exit_after_terminate_handlers: bool = True,
        raise_again_after_quit_handlers: bool = True,
    ):

        self.raise_again_after_quit_handlers = raise_again_after_quit_handlers
        self.exit_after_terminate_handlers = exit_after_terminate_handlers
        self.call_previous_exception_handlers = call_previous_exception_handler

        # Always called
        self.finish_handlers: OrderedSet[FinishHandlerType] = OrderedSet()

        # Called on SIGINT (so Ctrl + C), SIGTERM, SIGQUIT and SIGBREAK
        self.terminate_handlers: OrderedSet[TerminateHandlerType] = OrderedSet()

        # Call when there is an unhandled exception
        self.crash_handlers: OrderedSet[CrashHandlerType] = OrderedSet()

        # Call on sys.exit and manual raise of SystemExit
        self.quit_handlers: OrderedSet[QuitHandlerType] = OrderedSet()

        # A set of already called handlers to avoid
        # duplicate calls
        self._called_handlers: Set[EventWatcherHandlerType] = set()

        # We use this to avoid registering handlers twice
        self._started = False

    @property
    def started(self) -> bool:
        """ Make the public property read only """
        return self._started

    def on_terminate(self, func=None):
        return create_handler_decorator(
            func, self.terminate_handlers.add, "on_terminate"
        )

    def on_quit(self, func=None):
        return create_handler_decorator(func, self.quit_handlers.add, "on_quit")

    def on_finish(self, func=None):
        return create_handler_decorator(func, self.finish_handlers.add, "on_finish")

    def on_crash(self, func=None):
        return create_handler_decorator(func, self.crash_handlers.add, "on_crash")

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

    def stop(self):

        restore_previous_exception_handler()
        restore_previous_signals_handlers(PROCESS_TERMINATING_SIGNAL)

        atexit.unregister(self._call_finish_handlers)

        self._started = False

    def _call_handler(
        self, handler: EventWatcherHandlerType, context: EventWatcherHandlerContextType
    ):
        if handler not in self._called_handlers:
            self._called_handlers.add(handler)
            return handler(context)  # type: ignore
        return None

    def _call_finish_handlers(self, context: EventWatcherHandlerContextType = None):
        for handler in self.finish_handlers:
            self._call_handler(handler, context or {})
        self._called_handlers = set()

    def _call_crash_handlers(
        self,
        type_: Type[Exception],
        exception: Exception,
        traceback: TracebackType,
        previous_handler: ExceptionHandlerType,
    ):
        context: CrashHandlerContextType = {
            "exception_type": type_,
            "exception_value": exception,
            "exception_traceback": traceback,
            "previous_exception_handler": previous_handler,
        }

        for handler in self.crash_handlers:
            self._call_handler(handler, context)

        self._call_finish_handlers(context)

        if not self.raise_again_after_quit_handlers:
            self._called_handlers = set()

    def _call_terminate_handlers(
        self, sig: signal.Signals, frame: FrameType, previous_handler: SignalHandlerType
    ):
        recommended_exit_code = 128 + sig
        context: TerminateHandlerContextType = {
            "signal": sig,
            "signal_frame": frame,
            "previous_signal_handler": previous_handler,
            "recommended_exit_code": recommended_exit_code,
        }

        for handler in self.terminate_handlers:
            self._call_handler(handler, context)

        # TODO: check manual exit
        # TODO: check that a custom exit will trigger finish anyway
        if self.exit_after_terminate_handlers:
            self._call_finish_handlers(context)
            raise ExitFromSignal(recommended_exit_code)

        self._called_handlers = set()

    # TODO: test reraise from there
    def _call_quit_handlers(
        self, type_: Type[SystemExit], exception: SystemExit, traceback: TracebackType
    ):
        context: QuitHandlerContextType = {"exit_code": exception.code}

        for handler in self.quit_handlers:
            self._call_handler(handler, context)
        self._call_finish_handlers(context)

    def __call__(self) -> catch_system_exit:
        def enter_handler(*args, **kwargs):
            if not self.started:
                self.start()

        return catch_system_exit(
            on_system_exit=self._call_quit_handlers,
            on_enter=self.start,
            raise_again=self.raise_again_after_quit_handlers,
        )
