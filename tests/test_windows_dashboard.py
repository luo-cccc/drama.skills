"""Windows handle-backend regressions for the short-drama Dashboard."""

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import ctypes
import gc
from ctypes import wintypes
from contextlib import redirect_stderr
from http import HTTPStatus
from pathlib import Path
from queue import Empty
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SERVER = REPO_ROOT / "skills/short-drama/scripts/dashboard_server.py"
PROJECT_TOOL = REPO_ROOT / "skills/short-drama/scripts/project_tool.py"
WINDOWS_SECURE_FS = REPO_ROOT / "skills/short-drama/scripts/windows_secure_fs.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _save_worker(
    workspace: str,
    expected_version: str,
    content: str,
    ready_queue,
    start_event,
    result_queue,
) -> None:
    dashboard = _load_module(DASHBOARD_SERVER, f"dashboard_worker_{os.getpid()}")
    project_tool = _load_module(PROJECT_TOOL, f"project_tool_worker_{os.getpid()}")
    store = dashboard.ProjectStore(Path(workspace), project_tool)
    try:
        projects, _warnings = store.discover()
        project_id = projects[0]["id"]
        ready_queue.put(True)
        if not start_event.wait(10):
            result_queue.put(("timeout", None))
            return
        try:
            store.write_text(project_id, "README.md", content, expected_version)
        except dashboard.DashboardError as exc:
            result_queue.put(("error", int(exc.status)))
        else:
            result_queue.put(("saved", None))
    finally:
        store.close()


def _cli_lock_worker(project: str, lock_held, release_lock) -> None:
    project_tool = _load_module(
        PROJECT_TOOL, f"project_tool_lock_worker_{os.getpid()}"
    )
    with project_tool._transaction_lock(Path(project)):
        lock_held.set()
        release_lock.wait(10)


@unittest.skipUnless(os.name == "nt", "Windows handle backend only")
class WindowsSecureFilesystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.windows_fs = _load_module(
            WINDOWS_SECURE_FS, "windows_secure_fs_under_test"
        )

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name) / "workspace"
        self.root.mkdir()

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _junction(self, link: Path, target: Path) -> None:
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)

    def test_workspace_junction_is_rejected(self) -> None:
        link = self.root.parent / "workspace-link"
        self._junction(link, self.root)
        with self.assertRaisesRegex(
            self.windows_fs.WindowsFilesystemError, "reparse points"
        ):
            self.windows_fs.WindowsDirectory.open_workspace(link)

    def test_workspace_symlink_is_rejected(self) -> None:
        link = self.root.parent / "workspace-symlink"
        try:
            os.symlink(self.root, link, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")
        with self.assertRaisesRegex(
            self.windows_fs.WindowsFilesystemError, "reparse points"
        ):
            self.windows_fs.WindowsDirectory.open_workspace(link)

    def test_nested_junction_is_rejected(self) -> None:
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "secret.md").write_bytes(b"outside")
        self._junction(self.root / "nested", outside)
        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            with self.assertRaisesRegex(
                self.windows_fs.WindowsFilesystemError, "reparse points"
            ):
                directory.read_regular("nested/secret.md")

    def test_pinned_parent_survives_path_replacement(self) -> None:
        original = self.root / "parent"
        original.mkdir()
        (original / "note.md").write_bytes(b"original")
        with self.windows_fs.WindowsDirectory.open_workspace(original) as directory:
            moved = self.root / "parent-moved"
            os.replace(original, moved)
            original.mkdir()
            (original / "note.md").write_bytes(b"replacement")
            self.assertEqual(directory.read_regular("note.md"), b"original")
            old_hash = hashlib.sha256(b"original").hexdigest()
            directory.replace_regular("note.md", b"updated", old_hash)
        self.assertEqual((moved / "note.md").read_bytes(), b"updated")
        self.assertEqual((original / "note.md").read_bytes(), b"replacement")

    def test_open_media_handle_survives_path_replacement(self) -> None:
        media = self.root / "preview.png"
        media.write_bytes(b"original-media")
        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            stream, size = directory.open_regular("preview.png")
            moved = self.root / "preview-original.png"
            os.replace(media, moved)
            media.write_bytes(b"replacement-media")
            try:
                self.assertEqual(size, len(b"original-media"))
                self.assertEqual(stream.read(), b"original-media")
            finally:
                stream.close()

    def test_target_lock_blocks_mid_save_external_write(self) -> None:
        target = self.root / "note.md"
        target.write_bytes(b"before")
        expected = hashlib.sha256(b"before").hexdigest()
        original_write = self.windows_fs.WindowsDirectory._write_handle
        blocked: list[OSError] = []

        def racing_write(handle, content):
            original_write(handle, content)
            try:
                target.write_bytes(b"external")
            except OSError as exc:
                blocked.append(exc)

        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            with mock.patch.object(
                self.windows_fs.WindowsDirectory,
                "_write_handle",
                side_effect=racing_write,
            ):
                directory.replace_regular("note.md", b"submitted", expected)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(target.read_bytes(), b"submitted")
        self.assertEqual(list(self.root.glob(".sd-*.tmp")), [])

    def test_existing_external_write_handle_causes_conflict(self) -> None:
        target = self.root / "note.md"
        target.write_bytes(b"before")
        expected = hashlib.sha256(b"before").hexdigest()
        with (
            target.open("r+b") as external,
            self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory,
        ):
            external.seek(0)
            with self.assertRaisesRegex(
                FileExistsError, "modified by another process"
            ):
                directory.replace_regular("note.md", b"submitted", expected)
        self.assertEqual(target.read_bytes(), b"before")

    def test_long_legal_filename_can_be_replaced(self) -> None:
        name = f"{'a' * 220}.md"
        target = self.root / name
        target.write_bytes(b"before")
        expected = hashlib.sha256(b"before").hexdigest()
        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            directory.replace_regular(name, b"after", expected)
        self.assertEqual(target.read_bytes(), b"after")

    def test_empty_file_lock_does_not_change_content(self) -> None:
        target = self.root / "empty.md"
        target.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            directory.replace_regular("empty.md", b"filled", expected)
        self.assertEqual(target.read_bytes(), b"filled")

    def test_write_and_rename_failures_clean_temporary_files(self) -> None:
        target = self.root / "note.md"
        target.write_bytes(b"before")
        expected = hashlib.sha256(b"before").hexdigest()
        for method in ("_write_handle", "_rename_replace"):
            with self.subTest(method=method):
                with self.windows_fs.WindowsDirectory.open_workspace(
                    self.root
                ) as directory:
                    with mock.patch.object(
                        self.windows_fs.WindowsDirectory,
                        method,
                        side_effect=OSError("injected failure"),
                    ):
                        with self.assertRaisesRegex(OSError, "injected failure"):
                            directory.replace_regular(
                                "note.md", b"submitted", expected
                            )
                self.assertEqual(target.read_bytes(), b"before")
                self.assertEqual(list(self.root.glob(".sd-*.tmp")), [])

    def test_oversize_read_closes_its_handle(self) -> None:
        (self.root / "note.md").write_bytes(b"too large")
        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            handle = directory._open_regular_handle("note.md")
            with self.assertRaisesRegex(ValueError, "configured limit"):
                directory._read_handle(handle, limit=1)
            self.assertEqual(handle.value, 0)

    def test_repeated_operations_do_not_leak_process_handles(self) -> None:
        (self.root / "note.md").write_bytes(b"content")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessHandleCount.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetProcessHandleCount.restype = wintypes.BOOL

        def handle_count() -> int:
            count = wintypes.DWORD()
            self.assertTrue(
                kernel32.GetProcessHandleCount(
                    kernel32.GetCurrentProcess(), ctypes.byref(count)
                )
            )
            return int(count.value)

        with self.windows_fs.WindowsDirectory.open_workspace(self.root) as directory:
            baseline = handle_count()
            for _ in range(100):
                directory.scan()
                directory.read_regular("note.md")
                stream, _size = directory.open_regular("note.md")
                stream.close()
            gc.collect()
            self.assertLessEqual(handle_count(), baseline + 2)

    def test_missing_api_nonfixed_drive_and_non_ntfs_fail_closed(self) -> None:
        with mock.patch.object(self.windows_fs, "_REQUIRED_APIS", (None,)):
            with self.assertRaisesRegex(
                self.windows_fs.WindowsFilesystemError, "APIs are unavailable"
            ):
                self.windows_fs.WindowsDirectory.open_workspace(self.root)
        with mock.patch.object(self.windows_fs, "_drive_type", return_value=4):
            with self.assertRaisesRegex(
                self.windows_fs.WindowsFilesystemError, "fixed local drive"
            ):
                self.windows_fs.WindowsDirectory.open_workspace(self.root)
        with mock.patch.object(
            self.windows_fs, "_volume_filesystem", return_value="ReFS"
        ):
            with self.assertRaisesRegex(
                self.windows_fs.WindowsFilesystemError, "require NTFS"
            ):
                self.windows_fs.WindowsDirectory.open_workspace(self.root)


@unittest.skipUnless(os.name == "nt", "Windows Dashboard backend only")
class WindowsDashboardStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dashboard = _load_module(DASHBOARD_SERVER, "windows_dashboard_under_test")
        cls.project_tool = _load_module(PROJECT_TOOL, "windows_project_tool_under_test")

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tempdir.name)
        self.project = self.workspace / "proj"
        self.project_tool.initialize_project(
            self.project,
            title="Windows Dashboard",
            language="zh-CN",
            aspect_ratio="9:16",
        )
        (self.project / "README.md").write_bytes(b"first\n")
        (self.project / "preview.png").write_bytes(b"media-original")
        self.store = self.dashboard.ProjectStore(self.workspace, self.project_tool)

    def tearDown(self) -> None:
        self.store.close()
        self._tempdir.cleanup()

    def _project_id(self) -> str:
        projects, _warnings = self.store.discover()
        self.assertEqual(len(projects), 1)
        return projects[0]["id"]

    def test_ads_and_reserved_device_paths_are_rejected(self) -> None:
        project_id = self._project_id()
        for relative in ("README.md:stream", "CON.md", "aux.txt", "bad. "):
            with self.subTest(relative=relative):
                with self.assertRaises(self.dashboard.DashboardError) as context:
                    self.store.read_text(project_id, relative)
                self.assertEqual(context.exception.status, HTTPStatus.BAD_REQUEST)

    def test_store_implements_public_project_store_type(self) -> None:
        self.assertIsInstance(self.store, self.dashboard.ProjectStore)

    def test_pinned_project_root_survives_replacement(self) -> None:
        project_id = self._project_id()
        with self.store._pinned_project(project_id) as (project, _root):
            moved = self.workspace / "proj-moved"
            os.replace(self.project, moved)
            self.project.mkdir()
            (self.project / "README.md").write_bytes(b"replacement\n")
            self.assertEqual(project.read_regular("README.md"), b"first\n")
            expected = hashlib.sha256(b"first\n").hexdigest()
            project.replace_regular("README.md", b"updated\n", expected)
        self.assertEqual((moved / "README.md").read_bytes(), b"updated\n")
        self.assertEqual((self.project / "README.md").read_bytes(), b"replacement\n")

    def test_public_media_stream_remains_bound_after_replacement(self) -> None:
        stream, _pure, _content_type, size = self.store.open_media(
            self._project_id(), "preview.png"
        )
        media = self.project / "preview.png"
        moved = self.project / "preview-original.png"
        os.replace(media, moved)
        media.write_bytes(b"media-replacement")
        try:
            self.assertEqual(size, len(b"media-original"))
            self.assertEqual(stream.read(), b"media-original")
        finally:
            stream.close()

    def test_http_media_range_uses_the_windows_store(self) -> None:
        store = self.dashboard.ProjectStore(self.workspace, self.project_tool)
        server = self.dashboard.DashboardHTTPServer(("127.0.0.1", 0), store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=5
        )
        try:
            connection.request(
                "POST",
                f"{server.api_prefix}/api/session",
                headers={"X-Short-Drama-Token": server.access_token},
            )
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, HTTPStatus.OK)
            cookie = str(response.getheader("Set-Cookie")).split(";", 1)[0]
            connection.request(
                "GET",
                (
                    f"{server.api_prefix}/api/media/content"
                    f"?project={self._project_id()}&path=preview.png"
                ),
                headers={"Cookie": cookie, "Range": "bytes=0-4"},
            )
            response = connection.getresponse()
            body = response.read()
            self.assertEqual(response.status, HTTPStatus.PARTIAL_CONTENT, body)
            self.assertEqual(response.getheader("Content-Range"), "bytes 0-4/14")
            self.assertEqual(body, b"media")
        finally:
            connection.close()
            server.shutdown()
            thread.join(5)
            server.server_close()

    def test_save_marks_owned_artifact_stale_in_status(self) -> None:
        before = self.store.read_text(self._project_id(), "README.md")
        state_path = self.project / ".short-drama/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["artifacts"] = {
            "script": {
                "build_state": "materialized",
                "validation_state": "pass",
                "creator_acceptance": "accepted",
                "independent_review": "approve",
                "delivery_gate": "ready",
                "accepted_targets": {"README.md": before["version"]},
            }
        }
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.store.write_text(
            self._project_id(), "README.md", "second\n", before["version"]
        )
        status = self.store.status(self._project_id())
        self.assertEqual(status["artifact_build_states"], {"stale": 1})
        self.assertEqual(status["last_action"], "working_text_edited")

    def test_state_update_failure_returns_saved_result_with_warning(self) -> None:
        project_id = self._project_id()
        before = self.store.read_text(project_id, "README.md")
        state_path = self.project / ".short-drama/state.json"
        state_before = state_path.read_bytes()
        with mock.patch.object(
            self.project_tool,
            "update_working_text_state",
            side_effect=ValueError("injected state failure"),
        ):
            result = self.store.write_text(
                project_id, "README.md", "second\n", before["version"]
            )
        self.assertTrue(result["saved"])
        self.assertEqual(result["stateWarning"], "lifecycle_update_failed")
        self.assertEqual(
            result["version"], hashlib.sha256(b"second\n").hexdigest()
        )
        self.assertEqual((self.project / "README.md").read_bytes(), b"second\n")
        self.assertEqual(state_path.read_bytes(), state_before)

    def test_state_replace_failure_returns_saved_result_with_warning(self) -> None:
        project_id = self._project_id()
        before = self.store.read_text(project_id, "README.md")
        state_path = self.project / ".short-drama/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["artifacts"] = {
            "script": {
                "build_state": "materialized",
                "accepted_targets": {"README.md": before["version"]},
            }
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        state_before = state_path.read_bytes()
        directory_type = self.store.windows_fs.WindowsDirectory
        original_replace = directory_type.replace_regular

        def fail_state_replace(directory, relative, content, expected_hash):
            if str(relative) == ".short-drama/state.json":
                raise OSError("injected state replace failure")
            return original_replace(directory, relative, content, expected_hash)

        with mock.patch.object(
            directory_type,
            "replace_regular",
            autospec=True,
            side_effect=fail_state_replace,
        ):
            result = self.store.write_text(
                project_id, "README.md", "second\n", before["version"]
            )
        self.assertTrue(result["saved"])
        self.assertEqual(result["stateWarning"], "lifecycle_update_failed")
        self.assertEqual((self.project / "README.md").read_bytes(), b"second\n")
        self.assertEqual(state_path.read_bytes(), state_before)

    def test_missing_state_is_a_valid_project_status(self) -> None:
        (self.project / ".short-drama/state.json").unlink()
        status = self.project_tool.project_status(self.project)
        self.assertEqual(status["artifact_build_states"], {})

    def test_reparse_lifecycle_target_is_reported_stale(self) -> None:
        outside = self.workspace / "outside"
        outside.mkdir()
        (outside / "target.md").write_bytes(b"outside")
        junction = self.project / "linked"
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode, 0, completed.stderr or completed.stdout
        )
        state_path = self.project / ".short-drama/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["artifacts"] = {
            "script": {
                "build_state": "materialized",
                "accepted_targets": {
                    "linked/target.md": hashlib.sha256(b"outside").hexdigest()
                },
            }
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        status = self.store.status(self._project_id())
        self.assertEqual(status["artifact_build_states"], {"stale": 1})

    def test_missing_transaction_wal_remains_needs_rollback(self) -> None:
        transaction = self.project / ".short-drama/transactions/interrupted"
        transaction.mkdir(parents=True)
        (transaction / "manifest.json").write_text("{}", encoding="utf-8")
        status = self.store.status(self._project_id())
        self.assertEqual(
            status["recovery"]["transaction_counts"], {"needs_rollback": 1}
        )

    def test_working_text_update_preserves_malformed_artifacts(self) -> None:
        digest = hashlib.sha256(b"after").hexdigest()
        state = {
            "artifacts": {
                "owner": {
                    "build_state": "materialized",
                    "accepted_targets": {"README.md": hashlib.sha256(b"before").hexdigest()},
                },
                "malformed": "keep-me",
            }
        }
        updated = self.project_tool.update_working_text_state(
            state, "README.md", digest
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["artifacts"]["malformed"], "keep-me")

    def test_unsupported_workspace_fails_before_server_binding(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.object(
                self.dashboard,
                "DashboardHTTPServer",
                side_effect=AssertionError("server must not bind"),
            ),
            redirect_stderr(stderr),
        ):
            result = self.dashboard.main(
                ["--workspace", r"\\server\share", "--port", "0"]
            )
        self.assertEqual(result, 2)
        self.assertIn("normal drive-letter path", stderr.getvalue())

    def test_dashboard_and_cli_transaction_locks_are_mutually_exclusive(self) -> None:
        project_id = self._project_id()
        before = self.store.read_text(project_id, "README.md")
        context = multiprocessing.get_context("spawn")
        lock_held = context.Event()
        release_lock = context.Event()
        writer_started = threading.Event()
        writer_done = threading.Event()
        failures: list[BaseException] = []

        def write_dashboard() -> None:
            writer_started.set()
            try:
                self.store.write_text(
                    project_id, "README.md", "second\n", before["version"]
                )
            except BaseException as exc:
                failures.append(exc)
            finally:
                writer_done.set()

        holder = context.Process(
            target=_cli_lock_worker,
            args=(str(self.project), lock_held, release_lock),
        )
        writer = threading.Thread(target=write_dashboard)
        holder.start()
        self.assertTrue(lock_held.wait(15))
        writer.start()
        self.assertTrue(writer_started.wait(5))
        self.assertFalse(writer_done.wait(0.25))
        release_lock.set()
        holder.join(15)
        writer.join(5)
        if holder.is_alive():
            holder.terminate()
            holder.join(5)
        self.assertEqual(holder.exitcode, 0)
        self.assertFalse(writer.is_alive())
        self.assertEqual(failures, [])

    def test_two_processes_with_one_version_allow_only_one_save(self) -> None:
        expected = self.store.read_text(self._project_id(), "README.md")["version"]
        context = multiprocessing.get_context("spawn")
        ready_queue = context.Queue()
        result_queue = context.Queue()
        start_event = context.Event()
        processes = [
            context.Process(
                target=_save_worker,
                args=(
                    str(self.workspace),
                    expected,
                    f"process-{index}\n",
                    ready_queue,
                    start_event,
                    result_queue,
                ),
            )
            for index in range(2)
        ]
        try:
            for process in processes:
                process.start()
            for _ in processes:
                self.assertTrue(ready_queue.get(timeout=15))
            start_event.set()
            results = [result_queue.get(timeout=15) for _ in processes]
        except Empty as exc:
            self.fail(f"worker did not report in time: {exc}")
        finally:
            start_event.set()
            for process in processes:
                process.join(15)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
        self.assertEqual(sorted(results), [("error", 409), ("saved", None)])
        self.assertTrue(all(process.exitcode == 0 for process in processes))


if __name__ == "__main__":
    unittest.main()
