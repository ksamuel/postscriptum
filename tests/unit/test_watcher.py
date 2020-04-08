import sys
import signal
import traceback

from unittest.mock import patch, Mock, call

import pytest

from postscriptum.watcher import EventWatcher, PROCESS_TERMINATING_SIGNAL
from postscriptum.signals import signals_from_names, SIGNAL_HANDLERS_HISTORY
from postscriptum.excepthook import EXCEPTION_HANDLERS_HISTORY
from postscriptum.exceptions import ExitFromSignal


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

    with watch():

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

    assert sys.excepthook == sys.__excepthook__, "Stop reset the except hook"


def test_terminate_handler(subtests):

    signal_handler = Mock()
    fake_frame = Mock()

    watch = EventWatcher()

    watch.terminate_handlers.add(signal_handler)

    with watch():
        previous_signals = {}
        for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):

            with subtests.test(msg="Test each signal handler", signal=sig):

                handler = signal.getsignal(sig)
                assert (
                    signal.getsignal(sig).__wrapped__ == watch._call_terminate_handlers
                ), "Watcher signal handler should the handler for this signal"

                with pytest.raises(ExitFromSignal):
                    handler(sig, fake_frame)

                signal_handler._called_handlers = set()
                previous_signals[sig] = SIGNAL_HANDLERS_HISTORY[sig][-1]
                assert signal_handler.call_args == call(
                    {
                        "signal": sig,
                        "signal_frame": fake_frame,
                        "previous_signal_handler": previous_signals[sig],
                        "recommended_exit_code": sig + 128,
                    }
                ), "Our handler should be called with the signal context"

    for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):
        with subtests.test(msg="Check that each handler is reset", signal=sig):
            assert previous_signals[sig] == signal.getsignal(
                sig
            ), "Signal should be restored to its previous value"

    watch = EventWatcher(exit_after_terminate_handlers=False)

    with watch():

        for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):
            with subtests.test(msg="Test each signal handler without exit", signal=sig):
                handler = signal.getsignal(sig)
                handler(sig, fake_frame)
