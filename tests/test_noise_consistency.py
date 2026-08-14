"""Suite-internal consistency tests, stdlib-only so CI needs no third-party deps.

Each test derives expectations from the live suite so a passing run stays
meaningful when the suite evolves, and fails when the derivation itself
breaks — the exact cases that used to drift silently:

- the noise sets duplicated across suite_verify.py and the manifest tool;
- the manifest no longer matching the canonical text state of the public skills;
- the manifest regenerator no longer being idempotent on an unchanged tree;
- the public SKILL.md frontmatters drifting from their installed metadata.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE = REPO_ROOT / "skills" / "short-drama"
SKILLS = REPO_ROOT / "skills"
SUITE_VERIFY = CORE / "scripts" / "suite_verify.py"
UPDATE_MANIFEST = REPO_ROOT / "tools" / "update_suite_manifest.py"

NOISE_DIR_NAMES = frozenset({".ruff_cache", ".mypy_cache", ".pytest_cache"})
NOISE_FILE_NAMES = frozenset({".DS_Store"})
NOISE_FILE_SUFFIXES = ("~", ".swp", ".swo")
BYTECODE_SUFFIXES = (".pyc", ".pyo")
EXECUTABLE_SUFFIXES = (
    ".py", ".sh", ".bash", ".zsh", ".fish", ".js", ".mjs", ".cjs",
    ".rb", ".pl", ".php", ".exe", ".dll", ".so", ".dylib", ".command",
)
TEXT_FILE_SUFFIXES = frozenset(
    {".css", ".csv", ".html", ".js", ".json", ".jsonl", ".md", ".py", ".toml", ".tsv", ".txt", ".xml", ".yaml", ".yml"}
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_OPENAI_RE = re.compile(r'^  ([a-z_]+):\s+"((?:[^"\\]|\\.)*)"$')


def is_local_noise(parts: tuple[str, ...]) -> bool:
    """Local copy of the shared noise policy (mirrors the two tools)."""

    name = parts[-1]
    if name.endswith(EXECUTABLE_SUFFIXES):
        return False
    if "__pycache__" in parts[:-1]:
        return name.endswith(BYTECODE_SUFFIXES)
    if any(part in NOISE_DIR_NAMES for part in parts[:-1]):
        return True
    return name in NOISE_FILE_NAMES or name.endswith(NOISE_FILE_SUFFIXES)


def text_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def suite_file_sha256(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in TEXT_FILE_SUFFIXES:
        return text_sha256(data)
    return hashlib.sha256(data).hexdigest()


class NoisePolicyConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verify_mod = _load_module(SUITE_VERIFY)
        cls.regen_mod = _load_module(UPDATE_MANIFEST)

    def _run(self, target: str) -> str:
        result = subprocess.run(  # noqa: PLW1510  (exit codes checked below)
            [sys.executable, target],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        return result.stdout

    def test_verify_and_regenerator_noise_sets_agree(self) -> None:
        for key in (
            "NOISE_DIR_NAMES",
            "NOISE_FILE_NAMES",
            "NOISE_FILE_SUFFIXES",
            "BYTECODE_SUFFIXES",
            "EXECUTABLE_SUFFIXES",
            "TEXT_FILE_SUFFIXES",
        ):
            verify_value = getattr(self.verify_mod, key)
            regenerator_value = getattr(self.regen_mod, key)
            self.assertEqual(
                verify_value,
                regenerator_value,
                f"{key} drifted between suite_verify.py and update_suite_manifest.py",
            )
            self.assertEqual(
                verify_value,
                globals()[key],
                f"{key} drifted from tests/test_noise_consistency.py",
            )

    def test_is_local_noise_matches_verify_source(self) -> None:
        # Noise dir names count only as parent directories, not as top-level files.
        for name in NOISE_DIR_NAMES:
            self.assertTrue(is_local_noise((name, "anything.json")))
            self.assertFalse(is_local_noise((name,)))
        for name in NOISE_FILE_NAMES:
            self.assertTrue(is_local_noise((name,)))
        for suffix in NOISE_FILE_SUFFIXES:
            self.assertTrue(is_local_noise(("file" + suffix,)))
        self.assertTrue(is_local_noise(("pkg", "__pycache__", "mod.pyc")))
        self.assertFalse(is_local_noise(("pkg", "mod.py")))
        samples = [
            (("a.py",), False),
            (("pkg", "mod.py"), False),
            ((".DS_Store",), True),
            (("pkg", "__pycache__", "mod.pyc"), True),
            (("pkg", "__pycache__", "payload.py"), False),
            ((".ruff_cache", "anything.json"), True),
            (("notes.txt~",), True),
            (("notes.txt.swp",), True),
        ]
        for parts, expected in samples:
            self.assertEqual(
                self.verify_mod.is_local_noise(parts),
                expected,
                f"suite_verify.is_local_noise({parts!r})",
            )
            self.assertEqual(
                self.regen_mod.is_local_noise(parts),
                expected,
                f"update_suite_manifest.is_local_noise({parts!r})",
            )

    def test_manifest_matches_disk_state(self) -> None:
        manifest = json.loads((CORE / "suite-manifest.json").read_text(encoding="utf-8"))
        files = manifest["files"]
        expected = _disk_file_index()
        self.assertEqual(
            sorted(files), sorted(expected), "manifest file list does not match disk"
        )
        for relative, digest in files.items():
            actual = text_sha256((SKILLS / relative).read_bytes())
            self.assertEqual(
                actual, digest, f"content hash mismatch for {relative}"
            )

    def test_regenerator_is_idempotent(self) -> None:
        before = (CORE / "suite-manifest.json").read_bytes()
        self._run(str(UPDATE_MANIFEST))
        after = (CORE / "suite-manifest.json").read_bytes()
        self.assertEqual(
            before, after, "regenerator changed an unchanged suite (not idempotent)"
        )

    def test_suite_verify_passes(self) -> None:
        self.assertIn(
            '"checked_files"',
            self._run(str(SUITE_VERIFY)),
            "suite_verify failed on the installed suite",
        )

    def test_suite_verify_accepts_a_crlf_text_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "skills"
            import shutil

            shutil.copytree(SKILLS, copied)
            text_suffixes = {".css", ".html", ".js", ".json", ".jsonl", ".md", ".py", ".yaml"}
            for path in copied.rglob("*"):
                if path.is_file() and path.suffix.casefold() in text_suffixes:
                    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            result = self.verify_mod.verify_suite(copied / "short-drama")
            manifest = json.loads(
                (copied / "short-drama/suite-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["checked_files"], len(manifest["files"]))

    def test_verify_rehashes_even_when_size_and_mtime_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "skills"
            import shutil

            shutil.copytree(SKILLS, copied)
            core = copied / "short-drama"
            self.verify_mod.verify_suite(core)
            target = copied / "short-drama" / "SKILL.md"
            original = target.read_bytes()
            stat = target.stat()
            mutated = bytearray(original)
            mutated[-2] = ord("X") if mutated[-2] != ord("X") else ord("Y")
            target.write_bytes(bytes(mutated))
            os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                self.verify_mod.verify_suite(core)

    def test_suite_text_hash_is_stable_across_crlf_checkouts(self) -> None:
        generator = _load_module(UPDATE_MANIFEST)
        samples = (
            b"one\ntwo\n",
            b"one\r\ntwo\r\n",
            b"embedded\x00bytes\r\n",
        )
        for data in samples:
            with self.subTest(data=data):
                self.assertEqual(generator.text_sha256(data), self.verify_mod.text_sha256(data))
        self.assertEqual(
            self.verify_mod.text_sha256(b"one\ntwo\n"),
            self.verify_mod.text_sha256(b"one\r\ntwo\r\n"),
        )
        self.assertNotEqual(
            self.verify_mod.text_sha256(b"one\ntwo\n"),
            self.verify_mod.text_sha256(b"one\rtwo\r"),
        )

    def test_suite_binary_hash_preserves_crlf_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lf_path = root / "payload.bin"
            crlf_path = root / "payload-copy.bin"
            lf_path.write_bytes(b"header\x00one\ntwo\n")
            crlf_path.write_bytes(b"header\x00one\r\ntwo\r\n")
            self.assertNotEqual(
                self.verify_mod.suite_file_sha256(lf_path),
                self.verify_mod.suite_file_sha256(crlf_path),
            )
            self.assertEqual(
                self.verify_mod.suite_file_sha256(lf_path),
                self.regen_mod.suite_file_sha256(lf_path),
            )

    def test_public_skill_contracts(self) -> None:
        for skill_dir in sorted(SKILLS.glob("short-drama*")):
            if not skill_dir.is_dir():
                continue
            name = skill_dir.name
            skill_md = skill_dir / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f"{name} missing SKILL.md")
            raw = skill_md.read_text(encoding="utf-8")
            match = _FRONTMATTER_RE.match(raw)
            self.assertIsNotNone(match, f"{name} SKILL.md missing frontmatter")
            frontmatter: dict[str, str] = {}
            for line in match.group(1).splitlines():
                parts = line.split(":", 1)
                if len(parts) == 2:
                    frontmatter[parts[0]] = parts[1].strip()
            self.assertIn("name", frontmatter)
            self.assertEqual(frontmatter["name"], name)
            self.assertTrue(frontmatter.get("description"))
            metadata = skill_dir / "agents" / "openai.yaml"
            self.assertTrue(metadata.is_file(), f"{name} missing agents/openai.yaml")
            interface = _parse_openai_interface(metadata.read_text(encoding="utf-8"))
            self.assertEqual(
                set(interface),
                {"display_name", "short_description", "default_prompt"},
                f"{name} openai.yaml interface keys are invalid",
            )
            self.assertTrue(interface["display_name"].strip())
            self.assertGreaterEqual(len(interface["short_description"]), 25)
            self.assertLessEqual(len(interface["short_description"]), 64)
            self.assertIn(f"${name}", interface["default_prompt"])


def _load_module(path: Path):
    """Import a sibling tool module by path so its constants are the same objects."""

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def _parse_openai_interface(content: str) -> dict[str, str]:
    interface: dict[str, str] = {}
    for line in content.splitlines():
        match = _OPENAI_RE.match(line)
        if match:
            interface[match.group(1)] = match.group(2)
    return interface


def _disk_file_index() -> dict[str, str]:
    """Recompute what update_suite_manifest.py would record on this tree."""

    index: dict[str, str] = {}
    for skill in sorted(SKILLS.glob("short-drama*")):
        if not skill.is_dir():
            continue
        name = skill.name
        for path in sorted(skill.rglob("*")):
            if not path.is_file() or is_local_noise(path.relative_to(skill).parts):
                continue
            relative = f"{name}/{path.relative_to(skill).as_posix()}"
            if relative == "short-drama/suite-manifest.json":
                continue
            if name != "short-drama" and relative == f"{name}/suite-ref.json":
                continue
            index[relative] = suite_file_sha256(path)
    return index


if __name__ == "__main__":
    unittest.main()
