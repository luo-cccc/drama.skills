#!/usr/bin/env python3
"""Regenerate skills/short-drama/suite-manifest.json and every child suite-ref.json.

Run after editing any file inside the nine skill directories:

    python3 tools/update_suite_manifest.py [repo-root]

The manifest pins the SHA-256 of every file under the nine skills, and each
child skill's suite-ref.json pins the manifest hash itself. The noise sets
below intentionally mirror `skills/short-drama/scripts/suite_verify.py` (its
`is_local_noise`); keep them in lockstep: anything the verifier ignores must be
ignored here, and anything the verifier reports must be hashed here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


NOISE_DIR_NAMES = frozenset({".ruff_cache", ".mypy_cache", ".pytest_cache"})
NOISE_FILE_NAMES = frozenset({".DS_Store"})
NOISE_FILE_SUFFIXES = ("~", ".swp", ".swo")
BYTECODE_SUFFIXES = (".pyc", ".pyo")
EXECUTABLE_SUFFIXES = (
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".js",
    ".mjs",
    ".cjs",
    ".rb",
    ".pl",
    ".php",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".command",
)
TEXT_FILE_SUFFIXES = frozenset(
    {".css", ".csv", ".html", ".js", ".json", ".jsonl", ".md", ".py", ".toml", ".tsv", ".txt", ".xml", ".yaml", ".yml"}
)


def text_sha256(data: bytes) -> str:
    """Hash text content in the suite's canonical LF form."""

    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def suite_file_sha256(path: Path) -> str:
    """Hash known text files canonically and all other files byte-for-byte."""

    data = path.read_bytes()
    if path.suffix.casefold() in TEXT_FILE_SUFFIXES:
        return text_sha256(data)
    return hashlib.sha256(data).hexdigest()


def is_local_noise(parts: tuple[str, ...]) -> bool:
    """Mirror of suite_verify.is_local_noise; keep the two in lockstep."""

    name = parts[-1]
    # Executable content is never noise, wherever it sits.
    if name.endswith(EXECUTABLE_SUFFIXES):
        return False
    # Bytecode caches regenerate at runtime, so the bytecode itself is
    # tolerated; anything else under them is not.
    if "__pycache__" in parts[:-1]:
        return name.endswith(BYTECODE_SUFFIXES)
    if any(part in NOISE_DIR_NAMES for part in parts[:-1]):
        return True
    return name in NOISE_FILE_NAMES or name.endswith(NOISE_FILE_SUFFIXES)


def regenerate(root: Path) -> tuple[str, int]:
    core = root / "skills" / "short-drama"
    if not (core / "suite-manifest.json").is_file():
        raise SystemExit(f"cannot locate suite manifest under {root}")
    skills_root = root / "skills"
    skills = sorted(entry for entry in skills_root.glob("short-drama*") if entry.is_dir())
    if len(skills) != 9:
        raise SystemExit(f"expected 9 skills, found {len(skills)}")

    files: dict[str, str] = {}
    for skill in skills:
        name = skill.name
        for path in sorted(skill.rglob("*")):
            if not path.is_file() or is_local_noise(path.relative_to(skill).parts):
                continue
            relative = f"{name}/{path.relative_to(skill).as_posix()}"
            if relative == "short-drama/suite-manifest.json":
                continue
            if name != "short-drama" and relative == f"{name}/suite-ref.json":
                continue
            files[relative] = suite_file_sha256(path)

    manifest = json.loads((core / "suite-manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = files
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (core / "suite-manifest.json").write_bytes(payload.encode("utf-8"))
    manifest_hash = text_sha256(payload.encode("utf-8"))

    for skill in skills:
        if skill.name == "short-drama":
            continue
        ref_path = skill / "suite-ref.json"
        reference = json.loads(ref_path.read_text(encoding="utf-8"))
        for key in (
            "suite",
            "suite_version",
            "contract_version",
            "core_skill",
            "recipe_version",
        ):
            reference[key] = manifest[key]
        reference["core_manifest"] = "../short-drama/suite-manifest.json"
        reference["core_manifest_sha256"] = manifest_hash
        ref_path.write_bytes(
            (json.dumps(reference, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
    return manifest_hash, len(files)


def main(argv: list[str] | None = None) -> int:
    root = (
        Path(argv[0]).resolve()
        if argv
        else Path(__file__).resolve().parents[1]
    )
    manifest_hash, file_count = regenerate(root)
    print(
        json.dumps(
            {"root": str(root), "manifest_sha256": manifest_hash, "files": file_count},
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
