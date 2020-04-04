
import sys
import traceback

from unittest.mock import Mock, patch, call

from signal import Signals

import pytest

from postscriptum.register import signals_from_names, EXCEPT_HOOKS_HISTORY, register_except_hook, restore_previous_except_hook


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


def test_register_and_restore_except_hook():

    assert not EXCEPT_HOOKS_HISTORY

    mock_handler_1 = Mock()
    mock_handler_2 = Mock()
    fake_exception = Exception()
    fake_traceback = traceback.format_list([('foo.py', 3, '<module>', 'foo.bar()')])

    original_python_hook = register_except_hook(mock_handler_1)

    assert EXCEPT_HOOKS_HISTORY == [original_python_hook], "Hook history should contain original hook"
    assert original_python_hook is sys.__excepthook__, "Original hook should be python builtin one"
    assert sys.excepthook is not original_python_hook, "The except hook should not be the original one anymore"
    assert sys.excepthook.__wrapped__ is mock_handler_1, "The current except hook should be a wrapper around our callback"

    first_hook_wrapper = sys.excepthook
    previous_hook = register_except_hook(mock_handler_2)
    assert previous_hook == first_hook_wrapper, "The previous hook should be the wrapper around our first callback"

    assert EXCEPT_HOOKS_HISTORY == [original_python_hook, first_hook_wrapper], "The history should now contains both the original python hook and the wrapper around our first callback"
    assert sys.excepthook is not first_hook_wrapper, "The wrapper around our first callback should not be the current except hook"
    assert sys.excepthook.__wrapped__ is mock_handler_2, "The current except hook should be the wrapper around our second callback"

    restore_previous_except_hook()

    assert EXCEPT_HOOKS_HISTORY == [original_python_hook], "History should have been restored to its previous state"
    assert sys.excepthook is first_hook_wrapper, "Except hook should have been restored to it's previous value"

    restore_previous_except_hook()

    assert not EXCEPT_HOOKS_HISTORY, "History should be empty"
    assert sys.excepthook is original_python_hook, "Current except hook should be the original one"

    with patch('sys.excepthook') as original_python_hook:

        original_python_hook = register_except_hook(mock_handler_1)

        wrapper_for_mock_handler_1 = register_except_hook(mock_handler_2)

        sys.excepthook(Exception, fake_exception, fake_traceback)

        restore_previous_except_hook()

        sys.excepthook(Exception, fake_exception, fake_traceback)

        restore_previous_except_hook()

        assert original_python_hook.mock_calls == [
            call(Exception, fake_exception, fake_traceback),
            call(Exception, fake_exception, fake_traceback),
        ], "Original except hook should have been called every time"

        assert mock_handler_1.mock_calls == [
            call(Exception, fake_exception, fake_traceback, original_python_hook),
            call(Exception, fake_exception, fake_traceback, original_python_hook),
        ], "First hook replacement should have been called every time, with the original hook as param"

        assert mock_handler_2.mock_calls == [
            call(Exception, fake_exception, fake_traceback, wrapper_for_mock_handler_1),
        ], "Second hook replacement should have been called one time, with the first hook replacement as param"


    with patch('sys.excepthook') as original_python_hook:

        original_python_hook = register_except_hook(mock_handler_1, call_previous_hook=False)

        sys.excepthook(Exception, fake_exception, fake_traceback)

        restore_previous_except_hook()

        assert not original_python_hook.call_count, "Original hook should not have been called"
