import signal

from unittest.mock import Mock

from signal import Signals

import pytest

from postscriptum.utils import IS_UNIX, IS_WINDOWS
from postscriptum.signals import (
    signals_from_names,
    SIGNAL_HANDLERS_HISTORY,
    register_signals_handler,
    restore_previous_signals_handlers,
)


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows only test")
def test_signals_from_names_windows():

    signals = list(signals_from_names(("SIGABRT", "SIGBREAK", "SIGTERM")))
    assert signals == [Signals.SIGABRT, Signals.SIGBREAK]


@pytest.mark.skipif(not IS_UNIX, reason="Unix only test")
def test_signals_from_names_unix():

    signals = list(signals_from_names(("SIGABRT", "SIGBREAK", "SIGTERM")))
    assert signals == [Signals.SIGABRT, Signals.SIGTERM]

    signals = list(signals_from_names((Signals.SIGABRT, "SIGBREAK", "SIGTERM")))
    assert signals == [Signals.SIGABRT, Signals.SIGTERM]


def test_register_and_restore_signal_handlers():

    assert not SIGNAL_HANDLERS_HISTORY

    mock_handler_1 = Mock()
    mock_handler_2 = Mock()

    sigart_default_handler = signal.getsignal(signal.SIGABRT)
    original_python_handlers = register_signals_handler(mock_handler_1, ["SIGABRT"])

    (sig, original_handler), *_ = original_python_handlers.items()
    assert SIGNAL_HANDLERS_HISTORY == {
        sig: [original_handler]
    }, "handler history should contain original handler"
    assert (
        original_handler is sigart_default_handler
    ), "Original handler should be python builtin one"
    assert (
        signal.getsignal(signal.SIGABRT) is not original_handler
    ), "The signal handler should not be the original one anymore"
    assert (
        signal.getsignal(signal.SIGABRT).__wrapped__ is mock_handler_1
    ), "The current signal handler should be a wrapper around our callback"

    first_handler_wrapper = signal.getsignal(signal.SIGABRT)
    previous_handlers = register_signals_handler(mock_handler_2, ["SIGABRT"])
    (sig, prev_handler), *_ = previous_handlers.items()
    assert (
        prev_handler == first_handler_wrapper
    ), "The previous handler should be the wrapper around our first callback"

    assert SIGNAL_HANDLERS_HISTORY == {
        sig: [original_handler, first_handler_wrapper]
    }, "The history should now contains both the original python handler and the wrapper around our first callback"
    assert (
        signal.getsignal(signal.SIGABRT) is not first_handler_wrapper
    ), "The wrapper around our first callback should not be the current signal handler"
    assert (
        signal.getsignal(signal.SIGABRT).__wrapped__ is mock_handler_2
    ), "The current signal handler should be the wrapper around our second callback"

    restore_previous_signals_handlers(["SIGABRT"])

    assert SIGNAL_HANDLERS_HISTORY == {
        sig: [original_handler]
    }, "History should have been restored to its previous state"
    assert (
        signal.getsignal(signal.SIGABRT) is first_handler_wrapper
    ), "Except handler should have been restored to it's previous value"

    restore_previous_signals_handlers(["SIGABRT"])

    assert not SIGNAL_HANDLERS_HISTORY, "History should be empty"
    assert (
        signal.getsignal(signal.SIGABRT) is original_handler
    ), "Current signal handler should be the original one"


@pytest.mark.skipif(not IS_UNIX, reason="Unix only test")
def test_register_and_restore_several_signal_handlers():

    assert not SIGNAL_HANDLERS_HISTORY

    handler = Mock()

    sigart_default_handler = signal.getsignal(signal.SIGABRT)
    sigint_default_handler = signal.getsignal(signal.SIGINT)
    original_python_handlers = register_signals_handler(
        handler, [signal.SIGABRT, "SIGINT"]
    )

    (
        (sigart, original_sigart_handler),
        (sigint, original_sigint_handler),
    ) = original_python_handlers.items()
    assert (
        SIGNAL_HANDLERS_HISTORY
        == {sigart: [original_sigart_handler], sigint: [original_sigint_handler],}
        == {sigart: [sigart_default_handler], sigint: [sigint_default_handler],}
    ), "handler history should contain original handlers"

    assert (
        signal.getsignal(signal.SIGABRT).__wrapped__ is handler
    ), "The current signal handler should be a wrapper around our callback"
    assert (
        signal.getsignal(signal.SIGINT).__wrapped__ is handler
    ), "The current signal handler should be a wrapper around our callback"

    restore_previous_signals_handlers(["SIGABRT", signal.SIGINT])

    assert not SIGNAL_HANDLERS_HISTORY, "History should be empty"

    with pytest.raises(IndexError):
        restore_previous_signals_handlers(["SIGABRT", signal.SIGINT])

    assert (
        signal.getsignal(signal.SIGABRT) is original_sigart_handler
    ), "Current signal handler should be the original one"
    assert (
        signal.getsignal(signal.SIGINT) is original_sigint_handler
    ), "Current signal handler should be the original one"

    original_python_handlers = register_signals_handler(
        handler, [signal.SIGABRT, "SIGINT"]
    )
    restore_previous_signals_handlers([signal.SIGINT])
    assert (
        signal.getsignal(signal.SIGINT) is original_sigint_handler
    ), "Current signal handler should be the original one"
    assert (
        signal.getsignal(signal.SIGABRT).__wrapped__ is handler
    ), "The current signal handler should be a wrapper around our callback"
    assert SIGNAL_HANDLERS_HISTORY == {signal.SIGABRT: [original_sigart_handler]}


def test_register_and_restore_signal_handler_with_call():

    mock_handler_1 = Mock()
    mock_handler_2 = Mock()
    fake_frame = Mock()

    original_python_handlers = register_signals_handler(mock_handler_1, ["SIGABRT"])
    previous_handlers = register_signals_handler(mock_handler_2, ["SIGABRT"])

    signal.getsignal(signal.SIGABRT)(signal.SIGABRT, fake_frame)

    restore_previous_signals_handlers(["SIGABRT"])

    signal.getsignal(signal.SIGABRT)(signal.SIGABRT, fake_frame)

    restore_previous_signals_handlers(["SIGABRT"])

    mock_handler_1.assert_called_once_with(
        signal.SIGABRT, fake_frame, original_python_handlers[signal.SIGABRT]
    )

    mock_handler_2.assert_called_once_with(
        signal.SIGABRT, fake_frame, previous_handlers[signal.SIGABRT]
    )
