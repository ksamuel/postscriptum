
import sys

from unittest.mock import Mock

import pytest

from postscriptum.system_exit import catch_system_exit
from postscriptum.exceptions import ExitFromSignal

def catcher(exception_type, exception_value, traceback):
    pass


def test_decorator():

    mock = Mock(spec=catcher)

    @catch_system_exit(mock)
    def _():
        sys.exit(0)

    with pytest.raises(SystemExit):
        _()

    (exception_class, exception, traceback), kwargs = mock.call_args
    assert isinstance(exception, exception_class), "We should have info on exception"
    assert isinstance(exception, SystemExit), "Exception is SystemExit"

    @catch_system_exit(mock, raise_again=False)
    def _():
        sys.exit(0)

    _()


def test_context_manager():

    mock = Mock(spec=catcher)

    with catch_system_exit(mock, raise_again=False):
        raise sys.exit(0)

    (exception_class, exception, traceback), kwargs = mock.call_args
    assert isinstance(exception, exception_class), "We should have info on exception"
    assert isinstance(exception, SystemExit), "Exception is SystemExit"

    with catch_system_exit(mock, raise_again=False):
        raise sys.exit(0)

    with pytest.raises(ExitFromSignal):

        with catch_system_exit(mock):
            raise ExitFromSignal(0)
