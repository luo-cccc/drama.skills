"""Regression tests for portable paths, strict JSON, and pinned suite versions."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TOOL = REPO_ROOT / "skills/short-drama/scripts/project_tool.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


project_tool = _load_module(PROJECT_TOOL, "project_tool_security_under_test")


class PortablePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name) / "project"
        project_tool.initialize_project(
            self.root,
            title="portable paths",
            language="zh-CN",
            aspect_ratio="9:16",
        )

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _publish(self, outputs: dict[str, bytes]) -> None:
        project_tool.publish_transaction(
            self.root,
            stage="portable-test",
            outputs=outputs,
            lifecycle_changes={},
        )

    def test_separator_aliases_are_rejected_before_overwrite(self) -> None:
        with self.assertRaisesRegex(ValueError, "portable filesystem"):
            self._publish(
                {
                    "项目开发/same.md": b"first",
                    "项目开发\\same.md": b"second",
                }
            )
        self.assertFalse((self.root / "项目开发/same.md").exists())

    def test_case_aliases_are_rejected_on_every_platform(self) -> None:
        with self.assertRaisesRegex(ValueError, "portable filesystem"):
            self._publish(
                {
                    "项目开发/Foo.md": b"first",
                    "项目开发/foo.md": b"second",
                }
            )

    def test_unicode_normalization_aliases_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "portable filesystem"):
            self._publish(
                {
                    "项目开发/Caf\u00e9.md": b"first",
                    "项目开发/Cafe\u0301.md": b"second",
                }
            )

    def test_windows_nonportable_components_are_rejected(self) -> None:
        values = (
            "项目开发/CON.md",
            "项目开发/NUL.txt",
            "项目开发/com1.json",
            "项目开发/notes?.md",
            "项目开发/notes.md ",
            "项目开发/notes.md.",
            "项目开发/line\x01.md",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(
                project_tool.NonPortablePathError
            ):
                project_tool._relative_path(value)

    def test_manifest_recovery_rejects_portable_target_aliases(self) -> None:
        digest = "a" * 64
        manifest = {
            "transaction_id": "b" * 32,
            "authority": "accepted",
            "owner": None,
            "read_set": [],
            "lifecycle_changes": {},
            "targets": [
                {
                    "index": index,
                    "path": path,
                    "artifact_id": "artifact",
                    "expected_prior": None,
                    "prior_snapshot": None,
                    "candidate_hash": digest,
                    "candidate_snapshot": (
                        ".short-drama/accepted-snapshots/artifact/" + digest + "/content"
                    ),
                }
                for index, path in enumerate(
                    ("项目开发/Foo.md", "项目开发/foo.md")
                )
            ],
        }
        with self.assertRaisesRegex(project_tool.TransactionError, "portable filesystem"):
            project_tool._validate_manifest(manifest, "b" * 32)


class InputValidationTests(unittest.TestCase):
    def test_aspect_ratio_accepts_positive_colon_form(self) -> None:
        for value in ("9:16", "16:9", "2.39:1", " 1:1 "):
            self.assertEqual(project_tool.normalize_aspect_ratio(value), value.strip())

    def test_aspect_ratio_rejects_invalid_or_nonpositive_forms(self) -> None:
        for value in ("", "banana", "9/16", "-1:1", "1:0", "0:1", "1:Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                project_tool.normalize_aspect_ratio(value)

    def test_generation_clip_limit_is_positive_and_written_to_new_projects(self) -> None:
        for value in (0, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                project_tool.normalize_positive_seconds(value, field="max_clip_seconds")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            result = project_tool.initialize_project(
                root,
                title="clip limit",
                language="zh-CN",
                aspect_ratio="9:16",
                max_clip_seconds=12.5,
            )
            limits = result["project"]["format"]["generation_limits"]
            self.assertEqual(limits["max_clip_seconds"], 12.5)
            self.assertFalse(limits["continuation_supported"])

    def test_strict_json_rejects_non_finite_constants(self) -> None:
        for value in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            with self.subTest(value=value), self.assertRaises(json.JSONDecodeError):
                project_tool._json_loads(value)

    def test_invalid_aspect_ratio_does_not_leave_a_partial_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            with self.assertRaises(ValueError):
                project_tool.initialize_project(
                    root,
                    title="invalid",
                    language="zh-CN",
                    aspect_ratio="9/16",
                )
            self.assertFalse(root.exists())

    def test_descriptor_read_detects_a_path_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "source.md"
            replacement = root / "replacement.md"
            target.write_bytes(b"original")
            replacement.write_bytes(b"replacement")
            original_open = project_tool.os.open
            swapped = False

            def racing_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if not swapped and Path(path) == target:
                    swapped = True
                    project_tool.os.replace(replacement, target)
                return original_open(path, flags, *args, **kwargs)

            with mock.patch.object(project_tool.os, "open", side_effect=racing_open):
                with self.assertRaises(project_tool.TransactionConflictError):
                    project_tool._read_project_regular(root, "source.md")

    def test_cli_json_is_ascii_safe_under_a_legacy_code_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "中文项目"
            environment = os.environ.copy()
            environment["PYTHONUTF8"] = "0"
            environment["PYTHONIOENCODING"] = "cp1252"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_TOOL),
                    "init",
                    str(root),
                    "--title",
                    "中文项目",
                ],
                check=False,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("ascii", "replace"),
            )
            output = completed.stdout.decode("ascii")
            payload = json.loads(output)
            self.assertEqual(payload["project_root"], str(root))
            self.assertIn("\\u", output)


class SuiteVersionTests(unittest.TestCase):
    def test_code_manifest_and_template_versions_match(self) -> None:
        manifest = json.loads(
            (REPO_ROOT / "skills/short-drama/suite-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        template = json.loads(
            (REPO_ROOT / "skills/short-drama/assets/project-template/short-drama.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(project_tool.SUITE_VERSION, manifest["suite_version"])
        self.assertEqual(project_tool.CONTRACT_VERSION, manifest["contract_version"])
        self.assertEqual(
            project_tool.CONTRACT_VERSION, template["schema_version"]
        )
        self.assertEqual(
            project_tool.PIPELINE_VERSION,
            template["production_flow"]["pipeline_version"],
        )


if __name__ == "__main__":
    unittest.main()
