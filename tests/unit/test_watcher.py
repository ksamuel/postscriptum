from unittest.mock import patch, Mock

from postscriptum.watcher import EventWatcher


def test_finish_handler():

    watch = EventWatcher()

    finish_handler = Mock()

    watch.finish_handlers.add(finish_handler)
    watch.finish_handlers.add(finish_handler)

    with patch("atexit.register") as mock:
        watch.start()

    mock.assert_called_once_with(watch._call_finish_handlers)

    with patch("atexit.unregister") as mock:
        watch.stop()

    mock.assert_called_once_with(watch._call_finish_handlers)

    watch._call_finish_handlers()

    finish_handler.assert_called_once()
