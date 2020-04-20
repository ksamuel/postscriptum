"""
When an exception is not handled, it cause the program to crash. You cannot
prevent the crash once this happens, but you can run Python code to
help with debugging on cleaning up.

This script demonstrates how to save any stacktrace from an uncaught exception
to a file. It also avoid displaying the stack trace in the terminal, as it
is useful for debugging, but confusing to the end user.

For simplicity, we use open(), but once could use the logging module.
"""


import time
from traceback import format_exception

from postscriptum import PubSub

# By default, postscriptum calls the previous exception handler, which in our
# case is the original one provided by Python itself. It is responsaible for
# printing the stacktrace, so we explicitly ask to not call it.
ps = PubSub(call_previous_exception_handler=False)


@ps.on_crash()
def _(event):  # we can just use a throwaway name for the handler

    with open("crash.log", "a") as f:
        # The event is a dictionary and contains, among other things,
        # a function to get a formatted stack trace as a string
        f.write(event["stacktrace"]())

    print('An error has occured and has been logged in "crash.log"')


with ps():  # Starts watching for events to react to

    # Here just put the code of your app.
    1 / 0
