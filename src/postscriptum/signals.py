"""Low level tooling to register handlers for excepthandler and signals
"""

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


def register_signals_handler(
    handler: Callable[[signal.Signals, FrameType, Optional[SignalHandlerType]], None],
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

        register_signals_handler(handler2, [Signals.SIGABRT])

    """

    @wraps(handler)
    def handler_wrapper(sig: signal.Signals, frame: FrameType):
        return handler(sig, frame, SIGNAL_HANDLERS_HISTORY[sig][-1])

    previous_handlers = {}
    for sig in signals_from_names(signals):
        previous_handler = signal.getsignal(sig)
        SIGNAL_HANDLERS_HISTORY.setdefault(sig, []).append(previous_handler)
        previous_handlers[sig] = previous_handler
        signal.signal(sig, handler_wrapper)

    return previous_handlers


def restore_previous_signals_handlers(
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

        # cleaning history from signals with no handlers
        if not previous_handlers:
            SIGNAL_HANDLERS_HISTORY.pop(sig)

    return replacing_handlers
