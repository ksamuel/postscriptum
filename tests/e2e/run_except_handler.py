import sys

from postscriptum.excepthook import register_exception_handler


def handler(type_, exception, traceback, previous_handler):
    print("handled")


raise_again = len(sys.argv[1:])

register_exception_handler(handler, call_previous_handler=raise_again)

1 / 0  # pylint: disable=pointless-statement
