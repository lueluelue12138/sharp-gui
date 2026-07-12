import os
import socket
import subprocess
import sys
import threading
import time

from backend import runtime
from backend.config import coerce_bool, get_access_control_config
from backend.services.workspace_lock import WorkspaceInUseError

WINDOWS_RESTART_EXIT_CODE = 75
WINDOWS_SERVER_CHILD_ENV = "SHARP_WINDOWS_SERVER_CHILD"


def get_local_ip():
    """通过 hostname 解析获取所有本机 IP，返回第一个私有网络地址。"""
    try:
        hostname = socket.gethostname()
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
        ips = list(set(ip[4][0] for ip in addrs))

        for ip in ips:
            if ip.startswith("127."):
                continue
            if ip.startswith("28.0.") or ip.startswith("172.17."):
                continue
            if ip.startswith("192.168.") or ip.startswith("10."):
                return ip
            if ip.startswith("172."):
                parts = ip.split(".")
                if 16 <= int(parts[1]) <= 31:
                    return ip

        for ip in ips:
            if not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def _exec_current_process():
    """以干净的 Werkzeug 环境替换当前进程，失败时保持现有服务可用。"""
    exec_env = os.environ.copy()
    werkzeug_fd = exec_env.pop("WERKZEUG_SERVER_FD", None)
    exec_env.pop("WERKZEUG_RUN_MAIN", None)

    if werkzeug_fd is not None:
        try:
            os.set_inheritable(int(werkzeug_fd), False)
        except (OSError, TypeError, ValueError):
            pass

    try:
        os.execve(sys.executable, [sys.executable] + sys.argv, exec_env)
    except OSError as exc:
        print(f"❌ Server restart failed: {exc}", file=sys.stderr, flush=True)
        return False

    return True


def _is_windows_supervised_child():
    return os.name == "nt" and os.environ.get(WINDOWS_SERVER_CHILD_ENV) == "1"


def _restart_current_process():
    if _is_windows_supervised_child():
        return os._exit(WINDOWS_RESTART_EXIT_CODE)
    return _exec_current_process()


def run_windows_server_supervisor(argv):
    """在 Windows 上监督服务子进程，并用专用退出码完成可靠重启。"""
    child_env = os.environ.copy()
    child_env[WINDOWS_SERVER_CHILD_ENV] = "1"
    child_command = [sys.executable] + list(argv)

    while True:
        exit_code = subprocess.call(child_command, env=child_env, cwd=os.getcwd())
        if exit_code != WINDOWS_RESTART_EXIT_CODE:
            return exit_code
        print("🔄 Server stopped; starting a fresh process...", flush=True)


def restart_process_later():
    def do_restart():
        time.sleep(1)
        print("🔄 Restarting server...", flush=True)
        _restart_current_process()

    threading.Thread(target=do_restart, daemon=True).start()


def run_server(app):
    """Run the Flask service and explicitly start background workers."""
    runtime.configure_werkzeug_logging()
    task_manager = app.config["TASK_MANAGER"]
    is_serving_process = not runtime.SHARP_DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if is_serving_process:
        try:
            task_manager.start_workers()
        except WorkspaceInUseError as exc:
            print(f"❌ {exc}")
            runtime.log("ERROR", str(exc))
            raise SystemExit(1) from exc

    local_ip = os.environ.get("SHARP_LAN_IP") or get_local_ip()
    cert_file = os.path.join(runtime.BASE_DIR, "cert.pem")
    key_file = os.path.join(runtime.BASE_DIR, "key.pem")

    if os.path.exists(cert_file) and os.path.exists(key_file):
        protocol = "https"
        ssl_ctx = (cert_file, key_file)
    else:
        protocol = "http"
        ssl_ctx = None

    startup_access_config = get_access_control_config(persist_missing=False)
    lan_bind_enabled = coerce_bool(startup_access_config.get("lan_bind_enabled"), True)
    bind_host = os.environ.get("SHARP_BIND_HOST", "").strip() or (
        "0.0.0.0" if lan_bind_enabled else "127.0.0.1"
    )

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not runtime.SHARP_DEBUG:
        print(f" * Running on {protocol}://127.0.0.1:5050")
        if lan_bind_enabled and bind_host != "127.0.0.1":
            print(f" * Running on {protocol}://{local_ip}:5050")
        else:
            print(" * 仅本机访问（局域网绑定已关闭）/ Localhost only (LAN bind disabled)")
        if protocol == "http":
            print(" * ⚠️ 当前为 HTTP，访问码与会话将明文传输，局域网共享建议先生成证书启用 HTTPS")
            print("   / HTTP mode: access code and session travel unencrypted; enable HTTPS for LAN sharing")
        if bind_host == "0.0.0.0":
            print(" * ⚠️ 若在本机前置反向代理（nginx/frp 等），所有请求会被判为 owner；")
            print("   如需强制访问码，请在设置中关闭“本机免登录”(allow_localhost_bypass)")
            print("   / Behind a local reverse proxy every client is treated as owner; disable localhost bypass to force the access code")
        print("Press CTRL+C to quit")
        runtime.print_runtime_diagnostics(protocol, local_ip)

    run_kwargs = {
        "port": 5050,
        "host": bind_host,
        "debug": runtime.SHARP_DEBUG,
        "use_debugger": runtime.SHARP_DEBUG,
        "use_reloader": runtime.SHARP_DEBUG,
    }
    if ssl_ctx:
        run_kwargs["ssl_context"] = ssl_ctx
    try:
        app.run(**run_kwargs)
    finally:
        if is_serving_process:
            task_manager.release_workspace_lock()
