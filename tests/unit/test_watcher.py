import sys
import signal
import traceback

from unittest.mock import patch, Mock, call

import pytest

from postscriptum.pubsub import PubSub, PROCESS_TERMINATING_SIGNAL
from postscriptum.signals import signals_from_names, SIGNAL_HANDLERS_HISTORY
from postscriptum.excepthook import EXCEPTION_HANDLERS_HISTORY
from postscriptum.exceptions import PubSubExit


def test_watcher_context_decorator():

    ps = PubSub()
    context_decorator = ps()

    assert context_decorator.on_enter == ps.start
    assert context_decorator.on_system_exit == ps._handle_quit

    with patch.object(ps, "_called_handlers") as mock:
        ps.start()
        mock.clear.assert_called_once()
        assert ps.started

    with patch.object(ps, "_called_handlers") as mock:
        ps.start()
        assert not mock.clear.call_count

    ps.stop()
    assert not ps.started


def test_finish_handler():

    finish_handler = Mock()
    ps = PubSub()
    ps.finish_handlers.add(finish_handler)

    with patch("atexit.register") as mock:
        ps.start()

    mock.assert_called_once_with(ps._handle_finish)

    with patch("atexit.unregister") as mock:
        ps.stop()

    mock.assert_called_once_with(ps._handle_finish)

    ps._handle_finish()

    finish_handler.assert_called_once()

    ps = PubSub()

    with pytest.raises(AssertionError):

        @ps.on_finish
        def _():
            pass

    @ps.on_finish()
    def _():
        pass

    assert set(ps.finish_handlers) == {
        _
    }, "on_finish() should add the function as a handler"


def test_crash_handler():

    fake_exception = Exception()
    fake_traceback = traceback.format_list([("foo.py", 3, "<module>", "foo.bar()")])
    crash_handler = Mock()

    ps = PubSub()
    ps.crash_handlers.add(crash_handler)

    with ps():

        assert (
            sys.excepthook.__wrapped__ == ps._handle_crash
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

    ps.stop()
    assert sys.excepthook == sys.__excepthook__, "Stop reset the except hook"

    ps = PubSub()

    with pytest.raises(AssertionError):

        @ps.on_crash
        def _():
            pass

    @ps.on_crash()
    def _():
        pass

    assert set(ps.crash_handlers) == {
        _
    }, "on_crash() should add the function as a handler"


def test_terminate_handler(subtests):

    signal_handler = Mock()
    fake_frame = Mock()
    ps = PubSub()
    ps.terminate_handlers.add(signal_handler)

    with ps():

        previous_signals = {}
        for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):

            with subtests.test(msg="Test each signal handler", signal=sig):

                ps._called_handlers.clear()

                handler = signal.getsignal(sig)
                assert (
                    signal.getsignal(sig).__wrapped__ == ps._handle_terminate
                ), "The PubSub signal handler should the handler for this signal"

                with pytest.raises(PubSubExit):
                    handler(sig, fake_frame)

                signal_handler._called_handlers = set()
                previous_signals[sig] = SIGNAL_HANDLERS_HISTORY[sig][-1]

                assert signal_handler.call_args == call(
                    {
                        "signal": sig,
                        "signal_frame": fake_frame,
                        "previous_signal_handler": previous_signals[sig],
                        "exit": signal_handler.call_args[0][0]["exit"],
                    }
                ), "Our handler should be called with the signal context"

    ps.stop()

    for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):
        with subtests.test(msg="Check that each handler is reset", signal=sig):
            assert previous_signals[sig] == signal.getsignal(
                sig
            ), "Signal should be restored to its previous value"

    ps = PubSub(exit_after_terminate_handlers=False)

    with ps():

        for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):
            with subtests.test(msg="Test each signal handler without exit", signal=sig):
                handler = signal.getsignal(sig)
                handler(sig, fake_frame)

    ps = PubSub()

    with pytest.raises(AssertionError):

        @ps.on_terminate
        def _():
            pass

    @ps.on_terminate()
    def _():
        pass

    assert set(ps.terminate_handlers) == {
        _
    }, "on_terminate() should add the function as a handler"


def test_quit_handler():

    quit_handler = Mock()
    ps = PubSub()
    ps.quit_handlers.add(quit_handler)

    with pytest.raises(SystemExit):
        with ps():
            raise SystemExit(1)

    assert quit_handler.call_args == call(
        {"exit_code": 1, "exit": quit_handler.call_args[0][0]["exit"]}
    ), "Handler should be called for SystemExit"

    ps = PubSub()

    with pytest.raises(AssertionError):

        @ps.on_quit
        def _(context):
            pass

    ps = PubSub(exit_after_quit_handlers=False)

    @ps.on_quit()
    def _(context):
        quit_handler(context)

    with ps():
        raise sys.exit(2)

    assert quit_handler.call_args == call(
        {"exit_code": 2, "exit": quit_handler.call_args[0][0]["exit"]}
    ), "Handler should be called for sys.exit()"


def test_handlers_are_not_called_twice():

    fake_exception = Exception()
    fake_traceback = traceback.format_list([("foo.py", 3, "<module>", "foo.bar()")])
    handler = Mock()

    ps = PubSub()
    ps.finish_handlers.add(handler)
    ps.crash_handlers.add(handler)

    with ps():
        sys.excepthook(Exception, fake_exception, fake_traceback)
        handler.assert_called_once_with(
            {
                "exception_type": Exception,
                "exception_value": fake_exception,
                "exception_traceback": fake_traceback,
                "previous_exception_handler": EXCEPTION_HANDLERS_HISTORY[-1],
            }
        )
