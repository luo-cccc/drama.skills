"""Dashboard server tests (stdlib-only, loopback/static only).

`dashboard_server.py` is the security-sensitive surface of the suite (session
auth, Host/Origin checks, path confinement, compare-and-swap saves). It had no
execution coverage beyond `compileall`. These tests exercise the pure helpers
on every platform; the parts that need a live project go behind
`SECURE_DIR_FD` so they still run on macOS/Linux CI while the unsupported
Windows platform is skipped rather than failing.
"""

from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http import HTTPStatus
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SERVER = REPO_ROOT / "skills/short-drama/scripts/dashboard_server.py"
PROJECT_TOOL = REPO_ROOT / "skills/short-drama/scripts/project_tool.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dashboard = _load_module(DASHBOARD_SERVER, "dashboard_server_under_test")


class _DummyStore:
    max_request_bytes = 1024 * 1024

    def __init__(self) -> None:
        self.saved: tuple[str, str, object, object] | None = None

    def discover(self):
        return ([{"id": "project-1", "title": "Test"}], [])

    def write_text(self, project, path, content, expected_version):
        self.saved = (project, path, content, expected_version)
        return {"saved": True, "version": "new-version"}

    def close(self) -> None:
        pass


def _server_port(server) -> int:
    return server.server_address[1]


class LoopbackGuardTests(unittest.TestCase):
    def test_loopback_addresses_are_recognized(self) -> None:
        for host in ("localhost", "LOCALHOST", "127.0.0.1", "127.0.0.2", "::1"):
            self.assertTrue(dashboard._is_loopback(host), host)

    def test_non_loopback_addresses_are_rejected(self) -> None:
        for host in ("example.com", "0.0.0.0", "192.168.1.1", "10.0.0.1", "8.8.8.8"):
            self.assertFalse(dashboard._is_loopback(host), host)


class VersionTests(unittest.TestCase):
    def test_version_is_sha256_hex(self) -> None:
        self.assertEqual(
            dashboard._version(b"abc"), hashlib.sha256(b"abc").hexdigest()
        )


class ByteRangeTests(unittest.TestCase):
    def test_full_range_when_header_absent(self) -> None:
        self.assertIsNone(dashboard.DashboardHandler._byte_range(None, 10))

    def test_prefix_suffix_and_clamp(self) -> None:
        self.assertEqual(dashboard.DashboardHandler._byte_range("bytes=0-4", 10), (0, 4))
        self.assertEqual(dashboard.DashboardHandler._byte_range("bytes=5-", 10), (5, 9))
        self.assertEqual(dashboard.DashboardHandler._byte_range("bytes=-3", 10), (7, 9))
        self.assertEqual(dashboard.DashboardHandler._byte_range("bytes=0-99", 10), (0, 9))

    def test_invalid_ranges_are_rejected(self) -> None:
        for value in (
            "garbage",
            "bytes=10-11",  # start beyond size
            "bytes=5-2",  # end before start
            "bytes=0-4,6-8",  # multiple ranges unsupported
            "bytes=-0",  # zero suffix
        ):
            with self.assertRaises(dashboard.DashboardError) as context:
                dashboard.DashboardHandler._byte_range(value, 10)
            self.assertEqual(
                context.exception.status,
                HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
                value,
            )

    def test_zero_size_is_rejected(self) -> None:
        with self.assertRaises(dashboard.DashboardError):
            dashboard.DashboardHandler._byte_range("bytes=0-0", 0)


class SafeRelativeTests(unittest.TestCase):
    def test_plain_path_is_accepted(self) -> None:
        pure = dashboard.ProjectStore._safe_relative("a/b.md")
        self.assertEqual(pure.as_posix(), "a/b.md")

    def test_traversal_and_absolute_paths_are_rejected(self) -> None:
        for raw in ("", ".", "..", "a/../b", "/etc/passwd", "a/../../b"):
            with self.assertRaises(dashboard.DashboardError) as context:
                dashboard.ProjectStore._safe_relative(raw)
            self.assertEqual(context.exception.status, HTTPStatus.BAD_REQUEST, raw)

    def test_dot_segments_normalize_to_a_safe_path(self) -> None:
        # PurePosixPath collapses "." segments; "a/./b" is the same file as "a/b",
        # not traversal, so it stays accepted (and O_NOFOLLOW still binds it).
        self.assertEqual(
            dashboard.ProjectStore._safe_relative("a/./b").as_posix(), "a/b"
        )

    def test_percent_encoded_traversal_is_rejected(self) -> None:
        # A URL-encoded "../" must not sneak past the unquote-then-validate step.
        with self.assertRaises(dashboard.DashboardError) as context:
            dashboard.ProjectStore._safe_relative("a%2F..%2Fb")
        self.assertEqual(context.exception.status, HTTPStatus.BAD_REQUEST)


class AuthorityGuardTests(unittest.TestCase):
    def test_loopback_authority_with_matching_port_is_allowed(self) -> None:
        server = dashboard.DashboardHTTPServer(("127.0.0.1", 0), _DummyStore())
        try:
            port = _server_port(server)
            self.assertTrue(server.allowed_authority(f"127.0.0.1:{port}"))
            self.assertTrue(server.allowed_authority(f"localhost:{port}"))
            self.assertTrue(server.allowed_authority(f"[::1]:{port}"))
        finally:
            server.server_close()

    def test_non_matching_authorities_are_rejected(self) -> None:
        server = dashboard.DashboardHTTPServer(("127.0.0.1", 0), _DummyStore())
        try:
            port = _server_port(server)
            self.assertFalse(server.allowed_authority(f"127.0.0.1:{port + 1}"))
            self.assertFalse(server.allowed_authority("127.0.0.1"))  # no port
            self.assertFalse(server.allowed_authority(f"example.com:{port}"))
            self.assertFalse(server.allowed_authority(f"user@127.0.0.1:{port}"))
        finally:
            server.server_close()


class HTTPHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _DummyStore()
        self.server = dashboard.DashboardHTTPServer(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1", _server_port(self.server), timeout=5
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def _request(self, method: str, path: str, **kwargs):
        self.connection.request(method, path, **kwargs)
        response = self.connection.getresponse()
        body = response.read()
        return response, body

    def _session_cookie(self) -> str:
        response, body = self._request(
            "POST",
            f"{self.server.api_prefix}/api/session",
            headers={"X-Short-Drama-Token": self.server.access_token},
        )
        self.assertEqual(response.status, HTTPStatus.OK, body)
        self.assertEqual(json.loads(body)["apiBase"], self.server.api_prefix)
        cookie = response.getheader("Set-Cookie")
        self.assertIsNotNone(cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        return str(cookie).split(";", 1)[0]

    def test_api_requires_a_session(self) -> None:
        response, body = self._request(
            "GET", f"{self.server.api_prefix}/api/projects"
        )
        self.assertEqual(response.status, HTTPStatus.UNAUTHORIZED, body)

    def test_session_cookie_authorizes_prefixed_api(self) -> None:
        cookie = self._session_cookie()
        response, body = self._request(
            "GET",
            f"{self.server.api_prefix}/api/projects",
            headers={"Cookie": cookie},
        )
        self.assertEqual(response.status, HTTPStatus.OK, body)
        self.assertEqual(json.loads(body)["projects"][0]["id"], "project-1")

    def test_invalid_host_and_origin_are_rejected(self) -> None:
        response, body = self._request("GET", "/", headers={"Host": "example.com"})
        self.assertEqual(response.status, HTTPStatus.FORBIDDEN, body)
        response, body = self._request(
            "GET", "/", headers={"Origin": "https://example.com"}
        )
        self.assertEqual(response.status, HTTPStatus.FORBIDDEN, body)

    def test_security_headers_are_sent_on_static_responses(self) -> None:
        response, body = self._request("GET", "/")
        self.assertEqual(response.status, HTTPStatus.OK, body)
        self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
        self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))

    def test_put_route_saves_and_rejects_non_standard_json(self) -> None:
        cookie = self._session_cookie()
        path = f"{self.server.api_prefix}/api/file?project=p&path=notes.json"
        payload = json.dumps({"content": "{}", "expectedVersion": "old"})
        response, body = self._request(
            "PUT",
            path,
            body=payload.encode("utf-8"),
            headers={"Cookie": cookie, "Content-Type": "application/json"},
        )
        self.assertEqual(response.status, HTTPStatus.OK, body)
        self.assertEqual(self.store.saved, ("p", "notes.json", "{}", "old"))

        response, body = self._request(
            "PUT",
            path,
            body=b'{"content":NaN,"expectedVersion":"old"}',
            headers={"Cookie": cookie, "Content-Type": "application/json"},
        )
        self.assertEqual(response.status, HTTPStatus.BAD_REQUEST, body)

@unittest.skipUnless(dashboard.SECURE_DIR_FD, "dashboard requires POSIX directory descriptors")
class ProjectStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_tool = _load_module(PROJECT_TOOL, "dashboard_project_tool_under_test")

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tempdir.name)
        self.project = self.workspace / "proj"
        self.project_tool.initialize_project(
            self.project,
            title="冒烟测试",
            language="zh-CN",
            aspect_ratio="9:16",
            prompt_language="en",
        )
        (self.project / "README.md").write_text("第一版\n", encoding="utf-8")
        (self.project / "notes.json").write_text("{}\n", encoding="utf-8")
        self.store = dashboard.ProjectStore(self.workspace, self.project_tool)

    def tearDown(self) -> None:
        self.store.close()
        self._tempdir.cleanup()

    def _project_id(self) -> str:
        projects, _warnings = self.store.discover()
        self.assertEqual(len(projects), 1, projects)
        self.assertEqual(projects[0]["path"], "proj")
        self.assertEqual(projects[0]["title"], "冒烟测试")
        return projects[0]["id"]

    def test_discover_finds_the_project(self) -> None:
        self._project_id()

    def test_read_text_returns_content_and_version(self) -> None:
        data = self.store.read_text(self._project_id(), "README.md")
        self.assertEqual(data["content"], "第一版\n")
        self.assertTrue(data["writable"])
        self.assertEqual(data["version"], dashboard._version("第一版\n".encode("utf-8")))

    def test_write_text_saves_and_returns_new_version(self) -> None:
        project_id = self._project_id()
        before = self.store.read_text(project_id, "README.md")
        result = self.store.write_text(
            project_id, "README.md", "第二版\n", before["version"]
        )
        self.assertTrue(result["saved"])
        self.assertEqual(
            self.store.read_text(project_id, "README.md")["content"], "第二版\n"
        )

    def test_write_text_rejects_a_stale_version(self) -> None:
        project_id = self._project_id()
        before = self.store.read_text(project_id, "README.md")
        (self.project / "README.md").write_text("被外部改过\n", encoding="utf-8")
        with self.assertRaises(dashboard.DashboardError) as context:
            self.store.write_text(project_id, "README.md", "第二版\n", before["version"])
        self.assertEqual(context.exception.status, HTTPStatus.CONFLICT)

    def test_project_manifest_is_read_only(self) -> None:
        project_id = self._project_id()
        data = self.store.read_text(project_id, "short-drama.json")
        self.assertFalse(data["writable"])
        with self.assertRaises(dashboard.DashboardError) as context:
            self.store.write_text(
                project_id, "short-drama.json", "{}", dashboard._version(b"{}")
            )
        self.assertEqual(context.exception.status, HTTPStatus.FORBIDDEN)

    def test_invalid_json_save_is_rejected(self) -> None:
        project_id = self._project_id()
        before = self.store.read_text(project_id, "notes.json")
        with self.assertRaises(dashboard.DashboardError) as context:
            self.store.write_text(
                project_id, "notes.json", "not-json", before["version"]
            )
        self.assertEqual(context.exception.status, HTTPStatus.BAD_REQUEST)


if __name__ == "__main__":
    unittest.main()
