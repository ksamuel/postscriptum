# pylint: disable=invalid-name

import signal

from types import TracebackType, FrameType
from typing import Callable, Type, Any, Union

from typing_extensions import TypedDict

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


TerminateHandlerContextType = TypedDict(
    "TerminateHandlerContextType",
    {
        "signal": signal.Signals,
        "signal_frame": FrameType,
        "previous_signal_handler": SignalHandlerType,
        "recommended_exit_code": int,
    },
)

CrashHandlerContextType = TypedDict(
    "CrashHandlerContextType",
    {
        "exception_type": Type[Exception],
        "exception_value": Exception,
        "exception_traceback": TracebackType,
        "previous_exception_handler": ExceptionHandlerType,
    },
)

QuitHandlerContextType = TypedDict("QuitHandlerContextType", {"exit_code": int,})

EmptyContextType = TypedDict("EmptyContextType", {})

EventWatcherHandlerContextType = Union[
    EmptyContextType,
    TerminateHandlerContextType,
    QuitHandlerContextType,
    CrashHandlerContextType,
]


TerminateHandlerType = Callable[[TerminateHandlerContextType], None]
QuitHandlerType = Callable[[QuitHandlerContextType], None]
CrashHandlerType = Callable[[CrashHandlerContextType], None]
FinishHandlerType = Callable[
    [EventWatcherHandlerContextType], None,
]

EventWatcherHandlerType = Union[
    TerminateHandlerType, QuitHandlerType, CrashHandlerType, FinishHandlerType
]
