import pytest

from backend.services import self_update


class RecordingUpdateManager:
    def __init__(self):
        self.calls = []

    def status(self, *, is_owner, server_instance_id):
        self.calls.append(("status", is_owner, server_instance_id))
        return {
            "server_instance_id": server_instance_id,
            "is_owner": is_owner,
            "current": {"display_version": "v1.2.3"},
        }

    def check(self, channel, *, is_owner, server_instance_id):
        self.calls.append(("check", channel, is_owner, server_instance_id))
        return {"result": "checked", "channel": channel}

    def start_apply(self, channel, *, is_owner, server_instance_id):
        self.calls.append(("apply", channel, is_owner, server_instance_id))
        return {"result": "queued", "channel": channel}


def _remote_post(client, path, payload):
    return client.post(
        path,
        json=payload,
        base_url="http://192.168.1.2",
        environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
        headers={
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
            "Forwarded": "for=127.0.0.1",
        },
    )


def test_update_status_and_owner_mutation_routes(client, app):
    manager = RecordingUpdateManager()
    app.config["UPDATE_MANAGER"] = manager
    instance_id = app.config["SERVER_INSTANCE_ID"]

    status = client.get("/api/updates/status")
    checked = client.post("/api/updates/check", json={"channel": "latest"})
    applied = client.post(
        "/api/updates/apply",
        json={"channel": "latest"},
    )

    assert status.status_code == 200
    assert status.get_json()["current"]["display_version"] == "v1.2.3"
    assert checked.status_code == 200
    assert checked.get_json() == {"channel": "latest", "result": "checked"}
    assert applied.status_code == 202
    assert applied.get_json() == {"channel": "latest", "result": "queued"}
    assert manager.calls == [
        ("status", True, instance_id),
        ("check", "latest", True, instance_id),
        ("apply", "latest", True, instance_id),
    ]


def test_remote_client_can_read_status_without_receiving_owner_capability(client, app):
    manager = RecordingUpdateManager()
    app.config["UPDATE_MANAGER"] = manager

    response = client.get(
        "/api/updates/status",
        base_url="http://192.168.1.2",
        environ_overrides={"REMOTE_ADDR": "192.168.1.50"},
    )

    assert response.status_code == 200
    assert response.get_json()["is_owner"] is False
    assert manager.calls == [("status", False, app.config["SERVER_INSTANCE_ID"])]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/updates/check", {"channel": "stable"}),
        ("/api/updates/apply", {"channel": "latest"}),
    ],
)
def test_forwarded_header_spoof_cannot_mutate_or_call_manager(client, app, path, payload):
    manager = RecordingUpdateManager()
    app.config["UPDATE_MANAGER"] = manager

    response = _remote_post(client, path, payload)

    assert response.status_code == 403
    assert response.get_json()["code"] == "OWNER_REQUIRED"
    assert manager.calls == []


@pytest.mark.parametrize(
    ("path", "payload", "expected_code"),
    [
        ("/api/updates/check", {"channel": "preview"}, "update_channel_invalid"),
        (
            "/api/updates/check",
            {"channel": "stable", "url": "https://example.invalid/update"},
            "update_request_invalid",
        ),
        ("/api/updates/check", ["stable"], "update_request_invalid"),
        ("/api/updates/apply", {"channel": "preview"}, "update_channel_invalid"),
        (
            "/api/updates/apply",
            {"channel": "latest", "sha": "a" * 40},
            "update_request_invalid",
        ),
    ],
)
def test_update_routes_reject_invalid_or_client_controlled_targets(
    client,
    app,
    tmp_path,
    path,
    payload,
    expected_code,
):
    def forbidden_resolver():
        raise AssertionError("invalid payload reached update target resolution")

    app.config["UPDATE_MANAGER"] = self_update.SelfUpdateManager(
        base_dir=tmp_path,
        resolver_factory=forbidden_resolver,
    )

    response = client.post(path, json=payload)

    assert response.status_code == 400
    assert response.get_json()["code"] == expected_code
