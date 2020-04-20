# pylint: disable=invalid-name

import signal

from types import TracebackType, FrameType
from typing import Callable, Type, Any, Union, TypeVar, TYPE_CHECKING

from typing_extensions import TypedDict, NoReturn

from ordered_set import OrderedSet

# The callable in sys.excepthook
ExceptionHandlerType = Callable[
    [Type[BaseException], BaseException, TracebackType], Any
]

# The user provided callable we will call in sys.excepthook
PostScripumExceptionHandlerType = Callable[
    [Type[BaseException], BaseException, TracebackType, ExceptionHandlerType], None,
]


# The values to set as a handler for a given signal
SignalHandlerType = Union[
    Callable[[signal.Signals, FrameType], None], int, signal.Handlers, None
]


# Signal Enum value or signal name
SignalType = Union[signal.Signals, str]


TerminateEventType = TypedDict(
    "TerminateEventType",
    {
        "signal": signal.Signals,
        "signal_frame": FrameType,
        "previous_signal_handler": SignalHandlerType,
        "exit": Callable[[int], NoReturn],
    },
)

CrashEventType = TypedDict(
    "CrashEventType",
    {
        "exception": Exception,
        "stacktrace": Callable[[Type[Exception], Exception, TracebackType], str],
        "traceback": TracebackType,
        "previous_exception_handler": ExceptionHandlerType,
    },
)

QuitEventType = TypedDict(
    "QuitEventType", {"exit_code": int, "exit": Callable[[int], NoReturn],}
)

EmptyEventType = TypedDict("EmptyEventType", {})

EventType = Union[
    EmptyEventType, TerminateEventType, QuitEventType, CrashEventType,
]


TerminateHandlerType = Callable[[TerminateEventType], None]
QuitHandlerType = Callable[[QuitEventType], None]
CrashHandlerType = Callable[[CrashEventType], None]
FinishHandlerType = Callable[
    [EventType], None,
]
AlwaysHandlerType = Callable[
    [EventType], None,
]
HoldHandlerType = Callable[
    [EventType], None,
]

EventHandlerType = Union[
    TerminateHandlerType,
    QuitHandlerType,
    CrashHandlerType,
    FinishHandlerType,
    AlwaysHandlerType,
    HoldHandlerType,
]

EventTypeVar = TypeVar(
    "EventTypeVar", EmptyEventType, TerminateEventType, QuitEventType, CrashEventType,
)


if TYPE_CHECKING:
    OrderedSetType = OrderedSet
else:

    class _OrderedSet:
        def __getitem__(self, *args):
            return OrderedSet

    OrderedSetType = _OrderedSet()
