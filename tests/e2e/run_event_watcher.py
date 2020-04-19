import sys
import time

from postscriptum import EventWatcher

watch = EventWatcher()


@watch.on_terminate()
def _(context):  # type: ignore
    print("terminated")


@watch.on_crash()
def _(context):  # type: ignore
    print("crashed")


@watch.on_quit()
def _(context):  # type: ignore
    print("quitted")


@watch.on_finish()
def _(context):  # type: ignore
    print("finished")


watch.start()

action = (sys.argv[1:] + ["finish"])[0]
if action == "quit":
    sys.exit(1)
if action == "crash":
    print(sys.excepthook)
    1 / 0

for x in range(100):
    time.sleep(0.1)
