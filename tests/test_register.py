
import sys
import traceback

from unittest.mock import Mock, patch, call

from signal import Signals

import pytest

from postscriptum.register import SIGNAL_HANDLERS_HISTORY, EXCEPTION_HANDLERS_HISTORY, register_exception_handler, restore_previous_exception_handler, register_signals_handler, signals_from_names


not_windows = not sys.platform.startswith("win")
not_unix = not any(sys.platform.startswith(n) for n in ('linux', 'freebsd', 'darwin'))

@pytest.mark.skipif(not_windows, reason="Windows only test")
def test_signals_from_names_windows():

    signals = list(signals_from_names(('SIGABRT', 'SIGBREAK', 'SIGTERM')))
    assert signals ==  [Signals.SIGABRT, Signals.SIGBREAK]


@pytest.mark.skipif(not_unix, reason="Unix only test")
def test_signals_from_names_unix():

    signals = list(signals_from_names(('SIGABRT', 'SIGBREAK', 'SIGTERM')))
    assert signals ==  [Signals.SIGABRT, Signals.SIGTERM]

    signals = list(signals_from_names((Signals.SIGABRT, 'SIGBREAK', 'SIGTERM')))
    assert signals ==  [Signals.SIGABRT, Signals.SIGTERM]


def test_register_and_restore_except_handler():

    assert not EXCEPTION_HANDLERS_HISTORY

    mock_handler_1 = Mock()
    mock_handler_2 = Mock()
    fake_exception = Exception()
    fake_traceback = traceback.format_list([('foo.py', 3, '<module>', 'foo.bar()')])

    original_python_handler = register_exception_handler(mock_handler_1)

    assert EXCEPTION_HANDLERS_HISTORY == [original_python_handler], "handler history should contain original handler"
    assert original_python_handler is sys.__excepthook__, "Original handler should be python builtin one"
    assert sys.excepthook is not original_python_handler, "The except handler should not be the original one anymore"
    assert sys.excepthook.__wrapped__ is mock_handler_1, "The current except handler should be a wrapper around our callback"

    first_handler_wrapper = sys.excepthook
    previous_handler = register_exception_handler(mock_handler_2)
    assert previous_handler == first_handler_wrapper, "The previous handler should be the wrapper around our first callback"

    assert EXCEPTION_HANDLERS_HISTORY == [original_python_handler, first_handler_wrapper], "The history should now contains both the original python handler and the wrapper around our first callback"
    assert sys.excepthook is not first_handler_wrapper, "The wrapper around our first callback should not be the current except handler"
    assert sys.excepthook.__wrapped__ is mock_handler_2, "The current except handler should be the wrapper around our second callback"

    restore_previous_exception_handler()

    assert EXCEPTION_HANDLERS_HISTORY == [original_python_handler], "History should have been restored to its previous state"
    assert sys.excepthook is first_handler_wrapper, "Except handler should have been restored to it's previous value"

    restore_previous_exception_handler()

    assert not EXCEPTION_HANDLERS_HISTORY, "History should be empty"
    assert sys.excepthook is original_python_handler, "Current except handler should be the original one"

    with patch('sys.excepthook') as original_python_handler:

        original_python_handler = register_exception_handler(mock_handler_1)

        wrapper_for_mock_handler_1 = register_exception_handler(mock_handler_2)

        sys.excepthook(Exception, fake_exception, fake_traceback)

        restore_previous_exception_handler()

        sys.excepthook(Exception, fake_exception, fake_traceback)

        restore_previous_exception_handler()

        assert original_python_handler.mock_calls == [
            call(Exception, fake_exception, fake_traceback),
            call(Exception, fake_exception, fake_traceback),
        ], "Original except handler should have been called every time"

        assert mock_handler_1.mock_calls == [
            call(Exception, fake_exception, fake_traceback, original_python_handler),
            call(Exception, fake_exception, fake_traceback, original_python_handler),
        ], "First handler replacement should have been called every time, with the original handler as param"

        assert mock_handler_2.mock_calls == [
            call(Exception, fake_exception, fake_traceback, wrapper_for_mock_handler_1),
        ], "Second handler replacement should have been called one time, with the first handler replacement as param"


    with patch('sys.excepthook') as original_python_handler:

        original_python_handler = register_exception_handler(mock_handler_1, call_previous_handler=False)

        sys.excepthook(Exception, fake_exception, fake_traceback)

        restore_previous_exception_handler()

        assert not original_python_handler.call_count, "Original handler should not have been called"

# def test_register_and_restore_signal_handlers():

#     assert not SIGNAL_HANDLERS_HISTORY

#     mock_handler_1 = Mock()
#     mock_handler_2 = Mock()

#     original_python_handler = signal.getsignal(signal.SIGABRT)
#     original_python_handler = register_signals_handler(mock_handler_1, ['SIGABRT'])

#     assert SIGNAL_HANDLERS_HISTORY == [original_python_handler], "handler history should contain original handler"
#     assert original_python_handler is sys.__excepthook__, "Original handler should be python builtin one"
#     assert sys.excepthook is not original_python_handler, "The except handler should not be the original one anymore"
#     assert sys.excepthook.__wrapped__ is mock_handler_1, "The current except handler should be a wrapper around our callback"

#     first_handler_wrapper = sys.excepthook
#     previous_handler = register_signals_handler(mock_handler_2)
#     assert previous_handler == first_handler_wrapper, "The previous handler should be the wrapper around our first callback"

#     assert SIGNAL_HANDLERS_HISTORY == [original_python_handler, first_handler_wrapper], "The history should now contains both the original python handler and the wrapper around our first callback"
#     assert sys.excepthook is not first_handler_wrapper, "The wrapper around our first callback should not be the current except handler"
#     assert sys.excepthook.__wrapped__ is mock_handler_2, "The current except handler should be the wrapper around our second callback"

#     restore_previous_exception_handler()

#     assert SIGNAL_HANDLERS_HISTORY == [original_python_handler], "History should have been restored to its previous state"
#     assert sys.excepthook is first_handler_wrapper, "Except handler should have been restored to it's previous value"

#     restore_previous_except_handler()

#     assert not SIGNAL_HANDLERS_HISTORY, "History should be empty"
#     assert sys.excepthook is original_python_handler, "Current except handler should be the original one"

#     def register_signal_handler(
#         handler: Callable[[signal.Signals, FrameType, Optional[SignalHandlerType]], bool],
#         signals: Iterable[SignalType],
#     ) -> Mapping[signal.Signals, SignalHandlerType]: pass
