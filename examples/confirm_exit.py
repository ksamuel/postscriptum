"""
This script demonstrates how to prompt for user confirmation before exiting
when we receive a terminating signal.

We also exit if we receive 2 signals in a raw.

This will work for:

- SIGINT (Ctrl + C or kill -2)
- SIGQUIT (Ctrl + \ or kill -3),: core will also be dumped
- SIGTERM (kill -15)
- SIGBREAK (Ctrl + break on Windows )

SIGKILL cannot be caught.

You can inspect the event if you want to do special things for each
individual signals.
"""


import time

from postscriptum import PubSub


# Normally, PostScriptum automatically exits after receiving
# a terminating signal, but we can tell it we will handle exiting ourself
ps = PubSub(exit_on_terminate=False)


confirmed = False


@ps.on_terminate()
def bye(event):

    global confirmed
    if confirmed:
        # The event is a dictionary and contains, among other things,
        # a function to exit manually.
        event["exit"]()

    confirmed = True

    answer = input("Are you sure you want to exit? [n/Y]")
    if answer.lower().strip() in ("y", "yes"):
        event["exit"]()

    confirmed = False


with ps():  # Starts watching for events to react to

    # Here just put the code of your app.
    print("Press Ctrl + C twice to interrup")
    while True:
        print(".")
        time.sleep(1)
