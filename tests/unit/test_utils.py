
import sys
import traceback

from postscriptum.utils import format_stacktrace

def test_format_stacktrace():

    try:
        1 / 0
    except:
        stacktrace = format_stacktrace(*sys.exc_info())

    expected_stack_trace = (
        'Traceback (most recent call last):\n\n'
        f'  File "{__file__}", line 10, in test_format_stacktrace\n'
        '    1 / 0\n\n'
        'ZeroDivisionError: division by zero\n'
    )

    assert stacktrace == expected_stack_trace
