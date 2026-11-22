import subprocess

import pytest

from backend.services import folder_picker


@pytest.fixture
def windows_picker(monkeypatch):
    monkeypatch.setattr(folder_picker.platform, "system", lambda: "Windows")
    monkeypatch.setattr(folder_picker.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)


def test_select_folder_preserves_unicode_and_passes_dialog_data_as_arguments(client, monkeypatch, tmp_path, windows_picker):
    directory = tmp_path / "照片 ' 目录"
    directory.mkdir()
    title = '选择 "相册" 目录'

    def run(command, **options):
        assert command[:5] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-Command"]
        assert title not in command[-1] and str(directory) not in command[-1]
        assert options["env"]["SHARP_PICKER_TITLE"] == title
        assert options["env"]["SHARP_PICKER_INITIAL_DIR"] == str(directory)
        assert options["encoding"] == "utf-8"
        return subprocess.CompletedProcess(command, 0, f"{directory}\r\n", "")

    monkeypatch.setattr(folder_picker.subprocess, "run", run)
    response = client.post("/api/browse-folder", json={"title": title, "initial_dir": str(directory)})
    assert response.status_code == 200
    assert response.json == {"success": True, "path": str(directory)}


def test_folder_picker_rejects_overlapping_requests_and_reports_cancel(monkeypatch, tmp_path, windows_picker):
    def run(command, **options):
        result, status = folder_picker.browse_folder_native("Second attempt", str(tmp_path))
        assert status == 409
        assert result["code"] == "folderPickerBusy"
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(folder_picker.subprocess, "run", run)
    for _ in range(2):
        result, status = folder_picker.browse_folder_native("Select folder", str(tmp_path))
        assert status == 200
        assert result == {"success": False, "cancelled": True}


def test_folder_picker_timeout_is_recoverable(monkeypatch, tmp_path, windows_picker):
    def run(command, **options):
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(folder_picker.subprocess, "run", run)
    for _ in range(2):
        result, status = folder_picker.browse_folder_native("Select folder", str(tmp_path))
        assert status == 504
        assert result["code"] == "folderPickerTimeout"
