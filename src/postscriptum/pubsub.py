"""Postscriptum: an unified API to run code when Python exits

Postscriptum wraps ``atexit.register``, ``sys.excepthook`` and
``signal.signal`` to lets you do:

::

    from postscriptum import PubSub
    ps = PubSub() # do this before creating a thread or a process

    @ps.on_finish() # don't forget the parenthesis !
    def _(context):
        print("When the program finishes, no matter the reason.")

    @ps.on_terminate()
    def _(context):  # context contains the signal that lead to termination
        print("When the user terminates the program. E.G: Ctrl + C")

    @ps.on_crash()
    def _(context): # context contains the exception and traceback
        print("When there is an unhandled exception")

    ps.start()

All those functions will be called automatically at the proper moment.
The handler for ``on_finish`` will be called even if another handler
has been called.

If the same function is used for several events:

::

    @ps.on_finish()
    @ps.on_terminate()
    def t(context):
        print('woot!')

It will be called only once, on the earliest event.

If several functions are used as handlers for the same event:

::

    @ps.on_terminate()
    def _(context):
        print('one!')

    @ps.on_terminate()
    def _(context):
        print('two!')

The two functions will be called. Hooks from code not using postscriptum will
be preserved by default for exceptions and atexit.  Hooks from code not using
postscriptum for signals are replaced. They can be restored
using ps.restore_handlers().

You can also react to ``sys.exit()`` and manual raise of ``SystemExit``:

::

    @ps.on_quit()
    def _(context):  # context contains the exit code
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
    def handler(context):
        pass

Alternatively, you can add the handler imperatively:

::

    @other_decorator()
    def handler(context):
        pass

``ps.add_quit_handler(handler)``. All ``on_*`` method have their
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

from functools import partial

from typing import Set, Type, Callable
from types import TracebackType, FrameType

from typing_extensions import NoReturn

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
    EventContextType,
    EventContextTypeVar,
    TerminateContextType,
    CrashContextType,
    QuitContextType,
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
from postscriptum.utils import create_handler_decorator

PROCESS_TERMINATING_SIGNAL = ("SIGINT", "SIGQUIT", "SIGTERM", "SIGBREAK")


# TODO: finish end 2 end tests
# TODO: test hold
# TODO: test alaways
# TODO: change context to be classes
# TODO: loop.add_signal_handler for asyncio, see: https://gist.github.com/nvgoldin/30cea3c04ee0796ebd0489aa62bcf00a
# TODO: check if main thread
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


class PubSub:
    """
        A Registry+Observer pattern for containing/attaching handlers
        to the various exit scenarios
    """

    def __init__(
        self,
        call_previous_exception_handler: bool = True,
        exit_after_terminate_handlers: bool = True,
        exit_after_quit_handlers: bool = True,
    ):

        self.exit_after_quit_handlers = exit_after_quit_handlers
        self.exit_after_terminate_handlers = exit_after_terminate_handlers
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

        self.reset()

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

    def reset(self):
        self._called_handlers = set()

    @staticmethod
    def force_exit(exit_code) -> NoReturn:
        raise PubSubExit(exit_code)

    def _call_handlers(
        self,
        handlers: OrderedSetType[Callable[[EventContextTypeVar], None]],
        context: EventContextTypeVar,
    ):
        for handler in handlers:
            if handler not in self._called_handlers:
                self._called_handlers.add(handler)
                handler(context)

    def _handle_finish(self, context: EventContextType = None):
        self._call_handlers(self.finish_handlers, context or {})
        self._call_handlers(self.always_handlers, context or {})

    def _handle_hold(self, context: EventContextType = None):
        self._call_handlers(self.hold_handlers, context or {})
        self._call_handlers(self.always_handlers, context or {})
        self.reset()

    def _handle_crash(
        self,
        type_: Type[Exception],
        exception: Exception,
        traceback: TracebackType,
        previous_handler: ExceptionHandlerType,
    ):
        context: CrashContextType = {
            "exception_type": type_,
            "exception_value": exception,
            "exception_traceback": traceback,
            "previous_exception_handler": previous_handler,
        }

        self._call_handlers(self.crash_handlers, context)
        self._handle_finish(context)

    def _handle_terminate(
        self, sig: signal.Signals, frame: FrameType, previous_handler: SignalHandlerType
    ):
        recommended_exit_code = 128 + sig
        context: TerminateContextType = {
            "signal": sig,
            "signal_frame": frame,
            "previous_signal_handler": previous_handler,
            "exit": partial(self.force_exit, exit_code=recommended_exit_code),
        }

        # TODO: check manual exit
        # TODO: check that a custom exit will trigger finish anyway

        try:
            self._call_handlers(self.terminate_handlers, context)
        except PubSubExit:
            self._handle_finish(context)
            raise

        # If we are here, this means no handler called exit(),
        if self.exit_after_terminate_handlers:
            self._handle_finish(context)
            self.force_exit(recommended_exit_code)
        else:
            self._handle_hold(context)

    # TODO: test reraise from there
    def _handle_quit(
        self, type_: Type[SystemExit], exception: SystemExit, traceback: TracebackType
    ):
        context: QuitContextType = {
            "exit_code": exception.code,
            "exit": partial(self.force_exit, exit_code=exception.code),
        }

        try:
            self._call_handlers(self.quit_handlers, context)
        except PubSubExit:
            self._handle_finish(context)
            raise

        # If we are here, this means no handler called exit(),
        if self.exit_after_quit_handlers:
            self._handle_finish(context)
        else:
            self._handle_hold(context)

    def __call__(self) -> catch_system_exit:

        return catch_system_exit(
            on_system_exit=self._handle_quit,
            on_enter=self.start,
            raise_again=self.exit_after_quit_handlers,
        )
