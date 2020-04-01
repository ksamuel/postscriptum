Goodbye: an intuitive and unified API to run code when Python exit
===================================================================

.. warning::
    While the code is considered functional and I used it in my projects,
    the API is not complete and may change until we reach 1.0.

Goodbye wraps atexit.register, sys.excepthook and signal.signal to lets you do:

::

    import goodbye
    watch = goodbye.setup() # do this before creating a thread or a process

    @watch.on_finish() # don't forget the parenthesis !
    def _(context):
        print("When the program finish, no matter the reason.")

    @watch.on_terminate()
    def _(context):  # context contains the signal that lead to termination
        print("When the user terminate the program. E.G: Ctrl + C, kill -9, etc.")

    @watch.on_crash()
    def _(context): # context contains the exception and traceback
        print("When there is an unhandled exception")

All those functions will be called automatically at the proper moment. The handler for on_finish() will be called even if another handler has been called.

If the same function is used for several events:

::

    @watch.on_finish()
    @watch.on_terminate()
    def t(context):
        print('woot!')

It will be called only once.

If several functions are used as handlers for the same event:

::

    @watch.on_terminate()
    def _(context):
        print('one!')

    @watch.on_terminate()
    def _(context):
        print('two!')

The two functions will be called. Hooks from code not using goodbye will be preserved by default for exceptions and atexit.  Hooks from code not using goodbye for signals are replaced. They can be restored using watch.restore_hooks().

You can also capture sys.exit() and manual raise of SystemExit:

::

    @watch.on_quit()
    def _(context):  # context contains the exit code
        print('Why me ?')

BUT for this you MUST use the watcher as a decorator:

::

    @watch() # parenthesis !
    def main():
        do_stuff()

    main()

Or as a context manager:

::

    with watch: # NO parenthesis !
        do_stuff()


The context is a dictionary that can contain:

    For on_crash handlers:

        - **exception_type**: the class of the exception that lead to the crash
        - **exception_value**: the value of the exception that lead to the crash
        - **exception_traceback**: the traceback at the moment of the crash
        - **previous_exception_hook**: the callable that was the exception hook before we called setup()

    For on_terminate handlers:

        - **signal**: the number representing the signal that was sent to terminate the program
        - **signal_frame**: the frame state at the moment the signal arrived
        - **previous_signal_hook**: the signal handler that was set before we called setup()
        - **recommended_exit_code**: the polite exit code to use when exiting after this signal

    For on_quit_handlers:

        - **exit_code**: the code passed to SystemExit/sys.exit.

    on_finish handlers context is empty.

Currently, goodbye does not provide a hook for

- sys.unraisablehook
- exception occuring in other threads (threading.excepthook from 3.8 will allow us to do that later)
- unhandled exception errors in unawaited asyncio (not sure we should do something though)

.. warning::
    You must be very careful about the code you put in handlers. If you mess in there,
    it may give you no error message!

    Test your function without being a hook, then hook it up.


Install
--------

It's on pypi::

    pip install goodbye



*Gotchas (in case you wanted to know)
---------------------------------------

Python has 3 very different API to deal with exiting, and they all have their challenge.

- atexit is always called, weither python exited cleanly or not, which can lead do duplicated calls. Except if you get a SIGTERM signal. And you don't have any information on the cause of the exit.
- To you capture terminating signals, you need to know which ones (they differ depending of the OS), once you do the program will not exit unless you call sys.exit(). However, there is no automatic way to react to sys.exit(). And no way to distinguish SystemExit from sys.exit() and from a signal.
- excepthook are calls on exceptions, but setting it leads to hard to debug errors, if you don't call the previous hook properly.

Goodbye doesn't deal with the last goatchas yet: signals are caught by childs and passed to the main threads, but not exception.
