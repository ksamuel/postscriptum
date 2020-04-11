import signal

from typing import Callable, Type, Any, Union
from types import TracebackType, FrameType

# The callable in sys.excepthook
ExceptionHandlerType = Callable[
    [Type[BaseException], BaseException, TracebackType], Any
]

# The user provided callable we will call in sys.excepthook
PostScripumExceptionHandlerType = Callable[
    [Type[BaseException], BaseException, TracebackType, ExceptionHandlerType], None,
]

EventWatcherHandlerType = Callable[[dict], None]

# The values to set as a handler for a given signal
SignalHandlerType = Union[
    Callable[[signal.Signals, FrameType], None], int, signal.Handlers, None
]

# Signal Enum value or signal name
SignalType = Union[signal.Signals, str]
