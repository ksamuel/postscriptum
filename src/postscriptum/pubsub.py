"""Postscriptum: an unified API to run code when Python exits

Postscriptum wraps ``atexit.register``, ``sys.excepthook`` and
``signal.signal`` to lets you do:

::

    from postscriptum import PubSub
    ps = PubSub() # do this before creating a thread or a process

    @ps.on_finish() # don't forget the parenthesis !
    def _(event):
        print("When the program finishes, no matter the reason.")

    @ps.on_terminate()
    def _(event):  # event contains the signal that lead to termination
        print("When the user terminates the program. E.G: Ctrl + C")

    @ps.on_crash()
    def _(event): # event contains the exception and traceback
        print("When there is an unhandled exception")

    ps.start()

All those functions will be called automatically at the proper moment.
The handler for ``on_finish`` will be called even if another handler
has been called.

If the same function is used for several events:

::

    @ps.on_finish()
    @ps.on_terminate()
    def t(event):
        print('woot!')

It will be called only once, on the earliest event.

If several functions are used as handlers for the same event:

::

    @ps.on_terminate()
    def _(event):
        print('one!')

    @ps.on_terminate()
    def _(event):
        print('two!')

The two functions will be called. Hooks from code not using postscriptum will
be preserved by default for exceptions and atexit.  Hooks from code not using
postscriptum for signals are replaced. They can be restored
using ps.restore_handlers().

You can also react to ``sys.exit()`` and manual raise of ``SystemExit``:

::

    @ps.on_quit()
    def _(event):  # event contains the exit code
        print('Why me ?')

BUT for this you MUST use the PubSub object as a decorator:

::

    @ps()
    def do_stuff():
        ...

    do_stuff()

Or as a context manager:

::

    with ps():
        do_stuff()

In that case, don't call ``ps.start()``, it is done for you.


All decorators are stackable. If you use other decorators than the ones
from postcriptum, put postcriptum decorators at the top:

::

    @ps.on_quit()
    @other_decorator()
    def handler(event):
        pass

Alternatively, you can add the handler imperatively:

::

    @other_decorator()
    def handler(event):
        pass

``ps.add_quit_handler(handler)``. All ``on_*`` method have their
imperative equivalent.

The event is a dictionary that can contain:

For ``on_crash`` handlers:

- **exception**: the value of the exception that lead to the crash
- **traceback**: the traceback at the moment of the crash
- **stacktrace**: a function to get the formatted stack trace as a string
- **previous_exception_handler**: the callable that was the exception handler
                                 before we called setup()


For ``on_terminate`` handlers:

- **signal**: the number representing the signal that was sent to terminate the program
- **signal_frame**: the frame state at the moment the signal arrived
- **previous_signal_handler**: the signal handler that was set before
  we called setup()
- **exit**: a callable you can use to manually trigger the exit.

For ``on_quit`` handlers:

- **exit_code**: the code passed to ``SystemExit``/``sys.exit``.
- **exit**: a callable you can use to manually trigger the exit.

For ``on_finish`` handlers:

- The contex is empty if the program ends cleanly, otherwise,
  it will contain the same entries as one of the events above.

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

from functools import partial

from typing import Set, Type, Callable
from types import TracebackType, FrameType

from postscriptum.types import (
    SignalHandlerType,
    ExceptionHandlerType,
    TerminateHandlerType,
    QuitHandlerType,
    CrashHandlerType,
    FinishHandlerType,
    HoldHandlerType,
    AlwaysHandlerType,
    EventHandlerType,
    EventType,
    EventTypeVar,
    TerminateEventType,
    CrashEventType,
    QuitEventType,
    OrderedSetType,
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
from postscriptum.exceptions import PubSubExit
from postscriptum.utils import create_handler_decorator, force_exit, format_stacktrace

PROCESS_TERMINATING_SIGNAL = ("SIGINT", "SIGQUIT", "SIGTERM", "SIGBREAK")

# TODO: check finish and hold are called correctly
# TODO: finish end 2 end tests
# TODO: test hold
# TODO: test alaways
# TODO: loop.add_signal_handler for asyncio,
#       see: https://gist.github.com/nvgoldin/30cea3c04ee0796ebd0489aa62bcf00a
# TODO: check if main thread
# TODO: test if one can call sys.exit() in a terminate handler
# TODO: test if on can reraise from a quit handler
# TODO: check if one can avoid exciting from an exception handler and then exit manually
# TODO: test with several handlers
# TODO: test if event is passed to finish
# TODO: improve error messages
# TODO: e2e on decorators
# TODO: test on azur cloud
# TODO: create an "examples" directory
# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio
# TODO: more doc
# TODO: write docstrings


class PubSub:
    """
        A Registry+Observer pattern for containing/attaching handlers
        to the various exit scenarios
    """

    def __init__(
        self,
        call_previous_exception_handler: bool = True,
        exit_on_terminate: bool = True,
        exit_after_quit_handlers: bool = True,
    ):

        self.exit_after_quit_handlers = exit_after_quit_handlers
        self.exit_on_terminate = exit_on_terminate
        self.call_previous_exception_handlers = call_previous_exception_handler

        # Called when terminate, crash or quit results in an exit
        self.finish_handlers = OrderedSetType[FinishHandlerType]()
        # Called on SIGINT (so Ctrl + C), SIGTERM, SIGQUIT and SIGBREAK
        self.terminate_handlers = OrderedSetType[TerminateHandlerType]()
        # Call when there is an unhandled exception
        self.crash_handlers = OrderedSetType[CrashHandlerType]()
        # Call on sys.exit and manual raise of SystemExit
        self.quit_handlers = OrderedSetType[QuitHandlerType]()
        # Always called
        self.always_handlers = OrderedSetType[AlwaysHandlerType]()
        # Called when the user chose to abort exit
        self.hold_handlers = OrderedSetType[HoldHandlerType]()

        # A set of already called handlers to avoid duplicate calls
        self._called_handlers: Set[EventHandlerType] = set()  # type: ignore
        # We use this to avoid registering handlers twice
        self._started = False

    @property
    def started(self) -> bool:
        """ Has start() been called already? Read only """
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

    def on_hold(self, func=None):
        return create_handler_decorator(func, self.hold_handlers.add, "on_hold")

    def always(self, func=None):
        return create_handler_decorator(func, self.always_handlers.add, "always")

    def start(self):

        if self.started:
            return

        self._called_handlers.clear()

        register_exception_handler(
            self._handle_crash,
            call_previous_handler=self.call_previous_exception_handlers,
        )
        register_signals_handler(self._handle_terminate, PROCESS_TERMINATING_SIGNAL)
        atexit.register(self._handle_finish)

        self._started = True

    def stop(self):

        if not self.started:
            return

        restore_previous_exception_handler()
        restore_previous_signals_handlers(PROCESS_TERMINATING_SIGNAL)
        atexit.unregister(self._handle_finish)

        self._started = False

    def _call_handlers(
        self,
        handlers: OrderedSetType[Callable[[EventTypeVar], None]],
        event: EventTypeVar,
    ):
        for handler in handlers:
            if handler not in self._called_handlers:
                self._called_handlers.add(handler)
                handler(event)

    def _handle_finish(self, event: EventType = None):
        self._call_handlers(self.finish_handlers, event or {})
        self._call_handlers(self.always_handlers, event or {})

    def _handle_hold(self, event: EventType = None):
        self._call_handlers(self.hold_handlers, event or {})
        self._call_handlers(self.always_handlers, event or {})
        self._called_handlers.clear()

    def _handle_crash(
        self,
        type_: Type[Exception],
        exception: Exception,
        traceback: TracebackType,
        previous_handler: ExceptionHandlerType,
    ):
        event: CrashEventType = {
            "exception": exception,
            "traceback": traceback,
            "previous_exception_handler": previous_handler,
            "stacktrace": partial(format_stacktrace, type_, exception, traceback),
        }

        self._call_handlers(self.crash_handlers, event)
        self._handle_finish(event)

    def _handle_terminate(
        self, sig: signal.Signals, frame: FrameType, previous_handler: SignalHandlerType
    ):
        recommended_exit_code = 128 + sig  # Most POSIX shell seem to do that
        event: TerminateEventType = {
            "signal": sig,
            "signal_frame": frame,
            "previous_signal_handler": previous_handler,
            "exit": lambda code=recommended_exit_code: force_exit(code),  # type: ignore
        }

        # TODO: check manual exit
        # TODO: check that a custom exit will trigger finish anyway

        # We need to temporarly restore original signal handlers so that
        # Ctrl + C works in an input() call inside a handler
        restore_previous_signals_handlers(PROCESS_TERMINATING_SIGNAL)
        registered_signals = None

        # In the simplest scenario, we can just call the handlers and
        # hook into signals again...
        try:
            self._call_handlers(self.terminate_handlers, event)
            registered_signals = register_signals_handler(
                self._handle_terminate, PROCESS_TERMINATING_SIGNAL
            )

        # But the DEV user may manually exit from inside his own handlers.
        # This should result in a definitive exit, so we call related handler
        # for THAT. Also, since they could receive a signal, we need
        # to hook into signals again.
        except PubSubExit:
            registered_signals = register_signals_handler(
                self._handle_terminate, PROCESS_TERMINATING_SIGNAL
            )
            self._handle_finish(event)
            raise

        # If the END user hits Ctrl + C during one of the DEV user handler,
        # the default signal handlers we just restored will give us a
        # KeyboardInterrupt.
        # Now we can pretend we were handling it all along by recursively
        # call self._handle_terminate(). To do so, again we hook back into
        # signals (since self._handle_terminate() will reverse that)
        # and clear the _called_handlers to allow exceptionnally calling
        # a handler twice.
        except KeyboardInterrupt:
            registered_signals = register_signals_handler(
                self._handle_terminate, PROCESS_TERMINATING_SIGNAL
            )
            self._called_handlers.clear()
            self._handle_terminate(sig, frame, previous_handler)

        # In case of an exception that is actually an error, we want
        # to be sure we are hooks into signals again, but not do it twice
        finally:
            if not registered_signals:
                register_signals_handler(
                    self._handle_terminate, PROCESS_TERMINATING_SIGNAL
                )

        # If were are here, no handler manually exited, and edge cases
        # are handled, so we can proceed normally
        if self.exit_on_terminate:
            self._handle_finish(event)
            force_exit(code=recommended_exit_code)
        else:
            self._handle_hold(event)

    # TODO: test reraise from there
    def _handle_quit(
        self, type_: Type[SystemExit], exception: SystemExit, traceback: TracebackType
    ):
        event: QuitEventType = {
            "exit_code": exception.code,
            "exit": lambda code=exception.code: force_exit(code),  # type: ignore
        }

        try:
            self._call_handlers(self.quit_handlers, event)
        except PubSubExit:  # Deal with a handler manually exiting
            self._handle_finish(event)
            raise

        # If we are here, this means no handler manually exited.
        # We rely on catch_system_exit to exit for us if needed.
        if self.exit_after_quit_handlers:
            self._handle_finish(event)
        else:
            self._handle_hold(event)

    def __call__(self) -> catch_system_exit:

        return catch_system_exit(
            on_system_exit=self._handle_quit,
            on_enter=self.start,
            raise_again=self.exit_after_quit_handlers,
        )
