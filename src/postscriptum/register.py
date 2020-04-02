"""Low level tooling to register handlers for excepthook and signals
"""

import sys
import signal

from typing import *

from functools import wraps
from types import FrameType

PROCESS_ENDING_SIGNALS = (
    "SIGABRT",
    "SIGBREAK",
    "SIGILL",
    "SIGINT",
    "SIGSEGV",
    "SIGTERM",
)


def register_except_hook(hook: Callable, call_previous_hook: bool = True):
    """ Set the callable to be used when an exception is not handled

            You probably don't want to use that manually. We use it to
            set the Watcher class hook.

        hook: the callable to put into sys.excepthook
        call_previous_hook: should we call the previous hook as well ? Keep
        that to True unless you really know what you are doing.

    """
    previous_except_hook = sys.excepthook
    register_except_hook.previous_except_hooks.append(  # type: ignore
        previous_except_hook
    )

    def hook_wrapper(exception_type, exception_value, traceback):
        if call_previous_hook:
            previous_except_hook(exception_type, exception_value, traceback)
        hook(exception_type, exception_value, traceback, previous_except_hook)

    sys.excepthook = hook_wrapper
    return previous_except_hook


register_except_hook.previous_except_hooks = []  # type: ignore


def restore_except_hook(hook: Callable = None):
    """ Restore sys.excepthook to contain the previous hook

        This is never called automatically but you migth want to call it
        yourself if you need to remove the hooks from the watcher.

        hook: the whole hook to put back. Default is to pop it from the
        list register_except_hook.previous_except_hooks, which contains
        a stack of all hooks replaced by register_except_hook.

    """
    replacing_hook = sys.excepthook
    if not hook:
        if not register_except_hook.previous_except_hooks:  # type: ignore
            raise RuntimeError("No previous hook found to put back")
        hook = register_except_hook.previous_except_hooks.pop()  # type: ignore
    sys.excepthook = hook
    return replacing_hook


def register_signal_hook(
    hook: Callable[[signal.Signals, FrameType, Optional[None]], bool],
    signals: Iterable[str] = PROCESS_ENDING_SIGNALS,
):
    """ Register a callable to run for when a list of system signals is received

        You probably don't want to use that manually. We use it to
        set the Watcher class hooks.

        hook: the callable to attach. If the callable return True, don't exit
        no matter the signal.
        signals: a list of signal names to attach to. Usually exit signals.
    """
    previous_hooks: dict = {}

    @wraps(hook)
    def hook_wrapper(code: signal.Signals, frame: FrameType) -> bool:
        return hook(code, frame, previous_hooks.get(code, None))

    for name in signals:
        code = getattr(signal, name, None)  # handle different OSes
        if code:
            previous_hook = signal.getsignal(code)
            previous_hooks[code] = previous_hook
            signal.signal(code, hook_wrapper)
    register_signal_hook.previous_except_hooks.append(previous_hooks)  # type: ignore


register_signal_hook.previous_except_hooks = []  # type: ignore


def restore_signal_hooks(hooks: Mapping[signal.Signals, Any] = None):
    """ Set signals hooks to their previous values

        This is never called automatically but you migth want to call it
        yourself if you need to remove the hooks from the watcher.

        hooks: a mapping with keys being the signals and values being the
        handlers to set.

    """
    restore_hooks = {}
    if register_signal_hook.previous_except_hooks:  # type: ignore
        restore_hooks.update(
            register_signal_hook.previous_except_hooks.pop()  # type: ignore
        )
    if hooks:
        restore_hooks.update(hooks)
    for code, hook in restore_hooks.items():
        previous_hook = signal.signal(code, hook)
