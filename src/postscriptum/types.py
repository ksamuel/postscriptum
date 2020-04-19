# pylint: disable=invalid-name

import signal

from types import TracebackType, FrameType
from typing import Callable, Type, Any, Union, TypeVar

from typing_extensions import TypedDict, NoReturn

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


TerminateContextType = TypedDict(
    "TerminateContextType",
    {
        "signal": signal.Signals,
        "signal_frame": FrameType,
        "previous_signal_handler": SignalHandlerType,
        "exit": Callable[[int], NoReturn],
    },
)

CrashContextType = TypedDict(
    "CrashContextType",
    {
        "exception_type": Type[Exception],
        "exception_value": Exception,
        "exception_traceback": TracebackType,
        "previous_exception_handler": ExceptionHandlerType,
    },
)

QuitContextType = TypedDict(
    "QuitContextType", {"exit_code": int, "exit": Callable[[int], NoReturn],}
)

EmptyContextType = TypedDict("EmptyContextType", {})

EventContextType = Union[
    EmptyContextType, TerminateContextType, QuitContextType, CrashContextType,
]


TerminateHandlerType = Callable[[TerminateContextType], None]
QuitHandlerType = Callable[[QuitContextType], None]
CrashHandlerType = Callable[[CrashContextType], None]
FinishHandlerType = Callable[
    [EventContextType], None,
]
AlwaysHandlerType = Callable[
    [EventContextType], None,
]
HoldHandlerType = Callable[
    [EventContextType], None,
]

EventHandlerType = Union[
    TerminateHandlerType,
    QuitHandlerType,
    CrashHandlerType,
    FinishHandlerType,
    AlwaysHandlerType,
    HoldHandlerType,
]

EventContextTypeVar = TypeVar(
    "EventContextTypeVar",
    EmptyContextType,
    TerminateContextType,
    QuitContextType,
    CrashContextType,
)
