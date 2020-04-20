
import sys
import time

from postscriptum import PubSub

ps = PubSub()


@ps.on_terminate()
def _(event):  # type: ignore
    print("terminated")


@ps.on_crash() # type: ignore
def _(event):
    print("crashed")


@ps.on_quit() # type: ignore
def _(event):
    print("quitted")


@ps.on_finish() # type: ignore
def _(event):
    print("finished")


ps.start()

action = (sys.argv[1:] + ["finish"])[0]
if action == "quit":
    sys.exit(1)
if action == "crash":
    print(sys.excepthook)
    1 / 0

for x in range(100):
    time.sleep(0.1)
