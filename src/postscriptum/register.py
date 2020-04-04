"""Low level tooling to register handlers for excepthook and signals
"""

import sys
import signal

from typing import *
from typing import cast
from types import TracebackType, FrameType
from postscriptum.types import (
    SignalType,
    ExceptHookType,
    SignalHandlerType,
    PostScripumExceptHookType,
)

from functools import wraps


def signals_from_names(
    signal_names: Iterable[Union[str, signal.Signals]]
) -> Iterable[signal.Signals]:
    """ Yields Signals Enum values matching names if they are available

    This functions allows to get the signal.Signals enum value for
    the given signal names, filtering the results to get only the ones that
    are available on the current OS.

    This is used by register_signal_hook() and restore_signal_hook()
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


EXCEPT_HOOKS_HISTORY: List[ExceptHookType] = []
PREVIOUS_SIGNAL_HOOKS: Dict[signal.Signals, List[SignalHandlerType]] = {}


def register_except_hook(
    hook: PostScripumExceptHookType, call_previous_hook: bool = True
) -> ExceptHookType:
    """ Set the callable to use when an exception is not handled

    The previous one is added in the PREVIOUS_EXCEPT_HOOKS stack.

    You probably don't want to use that manually. We use it to
    set the Watcher class hook.

    Use restore_except_hook() to restore the excepthook to the previous
    one.

    Not thread safe. Do it before starting any thread, subprocess or event loop

    Args:

        hook: the callable to put into sys.excepthook. It will we wrapped in
                an adapter of type ExceptHookType
        call_previous_hook: should the adapter call the previous hook before
            yours ? Keep that to True unless you really know what you are doing.

    Example:

        def hook(type_, value, traceback, previous_except_hook):
            print("I'll be called on an exception before it crashes the VM")

        register_except_hook(hook)

    """
    previous_except_hook = sys.excepthook
    EXCEPT_HOOKS_HISTORY.append(previous_except_hook)

    def hook_wrapper(
        type_: Type[BaseException], value: BaseException, traceback: TracebackType
    ):
        f""" Adapter created by register_except_hook() to wrap {hook}()
            This is done so {hook}() can accept a forth param, the
            previous except hook, which is not passed other wise.

            You can get a reference on the {hook}() function by accessing
            hook_wrapper.__wrapped__
        """
        if call_previous_hook:
            previous_except_hook(type_, value, traceback)
        return hook(type_, value, traceback, previous_except_hook)

    hook_wrapper.__wrapped__ = hook  # type: ignore

    sys.excepthook = hook_wrapper
    return previous_except_hook


def restore_previous_except_hook():
    """ Restore sys.excepthook to contain the previous hook

    Get the hooks by poping PREVIOUS_EXCEPT_HOOKS.

    Not thread safe. Do it after closing all threads, subprocesses
    or event loops

    Example:

        restore_except_hook() # It's all automatic, nothing else to do

    """
    replacing_hook = sys.excepthook
    if not EXCEPT_HOOKS_HISTORY:
        raise IndexError("No previous except hook found to restore")
    hook = EXCEPT_HOOKS_HISTORY.pop()
    sys.excepthook = hook
    return replacing_hook


def register_signal_hook(
    hook: Callable[[signal.Signals, FrameType, Optional[SignalHandlerType]], bool],
    signals: Iterable[signal.Signals],
):
    """ Register a callable to run for when a set of system signals is received

    Not thread safe. Do it before starting any thread, subprocess or event loop

    Args:

        hook: the callable to attach. If the callable return True, don't exit
              no matter the signal. It will we wrapped in an adapter of
              type SignalHookType
        signals: a list of signal names to attach to.
                Use signals_from_names() to pass a list
                of signals that will be filtered depending of the OS.

    Example:

        def hook1(sig, frame, previous_hook):
            print("I'll be called when the program receive a signal")

        register_signal_hook(hook1)

        # This will replace the previous hook for SIGABRT:

        from signals import Signals

        def hook2(sig, frame, previous_hook):
            print("I'll be called when the code calls os.abort()")
            return True # keep running, don't exit

        register_signal_hook(hook2, [Signals.SIGABRT])

    """

    @wraps(hook)
    def hook_wrapper(sig: signal.Signals, frame: FrameType) -> bool:
        return hook(sig, frame, PREVIOUS_SIGNAL_HOOKS[sig][-1])

    for sig in signals_from_names(signals):
        previous_handler = signal.getsignal(sig)
        PREVIOUS_SIGNAL_HOOKS.setdefault(sig, []).append(previous_handler)
        signal.signal(sig, hook_wrapper)


def restore_signal_hooks(signals: Iterable[signal.Signals]):
    """ Set signals hooks to their previous values

    Args:
        signals: the names of the signal look for in PREVIOUS_SIGNAL_HOOKS
                 for handlers to restore

    Not thread safe. Do it after closing all threads, subprocesses
    or event loops.

    Example:

        restore_signal_hooks()

    """
    for sig in signals_from_names(signals):
        previous_hooks = PREVIOUS_SIGNAL_HOOKS.get(sig, [])
        if not previous_hooks:
            raise IndexError(f"No previous hooks found for signal {signal} to restore")
        signal.signal(sig, previous_hooks.pop())
