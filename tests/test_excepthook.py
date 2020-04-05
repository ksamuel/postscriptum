
import sys
import traceback

from unittest.mock import Mock, patch, call

from signal import Signals

import pytest

from postscriptum.excepthook import EXCEPTION_HANDLERS_HISTORY, register_exception_handler, restore_previous_exception_handler


def test_register_and_restore_except_handler():

    assert not EXCEPTION_HANDLERS_HISTORY

    mock_handler_1 = Mock()
    mock_handler_2 = Mock()

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


def test_register_and_restore_except_handler_with_call():

    mock_handler_1 = Mock()
    mock_handler_2 = Mock()
    fake_exception = Exception()
    fake_traceback = traceback.format_list([('foo.py', 3, '<module>', 'foo.bar()')])

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
