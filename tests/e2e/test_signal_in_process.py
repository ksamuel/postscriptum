import sys
import signal
import asyncio

from pathlib import Path

import pytest

from postscriptum.utils import IS_UNIX, IS_WINDOWS

TEST_SCRIPT = Path(__file__).absolute().parent / "run_signal_handler.py"


@pytest.mark.skipif(not IS_UNIX, reason="Unix only test")
def test_register_on_unix():

    exit_on_sigint = True

    async def main():

        nonlocal exit_on_sigint
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(TEST_SCRIPT), stdout=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.wait_for(proc.stdout.read(1024), timeout=0.1)
            assert False, "Reading should not work"
        except asyncio.TimeoutError:
            # Python 3.6 has a bug (https://github.com/encode/httpx/pull/383)
            # so we need to do this:
            await asyncio.sleep(0)

        proc.send_signal(signal.SIGINT)
        stdout = await proc.stdout.read(1024)
        assert stdout == b"handled\n"

        exit_on_sigint = False

        proc.send_signal(signal.SIGTERM)

    asyncio.get_event_loop().run_until_complete(main())
    assert not exit_on_sigint, "SIGINT handler should not have exited"


@pytest.mark.skipif(not IS_WINDOWS, reason="Unix only test")
def test_register_on_windows():

    exit_on_sigint = True

    async def main():

        nonlocal exit_on_sigint
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(TEST_SCRIPT), stdout=asyncio.subprocess.PIPE
        )

        try:
            await asyncio.wait_for(proc.stdout.read(1024), timeout=0.1)
            assert False, "Reading should not work"
        except asyncio.TimeoutError:
            pass

        proc.send_signal(signal.SIGBREAK)
        stdout = await proc.stdout.read(1024)
        assert stdout == b"handled\n"

        exit_on_sigint = False

        proc.send_signal(signal.SIGTERM)

    asyncio.get_event_loop().run_until_complete(main())
    assert not exit_on_sigint, "SIGINT handler should not have exited"
