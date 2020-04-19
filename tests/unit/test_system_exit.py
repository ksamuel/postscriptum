import sys

from unittest.mock import Mock

import pytest

from postscriptum.system_exit import catch_system_exit
from postscriptum.exceptions import PostScriptumExit


def catcher(exception_type, exception_value, traceback):
    pass


def test_decorator():

    on_enter = Mock()
    on_exit = Mock(spec=catcher)
    on_system_exit = Mock(spec=catcher)

    @catch_system_exit(on_system_exit, on_enter, on_exit)
    def _():
        sys.exit(0)

    with pytest.raises(SystemExit):
        _()

    on_enter.assert_called_once()

    (exception_class, exception, traceback), kwargs = on_system_exit.call_args
    assert isinstance(exception, exception_class), "We should have info on exception"
    assert isinstance(exception, SystemExit), "Exception is SystemExit"

    @catch_system_exit(on_system_exit, on_enter, on_exit, raise_again=False)
    def _():
        sys.exit(0)

    _()


def test_context_manager():

    on_enter = Mock()
    on_exit = Mock(spec=catcher)
    on_system_exit = Mock(spec=catcher)

    with catch_system_exit(on_system_exit, on_enter, on_exit, raise_again=False):
        raise sys.exit(0)

    on_enter.assert_called_once()

    (exception_class, exception, traceback), kwargs = on_system_exit.call_args
    assert isinstance(exception, exception_class), "We should have info on exception"
    assert isinstance(exception, SystemExit), "Exception is SystemExit"

    with catch_system_exit(on_system_exit, on_enter, on_exit, raise_again=False):
        raise sys.exit(0)

    with pytest.raises(PostScriptumExit):

        with catch_system_exit(on_system_exit, on_enter, on_exit):
            raise PostScriptumExit(0)
