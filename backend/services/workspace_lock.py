import atexit
import json
import os
import time


class WorkspaceInUseError(RuntimeError):
    """工作区已由另一个 Sharp GUI 服务实例占用。"""


class WorkspaceInstanceLock:
    """持有工作区级进程锁，防止多个服务实例相互清理运行时文件。"""

    LOCK_FILENAME = ".sharp-gui.lock"

    def __init__(self, workspace_folder):
        self.workspace_folder = os.path.abspath(workspace_folder)
        self.lock_path = os.path.join(self.workspace_folder, self.LOCK_FILENAME)
        self._handle = None
        self._atexit_registered = False

    def acquire(self):
        if self._handle is not None:
            return

        os.makedirs(self.workspace_folder, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT)
        handle = os.fdopen(descriptor, "r+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()

            handle.seek(0)
            self._lock_handle(handle)
        except OSError as exc:
            owner = self._read_owner_details(handle)
            handle.close()
            owner_hint = f" ({owner})" if owner else ""
            raise WorkspaceInUseError(
                f"Workspace is already in use by another Sharp GUI service{owner_hint}: "
                f"{self.workspace_folder}"
            ) from exc

        self._handle = handle
        try:
            self._write_owner_details()
        except Exception:
            self.release()
            raise
        if not self._atexit_registered:
            atexit.register(self.release)
            self._atexit_registered = True

    def release(self):
        handle = self._handle
        if handle is None:
            return

        self._handle = None
        try:
            handle.seek(0)
            self._unlock_handle(handle)
        except OSError:
            pass
        finally:
            handle.close()

    def _write_owner_details(self):
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "started_at": time.time(),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
        self._handle.seek(1)
        self._handle.write(payload)
        self._handle.truncate()
        self._handle.flush()

    @staticmethod
    def _read_owner_details(handle):
        try:
            handle.seek(1)
            payload = json.loads(handle.read().decode("ascii"))
            pid = payload.get("pid")
            return f"PID {pid}" if isinstance(pid, int) else ""
        except (AttributeError, OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return ""

    @staticmethod
    def _lock_handle(handle):
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_handle(handle):
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
