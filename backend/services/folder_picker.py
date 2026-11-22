import logging
import os
import platform
import subprocess
from threading import Lock


PICKER_TIMEOUT = 120
_picker_lock = Lock()
_logger = logging.getLogger(__name__)
_WINDOWS_PICKER = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
if (-not [Environment]::UserInteractive) { exit 1 }

Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$browser = New-Object System.Windows.Forms.FolderBrowserDialog
try {
    # Give the modal an owner above the browser on the current monitor.
    $owner.StartPosition = 'Manual'
    $area = [System.Windows.Forms.Screen]::FromPoint([System.Windows.Forms.Cursor]::Position).WorkingArea
    $owner.Location = [System.Drawing.Point]::new(
        ($area.Left + ($area.Width - $owner.Width) / 2),
        ($area.Top + ($area.Height - $owner.Height) / 2)
    )
    $owner.ShowInTaskbar = $false
    $owner.Opacity = 0
    $owner.TopMost = $true
    $owner.Show()

    $browser.Description = $env:SHARP_PICKER_TITLE
    $browser.SelectedPath = $env:SHARP_PICKER_INITIAL_DIR
    $browser.ShowNewFolderButton = $true
    if ($browser.ShowDialog($owner) -eq 'OK') {
        [Console]::WriteLine($browser.SelectedPath)
    }
} finally {
    $browser.Dispose()
    $owner.Dispose()
}
"""


def browse_folder_native(title, initial_dir):
    """调用系统原生文件夹选择对话框。"""
    if not _picker_lock.acquire(blocking=False):
        return {
            "success": False,
            "code": "folderPickerBusy",
            "error": "A folder selection window is already open on the host.",
        }, 409
    try:
        return _browse_folder(title, initial_dir)
    finally:
        _picker_lock.release()


def _browse_folder(title, initial_dir):
    if not os.path.isdir(initial_dir):
        initial_dir = os.path.expanduser("~")

    system = platform.system()

    try:
        if system == "Linux":
            try:
                result = subprocess.run(
                    [
                        "zenity",
                        "--file-selection",
                        "--directory",
                        "--title=" + title,
                        "--filename=" + initial_dir + "/",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=PICKER_TIMEOUT,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return {"success": True, "path": result.stdout.strip()}, 200
                if result.returncode == 1:
                    return {"success": False, "cancelled": True}, 200
            except FileNotFoundError:
                try:
                    result = subprocess.run(
                        ["kdialog", "--getexistingdirectory", initial_dir, "--title", title],
                        capture_output=True,
                        text=True,
                        timeout=PICKER_TIMEOUT,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        return {"success": True, "path": result.stdout.strip()}, 200
                    if result.returncode == 1:
                        return {"success": False, "cancelled": True}, 200
                except FileNotFoundError:
                    pass

        elif system == "Darwin":
            script = '''
            on run argv
            tell application "System Events"
                activate
                set folderPath to choose folder with prompt (item 1 of argv) default location (POSIX file (item 2 of argv))
                return POSIX path of folderPath
            end tell
            end run
            '''
            result = subprocess.run(
                ["osascript", "-e", script, title, initial_dir],
                capture_output=True,
                text=True,
                timeout=PICKER_TIMEOUT,
            )
            if result.returncode == 0 and result.stdout.strip():
                return {"success": True, "path": result.stdout.strip().rstrip("/")}, 200
            if result.returncode != 0 and "(-128)" in result.stderr:
                return {"success": False, "cancelled": True}, 200

        elif system == "Windows":
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-Command", _WINDOWS_PICKER],
                env={**os.environ, "SHARP_PICKER_TITLE": title, "SHARP_PICKER_INITIAL_DIR": initial_dir},
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=PICKER_TIMEOUT,
            )
            if result.returncode == 0:
                path = result.stdout.rstrip("\r\n")
                return ({"success": True, "path": path} if path else {"success": False, "cancelled": True}), 200
            _logger.warning("Windows folder picker exited with status %s", result.returncode)

        return {
            "success": False,
            "code": "folderPickerUnavailable",
            "error": "No dialog tool available. Please enter path manually.",
        }, 500

    except subprocess.TimeoutExpired:
        return {"success": False, "code": "folderPickerTimeout", "error": "The folder selection window timed out."}, 504
    except OSError:
        _logger.warning("Could not start the native folder picker", exc_info=True)
        return {
            "success": False,
            "code": "folderPickerUnavailable",
            "error": "Could not open the folder selection window. Please enter the path manually.",
        }, 500
