import sys

from subprocess import Popen, PIPE
from pathlib import Path

TEST_SCRIPT = Path(__file__).absolute().parent / "run_except_handler.py"


def test_register():

    process = Popen([sys.executable, TEST_SCRIPT], stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    assert stdout == b"handled\n", "New handler is called"
    assert not stderr, "Previous handler is not called"

    process = Popen(
        [sys.executable, TEST_SCRIPT, "call_previous_handler"], stdout=PIPE, stderr=PIPE
    )
    stdout, stderr = process.communicate()
    assert stdout == b"handled\n", "New handler is called"
    assert b"ZeroDivisionError" in stderr, "Previous handler is called"
