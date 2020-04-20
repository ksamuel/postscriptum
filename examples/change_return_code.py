"""
Sometime you use underlying code that exits outside of your control, and
doesn't use the exit code you wish.

This script demonsrates how to change the exit code on the fly.
"""


import sys

from postscriptum import PubSub


ps = PubSub()


@ps.on_quit()
def _(event):  # we can just use a throwaway name for the handler

    # The event is a dictionary, and contains, among other things,
    # a function to quit the program using the exit code you wish.
    # DO NOT use system.exit() here.
    event["exit"](42)


with ps():  # Starts watching for events to react to

    # Here just put the code of your app.
    sys.exit(0)
