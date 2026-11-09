# flake8: noqa
"""Compatibility re-exports for :mod:`jllabeling.core.io`.

The implementation lives in the headless core package.  The standard-library
imports stay as module attributes because existing callers and tests patch
``_io.os`` / ``_io.time`` / ``_io.shutil``.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import time

from jllabeling.core.io import (
    copy_file_atomic,
    io_open,
    load_json,
    safe_replace,
    save_json,
    save_text,
)
