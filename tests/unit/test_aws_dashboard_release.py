from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_under_test",
    Path(__file__).resolve().parents[2] / "scripts/deployment/aws_dashboard_release.py",
)
assert spec is not None and spec.loader is not None
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def source_archive():
    files = {
        "package.json": b'{"dependencies":{"next":"15.5.29"}}',
        "Dockerfile": b"FROM node:22-alpine AS builder\n",
        "src/lib/portalProxy.ts": b"// Source gateway replaced with reviewed AWS gateway.",
        "public/images/developers/dubai-waterfront-hero.webp": b"fictional image",
        ".env.example": b"TEMPLATE_ONLY=1",
    }
    files.update({f"src/example-{i}.txt": b"fixture" for i in range(101)})
    output = io.BytesIO()
    prefix = "dubai-property-developers-" + release.REVISION + "/"
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        for name, data in files.items():
            item = tarfile.TarInfo(prefix + "apps/dashboard/" + name)
            item.size = len(data)
            bundle.addfile(item, io.BytesIO(data))
        outside = tarfile.TarInfo(prefix + "database/unrelated.txt")
        bundle.addfile(outside)
    return output.getvalue()


class SourceResponse(io.BytesIO):
    def geturl(self):
        return release.URL


def opener_for(data):
    class Opener:
        def open(self, *args, **kwargs):
            return SourceResponse(data)

    return Opener()


def test_source_extracts_only_dashboard_and_preserves_read_only_gateway(tmp_path, monkeypatch):
    archive = source_archive()
    monkeypatch.setattr(release, "ARCHIVE_SHA", release.digest(archive))
    monkeypatch.setattr(release, "build_opener", lambda *args: opener_for(archive))
    context = tmp_path / "dashboard"
    context.mkdir()
    gateway_sha = release.download_source(context)
    gateway = (context / "src/lib/portalProxy.ts").read_bytes()
    assert gateway == release.GATEWAY.encode()
    assert release.digest(gateway) == gateway_sha
    assert b"API changes are not enabled in this AWS preview." in gateway
    assert b"'Authorization':'Bearer '+token" in gateway
    assert json.loads((context / "package.json").read_text())["dependencies"]["next"] == "15.5.29"
    assert (context / "public/images/developers/dubai-waterfront-hero.webp").is_file()
    assert not (context / ".env").exists()
    assert not (tmp_path / "database").exists()


def test_tampered_download_is_rejected_before_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "build_opener", lambda *args: opener_for(b"tampered"))
    with pytest.raises(release.Stop, match="checksum"):
        release.download_source(tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "name,kind", [("../escape", "file"), (".env", "file"), ("src/link", "symlink")]
)
def test_unsafe_archive_members_are_rejected(tmp_path, monkeypatch, name, kind):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        member = tarfile.TarInfo(
            "dubai-property-developers-" + release.REVISION + "/apps/dashboard/" + name
        )
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
        bundle.addfile(member)
    raw = buffer.getvalue()
    monkeypatch.setattr(release, "ARCHIVE_SHA", release.digest(raw))
    monkeypatch.setattr(release, "build_opener", lambda *args: opener_for(raw))
    with pytest.raises(release.Stop, match="archive member"):
        release.download_source(tmp_path)


def test_backup_is_complete_and_excludes_only_transient_locks(tmp_path):
    data = tmp_path / "volume"
    data.mkdir()
    (data / "sessions.json").write_text('{"version":1}')
    (data / "agent-portal.lock").write_text("transient")
    (data / "photos").mkdir()
    (data / "photos/example.jpg").write_bytes(b"fictional image bytes")
    archive = tmp_path / "backup.tar.gz"
    before = release.backup_volume(data, archive)
    assert set(before) == {"sessions.json", "photos/example.jpg"}
    with tarfile.open(archive) as bundle:
        assert bundle.extractfile("data/sessions.json").read() == b'{"version":1}'
        assert "data/agent-portal.lock" not in bundle.getnames()
    assert (data / "agent-portal.lock").is_file()


def test_changed_records_during_backup_are_rejected(tmp_path, monkeypatch):
    data = tmp_path / "volume"
    data.mkdir()
    (data / "record.json").write_text("original")
    actual = release.storage_manifest
    calls = 0

    def changed(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            (path / "record.json").write_text("updated")
        return actual(path)

    monkeypatch.setattr(release, "storage_manifest", changed)
    with pytest.raises(release.Stop, match="changed during"):
        release.backup_volume(data, tmp_path / "backup.tar.gz")
    assert (data / "record.json").read_text() == "updated"


def test_candidate_configuration_is_loopback_only_with_no_secret_in_command(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(release, "docker", lambda *args, **kwargs: calls.append(args) or "")
    env = tmp_path / "private.env"
    env.write_text("TOKEN=fictional-private-value")
    release.create_container(
        "test-candidate", "sha256:test", "test-volume", 13095, env, {"revision": "test"}
    )
    create = calls[0]
    assert "127.0.0.1:13095:3000" in create
    assert "--env-file" in create
    assert "--cap-drop" in create and "ALL" in create
    assert "--security-opt" in create and "no-new-privileges:true" in create
    assert "fictional-private-value" not in repr(calls)
    assert calls[1] == ("network", "connect", release.NETWORK, "test-candidate")


@pytest.fixture
def activation(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "STATE", tmp_path / "state.json")
    env = tmp_path / "runtime-private.env"
    env.write_text("TEST=fixture")
    state = {
        "status": "prepared",
        "runtime_env_sha256": release.digest(env.read_bytes()),
        "candidate_id": "candidate-id",
        "image_id": "sha256:new",
        "original_labels": {},
    }
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        return "sha256:new" if args[:2] == ("image", "inspect") else ""

    monkeypatch.setattr(release, "docker", docker)
    monkeypatch.setattr(release, "unchanged", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        release,
        "inspect",
        lambda name: {"Id": "candidate-id" if name == release.CANDIDATE else "new-id"},
    )
    monkeypatch.setattr(release, "exists", lambda name: False)
    monkeypatch.setattr(release, "validate_live", lambda info: None)
    monkeypatch.setattr(release, "volume_path", lambda name: tmp_path)
    monkeypatch.setattr(
        release, "create_container", lambda *args: calls.append(("create", *args[:3]))
    )
    return state, calls


def test_failed_preflight_never_stops_original(activation, monkeypatch):
    state, calls = activation
    monkeypatch.setattr(
        release,
        "wait_checks",
        lambda *args, **kwargs: (_ for _ in ()).throw(release.Stop("bad candidate")),
    )
    with pytest.raises(release.Stop, match="bad candidate"):
        release.activate(state)
    assert not any(c[0] in {"stop", "rename", "create", "rm"} for c in calls)


def test_changed_private_env_never_stops_original(activation):
    state, calls = activation
    (release.ROOT / "runtime-private.env").write_text("TEST=changed")
    with pytest.raises(release.Stop, match="runtime settings changed"):
        release.activate(state)
    assert calls == []


def test_backup_failure_restarts_original_without_renaming_or_deleting_storage(
    activation, monkeypatch
):
    state, calls = activation
    monkeypatch.setattr(release, "wait_checks", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        release, "backup_volume", lambda *args: (_ for _ in ()).throw(release.Stop("backup failed"))
    )
    with pytest.raises(release.Stop, match="backup failed"):
        release.activate(state)
    assert ("stop", "--time", "30", release.WEB) in calls
    assert ("start", release.WEB) in calls
    assert not any(c[0] in {"rename", "rm", "volume"} for c in calls)
    assert state["status"] == "rolled-back"


def test_failed_new_site_checks_restore_original_container_and_keep_all_volumes(
    activation, monkeypatch
):
    state, calls = activation

    def checks(name, port, **kwargs):
        if name == release.WEB:
            raise release.Stop("website failed")

    monkeypatch.setattr(release, "wait_checks", checks)
    monkeypatch.setattr(release, "backup_volume", lambda *args: {})
    with pytest.raises(release.Stop, match="website failed"):
        release.activate(state)
    assert ("rename", release.WEB, release.PREVIOUS) in calls
    assert ("rm", "-f", release.WEB) in calls
    assert ("rename", release.PREVIOUS, release.WEB) in calls
    assert ("start", release.WEB) in calls
    assert not any(c[0] == "volume" for c in calls)
    assert state["status"] == "rolled-back"


def test_successful_switch_records_identity_and_retains_previous_container(activation, monkeypatch):
    state, calls = activation
    monkeypatch.setattr(release, "wait_checks", lambda *args, **kwargs: None)
    monkeypatch.setattr(release, "backup_volume", lambda *args: {})
    release.activate(state)
    assert state["status"] == "active"
    assert state["active_id"] == "new-id"
    assert ("rename", release.WEB, release.PREVIOUS) in calls
    assert ("stop", release.CANDIDATE) in calls
    assert not any(c[0] in {"rm", "volume"} for c in calls)


def test_rollback_identity_mismatch_does_not_stop_any_container(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "inspect", lambda name: {"Id": "unexpected"})
    calls = []
    monkeypatch.setattr(release, "docker", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(release.Stop, match="identity"):
        release.rollback({"status": "active", "active_id": "expected", "original_id": "old"})
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [[], ["bash", "-c", "echo unsafe"], ["python3", "-c", "print(1)"], ["docker", "bad\0argument"]],
)
def test_command_rejects_unreviewed_executables_and_null_arguments(args, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("No process should start")

    monkeypatch.setattr(release.subprocess, "run", unexpected)
    with pytest.raises(release.Stop, match="fixed Docker and archive"):
        release.command(args)


@pytest.mark.parametrize(
    "port,path", [(22, "/"), (3000, "https://other.example/"), (3000, "/bad\r\nheader")]
)
def test_request_rejects_unexpected_targets_before_network_access(port, path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("No network request should start")

    monkeypatch.setattr(release, "build_opener", unexpected)
    with pytest.raises(release.Stop, match="probe target"):
        release.request(port, path)
