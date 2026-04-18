from __future__ import annotations

import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - windows is the main local target
    import fcntl


class PollingLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True

        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+", encoding="utf-8")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write("0")
                handle.flush()

            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - windows is the main local target
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            handle.seek(0)
            handle.write(str(os.getpid()).ljust(16))
            handle.flush()
            self._handle = handle
            return True
        except OSError:
            handle.close()
            return False

    def release(self) -> None:
        if self._handle is None:
            return

        try:
            self._handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - windows is the main local target
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                self._handle.close()
            finally:
                self._handle = None
