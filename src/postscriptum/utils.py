import sys

from typing import Callable
from typing_extensions import NoReturn

from postscriptum.exceptions import PubSubExit


IS_WINDOWS = sys.platform.startswith("win")
IS_UNIX = any(sys.platform.startswith(n) for n in ("linux", "freebsd", "darwin"))


def create_handler_decorator(func: Callable, add_handler: Callable, name: str):
    """ Utility method to create the on_* decorators for each type of event
    """
    assert func is None, (
        f"{name} must be called before being used as a decorator. "
        "Add parenthesis: {name}()"
    )

    def decorator(func):
        add_handler(func)
        return func

    return decorator


def force_exit(exit_code) -> NoReturn:
    raise PubSubExit(exit_code)
