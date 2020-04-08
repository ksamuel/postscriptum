import sys
import traceback

from unittest.mock import patch, Mock

from postscriptum.watcher import EventWatcher
from postscriptum.excepthook import EXCEPTION_HANDLERS_HISTORY


def test_finish_handler():

    watch = EventWatcher()

    finish_handler = Mock()

    watch.finish_handlers.add(finish_handler)

    with patch("atexit.register") as mock:
        watch.start()

    mock.assert_called_once_with(watch._call_finish_handlers)

    with patch("atexit.unregister") as mock:
        watch.stop()

    mock.assert_called_once_with(watch._call_finish_handlers)

    watch._call_finish_handlers()

    finish_handler.assert_called_once()


def test_crash_handler():

    fake_exception = Exception()
    fake_traceback = traceback.format_list([("foo.py", 3, "<module>", "foo.bar()")])
    crash_handler = Mock()

    watch = EventWatcher()

    watch.crash_handlers.add(crash_handler)

    watch.start()

    assert (
        sys.excepthook.__wrapped__ == watch._call_crash_handlers
    ), "Start set the excepthook"

    sys.excepthook(Exception, fake_exception, fake_traceback)

    crash_handler.assert_called_once_with(
        {
            "exception_type": Exception,
            "exception_value": fake_exception,
            "exception_traceback": fake_traceback,
            "previous_exception_handler": EXCEPTION_HANDLERS_HISTORY[-1],
        }
    )

    watch.stop()

    assert sys.excepthook == sys.__excepthook__, "Stop reset the except hook"
