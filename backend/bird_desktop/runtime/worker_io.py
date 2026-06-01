from __future__ import annotations

import errno
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO


class WorkerLogRedirect:
    def __init__(self, path: str | None):
        self.path = Path(path) if path else None
        self._saved_stdout: int | None = None
        self._saved_stderr: int | None = None
        self._log_handle = None


    def __enter__(self):
        if self.path is None:
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._saved_stdout = os.dup(1)
        self._saved_stderr = os.dup(2)
        self._log_handle = self.path.open("a", encoding="utf-8", errors="replace")
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(self._log_handle.fileno(), 1)
        os.dup2(self._log_handle.fileno(), 2)
        return self


    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self.path is None or self._saved_stdout is None or self._saved_stderr is None:
            return

        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(self._saved_stdout, 1)
        os.dup2(self._saved_stderr, 2)
        os.close(self._saved_stdout)
        os.close(self._saved_stderr)
        if self._log_handle is not None:
            self._log_handle.close()


class WorkerStatusWriter:
    def __init__(self, stream: TextIO | None = None):
        self._stream = stream or sys.stdout


    def write(self, payload: dict[str, Any]) -> bool:
        try:
            self._stream.write(json.dumps(payload) + "\n")
            self._stream.flush()
            return True
        except BrokenPipeError:
            return False
        except ValueError:
            return False
        except OSError as exc:
            if exc.errno in (errno.EINVAL, errno.EPIPE):
                return False

            raise
