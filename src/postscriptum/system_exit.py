from typing import Callable, Type, Any
from typing import cast
from types import TracebackType

from contextlib import ContextDecorator

from postscriptum.types import ExceptionHandlerType
from postscriptum.exceptions import PubSubExit


class catch_system_exit(ContextDecorator):  # pylint: disable=invalid-name
    """React to system exit if it's not sent from a signal handler.

    It can be used as a decorator and a context manager.

    Args:
        handler: the callable to run when the SystemExit is caught.
                 It should accept Type[Exception], Exception, TracebackType as
                 a param
        raise_again: do we raise the exception again after catching it?

    Example:

            def callback(exception_type, exception_value, traceback):
                print("I will be called on sys.exit() or raise SystemExit")

            # This prints, then exit.
            with catch_system_exit(callback):
                sys.exit(0)

        Or:

            # This prints but doesn't exit.
            @catch_system_exit(callback, raise=False)
            def main():
                raise SystemExit()


    """

    def __init__(
        self,
        on_system_exit: Callable[[Type[SystemExit], SystemExit, TracebackType], Any],
        on_enter: Callable = None,
        on_exit: ExceptionHandlerType = None,
        raise_again: bool = True,
    ):
        self.on_enter = on_enter
        self.on_exit = on_exit
        self.on_system_exit = on_system_exit
        self.raise_again = raise_again

    def __enter__(self):
        if self.on_enter:
            self.on_enter()

    def __exit__(
        self,
        exception_type: Type[Exception],
        exception_value: Exception,
        traceback: TracebackType,
    ) -> bool:

        received_signal = isinstance(exception_value, PubSubExit)
        received_quit = isinstance(exception_value, SystemExit)
        if received_quit and not received_signal:
            self.on_system_exit(
                cast(Type[SystemExit], exception_type),
                cast(SystemExit, exception_value),
                traceback,
            )
        elif self.on_exit:
            self.on_exit(exception_type, exception_value, traceback)

        return not self.raise_again
