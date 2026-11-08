"""Use UTF-8 for service pipes, including the frozen Windows backend."""

import os
import sys


def configure_standard_streams():
    # Also applies to Python converter processes launched by the backend.
    os.environ["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    os.environ["PYTHONUTF8"] = "1"
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


configure_standard_streams()
