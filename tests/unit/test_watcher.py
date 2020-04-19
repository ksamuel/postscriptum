import sys
import signal
import traceback

from unittest.mock import patch, Mock, call

import pytest

from postscriptum.watcher import EventWatcher, PROCESS_TERMINATING_SIGNAL
from postscriptum.signals import signals_from_names, SIGNAL_HANDLERS_HISTORY
from postscriptum.excepthook import EXCEPTION_HANDLERS_HISTORY
from postscriptum.exceptions import ExitFromSignal


def test_watcher_context_decorator():

    watch = EventWatcher()
    context_decorator = watch()

    assert context_decorator.on_enter == watch.start
    assert context_decorator.on_system_exit == watch._call_quit_handlers

    with pytest.raises(RuntimeError):
        watch.start()
        assert watch.started
        watch.start()

    assert not watch.started


def test_finish_handler():

    finish_handler = Mock()
    watch = EventWatcher()
    watch.finish_handlers.add(finish_handler)

    with patch("atexit.register") as mock:
        watch.start()

    mock.assert_called_once_with(watch._call_finish_handlers)

    with patch("atexit.unregister") as mock:
        watch.stop()

    mock.assert_called_once_with(watch._call_finish_handlers)

    watch._call_finish_handlers()

    finish_handler.assert_called_once()

    watch = EventWatcher()

    with pytest.raises(AssertionError):

        @watch.on_finish
        def _():
            pass

    @watch.on_finish()
    def _():
        pass

    assert set(watch.finish_handlers) == {
        _
    }, "on_finish() should add the function as a handler"


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

    watch.stop()
    assert sys.excepthook == sys.__excepthook__, "Stop reset the except hook"

    watch = EventWatcher()

    with pytest.raises(AssertionError):

        @watch.on_crash
        def _():
            pass

    @watch.on_crash()
    def _():
        pass

    assert set(watch.crash_handlers) == {
        _
    }, "on_crash() should add the function as a handler"


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

    watch.stop()

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

    watch = EventWatcher()

    with pytest.raises(AssertionError):

        @watch.on_terminate
        def _():
            pass

    @watch.on_terminate()
    def _():
        pass

    assert set(watch.terminate_handlers) == {
        _
    }, "on_terminate() should add the function as a handler"


def test_quit_handler():

    quit_handler = Mock()
    watch = EventWatcher()
    watch.quit_handlers.add(quit_handler)

    with pytest.raises(SystemExit):
        with watch():
            raise SystemExit(1)

    assert quit_handler.call_args == call(
        {"exit_code": 1}
    ), "Handler should be called for SystemExit"

    watch = EventWatcher()

    with pytest.raises(AssertionError):

        @watch.on_quit
        def _(context):
            pass

    watch = EventWatcher(raise_again_after_quit_handlers=False)

    @watch.on_quit()
    def _(context):
        quit_handler(context)

    with watch():
        raise sys.exit(2)

    assert quit_handler.call_args == call(
        {"exit_code": 2}
    ), "Handler should be called for sys.exit()"


def test_handlers_are_not_called_twice():

    fake_exception = Exception()
    fake_traceback = traceback.format_list([("foo.py", 3, "<module>", "foo.bar()")])
    handler = Mock()

    watch = EventWatcher()
    watch.finish_handlers.add(handler)
    watch.crash_handlers.add(handler)

    with watch():
        sys.excepthook(Exception, fake_exception, fake_traceback)
        handler.assert_called_once_with(
            {
                "exception_type": Exception,
                "exception_value": fake_exception,
                "exception_traceback": fake_traceback,
                "previous_exception_handler": EXCEPTION_HANDLERS_HISTORY[-1],
            }
        )
