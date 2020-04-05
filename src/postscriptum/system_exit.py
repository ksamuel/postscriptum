from typing import *
from types import TracebackType

from contextlib import ContextDecorator

from postscriptum.exceptions import ExitFromSignal


class catch_system_exit(ContextDecorator):
    """React to system exit if it's not sent from a signal handler.

    It can be used as a decorator and a context manager.

    Args:
        handler: the callable to run when the SystemExit is caught.
                 It should accept Type[Exception], Exception, TracebackType as
                 a param
        raise_again: do we raise the exception again after catching it?

    Example:

            def callback(exception_type, exception_value, traceback):
                print("I will be called is something call sys.exit() or raise SystemExit")

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
        handler: Callable[[Type[Exception], Exception, TracebackType], None],
        raise_again: bool = True,
    ):
        self.handler = handler
        self.raise_again = raise_again

    def __enter__(self):
        pass

    def __exit__(
        self,
        exception_type: Type[Exception],
        exception_value: Exception,
        traceback: TracebackType,
    ) -> bool:
        received_signal = isinstance(exception_value, ExitFromSignal)
        received_quit = isinstance(exception_value, SystemExit)
        if received_quit and not received_signal:
            self.handler(exception_type, exception_value, traceback)
        return not self.raise_again
