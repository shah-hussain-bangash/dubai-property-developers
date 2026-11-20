"""Offline setup and collision simulations. Never calls Docker or a real provider."""

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("local_n8n", ROOT / "scripts/local_n8n.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
IMAGE = m.REPOSITORY + "@sha256:" + "a" * 64
ID = "b" * 12


class LocalN8nTests(unittest.TestCase):
    def test_compose_is_separate_and_loopback_only(self):
        c = json.loads((ROOT / "infra/local-n8n/compose.json").read_text())
        self.assertEqual(set(c["services"]), {"n8n"})
        self.assertEqual(c["name"], m.NAME)
        self.assertEqual(c["services"]["n8n"]["ports"], ["127.0.0.1:5678:5678"])
        self.assertNotIn("networks", c["services"]["n8n"])

    def test_no_host_mounts_docker_socket_or_privileged_mode(self):
        c = json.loads((ROOT / "infra/local-n8n/compose.json").read_text())["services"]["n8n"]
        self.assertEqual(c["volumes"], ["n8n_data:/home/node/.n8n"])
        self.assertEqual(c["cap_drop"], ["ALL"])
        self.assertNotIn("privileged", c)
        self.assertIn("no-new-privileges:true", c["security_opt"])

    def test_authentication_and_private_data_controls_remain_enabled(self):
        e = json.loads((ROOT / "infra/local-n8n/compose.json").read_text())["services"]["n8n"][
            "environment"
        ]
        for key in [
            "N8N_SECURE_COOKIE",
            "N8N_BLOCK_ENV_ACCESS_IN_NODE",
            "N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES",
            "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS",
        ]:
            self.assertEqual(e[key], "true")
        self.assertNotIn("N8N_USER_MANAGEMENT_DISABLED", e)
        self.assertEqual(e["N8N_COMMUNITY_PACKAGES_ENABLED"], "false")
        self.assertEqual(e["EXECUTIONS_DATA_SAVE_ON_SUCCESS"], "none")
        self.assertEqual(e["EXECUTIONS_DATA_SAVE_ON_ERROR"], "none")

    def test_resource_and_log_bounds(self):
        c = json.loads((ROOT / "infra/local-n8n/compose.json").read_text())["services"]["n8n"]
        self.assertEqual(c["mem_limit"], "1g")
        self.assertEqual(c["pids_limit"], 256)
        self.assertEqual(c["logging"]["options"]["max-file"], "3")

    def test_remote_docker_context_is_refused(self):
        with patch.object(m, "run", return_value="ssh://remote.example"):  # noqa: SIM117 -- Keep fixture setup and expected-failure scopes separate for test clarity.
            with self.assertRaises(m.SetupError):
                m.local_engine("docker")

    def test_windows_container_engine_is_refused(self):
        with patch.object(m, "run", side_effect=["npipe:////./pipe/docker_engine", "windows"]):  # noqa: SIM117 -- Keep fixture setup and expected-failure scopes separate for test clarity.
            with self.assertRaises(m.SetupError):
                m.local_engine("docker")

    def test_local_linux_engine_is_accepted(self):
        with patch.object(
            m, "run", side_effect=["npipe:////./pipe/dockerDesktopLinuxEngine", "linux", "v2"]
        ) as call:
            m.local_engine("docker")
            self.assertEqual(call.call_count, 3)

    def test_docker_errors_do_not_print_private_output(self):
        with patch.object(
            m.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "PRIVATE", "PRIVATE"),
        ):
            with self.assertRaises(m.SetupError) as error:
                m.run(["docker", "info"])
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_command_environment_does_not_forward_provider_keys_or_remote_host(self):
        with (
            patch.dict(
                os.environ, {"PRIVATE_PROVIDER_KEY": "PRIVATE", "DOCKER_HOST": "tcp://remote"}
            ),
            patch.object(
                m.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok", "")
            ) as command,
        ):
            m.run(["docker", "info"])
            env = command.call_args.kwargs["env"]
            self.assertNotIn("DOCKER_HOST", env)
            self.assertNotIn("PRIVATE_PROVIDER_KEY", env)

    def test_image_is_resolved_to_immutable_official_digest(self):
        with (
            tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder,
            patch.object(m, "run", side_effect=["", json.dumps([IMAGE])]),
            redirect_stdout(io.StringIO()),
        ):
            p = Path(folder) / "pin.json"
            self.assertEqual(m.pinned_image("docker", p), IMAGE)
            self.assertEqual(json.loads(p.read_text())["tag"], m.TAG)

    def test_unofficial_image_digest_is_not_saved(self):
        with (
            tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder,
            patch.object(m, "run", side_effect=["", json.dumps(["other/n8n@sha256:" + "a" * 64])]),
            redirect_stdout(io.StringIO()),
        ):
            p = Path(folder) / "pin.json"
            with self.assertRaises(m.SetupError):
                m.pinned_image("docker", p)
            self.assertFalse(p.exists())

    def test_existing_digest_is_reused_without_tag_upgrade(self):
        with (
            tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder,
            patch.object(m, "run", return_value="") as command,
        ):
            p = Path(folder) / "pin.json"
            p.write_text(json.dumps({"tag": m.TAG, "image": IMAGE}))
            self.assertEqual(m.pinned_image("docker", p), IMAGE)
            self.assertEqual(command.call_args.args[0], ["docker", "pull", IMAGE])

    def test_changed_pin_is_refused_without_pulling(self):
        with (
            tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder,
            patch.object(m, "run") as command,
        ):
            p = Path(folder) / "pin.json"
            p.write_text(json.dumps({"tag": "other", "image": IMAGE}))
            with self.assertRaises(m.SetupError):
                m.pinned_image("docker", p)
            command.assert_not_called()

    def test_foreign_volume_is_preserved_and_refused(self):
        with patch.object(m, "run", side_effect=[m.VOLUME, "other-root"]):  # noqa: SIM117 -- Keep fixture setup and expected-failure scopes separate for test clarity.
            with self.assertRaises(m.SetupError):
                m.check_volume("docker", "our-root")

    def test_named_owned_volume_is_detected(self):
        with patch.object(m, "run", side_effect=[m.VOLUME, "our-root"]):
            self.assertTrue(m.check_volume("docker", "our-root"))

    def test_port_collision_is_not_stopped(self):
        with patch.object(m.socket, "socket") as server:
            server.return_value.__enter__.return_value.bind.side_effect = OSError()
            with self.assertRaises(m.SetupError):
                m.port_free()

    def container(self, ports=None, running="true", owner="root"):
        values = [
            ID,
            owner,
            "config",
            "false",
            "volume|" + m.VOLUME,
            IMAGE,
            json.dumps(ports or {"5678/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5678"}]}),
            running,
        ]
        with patch.object(m, "run", side_effect=values):
            return m.existing_container("docker", "root", "config", IMAGE)

    def test_existing_container_must_belong_to_this_project(self):
        with self.assertRaises(m.SetupError):
            self.container(owner="someone-else")

    def test_existing_container_cannot_expose_all_interfaces(self):
        with self.assertRaises(m.SetupError):
            self.container(ports={"5678/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5678"}]})  # noqa: S104 -- Negative fixture verifies that public interface binding is rejected.

    def test_stopped_container_is_not_resumed(self):
        with self.assertRaisesRegex(m.SetupError, "stopped"):
            self.container(running="false")

    def test_unchanged_running_container_can_be_reused(self):
        self.assertEqual(self.container(), ID)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder:  # noqa: SIM117 -- Keep fixture setup and expected-failure scopes separate for test clarity.
            with self.assertRaises(m.SetupError):
                m.safe_path(Path(folder).resolve(), "../outside")

    def test_project_verifier_detects_changed_protected_file(self):
        with tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder:
            root = Path(folder).resolve()
            p = root / "database/project_knowledge/reports/step649_local_n8n_results.json"
            p.parent.mkdir(parents=True)
            (root / "source.txt").write_text("changed")
            p.write_text(
                json.dumps(
                    {
                        "acceptance_status": "local_n8n_sources_installed",
                        "protected_sha256": {"source.txt": "0" * 64},
                        "file_sha256": {},
                    }
                )
            )
            with self.assertRaises(m.SetupError):
                m.verify_project(root)

    def exercise(self, existing=False, volume=False):
        with tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder:
            root = Path(folder).resolve()
            compose = root / "infra/local-n8n/compose.json"
            compose.parent.mkdir(parents=True)
            compose.write_text("{}")
            reports = root / "database/project_knowledge/reports"
            reports.mkdir(parents=True)
            if existing:
                (reports / "step649_n8n_image_pin.json").write_text("{}")
            with (
                patch.object(m, "verify_project", return_value={}) as verify,
                patch.object(m.shutil, "which", return_value="docker"),
                patch.object(m, "local_engine"),
                patch.object(
                    m, "existing_container", side_effect=[ID, ID] if existing else [None, ID]
                ),
                patch.object(m, "check_volume", return_value=volume),
                patch.object(m, "port_free") as port,
                patch.object(m, "pinned_image", return_value=IMAGE) as pin,
                patch.object(m, "run", return_value="") as command,
                patch.object(m, "ready") as ready,
                redirect_stdout(io.StringIO()),
            ):
                if volume and not existing:
                    with self.assertRaises(m.SetupError):
                        m.main(root)
                    pin.assert_not_called()
                    command.assert_not_called()
                    ready.assert_not_called()
                    return
                m.main(root)
                return (
                    command.call_args_list,
                    port.call_count,
                    verify.call_count,
                    json.loads((reports / "step649_local_n8n_start_results.json").read_text()),
                )

    def test_start_touches_only_separate_n8n_compose_project(self):
        calls, port, verify, report = self.exercise()
        self.assertEqual(len(calls), 2)
        for call in calls:
            args = call.args[0]
            self.assertEqual(args[args.index("--project-name") + 1], m.NAME)
            self.assertNotIn("dashboard", args)
            self.assertNotIn("api", args)
        self.assertEqual(calls[-1].args[0][-1], "n8n")
        self.assertIn("--pull", calls[-1].args[0])
        self.assertEqual((port, verify), (1, 2))
        self.assertEqual(report["workflows_created"], 0)

    def test_repeated_start_never_recreates_running_service(self):
        calls, port, _verify, _report = self.exercise(existing=True, volume=True)
        self.assertEqual(calls, [])
        self.assertEqual(port, 0)

    def test_orphaned_volume_cannot_resume_saved_workflows(self):
        self.exercise(volume=True)

    def test_readiness_uses_loopback_and_does_not_create_an_account(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(m, "build_opener", return_value=opener):
            m.ready()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:5678/healthz/readiness")
        self.assertIsNone(request.data)

    def test_readiness_timeout_preserves_the_service_for_diagnosis(self):
        opener = MagicMock()
        opener.open.side_effect = OSError()
        with patch.object(m, "build_opener", return_value=opener), patch.object(m.time, "sleep"):  # noqa: SIM117 -- Keep fixture setup and expected-failure scopes separate for test clarity.
            with self.assertRaisesRegex(m.SetupError, "preserved"):
                m.ready()
        self.assertEqual(opener.open.call_count, 45)

    def test_readiness_retries_only_until_success(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        opener = MagicMock()
        opener.open.side_effect = [OSError(), response]
        with patch.object(m, "build_opener", return_value=opener), patch.object(m.time, "sleep"):
            m.ready()
        self.assertEqual(opener.open.call_count, 2)

    def test_windows_appdata_is_retained_without_provider_keys(self):
        with (
            patch.dict(
                os.environ,
                {
                    "APPDATA": "Windows-config",
                    "PROGRAMFILES": "Windows-programs",
                    "PROGRAMFILES(X86)": "Windows-programs-x86",
                    "PRIVATE_PROVIDER_KEY": "SECRET",
                },
            ),
            patch.object(
                m.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok", "")
            ) as command,
        ):
            m.run(["docker", "compose", "version"])
            env = command.call_args.kwargs["env"]
            self.assertEqual(env["APPDATA"], "Windows-config")
            self.assertEqual(env["PROGRAMFILES"], "Windows-programs")
            self.assertEqual(env["PROGRAMFILES(X86)"], "Windows-programs-x86")
            self.assertNotIn("PRIVATE_PROVIDER_KEY", env)

    def test_compose_failures_name_the_stage_without_private_output(self):
        with patch.object(
            m.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "SECRET", "PRIVATE access denied"),
        ):
            with self.assertRaisesRegex(
                m.SetupError, r"Docker Compose plugin check failed \[access-denied\]"
            ) as error:
                m.run(["docker", "compose", "version"])
            self.assertNotIn("SECRET", str(error.exception))
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_fixed_verifier_prefers_repair_evidence(self):
        with tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder:
            root = Path(folder).resolve()
            reports = root / "database/project_knowledge/reports"
            reports.mkdir(parents=True)
            (reports / "step649_local_n8n_results.json").write_text("invalid prior data")
            data = {
                "acceptance_status": "local_n8n_fix_installed",
                "file_sha256": {},
                "protected_sha256": {},
            }
            (reports / "step649_fix_local_n8n_results.json").write_text(json.dumps(data))
            self.assertEqual(m.verify_project(root), data)

    def test_corrupt_repair_evidence_does_not_fall_back_to_old_hashes(self):
        with tempfile.TemporaryDirectory(prefix="dpd-n8n-test-") as folder:
            root = Path(folder).resolve()
            reports = root / "database/project_knowledge/reports"
            reports.mkdir(parents=True)
            (reports / "step649_local_n8n_results.json").write_text(
                json.dumps(
                    {
                        "acceptance_status": "local_n8n_sources_installed",
                        "file_sha256": {},
                        "protected_sha256": {},
                    }
                )
            )
            (reports / "step649_fix_local_n8n_results.json").write_text(
                json.dumps({"acceptance_status": "wrong"})
            )
            with self.assertRaises(m.SetupError):
                m.verify_project(root)


if __name__ == "__main__":
    unittest.main()
