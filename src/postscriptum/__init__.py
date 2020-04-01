"""Postscriptum: an intuitive and unified API to run code when Python exit

Postscriptum wraps atexit.register, sys.excepthook and signal.signal to lets you do:

::

    import postscriptum
    watch = postscriptum.setup() # do this before creating a thread or a process

    @watch.on_finish() # don't forget the parenthesis !
    def _(context):
        print("When the program finish, no matter the reason.")

    @watch.on_terminate()
    def _(context):  # context contains the signal that lead to termination
        print("When the user terminate the program. E.G: Ctrl + C, kill -9, etc.")

    @watch.on_crash()
    def _(context): # context contains the exception and traceback
        print("When there is an unhandled exception")

All those functions will be called automatically at the proper moment. The handler for on_finish() will be called even if another handler has been called.

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

You can also capture sys.exit() and manual raise of SystemExit:

::

    @watch.on_quit()
    def _(context):  # context contains the exit code
        print('Why me ?')

BUT for this you MUST use the watcher as a decorator:

::

    @watch() # parenthesis !
    def main():
        do_stuff()

    main()

Or as a context manager:

::

    with watch: # NO parenthesis !
        do_stuff()

The context is a dictionary that can contain:

    For on_crash handlers:

        - **exception_type**: the class of the exception that lead to the crash
        - **exception_value**: the value of the exception that lead to the crash
        - **exception_traceback**: the traceback at the moment of the crash
        - **previous_exception_hook**: the callable that was the exception hook before we called setup()

    For on_terminate handlers:

        - **signal**: the number representing the signal that was sent to terminate the program
        - **signal_frame**: the frame state at the moment the signal arrived
        - **previous_signal_hook**: the signal handler that was set before we called setup()
        - **recommended_exit_code**: the polite exit code to use when exiting after this signal

    For on_quit_handlers:

        - **exit_code**: the code passed to SystemExit/sys.exit.

    on_finish handlers context is empty.


Currently, postscriptum does not provide a hook for

- sys.unraisablehook
- exception occuring in other threads (threading.excepthook from 3.8 will allow us to do that later)
- unhandled exception errors in unawaited asyncio (not sure we should do something though)

.. warning::
    You must be very careful about the code you put in handlers. If you mess in there,
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

__version__ = "0.1"

import sys
import os
import time
import atexit
import signal

from functools import wraps

from typing import *
from types import FrameType

PROCESS_ENDING_SIGNALS = (
    "SIGABRT",
    "SIGBREAK",
    "SIGILL",
    "SIGINT",
    "SIGSEGV",
    "SIGTERM",
)

# TODO: unraisable hook: https://docs.python.org/3/library/sys.html#sys.unraisablehook
# TODO: threading excepthook: threading.excepthook()
# TODO: default for unhandled error in asyncio


class ExitFromSignal(SystemExit):
    """ SystemExit child we raise when we want to exit form signals

        This is done to catch it specifically later and deal with this exit
        as a special case.
    """

    pass


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


class ExitWatcher:
    """
        A registry containing/attaching hooks to the various exit scenario

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

        # called atexit, signal handler, systemexit and exceptook
        self._finish_handlers = list(finish_handlers)

        # Called on External signals and Ctrl + C
        self._terminate_handlers = list(terminate_handlers)

        # Call on system except hooks
        self._crash_handlers = list(crash_handlers)

        # Call on sys.exit and Ctrl + C
        self._quit_handlers = list(quit_handlers)

        self._called_handlers: Set[Callable] = set()
        self.context: dict = {}
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

    # def on_traceback(self, func=None):
    #     return self._register_handler(func, self._traceback_handlers, 'on_traceback')

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

        if func is not None:
            raise ValueError(
                f"This object must be called before being used as a "
                "decorator: add parenthesis. E.G: if you have this object in "
                "a variabled 'watch', do @watch() and not @watch."
            )

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self:
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def __enter__(self):
        pass

    def __exit__(self, exception_type, exception_value, traceback):
        received_signal = isinstance(exception_value, ExitFromSignal)
        received_quit = isinstance(exception_value, SystemExit)
        if received_quit and not received_signal:
            return not self._call_quit_handlers(exception_value)


def setup(*args, **kwargs):
    hook = ExitWatcher(*args, **kwargs)
    hook.register_hooks()
    return hook


if __name__ == "__main__":

    watch = setup()

    @watch.on_quit()
    def q(context):
        print("Quit")
        print(context)

    @watch.on_finish()
    def f(context):
        print("Finish")
        print(context)

    @watch.on_terminate()
    def t(context):
        print("Terminate")
        print(context)

    @watch.on_crash()
    def c(context):
        print("Crash")
        print(context)

    @watch()
    def main():
        print(os.getpid())
        name, *rest = sys.argv
        if rest:
            if rest[0] == "loop":
                for x in range(1):
                    print(".")
                    time.sleep(1)
                sys.exit(0)  # test quit
            else:
                1 / 0  # test crash

    main()
    # test finish
