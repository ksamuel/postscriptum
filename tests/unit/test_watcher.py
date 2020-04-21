import sys
import signal
import traceback

from contextlib import ExitStack

from unittest.mock import patch, Mock, call

import pytest

from postscriptum.pubsub import PubSub, PROCESS_TERMINATING_SIGNAL
from postscriptum.signals import signals_from_names, SIGNAL_HANDLERS_HISTORY
from postscriptum.excepthook import EXCEPTION_HANDLERS_HISTORY
from postscriptum.exceptions import PubSubExit


def test_pubsub_context_decorator():

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


def test_start_stop():

    ps = PubSub()

    with ExitStack() as stack:

        setup_ex = stack.enter_context(patch.object(ps, "setup_exception_handler"))
        setup_sig = stack.enter_context(patch.object(ps, "setup_signal_handler"))
        setup_atexit = stack.enter_context(patch.object(ps, "setup_atexit_handler"))

        assert ps.start()

        setup_ex.assert_called_once()
        setup_sig.assert_called_once()
        setup_atexit.assert_called_once()

        assert not ps.start(), "Calling start() twice should be a noop"

        teardown_ex = stack.enter_context(
            patch.object(ps, "teardown_exception_handler")
        )
        teardown_sig = stack.enter_context(patch.object(ps, "teardown_signal_handler"))
        teardown_atexit = stack.enter_context(
            patch.object(ps, "teardown_atexit_handler")
        )

        assert ps.stop()

        teardown_ex.assert_called_once()
        teardown_sig.assert_called_once()
        teardown_atexit.assert_called_once()

        assert not ps.stop(), "Calling stop() twice should be a noop"


def test_finish_handler():

    finish_handler = Mock()
    always_handler = Mock()

    ps = PubSub()
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)

    with patch("atexit.register") as mock:
        ps.start()

    mock.assert_called_once_with(ps._handle_finish)

    with patch("atexit.unregister") as mock:
        ps.stop()

    mock.assert_called_once_with(ps._handle_finish)

    ps._handle_finish()

    finish_handler.assert_called_once()
    always_handler.assert_called_once()

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
    finish_handler = Mock()
    always_handler = Mock()

    ps = PubSub()
    ps.crash_handlers.add(crash_handler)
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)

    with patch("sys.excepthook") as fake_hook:
        with ps():

            assert (
                sys.excepthook.__wrapped__ == ps._handle_crash
            ), "Start set the excepthook"

            sys.excepthook(Exception, fake_exception, fake_traceback)

            event = {
                "exception": fake_exception,
                "traceback": fake_traceback,
                "stacktrace": crash_handler.call_args[0][0]["stacktrace"],
                "previous_exception_handler": EXCEPTION_HANDLERS_HISTORY[-1],
            }

            crash_handler.assert_called_once_with(event)
            finish_handler.assert_called_once_with(event)
            always_handler.assert_called_once_with(event)

        fake_hook.assert_called_once()

    ps.stop()
    assert sys.excepthook == fake_hook, "Stop reset the except hook"

    with patch("sys.excepthook") as fake_hook:
        ps = PubSub(call_previous_exception_handler=False)
        with ps():
            sys.excepthook(Exception, fake_exception, fake_traceback)
        assert not fake_hook.call_count, "Previous handler should not be called"
        ps.stop()

    sys.excepthook = sys.__excepthook__

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

    fake_frame = Mock()
    terminate_handler = Mock()
    finish_handler = Mock()
    always_handler = Mock()
    hold_handler = Mock()

    ps = PubSub()
    ps.terminate_handlers.add(terminate_handler)
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)
    ps.hold_handlers.add(hold_handler)

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

                previous_signals[sig] = SIGNAL_HANDLERS_HISTORY[sig][-1]

                event = {
                    "signal": sig,
                    "signal_frame": fake_frame,
                    "previous_signal_handler": previous_signals[sig],
                    "exit": terminate_handler.call_args[0][0]["exit"],
                }
                assert terminate_handler.call_args == call(
                    event
                ), "Main handler should be called with the signal context"

                assert finish_handler.call_args == call(
                    event
                ), "Finish handler should be called with the signal context"

                assert always_handler.call_args == call(
                    event
                ), "Always handler should be called with the signal context"

                assert not hold_handler.call_count, "Hold handler should not be called"

    ps.stop()

    for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):
        with subtests.test(msg="Check that each handler is reset", signal=sig):
            assert previous_signals[sig] == signal.getsignal(
                sig
            ), "Signal should be restored to its previous value"

    ps = PubSub(exit_on_terminate=False)
    finish_handler = Mock()
    ps.terminate_handlers.add(terminate_handler)
    ps.finish_handlers.add(finish_handler)
    ps.hold_handlers.add(hold_handler)
    ps.always_handlers.add(always_handler)

    with ps():

        for sig in signals_from_names(PROCESS_TERMINATING_SIGNAL):
            with subtests.test(msg="Test each signal handler without exit", signal=sig):
                handler = signal.getsignal(sig)
                handler(sig, fake_frame)
                event = {
                    "signal": sig,
                    "signal_frame": fake_frame,
                    "previous_signal_handler": previous_signals[sig],
                    "exit": terminate_handler.call_args[0][0]["exit"],
                }

                assert hold_handler.call_args == call(
                    event
                ), "Hold handler should be called with the signal context"

                assert always_handler.call_args == call(
                    event
                ), "Always handler should be called with the signal context"

                assert (
                    not finish_handler.call_count
                ), "Finish handler should not be called"

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


def test_terminate_with_exception():

    fake_frame = Mock()
    finish_handler = Mock()
    always_handler = Mock()

    ps = PubSub()
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)

    @ps.on_terminate()
    def _(event):
        event["exit"]()

    ps.start()

    with pytest.raises(PubSubExit):
        signal.getsignal(signal.SIGINT)(signal.SIGINT, fake_frame)

    finish_handler.assert_called_once()
    always_handler.assert_called_once()

    ps = PubSub()
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)

    @ps.on_terminate()
    def _(event):

        _.called += 1

        if _.called == 1:
            raise KeyboardInterrupt

    _.called = 0

    ps.start()
    with pytest.raises(PubSubExit):
        signal.getsignal(signal.SIGINT)(signal.SIGINT, fake_frame)

    assert _.called == 2

    assert finish_handler.call_count == 2
    assert always_handler.call_count == 2

    ps = PubSub()

    @ps.on_terminate()
    def _(event):
        raise TypeError

    ps.start()
    with pytest.raises(TypeError):
        signal.getsignal(signal.SIGINT)(signal.SIGINT, fake_frame)


def test_quit_handler():

    quit_handler = Mock()
    finish_handler = Mock()
    always_handler = Mock()
    hold_handler = Mock()

    ps = PubSub()
    ps.quit_handlers.add(quit_handler)
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)
    ps.hold_handlers.add(hold_handler)

    with pytest.raises(SystemExit):
        with ps():
            raise SystemExit(1)

    event = {"exit_code": 1, "exit": quit_handler.call_args[0][0]["exit"]}
    assert quit_handler.call_args == call(
        event
    ), "Handler should be called for SystemExit"

    assert finish_handler.call_args == call(
        event
    ), "Handler should be called for SystemExit"

    assert always_handler.call_args == call(
        event
    ), "Handler should be called for SystemExit"

    assert not hold_handler.call_count, "Hold handler should not be called"

    ps = PubSub()

    with pytest.raises(AssertionError):

        @ps.on_quit
        def _(event):
            pass

    @ps.on_quit()
    def _(event):
        pass

    assert ps.quit_handlers == {_}

    ps = PubSub(exit_after_quit_handlers=False)
    ps.quit_handlers.add(quit_handler)
    finish_handler = Mock()
    ps.finish_handlers.add(finish_handler)
    ps.always_handlers.add(always_handler)
    ps.hold_handlers.add(hold_handler)

    with ps():
        raise sys.exit(2)

    event = {"exit_code": 2, "exit": quit_handler.call_args[0][0]["exit"]}
    assert quit_handler.call_args == call(
        event
    ), "Handler should be called for sys.exit()"

    assert hold_handler.call_args == call(
        event
    ), "Handler should be called for SystemExit"

    assert always_handler.call_args == call(
        event
    ), "Handler should be called for SystemExit"

    assert not finish_handler.call_count, "Finish handler should not be called"

    ps = PubSub()

    @ps.on_quit()
    def _(event):
        event["exit"]()

    with pytest.raises(PubSubExit):
        with ps():
            raise sys.exit(2)


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
                "exception": fake_exception,
                "traceback": fake_traceback,
                "stacktrace": handler.call_args[0][0]["stacktrace"],
                "previous_exception_handler": EXCEPTION_HANDLERS_HISTORY[-1],
            }
        )


def test_hold_handlers():

    ps = PubSub()

    @ps.on_hold()
    def _(event):
        pass

    assert ps.hold_handlers == {_}, "Our function should be in the handler set"


def test_always_handlers():

    ps = PubSub()

    @ps.always()
    def _(event):
        pass

    assert ps.always_handlers == {_}, "Our function should be in the handler set"
