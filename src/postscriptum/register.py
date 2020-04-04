"""Low level tooling to register handlers for excepthandler and signals
"""

import sys
import signal

from typing import *
from typing import cast
from types import TracebackType, FrameType

from functools import wraps

from postscriptum.types import (
    SignalType,
    ExceptionHandlerType,
    SignalHandlerType,
    PostScripumExceptionHandlerType,
)


EXCEPTION_HANDLERS_HISTORY: List[ExceptionHandlerType] = []

SIGNAL_HANDLERS_HISTORY: Dict[signal.Signals, List[SignalHandlerType]] = {}


def signals_from_names(
    signal_names: Iterable[Union[str, signal.Signals]]
) -> Iterable[signal.Signals]:
    """ Yield Signals Enum values matching names if they are available

    This functions allows to get the signal.Signals enum value for
    the given signal names, filtering the results to get only the ones that
    are available on the current OS.

    This is used by register_signals_handler() and restore_signal_handlers()
    to be able to pass a list of signals no matter the plateform.

    Passing a signal.Signals among the string is a noop, the value
    will be yieled as-is.

    Args:
        signals_names: the names of signals to look up the Enum value for.

    Example:

        Calling:

            list(signals_from_names(('SIGABRT', 'SIGBREAK', 'SIGTERM')))

        Will result in:

            [<Signals.SIGABRT: 6>, <Signals.SIGBREAK: 21>]

        on Windows and on Unix:

            [<Signals.SIGABRT: 6>, <Signals.SIGTERM: 15>]

    """
    for sig in signal_names:
        if isinstance(sig, signal.Signals):
            yield sig
        else:
            sig = getattr(signal, sig, None)
            if sig:
                yield cast(signal.Signals, sig)


def register_exception_handler(
    handler: PostScripumExceptionHandlerType, call_previous_handler: bool = True
) -> ExceptionHandlerType:
    """ Set the callable to use when an exception is not handled

    The previous one is added in the PREVIOUS_EXCEPT_HOOKS stack.

    You probably don't want to use that manually. We use it to
    set the Watcher class handler.

    Use restore_exception_handler() to restore the exception handler to the previous
    one.

    Not thread safe. Do it before starting any thread, subprocess or event loop

    Args:

        handler: the callable to put into sys.excepthook. It will we wrapped in
                an adapter of type ExceptHookType
        call_previous_handler: should the adapter call the previous handler before
            yours ? Keep that to True unless you really know what you are doing.

    Example:

        def handler(type_, value, traceback, previous_except_handler):
            print("I'll be called on an exception before it crashes the VM")

        register_exception_handler(handler)

    """
    previous_except_handler = sys.excepthook
    EXCEPTION_HANDLERS_HISTORY.append(previous_except_handler)

    def handler_wrapper(
        type_: Type[BaseException], value: BaseException, traceback: TracebackType
    ):
        f""" Adapter created by register_exception_handler() to wrap {handler}()
            This is done so {handler}() can accept a forth param, the
            previous except handler, which is not passed other wise.

            You can get a reference on the {handler}() function by accessing
            handler_wrapper.__wrapped__
        """
        if call_previous_handler:
            previous_except_handler(type_, value, traceback)
        return handler(type_, value, traceback, previous_except_handler)

    handler_wrapper.__wrapped__ = handler  # type: ignore

    sys.excepthook = handler_wrapper
    return previous_except_handler


def restore_previous_exception_handler():
    """ Restore sys.excepthook to contain the previous handler

    Get the handlers by poping PREVIOUS_EXCEPT_HOOKS.

    Not thread safe. Do it after closing all threads, subprocesses
    or event loops

    Example:

        restore_exception_handler() # It's all automatic, nothing else to do

    """
    replacing_handler = sys.excepthook
    if not EXCEPTION_HANDLERS_HISTORY:
        raise IndexError("No previous except handler found to restore")
    handler = EXCEPTION_HANDLERS_HISTORY.pop()
    sys.excepthook = handler
    return replacing_handler


def register_signals_handler(
    handler: Callable[[signal.Signals, FrameType, Optional[SignalHandlerType]], bool],
    signals: Iterable[SignalType],
) -> Mapping[signal.Signals, SignalHandlerType]:
    """ Register a callable to run for when a set of system signals is received

    Not thread safe. Do it before starting any thread, subprocess or event loop

    Args:

        handler: the callable to attach. If the callable return True, don't exit
              no matter the signal. It will we wrapped in an adapter of
              type SignalHookType
        signals: a list of signal names to attach to.
                Use signals_from_names() to pass a list
                of signals that will be filtered depending of the OS.

    Example:

        def handler1(sig, frame, previous_handler):
            print("I'll be called when the program receive a signal")

        register_signals_handler(handler1)

        # This will replace the previous handler for SIGABRT:

        from signals import Signals

        def handler2(sig, frame, previous_handler):
            print("I'll be called when the code calls os.abort()")
            return True # keep running, don't exit

        register_signals_handler(handler2, [Signals.SIGABRT])

    """

    @wraps(handler)
    def handler_wrapper(sig: signal.Signals, frame: FrameType) -> bool:
        return handler(sig, frame, SIGNAL_HANDLERS_HISTORY[sig][-1])

    previous_handlers = {}
    for sig in signals_from_names(signals):
        previous_handler = signal.getsignal(sig)
        SIGNAL_HANDLERS_HISTORY.setdefault(sig, []).append(previous_handler)
        previous_handlers[sig] = previous_handler
        signal.signal(sig, handler_wrapper)

    return previous_handlers


def restore_signals_handlers(
    signals: Iterable[signal.Signals],
) -> Mapping[signal.Signals, SignalHandlerType]:
    """ Restore signals handlers to their previous values

    Args:
        signals: the names of the signal look for in PREVIOUS_SIGNAL_HOOKS
                 for handlers to restore

    Not thread safe. Do it after closing all threads, subprocesses
    or event loops.

    Example:

        restore_signal_handlers()

    """
    replacing_handlers = {}
    for sig in signals_from_names(signals):
        previous_handlers = SIGNAL_HANDLERS_HISTORY.get(sig, [])
        if not previous_handlers:
            raise IndexError(
                f"No previous handlers found for signal {signal} to restore"
            )

        replacing_handlers[sig] = previous_handlers.pop()
        signal.signal(sig, replacing_handlers[sig])

    return replacing_handlers
