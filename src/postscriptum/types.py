import signal

from typing import *
from typing import Callable  # * does't include those
from types import TracebackType, FrameType

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
