import os
import sys

from backend import server


def test_windows_supervisor_restarts_only_for_the_reserved_exit_code(monkeypatch):
    calls = []
    exit_codes = iter([server.WINDOWS_RESTART_EXIT_CODE, 0])

    def run_child(command, *, env, cwd):
        calls.append({"command": command, "env": env, "cwd": cwd})
        return next(exit_codes)

    monkeypatch.setattr(server.subprocess, "call", run_child)

    assert server.run_windows_server_supervisor(["app.py", "--verbose"]) == 0
    assert len(calls) == 2
    assert calls[0]["command"] == [sys.executable, "app.py", "--verbose"]
    assert calls[0]["env"][server.WINDOWS_SERVER_CHILD_ENV] == "1"
    assert calls[0]["cwd"] == os.getcwd()


def test_windows_supervisor_relaunches_a_real_child_process(tmp_path):
    marker = tmp_path / "restart-count.txt"
    worker = tmp_path / "restart-worker.py"
    worker.write_text(
        "import pathlib\n"
        "import sys\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "count = int(marker.read_text() if marker.exists() else '0') + 1\n"
        "marker.write_text(str(count))\n"
        f"raise SystemExit({server.WINDOWS_RESTART_EXIT_CODE} if count == 1 else 0)\n",
        encoding="utf-8",
    )

    assert server.run_windows_server_supervisor([str(worker)]) == 0
    assert marker.read_text(encoding="utf-8") == "2"


def test_supervised_windows_restart_uses_exit_code_instead_of_exec(monkeypatch):
    exit_calls = []
    monkeypatch.setattr(server, "_is_windows_supervised_child", lambda: True)
    monkeypatch.setattr(os, "_exit", lambda code: exit_calls.append(code))
    monkeypatch.setattr(server, "_exec_current_process", lambda: exit_calls.append("exec"))

    server._restart_current_process()

    assert exit_calls == [server.WINDOWS_RESTART_EXIT_CODE]


def test_exec_current_process_scrubs_werkzeug_state_without_closing_fds(monkeypatch):
    exec_call = {}

    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    monkeypatch.setenv("WERKZEUG_SERVER_FD", "42")
    monkeypatch.setattr(os, "set_inheritable", lambda fd, inheritable: exec_call.update({
        "fd": fd,
        "inheritable": inheritable,
    }))
    monkeypatch.setattr(os, "closerange", lambda *_args: exec_call.update({"closed": True}))

    def fail_exec(executable, argv, env):
        exec_call.update({"executable": executable, "argv": argv, "env": env})
        raise OSError("restart failed")

    monkeypatch.setattr(os, "execve", fail_exec)

    assert server._exec_current_process() is False
    assert exec_call["fd"] == 42
    assert exec_call["inheritable"] is False
    assert "closed" not in exec_call
    assert exec_call["executable"] == sys.executable
    assert exec_call["argv"] == [sys.executable] + sys.argv
    assert "WERKZEUG_RUN_MAIN" not in exec_call["env"]
    assert "WERKZEUG_SERVER_FD" not in exec_call["env"]
