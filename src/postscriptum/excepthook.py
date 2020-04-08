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
