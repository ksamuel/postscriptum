import time

from postscriptum.signals import register_signals_handler


def handler(code, frame, previous_handler):  # pylint: disable-all
    print("handled", flush=True)


original_python_handlers = register_signals_handler(handler, ["SIGINT", "SIGBREAK"])

for x in range(50):
    time.sleep(0.1)
