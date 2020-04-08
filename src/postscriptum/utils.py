import sys

is_windows = sys.platform.startswith("win")
is_unix = any(sys.platform.startswith(n) for n in ("linux", "freebsd", "darwin"))
