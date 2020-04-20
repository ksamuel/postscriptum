Postscriptum: an unified API to run code when Python exits
============================================================

.. warning::
    While the code is considered functional and I used it in my projects,
    the API is not complete and may change until we reach 1.0.

Postscriptum wraps ``atexit.register``, ``sys.excepthook`` and ``signal.signal`` to lets you do:

::

    from postscriptum import PubSub
    ps = PubSub() # do this before creating a thread or a process

    @ps.on_finish() # don't forget the parenthesis !
    def _(context):
        print("When the program finishes, no matter the reason.")

    @ps.on_terminate()
    def _(context):  # context contains the signal that lead to termination
        print("When the user terminates the program. E.G: Ctrl + C, kill -9, etc.")

    @ps.on_crash()
    def _(context): # context contains the exception and traceback
        print("When there is an unhandled exception")

    ps.start()

All those functions will be called automatically at the proper moment. The handler for ``on_finish`` will be called even if another handler has been called.

Install
--------

::

    pip install postscriptum


- Coverage: 100%
- Tested: Linux, but should work on Windows and Mac
- Fully typed hint



Why this lib ?
----------------

Python has 3 very different API to deal with exiting, and they all have their challenges:

- **atexit**: the handler is always called, weither python exited cleanly or not, which can lead do duplicated calls. Except if you get a SIGTERM signal when it's silently ignored. Even whell called, it doesn't give any information on the cause of the exit.
- **signal**: to capture terminating signals, you need to know which ones to watch for (and they differ depending of the OS). Normal behavior is to exit, but if you set your handler, the program will not exit unless you call sys.exit(). Finally, you can only have one handler for each signal.
- **sys.excepthool** is called on all exception, but not SystemExit. It also leads to hard to debug errors if you don't call the previous hook properly. And you can have only one handler.

Also, there is no automatic way to react to ``sys.exit()``. And no way to distinguish ``SystemExit`` from ``sys.exit()``, which you need for signals.

Postscriptum doesn't deal with the last goatchas yet:

- signals are caught by childs and passed to the main threads, but not exceptions.
- messing up in your handler may cause you to have no error message at all.
