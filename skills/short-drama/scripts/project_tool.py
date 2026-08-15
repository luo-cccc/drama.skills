#!/usr/bin/env python3
"""Deterministic project, recovery, and delivery operations.

Creative judgment stays in the skill documents and creator-authored files. This
module owns only filesystem integrity: five independent lifecycle axes,
recoverable multi-file publication, creator-safe status, and text/JSON delivery.
It uses no network or media service.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import shutil
import stat
import sys
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


# Creators run these scripts on whatever interpreter their machine provides, so
# an unsupported version must say so instead of failing inside an import.
MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "short-drama needs Python {}.{} or newer; this interpreter is {}.{}".format(
            *MINIMUM_PYTHON, sys.version_info.major, sys.version_info.minor
        )
    )

PROJECT_FILE = "short-drama.json"
# A machine-path token is the leading marker plus the rest of the path.
# Delivery scans the token form, so an exception must quote a whole path to
# release it. Declarations are checked against the complete form, which
# requires at least one character after the marker, so a marker on its own can
# never be declared and act as a wildcard over every path sharing it.
# A path token ends at whitespace or at a character that cannot continue a
# path: quotes and braces (so a path inside a JSON string is captured without
# its delimiters) and CJK punctuation (so prose that ends a sentence right
# after a path is captured without the full stop).
_PATH_TAIL = r"[^\s\"'`,;<>)\]}，。；：、！？（）【】「」]"
# The leading guard excludes only ASCII path-continuation characters, so a path
# written straight after a CJK character — the normal case in this product —
# is still detected, while a URL's own path is not double-reported.
MACHINE_PATH_TOKEN_RE = re.compile(
    rf"(?<![A-Za-z0-9_.\-])/(?:Users|home|private|var|tmp)/{_PATH_TAIL}*"
    rf"|(?<![A-Za-z0-9])[A-Za-z]:[\\/]{_PATH_TAIL}*"
)
MACHINE_PATH_COMPLETE_RE = re.compile(
    rf"(?<![A-Za-z0-9_.\-])/(?:Users|home|private|var|tmp)/{_PATH_TAIL}+"
    rf"|(?<![A-Za-z0-9])[A-Za-z]:[\\/]{_PATH_TAIL}+"
)
# On-screen text is a single displayed string, never a document. Bounding it
# stops a whole-file declaration from acting as a blanket release.
MAX_TEXT_EXCEPTION_LENGTH = 200
STATE_FILE = Path(".short-drama/state.json")
OPERATIONS_DIR = Path(".short-drama")
ABSENT_HASH: None = None
# One literal owns the project roots; every other view of them is derived.
# Spelling the set out per view is how an unrelated role ends up in PROJECT_DIRS —
# so `init` creates the directory — but missing from the alias table, so
# `_validate_publication_layout` then refuses every write into it.
CANONICAL_ROOTS = {
    "inputs": "输入",
    "development": "项目开发",
    "bible": "设定集",
    "episodes": "剧集",
    "delivery": "交付",
    "creator-decisions": "创作者决策",
    "reviews": "审查",
}
# Projects created before the Chinese layout name each directory after its role,
# so the legacy view is the identity map.
LEGACY_ROOTS = {role: role for role in CANONICAL_ROOTS}
ROOT_ROLE_ALIASES: dict[str, str] = {
    name.casefold(): role
    for roots in (CANONICAL_ROOTS, LEGACY_ROOTS)
    for role, name in roots.items()
}
LAYOUT_MODES = frozenset({"auto", "canonical", "legacy"})
# Bounded retries for the unserialized create-or-open of the lock file itself.
_LOCK_OPEN_ATTEMPTS = 8
LAYOUT_PINNING_ROLES = frozenset(
    {"development", "bible", "episodes", "delivery", "creator-decisions", "reviews"}
)
PROJECT_DIRS = (
    *CANONICAL_ROOTS.values(),
    "设定集/generation",
    ".short-drama/transactions",
    ".short-drama/accepted-snapshots",
    ".short-drama/conflicts",
    ".short-drama/locks",
    ".short-drama/tmp",
    ".short-drama/evidence",
)
# Episode directories are the unit the delivery completeness gate enumerates by
# prefix, so a path whose episode segment does not match this form is accepted,
# then silently skipped by _episode_coverage and never reconciled. Exactly one
# spelling per episode number is therefore required: three digits up to EP999,
# then unpadded. EP0001 is refused because it would be a second, invisible
# spelling of EP001 rather than a distinct episode.
EPISODE_ID_RE = re.compile(r"EP(?:[0-9]{3}|[1-9][0-9]{3,})")
SCENE_ID_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9])SC(?:[0-9]{3}|[1-9][0-9]{3,})(?![A-Z0-9])"
)
WINDOWS_FORBIDDEN_PATH_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_RESERVED_PATH_STEMS = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
        "com¹",
        "com²",
        "com³",
        "lpt¹",
        "lpt²",
        "lpt³",
    }
)
# Roots no stage may publish into, each with the reason a creator needs. Matched
# case-insensitively: this suite is developed on case-insensitive filesystems,
# where `Inputs/x.md` and `inputs/x.md` are the same file on disk, so a
# case-sensitive guard is not a guard at all.
PROTECTED_PUBLISH_ROLE_REASONS = {
    "inputs": "creator inputs are immutable publication sources",
    "delivery": "the delivery tree is written by the packaging gate, not by publication",
}
PROTECTED_PUBLISH_ROOTS = {
    name.casefold(): reason
    for role, reason in PROTECTED_PUBLISH_ROLE_REASONS.items()
    for name in (CANONICAL_ROOTS[role], LEGACY_ROOTS[role])
} | {".short-drama": "operational state cannot be a publication target"}
# Roots a stage may publish into. Anything else needs an explicit opt-in, so an
# ad-hoc creator file stays possible but never silent: a typo like `epsiodes/`
# otherwise builds a parallel tree that `status` never reports.
PUBLISHABLE_ROOT_ROLES = frozenset(
    {"development", "bible", "episodes", "creator-decisions", "reviews"}
)
# Both spellings, Chinese first — this is the "expected one of …" error text.
PUBLISHABLE_ROOTS = tuple(
    roots[role]
    for roots in (CANONICAL_ROOTS, LEGACY_ROOTS)
    for role in CANONICAL_ROOTS
    if role in PUBLISHABLE_ROOT_ROLES
)
# Declared artifact -> owning skill, transcribed from each stage SKILL.md's
# owned-output list and the single-owner registry in
# references/contract-and-ownership.md. Keys are casefolded; see
# _expected_path_owner.
#
# General artifacts are deliberately keyed on exact declared names rather than
# stage-directory prefixes. An episode directory holds artifacts from four
# skills, and a creator may legitimately place their own file beside them.
# Only the two explicitly declared per-scene families below use bounded
# subdirectory ownership; everything else unnamed stays owner-unconstrained.
DECLARED_PROJECT_ARTIFACT_OWNERS: dict[str, str] = {
    "development/creative-brief.md": "short-drama-develop",
    "development/story-engine.md": "short-drama-develop",
    "development/director-brief.md": "short-drama-develop",
    "development/adaptation-map.jsonl": "short-drama-develop",
    "development/series-arc.json": "short-drama-develop",
    "development/episode-intake-index.json": "short-drama-develop",
    "development/episode-map.jsonl": "short-drama-develop",
    "development/source-analysis/_index.json": "short-drama-novel-analyze",
    "development/source-analysis/_progress.md": "short-drama-novel-analyze",
    "development/source-analysis/triage.md": "short-drama-novel-analyze",
    "development/source-analysis/story-units.md": "short-drama-novel-analyze",
    "development/source-analysis/rhythm-and-emotion.md": "short-drama-novel-analyze",
    "development/source-analysis/characters.md": "short-drama-novel-analyze",
    "development/source-analysis/world.md": "short-drama-novel-analyze",
    "development/source-analysis/adaptation-value.md": "short-drama-novel-analyze",
    "development/source-analysis/episode-candidates.jsonl": "short-drama-novel-analyze",
    "development/lookdev-image-prompt-specs.jsonl": "short-drama-image-prompts",
    "development/lookdev-prompts.md": "short-drama-image-prompts",
    # Cross-episode identity ledgers. Every skill that names these reads them;
    # `short-drama-assets/SKILL.md:130` is the only declared writer.
    "bible/characters.jsonl": "short-drama-assets",
    "bible/looks.jsonl": "short-drama-assets",
    "bible/locations.jsonl": "short-drama-assets",
    "bible/location-views.jsonl": "short-drama-assets",
    "bible/props.jsonl": "short-drama-assets",
    "bible/prop-states.jsonl": "short-drama-assets",
    "bible/generation/asset-scope.jsonl": "short-drama-assets",
    "bible/generation/asset-models.jsonl": "short-drama-assets",
    "bible/generation/spatial-models.jsonl": "short-drama-assets",
    "bible/generation/variant-models.jsonl": "short-drama-assets",
    "bible/generation/view-contracts.jsonl": "short-drama-assets",
    "bible/generation/asset-baseline.md": "short-drama-assets",
    "bible/generation/canonical-fragments.jsonl": "short-drama-image-prompts",
    "bible/generation/canonical-prompt-library.md": "short-drama-image-prompts",
}
# Same, for the path below `episodes/<EP>/`.
DECLARED_EPISODE_ARTIFACT_OWNERS: dict[str, str] = {
    "episode-card.json": "short-drama-write",
    "beats.jsonl": "short-drama-write",
    "screenplay.md": "short-drama-write",
    "screenplay-index.jsonl": "short-drama-write",
    "voice-record-sheet.jsonl": "short-drama-write",
    "assets/occurrences.jsonl": "short-drama-assets",
    "assets/decisions.jsonl": "short-drama-assets",
    "assets/continuity.jsonl": "short-drama-assets",
    "assets/image-prompt-specs.jsonl": "short-drama-image-prompts",
    "assets/image-prompts.md": "short-drama-image-prompts",
    "storyboard/coverage.json": "short-drama-storyboard",
    "storyboard/shots.jsonl": "short-drama-storyboard",
    "storyboard/keyframes.jsonl": "short-drama-storyboard",
    "storyboard/keyframe-prompts.md": "short-drama-storyboard",
    "storyboard/motion-specs.jsonl": "short-drama-video-prompts",
    "storyboard/generation-clips.jsonl": "short-drama-video-prompts",
    "storyboard/delivery-containers.jsonl": "short-drama-video-prompts",
    "storyboard/video-prompts.md": "short-drama-video-prompts",
}
# These two optional layers have one independently accepted file per scene, so
# their `<SC>.jsonl` members are a safe owner namespace: unlike the episode or
# storyboard root, that declared filename carries no creator-defined or
# cross-skill artifact. Ownership is claimed for those members only, not for the
# directory as a whole — a `.json`, `.md`, or more deeply nested file beside them
# stays owner-unconstrained like any other undeclared path, because the contract
# names `<SC>.jsonl` and nothing else.
DECLARED_EPISODE_ARTIFACT_FAMILY_OWNERS: dict[str, str] = {
    "storyboard/coverage-auditions": "short-drama-storyboard",
    "storyboard/scene-visual-plans": "short-drama-storyboard",
}
DECLARED_PROJECT_ARTIFACT_FAMILY_OWNERS: dict[str, str] = {
    "development/source-analysis/chapters": "short-drama-novel-analyze",
}

LIFECYCLE_STATES: dict[str, tuple[str, ...]] = {
    "build_state": ("absent", "in_progress", "materialized", "stale", "failed"),
    "validation_state": ("not_run", "pass", "pass_with_warnings", "fail"),
    "creator_acceptance": ("not_requested", "pending", "accepted", "rejected"),
    "independent_review": (
        "not_requested",
        "provisional",
        "approve",
        "approve_with_notes",
        "revise",
    ),
    "delivery_gate": ("not_evaluated", "blocked", "ready", "delivered"),
}
LIFECYCLE_DEFAULTS = {
    "build_state": "absent",
    "validation_state": "not_run",
    "creator_acceptance": "not_requested",
    "independent_review": "not_requested",
    "delivery_gate": "not_evaluated",
}
DELIVERY_SUFFIXES = {".md", ".json", ".jsonl"}
FaultInjector = Callable[[str, dict[str, object]], None]


def _reject_json_constant(value: str) -> Any:
    raise json.JSONDecodeError(f"non-finite JSON number is not allowed: {value}", value, 0)


def _json_loads(value: str | bytes | bytearray, **kwargs: Any) -> Any:
    kwargs.setdefault("parse_constant", _reject_json_constant)
    return json.loads(value, **kwargs)


def _json_dumps(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("allow_nan", False)
    return json.dumps(value, **kwargs)


def _stdout_json(value: Any) -> str:
    """Render machine JSON in Unicode when stdout can encode it, otherwise ASCII-safe."""

    rendered = _json_dumps(value, ensure_ascii=False, sort_keys=True)
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        rendered.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return _json_dumps(value, ensure_ascii=True, sort_keys=True)
    return rendered


class TransactionError(RuntimeError):
    """Base class for a recoverable transaction failure."""


class TransactionConflictError(TransactionError):
    """A live file no longer matches either transaction-owned version."""


class StaleReadSetError(TransactionError):
    """An input changed after the transaction captured its read set."""


class RecoveryMaterialError(TransactionError):
    """A required immutable candidate or prior snapshot is unavailable."""


class PackageBlockedError(RuntimeError):
    """Delivery policy rejected one or more selected artifacts."""


class NonPortablePathError(ValueError):
    """A path spelling is rejected by a supported filesystem."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    # Windows cannot open a directory as a regular file for fsync. The file
    # itself is flushed before os.replace; POSIX additionally persists the
    # parent-directory entry here.
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_json(path: Path, document: dict[str, Any]) -> None:
    encoded = (
        _json_dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_bytes(path, encoded)


def _append_wal(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_json_dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    with path.open("ab") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _write_marker(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != b"committed\n":
            raise TransactionError(f"invalid commit marker: {path.name}")
        return
    # The marker becomes visible only after its complete bytes are durable. A
    # crash while writing the temporary therefore cannot masquerade as COMMIT.
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(b"committed\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def default_lifecycle() -> dict[str, str]:
    return dict(LIFECYCLE_DEFAULTS)


def apply_lifecycle_changes(
    current: Mapping[str, Any], changes: Mapping[str, Any]
) -> dict[str, Any]:
    unknown = sorted(set(changes) - set(LIFECYCLE_STATES))
    if unknown:
        raise ValueError(f"unknown lifecycle axes: {', '.join(unknown)}")
    result = dict(current)
    for axis, default in LIFECYCLE_DEFAULTS.items():
        value = result.get(axis, default)
        if value not in LIFECYCLE_STATES[axis]:
            raise ValueError(f"invalid {axis}: {value!r}")
        result[axis] = value
    for axis, value in changes.items():
        if value not in LIFECYCLE_STATES[axis]:
            raise ValueError(f"invalid {axis}: {value!r}")
        result[axis] = value
    return result


# Creator-facing artifacts follow the project language; prompt bodies follow
# prompt_language, which defaults to English because most image, video and voice
# generators handle English prompt text most reliably. Keeping them as two
# fields is the point: changing the language a creator reads must never silently
# change the language a generator is asked to render, and vice versa.
DEFAULT_PROMPT_LANGUAGE = "en"
DEFAULT_MAX_CLIP_SECONDS = 15.0
# A permissive BCP 47 shape. This validates form, not registry membership: a
# malformed tag is worth refusing at init, because it then propagates into every
# artifact that claims to follow it, and nothing downstream re-checks it.
LANGUAGE_TAG_RE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
ASPECT_RATIO_RE = re.compile(
    r"(?P<width>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?):"
    r"(?P<height>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)"
)


def normalize_language_tag(value: str, *, field: str) -> str:
    tag = value.strip()
    if not tag:
        raise ValueError(f"{field} must not be empty")
    if LANGUAGE_TAG_RE.fullmatch(tag) is None:
        raise ValueError(f"{field} is not a well-formed language tag: {value!r}")
    return tag


def normalize_aspect_ratio(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("aspect_ratio must use positive WIDTH:HEIGHT numbers")
    ratio = value.strip()
    match = ASPECT_RATIO_RE.fullmatch(ratio)
    if match is None:
        raise ValueError("aspect_ratio must use positive WIDTH:HEIGHT numbers")
    if float(match["width"]) <= 0 or float(match["height"]) <= 0:
        raise ValueError("aspect_ratio dimensions must be greater than zero")
    return ratio


def normalize_positive_seconds(value: str | int | float, *, field: str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a positive number of seconds") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(f"{field} must be a positive number of seconds")
    return seconds


def _effective_prompt_language(project: Mapping[str, Any]) -> str:
    """Resolve the prompt language a project is working under.

    Projects written before `prompt_language` existed have no such field; they
    work under the same default `init` would have chosen, so `status` and the
    review-bundle project summary report that default instead of `None`.
    """

    format_block = project.get("format")
    if isinstance(format_block, dict):
        value = format_block.get("prompt_language")
        if isinstance(value, str) and value:
            return value
    return DEFAULT_PROMPT_LANGUAGE


def initialize_project(
    path: Path,
    *,
    title: str,
    language: str,
    aspect_ratio: str,
    prompt_language: str = DEFAULT_PROMPT_LANGUAGE,
    max_clip_seconds: float = DEFAULT_MAX_CLIP_SECONDS,
    suite_root: Path | None = None,
) -> dict[str, Any]:
    root = path.expanduser().resolve()
    project_path = root / PROJECT_FILE
    if project_path.exists():
        raise FileExistsError(f"project already exists: {project_path}")

    normalized_language = normalize_language_tag(language, field="language")
    normalized_prompt_language = normalize_language_tag(
        prompt_language, field="prompt_language"
    )
    normalized_aspect_ratio = normalize_aspect_ratio(aspect_ratio)
    normalized_max_clip_seconds = normalize_positive_seconds(
        max_clip_seconds, field="max_clip_seconds"
    )

    root.mkdir(parents=True, exist_ok=True)
    for relative in PROJECT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)

    core = suite_root or Path(__file__).resolve().parents[1]
    manifest = _json_loads((core / "suite-manifest.json").read_text(encoding="utf-8"))
    template_path = core / "assets/project-template/short-drama.json"
    project = _json_loads(template_path.read_text(encoding="utf-8"))
    project.update(
        {
            "project_id": f"SD-{uuid.uuid4().hex[:12].upper()}",
            "title": title.strip() or "未命名短剧",
            "language": normalized_language,
            "suite_version": manifest["suite_version"],
            "contract_version": manifest["contract_version"],
            "created_at": utc_now(),
        }
    )
    project["format"]["aspect_ratio"] = normalized_aspect_ratio
    project["format"]["prompt_language"] = normalized_prompt_language
    project["format"]["generation_limits"]["max_clip_seconds"] = normalized_max_clip_seconds

    state = {
        "schema_version": manifest["contract_version"],
        "project_id": project["project_id"],
        "project_layout_mode": "auto",
        "updated_at": utc_now(),
        "artifacts": {},
        "blocked_transactions": {},
        "active_transaction": None,
        "last_action": "initialized",
    }

    # The discoverable project marker is last, so minimum state always exists.
    atomic_json(root / STATE_FILE, state)
    atomic_json(project_path, project)
    return {"project_root": str(root), "project": project, "state": state}


def find_project(start: Path) -> Path:
    candidate = start.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / PROJECT_FILE).is_file():
            return directory
    raise FileNotFoundError(f"no {PROJECT_FILE} found from {start}")


def _transaction_status(transaction: Path) -> str:
    if not (transaction / "manifest.json").is_file():
        return "incomplete"
    try:
        events = _read_wal(transaction / "wal.jsonl", tolerate_missing=True)
    except (OSError, UnicodeError, TransactionError):
        return "corrupt"
    names = {event.get("event") for event in events}
    if "BLOCKED" in names:
        return "blocked"
    if "ROLLED_BACK" in names or "STATE_APPLIED" in names:
        return "complete"
    return "needs_rollforward" if _has_commit(transaction) else "needs_rollback"


def _open_directory_at(directory_fd: int, parts: Iterable[str]) -> int:
    descriptor = os.dup(directory_fd)
    try:
        for part in parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_regular_at(directory_fd: int, relative: str | Path) -> bytes:
    pure = PurePosixPath(relative)
    parent_fd = _open_directory_at(directory_fd, pure.parts[:-1])
    descriptor = -1
    try:
        descriptor = os.open(
            pure.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise TransactionConflictError(f"project path is not a regular file: {relative}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _live_hash_at(directory_fd: int, relative: str) -> str | None:
    try:
        content = _read_regular_at(directory_fd, relative)
    except FileNotFoundError:
        return ABSENT_HASH
    return sha256_bytes(content)


def _fresh_baselines(effective_artifacts: Mapping[str, Any]) -> list[str]:
    """Owner skills whose artifact type already has a non-provisional fresh verdict.

    Review routing (L1 fresh vs L1.5 cold_read) keys off this list; deriving it
    from state keeps the decision out of model memory.
    """

    owners: set[str] = set()
    for record in effective_artifacts.values():
        if not isinstance(record, dict):
            continue
        evidence = record.get("review_evidence")
        if not isinstance(evidence, dict):
            continue
        independence = evidence.get("reviewer_independence")
        if not isinstance(independence, dict):
            continue
        if independence.get("effective_review_mode") != "fresh_agent":
            continue
        if str(evidence.get("verdict", "")).casefold() == "provisional":
            continue
        owner = record.get("owner")
        if isinstance(owner, str) and owner:
            owners.add(owner)
    return sorted(owners)


def _build_project_status(
    *,
    project: Mapping[str, Any],
    state: Mapping[str, Any],
    effective_artifacts: Mapping[str, Any],
    transaction_counts: dict[str, int],
    layout: Mapping[str, Any],
    project_root: str,
) -> dict[str, Any]:
    lifecycle: dict[str, dict[str, int]] = {axis: {} for axis in LIFECYCLE_STATES}
    for record in effective_artifacts.values():
        if not isinstance(record, dict):
            continue
        for axis in LIFECYCLE_STATES:
            value = str(record.get(axis, "unknown"))
            lifecycle[axis][value] = lifecycle[axis].get(value, 0) + 1

    blocked = state.get("blocked_transactions", {})
    blocked_count = len(blocked) if isinstance(blocked, dict) else 0
    needs_recovery = any(
        transaction_counts.get(name, 0)
        for name in (
            "incomplete",
            "corrupt",
            "needs_rollback",
            "needs_rollforward",
            "blocked",
        )
    ) or bool(blocked_count)
    pending_transactions = any(
        transaction_counts.get(name, 0)
        for name in ("incomplete", "corrupt", "needs_rollback", "needs_rollforward")
    )
    return {
        "project_root": project_root,
        "project_id": project.get("project_id"),
        "title": project.get("title"),
        "project_language": project.get("language"),
        "prompt_language": _effective_prompt_language(project),
        "current_checkpoint": project.get("current_checkpoint"),
        "layout": dict(layout),
        "artifact_build_states": lifecycle["build_state"],
        "lifecycle": lifecycle,
        "fresh_baselines": _fresh_baselines(effective_artifacts),
        "active_transaction": state.get("active_transaction"),
        "last_action": state.get("last_action"),
        "recovery": {
            "needed": bool(needs_recovery),
            "transaction_counts": transaction_counts,
            "blocked_count": blocked_count,
            "next_action": (
                "recover"
                if pending_transactions
                else "resolve_conflict"
                if blocked_count
                else "continue"
            ),
        },
    }


def _reader_hash(
    read_regular: Callable[[str], bytes], relative: str
) -> str | None:
    try:
        return sha256_bytes(read_regular(relative))
    except FileNotFoundError:
        return ABSENT_HASH


def _effective_lifecycle_records_from_reader(
    read_regular: Callable[[str], bytes], artifacts: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Overlay live drift using a caller-supplied, root-confined reader."""

    effective = {
        str(artifact_id): dict(record)
        for artifact_id, record in artifacts.items()
        if isinstance(artifact_id, str) and isinstance(record, dict)
    }
    direct_stale: list[tuple[str, dict[str, str | None]]] = []
    for artifact_id, record in effective.items():
        changed: dict[str, str | None] = {}
        for relative, expected in _current_record_targets(record).items():
            try:
                normalized = _relative_path(relative)
                actual = _reader_hash(read_regular, normalized)
            except (OSError, ValueError, TransactionConflictError):
                actual = None
            if actual != expected:
                changed[relative] = actual
        if changed:
            direct_stale.append((artifact_id, changed))
    stale_ids = {artifact_id for artifact_id, _ in direct_stale}
    for artifact_id, record in effective.items():
        if artifact_id in stale_ids or record.get("creator_acceptance") != "accepted":
            continue
        try:
            inputs = _input_bindings(record, "accepted_inputs")
            record_inputs = _input_record_bindings(record, "accepted_input_records")
            unknown_records = set(record_inputs) - set(inputs)
            if unknown_records:
                raise ValueError("record binding has no matching input")
            for relative, expected in inputs.items():
                normalized = _relative_path(relative)
                if normalized in record_inputs:
                    content = read_regular(normalized)
                    live_records = _record_digests(
                        content, normalized, record_inputs[normalized]
                    )
                    if any(
                        live_records.get(selector) != digest
                        for selector, digest in record_inputs[normalized].items()
                    ):
                        raise ValueError("accepted input record changed")
                elif _reader_hash(read_regular, normalized) != expected:
                    raise ValueError("accepted input changed")
        except (OSError, ValueError, UnicodeError, TransactionConflictError):
            targets = record.get("accepted_targets")
            direct_stale.append(
                (
                    artifact_id,
                    {path: None for path in targets} if isinstance(targets, dict) else {},
                )
            )
            stale_ids.add(artifact_id)
    stale_changes = _stale_lifecycle_changes()
    for artifact_id, changed in direct_stale:
        effective[artifact_id] = apply_lifecycle_changes(
            effective[artifact_id], stale_changes
        )
        downstream = _downstream_stale_changes(
            {"artifacts": artifacts},
            publishing_artifact=artifact_id,
            candidate_targets=changed,
        )
        for dependent in downstream:
            if dependent in effective:
                effective[dependent] = apply_lifecycle_changes(
                    effective[dependent], stale_changes
                )
    return effective


def _project_layout_from_reader(
    state: Mapping[str, Any],
    scan_directory: Callable[[str], list[Mapping[str, Any]]],
) -> dict[str, Any]:
    recorded = state.get("project_layout_mode", "auto")
    if recorded not in LAYOUT_MODES:
        recorded = "auto"
    canonical_roles: set[str] = set()
    legacy_roles: set[str] = set()
    nonstandard_roots: list[str] = []
    unsafe_roots: list[str] = []
    for entry in scan_directory("."):
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        role = _root_role(name)
        if role not in LAYOUT_PINNING_ROLES:
            continue
        if entry.get("reparse"):
            unsafe_roots.append(name)
            continue
        if entry.get("kind") != "directory":
            continue
        try:
            has_content = bool(scan_directory(name))
        except (FileNotFoundError, OSError, ValueError):
            unsafe_roots.append(name)
            continue
        if not has_content:
            continue
        if name == CANONICAL_ROOTS[role]:
            canonical_roles.add(role)
        elif name == LEGACY_ROOTS[role]:
            legacy_roles.add(role)
        else:
            nonstandard_roots.append(name)
    detected_modes = {
        mode
        for mode, roles in (
            ("canonical", canonical_roles),
            ("legacy", legacy_roles),
        )
        if roles
    }
    conflict = bool(nonstandard_roots or unsafe_roots) or len(detected_modes) > 1 or (
        recorded in {"canonical", "legacy"}
        and detected_modes
        and detected_modes != {recorded}
    )
    if conflict:
        mode = "mixed"
    elif recorded in {"canonical", "legacy"}:
        mode = recorded
    elif detected_modes:
        mode = next(iter(detected_modes))
    else:
        mode = "canonical"
    roots = CANONICAL_ROOTS if mode != "legacy" else LEGACY_ROOTS
    return {
        "mode": mode,
        "pinned": recorded != "auto" or bool(detected_modes),
        "roots": dict(roots),
        "nonstandardRoots": sorted(nonstandard_roots),
        "unsafeRoots": sorted(unsafe_roots),
    }


def _transaction_status_from_reader(
    transaction: str,
    read_regular: Callable[[str], bytes],
    scan_directory: Callable[[str], list[Mapping[str, Any]]],
) -> str:
    try:
        entries = {
            str(entry.get("name")): entry for entry in scan_directory(transaction)
        }
    except (FileNotFoundError, OSError, ValueError):
        return "corrupt"
    manifest = entries.get("manifest.json")
    if manifest is None:
        return "incomplete"
    if manifest.get("kind") != "file" or manifest.get("reparse"):
        return "corrupt"
    wal_path = f"{transaction}/wal.jsonl"
    try:
        content = read_regular(wal_path)
    except FileNotFoundError:
        content = b""
    except (OSError, TransactionError):
        return "corrupt"
    events: list[dict[str, Any]] = []
    try:
        for line in content.decode("utf-8").splitlines():
            if not line.strip():
                continue
            event = _json_loads(line)
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                return "corrupt"
            events.append(event)
    except (UnicodeError, json.JSONDecodeError):
        return "corrupt"
    names = {event.get("event") for event in events}
    if "BLOCKED" in names:
        return "blocked"
    if "ROLLED_BACK" in names or "STATE_APPLIED" in names:
        return "complete"
    marker = entries.get("COMMIT")
    committed = bool(
        marker is not None
        and marker.get("kind") == "file"
        and not marker.get("reparse")
    )
    return "needs_rollforward" if committed else "needs_rollback"


def project_status_from_reader(
    read_regular: Callable[[str], bytes],
    scan_directory: Callable[[str], list[Mapping[str, Any]]],
    *,
    project_root: str,
) -> dict[str, Any]:
    """Build project status through a storage backend's confined read API."""

    project = _json_loads(read_regular(PROJECT_FILE).decode("utf-8"))
    if not isinstance(project, dict):
        raise ValueError("short-drama.json must contain a JSON object")
    try:
        state = _json_loads(read_regular(STATE_FILE.as_posix()).decode("utf-8"))
    except FileNotFoundError:
        state = {}
    if not isinstance(state, dict):
        raise ValueError("project state must contain a JSON object")
    artifacts_value = state.get("artifacts")
    artifacts = artifacts_value if isinstance(artifacts_value, dict) else {}
    transaction_counts: dict[str, int] = {}
    try:
        transactions = scan_directory(".short-drama/transactions")
    except FileNotFoundError:
        transactions = []
    except (OSError, ValueError):
        transactions = [
            {"name": "<corrupt>", "kind": "directory", "reparse": True}
        ]
    for entry in transactions:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        if entry.get("reparse"):
            status = "corrupt"
        elif entry.get("kind") != "directory":
            continue
        else:
            status = _transaction_status_from_reader(
                f".short-drama/transactions/{name}",
                read_regular,
                scan_directory,
            )
        transaction_counts[status] = transaction_counts.get(status, 0) + 1
    return _build_project_status(
        project=project,
        state=state,
        effective_artifacts=_effective_lifecycle_records_from_reader(
            read_regular, artifacts
        ),
        transaction_counts=transaction_counts,
        layout=_project_layout_from_reader(state, scan_directory),
        project_root=project_root,
    )


def project_path_lifecycle_from_reader(
    read_regular: Callable[[str], bytes], relative: str | Path
) -> dict[str, Any] | None:
    """Return one path's lifecycle through a confined storage reader."""

    normalized = _relative_path(relative)
    try:
        state = _json_loads(read_regular(STATE_FILE.as_posix()).decode("utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(state, dict):
        raise ValueError("project state must contain a JSON object")
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    effective = _effective_lifecycle_records_from_reader(read_regular, artifacts)
    matches = [
        (artifact_id, record)
        for artifact_id, record in effective.items()
        if any(
            isinstance(record.get(key), dict) and normalized in record[key]
            for key in ("candidate_targets", "accepted_targets")
        )
    ]
    if len(matches) != 1:
        return None
    artifact_id, record = matches[0]
    return {
        "artifactId": artifact_id,
        **{
            axis: record.get(axis, LIFECYCLE_DEFAULTS[axis])
            for axis in LIFECYCLE_STATES
        },
    }


def _project_status_from_root(
    root: Path, *, project_root: str | None = None
) -> dict[str, Any]:
    def read_regular(relative: str) -> bytes:
        try:
            return _read_project_regular(root, relative)
        except ValueError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                raise FileNotFoundError(relative) from exc
            raise

    def scan_directory(relative: str) -> list[Mapping[str, Any]]:
        directory = root if relative == "." else _project_path(root, relative)
        entries: list[Mapping[str, Any]] = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                try:
                    details = entry.stat(follow_symlinks=False)
                except OSError:
                    entries.append(
                        {"name": entry.name, "kind": "other", "reparse": True}
                    )
                    continue
                attributes = getattr(details, "st_file_attributes", 0)
                reparse = entry.is_symlink() or bool(attributes & 0x400)
                kind = (
                    "directory"
                    if stat.S_ISDIR(details.st_mode)
                    else "file"
                    if stat.S_ISREG(details.st_mode)
                    else "other"
                )
                entries.append(
                    {"name": entry.name, "kind": kind, "reparse": reparse}
                )
        return entries

    return project_status_from_reader(
        read_regular,
        scan_directory,
        project_root=project_root or str(root),
    )


def project_status(path: Path) -> dict[str, Any]:
    root = find_project(path)
    return _project_status_from_root(root)


def _load_suite_verifier() -> Any:
    """Load the sibling suite_verify.py in-process, without a subprocess.

    `preflight` must not pay for a second interpreter startup, and the module
    is loaded under a unique name so loading it here never shadows or reloads
    a suite_verify already imported by a caller.
    """

    script = Path(__file__).resolve().parent / "suite_verify.py"
    spec = importlib.util.spec_from_file_location("short_drama_suite_verify", script)
    if spec is None or spec.loader is None:
        raise ValueError("cannot locate sibling suite_verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight_project(path: Path) -> dict[str, Any]:
    """One-process entry gate: suite verify + recover + compact status.

    Replaces the three separate calls the runtime preflight used to make
    (suite_verify.py, recover, status) with a single interpreter run and a
    single compact JSON document, so an entry needs one tool call instead of
    three and does not have to carry earlier command outputs in model context.
    The suite check hashes every manifest file's live bytes; recover still
    verifies every interrupted transaction's material bytes before touching
    anything.
    """

    verifier = _load_suite_verifier()
    core = Path(__file__).resolve().parents[1]
    suite = verifier.verify_suite(core)
    root = find_project(path)
    recovery = recover_project(root)
    status = project_status(root)
    return {
        "project_root": str(root),
        "suite": {
            "checked_skills": suite["checked_skills"],
            "checked_files": suite["checked_files"],
            "verify_cache": suite["verify_cache"],
        },
        "recovery": {
            "needed": recovery["checked"] > 0,
            "checked": recovery["checked"],
            "blocked": recovery["blocked"],
        },
        "status": status,
    }


def project_status_at(
    directory_fd: int, *, project_root: str | None = None
) -> dict[str, Any]:
    """Read project status relative to a caller-pinned directory descriptor."""

    if not isinstance(directory_fd, int) or directory_fd < 0:
        raise ValueError("directory_fd must be an open directory descriptor")
    details = os.fstat(directory_fd)
    if not stat.S_ISDIR(details.st_mode):
        raise ValueError("directory_fd must reference a directory")
    def read_regular(relative: str) -> bytes:
        return _read_regular_at(directory_fd, relative)

    def scan_directory(relative: str) -> list[Mapping[str, Any]]:
        pure = PurePosixPath(relative)
        target_fd = _open_directory_at(directory_fd, pure.parts if relative != "." else ())
        try:
            entries: list[Mapping[str, Any]] = []
            with os.scandir(target_fd) as iterator:
                for entry in iterator:
                    reparse = entry.is_symlink()
                    kind = (
                        "directory"
                        if entry.is_dir(follow_symlinks=False)
                        else "file"
                        if entry.is_file(follow_symlinks=False)
                        else "other"
                    )
                    entries.append(
                        {"name": entry.name, "kind": kind, "reparse": reparse}
                    )
            return entries
        finally:
            os.close(target_fd)

    return project_status_from_reader(
        read_regular,
        scan_directory,
        project_root=project_root or "pinned-project",
    )


def _relative_path(value: str | Path, *, allow_operations: bool = False) -> str:
    raw = str(value).replace("\\", "/")
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise ValueError(f"unsafe project-relative path: {value!s}")
    for part in pure.parts:
        stem = part.split(".", 1)[0].casefold()
        if (
            part.endswith((" ", "."))
            or any(ord(character) < 32 or ord(character) == 127 for character in part)
            or any(character in WINDOWS_FORBIDDEN_PATH_CHARACTERS for character in part)
            or stem in WINDOWS_RESERVED_PATH_STEMS
        ):
            raise NonPortablePathError(f"unsafe project-relative path: {value!s}")
    relative = pure.as_posix()
    if not allow_operations and pure.parts[0].casefold() == ".short-drama":
        raise ValueError("operational state cannot be a publication target")
    return relative


def normalize_project_relative_path(
    value: str | Path, *, allow_operations: bool = False
) -> str:
    """Return the suite's canonical, portable project-relative path spelling."""

    return _relative_path(value, allow_operations=allow_operations)


def _portable_path_key(relative: str) -> str:
    """Return the path identity shared by case-insensitive Unicode filesystems."""

    return unicodedata.normalize("NFC", relative).casefold()


def _remember_portable_path(
    seen: dict[str, str],
    relative: str,
    *,
    label: str,
    error_type: type[Exception] = ValueError,
) -> None:
    key = _portable_path_key(relative)
    previous = seen.get(key)
    if previous is not None:
        raise error_type(
            f"{label} paths collide on a portable filesystem: {previous} and {relative}"
        )
    seen[key] = relative


def _normalize_path_values(
    values: Iterable[str | Path],
    *,
    label: str,
    allow_operations: bool = False,
) -> list[str]:
    normalized: list[str] = []
    seen: dict[str, str] = {}
    for raw in values:
        relative = _relative_path(raw, allow_operations=allow_operations)
        _remember_portable_path(seen, relative, label=label)
        normalized.append(relative)
    return normalized


def _root_role(name: str) -> str | None:
    """Return one stable machine role for either Chinese or legacy root names."""

    return ROOT_ROLE_ALIASES.get(name.casefold())


def is_protected_project_text(value: str | Path) -> bool:
    """Return the shared Dashboard protection policy for project text paths."""

    raw = str(value).replace("\\", "/")
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or any(
        part in ("", ".", "..") for part in pure.parts
    ):
        return True
    return (
        pure.name.casefold() == PROJECT_FILE
        or pure.parts[0].casefold() == ".short-drama"
        or _root_role(pure.parts[0]) == "delivery"
    )


def _root_layout_mode(name: str) -> str | None:
    role = _root_role(name)
    if role is None:
        return None
    if name == CANONICAL_ROOTS[role]:
        return "canonical"
    if name == LEGACY_ROOTS[role]:
        return "legacy"
    return None


def _directory_has_content(path: Path) -> bool:
    try:
        details = os.lstat(path)
        if stat.S_ISLNK(details.st_mode):
            return True
        if not stat.S_ISDIR(details.st_mode):
            return False
        return any(path.iterdir())
    except FileNotFoundError:
        return False


def _project_layout_from_root(root: Path) -> dict[str, Any]:
    state = _read_state(root) if (root / STATE_FILE).is_file() else {}
    recorded = state.get("project_layout_mode", "auto")
    if recorded not in LAYOUT_MODES:
        recorded = "auto"
    canonical_roles = sorted(
        role
        for role, name in CANONICAL_ROOTS.items()
        if role in LAYOUT_PINNING_ROLES
        if _directory_has_content(root / name)
    )
    legacy_roles = sorted(
        role
        for role, name in LEGACY_ROOTS.items()
        if role in LAYOUT_PINNING_ROLES
        if _directory_has_content(root / name)
    )
    nonstandard_roots = sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_symlink() or entry.is_dir()
        if (role := _root_role(entry.name)) in LAYOUT_PINNING_ROLES
        if entry.name not in {CANONICAL_ROOTS[role], LEGACY_ROOTS[role]}
        if _directory_has_content(entry)
    )
    unsafe_roots = sorted(
        entry.name
        for entry in root.iterdir()
        if _root_role(entry.name) in LAYOUT_PINNING_ROLES
        if entry.is_symlink()
    )
    detected_modes = {
        mode
        for mode, roles in (
            ("canonical", canonical_roles),
            ("legacy", legacy_roles),
        )
        if roles
    }
    conflict = bool(nonstandard_roots or unsafe_roots) or len(detected_modes) > 1 or (
        recorded in {"canonical", "legacy"}
        and detected_modes
        and detected_modes != {recorded}
    )
    if conflict:
        mode = "mixed"
    elif recorded in {"canonical", "legacy"}:
        mode = recorded
    elif detected_modes:
        mode = next(iter(detected_modes))
    else:
        mode = "canonical"
    roots = CANONICAL_ROOTS if mode != "legacy" else LEGACY_ROOTS
    return {
        "mode": mode,
        "pinned": recorded != "auto" or bool(detected_modes),
        "roots": dict(roots),
        "nonstandardRoots": nonstandard_roots,
        "unsafeRoots": unsafe_roots,
    }


def project_layout(path: Path) -> dict[str, Any]:
    """Resolve one project-wide root layout while exposing mixed trees safely."""

    return _project_layout_from_root(find_project(path))


def _validate_project_output_layout(root: Path, relatives: Iterable[str]) -> str | None:
    # Only the roots that can *prove* a layout may choose one. `输入/` and
    # unregistered roots are excluded from detection (LAYOUT_PINNING_ROLES), so
    # letting them pin would record a family no stage directory on disk supports —
    # one `--allow-unregistered-path` write into an ad-hoc English directory
    # would lock a brand-new all-Chinese project into legacy and refuse every
    # later Chinese publish, with no supported way to undo it.
    families = {
        family
        for relative in relatives
        if (part := PurePosixPath(relative).parts[0])
        if _root_role(part) in LAYOUT_PINNING_ROLES
        if (family := _root_layout_mode(part)) is not None
    }
    if len(families) > 1:
        raise ValueError("不能在同一事务中混用中文与旧版英文目录")
    family = next(iter(families), None)
    layout = project_layout(root)
    if layout["mode"] == "mixed":
        raise ValueError("项目同时包含中文与旧版英文阶段目录，请先迁移并合并")
    if family is not None and layout["pinned"] and family != layout["mode"]:
        expected = "中文" if layout["mode"] == "canonical" else "旧版英文"
        raise ValueError(f"项目已使用{expected}目录布局，不能创建另一套平行目录")
    return family


def _layout_root_for_source(root: Path, role: str, source_root: str | None = None) -> str:
    """Choose a matching output root without mixing layouts implicitly."""

    layout = project_layout(root)
    if layout["mode"] == "mixed":
        raise ValueError("项目同时包含中文与旧版英文阶段目录，请先迁移并合并")
    if source_root is not None and _root_role(source_root) == role:
        family = _root_layout_mode(source_root)
        if layout["pinned"] and family != layout["mode"]:
            raise ValueError("源目录与项目布局不一致")
        if family == "canonical":
            return CANONICAL_ROOTS[role]
        if family == "legacy":
            return LEGACY_ROOTS[role]
    if layout["pinned"]:
        return str(layout["roots"][role])
    canonical = CANONICAL_ROOTS[role]
    legacy = LEGACY_ROOTS[role]
    canonical_exists = (root / canonical).exists()
    legacy_exists = (root / legacy).exists()
    if canonical_exists and legacy_exists:
        canonical_has_content = any((root / canonical).iterdir())
        legacy_has_content = any((root / legacy).iterdir())
        if canonical_has_content and legacy_has_content:
            raise ValueError(
                f"同一目录职责同时存在 {canonical}/ 与 {legacy}/，请先合并后再继续"
            )
        return canonical if canonical_has_content or not legacy_has_content else legacy
    if canonical_exists:
        return canonical
    if legacy_exists:
        return legacy
    return canonical


def _validate_publication_layout(
    relative: str, *, owner: str | None = None, allow_unregistered: bool = False
) -> None:
    """Reject a publication target that breaks the project layout contract.

    Deliberately NOT part of _relative_path. That function also normalizes
    paths already recorded in a write-ahead log, and applying today's layout
    policy to yesterday's manifest would make an interrupted transaction
    unrecoverable: rollback would raise instead of restoring the creator's
    prior bytes, and every later `recover` would re-report the same block.
    Layout is therefore checked only where a new path is minted.
    """

    pure = PurePosixPath(relative)
    first = pure.parts[0].casefold()
    role = _root_role(pure.parts[0])
    reason = PROTECTED_PUBLISH_ROOTS.get(first)
    if reason is not None:
        raise ValueError(reason)
    # Compared by basename, not by full path: a planted development/short-drama.json
    # makes find_project treat that subdirectory as its own project root, so a
    # creator running `status` from inside it reads the decoy.
    if pure.name.casefold() == PROJECT_FILE:
        raise ValueError("creator authority file cannot be a publication target")
    if role == "episodes":
        if len(pure.parts) < 3:
            raise ValueError(
                "episode artifacts live in 剧集/<EP>/"
                f"（兼容 episodes/<EP>/）：{relative}"
            )
        if EPISODE_ID_RE.fullmatch(pure.parts[1]) is None:
            raise ValueError(
                f"episode directory must use an EP001-style identifier: {pure.parts[1]}"
            )
    if not allow_unregistered and role not in PUBLISHABLE_ROOT_ROLES:
        raise ValueError(
            f"{pure.parts[0]} is not a project stage directory; "
            f"expected one of {', '.join(PUBLISHABLE_ROOTS)}"
        )
    if owner is not None:
        expected = _expected_path_owner(relative)
        if expected is not None and owner != expected:
            raise ValueError(f"{expected} owns {relative}, not {owner}")
    if role is not None and pure.parts[0] not in {
        CANONICAL_ROOTS[role],
        LEGACY_ROOTS[role],
    }:
        raise ValueError(f"阶段目录大小写或拼写不规范：{pure.parts[0]}")


def _expected_path_owner(relative: str) -> str | None:
    # Casefolded like every other path guard here. A case-sensitive lookup
    # would let `Episodes/EP001/screenplay.md` past the ownership check and,
    # on a case-insensitive filesystem, overwrite the very artifact the check
    # protects.
    pure = PurePosixPath(relative)
    role = _root_role(pure.parts[0])
    folded_parts = tuple(part.casefold() for part in pure.parts)
    if role == "episodes" and len(pure.parts) >= 3:
        remainder = PurePosixPath(*folded_parts[2:]).as_posix()
        exact = DECLARED_EPISODE_ARTIFACT_OWNERS.get(remainder)
        if exact is not None:
            return exact
        remainder_parts = PurePosixPath(remainder).parts
        if len(remainder_parts) == 3 and remainder_parts[-1].endswith(".jsonl"):
            family = PurePosixPath(*remainder_parts[:2]).as_posix()
            return DECLARED_EPISODE_ARTIFACT_FAMILY_OWNERS.get(family)
        return None
    if role is None:
        return None
    normalized = PurePosixPath(role, *folded_parts[1:]).as_posix()
    exact = DECLARED_PROJECT_ARTIFACT_OWNERS.get(normalized)
    if exact is not None:
        return exact
    normalized_parts = PurePosixPath(normalized).parts
    if len(normalized_parts) == 4 and normalized_parts[-1].endswith(".md"):
        family = PurePosixPath(*normalized_parts[:3]).as_posix()
        return DECLARED_PROJECT_ARTIFACT_FAMILY_OWNERS.get(family)
    return None


def _project_path(root: Path, relative: str) -> Path:
    target = root / relative
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise TransactionConflictError(
                f"publication parent cannot be a symlink: {part}"
            )
    resolved_parent = target.parent.resolve()
    if not resolved_parent.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes project root: {relative}")
    return target


def _read_project_regular(root: Path, relative: str) -> bytes:
    """Read one project file through a descriptor whose identity is revalidated."""

    def identity(value: os.stat_result) -> tuple[int, int, int]:
        return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)

    target = _project_path(root, relative)
    try:
        before = os.lstat(target)
    except FileNotFoundError as error:
        raise ValueError(f"project file is unavailable: {relative}") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise TransactionConflictError(f"project path is not a regular file: {relative}")
    descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        current = os.lstat(target)
        if identity(before) != identity(opened) or identity(current) != identity(opened):
            raise TransactionConflictError(f"project path changed while opening: {relative}")
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(root.resolve()):
            raise TransactionConflictError(f"project path escaped while opening: {relative}")
        verified = os.lstat(target)
        if identity(verified) != identity(opened):
            raise TransactionConflictError(f"project path changed while opening: {relative}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _secure_project_dir_fd() -> bool:
    return (
        os.name != "nt"
        and bool(getattr(os, "O_DIRECTORY", 0))
        and bool(getattr(os, "O_NOFOLLOW", 0))
    )


@contextlib.contextmanager
def _open_project_directory(root: Path) -> Iterator[int]:
    def identity(value: os.stat_result) -> tuple[int, int, int]:
        return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    before = os.lstat(root)
    descriptor = os.open(root, flags)
    try:
        opened = os.fstat(descriptor)
        if stat.S_ISLNK(before.st_mode) or identity(before) != identity(opened):
            raise TransactionConflictError("project root changed while opening")
        yield descriptor
    finally:
        os.close(descriptor)


def _live_project_hash(root: Path, relative: str) -> str | None:
    if _secure_project_dir_fd():
        with _open_project_directory(root) as directory_fd:
            return _live_hash_at(directory_fd, relative)
    target = _project_path(root, relative)
    try:
        return sha256_bytes(_read_project_regular(root, relative))
    except ValueError:
        if not target.exists():
            return ABSENT_HASH
        raise


def _ensure_project_parent(root: Path, relative: str) -> os.stat_result:
    parts = PurePosixPath(relative).parts[:-1]
    if _secure_project_dir_fd():
        with _open_project_directory(root) as directory_fd:
            parent_fd = os.dup(directory_fd)
            try:
                for part in parts:
                    child_fd = _open_or_create_directory_at(parent_fd, part)
                    os.close(parent_fd)
                    parent_fd = child_fd
                return os.fstat(parent_fd)
            finally:
                os.close(parent_fd)
    parent = _project_path(root, relative).parent
    parent.mkdir(parents=True, exist_ok=True)
    details = os.lstat(parent)
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise TransactionConflictError("publication parent is not a directory")
    if not parent.resolve().is_relative_to(root.resolve()):
        raise TransactionConflictError("publication parent escaped the project")
    return details


def _live_hash(path: Path) -> str | None:
    if not path.exists():
        return ABSENT_HASH
    if path.is_symlink() or not path.is_file():
        raise TransactionConflictError(f"target is not a regular file: {path.name}")
    return sha256_file(path)


def _artifact_directory(artifact_id: str) -> str:
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", artifact_id).strip("-.") or "artifact"
    return f"{label[:48]}-{sha256_bytes(artifact_id.encode('utf-8'))[:12]}"


def _snapshot_file(root: Path, artifact_id: str, digest: str) -> Path:
    return (
        root
        / ".short-drama/accepted-snapshots"
        / _artifact_directory(artifact_id)
        / digest
        / "content"
    )


def _preserve_snapshot(root: Path, artifact_id: str, content: bytes) -> str:
    digest = sha256_bytes(content)
    snapshot = _snapshot_file(root, artifact_id, digest)
    if snapshot.exists():
        if not snapshot.is_file() or sha256_file(snapshot) != digest:
            raise RecoveryMaterialError("immutable snapshot hash mismatch")
    else:
        _atomic_bytes(snapshot, content)
    return snapshot.relative_to(root).as_posix()


@contextlib.contextmanager
def _transaction_lock(root: Path):
    lock = root / ".short-drama/locks/transaction.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+b") as handle:
        if os.name == "nt":
            locking = importlib.import_module("msvcrt")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            locking.locking(handle.fileno(), locking.LK_LOCK, 1)
        else:
            locking = importlib.import_module("fcntl")
            locking.flock(handle.fileno(), locking.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                locking.locking(handle.fileno(), locking.LK_UNLCK, 1)
            else:
                locking.flock(handle.fileno(), locking.LOCK_UN)


def _fault(injector: FaultInjector | None, point: str, txid: str) -> None:
    if injector is not None:
        injector(point, {"transaction_id": txid})


def _normalize_read_set(
    root: Path,
    read_set: Mapping[str, str | None] | Iterable[str] | None,
    read_records: Mapping[str, Mapping[str, str]] | None = None,
) -> list[dict[str, Any]]:
    if read_set is None:
        return []
    entries: list[dict[str, Any]] = []
    items: Iterable[tuple[str, str | None]]
    if isinstance(read_set, Mapping):
        items = ((str(path), expected) for path, expected in read_set.items())
    else:
        items = (
            (
                str(path),
                _live_project_hash(
                    root, _relative_path(path, allow_operations=True)
                ),
            )
            for path in read_set
        )
    records: dict[str, Mapping[str, str]] = {}
    record_paths: dict[str, str] = {}
    for raw, bindings in (read_records or {}).items():
        relative = _relative_path(raw, allow_operations=True)
        _remember_portable_path(record_paths, relative, label="read record binding")
        records[relative] = bindings
    read_paths: dict[str, str] = {}
    for raw, expected in items:
        relative = _relative_path(raw, allow_operations=True)
        _remember_portable_path(read_paths, relative, label="read set")
        if expected is not None and not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"invalid expected read hash for {relative}")
        actual = _live_project_hash(root, relative)
        if actual != expected:
            raise StaleReadSetError(f"read set was stale before prepare: {relative}")
        entry: dict[str, Any] = {"path": relative, "expected_hash": expected}
        bound = records.pop(relative, None)
        if bound:
            entry["records"] = dict(sorted(bound.items()))
        entries.append(entry)
    if records:
        raise ValueError(
            "record binding has no matching read set path: " + ", ".join(sorted(records))
        )
    return sorted(entries, key=lambda entry: entry["path"])


def _validate_read_set(root: Path, entries: list[dict[str, Any]]) -> None:
    stale = [
        entry["path"]
        for entry in entries
        if _live_project_hash(root, entry["path"]) != entry["expected_hash"]
    ]
    if stale:
        raise StaleReadSetError("read set changed after prepare: " + ", ".join(stale))


def _replace_from_file(
    root: Path, source: Path, relative: str, expected_hash: str | None
) -> None:
    if _secure_project_dir_fd():
        source_relative = source.relative_to(root).as_posix()
        with _open_project_directory(root) as directory_fd:
            content = _read_regular_at(directory_fd, source_relative)
            pure = PurePosixPath(relative)
            parent_fd = os.dup(directory_fd)
            try:
                for part in pure.parts[:-1]:
                    child_fd = _open_or_create_directory_at(parent_fd, part)
                    os.close(parent_fd)
                    parent_fd = child_fd
                temporary = f".{pure.name}.apply-{uuid.uuid4().hex}.tmp"
                descriptor = -1
                try:
                    descriptor = os.open(
                        temporary,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=parent_fd,
                    )
                    with os.fdopen(descriptor, "wb") as writer:
                        descriptor = -1
                        writer.write(content)
                        writer.flush()
                        os.fsync(writer.fileno())
                    if _live_hash_at(directory_fd, relative) != expected_hash:
                        raise TransactionConflictError(
                            "target changed immediately before replace"
                        )
                    os.replace(
                        temporary,
                        pure.name,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    os.fsync(parent_fd)
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                    try:
                        os.unlink(temporary, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
            finally:
                os.close(parent_fd)
        return

    target = _project_path(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_dev != target.parent.stat().st_dev:
        raise TransactionError("transaction staging and target must share a filesystem")
    temporary = target.parent / f".{target.name}.apply-{uuid.uuid4().hex}.tmp"
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        if _live_hash(target) != expected_hash:
            raise TransactionConflictError("target changed immediately before replace")
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _unlink_project_file(root: Path, relative: str, expected_hash: str | None) -> None:
    if _secure_project_dir_fd():
        with _open_project_directory(root) as directory_fd:
            pure = PurePosixPath(relative)
            parent_fd = _open_directory_at(directory_fd, pure.parts[:-1])
            try:
                if _live_hash_at(directory_fd, relative) != expected_hash:
                    raise TransactionConflictError("target changed during recovery")
                os.unlink(pure.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        return
    destination = _project_path(root, relative)
    if _live_project_hash(root, relative) != expected_hash:
        raise TransactionConflictError("target changed during recovery")
    destination.unlink()


def _read_state(root: Path) -> dict[str, Any]:
    state = _json_loads((root / STATE_FILE).read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("state must be a JSON object")
    if not isinstance(state.get("artifacts", {}), dict):
        raise ValueError("state.artifacts must be an object")
    return state


def _apply_snapshot_pointers(root: Path, manifest: dict[str, Any]) -> bool:
    state = _read_state(root)
    before = _json_dumps(state, ensure_ascii=False, sort_keys=True)
    artifacts = state.setdefault("artifacts", {})
    grouped: dict[str, list[dict[str, Any]]] = {}
    for target in manifest["targets"]:
        grouped.setdefault(target["artifact_id"], []).append(target)
    for artifact_id, targets in grouped.items():
        existing = artifacts.get(artifact_id, {})
        if not isinstance(existing, dict):
            existing = {}
        record = apply_lifecycle_changes(existing, {})
        authority = manifest.get("authority", "accepted")
        if authority == "candidate":
            candidate_targets = {
                target["path"]: target["candidate_hash"] for target in targets
            }
            candidate_snapshots = {
                target["path"]: target["candidate_snapshot"] for target in targets
            }
            record["owner"] = manifest["owner"]
            record["candidate_targets"] = dict(sorted(candidate_targets.items()))
            record["candidate_snapshots"] = dict(sorted(candidate_snapshots.items()))
            record["candidate_inputs"] = {
                entry["path"]: entry["expected_hash"]
                for entry in manifest.get("read_set", [])
            }
            candidate_input_records = {
                entry["path"]: entry["records"]
                for entry in manifest.get("read_set", [])
                if entry.get("records")
            }
            if candidate_input_records:
                record["candidate_input_records"] = candidate_input_records
            else:
                record.pop("candidate_input_records", None)
            record["candidate_source_transaction"] = manifest["transaction_id"]
            record.pop("creator_decision", None)
            record.pop("review_evidence", None)
            pointer_targets = record["candidate_targets"]
            pointer_name = "candidate_snapshot"
        else:
            accepted_targets = record.get("accepted_targets", {})
            if not isinstance(accepted_targets, dict):
                accepted_targets = {}
            snapshots = record.get("accepted_snapshots", {})
            if not isinstance(snapshots, dict):
                snapshots = {}
            for target in targets:
                accepted_targets[target["path"]] = target["candidate_hash"]
                snapshots[target["path"]] = target["candidate_snapshot"]
            record["accepted_targets"] = dict(sorted(accepted_targets.items()))
            record["accepted_snapshots"] = dict(sorted(snapshots.items()))
            record["source_transaction"] = manifest["transaction_id"]
            pointer_targets = record["accepted_targets"]
            pointer_name = "accepted_snapshot"
        pointer_material = _json_dumps(
            pointer_targets, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        record[pointer_name] = sha256_bytes(pointer_material)
        artifacts[artifact_id] = record
    after = _json_dumps(state, ensure_ascii=False, sort_keys=True)
    if after == before:
        return False
    state["updated_at"] = utc_now()
    state["last_action"] = "snapshot_pointers_applied"
    atomic_json(root / STATE_FILE, state)
    return True


def _apply_intended_lifecycle(root: Path, manifest: dict[str, Any]) -> bool:
    state = _read_state(root)
    before = _json_dumps(state, ensure_ascii=False, sort_keys=True)
    artifacts = state.setdefault("artifacts", {})
    for artifact_id, changes in manifest["lifecycle_changes"].items():
        existing = artifacts.get(artifact_id, {})
        if not isinstance(existing, dict):
            existing = {}
        artifacts[artifact_id] = apply_lifecycle_changes(existing, changes)
    layout_mode = manifest.get("project_layout_mode")
    if layout_mode in {"canonical", "legacy"}:
        recorded = state.get("project_layout_mode", "auto")
        if recorded not in {"auto", layout_mode}:
            raise TransactionConflictError("transaction layout conflicts with project layout")
        state["project_layout_mode"] = layout_mode
    blocked = state.setdefault("blocked_transactions", {})
    if isinstance(blocked, dict):
        blocked.pop(manifest["transaction_id"], None)
    after = _json_dumps(state, ensure_ascii=False, sort_keys=True)
    if after == before:
        return False
    state["updated_at"] = utc_now()
    state["last_action"] = "transaction_committed"
    atomic_json(root / STATE_FILE, state)
    return True


def _block_transaction(
    root: Path,
    manifest: dict[str, Any],
    *,
    code: str,
    append_event: bool = True,
) -> None:
    state = _read_state(root)
    blocked = state.setdefault("blocked_transactions", {})
    artifact_ids = sorted(
        set(manifest["lifecycle_changes"])
        | {target["artifact_id"] for target in manifest["targets"]}
    )
    value = {
        "code": code,
        "artifact_ids": artifact_ids,
        "resolution": ["adopt", "restore", "merge"],
    }
    changed = not isinstance(blocked, dict) or blocked.get(manifest["transaction_id"]) != value
    if not isinstance(blocked, dict):
        blocked = {}
        state["blocked_transactions"] = blocked
    blocked[manifest["transaction_id"]] = value
    artifacts = state.setdefault("artifacts", {})
    for artifact_id in artifact_ids:
        existing = artifacts.get(artifact_id, {})
        if not isinstance(existing, dict):
            existing = {}
        failed = apply_lifecycle_changes(
            existing, {"build_state": "failed", "delivery_gate": "blocked"}
        )
        if failed != existing:
            changed = True
        artifacts[artifact_id] = failed
    if changed:
        state["updated_at"] = utc_now()
        state["last_action"] = "transaction_blocked"
        atomic_json(root / STATE_FILE, state)
    wal = root / ".short-drama/transactions" / manifest["transaction_id"] / "wal.jsonl"
    if append_event and "BLOCKED" not in _event_names(_read_wal(wal, tolerate_missing=True)):
        _append_wal(wal, {"event": "BLOCKED", "code": code})


def _quarantine_manifestless_transaction(root: Path, transaction_id: str) -> Path:
    transaction = root / ".short-drama/transactions" / transaction_id
    quarantine = (
        root
        / ".short-drama/conflicts/orphaned-transactions"
        / transaction_id
    )
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    if transaction.exists() and not quarantine.exists():
        os.replace(transaction, quarantine)
        _fsync_directory(transaction.parent)
        _fsync_directory(quarantine.parent)
    elif transaction.exists() and quarantine.exists():
        raise TransactionError("manifest-less transaction quarantine already exists")

    state = _read_state(root)
    blocked = state.setdefault("blocked_transactions", {})
    record = {
        "code": "MANIFEST_MISSING",
        "artifact_ids": [],
        "resolution": ["inspect", "restore_from_known_good"],
    }
    if not isinstance(blocked, dict):
        blocked = {}
        state["blocked_transactions"] = blocked
    if blocked.get(transaction_id) != record:
        blocked[transaction_id] = record
        state["updated_at"] = utc_now()
        state["last_action"] = "transaction_quarantined"
        atomic_json(root / STATE_FILE, state)
    return quarantine


def _preserve_conflict(
    root: Path, manifest: dict[str, Any], target: dict[str, Any], content: bytes
) -> Path:
    digest = sha256_bytes(content)
    conflict = (
        root
        / ".short-drama/conflicts"
        / manifest["transaction_id"]
        / f"{target['index']:04d}-{digest}.bin"
    )
    if conflict.exists():
        if conflict.read_bytes() != content:
            raise RecoveryMaterialError("conflict copy is not immutable")
    else:
        _atomic_bytes(conflict, content)
    return conflict


def _preserve_live_conflict(
    root: Path, manifest: dict[str, Any], target: dict[str, Any]
) -> None:
    try:
        content = _read_project_regular(root, target["path"])
    except (OSError, ValueError, TransactionConflictError):
        return
    _preserve_conflict(root, manifest, target, content)


def publish_transaction(
    path: Path,
    *,
    stage: str,
    outputs: Mapping[str, str | bytes],
    lifecycle_changes: Mapping[str, Mapping[str, Any]],
    target_artifacts: Mapping[str, str] | None = None,
    read_set: Mapping[str, str | None] | Iterable[str] | None = None,
    read_records: Mapping[str, Mapping[str, str]] | None = None,
    fault_injector: FaultInjector | None = None,
    authority: str = "accepted",
    owner: str | None = None,
    allow_unregistered_path: bool = False,
    _delivery_gate: bool = False,
) -> dict[str, Any]:
    """Publish multiple files with deterministic crash recovery.

    The COMMIT marker is the sole recovery-direction decision. Before it,
    recovery restores every expected prior version. After it, recovery restores
    every candidate version and completes missing pointer/lifecycle state.
    """

    root = find_project(path)
    if not outputs:
        raise ValueError("a transaction needs at least one output")
    if not stage or not re.fullmatch(r"[A-Za-z0-9._:-]+", stage):
        raise ValueError("stage must be an opaque identifier")
    if authority not in {"accepted", "candidate"}:
        raise ValueError("authority must be accepted or candidate")
    if authority == "candidate":
        if not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9._:-]+", owner):
            raise ValueError("candidate owner must be an opaque identifier")
    elif owner is not None:
        raise ValueError("owner metadata is only valid for candidate publication")
    validated_changes: dict[str, dict[str, Any]] = {}
    for artifact_id, changes in lifecycle_changes.items():
        if not artifact_id:
            raise ValueError("artifact id cannot be empty")
        apply_lifecycle_changes({}, changes)
        validated_changes[str(artifact_id)] = dict(changes)
    relative_outputs: dict[str, str | bytes] = {}
    output_paths: dict[str, str] = {}
    for raw, value in outputs.items():
        relative = _relative_path(raw)
        _remember_portable_path(output_paths, relative, label="transaction output")
        relative_outputs[relative] = value
    # `_delivery_gate` is an internal argument, not a stage name: `stage` is
    # creator-supplied, so gating on stage == "delivery" would let any caller
    # unlock the packaged tree by naming itself after it. It skips the layout
    # contract entirely because build_delivery_package constructs every one of
    # its output keys itself from an already-validated episode id.
    if not _delivery_gate:
        for relative in relative_outputs:
            _validate_publication_layout(
                relative, owner=owner, allow_unregistered=allow_unregistered_path
            )

    if target_artifacts is None:
        default_artifact = next(iter(validated_changes)) if len(validated_changes) == 1 else stage
        mapped_artifacts = {relative: default_artifact for relative in relative_outputs}
    else:
        mapped_artifacts: dict[str, str] = {}
        artifact_paths: dict[str, str] = {}
        for raw, artifact in target_artifacts.items():
            relative = _relative_path(raw)
            _remember_portable_path(
                artifact_paths, relative, label="target artifact mapping"
            )
            mapped_artifacts[relative] = str(artifact)
        missing = sorted(set(relative_outputs) - set(mapped_artifacts))
        extra = sorted(set(mapped_artifacts) - set(relative_outputs))
        if missing or extra:
            raise ValueError(f"target artifact mapping mismatch; missing={missing}, extra={extra}")
    if any(not artifact for artifact in mapped_artifacts.values()):
        raise ValueError("target artifact id cannot be empty")

    with _transaction_lock(root):
        # Layout selection is project-wide state. Validate it while holding the
        # same lock that covers target replacement and state application so two
        # first publications cannot commit opposite directory families.
        layout_family = _validate_project_output_layout(root, relative_outputs)
        transaction_id = uuid.uuid4().hex
        transaction = root / ".short-drama/transactions" / transaction_id
        staged = transaction / "staged"
        staged.mkdir(parents=True, exist_ok=False)
        if transaction.stat().st_dev != root.stat().st_dev:
            raise TransactionError("transaction directory is not on the project filesystem")

        read_entries = _normalize_read_set(root, read_set, read_records)
        targets: list[dict[str, Any]] = []
        for index, relative in enumerate(sorted(relative_outputs)):
            content_value = relative_outputs[relative]
            content = content_value.encode("utf-8") if isinstance(content_value, str) else bytes(content_value)
            parent_details = _ensure_project_parent(root, relative)
            if parent_details.st_dev != transaction.stat().st_dev:
                raise TransactionError("target and transaction staging must share a filesystem")
            expected_prior = _live_project_hash(root, relative)
            prior_snapshot = None
            if expected_prior is not None:
                prior_snapshot = _preserve_snapshot(
                    root, mapped_artifacts[relative], _read_project_regular(root, relative)
                )
            staged_file = staged / f"{index:04d}.candidate"
            _atomic_bytes(staged_file, content)
            candidate_hash = sha256_bytes(content)
            candidate_snapshot = _preserve_snapshot(
                root, mapped_artifacts[relative], content
            )
            targets.append(
                {
                    "index": index,
                    "path": relative,
                    "artifact_id": mapped_artifacts[relative],
                    "expected_prior": expected_prior,
                    "prior_snapshot": prior_snapshot,
                    "candidate_hash": candidate_hash,
                    "candidate_snapshot": candidate_snapshot,
                    "staged": staged_file.relative_to(root).as_posix(),
                }
            )

        manifest: dict[str, Any] = {
            "schema_version": 1,
            "transaction_id": transaction_id,
            "stage": stage,
            "authority": authority,
            "owner": owner,
            "read_set": read_entries,
            "targets": targets,
            "lifecycle_changes": validated_changes,
        }
        if layout_family is not None:
            manifest["project_layout_mode"] = layout_family
        atomic_json(transaction / "manifest.json", manifest)
        _fault(fault_injector, "after_manifest", transaction_id)
        _append_wal(transaction / "wal.jsonl", {"event": "PREPARED"})
        _fault(fault_injector, "after_prepared", transaction_id)
        _validate_read_set(root, read_entries)

        for target in targets:
            index = target["index"]
            _fault(fault_injector, f"before_replace:{index}", transaction_id)
            actual = _live_project_hash(root, target["path"])
            if actual == target["candidate_hash"]:
                pass
            elif actual != target["expected_prior"]:
                _preserve_live_conflict(root, manifest, target)
                _block_transaction(root, manifest, code="EXTERNAL_EDIT_CONFLICT")
                raise TransactionConflictError(
                    f"target changed before replace at index {index}"
                )
            else:
                try:
                    _replace_from_file(
                        root,
                        _project_path(root, target["staged"]),
                        target["path"],
                        target["expected_prior"],
                    )
                except TransactionConflictError:
                    latest = _live_project_hash(root, target["path"])
                    if latest not in (
                        target["expected_prior"],
                        target["candidate_hash"],
                    ):
                        _preserve_live_conflict(root, manifest, target)
                    _block_transaction(root, manifest, code="EXTERNAL_EDIT_CONFLICT")
                    raise
            _fault(fault_injector, f"after_replace:{index}", transaction_id)
            _append_wal(
                transaction / "wal.jsonl", {"event": "APPLIED", "index": index}
            )
            _fault(fault_injector, f"after_applied:{index}", transaction_id)

        for target in targets:
            actual = _live_project_hash(root, target["path"])
            if actual != target["candidate_hash"]:
                if actual not in (target["expected_prior"], target["candidate_hash"]):
                    _preserve_live_conflict(root, manifest, target)
                    _block_transaction(root, manifest, code="EXTERNAL_EDIT_CONFLICT")
                    raise TransactionConflictError("target changed before commit")
                raise TransactionError("candidate verification failed before commit")

        _fault(fault_injector, "before_commit", transaction_id)
        _write_marker(transaction / "COMMIT")
        _fault(fault_injector, "after_commit_marker", transaction_id)
        _append_wal(transaction / "wal.jsonl", {"event": "COMMIT"})
        _fault(fault_injector, "after_commit", transaction_id)
        _apply_snapshot_pointers(root, manifest)
        _fault(fault_injector, "after_pointer_state", transaction_id)
        _append_wal(transaction / "wal.jsonl", {"event": "POINTERS_APPLIED"})
        _fault(fault_injector, "after_pointers", transaction_id)
        _apply_intended_lifecycle(root, manifest)
        _fault(fault_injector, "after_lifecycle_state", transaction_id)
        _append_wal(transaction / "wal.jsonl", {"event": "STATE_APPLIED"})
        _fault(fault_injector, "after_state", transaction_id)
        return {
            "transaction_id": transaction_id,
            "status": "committed",
            "target_count": len(targets),
        }


def _read_wal(path: Path, *, tolerate_missing: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        if tolerate_missing:
            return []
        raise TransactionError("transaction WAL is missing")
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = _json_loads(line)
        except json.JSONDecodeError as error:
            raise TransactionError(f"invalid WAL line {number}") from error
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            raise TransactionError(f"invalid WAL event at line {number}")
        events.append(event)
    return events


def _event_names(events: list[dict[str, Any]]) -> set[str]:
    return {str(event.get("event")) for event in events}


def _validate_manifest(manifest: dict[str, Any], txid: str) -> None:
    if manifest.get("transaction_id") != txid:
        raise TransactionError("transaction id does not match its directory")
    if not isinstance(manifest.get("targets"), list) or not manifest["targets"]:
        raise TransactionError("transaction manifest has no targets")
    if not isinstance(manifest.get("lifecycle_changes"), dict):
        raise TransactionError("transaction lifecycle changes are missing")
    authority = manifest.get("authority", "accepted")
    if authority not in {"accepted", "candidate"}:
        raise TransactionError("transaction authority is invalid")
    owner = manifest.get("owner")
    if authority == "candidate" and (
        not isinstance(owner, str)
        or re.fullmatch(r"[A-Za-z0-9._:-]+", owner) is None
    ):
        raise TransactionError("candidate transaction owner is invalid")
    if authority == "accepted" and owner is not None:
        raise TransactionError("accepted transaction cannot claim candidate ownership")
    read_set = manifest.get("read_set")
    if not isinstance(read_set, list):
        raise TransactionError("transaction read set is invalid")
    read_paths: dict[str, str] = {}
    for entry in read_set:
        if not isinstance(entry, dict) or not {"path", "expected_hash"} <= set(entry):
            raise TransactionError("transaction read set entry is invalid")
        if set(entry) - {"path", "expected_hash", "records"}:
            raise TransactionError("transaction read set entry is invalid")
        bound = entry.get("records")
        if "records" in entry:
            if not isinstance(bound, dict) or not bound:
                raise TransactionError("transaction read set records are invalid")
            for selector, digest in bound.items():
                if (
                    not isinstance(selector, str)
                    or not selector
                    or not isinstance(digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                ):
                    raise TransactionError("transaction read set records are invalid")
        relative = _relative_path(
            entry["path"], allow_operations=authority == "accepted"
        )
        _remember_portable_path(
            read_paths,
            relative,
            label="transaction read set",
            error_type=TransactionError,
        )
        expected = entry["expected_hash"]
        if expected is not None and (
            not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            raise TransactionError("transaction read set hash is invalid")
        if authority == "candidate" and expected is None:
            raise TransactionError("candidate read set hash must be exact")
    indices: set[int] = set()
    paths: dict[str, str] = {}
    for target in manifest["targets"]:
        required = {
            "index",
            "path",
            "artifact_id",
            "expected_prior",
            "prior_snapshot",
            "candidate_hash",
            "candidate_snapshot",
        }
        if not isinstance(target, dict) or not required.issubset(target):
            raise TransactionError("transaction target record is incomplete")
        if not isinstance(target["artifact_id"], str) or not target["artifact_id"]:
            raise TransactionError("transaction artifact id is invalid")
        if not isinstance(target["index"], int) or target["index"] < 0:
            raise TransactionError("transaction target index is invalid")
        relative = _relative_path(target["path"])
        if target["index"] in indices:
            raise TransactionError("transaction target records are duplicated")
        _remember_portable_path(
            paths,
            relative,
            label="transaction target",
            error_type=TransactionError,
        )
        indices.add(target["index"])
        for key in ("candidate_hash", "expected_prior"):
            value = target[key]
            if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value):
                raise TransactionError(f"invalid {key} in transaction manifest")
        for key in ("candidate_snapshot", "prior_snapshot"):
            pointer = target[key]
            if pointer is None and key == "prior_snapshot":
                continue
            if not isinstance(pointer, str):
                raise TransactionError(f"invalid {key} in transaction manifest")
            snapshot = PurePosixPath(_relative_path(pointer, allow_operations=True))
            if snapshot.parts[:2] != (".short-drama", "accepted-snapshots"):
                raise TransactionError(f"invalid {key} zone in transaction manifest")
    if indices != set(range(len(manifest["targets"]))):
        raise TransactionError("transaction target indices are not contiguous")


def _has_commit(transaction: Path) -> bool:
    marker = transaction / "COMMIT"
    return marker.is_file() and marker.read_bytes() == b"committed\n"


def _material_for(root: Path, target: dict[str, Any], direction: str) -> Path | None:
    relative = target["candidate_snapshot"] if direction == "forward" else target["prior_snapshot"]
    expected = target["candidate_hash"] if direction == "forward" else target["expected_prior"]
    if expected is None:
        return None
    if not relative:
        raise RecoveryMaterialError("required snapshot pointer is absent")
    snapshot = _project_path(root, _relative_path(relative, allow_operations=True))
    if _live_project_hash(root, relative) != expected:
        raise RecoveryMaterialError("required immutable snapshot is missing or corrupt")
    return snapshot


def _observe_targets(root: Path, manifest: dict[str, Any]) -> list[str | None]:
    return [_live_project_hash(root, target["path"]) for target in manifest["targets"]]


def _state_satisfies_manifest(root: Path, manifest: dict[str, Any]) -> bool:
    state = _read_state(root)
    artifacts = state.get("artifacts", {})
    pointer_key = (
        "candidate_targets"
        if manifest.get("authority", "accepted") == "candidate"
        else "accepted_targets"
    )
    expected_candidates: dict[str, dict[str, str]] = {}
    if pointer_key == "candidate_targets":
        for target in manifest["targets"]:
            expected_candidates.setdefault(target["artifact_id"], {})[
                target["path"]
            ] = target["candidate_hash"]
    for target in manifest["targets"]:
        record = artifacts.get(target["artifact_id"], {})
        if not isinstance(record, dict):
            return False
        pointers = record.get(pointer_key, {})
        if not isinstance(pointers, dict) or pointers.get(target["path"]) != target["candidate_hash"]:
            return False
        if pointer_key == "candidate_targets":
            expected_inputs = {
                entry["path"]: entry["expected_hash"]
                for entry in manifest.get("read_set", [])
            }
            expected_input_records = {
                entry["path"]: entry["records"]
                for entry in manifest.get("read_set", [])
                if entry.get("records")
            }
            if (
                record.get("owner") != manifest.get("owner")
                or record.get("candidate_inputs") != expected_inputs
                or record.get("candidate_input_records", {}) != expected_input_records
                or pointers != expected_candidates[target["artifact_id"]]
            ):
                return False
    for artifact_id, changes in manifest["lifecycle_changes"].items():
        record = artifacts.get(artifact_id, {})
        if not isinstance(record, dict) or any(record.get(axis) != value for axis, value in changes.items()):
            return False
    return True


def recover_transaction(
    path: Path,
    transaction_id: str,
    *,
    fault_injector: FaultInjector | None = None,
) -> dict[str, Any]:
    root = find_project(path)
    if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise ValueError("invalid transaction id")
    with _transaction_lock(root):
        transaction = root / ".short-drama/transactions" / transaction_id
        manifest_path = transaction / "manifest.json"
        if not manifest_path.is_file():
            _quarantine_manifestless_transaction(root, transaction_id)
            return {
                "transaction_id": transaction_id,
                "status": "blocked",
                "direction": "unknown",
                "already_recovered": False,
                "code": "MANIFEST_MISSING",
            }
        manifest = _json_loads(manifest_path.read_text(encoding="utf-8"))
        _validate_manifest(manifest, transaction_id)
        try:
            events = _read_wal(transaction / "wal.jsonl", tolerate_missing=True)
        except (OSError, UnicodeError, TransactionError):
            _block_transaction(
                root,
                manifest,
                code="WAL_CORRUPT",
                append_event=False,
            )
            return {
                "transaction_id": transaction_id,
                "status": "blocked",
                "direction": "forward" if _has_commit(transaction) else "rollback",
                "already_recovered": False,
            }
        names = _event_names(events)
        committed = _has_commit(transaction)
        direction = "forward" if committed else "rollback"

        observations = _observe_targets(root, manifest)
        conflicts: list[tuple[dict[str, Any], Path]] = []
        for target, actual in zip(manifest["targets"], observations, strict=True):
            allowed = {target["expected_prior"], target["candidate_hash"]}
            if actual not in allowed:
                destination = _project_path(root, target["path"])
                if destination.is_file():
                    conflicts.append((target, destination))
                else:
                    conflicts.append((target, destination))
        if conflicts:
            for target, _destination in conflicts:
                _preserve_live_conflict(root, manifest, target)
            _block_transaction(root, manifest, code="EXTERNAL_EDIT_CONFLICT")
            return {
                "transaction_id": transaction_id,
                "status": "blocked",
                "direction": direction,
                "already_recovered": "BLOCKED" in names,
            }

        terminal = "STATE_APPLIED" if committed else "ROLLED_BACK"
        final_hashes = [
            target["candidate_hash"] if committed else target["expected_prior"]
            for target in manifest["targets"]
        ]
        state_complete = not committed or _state_satisfies_manifest(root, manifest)
        if terminal in names and observations == final_hashes and state_complete:
            return {
                "transaction_id": transaction_id,
                "status": "recovered",
                "direction": direction,
                "already_recovered": True,
            }

        materials: list[Path | None] = []
        try:
            for target, actual, final_hash in zip(
                manifest["targets"], observations, final_hashes, strict=True
            ):
                materials.append(
                    None if actual == final_hash else _material_for(root, target, direction)
                )
        except RecoveryMaterialError:
            _block_transaction(root, manifest, code="RECOVERY_MATERIAL_MISSING")
            return {
                "transaction_id": transaction_id,
                "status": "blocked",
                "direction": direction,
                "already_recovered": False,
            }

        for target, observed, final_hash, material in zip(
            manifest["targets"], observations, final_hashes, materials, strict=True
        ):
            if observed == final_hash:
                continue
            index = target["index"]
            destination = _project_path(root, target["path"])
            _fault(fault_injector, f"recovery:before_replace:{index}", transaction_id)
            try:
                if final_hash is None:
                    _unlink_project_file(root, target["path"], observed)
                else:
                    assert material is not None
                    _replace_from_file(root, material, target["path"], observed)
            except TransactionConflictError:
                _preserve_live_conflict(root, manifest, target)
                _block_transaction(root, manifest, code="EXTERNAL_EDIT_CONFLICT")
                return {
                    "transaction_id": transaction_id,
                    "status": "blocked",
                    "direction": direction,
                    "already_recovered": False,
                }
            _fault(fault_injector, f"recovery:after_replace:{index}", transaction_id)

        if committed:
            if "COMMIT" not in names:
                _append_wal(transaction / "wal.jsonl", {"event": "COMMIT"})
            _apply_snapshot_pointers(root, manifest)
            _fault(fault_injector, "recovery:after_pointers", transaction_id)
            if "POINTERS_APPLIED" not in names:
                _append_wal(transaction / "wal.jsonl", {"event": "POINTERS_APPLIED"})
            try:
                _apply_intended_lifecycle(root, manifest)
            except TransactionConflictError:
                # Every other conflict here becomes a blocked transaction. Left
                # bare, a layout clash raises past `recover_project`'s generic
                # handler without ever writing STATE_APPLIED, so the transaction
                # stays `needs_rollforward` and each later `recover` fails the
                # same way — with `blocked_transactions` empty, so no resolution
                # path is ever offered.
                _block_transaction(root, manifest, code="LAYOUT_CONFLICT")
                return {
                    "transaction_id": transaction_id,
                    "status": "blocked",
                    "direction": direction,
                    "already_recovered": False,
                }
            _fault(fault_injector, "recovery:after_lifecycle", transaction_id)
            if "STATE_APPLIED" not in names:
                _append_wal(transaction / "wal.jsonl", {"event": "STATE_APPLIED"})
        elif "ROLLED_BACK" not in names:
            _append_wal(transaction / "wal.jsonl", {"event": "ROLLED_BACK"})
        return {
            "transaction_id": transaction_id,
            "status": "recovered",
            "direction": direction,
            "already_recovered": False,
        }


def recover_project(path: Path) -> dict[str, Any]:
    root = find_project(path)
    transactions = root / ".short-drama/transactions"
    results = []
    if transactions.is_dir():
        for transaction in sorted(transactions.iterdir()):
            if transaction.is_dir() and re.fullmatch(r"[0-9a-f]{32}", transaction.name):
                status = _transaction_status(transaction)
                if status == "complete":
                    continue
                try:
                    results.append(recover_transaction(root, transaction.name))
                except (OSError, UnicodeError, ValueError, TransactionError):
                    results.append(
                        {
                            "transaction_id": transaction.name,
                            "status": "blocked",
                            "direction": "unknown",
                            "already_recovered": False,
                            "code": "TRANSACTION_METADATA_CORRUPT",
                        }
                    )
    return {
        "project_root": str(root),
        "checked": len(results),
        "blocked": sum(result["status"] == "blocked" for result in results),
        "results": results,
    }


def _validate_scene_scoped_record_path(relative: str, record: Any) -> None:
    """Keep the two per-scene directing layers attached to their filename.

    This is deliberately a narrow path/ref consistency check, not a schema
    validator. Blank JSONL files, non-object records, and records without a
    usable ``scene_ref`` keep their existing behavior.
    """

    pure = PurePosixPath(relative)
    if _root_role(pure.parts[0]) != "episodes" or len(pure.parts) != 5:
        return
    family = PurePosixPath(*[part.casefold() for part in pure.parts[2:4]]).as_posix()
    if family not in DECLARED_EPISODE_ARTIFACT_FAMILY_OWNERS:
        return
    expected_scene = pure.stem
    if SCENE_ID_TOKEN_RE.fullmatch(expected_scene) is None:
        raise ValueError(
            "scene-scoped directing filename must use an SC001-style identifier: "
            f"{relative}"
        )
    if not isinstance(record, dict):
        return
    scene_ref = record.get("scene_ref")
    values: list[str] = []
    if isinstance(scene_ref, str):
        values.append(scene_ref)
    elif isinstance(scene_ref, dict):
        values.extend(
            value
            for key in ("scene_id", "record_id")
            if isinstance((value := scene_ref.get(key)), str)
        )
    referenced_scenes = {
        match.group(0)
        for value in values
        for match in SCENE_ID_TOKEN_RE.finditer(value)
    }
    mismatches = sorted(referenced_scenes - {expected_scene})
    if mismatches:
        raise ValueError(
            f"filename {expected_scene} does not match scene_ref {mismatches[0]}: "
            f"{relative}"
        )


def _validate_candidate_content(relative: str, content: bytes) -> None:
    suffix = PurePosixPath(relative).suffix.lower()
    if suffix not in DELIVERY_SUFFIXES:
        raise ValueError(f"candidate must be Markdown, JSON, or JSONL: {relative}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"candidate must be UTF-8 text: {relative}") from error
    if suffix == ".json":
        try:
            _json_loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid candidate JSON: {relative}") from error
    elif suffix == ".jsonl":
        # Validate the path even when the JSONL is intentionally blank.
        _validate_scene_scoped_record_path(relative, None)
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = _json_loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid candidate JSONL at {relative}:{number}"
                ) from error
            _validate_scene_scoped_record_path(relative, record)


def _validate_compiled_prompt_outputs(root: Path, outputs: Mapping[str, bytes]) -> None:
    """Reject prompt-bearing records whose rendered text was freely rewritten."""

    target_profiles = {
        "image-prompt-specs.jsonl": "asset_board",
        "keyframes.jsonl": "keyframe",
        "motion-specs.jsonl": "motion",
    }
    fragments_relative = "设定集/generation/canonical-fragments.jsonl"
    fragments_path = root / fragments_relative
    fragment_bytes = outputs.get(fragments_relative)
    if fragment_bytes is None and fragments_path.is_file():
        fragment_bytes = fragments_path.read_bytes()
    for relative, content in outputs.items():
        target_name = PurePosixPath(relative).name.casefold()
        if target_name not in target_profiles:
            continue
        records = [_json_loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
        compiled = [record for record in records if isinstance(record, dict) and "prompt_components" in record]
        if records and len(compiled) != len(records):
            raise ValueError(f"BLK-PROMPT-COMPILE: every record in {relative} needs prompt_components")
        if not records:
            raise ValueError(f"BLK-PROMPT-COMPILE: {relative} cannot be empty")
        if fragment_bytes is None:
            raise ValueError("BLK-PROMPT-COMPILE: canonical-fragments.jsonl is required")
        compiler_path = Path(__file__).resolve().parents[2] / "short-drama-image-prompts" / "scripts" / "prompt_compile.py"
        spec = importlib.util.spec_from_file_location("prompt_compile_runtime", compiler_path)
        if spec is None or spec.loader is None:
            raise ValueError("BLK-PROMPT-COMPILE: cannot load prompt compiler")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fragments: dict[str, dict[str, Any]] = {}
        for line in fragment_bytes.decode("utf-8").splitlines():
            if not line.strip():
                continue
            record = _json_loads(line)
            if isinstance(record, dict) and isinstance(record.get("fragment_id"), str):
                if record.get("fragment_hash") != module.fragment_hash(record):
                    raise ValueError(f"BLK-PROMPT-COMPILE: fragment hash mismatch: {record.get('fragment_id')}")
                fragments[record["fragment_id"]] = record
        try:
            for record in compiled:
                module.validate_compiled_record(
                    record,
                    fragments,
                    expected_profile=target_profiles[target_name],
                )
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"BLK-PROMPT-COMPILE: {relative}: {error}") from error

    _validate_derived_markdown_outputs(root, outputs)


def _candidate_or_live_bytes(
    root: Path, outputs: Mapping[str, bytes], relative: str
) -> bytes | None:
    candidate = outputs.get(relative)
    if candidate is not None:
        return candidate
    path = _project_path(root, relative)
    return path.read_bytes() if path.is_file() else None


def _markdown_projection_line(raw: str) -> str:
    value = raw.strip()
    while value.startswith(">"):
        value = value[1:].lstrip()
    if value.startswith("- "):
        value = value[2:].lstrip()
    return value


def _markdown_projection_lines(content: bytes) -> list[str]:
    """Return visible Markdown lines with quote/list decoration removed."""

    return [
        value
        for raw in content.decode("utf-8").splitlines()
        if (value := _markdown_projection_line(raw))
    ]


def _require_ordered_projection(
    visible_lines: list[str], required_lines: Iterable[str], *, label: str
) -> None:
    cursor = 0
    for raw in required_lines:
        expected = _markdown_projection_line(raw)
        if not expected:
            continue
        try:
            cursor = visible_lines.index(expected, cursor) + 1
        except ValueError as error:
            raise ValueError(
                f"BLK-DERIVED-MARKDOWN: {label} omits or reorders compiled text: {expected}"
            ) from error


def _validate_derived_markdown_outputs(
    root: Path, outputs: Mapping[str, bytes]
) -> None:
    """Bind user-copyable Markdown caches to their authoritative structured source."""

    projections = {
        "canonical-prompt-library.md": ("canonical-fragments.jsonl", "fragment_id", "text"),
        "image-prompts.md": ("image-prompt-specs.jsonl", "spec_id", "generic_prompt"),
        "keyframe-prompts.md": ("keyframes.jsonl", "keyframe_id", "generic_prompt"),
        "video-prompts.md": ("motion-specs.jsonl", "motion_id", "generic_prompt"),
    }
    for relative, markdown in outputs.items():
        name = PurePosixPath(relative).name.casefold()
        projection = projections.get(name)
        if projection is None:
            continue
        source_name, identity_key, text_key = projection
        source_relative = PurePosixPath(relative).with_name(source_name).as_posix()
        source = _candidate_or_live_bytes(root, outputs, source_relative)
        if source is None:
            raise ValueError(
                f"BLK-DERIVED-MARKDOWN: {relative} requires {source_relative}"
            )
        visible_lines = _markdown_projection_lines(markdown)
        source_digest = sha256_bytes(source)
        if not any(source_digest in line for line in visible_lines):
            raise ValueError(
                f"BLK-DERIVED-MARKDOWN: {relative} does not bind source hash {source_digest}"
            )
        records = _jsonl_records(source, source_relative)
        if not records:
            raise ValueError(
                f"BLK-DERIVED-MARKDOWN: {source_relative} has no records to render"
            )
        for record in records:
            identity = record.get(identity_key)
            rendered = record.get(text_key)
            if not isinstance(identity, str) or not identity:
                raise ValueError(
                    f"BLK-DERIVED-MARKDOWN: {source_relative} record lacks {identity_key}"
                )
            if not isinstance(rendered, str) or not rendered.strip():
                raise ValueError(
                    f"BLK-DERIVED-MARKDOWN: {identity} lacks renderable {text_key}"
                )
            if not any(identity in line for line in visible_lines):
                raise ValueError(
                    f"BLK-DERIVED-MARKDOWN: {relative} omits source record {identity}"
                )
            _require_ordered_projection(
                visible_lines,
                rendered.splitlines(),
                label=f"{relative} record {identity}",
            )
            if name == "canonical-prompt-library.md":
                fragment_hash = record.get("fragment_hash")
                if not isinstance(fragment_hash, str) or not any(
                    fragment_hash in line for line in visible_lines
                ):
                    raise ValueError(
                        f"BLK-DERIVED-MARKDOWN: {relative} omits fragment hash for {identity}"
                    )

        if name != "video-prompts.md":
            continue
        for sibling_name, identity_key in (
            ("generation-clips.jsonl", "clip_id"),
            ("delivery-containers.jsonl", "container_id"),
        ):
            sibling_relative = PurePosixPath(relative).with_name(sibling_name).as_posix()
            sibling = _candidate_or_live_bytes(root, outputs, sibling_relative)
            if sibling is None:
                if sibling_name == "generation-clips.jsonl":
                    raise ValueError(
                        f"BLK-DERIVED-MARKDOWN: {relative} requires {sibling_relative}"
                    )
                continue
            if sibling_name == "generation-clips.jsonl":
                digest = sha256_bytes(sibling)
                if not any(digest in line for line in visible_lines):
                    raise ValueError(
                        f"BLK-DERIVED-MARKDOWN: {relative} does not bind generation clip hash {digest}"
                    )
            for record in _jsonl_records(sibling, sibling_relative):
                identity = record.get(identity_key)
                if not isinstance(identity, str) or not identity or not any(
                    identity in line for line in visible_lines
                ):
                    raise ValueError(
                        f"BLK-DERIVED-MARKDOWN: {relative} omits {sibling_name} record {identity or '<unknown>'}"
                    )


def _validate_m3_new_assets(root: Path, owner: str, outputs: Mapping[str, bytes]) -> None:
    if owner != "short-drama-assets" or _effective_production_flow(root).get("pipeline_version") != PIPELINE_VERSION:
        return
    for relative, content in outputs.items():
        if PurePosixPath(relative).name.casefold() != "decisions.jsonl":
            continue
        records = _jsonl_records(content, relative)
        new_assets = sorted(
            str(record.get("decision_id") or record.get("proposed_binding", {}).get("identity_id") or "<unknown>")
            for record in records
            if record.get("decision_kind") == "new_asset"
        )
        new_variants = sorted(
            str(record.get("decision_id") or record.get("proposed_binding", {}).get("variant_id") or "<unknown>")
            for record in records
            if record.get("decision_kind") == "new_variant"
        )
        if new_assets or new_variants:
            code = "BLK-M15-SCOPE" if new_assets else "BLK-M15-MODEL"
            detail = [*(f"new_asset:{item}" for item in new_assets), *(f"new_variant:{item}" for item in new_variants)]
            raise ValueError(
                f"{code}: M3 cannot introduce new_asset/new_variant under pipeline 2.0; "
                "return to M1.5a/M1.5b, bind the asset in M2, then republish M3: "
                + ", ".join(detail)
            )


def _bind_and_validate_canonical_fragments(
    root: Path,
    outputs: Mapping[str, bytes],
    exact_inputs: Mapping[str, str],
    selectors: dict[str, list[str]],
) -> None:
    fragment_outputs = [
        (relative, content)
        for relative, content in outputs.items()
        if PurePosixPath(relative).name.casefold() == "canonical-fragments.jsonl"
    ]
    if not fragment_outputs:
        return
    compiler_path = Path(__file__).resolve().parents[2] / "short-drama-image-prompts" / "scripts" / "prompt_compile.py"
    spec = importlib.util.spec_from_file_location("prompt_compile_fragments", compiler_path)
    if spec is None or spec.loader is None:
        raise ValueError("BLK-M15-FRAGMENT: cannot load prompt compiler")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    prompt_language = _effective_prompt_language(project)
    for relative, content in fragment_outputs:
        for fragment in _jsonl_records(content, relative):
            fragment_id = fragment.get("fragment_id")
            if not isinstance(fragment_id, str) or not fragment_id:
                raise ValueError("BLK-M15-FRAGMENT: canonical fragment needs fragment_id")
            if fragment.get("fragment_hash") != module.fragment_hash(fragment):
                raise ValueError(f"BLK-M15-FRAGMENT: fragment hash mismatch: {fragment_id}")
            if fragment.get("language") != prompt_language:
                raise ValueError(f"BLK-M15-FRAGMENT: fragment language mismatch: {fragment_id}")
            input_hashes = fragment.get("input_hashes")
            model_refs = fragment.get("model_refs")
            if not isinstance(input_hashes, dict) or not isinstance(model_refs, list) or not model_refs:
                raise ValueError(f"BLK-M15-FRAGMENT: incomplete model refs: {fragment_id}")
            for reference in model_refs:
                if not isinstance(reference, dict):
                    raise ValueError(f"BLK-M15-FRAGMENT: invalid model ref: {fragment_id}")
                artifact = reference.get("artifact")
                selector = reference.get("record_id") or reference.get("field")
                if not isinstance(artifact, str) or not isinstance(selector, str) or not selector:
                    raise ValueError(f"BLK-M15-FRAGMENT: model ref needs artifact and selector: {fragment_id}")
                artifact = _relative_path(artifact)
                expected_file_hash = exact_inputs.get(artifact)
                source = _project_path(root, artifact)
                if expected_file_hash is None or not source.is_file() or sha256_file(source) != expected_file_hash:
                    raise ValueError(f"BLK-M15-FRAGMENT: exact input is missing or stale: {artifact}")
                live_record_hash = _record_digests(source.read_bytes(), artifact, [selector])[selector]
                if reference.get("record_hash") != live_record_hash or input_hashes.get(selector) != live_record_hash:
                    raise ValueError(f"BLK-M15-FRAGMENT: record hash mismatch: {fragment_id} {selector}")
                selectors.setdefault(artifact, [])
                if selector not in selectors[artifact]:
                    selectors[artifact].append(selector)
                    selectors[artifact].sort()


def _structured_candidate_refs(
    relative: str, content: bytes
) -> list[tuple[str, str, str, str | None, str | None, str | None]]:
    suffix = PurePosixPath(relative).suffix.lower()
    if suffix == ".md":
        return []
    text = content.decode("utf-8")
    if suffix == ".json":
        documents = [_json_loads(text)]
    else:
        documents = [_json_loads(line) for line in text.splitlines() if line.strip()]

    references: list[
        tuple[str, str, str, str | None, str | None, str | None]
    ] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            owner = value.get("owner")
            artifact = value.get("artifact")
            digest = value.get("hash")
            if isinstance(owner, str) and isinstance(artifact, str) and "hash" in value:
                # A ref carrying an unfilled placeholder used to be skipped
                # here, so a candidate published straight from a template
                # contributed no dependency edges at all and the exact-input
                # cross-check below never ran: the less that was filled in, the
                # cleaner the publish looked. _normalize_artifact_ref already
                # rejects the same shape for lifecycle evidence refs.
                #
                # Keyed on the presence of `hash`, not on its being a string:
                # gating on isinstance would leave `"hash": null` and
                # `"hash": 123` as the same silent drop under a new spelling.
                # `*_locator` objects carry no `hash` key at all, so they stay
                # untouched.
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise ValueError(f"structured ref hash is unfilled or invalid: {artifact}")
                authority = value.get("authority")
                if authority not in {None, "accepted", "candidate"}:
                    raise ValueError(
                        f"structured ref authority is invalid: {_relative_path(artifact)}"
                    )
                record_id = value.get("record_id")
                if record_id is not None and (
                    not isinstance(record_id, str) or not record_id
                ):
                    raise ValueError(
                        f"structured ref record_id is invalid: {_relative_path(artifact)}"
                    )
                field = value.get("field")
                if field is not None and (not isinstance(field, str) or not field):
                    raise ValueError(
                        f"structured ref field is invalid: {_relative_path(artifact)}"
                    )
                references.append(
                    (
                        owner,
                        _relative_path(artifact),
                        digest,
                        authority,
                        record_id,
                        field,
                    )
                )
            for child_key, child in value.items():
                if child_key == "previous_source_ref":
                    # Revision lineage, not an input dependency. screenplay_index
                    # meta records point previous_source_ref at the *previous*
                    # revision of the source artifact — that hash never has a
                    # candidate/accepted provider at publish time, so treating it
                    # as a consumed input makes the documented
                    # --previous-index --previous-source rebuild unpublishable.
                    continue
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for document in documents:
        collect(document)
    return references


def _structured_ref_selector(
    content: bytes,
    relative: str,
    *,
    record_id: str | None,
    field: str | None,
) -> str | None:
    """Validate a canonical ref locator and return its lifecycle selector."""

    suffix = PurePosixPath(relative).suffix.lower()
    if suffix == ".jsonl":
        if record_id is None:
            if field is not None:
                raise ValueError(
                    f"structured JSONL ref field requires record_id: {relative} {field}"
                )
            return None
        records = _jsonl_records(content, relative)
        matches = [
            record
            for record in records
            if any(
                key.endswith("_id") and value == record_id
                for key, value in record.items()
                if isinstance(value, str)
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                f"structured ref record_id must resolve exactly once: {relative} {record_id}"
            )
        if field is not None:
            _resolve_json_pointer(matches[0], field, relative)
        return record_id
    if suffix == ".json":
        document = _json_loads(content.decode("utf-8"))
        if record_id is not None:
            if not isinstance(document, dict) or not any(
                key.endswith("_id") and value == record_id
                for key, value in document.items()
                if isinstance(value, str)
            ):
                raise ValueError(
                    f"structured ref record_id does not match JSON record: {relative} {record_id}"
                )
        if field is not None:
            _resolve_json_pointer(document, field, relative)
            return field if record_id is None else None
        return None
    if record_id is not None or field is not None:
        raise ValueError(
            f"structured ref record_id/field needs JSON or JSONL: {relative}"
        )
    return None


def _intrinsic_authority_ref(owner: str, relative: str) -> bool:
    """Return whether project-owned creator authority intentionally has no provider."""

    if relative == PROJECT_FILE:
        return owner in {"creator", "short-drama"}
    parts = PurePosixPath(relative).parts
    if not parts or owner != "creator":
        return False
    return parts[0].casefold() in {
        CANONICAL_ROOTS["inputs"].casefold(),
        LEGACY_ROOTS["inputs"].casefold(),
        CANONICAL_ROOTS["creator-decisions"].casefold(),
        LEGACY_ROOTS["creator-decisions"].casefold(),
    }


def _ref_providers(
    artifacts: Mapping[str, Any],
    *,
    relative: str,
    digest: str,
    owner: str,
    target_key: str,
) -> list[str]:
    return sorted(
        artifact_id
        for artifact_id, record in artifacts.items()
        if isinstance(artifact_id, str)
        and isinstance(record, dict)
        and record.get("owner") == owner
        and isinstance(record.get(target_key), dict)
        and record[target_key].get(relative) == digest
    )


def _validate_scene_sheet_evidence_bindings(
    root: Path,
    outputs: Mapping[str, bytes],
    exact_inputs: Mapping[str, str],
) -> None:
    for relative, content in outputs.items():
        if PurePosixPath(relative).name.casefold() != "image-prompt-specs.jsonl":
            continue
        for prompt_spec in _jsonl_records(content, relative):
            sheet = prompt_spec.get("sheet_profile")
            if not isinstance(sheet, dict):
                continue
            bindings = prompt_spec.get("asset_bindings")
            if not isinstance(bindings, list) or len(bindings) != 1:
                continue
            binding = bindings[0]
            if not isinstance(binding, dict):
                continue
            model_id = _binding_value(binding, "model_id", "model_ref")
            orientation_ref = sheet.get("orientation_basis_ref")
            if not isinstance(orientation_ref, dict):
                continue
            spatial_relative = orientation_ref.get("artifact")
            if not isinstance(spatial_relative, str):
                continue
            spatial_relative = _relative_path(spatial_relative)
            expected_hash = exact_inputs.get(spatial_relative)
            if expected_hash is None:
                raise ValueError(
                    "BLK-M4A-SHEET-EVIDENCE: spatial model must be an exact input: "
                    f"{spatial_relative}"
                )
            spatial_content = _read_project_regular(root, spatial_relative)
            if sha256_bytes(spatial_content) != expected_hash:
                raise ValueError(
                    f"BLK-M4A-SHEET-EVIDENCE: spatial model input is stale: {spatial_relative}"
                )
            matches = [
                record
                for record in _jsonl_records(spatial_content, spatial_relative)
                if any(
                    key.endswith("_id") and value == model_id
                    for key, value in record.items()
                    if isinstance(value, str)
                )
            ]
            if len(matches) != 1:
                raise ValueError(
                    "BLK-M4A-SHEET-EVIDENCE: bound spatial model must resolve exactly once: "
                    f"{model_id}"
                )
            model = matches[0]
            coordinate_system = model.get("coordinate_system")
            if not isinstance(coordinate_system, dict) or any(
                not isinstance(coordinate_system.get(field), str)
                or not coordinate_system[field].strip()
                for field in ("north", "origin", "front", "left_right")
            ):
                raise ValueError(
                    "BLK-M4A-SHEET-ORIENTATION: bound spatial model needs non-empty "
                    f"north, origin, front, and left_right: {model_id}"
                )
            evidence_elements = model.get("evidence_elements")
            if not isinstance(evidence_elements, dict) or not evidence_elements:
                raise ValueError(
                    "BLK-M4A-SHEET-EVIDENCE: bound spatial model needs non-empty evidence_elements: "
                    f"{model_id}"
                )
            sheet_evidence = sheet.get("evidence_bindings")
            if not isinstance(sheet_evidence, list):
                continue
            covered_keys: set[str] = set()
            for item in sheet_evidence:
                if not isinstance(item, dict):
                    continue
                source_ref = item.get("source_ref")
                if not isinstance(source_ref, dict):
                    continue
                field = source_ref.get("field")
                if not isinstance(field, str):
                    continue
                target = _resolve_json_pointer(model, field, spatial_relative)
                if not isinstance(target, dict):
                    raise ValueError(
                        "BLK-M4A-SHEET-EVIDENCE: evidence field must resolve to an object: "
                        f"{field}"
                    )
                if target.get("element_id") != item.get("element_id"):
                    raise ValueError(
                        "BLK-M4A-SHEET-EVIDENCE: element_id does not match spatial evidence: "
                        f"{item.get('element_id')}"
                    )
                if target.get("status") != item.get("status"):
                    raise ValueError(
                        "BLK-M4A-SHEET-EVIDENCE: status does not match spatial evidence: "
                        f"{item.get('element_id')}"
                    )
                if target.get("prompt_group") != item.get("prompt_group"):
                    raise ValueError(
                        "BLK-M4A-SHEET-EVIDENCE: prompt_group does not match spatial evidence: "
                        f"{item.get('element_id')}"
                    )
                key = field.removeprefix("/evidence_elements/")
                covered_keys.add(key.replace("~1", "/").replace("~0", "~"))
            expected_keys = set(evidence_elements)
            if covered_keys != expected_keys:
                missing = sorted(expected_keys - covered_keys)
                extra = sorted(covered_keys - expected_keys)
                details: list[str] = []
                if missing:
                    details.append("missing " + ", ".join(missing))
                if extra:
                    details.append("extra " + ", ".join(extra))
                raise ValueError(
                    "BLK-M4A-SHEET-EVIDENCE: evidence_bindings must cover the spatial model exactly: "
                    + "; ".join(details)
                )


def _normalize_hash_mapping(values: Mapping[str, str], *, label: str) -> dict[str, str]:
    normalized: dict[str, str] = {}
    paths: dict[str, str] = {}
    for raw, value in values.items():
        relative = _relative_path(raw)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"invalid {label} hash for {relative}")
        _remember_portable_path(paths, relative, label=label)
        normalized[relative] = value
    if not normalized:
        raise ValueError(f"{label} cannot be empty")
    return dict(sorted(normalized.items()))


def _verify_live_hashes(root: Path, values: Mapping[str, str], *, label: str) -> None:
    for relative, expected in values.items():
        live = _live_project_hash(root, relative)
        if live != expected:
            raise ValueError(
                f"{label} hash does not match live file: {relative} "
                f"(expected {expected}, live {live if live is not None else '<missing>'})"
            )


def _canonical_record_bytes(value: Any) -> bytes:
    """Serialize one record so key order and whitespace cannot change its hash."""

    return _json_dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


SCREENPLAY_BLOCK_RECORD_HASH_VERSION = "screenplay-block-v1"


def _record_digest_material(relative: str, record: Mapping[str, Any]) -> Any:
    """Return versioned canonical material for one record-level binding.

    Screenplay index 1.1 block records explicitly opt into a stable digest.
    Their parent screenplay hash, byte/line position, and revision mapping are
    provenance for the index as a whole, not part of the block's semantic
    identity. Older indexes have no opt-in marker and keep their legacy full
    record digest, so existing accepted bindings are not silently reinterpreted.
    """

    if (
        PurePosixPath(relative).name.casefold() == "screenplay-index.jsonl"
        and record.get("record_type") == "block"
        and record.get("record_hash_version") == SCREENPLAY_BLOCK_RECORD_HASH_VERSION
    ):
        material = dict(record)
        source_ref = material.get("source_ref")
        if isinstance(source_ref, dict):
            stable_source_ref = dict(source_ref)
            stable_source_ref.pop("hash", None)
            material["source_ref"] = stable_source_ref
        for field in (
            "byte_start",
            "byte_end",
            "line_start",
            "line_end",
            "mapping",
        ):
            material.pop(field, None)
        return material
    return record


def _record_digest(relative: str, record: Mapping[str, Any]) -> str:
    return sha256_bytes(
        _canonical_record_bytes(_record_digest_material(relative, record))
    )


def _jsonl_records(content: bytes, relative: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = _json_loads(line)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ValueError(
                f"record binding needs parseable JSONL: {relative} line {number}"
            ) from error
        if not isinstance(record, dict):
            raise ValueError(
                f"record binding needs one object per line: {relative} line {number}"
            )
        records.append(record)
    return records


def _resolve_json_pointer(document: Any, pointer: str, relative: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError(
            f"JSON record selector must be an RFC 6901 pointer: {relative} {pointer}"
        )
    current = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"record selector does not resolve: {relative} {pointer}")
            current = current[token]
        elif isinstance(current, list):
            if re.fullmatch(r"(?:0|[1-9][0-9]*)", token) is None or int(token) >= len(
                current
            ):
                raise ValueError(
                    f"record selector does not resolve: {relative} {pointer}"
                )
            current = current[int(token)]
        else:
            raise ValueError(f"record selector does not resolve: {relative} {pointer}")
    return current


def _record_digests(
    content: bytes,
    relative: str,
    selectors: Iterable[str],
    *,
    missing_ok: bool = False,
) -> dict[str, str | None]:
    """Hash the selected records inside one structured artifact.

    A JSONL selector is a record ID: the value of some top-level ``*_id`` field
    that occurs exactly once in the file, so no per-artifact schema is needed
    and an ambiguous ID is reported instead of guessed. A JSON selector is an
    RFC 6901 pointer. With ``missing_ok`` an unresolvable selector yields None
    rather than raising, which is what staleness narrowing needs: a record that
    vanished or turned ambiguous must invalidate its consumers, not crash.
    """

    wanted = list(selectors)
    suffix = PurePosixPath(relative).suffix.lower()
    if suffix not in {".json", ".jsonl"}:
        raise ValueError(
            f"record-level input binding needs a .json or .jsonl input: {relative} "
            "(Markdown and other text inputs have no verifiable record IDs; "
            "bind the whole file instead with publish --no-input-record-auto)"
        )
    digests: dict[str, str | None] = {}
    try:
        if suffix == ".jsonl":
            records = _jsonl_records(content, relative)
            for selector in wanted:
                matches = [
                    record
                    for record in records
                    if any(
                        key.endswith("_id") and value == selector
                        for key, value in record.items()
                        if isinstance(value, str)
                    )
                ]
                if len(matches) != 1:
                    raise ValueError(
                        f"record selector must resolve exactly once: {relative} {selector}"
                    )
                digests[selector] = _record_digest(relative, matches[0])
        else:
            try:
                document = _json_loads(content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeError) as error:
                raise ValueError(
                    f"record binding needs parseable JSON: {relative}"
                ) from error
            for selector in wanted:
                digests[selector] = sha256_bytes(
                    _canonical_record_bytes(
                        _resolve_json_pointer(document, selector, relative)
                    )
                )
    except ValueError:
        if not missing_ok:
            raise
        return {selector: digests.get(selector) for selector in wanted}
    return digests


def _normalize_record_selectors(
    values: Mapping[str, Iterable[str]] | None,
) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    paths: dict[str, str] = {}
    for raw, selectors in (values or {}).items():
        relative = _relative_path(raw)
        _remember_portable_path(paths, relative, label="record binding")
        unique: list[str] = []
        for selector in selectors:
            if not isinstance(selector, str) or not selector:
                raise ValueError(f"record selector is invalid: {relative}")
            if selector in unique:
                raise ValueError(f"duplicate record selector: {relative} {selector}")
            unique.append(selector)
        if not unique:
            raise ValueError(f"record binding needs at least one selector: {relative}")
        normalized[relative] = sorted(unique)
    return dict(sorted(normalized.items()))


def _input_record_bindings(record: Mapping[str, Any], key: str) -> dict[str, dict[str, str]]:
    raw = record.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"artifact {key} are invalid")
    normalized: dict[str, dict[str, str]] = {}
    paths: dict[str, str] = {}
    for path, bindings in raw.items():
        relative = _relative_path(path)
        if not isinstance(bindings, dict) or not bindings:
            raise ValueError(f"artifact {key} entry is invalid: {relative}")
        _remember_portable_path(paths, relative, label=f"artifact {key}")
        selectors: dict[str, str] = {}
        for selector, digest in bindings.items():
            if not isinstance(selector, str) or not selector:
                raise ValueError(f"artifact {key} selector is invalid: {relative}")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError(
                    f"artifact {key} record hash is invalid: {relative} {selector}"
                )
            selectors[selector] = digest
        normalized[relative] = dict(sorted(selectors.items()))
    return dict(sorted(normalized.items()))


def _verify_live_records(
    root: Path,
    bindings: Mapping[str, Mapping[str, str]],
    *,
    label: str,
) -> None:
    for relative, selectors in bindings.items():
        path = _project_path(root, relative)
        if not path.is_file():
            raise ValueError(f"{label} record source is unavailable: {relative}")
        digests = _record_digests(path.read_bytes(), relative, selectors)
        for selector, expected in selectors.items():
            if digests.get(selector) != expected:
                raise ValueError(
                    f"{label} record hash does not match live file: {relative} {selector}"
                )


def _input_bindings(record: Mapping[str, Any], key: str) -> dict[str, str]:
    raw = record.get(key)
    if not isinstance(raw, dict):
        raise ValueError(f"artifact {key} are unavailable")
    normalized: dict[str, str] = {}
    paths: dict[str, str] = {}
    for path, expected in raw.items():
        relative = _relative_path(path)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError(f"artifact {key} hash is invalid: {relative}")
        _remember_portable_path(paths, relative, label=f"artifact {key}")
        normalized[relative] = expected
    return dict(sorted(normalized.items()))


def _validate_structured_ref_closure(
    root: Path,
    state: Mapping[str, Any],
    artifact_id: str,
    record: Mapping[str, Any],
    *,
    inputs: Mapping[str, str],
    candidate: bool,
) -> None:
    target_key = "candidate_targets" if candidate else "accepted_targets"
    targets = record.get(target_key)
    if not isinstance(targets, dict):
        raise ValueError(f"structured ref target registry is unavailable: {artifact_id}")
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("structured ref provider registry is unavailable")
    publication_owner = record.get("owner")
    for output, expected_output_hash in targets.items():
        if not isinstance(output, str) or not isinstance(expected_output_hash, str):
            raise ValueError(f"structured ref target registry is invalid: {artifact_id}")
        output_content = _read_project_regular(root, output)
        if sha256_bytes(output_content) != expected_output_hash:
            raise ValueError(f"structured ref target is stale: {output}")
        for (
            reference_owner,
            referenced_path,
            referenced_hash,
            reference_authority,
            record_id,
            field,
        ) in _structured_candidate_refs(output, output_content):
            if referenced_path in targets:
                if reference_authority != "candidate":
                    raise ValueError(
                        "same-publication ref must retain candidate authority: "
                        f"{referenced_path}"
                    )
                if reference_owner != publication_owner:
                    raise ValueError(
                        "same-publication ref owner does not match publication owner: "
                        f"{referenced_path}"
                    )
                if targets[referenced_path] != referenced_hash:
                    raise ValueError(
                        "same-publication ref hash does not match target: "
                        f"{referenced_path}"
                    )
                _structured_ref_selector(
                    _read_project_regular(root, referenced_path),
                    referenced_path,
                    record_id=record_id,
                    field=field,
                )
                continue
            if inputs.get(referenced_path) != referenced_hash:
                raise ValueError(
                    f"structured ref is not frozen as an exact input: {referenced_path}"
                )
            referenced_content = _read_project_regular(root, referenced_path)
            if sha256_bytes(referenced_content) != referenced_hash:
                raise ValueError(f"structured ref input is stale: {referenced_path}")
            _structured_ref_selector(
                referenced_content,
                referenced_path,
                record_id=record_id,
                field=field,
            )
            if _intrinsic_authority_ref(reference_owner, referenced_path):
                continue
            providers = _ref_providers(
                artifacts,
                relative=referenced_path,
                digest=referenced_hash,
                owner=reference_owner,
                target_key="accepted_targets",
            )
            if len(providers) > 1:
                raise ValueError(
                    f"accepted structured ref provider is ambiguous: {referenced_path}"
                )
            if not providers:
                raise ValueError(
                    "accepted structured ref has no matching accepted provider: "
                    f"{referenced_path}"
                )


def _validate_input_closure(
    root: Path,
    state: Mapping[str, Any],
    artifact_id: str,
    *,
    bindings: Mapping[str, str] | None = None,
    record_bindings: Mapping[str, Mapping[str, str]] | None = None,
    active: tuple[str, ...] = (),
) -> None:
    if artifact_id in active:
        raise ValueError("accepted input dependency cycle: " + " -> ".join((*active, artifact_id)))
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("accepted input artifact registry is unavailable")
    record = artifacts.get(artifact_id)
    if not isinstance(record, dict):
        raise ValueError(f"accepted input artifact is unavailable: {artifact_id}")
    inputs = dict(bindings) if bindings is not None else _input_bindings(record, "accepted_inputs")
    records = (
        {path: dict(selectors) for path, selectors in record_bindings.items()}
        if record_bindings is not None
        else _input_record_bindings(record, "accepted_input_records")
    )
    unknown_records = sorted(set(records) - set(inputs))
    if unknown_records:
        raise ValueError(
            "record binding has no matching input: " + ", ".join(unknown_records)
        )
    # A record-bound input is judged by its bound records, so an unrelated
    # append to the same shared file leaves this consumer current. The file
    # hash stays in accepted_inputs as the binding-time snapshot.
    _verify_live_hashes(
        root,
        {path: digest for path, digest in inputs.items() if path not in records},
        label="accepted input",
    )
    _verify_live_records(root, records, label="accepted input")
    _validate_structured_ref_closure(
        root,
        state,
        artifact_id,
        record,
        inputs=inputs,
        candidate=bindings is not None,
    )
    for relative, expected in inputs.items():
        record_bound = relative in records
        path_owners: list[str] = []
        providers: list[str] = []
        for provider_id, provider in artifacts.items():
            if not isinstance(provider_id, str) or not isinstance(provider, dict):
                continue
            candidate_targets = provider.get("candidate_targets")
            accepted_targets = provider.get("accepted_targets")
            if (
                isinstance(candidate_targets, dict) and relative in candidate_targets
            ) or (isinstance(accepted_targets, dict) and relative in accepted_targets):
                path_owners.append(provider_id)
            if isinstance(accepted_targets, dict) and (
                relative in accepted_targets
                if record_bound
                else accepted_targets.get(relative) == expected
            ):
                providers.append(provider_id)
        if len(set(path_owners)) > 1 or len(providers) > 1:
            raise ValueError(f"accepted input provider is ambiguous: {relative}")
        if path_owners and not providers:
            raise ValueError(f"accepted input has no matching accepted provider: {relative}")
        if not providers:
            continue
        provider_id = providers[0]
        if provider_id == artifact_id:
            raise ValueError(f"accepted input dependency cycle at: {relative}")
        provider = artifacts[provider_id]
        if (
            provider.get("build_state") != "materialized"
            or provider.get("creator_acceptance") != "accepted"
        ):
            raise ValueError(f"accepted input provider is not current: {provider_id}")
        _validate_input_closure(
            root,
            state,
            provider_id,
            active=(*active, artifact_id),
        )


def _downstream_stale_changes(
    state: Mapping[str, Any],
    *,
    publishing_artifact: str,
    candidate_targets: Mapping[str, str | None],
    candidate_contents: Mapping[str, bytes] | None = None,
) -> dict[str, dict[str, str]]:
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    contents = dict(candidate_contents or {})
    resolved: dict[str, dict[str, str | None]] = {}

    def records_survive(path: str, bound: Mapping[str, str]) -> bool:
        """True when every record this consumer bound is byte-identical in the
        new bytes. Without the new bytes — a removed path, or a target reached
        transitively — survival cannot be proven and the consumer goes stale."""

        content = contents.get(path)
        if content is None:
            return False
        cached = resolved.setdefault(path, {})
        missing = [selector for selector in bound if selector not in cached]
        if missing:
            cached.update(_record_digests(content, path, missing, missing_ok=True))
        return all(cached.get(selector) == digest for selector, digest in bound.items())

    affected: dict[str, str | None] = dict(candidate_targets)
    publishing_record = artifacts.get(publishing_artifact)
    if isinstance(publishing_record, dict):
        for key in ("accepted_targets", "candidate_targets"):
            previous_targets = publishing_record.get(key)
            if not isinstance(previous_targets, dict):
                continue
            for path in previous_targets:
                if path not in candidate_targets:
                    affected[path] = None
    stale: set[str] = set()
    changed = True
    while changed:
        changed = False
        for artifact_id in sorted(artifacts):
            if artifact_id == publishing_artifact or artifact_id in stale:
                continue
            record = artifacts.get(artifact_id)
            if not isinstance(record, dict):
                continue
            accepted_inputs = record.get("accepted_inputs")
            if not isinstance(accepted_inputs, dict):
                continue
            try:
                bound_records = _input_record_bindings(record, "accepted_input_records")
            except ValueError:
                bound_records = {}
            invalidated = False
            for path, expected in accepted_inputs.items():
                if path not in affected:
                    continue
                if affected[path] is not None and affected[path] == expected:
                    continue
                bound = bound_records.get(path)
                if bound and records_survive(path, bound):
                    continue
                invalidated = True
                break
            if not invalidated:
                continue
            stale.add(artifact_id)
            changed = True
            accepted_targets = record.get("accepted_targets")
            if isinstance(accepted_targets, dict):
                for path in accepted_targets:
                    affected[path] = None
    changes = {
        "build_state": "stale",
        "validation_state": "not_run",
        "independent_review": "not_requested",
        "delivery_gate": "blocked",
    }
    return {artifact_id: dict(changes) for artifact_id in sorted(stale)}


def _stale_lifecycle_changes() -> dict[str, str]:
    return {
        "build_state": "stale",
        "validation_state": "not_run",
        "creator_acceptance": "not_requested",
        "independent_review": "not_requested",
        "delivery_gate": "blocked",
    }


def _current_record_targets(record: Mapping[str, Any]) -> dict[str, str]:
    """Return the snapshot whose bytes should currently be materialized."""

    candidates = record.get("candidate_targets")
    if isinstance(candidates, dict) and candidates:
        return {
            str(path): str(digest)
            for path, digest in candidates.items()
            if isinstance(path, str) and isinstance(digest, str)
        }
    accepted = record.get("accepted_targets")
    if isinstance(accepted, dict):
        return {
            str(path): str(digest)
            for path, digest in accepted.items()
            if isinstance(path, str) and isinstance(digest, str)
        }
    return {}


def _effective_lifecycle_records(
    root: Path, artifacts: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Overlay live-hash drift so status never reports stale evidence as ready."""

    effective = {
        str(artifact_id): dict(record)
        for artifact_id, record in artifacts.items()
        if isinstance(artifact_id, str) and isinstance(record, dict)
    }
    direct_stale: list[tuple[str, dict[str, str | None]]] = []
    for artifact_id, record in effective.items():
        targets = _current_record_targets(record)
        changed: dict[str, str | None] = {}
        for relative, expected in targets.items():
            try:
                actual = _live_hash(_project_path(root, _relative_path(relative)))
            except (OSError, ValueError, TransactionConflictError):
                actual = None
            if actual != expected:
                changed[relative] = actual
        if changed:
            direct_stale.append((artifact_id, changed))

    stale_ids = {artifact_id for artifact_id, _ in direct_stale}
    for artifact_id, record in effective.items():
        if artifact_id in stale_ids or record.get("creator_acceptance") != "accepted":
            continue
        try:
            inputs = _input_bindings(record, "accepted_inputs")
            record_inputs = _input_record_bindings(record, "accepted_input_records")
            _verify_live_hashes(
                root,
                {path: digest for path, digest in inputs.items() if path not in record_inputs},
                label="accepted input",
            )
            _verify_live_records(root, record_inputs, label="accepted input")
        except (OSError, ValueError, UnicodeError, TransactionConflictError):
            targets = record.get("accepted_targets")
            direct_stale.append(
                (
                    artifact_id,
                    {
                        path: None
                        for path in targets
                    }
                    if isinstance(targets, dict)
                    else {},
                )
            )
            stale_ids.add(artifact_id)

    stale_changes = _stale_lifecycle_changes()
    for artifact_id, changed in direct_stale:
        effective[artifact_id] = apply_lifecycle_changes(
            effective[artifact_id], stale_changes
        )
        downstream = _downstream_stale_changes(
            {"artifacts": artifacts},
            publishing_artifact=artifact_id,
            candidate_targets=changed,
        )
        for dependent in downstream:
            if dependent in effective:
                effective[dependent] = apply_lifecycle_changes(
                    effective[dependent], stale_changes
                )
    return effective
def project_path_lifecycle_at(
    directory_fd: int, relative: str | Path
) -> dict[str, Any] | None:
    """Return lifecycle evidence relative to a pinned project directory."""

    return project_path_lifecycle_from_reader(
        lambda path: _read_regular_at(directory_fd, path), relative
    )


def _open_or_create_directory_at(parent_fd: int, name: str) -> int:
    """Open a directory, creating it if absent, tolerating a concurrent creator.

    This runs *before* any lock is held — it is how the lock directory itself
    comes into being — so two callers can both find the directory missing and
    both try to create it. The loser of that race must open what the winner
    made, not fail.
    """

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        pass
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    return os.open(name, flags, dir_fd=parent_fd)


def _open_or_create_lock_file_at(parent_fd: int, name: str) -> int:
    """Open the lock file, creating it if absent, tolerating a lost create race.

    On macOS an ``openat`` with ``O_CREAT | O_NOFOLLOW`` that loses a creation
    race against another opener returns ENOENT rather than opening the file the
    winner just made. This is the very first step of acquiring the lock, so it
    runs unserialized by construction: retry instead of surfacing a spurious
    "no such file" from a path that plainly exists.
    """

    for _ in range(_LOCK_OPEN_ATTEMPTS):
        try:
            return os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            continue
        except FileExistsError:
            continue
    raise TransactionConflictError(f"transaction lock is unavailable: {name}")


@contextlib.contextmanager
def _transaction_lock_at(directory_fd: int):
    operational_fd = _open_or_create_directory_at(directory_fd, ".short-drama")
    locks_fd = -1
    lock_fd = -1
    try:
        locks_fd = _open_or_create_directory_at(operational_fd, "locks")
        lock_fd = _open_or_create_lock_file_at(locks_fd, "transaction.lock")
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise TransactionConflictError("transaction lock is not a regular file")
        import fcntl

        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if locks_fd >= 0:
            os.close(locks_fd)
        os.close(operational_fd)


def _atomic_json_at(
    directory_fd: int, relative: str | Path, document: Mapping[str, Any]
) -> None:
    pure = PurePosixPath(relative)
    parent_fd = _open_directory_at(directory_fd, pure.parts[:-1])
    temporary = f".{pure.name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    replaced = False
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        encoded = (
            _json_dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary, pure.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd
        )
        replaced = True
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not replaced:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent_fd)
        os.close(parent_fd)


def update_working_text_state(
    state: Mapping[str, Any], relative: str | Path, digest: str
) -> dict[str, Any] | None:
    """Return lifecycle state updated for one externally edited working file."""

    normalized = _relative_path(relative)
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("working text digest must be a SHA-256 hash")
    artifacts_value = state.get("artifacts")
    artifacts = (
        {
            artifact_id: dict(record) if isinstance(record, dict) else record
            for artifact_id, record in artifacts_value.items()
            if isinstance(artifact_id, str)
        }
        if isinstance(artifacts_value, dict)
        else None
    )
    if not isinstance(artifacts, dict):
        return None
    owners = [
        artifact_id
        for artifact_id, record in artifacts.items()
        if isinstance(artifact_id, str)
        and isinstance(record, dict)
        and any(
            isinstance(record.get(key), dict) and normalized in record[key]
            for key in ("candidate_targets", "accepted_targets")
        )
    ]
    if len(owners) > 1:
        raise TransactionConflictError(
            f"project path has multiple lifecycle owners: {normalized}"
        )
    if not owners:
        return None
    updated_state = dict(state)
    updated_state["artifacts"] = artifacts
    artifact_id = owners[0]
    record = artifacts[artifact_id]
    updated = apply_lifecycle_changes(record, _stale_lifecycle_changes())
    updated.pop("creator_decision", None)
    updated.pop("review_evidence", None)
    artifacts[artifact_id] = updated
    for dependent, changes in _downstream_stale_changes(
        updated_state,
        publishing_artifact=artifact_id,
        candidate_targets={normalized: digest},
    ).items():
        existing = artifacts.get(dependent)
        if isinstance(existing, dict):
            artifacts[dependent] = apply_lifecycle_changes(existing, changes)
    updated_state["updated_at"] = utc_now()
    updated_state["last_action"] = "working_text_edited"
    return updated_state


def _record_working_text_edit_at(
    directory_fd: int, relative: str, digest: str
) -> None:
    try:
        state = _json_loads(_read_regular_at(directory_fd, STATE_FILE).decode("utf-8"))
    except FileNotFoundError:
        return
    if not isinstance(state, dict):
        raise ValueError("project state must contain a JSON object")
    updated = update_working_text_state(state, relative, digest)
    if updated is not None:
        _atomic_json_at(directory_fd, STATE_FILE, updated)


@contextlib.contextmanager
def coordinated_project_text_edit_at(
    directory_fd: int, relative: str | Path, expected_hash: str
):
    """Coordinate a Dashboard edit relative to a pinned project root."""

    normalized = _relative_path(relative)
    if not isinstance(expected_hash, str) or re.fullmatch(
        r"[0-9a-f]{64}", expected_hash
    ) is None:
        raise ValueError("expected hash must be a SHA-256 digest")
    with _transaction_lock_at(directory_fd):
        if _live_hash_at(directory_fd, normalized) != expected_hash:
            raise StaleReadSetError("file changed since it was opened")
        outcome: dict[str, str] = {}
        yield outcome
        actual = _live_hash_at(directory_fd, normalized)
        if actual is None:
            raise TransactionConflictError("edited project file disappeared")
        if actual != expected_hash:
            try:
                _record_working_text_edit_at(directory_fd, normalized, actual)
            except Exception:
                # The content commit is authoritative; metadata repair is a
                # follow-up warning instead of a false save failure.
                outcome["state_warning"] = "lifecycle_update_failed"


def _normalize_artifact_ref(
    root: Path,
    reference: Mapping[str, Any],
    *,
    expected_owner: str | None = None,
    allow_operations: bool = False,
) -> dict[str, Any]:
    owner = reference.get("owner")
    artifact = reference.get("artifact")
    digest = reference.get("hash")
    if not isinstance(owner, str) or re.fullmatch(r"[A-Za-z0-9._:-]+", owner) is None:
        raise ValueError("evidence ref owner is invalid")
    if expected_owner is not None and owner != expected_owner:
        raise ValueError(f"evidence ref owner must be {expected_owner}")
    if not isinstance(artifact, str):
        raise ValueError("evidence ref artifact is invalid")
    relative = _relative_path(artifact, allow_operations=allow_operations)
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("evidence ref hash is invalid")
    if _live_hash(_project_path(root, relative)) != digest:
        raise ValueError(f"evidence ref hash does not match live file: {relative}")
    normalized: dict[str, Any] = {
        "owner": owner,
        "artifact": relative,
        "hash": digest,
    }
    for optional in ("record_id", "field"):
        value = reference.get(optional)
        if value is not None:
            if not isinstance(value, str) or not value:
                raise ValueError(f"evidence ref {optional} is invalid")
            normalized[optional] = value
    if reference.get("authority") is not None:
        raise ValueError("lifecycle evidence must reference published authority")
    return normalized


def _load_evidence_record(
    root: Path,
    reference: Mapping[str, Any],
    *,
    expected_owner: str,
    allow_operations: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load one hash-bound JSON or JSONL evidence record."""

    normalized = _normalize_artifact_ref(
        root,
        reference,
        expected_owner=expected_owner,
        allow_operations=allow_operations,
    )
    evidence_path = _project_path(root, normalized["artifact"])
    suffix = evidence_path.suffix.lower()
    record: dict[str, Any]
    if suffix == ".jsonl":
        record_id = normalized.get("record_id")
        if not isinstance(record_id, str):
            raise ValueError("JSONL evidence requires a record_id")
        matches: list[dict[str, Any]] = []
        for number, line in enumerate(
            evidence_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                candidate = _json_loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid evidence JSONL at line {number}") from error
            if not isinstance(candidate, dict):
                raise ValueError("evidence JSONL records must be objects")
            candidate_ids = {
                candidate.get(key)
                for key in ("decision_id", "review_id", "record_id")
            }
            if record_id in candidate_ids:
                matches.append(candidate)
        if len(matches) != 1:
            raise ValueError("evidence record_id must resolve exactly once")
        record = matches[0]
    elif suffix == ".json":
        try:
            candidate = _json_loads(evidence_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("invalid JSON evidence") from error
        if not isinstance(candidate, dict):
            raise ValueError("JSON evidence must be an object")
        record = candidate
        record_id = normalized.get("record_id")
        if record_id is not None and record_id not in {
            record.get("decision_id"),
            record.get("review_id"),
            record.get("record_id"),
        }:
            raise ValueError("evidence record_id does not match JSON evidence")
    else:
        raise ValueError("evidence must be JSON or JSONL")
    return normalized, record


def _validate_decision_authority(
    root: Path,
    record: Mapping[str, Any],
    *,
    artifact_id: str | None,
    operation: str,
) -> dict[str, Any]:
    """Require creator authority, directly or through a scoped delegation."""

    decided_by = record.get("decided_by")
    if decided_by == "creator":
        return {"decided_by": "creator", "mode": "direct"}
    if not isinstance(decided_by, str) or re.fullmatch(
        r"[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._-]*", decided_by
    ) is None:
        raise ValueError(
            "decided_by must be creator or a delegated <role>:<stable-id> identity"
        )
    delegate_role = decided_by.partition(":")[0].casefold()
    if (
        delegate_role.startswith("short-drama")
        or delegate_role in {"agent", "assistant", "reviewer", "skill", "model"}
    ):
        raise ValueError("skills, agents, models, and reviewers cannot be creator delegates")
    raw_ref = record.get("delegation_ref")
    if not isinstance(raw_ref, dict):
        raise ValueError("delegated creator decision requires delegation_ref")
    delegation_ref, delegation = _load_evidence_record(
        root, raw_ref, expected_owner="creator"
    )
    if delegation.get("decision_kind") != "delegation":
        raise ValueError("delegation evidence decision_kind must be delegation")
    if delegation.get("status") != "accepted":
        raise ValueError("delegation evidence must be accepted")
    if delegation.get("decided_by") != "creator":
        raise ValueError("delegation evidence must be decided by creator")
    if delegation.get("delegate") != decided_by:
        raise ValueError("delegation evidence delegate does not match decided_by")
    scope = delegation.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("delegation evidence scope must be an object")
    operations = scope.get("operations")
    if not isinstance(operations, list) or operation not in operations:
        raise ValueError("delegation scope does not permit this operation")
    artifacts = scope.get("artifacts")
    if artifact_id is not None and (
        not isinstance(artifacts, list)
        or not all(isinstance(value, str) for value in artifacts)
        or artifact_id not in artifacts
        and "*" not in artifacts
    ):
        raise ValueError("delegation scope does not permit this artifact")
    return {
        "decided_by": decided_by,
        "mode": "delegated",
        "delegation_ref": delegation_ref,
        "delegation_id": delegation.get("decision_id"),
    }


def _validate_creator_decision_evidence(
    root: Path,
    reference: Mapping[str, Any],
    *,
    decision: str,
    artifact_id: str,
    target_hashes: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, record = _load_evidence_record(
        root, reference, expected_owner="creator"
    )

    evidence_decisions = [
        record[key].casefold()
        for key in ("status", "decision")
        if isinstance(record.get(key), str)
    ]
    if not evidence_decisions:
        raise ValueError("creator decision evidence has no status or decision")
    if any(value != decision for value in evidence_decisions):
        raise ValueError("creator evidence does not match creator decision")
    if record.get("decision_kind") != "artifact_acceptance":
        raise ValueError("creator evidence decision_kind must be artifact_acceptance")
    if record.get("artifact_id") != artifact_id:
        raise ValueError("creator evidence artifact_id does not match artifact")
    raw_targets = record.get("target_hashes")
    if not isinstance(raw_targets, dict):
        raise ValueError("creator evidence target_hashes must be an object")
    evidence_targets = _normalize_hash_mapping(
        raw_targets, label="creator evidence target"
    )
    if evidence_targets != dict(target_hashes):
        raise ValueError("creator evidence target_hashes do not match candidate targets")
    _validate_decision_authority(
        root,
        record,
        artifact_id=artifact_id,
        operation="artifact_acceptance",
    )
    return normalized, record


FORM_DEPENDENT_OUTPUT_HINTS = frozenset(
    {
        "image-prompt-specs.jsonl",
        "image-prompts.md",
        "lookdev-prompts.md",
        "lookdev-image-prompt-specs.jsonl",
        "lookdev-frame-spec.jsonl.md",
    }
)


def _output_requires_form(relative: str) -> bool:
    """True for publication roots whose stage hard-requires an accepted form.

    Image-prompt outputs and storyboard outputs are unambiguously form-bound.
    Video outputs (motion-specs / delivery-containers / video-prompts) are not:
    the video stage may keep the form choice provisional when its accepted
    shots/keyframes already encode it.
    """

    parts = PurePosixPath(relative).parts
    name = parts[-1].casefold() if parts else ""
    if name in FORM_DEPENDENT_OUTPUT_HINTS:
        return True
    parent_names = [part.casefold() for part in parts[:-1]]
    if "storyboard" not in parent_names:
        return False
    return name in {
        "coverage.json",
        "shots.jsonl",
        "keyframes.jsonl",
        "keyframe-prompts.md",
    } or any(
        candidate in parent_names
        for candidate in ("coverage-auditions", "scene-visual-plans")
    )


def publish_candidate(
    path: Path,
    *,
    owner: str,
    artifact_id: str,
    outputs: Mapping[str, str | bytes],
    input_hashes: Mapping[str, str] | None = None,
    input_records: Mapping[str, Iterable[str]] | None = None,
    fault_injector: FaultInjector | None = None,
    allow_unregistered_path: bool = False,
    auto_bind_structured_refs: bool = True,
) -> dict[str, Any]:
    """Publish a validated candidate without claiming creator or review authority.

    ``input_records`` narrows an input binding from the whole file to the
    records this candidate actually consumed, so an unrelated append to a
    shared setting record or project file no longer invalidates it.
    """

    root = find_project(path)
    if not isinstance(owner, str) or re.fullmatch(r"[A-Za-z0-9._:-]+", owner) is None:
        raise ValueError("owner must be an opaque identifier")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("artifact id cannot be empty")
    normalized_outputs: dict[str, bytes] = {}
    output_paths: dict[str, str] = {}
    for raw, value in outputs.items():
        relative = _relative_path(raw)
        _remember_portable_path(output_paths, relative, label="candidate output")
        normalized_outputs[relative] = (
            value.encode("utf-8") if isinstance(value, str) else bytes(value)
        )
    if not normalized_outputs:
        raise ValueError("a candidate publication needs at least one output")
    _validate_compiled_prompt_outputs(root, normalized_outputs)
    form_gate_strict = (
        _effective_production_flow(root)["enforcement"] == "strict"
    )
    for relative, content in normalized_outputs.items():
        # Layout before content: a target that will be refused anyway should
        # say so, rather than first reporting that a file the creator never
        # meant to put there is not valid JSON.
        _validate_publication_layout(
            relative, owner=owner, allow_unregistered=allow_unregistered_path
        )
        if form_gate_strict and _output_requires_form(relative):
            form_ok, _form_issues = _form_status(root)
            if not form_ok:
                raise ValueError(
                    "strict production flow blocks form-dependent publication until "
                    "visual_direction and production_profile are accepted: " + relative
                )
        _validate_candidate_content(relative, content)
    _validate_m3_new_assets(root, owner, normalized_outputs)
    state = _read_state(root)
    artifacts = state["artifacts"]
    existing = artifacts.get(artifact_id, {})
    if isinstance(existing, dict) and existing.get("owner") not in (None, owner):
        raise ValueError("artifact owner cannot change during candidate publication")
    exact_inputs: dict[str, str] = {}
    input_paths: dict[str, str] = {}
    for raw, expected in (input_hashes or {}).items():
        relative = _relative_path(raw)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError(f"invalid input hash for {relative}")
        _remember_portable_path(input_paths, relative, label="input")
        exact_inputs[relative] = expected
    exact_inputs = dict(sorted(exact_inputs.items()))
    selectors = _normalize_record_selectors(input_records)
    _bind_and_validate_canonical_fragments(
        root, normalized_outputs, exact_inputs, selectors
    )
    prompt_targets = {
        relative: content
        for relative, content in normalized_outputs.items()
        if PurePosixPath(relative).name.casefold()
        in {"image-prompt-specs.jsonl", "keyframes.jsonl", "motion-specs.jsonl"}
    }
    fragment_binding_targets = dict(prompt_targets)
    fragment_binding_targets.update(
        {
            relative: content
            for relative, content in normalized_outputs.items()
            if PurePosixPath(relative).name.casefold() == "shots.jsonl"
        }
    )
    if fragment_binding_targets:
        fragments_relative = "设定集/generation/canonical-fragments.jsonl"
        fragments_path = _project_path(root, fragments_relative)
        if fragments_relative not in exact_inputs:
            raise ValueError(
                "BLK-PROMPT-COMPILE: prompt-bearing/shot outputs must declare "
                "canonical-fragments.jsonl as an exact input"
            )
        if not fragments_path.is_file() or sha256_file(fragments_path) != exact_inputs[fragments_relative]:
            raise ValueError("BLK-PROMPT-COMPILE: canonical fragment input hash is not current")
        fragment_ids: set[str] = set()
        for content in fragment_binding_targets.values():
            for line in content.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                record = _json_loads(line)
                components = record.get("prompt_components") if isinstance(record, dict) else None
                refs = components.get("fragment_refs") if isinstance(components, dict) else None
                if isinstance(refs, list):
                    fragment_ids.update(
                        reference["fragment_id"]
                        for reference in refs
                            if isinstance(reference, dict) and isinstance(reference.get("fragment_id"), str)
                    )
                shot_bindings = record.get("generation_asset_bindings") if isinstance(record, dict) else None
                if isinstance(shot_bindings, list):
                    for binding in shot_bindings:
                        if not isinstance(binding, dict):
                            continue
                        ids = binding.get("fragment_ids")
                        if isinstance(ids, list):
                            fragment_ids.update(item for item in ids if isinstance(item, str) and item)
                        fragment_refs = binding.get("fragment_refs")
                        if isinstance(fragment_refs, list):
                            fragment_ids.update(
                                reference["fragment_id"]
                                for reference in fragment_refs
                                if isinstance(reference, dict)
                                and isinstance(reference.get("fragment_id"), str)
                            )
        selectors.setdefault(fragments_relative, [])
        selectors[fragments_relative] = sorted(
            set(selectors[fragments_relative]) | fragment_ids
        )
    candidate_hashes = {
        relative: sha256_bytes(content)
        for relative, content in normalized_outputs.items()
    }
    for output, content in normalized_outputs.items():
        for (
            reference_owner,
            referenced_path,
            referenced_hash,
            reference_authority,
            record_id,
            field,
        ) in _structured_candidate_refs(output, content):
            if referenced_path in candidate_hashes:
                if reference_authority != "candidate":
                    raise ValueError(
                        "same-publication ref must declare candidate authority: "
                        f"{referenced_path}"
                    )
                if reference_owner != owner:
                    raise ValueError(
                        "same-publication ref owner does not match publication owner: "
                        f"{referenced_path}"
                    )
                if candidate_hashes[referenced_path] != referenced_hash:
                    raise ValueError(
                        "same-publication ref hash does not match candidate output: "
                        f"{referenced_path}"
                    )
                _structured_ref_selector(
                    normalized_outputs[referenced_path],
                    referenced_path,
                    record_id=record_id,
                    field=field,
                )
                continue
            if referenced_path not in exact_inputs:
                raise ValueError(
                    f"structured ref requires exact input: {referenced_path}"
                )
            referenced_content = _read_project_regular(root, referenced_path)
            input_file_hash = sha256_bytes(referenced_content)
            if input_file_hash != exact_inputs[referenced_path]:
                raise ValueError(
                    f"structured ref input is stale: {referenced_path}"
                )
            if input_file_hash != referenced_hash:
                raise ValueError(
                    f"structured ref input hash does not match: {referenced_path}"
                )
            selector = _structured_ref_selector(
                referenced_content,
                referenced_path,
                record_id=record_id,
                field=field,
            )
            if selector is not None and auto_bind_structured_refs:
                selectors.setdefault(referenced_path, [])
                selectors[referenced_path] = sorted(
                    set(selectors[referenced_path]) | {selector}
                )
            if _intrinsic_authority_ref(reference_owner, referenced_path):
                continue
            accepted_providers = _ref_providers(
                artifacts,
                relative=referenced_path,
                digest=input_file_hash,
                owner=reference_owner,
                target_key="accepted_targets",
            )
            candidate_providers = _ref_providers(
                artifacts,
                relative=referenced_path,
                digest=input_file_hash,
                owner=reference_owner,
                target_key="candidate_targets",
            )
            if len(accepted_providers) > 1 or len(candidate_providers) > 1:
                raise ValueError(
                    f"structured ref provider is ambiguous: {referenced_path}"
                )
            if reference_authority == "candidate":
                if accepted_providers:
                    raise ValueError(
                        "accepted input cannot declare candidate authority: "
                        f"{referenced_path}"
                    )
                if not candidate_providers:
                    raise ValueError(
                        "candidate input has no matching candidate provider: "
                        f"{referenced_path}"
                    )
            elif not accepted_providers:
                raise ValueError(
                    "accepted structured ref has no matching accepted provider: "
                    f"{referenced_path}"
                )
    _validate_scene_sheet_evidence_bindings(root, normalized_outputs, exact_inputs)
    unbound = sorted(set(selectors) - set(exact_inputs))
    if unbound:
        raise ValueError(
            "record binding needs an exact input: " + ", ".join(unbound)
        )
    read_records: dict[str, dict[str, str]] = {}
    for relative, wanted in selectors.items():
        source = _project_path(root, relative)
        if not source.is_file():
            raise ValueError(f"record binding source is unavailable: {relative}")
        content = source.read_bytes()
        if sha256_bytes(content) != exact_inputs[relative]:
            raise ValueError(f"record binding source does not match input: {relative}")
        digests = _record_digests(content, relative, wanted)
        read_records[relative] = {
            selector: digest
            for selector, digest in digests.items()
            if digest is not None
        }
    lifecycle_changes = {
        artifact_id: {
            "build_state": "materialized",
            "validation_state": "not_run",
            "creator_acceptance": "pending",
            "independent_review": "provisional",
            "delivery_gate": "blocked",
        },
        **_downstream_stale_changes(
            state,
            publishing_artifact=artifact_id,
            candidate_targets=candidate_hashes,
            candidate_contents=normalized_outputs,
        ),
    }
    transaction = publish_transaction(
        root,
        stage="candidate",
        outputs=normalized_outputs,
        lifecycle_changes=lifecycle_changes,
        target_artifacts={relative: artifact_id for relative in normalized_outputs},
        read_set=exact_inputs,
        read_records=read_records,
        authority="candidate",
        owner=owner,
        allow_unregistered_path=allow_unregistered_path,
        fault_injector=fault_injector,
    )
    return {
        **transaction,
        "authority": "candidate",
        "owner": owner,
        "artifact_id": artifact_id,
    }


def record_creator_acceptance(
    path: Path,
    *,
    artifact_id: str,
    decision: str,
    target_hashes: Mapping[str, str],
    evidence_ref: Mapping[str, Any],
) -> dict[str, Any]:
    """Record a creator decision against one exact candidate snapshot."""

    root = find_project(path)
    normalized_decision = decision.casefold()
    if normalized_decision not in {"accepted", "rejected"}:
        raise ValueError("creator decision must be accepted or rejected")
    targets = _normalize_hash_mapping(target_hashes, label="creator decision target")
    with _transaction_lock(root):
        state = _read_state(root)
        artifacts = state.setdefault("artifacts", {})
        record = artifacts.get(artifact_id)
        if not isinstance(record, dict):
            raise ValueError(f"unknown candidate artifact: {artifact_id}")
        candidates = record.get("candidate_targets")
        if not isinstance(candidates, dict) or candidates != targets:
            raise ValueError("creator decision does not match exact candidate targets")
        _verify_live_hashes(root, targets, label="candidate target")
        candidate_inputs = _input_bindings(record, "candidate_inputs")
        candidate_input_records = _input_record_bindings(record, "candidate_input_records")
        m2_names = {
            "/".join(PurePosixPath(path).parts[2:])
            for path in targets
            if len(PurePosixPath(path).parts) >= 3
        }
        complete_m2 = {
            "episode-card.json",
            "beats.jsonl",
            "screenplay.md",
            "screenplay-index.jsonl",
        } <= m2_names
        if (
            normalized_decision == "accepted"
            and record.get("owner") == "short-drama-write"
            and complete_m2
            and _effective_production_flow(root).get("pipeline_version") == PIPELINE_VERSION
        ):
            m2_issues = _m2_generation_binding_issues(
                root,
                target_paths=targets,
                input_records=candidate_input_records,
            )
            if m2_issues:
                raise ValueError("BLK-M2-ASSET-REF: " + "; ".join(m2_issues))
        if (
            normalized_decision == "accepted"
            and _effective_production_flow(root).get("pipeline_version") == PIPELINE_VERSION
        ):
            stage_issues = _fixed_stage_acceptance_issues(
                root,
                state,
                artifact_id=artifact_id,
                owner=str(record.get("owner") or ""),
                target_paths=targets,
            )
            if stage_issues:
                code, issues = stage_issues
                raise ValueError(f"{code}: " + "; ".join(issues))
        _validate_input_closure(
            root,
            state,
            artifact_id,
            bindings=candidate_inputs,
            record_bindings=candidate_input_records,
        )
        evidence, decision_record = _validate_creator_decision_evidence(
            root,
            evidence_ref,
            decision=normalized_decision,
            artifact_id=artifact_id,
            target_hashes=targets,
        )
        if evidence["artifact"] in targets:
            raise ValueError("creator decision evidence must be separate from its target")
        updated = apply_lifecycle_changes(
            record,
            {
                "creator_acceptance": normalized_decision,
                "independent_review": "not_requested",
                "delivery_gate": "blocked",
            },
        )
        updated["creator_decision"] = {
            "decision": normalized_decision,
            "target_hashes": targets,
            "evidence_ref": evidence,
            "authority": _validate_decision_authority(
                root,
                decision_record,
                artifact_id=artifact_id,
                operation="artifact_acceptance",
            ),
        }
        updated.pop("review_evidence", None)
        if normalized_decision == "accepted":
            snapshots = updated.get("candidate_snapshots")
            if not isinstance(snapshots, dict) or set(snapshots) != set(targets):
                raise RecoveryMaterialError("candidate snapshots are incomplete")
            for relative, digest in targets.items():
                snapshot = _project_path(
                    root, _relative_path(snapshots[relative], allow_operations=True)
                )
                if not snapshot.is_file() or sha256_file(snapshot) != digest:
                    raise RecoveryMaterialError("candidate snapshot is missing or corrupt")
            updated["accepted_targets"] = targets
            updated["accepted_snapshots"] = dict(sorted(snapshots.items()))
            updated["accepted_inputs"] = candidate_inputs
            if candidate_input_records:
                updated["accepted_input_records"] = candidate_input_records
            else:
                updated.pop("accepted_input_records", None)
            material = _json_dumps(
                targets, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            updated["accepted_snapshot"] = sha256_bytes(material)
            # Acceptance ends the candidate phase: archive the candidate
            # fields so "current target" resolves to the accepted snapshot and
            # re-running accept against the same target fails instead of
            # silently re-applying. Recovery is transaction-scoped and reads
            # the pointer matching the manifest authority, so this cannot break
            # an interrupted candidate or accepted transaction.
            for key in (
                "candidate_targets",
                "candidate_inputs",
                "candidate_input_records",
                "candidate_snapshots",
                "candidate_source_transaction",
                "candidate_snapshot",
            ):
                updated.pop(key, None)
        artifacts[artifact_id] = updated
        state["updated_at"] = utc_now()
        state["last_action"] = "creator_acceptance_recorded"
        atomic_json(root / STATE_FILE, state)
    return {
        "artifact_id": artifact_id,
        "creator_acceptance": normalized_decision,
        "target_count": len(targets),
        "status": "recorded",
    }


def _decision_records_from_file(
    path: Path,
) -> list[tuple[str | None, dict[str, Any]]]:
    """Return (record_id, record) pairs from one creator-decision evidence file."""

    def identity(record: dict[str, Any]) -> str | None:
        # Creator-decision records carry both decision_id and artifact_id, so
        # the generic `*_id` heuristic is ambiguous; the lifecycle evidence
        # contract locates JSONL records by decision_id.
        value = record.get("decision_id")
        return value if isinstance(value, str) and value else None

    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            return [
                (identity(record), record)
                for record in _jsonl_records(path.read_bytes(), path.name)
            ]
        if suffix == ".json":
            document = _json_loads(path.read_text(encoding="utf-8"))
            if isinstance(document, dict):
                return [(identity(document), document)]
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return []
    return []


def accept_decisions_batch(
    path: Path,
    *,
    decisions_dir: str | None = None,
    extra_evidence: Iterable[str] = (),
) -> dict[str, Any]:
    """Apply creator acceptance records already written to disk in one process.

    `accept` records one artifact per call; batch production (several episodes
    at once) would otherwise cost one model tool call per artifact. This
    command scans the project's creator-decisions root for
    `artifact_acceptance` records whose decision/status is `accepted`,
    verifies each exactly like `accept` does (candidate targets, live hashes,
    input closure, evidence file), and applies them. It never invents a
    decision: missing or mismatched records fail and the command exits
    non-zero if anything failed.
    """

    root = find_project(path)
    layout = project_layout(root)
    roots = layout.get("roots")
    if decisions_dir:
        decision_root = _relative_path(decisions_dir)
    elif isinstance(roots, dict) and roots.get("creator-decisions"):
        decision_root = str(roots["creator-decisions"])
    else:
        decision_root = "创作者决策"
    evidence_files: list[str] = []
    decision_path = _project_path(root, decision_root)
    if decision_path.is_dir():
        for entry in sorted(decision_path.iterdir()):
            if entry.is_file() and entry.suffix.lower() in {".json", ".jsonl"}:
                evidence_files.append(f"{decision_root}/{entry.name}")
    for raw in extra_evidence:
        relative = _relative_path(raw)
        if relative not in evidence_files:
            evidence_files.append(relative)

    results: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    decision_identities: dict[str, list[str]] = {}
    supersession_links: list[tuple[str, str]] = []
    for relative in evidence_files:
        source = _project_path(root, relative)
        if not source.is_file():
            results.append(
                {
                    "file": relative,
                    "artifact_id": None,
                    "status": "failed",
                    "reason": "evidence file is unavailable",
                }
            )
            continue
        digest = sha256_file(source)
        decisions = _decision_records_from_file(source)
        if not decisions:
            results.append(
                {
                    "file": relative,
                    "artifact_id": None,
                    "status": "failed",
                    "reason": "no parseable decision records found",
                }
            )
            continue
        for record_id, record in decisions:
            if record.get("decision_kind") != "artifact_acceptance":
                continue
            artifact_id = record.get("artifact_id")
            raw_decision = record.get("decision") or record.get("status")
            target_hashes = record.get("target_hashes")
            if isinstance(record_id, str) and isinstance(artifact_id, str):
                decision_identities.setdefault(record_id, []).append(artifact_id)
            superseded = record.get("supersedes_decision_id")
            if (
                isinstance(record_id, str)
                and isinstance(artifact_id, str)
                and isinstance(superseded, str)
                and superseded
                and isinstance(raw_decision, str)
                and raw_decision.casefold() in {"accepted", "rejected"}
                and isinstance(target_hashes, dict)
            ):
                supersession_links.append((record_id, superseded))
            if not isinstance(raw_decision, str) or raw_decision.casefold() != "accepted":
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "skipped",
                        "reason": f"decision is not accepted: {raw_decision!r}",
                    }
                )
                continue
            if not isinstance(artifact_id, str) or not isinstance(target_hashes, dict):
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": "record lacks artifact_id or target_hashes",
                    }
                )
                continue
            try:
                normalized_targets = _normalize_hash_mapping(
                    {
                        str(key): str(value)
                        for key, value in target_hashes.items()
                        if isinstance(key, str) and isinstance(value, str)
                    },
                    label="creator decision target",
                )
            except ValueError as error:
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": str(error),
                    }
                )
                continue
            tasks.append(
                {
                    "file": relative,
                    "digest": digest,
                    "record_id": record_id,
                    "artifact_id": artifact_id,
                    "target_hashes": normalized_targets,
                }
            )

    superseded_ids = {
        superseded_id
        for superseding_id, superseded_id in supersession_links
        if len(decision_identities.get(superseding_id, [])) == 1
        and len(decision_identities.get(superseded_id, [])) == 1
        and decision_identities[superseding_id][0]
        == decision_identities[superseded_id][0]
    }
    pending: list[dict[str, Any]] = []
    for task in tasks:
        if task["record_id"] in superseded_ids:
            results.append(
                {
                    "file": task["file"],
                    "artifact_id": task["artifact_id"],
                    "status": "skipped",
                    "reason": "decision is superseded by a newer evidence record",
                }
            )
        else:
            pending.append(task)

    while pending:
        progress = False
        retry: list[dict[str, Any]] = []
        for task in pending:
            artifact_id = task["artifact_id"]
            digest = task["digest"]
            evidence_ref: dict[str, Any] = {
                "owner": "creator",
                "artifact": task["file"],
                "hash": digest,
            }
            if task["record_id"] is not None:
                evidence_ref["record_id"] = task["record_id"]
            try:
                current_state = _read_state(root)
                current_artifacts = (
                    current_state.get("artifacts", {})
                    if isinstance(current_state, dict)
                    else {}
                )
                already = current_artifacts.get(artifact_id)
                accepted_targets = (
                    already.get("accepted_targets")
                    if isinstance(already, dict)
                    else None
                )
                recorded_evidence = (
                    already.get("creator_decision", {}).get("evidence_ref")
                    if isinstance(already, dict)
                    else None
                )
                evidence_hash_matches = (
                    isinstance(recorded_evidence, dict)
                    and recorded_evidence.get("hash") == digest
                )
                if (
                    isinstance(already, dict)
                    and already.get("creator_acceptance") == "accepted"
                    and isinstance(accepted_targets, dict)
                    and accepted_targets == task["target_hashes"]
                    and evidence_hash_matches
                ):
                    results.append(
                        {
                            "file": task["file"],
                            "artifact_id": artifact_id,
                            "status": "skipped",
                            "reason": "already accepted with identical targets",
                        }
                    )
                    continue
                record_creator_acceptance(
                    root,
                    artifact_id=artifact_id,
                    decision="accepted",
                    target_hashes=task["target_hashes"],
                    evidence_ref=evidence_ref,
                )
                results.append(
                    {
                        "file": task["file"],
                        "artifact_id": artifact_id,
                        "status": "accepted",
                    }
                )
                progress = True
            except (OSError, ValueError, TransactionError) as error:
                reason = str(error)
                if any(
                    marker in reason
                    for marker in (
                        "accepted input has no matching accepted provider",
                        "accepted input provider is not current",
                        "accepted structured ref has no matching accepted provider",
                    )
                ):
                    retry.append({**task, "last_error": reason})
                    continue
                results.append(
                    {
                        "file": task["file"],
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": reason,
                    }
                )
        if not retry:
            break
        if progress:
            pending = retry
            continue
        results.extend(
            {
                "file": task["file"],
                "artifact_id": task["artifact_id"],
                "status": "failed",
                "reason": task["last_error"],
            }
            for task in retry
        )
        break
    return {
        "checked": len(results),
        "applied": sum(result["status"] == "accepted" for result in results),
        "skipped": sum(result["status"] == "skipped" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }


def _verdict_records_from_file(path: Path) -> list[tuple[str | None, dict[str, Any]]]:
    """Return (review_id, document) pairs from one review-verdict evidence file.

    Verdict evidence must be a single JSON object (`review` requires a JSON
    artifact), so only the top-level document is read; its `review_id` becomes
    the record identity for evidence binding.
    """

    try:
        document = _json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(document, dict):
        return []
    review_id = document.get("review_id")
    identity = review_id if isinstance(review_id, str) and review_id else None
    return [(identity, document)]


def review_verdicts_batch(
    path: Path,
    *,
    verdicts_dir: str | None = None,
    extra_evidence: Iterable[str] = (),
    episode: str | None = None,
) -> dict[str, Any]:
    """Apply review verdict documents already written to disk in one process.

    `review` records one artifact per call; batch production would otherwise
    cost one model tool call per verdict. This command scans the project's
    reviews root for verdict JSON documents, verifies each exactly like
    `review` does (accepted targets, creator acceptance evidence, input
    closure, live hashes, verdict evidence), and records it. It never invents
    a verdict: documents without a review_id are skipped, anything the verdict
    validation rejects fails, and the command exits non-zero if anything
    failed. `findings_ref` inside each document binds its own findings file,
    so the batch does not need one findings file per command call.
    With `episode` set (e.g. EP001), verdicts whose artifact_id does not
    target that episode are skipped, so one episode's conclusions are applied
    in a single pass while other episodes' verdicts stay untouched.
    """

    root = find_project(path)
    layout = project_layout(root)
    roots = layout.get("roots")
    if verdicts_dir:
        verdict_root = _relative_path(verdicts_dir)
    elif isinstance(roots, dict) and roots.get("reviews"):
        verdict_root = str(roots["reviews"])
    else:
        verdict_root = "审查"
    evidence_files: list[str] = []
    verdict_path = _project_path(root, verdict_root)
    if verdict_path.is_dir():
        for entry in sorted(verdict_path.iterdir()):
            if entry.is_file() and entry.suffix.lower() == ".json":
                evidence_files.append(f"{verdict_root}/{entry.name}")
    for raw in extra_evidence:
        relative = _relative_path(raw)
        if relative not in evidence_files:
            evidence_files.append(relative)

    # Stable ordering independent of file names: a fresh/independent verdict
    # must land AFTER every non-independent one when they target the same
    # artifact. Applying a delta or cold_read last would set the delivery gate
    # to blocked and leave the final state wrong — only an independent verdict
    # may open the gate, so it must be the last one applied. Verdicts whose
    # mode cannot be read sort to the end by file name.
    _MODE_ORDER = {
        "delta_verify": 0,
        "cold_read": 1,
        "independent_agent": 2,
    }

    def _mode_key(relative: str) -> tuple[int, str]:
        try:
            document = _json_loads(
                _project_path(root, relative).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            return (3, relative)
        if not isinstance(document, dict):
            return (3, relative)
        mode = document.get("requested_review_mode")
        order = _MODE_ORDER.get(mode) if isinstance(mode, str) else None
        return (3 if order is None else order, relative)

    evidence_files.sort(key=_mode_key)

    results: list[dict[str, Any]] = []
    for relative in evidence_files:
        source = _project_path(root, relative)
        if not source.is_file():
            results.append(
                {
                    "file": relative,
                    "artifact_id": None,
                    "status": "failed",
                    "reason": "evidence file is unavailable",
                }
            )
            continue
        digest = sha256_file(source)
        records = _verdict_records_from_file(source)
        if not records:
            results.append(
                {
                    "file": relative,
                    "artifact_id": None,
                    "status": "failed",
                    "reason": "no parseable verdict records found",
                }
            )
            continue
        for record_id, document in records:
            if record_id is None:
                results.append(
                    {
                        "file": relative,
                        "artifact_id": None,
                        "status": "skipped",
                        "reason": "verdict has no review_id",
                    }
                )
                continue
            artifact_id = document.get("artifact_id")
            verdict = document.get("verdict")
            reviewer = document.get("reviewer")
            verdict_owner = reviewer.get("owner") if isinstance(reviewer, dict) else None
            reviewed_artifacts = document.get("reviewed_artifacts")
            if not isinstance(artifact_id, str):
                results.append(
                    {
                        "file": relative,
                        "artifact_id": None,
                        "status": "failed",
                        "reason": "verdict lacks artifact_id",
                    }
                )
                continue
            if episode is not None and not artifact_id.startswith(f"{episode}:"):
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "skipped",
                        "reason": f"verdict is not for episode {episode}",
                    }
                )
                continue
            if not isinstance(verdict, str):
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": "verdict lacks a verdict value",
                    }
                )
                continue
            if not isinstance(reviewed_artifacts, list) or not reviewed_artifacts:
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": "verdict reviewed_artifacts must be a non-empty array",
                    }
                )
                continue
            reviewed_targets: dict[str, str] = {}
            malformed: str | None = None
            for raw_reference in reviewed_artifacts:
                if not isinstance(raw_reference, dict):
                    malformed = "verdict reviewed artifact ref is invalid"
                    break
                target_path = raw_reference.get("artifact")
                target_hash = raw_reference.get("hash")
                if not isinstance(target_path, str) or not isinstance(target_hash, str):
                    malformed = "verdict reviewed artifact ref is invalid"
                    break
                if target_path in reviewed_targets:
                    malformed = (
                        "verdict reviewed artifact refs are duplicated: "
                        f"{target_path}"
                    )
                    break
                reviewed_targets[target_path] = target_hash
            if malformed is not None:
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": malformed,
                    }
                )
                continue
            if not isinstance(verdict_owner, str):
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": "verdict reviewer owner is unavailable",
                    }
                )
                continue
            verdict_ref: dict[str, Any] = {
                "owner": verdict_owner,
                "artifact": relative,
                "hash": digest,
            }
            if record_id is not None:
                verdict_ref["record_id"] = record_id
            try:
                record_independent_review(
                    root,
                    artifact_id=artifact_id,
                    verdict=verdict,
                    reviewed_targets=reviewed_targets,
                    verdict_ref=verdict_ref,
                )
                results.append(
                    {"file": relative, "artifact_id": artifact_id, "status": "recorded"}
                )
            except (OSError, ValueError, TransactionError) as error:
                results.append(
                    {
                        "file": relative,
                        "artifact_id": artifact_id,
                        "status": "failed",
                        "reason": str(error),
                    }
                )
    return {
        "checked": len(results),
        "applied": sum(result["status"] == "recorded" for result in results),
        "skipped": sum(result["status"] == "skipped" for result in results),
        "failed": sum(result["status"] == "failed" for result in results),
        "results": results,
    }


def write_creator_decision(
    path: Path,
    *,
    artifact_id: str,
    decision: str,
    decided_by: str = "creator",
    delegation_artifact: str | None = None,
    delegation_hash: str | None = None,
    delegation_record_id: str | None = None,
    output: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Write one compliant artifact_acceptance decision file for a candidate.

    The batch flow used to require hand-crafted decision JSON (decision_id,
    target_hashes, evidence self-references); any field mismatch fails
    `accept-batch` wholesale. This command derives the exact candidate targets
    from project state and writes a record that `accept-batch` and `accept`
    both accept. It never decides for the creator — the decision content is
    still whatever the creator confirms — it only removes the file-format
    chore. State is not touched: `accept-batch` still applies the decision.
    """

    root = find_project(path)
    normalized_decision = decision.casefold()
    if normalized_decision not in {"accepted", "rejected"}:
        raise ValueError("creator decision must be accepted or rejected")
    state = _read_state(root)
    record = state.get("artifacts", {}).get(artifact_id)
    candidate_targets = (
        record.get("candidate_targets") if isinstance(record, dict) else None
    )
    if not isinstance(candidate_targets, dict) or not candidate_targets:
        raise ValueError(f"unknown candidate artifact: {artifact_id}")
    targets = _normalize_hash_mapping(candidate_targets, label="candidate target")
    layout = project_layout(root)
    roots = layout.get("roots")
    decision_root = (
        str(roots["creator-decisions"])
        if isinstance(roots, dict) and roots.get("creator-decisions")
        else "创作者决策"
    )
    if output:
        relative = _relative_path(output)
        # A decision file is lifecycle evidence that accept-batch scans from the
        # creator-decisions root, and publish-time layout protection (protected
        # roots such as 交付/ and 输入/) does not apply to decide's own write.
        # Reject any explicit target that escapes that root instead of letting
        # --output write into a protected tree or orphan the decision.
        _validate_publication_layout(relative)
        decision_root_prefix = decision_root.rstrip("/") + "/"
        if relative != decision_root.rstrip("/") and not relative.startswith(
            decision_root_prefix
        ):
            raise ValueError(
                "decision output must live under the creator-decisions root "
                f"({decision_root}): {relative}"
            )
    else:
        label = re.sub(r"[^A-Za-z0-9._-]+", "-", artifact_id).strip("-.") or "artifact"
        relative = f"{decision_root}/{label}.json"
    decision_path = _project_path(root, relative)
    supersedes_decision_id = None
    if decision_path.exists():
        if not force:
            raise FileExistsError(f"decision file already exists: {relative}")
        # Accepted evidence is immutable: find the latest unsuperseded decision
        # for this artifact, link to it, and write a sibling file. Replacing the
        # old bytes would invalidate every accepted artifact that cites them.
        candidates: list[dict[str, Any]] = []
        for entry in sorted(decision_path.parent.glob("*.json")):
            try:
                previous = _json_loads(entry.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                continue
            if (
                isinstance(previous, dict)
                and previous.get("decision_kind") == "artifact_acceptance"
                and previous.get("artifact_id") == artifact_id
                and isinstance(previous.get("decision_id"), str)
            ):
                candidates.append(previous)
        superseded = {
            value
            for candidate in candidates
            if isinstance(
                (value := candidate.get("supersedes_decision_id")), str
            )
            and value
        }
        tips = [
            candidate
            for candidate in candidates
            if candidate["decision_id"] not in superseded
        ]
        if tips:
            latest = max(
                tips,
                key=lambda candidate: (
                    str(candidate.get("decided_at") or ""),
                    str(candidate["decision_id"]),
                ),
            )
            supersedes_decision_id = latest["decision_id"]
    decision_id = f"CD-{uuid.uuid4().hex[:12].upper()}"
    if decision_path.exists():
        pure = PurePosixPath(relative)
        relative = pure.with_name(
            f"{pure.stem}.superseding-{decision_id}{pure.suffix}"
        ).as_posix()
        decision_path = _project_path(root, relative)
    document = {
        "decision_id": decision_id,
        "decision_kind": "artifact_acceptance",
        "artifact_id": artifact_id,
        "status": normalized_decision,
        "target_hashes": targets,
        "decided_by": decided_by,
        "decided_at": utc_now(),
        "supersedes_decision_id": supersedes_decision_id,
    }
    if decided_by != "creator":
        if delegation_artifact is None:
            raise ValueError("delegated creator decision requires --delegation-artifact")
        delegation_ref: dict[str, Any] = {
            "owner": "creator",
            "artifact": delegation_artifact,
            "hash": delegation_hash
            or sha256_file(_project_path(root, delegation_artifact)),
        }
        if delegation_record_id:
            delegation_ref["record_id"] = delegation_record_id
        document["delegation_ref"] = delegation_ref
        _validate_decision_authority(
            root,
            document,
            artifact_id=artifact_id,
            operation="artifact_acceptance",
        )
    elif delegation_artifact or delegation_hash or delegation_record_id:
        raise ValueError("direct creator decisions must not carry delegation evidence")
    atomic_json(decision_path, document)
    return {
        "decision_id": document["decision_id"],
        "artifact_id": artifact_id,
        "decision": normalized_decision,
        "target_count": len(targets),
        "path": relative,
        "status": "written",
    }


def unpublish_artifact(
    path: Path,
    *,
    artifact_id: str,
) -> dict[str, Any]:
    """Remove an artifact record that was published but never accepted.

    A mis-published candidate (wrong direction, duplicate ownership of a shared
    file) has no tool path to undo: `recover` only repairs interrupted
    transactions, and there is no way to drop a committed record without
    hand-editing state. This command removes the record for an artifact whose
    `creator_acceptance` is not `accepted` — accepted artifacts are protected
    because downstream accepted evidence chains depend on them.

    The check is structural: any other record that names this artifact's
    candidate targets among its candidate/accepted inputs depends on it, and
    removal is refused with the dependents listed. Snapshot files are kept
    (orphans are harmless) and content files are never touched — only the
    state record disappears, so a corrected candidate can be published and
    accepted again.
    """

    root = find_project(path)
    with _transaction_lock(root):
        state = _read_state(root)
        artifacts = state.setdefault("artifacts", {})
        record = artifacts.get(artifact_id)
        if not isinstance(record, dict):
            raise ValueError(f"unknown artifact: {artifact_id}")
        if record.get("creator_acceptance") == "accepted":
            raise ValueError(
                "refusing to unpublish an accepted artifact: "
                f"{artifact_id} (its evidence chain is frozen)"
            )
        candidate_targets = record.get("candidate_targets")
        if not isinstance(candidate_targets, dict):
            raise ValueError(
                f"artifact has no candidate targets to revoke: {artifact_id}"
            )
        dependents = sorted(
            other_id
            for other_id, other in artifacts.items()
            if other_id != artifact_id
            if isinstance(other, dict)
            if any(
                candidate_targets.get(relative) is not None
                for source in (
                    other.get("candidate_inputs"),
                    other.get("accepted_inputs"),
                )
                if isinstance(source, dict)
                for relative in source
            )
        )
        if dependents:
            raise ValueError(
                "refusing to unpublish: these artifacts depend on "
                f"{artifact_id}: {', '.join(dependents)}"
            )
        del artifacts[artifact_id]
        state["updated_at"] = utc_now()
        state["last_action"] = "artifact_unpublished"
        atomic_json(root / STATE_FILE, state)
    return {"artifact_id": artifact_id, "status": "unpublished"}


def _normalize_review_verdict(value: str) -> str:
    normalized = value.casefold().replace("-", "_")
    if normalized not in {"approve", "approve_with_notes", "revise", "provisional"}:
        raise ValueError("invalid independent review verdict")
    return normalized


def _normalize_reviewer_evidence(
    raw_reviewer: Any,
    *,
    verdict_owner: str,
    artifact_owner: str,
    require_independent: bool = True,
    non_independent_kinds: frozenset[str] = frozenset({"self_check", "unattested"}),
) -> dict[str, Any]:
    if not isinstance(raw_reviewer, dict):
        raise ValueError("reviewer evidence must be an object")
    reviewer_owner = raw_reviewer.get("owner")
    reviewer_kind = raw_reviewer.get("kind")
    excluded = raw_reviewer.get("excluded_owner_skills")
    if reviewer_owner != verdict_owner:
        raise ValueError("reviewer owner does not match verdict owner")
    if (
        not isinstance(excluded, list)
        or any(not isinstance(owner, str) or not owner for owner in excluded)
        or len(excluded) != len(set(excluded))
        or set(excluded) != {artifact_owner}
    ):
        raise ValueError("reviewer excluded owner must match artifact owner")
    if not require_independent:
        if reviewer_kind not in non_independent_kinds:
            raise ValueError("non-independent reviewer kind is invalid")
        if raw_reviewer.get("independent") is not False:
            raise ValueError("provisional reviewer must not assert independence")
        if raw_reviewer.get("provenance") is not None:
            raise ValueError("provisional reviewer must not claim fresh provenance")
        return {
            "owner": reviewer_owner,
            "kind": reviewer_kind,
            "independent": False,
            "excluded_owner_skills": list(excluded),
            "provenance": None,
        }

    provenance = raw_reviewer.get("provenance")
    if reviewer_kind != "independent_agent":
        raise ValueError("reviewer kind must be independent_agent")
    if raw_reviewer.get("independent") is not True:
        raise ValueError("reviewer does not assert independence")
    if not isinstance(provenance, dict):
        raise ValueError("reviewer fresh-context provenance is missing")
    context_id = provenance.get("context_id")
    if not isinstance(context_id, str) or not context_id.strip():
        raise ValueError("reviewer fresh-context provenance has no context_id")
    if provenance.get("fresh_context") is not True:
        raise ValueError("reviewer context is not fresh")
    if provenance.get("authored_reviewed_artifacts") is not False:
        raise ValueError("reviewer authored a reviewed artifact")
    return {
        "owner": reviewer_owner,
        "kind": reviewer_kind,
        "independent": True,
        "excluded_owner_skills": list(excluded),
        "provenance": {
            "context_id": context_id,
            "fresh_context": True,
            "authored_reviewed_artifacts": False,
        },
    }


def _load_findings(
    root: Path, findings_ref: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    relative = str(findings_ref["artifact"])
    if PurePosixPath(relative).suffix.lower() != ".jsonl":
        raise ValueError("verdict findings_ref must reference JSONL")
    findings: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(
        _project_path(root, relative).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            finding = _json_loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid findings JSONL at line {number}") from error
        if not isinstance(finding, dict):
            raise ValueError("findings JSONL records must be objects")
        finding_id = finding.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id:
            raise ValueError("findings JSONL record has no finding_id")
        if finding_id in findings:
            raise ValueError(f"findings JSONL duplicates finding_id: {finding_id}")
        status = finding.get("status")
        severity = finding.get("severity")
        if not isinstance(status, str) or status.casefold() not in {
            "open",
            "closed",
            "superseded",
        }:
            raise ValueError(f"findings JSONL status is invalid: {finding_id}")
        if not isinstance(severity, str) or severity.casefold() not in {
            "fatal",
            "error",
            "warning",
            "note",
        }:
            raise ValueError(f"findings JSONL severity is invalid: {finding_id}")
        findings[finding_id] = finding
    return findings


def _open_blocking_finding_ids(root: Path, findings_ref: Mapping[str, Any]) -> set[str]:
    findings = _load_findings(root, findings_ref)
    return _open_blocking_ids(findings)


def _open_blocking_ids(findings: Mapping[str, dict[str, Any]]) -> set[str]:
    return {
        finding_id
        for finding_id, finding in findings.items()
        if str(finding.get("status", "")).casefold() == "open"
        and (
            str(finding.get("severity", "")).casefold()
            in {"fatal", "error"}
            or finding.get("blocking") is True
        )
    }


def _validate_delta_basis(
    root: Path,
    *,
    document: Mapping[str, Any],
    artifact_owner: str,
    verdict_owner: str,
    current_targets: Mapping[str, str],
    findings: Mapping[str, dict[str, Any]],
) -> None:
    """Re-verify that a delta_verify verdict legitimately closes its base."""
    basis = document.get("delta_basis")
    if not isinstance(basis, dict):
        raise ValueError("delta verdict is missing delta_basis")
    raw_base_ref = basis.get("base_verdict_ref")
    if not isinstance(raw_base_ref, dict):
        raise ValueError("delta_basis base_verdict_ref is missing")
    base_ref = _normalize_artifact_ref(
        root, raw_base_ref, expected_owner=verdict_owner
    )
    base_review_id = basis.get("base_review_id")
    if not isinstance(base_review_id, str) or not base_review_id:
        raise ValueError("delta_basis base_review_id is missing")
    try:
        base_document = _json_loads(
            _project_path(root, base_ref["artifact"]).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("delta base verdict artifact is invalid") from error
    if not isinstance(base_document, dict):
        raise ValueError("delta base verdict must be a JSON object")
    if base_document.get("review_id") != base_review_id:
        raise ValueError("delta_basis base_review_id does not match base verdict")
    if _normalize_review_verdict(str(base_document.get("verdict", ""))) == "provisional":
        raise ValueError("delta base verdict is provisional")
    base_effective_mode = base_document.get("effective_review_mode")
    if base_effective_mode == "fresh_agent":
        if base_document.get("requested_review_mode") != "independent_agent":
            raise ValueError("delta base verdict did not request an independent agent")
        _normalize_reviewer_evidence(
            base_document.get("reviewer"),
            verdict_owner=base_ref["owner"],
            artifact_owner=artifact_owner,
            require_independent=True,
        )
    elif base_effective_mode == "cold_read":
        if base_document.get("requested_review_mode") != "cold_read":
            raise ValueError("delta base verdict did not request a cold_read review")
        _normalize_reviewer_evidence(
            base_document.get("reviewer"),
            verdict_owner=base_ref["owner"],
            artifact_owner=artifact_owner,
            require_independent=False,
            non_independent_kinds=frozenset({"cold_reader"}),
        )
    else:
        raise ValueError("delta base verdict was not a fresh_agent or cold_read review")
    base_reviewed = base_document.get("reviewed_artifacts")
    if not isinstance(base_reviewed, list) or not base_reviewed:
        raise ValueError("delta base verdict reviewed_artifacts is invalid")
    base_paths: set[str] = set()
    for raw_reference in base_reviewed:
        if not isinstance(raw_reference, dict) or not isinstance(
            raw_reference.get("artifact"), str
        ):
            raise ValueError("delta base verdict reviewed artifact ref is invalid")
        base_paths.add(raw_reference["artifact"])
    if base_paths != set(current_targets):
        raise ValueError("delta verdict target set differs from its base verdict")
    base_blockers = base_document.get("blocking_findings")
    if not isinstance(base_blockers, list) or any(
        not isinstance(finding_id, str) for finding_id in base_blockers
    ):
        raise ValueError("delta base verdict blocking_findings is invalid")
    for finding_id in base_blockers:
        finding = findings.get(finding_id)
        if finding is None:
            raise ValueError(
                f"delta verdict findings are missing base blocker: {finding_id}"
            )
        if str(finding.get("status", "")).casefold() == "open":
            raise ValueError(
                f"delta verdict leaves base blocker open: {finding_id}"
            )


def _validate_review_verdict_evidence(
    root: Path,
    *,
    artifact_owner: str,
    verdict: str,
    reviewed_targets: Mapping[str, str],
    verdict_ref: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    reference = _normalize_artifact_ref(root, verdict_ref)
    if reference["owner"] == artifact_owner:
        raise ValueError("independent review owner must differ from artifact owner")
    if PurePosixPath(reference["artifact"]).suffix.lower() != ".json":
        raise ValueError("independent review verdict must be a JSON artifact")
    try:
        document = _json_loads(
            _project_path(root, reference["artifact"]).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("independent review verdict artifact is invalid") from error
    if not isinstance(document, dict):
        raise ValueError("independent review verdict must be a JSON object")

    # One pass over every independently checkable field, collecting all
    # problems instead of raising on the first. The linear checks below then
    # run against a document whose shape is already known good, so a broken
    # verdict is fixed in one round rather than four.
    issues: list[str] = []
    requested_mode = document.get("requested_review_mode")
    requested_valid = requested_mode in {"independent_agent", "delta_verify", "cold_read"}
    if not requested_valid:
        issues.append(f"requested_review_mode={requested_mode!r}")
    provisional = verdict == "provisional"
    delta = requested_mode == "delta_verify"
    cold = requested_mode == "cold_read"
    if requested_valid and delta and provisional:
        issues.append("delta_verify cannot issue a provisional verdict")
    effective_review_mode = document.get("effective_review_mode")
    if requested_valid:
        allowed_effective_modes = (
            {"self_check", "unattested"}
            if provisional
            else (
                {"delta_verify"}
                if delta
                else ({"cold_read"} if cold else {"fresh_agent"})
            )
        )
        if effective_review_mode not in allowed_effective_modes:
            issues.append(
                f"effective_review_mode={effective_review_mode!r} "
                f"(expected one of {sorted(allowed_effective_modes)})"
            )
    elif not isinstance(effective_review_mode, str):
        issues.append("effective_review_mode is not a string")
    reviewer = document.get("reviewer")
    if not isinstance(reviewer, dict):
        issues.append("reviewer is not an object")
    else:
        if reviewer.get("owner") != reference["owner"]:
            issues.append("reviewer.owner does not match verdict owner")
        excluded = reviewer.get("excluded_owner_skills")
        if (
            not isinstance(excluded, list)
            or not excluded
            or set(excluded) != {artifact_owner}
        ):
            issues.append("reviewer.excluded_owner_skills must be exactly the artifact owner")
        kind = reviewer.get("kind")
        independent = reviewer.get("independent")
        if requested_valid and not provisional and not delta and not cold:
            if kind != "independent_agent":
                issues.append(f"reviewer.kind={kind!r} (expected independent_agent)")
            if independent is not True:
                issues.append("reviewer.independent is not true")
            provenance = reviewer.get("provenance")
            if not isinstance(provenance, dict):
                issues.append("reviewer.provenance is missing")
            else:
                if not isinstance(provenance.get("context_id"), str) or not provenance["context_id"]:
                    issues.append("reviewer.provenance.context_id is missing")
                if provenance.get("fresh_context") is not True:
                    issues.append("reviewer.provenance.fresh_context is not true")
                if provenance.get("authored_reviewed_artifacts") is not False:
                    issues.append("reviewer.provenance.authored_reviewed_artifacts is not false")
        elif requested_valid:
            if not isinstance(kind, str):
                issues.append("reviewer.kind is not a string")
            if independent is not False:
                issues.append("reviewer.independent must be false for this review mode")
            if reviewer.get("provenance") is not None:
                issues.append("reviewer.provenance must be null for this review mode")
    if document.get("required_reviewer_independence") is not True:
        issues.append("required_reviewer_independence is not true")
    structural_validation = document.get("structural_validation")
    allowed_validation = {"pass", "pass_with_warnings", "fail"}
    if provisional:
        allowed_validation.add("not_run")
    if structural_validation not in allowed_validation:
        issues.append(
            f"structural_validation={structural_validation!r} "
            f"(expected one of {sorted(allowed_validation)})"
        )
    if not isinstance(document.get("findings_ref"), dict):
        issues.append("findings_ref is missing")
    if not isinstance(document.get("review_bundle_ref"), dict):
        issues.append("review_bundle_ref is missing")
    reviewed = document.get("reviewed_artifacts")
    if not isinstance(reviewed, list) or not reviewed:
        issues.append("reviewed_artifacts must be a non-empty array")
    blockers = document.get("blocking_findings")
    if (
        not isinstance(blockers, list)
        or any(not isinstance(finding_id, str) or not finding_id for finding_id in blockers)
        or len(blockers) != len(set(blockers))
    ):
        issues.append("blocking_findings must be an array of unique strings")
    blocker_count = document.get("open_blocker_count")
    if type(blocker_count) is not int:
        issues.append("open_blocker_count must be an integer")
    if issues:
        raise ValueError(
            "verdict has invalid fields: " + "; ".join(sorted(set(issues)))
        )

    requested_mode = document.get("requested_review_mode")
    if requested_mode not in {"independent_agent", "delta_verify", "cold_read"}:
        raise ValueError("verdict requested review mode is invalid")
    delta = requested_mode == "delta_verify"
    cold = requested_mode == "cold_read"
    provisional = verdict == "provisional"
    if delta and provisional:
        raise ValueError("delta_verify cannot issue a provisional verdict")
    effective_review_mode = document.get("effective_review_mode")
    allowed_effective_modes = (
        {"self_check", "unattested"}
        if provisional
        else (
            {"delta_verify"}
            if delta
            else ({"cold_read"} if cold else {"fresh_agent"})
        )
    )
    if effective_review_mode not in allowed_effective_modes:
        raise ValueError("verdict effective review mode is incompatible with verdict")
    if _normalize_review_verdict(str(document.get("verdict", ""))) != verdict:
        raise ValueError("review verdict does not match its evidence artifact")
    if provisional:
        non_independent_kinds = frozenset({"self_check", "unattested"})
    elif delta:
        non_independent_kinds = frozenset({"delta_verifier"})
    else:
        non_independent_kinds = frozenset({"cold_reader"})
    reviewer = _normalize_reviewer_evidence(
        document.get("reviewer"),
        verdict_owner=reference["owner"],
        artifact_owner=artifact_owner,
        require_independent=not provisional and not delta and not cold,
        non_independent_kinds=non_independent_kinds,
    )
    if document.get("required_reviewer_independence") is not True:
        raise ValueError("verdict does not assert required reviewer independence")
    structural_validation = document.get("structural_validation")
    allowed_validation = {"pass", "pass_with_warnings", "fail"}
    if provisional:
        allowed_validation.add("not_run")
    if structural_validation not in allowed_validation:
        raise ValueError("verdict structural_validation is invalid")
    if (
        verdict in {"approve", "approve_with_notes"}
        and structural_validation not in {"pass", "pass_with_warnings"}
    ):
        raise ValueError("approval verdict requires structural validation pass")
    raw_findings_ref = document.get("findings_ref")
    if not isinstance(raw_findings_ref, dict):
        raise ValueError("verdict findings_ref is missing")
    findings_ref = _normalize_artifact_ref(
        root, raw_findings_ref, expected_owner=reference["owner"]
    )
    if findings_ref["artifact"] == reference["artifact"]:
        raise ValueError("verdict findings_ref must reference a separate artifact")
    reviewed = document.get("reviewed_artifacts")
    if not isinstance(reviewed, list) or not reviewed:
        raise ValueError("verdict reviewed_artifacts must be a non-empty array")
    evidence_targets: dict[str, str] = {}
    for raw_reference in reviewed:
        if not isinstance(raw_reference, dict):
            raise ValueError("verdict reviewed artifact ref is invalid")
        target_reference = _normalize_artifact_ref(
            root, raw_reference, expected_owner=artifact_owner
        )
        artifact = target_reference["artifact"]
        if artifact in evidence_targets:
            raise ValueError("verdict reviewed artifact refs are duplicated")
        evidence_targets[artifact] = target_reference["hash"]
    if dict(sorted(evidence_targets.items())) != dict(reviewed_targets):
        raise ValueError("verdict does not bind the exact reviewed target hashes")
    review_bundle_ref = _validate_review_bundle_evidence(
        root,
        document.get("review_bundle_ref"),
        reviewed_targets=evidence_targets,
    )
    blockers = document.get("blocking_findings")
    if (
        not isinstance(blockers, list)
        or any(not isinstance(finding_id, str) or not finding_id for finding_id in blockers)
        or len(blockers) != len(set(blockers))
    ):
        raise ValueError("verdict blocking_findings must be an array")
    findings = _load_findings(root, findings_ref)
    open_blockers = _open_blocking_ids(findings)
    if set(blockers) != open_blockers:
        raise ValueError("verdict blocking_findings do not match findings snapshot")
    blocker_count = document.get("open_blocker_count")
    if type(blocker_count) is not int or blocker_count != len(blockers):
        raise ValueError("verdict open_blocker_count does not match blocking findings")
    if verdict in {"approve", "approve_with_notes"} and blocker_count != 0:
        raise ValueError("approval verdict has an open blocking finding")
    if delta:
        _validate_delta_basis(
            root,
            document=document,
            artifact_owner=artifact_owner,
            verdict_owner=reference["owner"],
            current_targets=evidence_targets,
            findings=findings,
        )
    document = dict(document)
    document["review_bundle_ref"] = review_bundle_ref
    return reference, document, reviewer, findings_ref


def record_independent_review(
    path: Path,
    *,
    artifact_id: str,
    verdict: str,
    reviewed_targets: Mapping[str, str],
    verdict_ref: Mapping[str, Any],
) -> dict[str, Any]:
    """Record an independent verdict bound to accepted bytes and its JSON proof."""

    root = find_project(path)
    normalized_verdict = _normalize_review_verdict(verdict)
    targets = _normalize_hash_mapping(reviewed_targets, label="review target")
    with _transaction_lock(root):
        state = _read_state(root)
        artifacts = state.setdefault("artifacts", {})
        record = artifacts.get(artifact_id)
        if not isinstance(record, dict):
            raise ValueError(f"unknown accepted artifact: {artifact_id}")
        owner = record.get("owner")
        if not isinstance(owner, str):
            raise ValueError("accepted artifact owner is unavailable")
        accepted = record.get("accepted_targets")
        if not isinstance(accepted, dict) or accepted != targets:
            raise ValueError("review does not match exact accepted targets")
        creator_decision = record.get("creator_decision")
        if (
            not isinstance(creator_decision, dict)
            or creator_decision.get("decision") != "accepted"
            or creator_decision.get("target_hashes") != targets
        ):
            raise ValueError("review requires exact creator acceptance evidence")
        _validate_creator_decision_evidence(
            root,
            creator_decision.get("evidence_ref", {}),
            decision="accepted",
            artifact_id=artifact_id,
            target_hashes=targets,
        )
        _validate_input_closure(root, state, artifact_id)
        _verify_live_hashes(root, targets, label="review target")
        reference, _document, reviewer, findings_ref = _validate_review_verdict_evidence(
            root,
            artifact_owner=owner,
            verdict=normalized_verdict,
            reviewed_targets=targets,
            verdict_ref=verdict_ref,
        )
        gate = (
            "ready"
            if normalized_verdict in {"approve", "approve_with_notes"}
            and reviewer["independent"]
            else "blocked"
        )
        updated = apply_lifecycle_changes(
            record,
            {
                "validation_state": _document["structural_validation"],
                "independent_review": normalized_verdict,
                "delivery_gate": gate,
            },
        )
        updated["review_evidence"] = {
            "verdict": normalized_verdict,
            "structural_validation": _document["structural_validation"],
            "reviewed_targets": targets,
            "verdict_ref": reference,
            "findings_ref": findings_ref,
            "review_bundle_ref": _document["review_bundle_ref"],
            "reviewer_independence": {
                "artifact_owner": owner,
                "reviewer_owner": reference["owner"],
                "kind": reviewer["kind"],
                "independent": reviewer["independent"],
                "excluded_owner_skills": reviewer["excluded_owner_skills"],
                "provenance": reviewer["provenance"],
                "requested_review_mode": _document["requested_review_mode"],
                "effective_review_mode": _document["effective_review_mode"],
                "attestation_structure_valid": reviewer["independent"],
                "verification_scope": (
                    "delta_closure_structure"
                    if _document["effective_review_mode"] == "delta_verify"
                    else (
                        "cold_read_structure"
                        if _document["effective_review_mode"] == "cold_read"
                        else "declared_provenance_structure"
                    )
                ),
            },
        }
        artifacts[artifact_id] = updated
        state["updated_at"] = utc_now()
        state["last_action"] = "independent_review_recorded"
        atomic_json(root / STATE_FILE, state)
    return {
        "artifact_id": artifact_id,
        "independent_review": normalized_verdict,
        "target_count": len(targets),
        "status": "recorded",
    }


def _validate_delivery_text(
    content: bytes,
    suffix: str,
    relative: str,
    allowed_urls: set[str],
) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackageBlockedError(f"delivery file is not UTF-8 text: {relative}") from error
    structured_documents: list[Any] = []
    if suffix == ".json":
        try:
            structured_documents.append(_json_loads(text))
        except json.JSONDecodeError as error:
            raise PackageBlockedError(f"invalid delivery JSON: {relative}") from error
    elif suffix == ".jsonl":
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                structured_documents.append(_json_loads(line))
            except json.JSONDecodeError as error:
                raise PackageBlockedError(
                    f"invalid delivery JSONL at {relative}:{number}"
                ) from error

    credential_fields = {
        "apikey",
        "accesstoken",
        "authtoken",
        "bearertoken",
        "clientsecret",
        "password",
        "privatekey",
        "secretkey",
    }

    def reject_structured_credentials(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
                if normalized in credential_fields:
                    raise PackageBlockedError(
                        f"credential field is excluded from delivery: {relative}"
                    )
                reject_structured_credentials(child)
        elif isinstance(value, list):
            for child in value:
                reject_structured_credentials(child)

    for document in structured_documents:
        reject_structured_credentials(document)

    # file URLs and private keys have no legitimate on-screen use, so they stay
    # unconditional blocks. A machine path can be genuine story content (a
    # hacking or investigation episode showing a path on screen), so it keeps
    # the same declared-exception channel the URL rule uses: default blocked,
    # released only for an exact text the creator bound to a path and field.
    unsafe_patterns = {
        "file URL": re.compile(r"\bfile://", re.IGNORECASE),
        "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    }
    for label, pattern in unsafe_patterns.items():
        if pattern.search(text):
            raise PackageBlockedError(f"{label} is excluded from delivery: {relative}")
    # Match the whole path token, not just its prefix. Containment is checked
    # against the full token, so declaring a bare prefix cannot release every
    # path that happens to share it.
    exempt_spans = [
        (match.start(), match.end())
        for allowed in allowed_urls
        for match in re.finditer(re.escape(allowed), text)
    ]
    for match in MACHINE_PATH_TOKEN_RE.finditer(text):
        covered = any(
            start <= match.start() and match.end() <= end
            for start, end in exempt_spans
        )
        if not covered:
            raise PackageBlockedError(
                f"machine path is excluded from delivery: {relative}"
            )
    url_pattern = re.compile(r"https?://[^\s<>\"'\])}，。；]+", re.IGNORECASE)
    disallowed = sorted(set(url_pattern.findall(text)) - allowed_urls)
    if disallowed:
        raise PackageBlockedError(f"URL-like text needs an explicit exception: {relative}")


def _normalize_text_exceptions(
    text_exceptions: Iterable[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    normalized: list[dict[str, Any]] = []
    allowed: dict[str, set[str]] = {}
    provenance_allowlist = {"creator_supplied", "story_world_authored"}
    text_policy_allowlist = {"visible_on_screen", "fictional_interface_text"}
    url_pattern = re.compile(r"https?://[^\s<>\"'\])}，。；]+", re.IGNORECASE)
    # An exception releases either a complete URL or an exact on-screen string
    # whose machine paths are quoted in full. A declaration that is only a path
    # prefix (or that carries no complete path token) is rejected, so it cannot
    # act as a wildcard over every path sharing that prefix.
    for exception in text_exceptions or []:
        exact = exception.get("exact_text")
        bound_path = exception.get("path")
        field = exception.get("field")
        if (
            not isinstance(exact, str)
            or not exact
            # A complete URL is inherently a single token, so the length bound
            # only needs to constrain free-form on-screen strings.
            or (
                len(exact) > MAX_TEXT_EXCEPTION_LENGTH
                and url_pattern.fullmatch(exact) is None
            )
            # Any line break or control character, not just \n: a declaration
            # spanning lines is a document, not a single on-screen string.
            or any(character < " " or character in "\x7f\x85  " for character in exact)
            or (
                url_pattern.fullmatch(exact) is None
                and MACHINE_PATH_COMPLETE_RE.search(exact) is None
            )
            or not isinstance(bound_path, str)
            or not isinstance(field, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", field)
            or exception.get("purpose") != "on_screen_text"
            or exception.get("provenance") not in provenance_allowlist
            or exception.get("text_policy") not in text_policy_allowlist
            or exception.get("allow_delivery") is not True
        ):
            raise PackageBlockedError("invalid on-screen text delivery exception")
        relative = _relative_path(bound_path)
        record = {
            "exact_text": exact,
            "path": relative,
            "field": field,
            "purpose": "on_screen_text",
            "provenance": exception["provenance"],
            "text_policy": exception["text_policy"],
            "allow_delivery": True,
        }
        normalized.append(record)
        allowed.setdefault(relative, set()).add(exact)
    normalized.sort(key=lambda item: (item["path"], item["field"], item["exact_text"]))
    return normalized, allowed


def _validate_delivery_evidence(
    root: Path,
    state: Mapping[str, Any],
    artifact_id: str,
    record: Mapping[str, Any],
) -> None:
    accepted = record.get("accepted_targets")
    if not isinstance(accepted, dict) or not accepted:
        raise PackageBlockedError(
            f"creator decision evidence has no accepted targets: {artifact_id}"
        )
    creator_decision = record.get("creator_decision")
    if (
        not isinstance(creator_decision, dict)
        or creator_decision.get("decision") != "accepted"
        or creator_decision.get("target_hashes") != accepted
    ):
        raise PackageBlockedError(
            f"creator decision evidence is missing or stale: {artifact_id}"
        )
    try:
        _validate_creator_decision_evidence(
            root,
            creator_decision.get("evidence_ref", {}),
            decision="accepted",
            artifact_id=artifact_id,
            target_hashes=accepted,
        )
    except ValueError as error:
        raise PackageBlockedError(
            f"creator decision evidence is invalid: {artifact_id}"
        ) from error
    try:
        _validate_input_closure(root, state, artifact_id)
    except ValueError as error:
        raise PackageBlockedError(
            f"accepted input evidence is stale: {artifact_id}"
        ) from error

    review = record.get("review_evidence")
    verdict = record.get("independent_review")
    owner = record.get("owner")
    if (
        not isinstance(review, dict)
        or verdict not in {"approve", "approve_with_notes"}
        or review.get("verdict") != verdict
        or review.get("structural_validation") != record.get("validation_state")
        or review.get("reviewed_targets") != accepted
        or not isinstance(owner, str)
    ):
        raise PackageBlockedError(
            f"independent review evidence is missing or stale: {artifact_id}"
        )
    independence = review.get("reviewer_independence")
    if (
        not isinstance(independence, dict)
        or independence.get("attestation_structure_valid") is not True
        or independence.get("verification_scope")
        != "declared_provenance_structure"
        or independence.get("artifact_owner") != owner
        or independence.get("reviewer_owner") == owner
        or independence.get("independent") is not True
        or independence.get("excluded_owner_skills") != [owner]
    ):
        raise PackageBlockedError(
            f"reviewer independence evidence is invalid: {artifact_id}"
        )
    try:
        reference, _document, reviewer, findings_ref = _validate_review_verdict_evidence(
            root,
            artifact_owner=owner,
            verdict=verdict,
            reviewed_targets=accepted,
            verdict_ref=review.get("verdict_ref", {}),
        )
    except ValueError as error:
        raise PackageBlockedError(
            f"independent review verdict evidence is invalid: {artifact_id}"
        ) from error
    if independence.get("reviewer_owner") != reference["owner"]:
        raise PackageBlockedError(
            f"reviewer independence evidence is stale: {artifact_id}"
        )
    if (
        independence.get("kind") != reviewer["kind"]
        or independence.get("excluded_owner_skills")
        != reviewer["excluded_owner_skills"]
        or review.get("findings_ref") != findings_ref
        or review.get("review_bundle_ref") != _document["review_bundle_ref"]
        or review.get("structural_validation")
        != _document["structural_validation"]
    ):
        raise PackageBlockedError(
            f"reviewer or findings evidence is stale: {artifact_id}"
        )


def _approved_artifact_for_path(
    root: Path, state: dict[str, Any], relative: str, current_hash: str
) -> str:
    matches: list[str] = []
    for artifact_id, record in state.get("artifacts", {}).items():
        if not isinstance(record, dict):
            continue
        accepted = record.get("accepted_targets", {})
        if isinstance(accepted, dict) and accepted.get(relative) == current_hash:
            matches.append(artifact_id)
    if len(matches) != 1:
        raise PackageBlockedError(f"selected file has no unique accepted snapshot: {relative}")
    artifact_id = matches[0]
    record = state["artifacts"][artifact_id]
    required = {
        "build_state": {"materialized"},
        "validation_state": {"pass", "pass_with_warnings"},
        "creator_acceptance": {"accepted"},
        "independent_review": {"approve", "approve_with_notes"},
        "delivery_gate": {"ready", "delivered"},
    }
    failures = [axis for axis, values in required.items() if record.get(axis) not in values]
    if failures:
        raise PackageBlockedError(
            f"selected artifact is not delivery-ready ({', '.join(failures)}): {relative}"
        )
    _validate_delivery_evidence(root, state, artifact_id, record)
    return artifact_id


DELIVERY_READY = {
    "build_state": {"materialized"},
    "validation_state": {"pass", "pass_with_warnings"},
    "creator_acceptance": {"accepted"},
    "independent_review": {"approve", "approve_with_notes"},
    "delivery_gate": {"ready", "delivered"},
}


def _episode_coverage(
    state: Mapping[str, Any], episode: str
) -> dict[str, dict[str, Any]]:
    """Enumerate every accepted file this episode already has.

    Completeness cannot be judged from the selection alone: a hand-written
    include list looks equally complete whether or not it forgot the keyframe
    prompts. The project state already knows which files exist under the
    episode, so the enumeration belongs here rather than in someone's memory.
    """

    # Casefolded: on a case-insensitive filesystem an artifact accepted as
    # `Episodes/EP001/…` is the same file as `episodes/EP001/…`, and a
    # case-sensitive prefix would skip it — leaving nothing to reconcile and
    # passing the completeness gate on an episode it never enumerated.
    coverage: dict[str, dict[str, Any]] = {}
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        return coverage
    for artifact_id, record in artifacts.items():
        if not isinstance(artifact_id, str) or not isinstance(record, dict):
            continue
        if artifact_id.startswith("delivery:"):
            continue
        accepted = record.get("accepted_targets")
        if not isinstance(accepted, dict):
            continue
        ready = all(
            record.get(axis) in values for axis, values in DELIVERY_READY.items()
        )
        for relative in accepted:
            if not isinstance(relative, str):
                continue
            pure = PurePosixPath(relative)
            if (
                len(pure.parts) < 3
                or _root_role(pure.parts[0]) != "episodes"
                or pure.parts[1].casefold() != episode.casefold()
            ):
                continue
            coverage[relative] = {"artifact_id": artifact_id, "ready": ready}
    return dict(sorted(coverage.items()))


def _validate_omission_evidence(
    root: Path,
    *,
    episode: str,
    omissions: set[str],
    evidence_paths: Iterable[str | Path],
) -> dict[str, dict[str, Any]]:
    authorized: dict[str, dict[str, Any]] = {}
    for value in evidence_paths:
        relative = _relative_path(value)
        reference = {
            "owner": "creator",
            "artifact": relative,
            "hash": sha256_file(_project_path(root, relative)),
        }
        normalized, record = _load_evidence_record(
            root, reference, expected_owner="creator"
        )
        if record.get("decision_kind") != "delivery_omission":
            raise PackageBlockedError(
                f"omission evidence decision_kind is invalid: {relative}"
            )
        if record.get("status") != "accepted" or record.get("episode") != episode:
            raise PackageBlockedError(
                f"omission evidence status or episode is invalid: {relative}"
            )
        try:
            authority = _validate_decision_authority(
                root,
                record,
                artifact_id=f"delivery:{episode}",
                operation="delivery_omission",
            )
        except ValueError as error:
            raise PackageBlockedError(
                f"omission evidence authority is invalid: {relative}"
            ) from error
        paths = record.get("paths")
        reasons = record.get("reasons")
        if (
            not isinstance(paths, list)
            or not all(isinstance(path, str) for path in paths)
            or not isinstance(reasons, dict)
        ):
            raise PackageBlockedError(f"omission evidence shape is invalid: {relative}")
        for raw_path in paths:
            path = _relative_path(raw_path)
            reason = reasons.get(raw_path)
            if not isinstance(reason, str) or not reason.strip():
                raise PackageBlockedError(
                    f"omission evidence needs a creator reason for {path}"
                )
            if path in authorized:
                raise PackageBlockedError(f"omission has duplicate evidence: {path}")
            authorized[path] = {
                "reason": reason.strip(),
                "decision_ref": normalized,
                "decision_id": record.get("decision_id"),
                "authority": authority,
            }
    missing = sorted(omissions - set(authorized))
    extra = sorted(set(authorized) - omissions)
    if missing:
        raise PackageBlockedError(
            "omitted paths require accepted creator evidence: " + ", ".join(missing)
        )
    if extra:
        raise PackageBlockedError(
            "omission evidence names paths not passed to --omit: " + ", ".join(extra)
        )
    return authorized


def _accounted_delivery_artifacts(
    selected_artifacts: Iterable[str], omitted: Iterable[Mapping[str, Any]]
) -> set[str]:
    """Artifacts are delivered when every target is selected or explicitly omitted."""

    return {str(artifact_id) for artifact_id in selected_artifacts} | {
        str(entry["artifact_id"])
        for entry in omitted
        if isinstance(entry.get("artifact_id"), str)
    }


def build_delivery_package(
    path: Path,
    *,
    episode: str,
    selected_paths: Iterable[str | Path],
    text_exceptions: Iterable[Mapping[str, Any]] | None = None,
    omitted_paths: Iterable[str | Path] | None = None,
    omission_evidence: Iterable[str | Path] = (),
) -> dict[str, Any]:
    root = find_project(path)
    if EPISODE_ID_RE.fullmatch(episode) is None:
        raise ValueError("episode must use an EP001-style identifier")
    exceptions, allowed_urls_by_path = _normalize_text_exceptions(text_exceptions)
    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    flow = _effective_production_flow(root)
    if flow.get("pipeline_version") != PIPELINE_VERSION:
        raise PackageBlockedError(
            f"project pipeline must be upgraded to {PIPELINE_VERSION} before packaging"
        )
    raw_state = _read_state(root)
    effective_state = dict(raw_state)
    raw_artifacts = raw_state.get("artifacts")
    effective_state["artifacts"] = _effective_lifecycle_records(
        root, raw_artifacts if isinstance(raw_artifacts, dict) else {}
    )
    baseline = _generation_baseline_status(root, effective_state)
    if not baseline.get("m15a_ready") or not baseline.get("m15b_ready"):
        raise PackageBlockedError("accepted M1.5 asset baseline is missing, ambiguous, or stale")
    authority = project.get("creator_authority")
    delivery_surface = (
        authority.get("delivery_surface") if isinstance(authority, dict) else None
    )
    if not isinstance(delivery_surface, dict) or delivery_surface.get("status") != "accepted":
        raise PackageBlockedError(
            "delivery_surface must be declared and accepted before packaging"
        )
    state = effective_state
    episode_flow = _episode_flow_report(root, state, episode)
    incomplete = [
        milestone
        for milestone, ready in (
            ("M2", episode_flow["m2_done"]),
            ("M3", episode_flow["m3_done"]),
            ("M4a", episode_flow["m4a_done"]),
            ("M4b", episode_flow["m4b_done"]),
            ("M5", episode_flow["m5_done"]),
            ("M6", episode_flow["m6_done"]),
        )
        if not ready
    ]
    if incomplete:
        raise PackageBlockedError(
            "fixed pipeline is incomplete before packaging: " + ", ".join(incomplete)
        )
    files: list[dict[str, Any]] = []
    outputs: dict[str, bytes] = {}
    source_artifacts: set[str] = set()
    normalized_selected = sorted(
        _normalize_path_values(selected_paths, label="delivery selection")
    )
    selected_episode_roots = {
        PurePosixPath(relative).parts[0]
        for relative in normalized_selected
        if _root_role(PurePosixPath(relative).parts[0]) == "episodes"
    }
    if len(selected_episode_roots) > 1:
        raise PackageBlockedError("不能在同一交付包中混用中文与旧版分集目录")
    source_episode_root = next(iter(selected_episode_roots), None)
    delivery_root = _layout_root_for_source(
        root,
        "delivery",
        CANONICAL_ROOTS["delivery"]
        if source_episode_root == CANONICAL_ROOTS["episodes"]
        else LEGACY_ROOTS["delivery"]
        if source_episode_root is not None
        else None,
    )
    for raw in normalized_selected:
        pure = PurePosixPath(raw)
        if pure.parts[0].casefold() in PROTECTED_PUBLISH_ROOTS:
            raise PackageBlockedError(f"private or operational zone excluded: {raw}")
        # A selection naming episodes/ep1/ would be prefix-skipped by
        # _episode_coverage, so the completeness reconciliation below would see
        # nothing to reconcile and pass on an episode it never enumerated.
        if _root_role(pure.parts[0]) == "episodes" and (
            len(pure.parts) < 3 or EPISODE_ID_RE.fullmatch(pure.parts[1]) is None
        ):
            raise PackageBlockedError(
                f"分集选择必须使用 剧集/<EP>/（兼容 episodes/<EP>/）：{raw}"
            )
        lowered_parts = {part.casefold() for part in pure.parts}
        if "research" in lowered_parts or "research-notes.md" in lowered_parts:
            raise PackageBlockedError(f"optional research notes are excluded: {raw}")
        source = _project_path(root, raw)
        if source.is_symlink() or not source.is_file():
            raise PackageBlockedError(f"selected delivery file is unavailable: {raw}")
        suffix = source.suffix.lower()
        if suffix not in DELIVERY_SUFFIXES:
            raise PackageBlockedError(f"only Markdown, JSON, and JSONL may be delivered: {raw}")
        content = source.read_bytes()
        digest = sha256_bytes(content)
        artifact_id = _approved_artifact_for_path(root, state, raw, digest)
        _validate_delivery_text(content, suffix, raw, allowed_urls_by_path.get(raw, set()))
        destination = f"{delivery_root}/{episode}/artifacts/{raw}"
        outputs[destination] = content
        source_artifacts.add(artifact_id)
        files.append(
            {
                "artifact_id": artifact_id,
                "source": raw,
                "delivery_path": str(
                    PurePosixPath(destination).relative_to(
                        PurePosixPath(delivery_root) / episode
                    )
                ),
                "sha256": digest,
            }
        )
    if not files:
        raise PackageBlockedError("delivery selection is empty")
    selected = {entry["source"] for entry in files}
    unused_exception_paths = sorted(set(allowed_urls_by_path) - selected)
    if unused_exception_paths:
        raise PackageBlockedError(
            "text exception path is not selected for delivery: "
            + ", ".join(unused_exception_paths)
        )

    coverage = _episode_coverage(state, episode)
    declared_omissions = set(
        _normalize_path_values(omitted_paths or (), label="delivery omission")
    )
    unknown_omissions = sorted(declared_omissions - set(coverage))
    if unknown_omissions:
        raise PackageBlockedError(
            "omitted path is not an accepted artifact of this episode: "
            + ", ".join(unknown_omissions)
        )
    contradictory = sorted(declared_omissions & selected)
    if contradictory:
        raise PackageBlockedError(
            "path cannot be both selected and omitted: " + ", ".join(contradictory)
        )
    omission_authorizations = _validate_omission_evidence(
        root,
        episode=episode,
        omissions=declared_omissions,
        evidence_paths=omission_evidence,
    )
    unaccounted = sorted(set(coverage) - selected - declared_omissions)
    if unaccounted:
        ready = [relative for relative in unaccounted if coverage[relative]["ready"]]
        pending = [relative for relative in unaccounted if not coverage[relative]["ready"]]
        detail = []
        if ready:
            detail.append("delivery-ready and unselected: " + ", ".join(ready))
        if pending:
            detail.append("not yet delivery-ready: " + ", ".join(pending))
        raise PackageBlockedError(
            "episode artifacts are neither selected nor declared omitted ("
            + "; ".join(detail)
            + "); add each to --include or --omit"
        )
    omitted = [
        {
            "source": relative,
            "artifact_id": coverage[relative]["artifact_id"],
            **omission_authorizations[relative],
        }
        for relative in sorted(declared_omissions)
    ]

    generation_prefix = "设定集/generation/"
    artifacts = state.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise PackageBlockedError("artifact registry is unavailable")
    baseline_files: dict[str, dict[str, Any]] = {}
    baseline_records: dict[str, dict[str, Any]] = {}
    baseline_read_set: dict[str, str] = {}
    visited: set[str] = set()

    def provider_for(relative: str, digest: str, *, record_bound: bool) -> str | None:
        providers = []
        for provider_id, provider in artifacts.items():
            if not isinstance(provider_id, str) or not isinstance(provider, dict):
                continue
            targets = provider.get("accepted_targets")
            if not isinstance(targets, dict):
                continue
            if relative in targets if record_bound else targets.get(relative) == digest:
                providers.append(provider_id)
        if len(providers) > 1:
            raise PackageBlockedError(f"accepted input provider is ambiguous: {relative}")
        return providers[0] if providers else None

    def selected_record(relative: str, selector: str, content: bytes) -> Any:
        suffix = PurePosixPath(relative).suffix.lower()
        if suffix == ".jsonl":
            matches = [
                item
                for item in _jsonl_records(content, relative)
                if any(
                    key.endswith("_id") and value == selector
                    for key, value in item.items()
                    if isinstance(value, str)
                )
            ]
            if len(matches) != 1:
                raise PackageBlockedError(
                    f"asset baseline selector does not resolve exactly once: {relative} {selector}"
                )
            return matches[0]
        if suffix == ".json":
            return _resolve_json_pointer(_json_loads(content.decode("utf-8")), selector, relative)
        raise PackageBlockedError(f"asset baseline record binding needs JSON/JSONL: {relative}")

    def collect_artifact(artifact_id: str) -> None:
        if artifact_id in visited:
            return
        visited.add(artifact_id)
        record = artifacts.get(artifact_id)
        if not isinstance(record, dict):
            return
        inputs = _input_bindings(record, "accepted_inputs")
        record_inputs = _input_record_bindings(record, "accepted_input_records")
        for relative, digest in inputs.items():
            selectors = record_inputs.get(relative, {})
            if relative.startswith(generation_prefix):
                path = _project_path(root, relative)
                if not path.is_file():
                    raise PackageBlockedError(f"asset baseline input is unavailable: {relative}")
                content = path.read_bytes()
                live_hash = sha256_bytes(content)
                baseline_read_set[relative] = live_hash
                file_entry = baseline_files.setdefault(
                    relative,
                    {
                        "accepted_input_sha256": digest,
                        "live_sha256": live_hash,
                        "file_sha256": live_hash,
                        "binding_mode": "records" if selectors else "whole_file",
                    },
                )
                if file_entry["live_sha256"] != live_hash:
                    raise PackageBlockedError(f"asset baseline changed while packaging: {relative}")
                if selectors:
                    live_digests = _record_digests(content, relative, selectors)
                    for selector, expected in selectors.items():
                        if live_digests.get(selector) != expected:
                            raise PackageBlockedError(
                                f"asset baseline record hash does not match live file: {relative} {selector}"
                            )
                        baseline_records.setdefault(relative, {})[selector] = {
                            "sha256": expected,
                            "record": selected_record(relative, selector, content),
                        }
                else:
                    if live_hash != digest:
                        raise PackageBlockedError(f"asset baseline file hash does not match live file: {relative}")
                    text = content.decode("utf-8")
                    file_entry["content"] = (
                        _json_loads(text)
                        if PurePosixPath(relative).suffix.lower() == ".json"
                        else [_json_loads(line) for line in text.splitlines() if line.strip()]
                        if PurePosixPath(relative).suffix.lower() == ".jsonl"
                        else text
                    )
            provider_id = provider_for(relative, digest, record_bound=bool(selectors))
            if provider_id is not None:
                collect_artifact(provider_id)

    for artifact_id in sorted(source_artifacts):
        collect_artifact(artifact_id)
    asset_consumption = _episode_asset_consumption_summary(root, state, episode)
    baseline_bundle = {
        "schema_version": CONTRACT_VERSION,
        "episode": episode,
        "source_artifacts": sorted(source_artifacts),
        "files": baseline_files,
        "records": baseline_records,
        "asset_consumption": asset_consumption,
    }
    baseline_bytes = (
        _json_dumps(baseline_bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    baseline_target = f"{delivery_root}/{episode}/asset-baseline-bundle.json"
    outputs[baseline_target] = baseline_bytes

    manifest = {
        "schema_version": 1,
        "episode": episode,
        "files": files,
        "omitted": omitted,
        "text_exceptions": exceptions,
        "asset_baseline_bundle": "asset-baseline-bundle.json",
        "exclusions": ["private_inputs", "operational_state", "binaries", "unselected_files"],
    }
    manifest_bytes = (
        _json_dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_target = f"{delivery_root}/{episode}/manifest.json"
    outputs[manifest_target] = manifest_bytes
    checksum_entries = [
        (entry["sha256"], entry["delivery_path"]) for entry in files
    ] + [
        (sha256_bytes(baseline_bytes), "asset-baseline-bundle.json"),
        (sha256_bytes(manifest_bytes), "manifest.json"),
    ]
    checksums = "".join(
        f"{digest}  {relative}\n" for digest, relative in sorted(checksum_entries, key=lambda item: item[1])
    ).encode("utf-8")
    checksum_target = f"{delivery_root}/{episode}/checksums.sha256"
    outputs[checksum_target] = checksums

    delivery_artifact = f"delivery:{episode}"
    accounted_artifacts = _accounted_delivery_artifacts(source_artifacts, omitted)
    lifecycle_changes = {
        artifact_id: {"delivery_gate": "delivered"}
        for artifact_id in sorted(accounted_artifacts)
    }
    lifecycle_changes[delivery_artifact] = {
        "build_state": "materialized",
        "validation_state": "pass",
        "creator_acceptance": "accepted",
        "delivery_gate": "delivered",
    }
    transaction = publish_transaction(
        root,
        stage="delivery",
        outputs=outputs,
        lifecycle_changes=lifecycle_changes,
        target_artifacts={target: delivery_artifact for target in outputs},
        read_set={
            **{entry["source"]: entry["sha256"] for entry in files},
            **baseline_read_set,
        },
        _delivery_gate=True,
    )
    return {
        "project_root": str(root),
        "episode": episode,
        "file_count": len(files),
        "transaction_id": transaction["transaction_id"],
        "status": "delivered",
    }


def verify_delivery_package(path: Path, *, episode: str) -> dict[str, Any]:
    """Re-read a delivered package and check it against its own checksums.

    `package` writes `checksums.sha256` and nothing ever read it back, so a
    delivered tree could be edited afterwards and still look delivered. This is
    the missing half: it re-hashes every listed file, and reports extra files
    too, because an unlisted addition is invisible to a checksum list.
    """

    root = find_project(path)
    if EPISODE_ID_RE.fullmatch(episode) is None:
        raise ValueError("episode must use an EP001-style identifier")
    # Portable path-based implementation: the original dir_fd version is
    # POSIX-only (os.O_DIRECTORY / dir_fd), so it crashed on Windows. Semantics
    # are preserved: symlinked package roots and symlinked files are never
    # trusted, checksums are authenticated against the recorded state hash
    # before any entry is traversed, and unlisted additions are reported.
    state_path = root / STATE_FILE
    state = (
        _json_loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file()
        else {}
    )
    layout = project_layout(root)

    def package_exists(name: str) -> bool:
        candidate = _project_path(root, f"{name}/{episode}")
        return candidate.is_dir() and not candidate.is_symlink()

    if layout["mode"] == "mixed":
        available = [
            name
            for name in (CANONICAL_ROOTS["delivery"], LEGACY_ROOTS["delivery"])
            if package_exists(name)
        ]
        if len(available) > 1:
            raise PackageBlockedError(f"{episode} 同时存在中文与旧版英文交付包")
        delivery_root = available[0] if available else CANONICAL_ROOTS["delivery"]
    else:
        # No cross-root fallback here: a package under the other family gives
        # that root content, which puts its family in detected_modes and makes
        # the layout `mixed`, so control would have taken the branch above.
        delivery_root = str(layout["roots"]["delivery"])

    delivery_dir = _project_path(root, f"{delivery_root}/{episode}")
    if delivery_dir.is_symlink() or not delivery_dir.is_dir():
        raise PackageBlockedError(f"no safe delivered package for {episode}")
    checksums_path = delivery_dir / "checksums.sha256"
    if checksums_path.is_symlink() or not checksums_path.is_file():
        raise PackageBlockedError(f"no delivered package for {episode}")
    checksums_content = checksums_path.read_bytes()

    # Authenticate the list before trusting any path inside it. A modified
    # unauthenticated list is reported as tampered without traversing its
    # entries, preventing it from becoming a hash oracle for outside files.
    checksums_relative = f"{delivery_root}/{episode}/checksums.sha256"
    artifacts = state.get("artifacts")
    recorded: str | None = None
    if isinstance(artifacts, dict):
        record = artifacts.get(f"delivery:{episode}")
        accepted = (
            record.get("accepted_targets") if isinstance(record, dict) else None
        )
        if isinstance(accepted, dict) and isinstance(
            accepted.get(checksums_relative), str
        ):
            recorded = accepted[checksums_relative]
    checksum_list_authentic = (
        recorded is not None and recorded == sha256_bytes(checksums_content)
    )
    if not checksum_list_authentic:
        return {
            "project_root": str(root),
            "episode": episode,
            "file_count": 0,
            "mismatched": [],
            "missing": [],
            "unlisted": [],
            "checksum_list_authentic": False,
            "status": "tampered",
        }

    expected: dict[str, str] = {}
    for number, line in enumerate(
        checksums_content.decode("utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        digest, separator, relative = line.partition("  ")
        if not separator or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise PackageBlockedError(f"checksum line {number} is malformed")
        try:
            normalized = _relative_path(relative)
        except ValueError as error:
            raise PackageBlockedError(
                f"checksum line {number} has an unsafe path"
            ) from error
        if normalized != relative or normalized == "checksums.sha256":
            raise PackageBlockedError(f"checksum line {number} has an unsafe path")
        if normalized in expected:
            raise PackageBlockedError(f"checksum line {number} repeats {normalized}")
        expected[normalized] = digest

    mismatched: list[str] = []
    missing: list[str] = []
    for relative, digest in sorted(expected.items()):
        target = delivery_dir / relative
        if target.is_symlink() or not target.is_file():
            missing.append(relative)
            continue
        try:
            actual = sha256_bytes(target.read_bytes())
        except OSError:
            missing.append(relative)
            continue
        if actual != digest:
            mismatched.append(relative)

    present: set[str] = set()

    def collect(directory: Path, parts: tuple[str, ...]) -> None:
        with os.scandir(directory) as iterator:
            entries = list(iterator)
        for entry in entries:
            relative = PurePosixPath(*parts, entry.name).as_posix()
            if entry.is_symlink():
                present.add(relative)
                continue
            if entry.is_dir(follow_symlinks=False):
                collect(directory / entry.name, (*parts, entry.name))
            else:
                present.add(relative)

    collect(delivery_dir, ())
    unlisted = sorted(present - set(expected) - {"checksums.sha256"})

    intact = not (mismatched or missing or unlisted)
    return {
        "project_root": str(root),
        "episode": episode,
        "file_count": len(expected),
        "mismatched": mismatched,
        "missing": missing,
        "unlisted": unlisted,
        "checksum_list_authentic": True,
        "status": "intact" if intact else "tampered",
    }


def _parse_cli_pairs(values: Iterable[str], *, label: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    paths: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item:
            raise ValueError(f"{label} must use PATH=VALUE")
        relative = _relative_path(key)
        _remember_portable_path(paths, relative, label=label)
        parsed[relative] = item
    return parsed


def _resolve_snapshot_targets(
    root: Path,
    artifact_id: str,
    raw_targets: Iterable[str],
    *,
    snapshot_key: str,
) -> dict[str, str]:
    """Fill omitted target hashes from the artifact's lifecycle snapshot.

    The tool re-verifies every hash against live bytes downstream, so a bare
    `--target PATH` — or no `--target` at all — binds exactly the recorded
    candidate/accepted snapshot. An explicit `PATH=SHA256` remains available
    as the strict form and is still checked for equality.
    """

    state = _read_state(root)
    record = state.get("artifacts", {}).get(artifact_id)
    snapshot = record.get(snapshot_key) if isinstance(record, dict) else None
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError(f"artifact has no {snapshot_key} snapshot: {artifact_id}")
    parsed: dict[str, str | None] = {}
    paths: dict[str, str] = {}
    for value in raw_targets:
        key, separator, item = value.partition("=")
        if not key:
            raise ValueError("target must use PATH or PATH=SHA256")
        if separator and not re.fullmatch(r"[0-9a-f]{64}", item):
            raise ValueError(f"target hash is invalid: {value}")
        relative = _relative_path(key)
        _remember_portable_path(paths, relative, label="target")
        parsed[relative] = item if separator else None
    if not parsed:
        return dict(sorted((str(key), str(value)) for key, value in snapshot.items()))
    resolved: dict[str, str] = {}
    for relative, digest in parsed.items():
        if relative not in snapshot:
            raise ValueError(f"target is not part of the artifact snapshot: {relative}")
        resolved[relative] = digest if digest is not None else str(snapshot[relative])
    if set(resolved) != set(snapshot):
        missing = sorted(set(snapshot) - set(resolved))
        raise ValueError(f"target set is incomplete; missing: {', '.join(missing)}")
    return dict(sorted(resolved.items()))


def _disk_evidence_hash(root: Path, relative: str, *, label: str) -> str:
    digest = _live_hash(_project_path(root, _relative_path(relative)))
    if digest is None:
        raise ValueError(f"{label} file is unavailable: {relative}")
    return digest


def _screenplay_index_warnings(
    root: Path, owner: str, outputs: Mapping[str, bytes]
) -> list[str]:
    """Warn (never block) when a published screenplay's index is stale.

    Downstream stages bind screenplays through `screenplay-index.jsonl`
    record IDs, not the whole file, so an index rebuilt for an older revision
    silently keeps referencing the previous block hashes. The index carries
    its source SHA-256 in the first meta record; compare it against the
    published bytes and list every mismatch as a non-blocking warning.
    A missing or unparseable index is not a warning — first publish has no
    index yet, and a malformed index is not this publish's job to diagnose.
    """
    if owner != "short-drama-write":
        return []
    warnings: list[str] = []
    for target, content in outputs.items():
        relative = _relative_path(target)
        if PurePosixPath(relative).name != "screenplay.md":
            continue
        index_relative = f"{PurePosixPath(relative).parent}/screenplay-index.jsonl"
        index_path = _project_path(root, index_relative)
        if not index_path.is_file():
            continue
        try:
            records = _jsonl_records(index_path.read_bytes(), index_relative)
        except ValueError:
            continue
        source_ref = (
            records[0].get("source_ref")
            if records and isinstance(records[0], dict)
            else None
        )
        expected = source_ref.get("hash") if isinstance(source_ref, dict) else None
        if expected != sha256_bytes(content):
            warnings.append(
                f"screenplay index is stale for {relative}: "
                f"screenplay-index.jsonl tracks source hash "
                f"{expected if expected is not None else '<missing>'}; "
                "rebuild it with screenplay_index.py --previous-index "
                "--previous-source before accepting this revision"
            )
    return warnings


def _target_seconds_per_episode(root: Path) -> int | None:
    """Return format/target_seconds_per_episode when the project declares it."""

    try:
        project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    target = project.get("format", {}).get("target_seconds_per_episode")
    return target if isinstance(target, int) and target > 0 else None


def _estimate_screenplay_seconds(content: bytes) -> int:
    """Rough on-screen time estimate from a screenplay's own text.

    Deliberately coarse and never a verdict: dialogue at ~0.25 s per character
    (about four spoken Chinese characters per second), action lines at ~2.5 s
    each, scene headers and production tags at ~1 s. Exact timing is a
    storyboard (SHT-16) responsibility; this only surfaces a density gap early
    enough to act on it in the writing stage.
    """

    text = content.decode("utf-8", errors="replace")
    dialogue_chars = 0
    action_lines = 0
    headers = 0
    tags = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            headers += 1
            continue
        upper = stripped.upper()
        if upper.startswith(("[VO]", "[OS]", "[SFX]", "[画面文字]", "[转场]", "[连续性]")):
            tags += 1
            continue
        colon = stripped.find("：")
        if colon == -1:
            colon = stripped.find(":")
        if 0 < colon < len(stripped) - 1:
            prefix = stripped[:colon].strip()
            if len(prefix) <= 12 and not prefix.endswith(
                ("。", "，", "！", "？", "；", ".")
            ):
                dialogue_chars += len(re.sub(r"\s+", "", stripped[colon + 1 :]))
                continue
        action_lines += 1
    return int(
        round(
            dialogue_chars * 0.25
            + action_lines * 2.5
            + headers * 1.0
            + tags * 1.0
        )
    )


def _screenplay_duration_warnings(
    root: Path, owner: str, outputs: Mapping[str, bytes]
) -> list[str]:
    """Warn (never block) when a published screenplay looks too short.

    target_seconds_per_episode is a creator decision accepted at M0, but it
    has no enforcement point before storyboard SHT-16; an under-dense script
    only surfaces there as a delta. Estimating on-screen time from the
    screenplay text right at publish makes the gap visible in the writing
    stage. The estimate is intentionally rough and only a clear shortfall
    (below the target) warns.
    """

    if owner != "short-drama-write":
        return []
    target = _target_seconds_per_episode(root)
    if target is None:
        return []
    warnings: list[str] = []
    for target_path, content in outputs.items():
        relative = _relative_path(target_path)
        if PurePosixPath(relative).name != "screenplay.md":
            continue
        estimated = _estimate_screenplay_seconds(content)
        if estimated >= target:
            continue
        warnings.append(
            f"estimated on-screen time for {relative} is ~{estimated}s, below "
            f"target_seconds_per_episode {target}s: density is only verified at "
            "storyboard SHT-16 — add dialogue/action or confirm the shortfall "
            "before accepting"
        )
    return warnings


def _publish_from_cli(args: argparse.Namespace) -> dict[str, Any]:
    root = find_project(args.path)
    bindings = _parse_cli_pairs(args.outputs, label="output")
    outputs: dict[str, bytes] = {}
    inputs = _parse_cli_pairs(args.inputs or [], label="input")
    for raw_target, raw_source in bindings.items():
        target = _relative_path(raw_target)
        source = _relative_path(raw_source)
        content = _read_project_regular(root, source)
        source_hash = sha256_bytes(content)
        if target != source:
            previous = inputs.get(source)
            if previous is not None and previous != source_hash:
                raise ValueError(f"input hash does not match candidate source: {source}")
            inputs[source] = source_hash
        outputs[target] = content
    records: dict[str, list[str]] = {}
    record_paths: dict[str, str] = {}
    for value in args.input_records or []:
        key, separator, selector = value.partition("=")
        if not separator or not key or not selector:
            raise ValueError("input record must use PATH=SELECTOR")
        relative = _relative_path(key)
        portable = _portable_path_key(relative)
        previous = record_paths.get(portable)
        if previous is not None and previous != relative:
            raise ValueError(
                "input record paths collide on a portable filesystem: "
                f"{previous} and {relative}"
            )
        record_paths[portable] = relative
        records.setdefault(relative, []).append(selector)
    result = publish_candidate(
        root,
        owner=args.owner,
        artifact_id=args.artifact_id,
        allow_unregistered_path=bool(getattr(args, "allow_unregistered_path", False)),
        outputs=outputs,
        input_hashes=inputs,
        input_records=records or None,
        auto_bind_structured_refs=bool(
            getattr(args, "input_record_auto", True)
        ),
    )
    warnings = _screenplay_index_warnings(root, args.owner, outputs)
    warnings.extend(_screenplay_duration_warnings(root, args.owner, outputs))
    if warnings:
        result = {**result, "warnings": warnings}
    return result


REVIEW_BUNDLE_SCHEMA = "short-drama-review-bundle"
REVIEW_BUNDLE_VERSION = 1
REVIEW_SCOPES = frozenset(
    {
        "source_analysis",
        "story_script",
        "assets_continuity",
        "image_prompts",
        "storyboard_keyframes",
        "video_prompts",
        "full_episode",
        "delivery_privacy",
        "project_calibration",
    }
)


def _mechanical_report_kinds(document: Mapping[str, Any]) -> set[str]:
    kinds: set[str] = set()
    if document.get("review_status") == "clean" and isinstance(
        document.get("source_sha256"), str
    ):
        kinds.add("screenplay_index")
    if document.get("status") == "pass":
        if "lines" in document and "dialogue_blocks" in document:
            kinds.add("voice_sheet")
        if "episode_id" in document and isinstance(document.get("checked"), dict):
            kinds.add("storyboard")
        if "motion_specs" in document and "explicit_checked" in document:
            kinds.add("motion_timing")
        if "generation_clips" in document and "max_clip_seconds" in document:
            kinds.add("generation_clips")
        if "containers" in document and "packed_shots" in document:
            kinds.add("containers")
    return kinds


def _required_mechanical_report_kinds(targets: Iterable[str]) -> set[str]:
    paths = set(targets)
    names = {PurePosixPath(path).name for path in paths}
    required: set[str] = set()
    if {"screenplay.md", "screenplay-index.jsonl"} <= names:
        required.add("screenplay_index")
    if "voice-record-sheet.jsonl" in names:
        required.add("voice_sheet")
    if {"coverage.json", "shots.jsonl", "keyframes.jsonl"} & names:
        required.add("storyboard")
    if "motion-specs.jsonl" in names:
        required.add("motion_timing")
        required.add("generation_clips")
    if "generation-clips.jsonl" in names:
        required.add("generation_clips")
    if "delivery-containers.jsonl" in names:
        required.add("containers")
    return required


def _load_check_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load mechanical checker: {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _live_mechanical_reports(root: Path, targets: Iterable[str]) -> list[dict[str, Any]]:
    """Run applicable repository checkers against the live target family."""

    target_paths = set(targets)
    episode_dirs = {
        PurePosixPath(path).parent
        if PurePosixPath(path).name in {"episode-card.json", "beats.jsonl", "screenplay.md", "screenplay-index.jsonl", "voice-record-sheet.jsonl"}
        else PurePosixPath(path).parent.parent
        for path in target_paths
        if len(PurePosixPath(path).parts) >= 3
        and _root_role(PurePosixPath(path).parts[0]) == "episodes"
    }
    scripts = Path(__file__).resolve().parents[2]
    reports: list[dict[str, Any]] = []
    for episode_dir in sorted(episode_dirs, key=str):
        prefix = episode_dir.as_posix()
        family_targets = {
            path for path in target_paths if path == prefix or path.startswith(prefix + "/")
        }
        required = _required_mechanical_report_kinds(family_targets)
        if "screenplay_index" in required:
            screenplay = _project_path(root, f"{prefix}/screenplay.md")
            index = _project_path(root, f"{prefix}/screenplay-index.jsonl")
            if not screenplay.is_file() or not index.is_file():
                raise ValueError("screenplay mechanical validation requires screenplay and index")
            records = _jsonl_records(index.read_bytes(), index.name)
            meta = next(
                (record for record in records if record.get("record_type") == "screenplay_index_meta"),
                None,
            )
            source_ref = meta.get("source_ref") if isinstance(meta, dict) else None
            clean = (
                isinstance(meta, dict)
                and meta.get("review_status") == "clean"
                and isinstance(source_ref, dict)
                and source_ref.get("hash") == sha256_file(screenplay)
            )
            reports.append(
                {
                    "source": "builtin:screenplay_index",
                    "content": {
                        "source_sha256": sha256_file(screenplay),
                        "review_status": "clean" if clean else "review_required",
                    },
                }
            )
        if "voice_sheet" in required:
            module = _load_check_module(
                "short_drama_voice_sheet_check",
                scripts / "short-drama-write/scripts/voice_sheet_check.py",
            )
            sheet = _project_path(root, f"{prefix}/voice-record-sheet.jsonl")
            index = _project_path(root, f"{prefix}/screenplay-index.jsonl")
            screenplay = _project_path(root, f"{prefix}/screenplay.md")
            result = module.check(
                module._load_jsonl(sheet), module._load_jsonl(index), screenplay.read_bytes()
            )
            reports.append({"source": "builtin:voice_sheet", "content": result})
        if "storyboard" in required:
            module = _load_check_module(
                "short_drama_storyboard_check",
                scripts / "short-drama-storyboard/scripts/storyboard_check.py",
            )
            result = module.check(
                _project_path(root, f"{prefix}/storyboard/coverage.json"),
                _project_path(root, f"{prefix}/storyboard/shots.jsonl"),
                _project_path(root, f"{prefix}/storyboard/keyframes.jsonl"),
                root / PROJECT_FILE,
            )
            reports.append({"source": "builtin:storyboard", "content": result})
        if "motion_timing" in required:
            module = _load_check_module(
                "short_drama_motion_timing_check",
                scripts / "short-drama-video-prompts/scripts/motion_timing_check.py",
            )
            result = module.check(
                module._load_jsonl(_project_path(root, f"{prefix}/storyboard/motion-specs.jsonl")),
                module._load_jsonl(_project_path(root, f"{prefix}/storyboard/shots.jsonl")),
            )
            reports.append({"source": "builtin:motion_timing", "content": result})
        if "generation_clips" in required:
            module = _load_check_module(
                "short_drama_generation_clip_check",
                scripts / "short-drama-video-prompts/scripts/generation_clip_check.py",
            )
            result = module.check(
                module._load_jsonl(
                    _project_path(root, f"{prefix}/storyboard/generation-clips.jsonl")
                ),
                module._load_jsonl(_project_path(root, f"{prefix}/storyboard/shots.jsonl")),
                module._load_jsonl(
                    _project_path(root, f"{prefix}/storyboard/motion-specs.jsonl")
                ),
                module._load_json(root / PROJECT_FILE),
            )
            reports.append({"source": "builtin:generation_clips", "content": result})
        if "containers" in required:
            module = _load_check_module(
                "short_drama_container_check",
                scripts / "short-drama-video-prompts/scripts/container_check.py",
            )
            result = module.reconcile(
                module._load_jsonl(_project_path(root, f"{prefix}/storyboard/delivery-containers.jsonl")),
                module._load_jsonl(_project_path(root, f"{prefix}/storyboard/shots.jsonl")),
                module._load_jsonl(_project_path(root, f"{prefix}/storyboard/motion-specs.jsonl")),
            )
            reports.append({"source": "builtin:containers", "content": result})
    failed = [
        report["source"]
        for report in reports
        if not _mechanical_report_kinds(report["content"])
    ]
    if failed:
        raise ValueError("mechanical validation failed: " + ", ".join(failed))
    return reports


def _validate_review_bundle_evidence(
    root: Path,
    raw_reference: Any,
    *,
    reviewed_targets: Mapping[str, str],
) -> dict[str, Any]:
    if not isinstance(raw_reference, dict):
        raise ValueError("verdict review_bundle_ref is missing")
    reference = _normalize_artifact_ref(
        root,
        raw_reference,
        expected_owner="short-drama-review",
        allow_operations=True,
    )
    try:
        bundle = _json_loads(
            _project_path(root, reference["artifact"]).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("review bundle is invalid JSON") from error
    if not isinstance(bundle, dict):
        raise ValueError("review bundle must be an object")
    if (
        bundle.get("schema") != REVIEW_BUNDLE_SCHEMA
        or bundle.get("version") != REVIEW_BUNDLE_VERSION
    ):
        raise ValueError("review bundle schema is invalid")
    raw_targets = bundle.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("review bundle targets are missing")
    bundle_targets: dict[str, str] = {}
    for target in raw_targets:
        if not isinstance(target, dict):
            raise ValueError("review bundle target is invalid")
        path = target.get("path")
        digest = target.get("hash")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ValueError("review bundle target is invalid")
        if path in bundle_targets:
            raise ValueError("review bundle targets are duplicated")
        bundle_targets[path] = digest
    if dict(sorted(bundle_targets.items())) != dict(sorted(reviewed_targets.items())):
        raise ValueError("review bundle does not bind the exact reviewed targets")
    state = _read_state(root)
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    records_by_path: dict[str, tuple[str, dict[str, Any]]] = {}
    for artifact_id, record in artifacts.items():
        if not isinstance(artifact_id, str) or not isinstance(record, dict):
            continue
        for key in ("candidate_targets", "accepted_targets"):
            mapping = record.get(key)
            if isinstance(mapping, dict):
                for path in mapping:
                    if path in bundle_targets:
                        records_by_path.setdefault(path, (artifact_id, record))
    for target in raw_targets:
        path = target["path"]
        project_path = _project_path(root, path)
        if _live_hash(project_path) != target["hash"]:
            raise ValueError(f"review bundle target is stale: {path}")
        content = project_path.read_bytes()
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".json", ".jsonl"}:
            extract, extract_issues = _extract_structured_target(content, path)
        elif suffix in {".md", ".markdown"}:
            extract, extract_issues = _extract_markdown_target(project_path, content, path)
        else:
            extract = {"kind": "raw", "content": content.decode("utf-8")}
            extract_issues = []
        if extract_issues or target.get("extract") != extract:
            raise ValueError(f"review bundle extract does not match live target: {path}")
        paired = records_by_path.get(path)
        expected_state = "unregistered"
        if paired is not None:
            artifact_id, record = paired
            accepted = record.get("accepted_targets")
            expected_state = (
                "accepted"
                if isinstance(accepted, dict) and accepted.get(path) == target["hash"]
                else "candidate"
            )
            if target.get("artifact_id") != artifact_id or target.get("owner") != record.get("owner"):
                raise ValueError(f"review bundle lifecycle identity is stale: {path}")
            bundle_lifecycle = target.get("lifecycle")
            if not isinstance(bundle_lifecycle, dict) or any(
                bundle_lifecycle.get(axis) != record.get(axis)
                for axis in ("build_state", "creator_acceptance")
            ):
                raise ValueError(f"review bundle lifecycle snapshot is stale: {path}")
            inputs, input_issues = _bundle_bound_inputs(
                root, record, accepted=(expected_state == "accepted")
            )
            if input_issues or target.get("inputs", []) != inputs:
                raise ValueError(f"review bundle input evidence is stale: {path}")
        if target.get("state") != expected_state:
            raise ValueError(f"review bundle target state is stale: {path}")
    if bundle.get("project") != _creator_authority_summary(root):
        raise ValueError("review bundle creator authority is stale")
    mechanical = bundle.get("mechanical")
    if not isinstance(mechanical, dict) or mechanical.get("status") != "pass":
        raise ValueError("review bundle mechanical status is not pass")
    issues = mechanical.get("issues")
    if not isinstance(issues, list) or issues:
        raise ValueError("review bundle contains mechanical issues")
    reports = mechanical.get("reports")
    if not isinstance(reports, list):
        raise ValueError("review bundle mechanical reports are invalid")
    present: set[str] = set()
    for report in reports:
        if not isinstance(report, dict) or not isinstance(report.get("content"), dict):
            raise ValueError("review bundle mechanical report is invalid")
        present.update(_mechanical_report_kinds(report["content"]))
    missing = sorted(_required_mechanical_report_kinds(bundle_targets) - present)
    if missing:
        raise ValueError("review bundle lacks passing mechanical reports: " + ", ".join(missing))
    live_reports = _live_mechanical_reports(root, bundle_targets)
    live_kinds = {
        kind
        for report in live_reports
        for kind in _mechanical_report_kinds(report["content"])
    }
    if not _required_mechanical_report_kinds(bundle_targets) <= live_kinds:
        raise ValueError("live mechanical validation does not pass")
    return reference


def _record_identity(record: Mapping[str, Any]) -> str | None:
    """Return the stable record ID when exactly one `*_id` value is present."""

    matches = {
        str(value)
        for key, value in record.items()
        if key.endswith("_id") and isinstance(value, str)
    }
    return matches.pop() if len(matches) == 1 else None


def _markdown_sections(content: bytes, relative: str) -> list[dict[str, Any]]:
    text = content.decode("utf-8")
    sections: list[dict[str, Any]] = []
    current_heading: str | None = None
    current: list[str] = []

    def flush() -> None:
        body = "\n".join(current).strip()
        if current_heading is not None or body:
            sections.append({"heading": current_heading, "text": body})
        current.clear()

    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            flush()
            current_heading = stripped
        else:
            current.append(line)
    flush()
    return sections


def _extract_structured_target(
    content: bytes, relative: str
) -> tuple[dict[str, Any], list[str]]:
    suffix = PurePosixPath(relative).suffix.lower()
    if suffix == ".jsonl":
        records = _jsonl_records(content, relative)
        seen: set[str] = set()
        issues: list[str] = []
        enriched: list[dict[str, Any]] = []
        for record in records:
            identity = _record_identity(record)
            if identity is not None:
                if identity in seen:
                    issues.append(f"duplicate record id {identity} in {relative}")
                seen.add(identity)
            enriched.append(
                {
                    "id": identity,
                    "hash": sha256_bytes(_canonical_record_bytes(record)),
                    "record": record,
                }
            )
        return {
            "kind": "jsonl-records",
            "records": enriched,
            "record_count": len(records),
        }, issues
    if suffix == ".json":
        return {"kind": "json-document", "document": _json_loads(content.decode("utf-8"))}, []
    return {"kind": "raw", "content": content.decode("utf-8")}, []


def _extract_markdown_target(
    path: Path, content: bytes, relative: str
) -> tuple[dict[str, Any], list[str]]:
    """Prefer screenplay-index block slices; fall back to heading sections."""

    index_path = path.with_name(f"{path.stem}-index.jsonl")
    if index_path.is_file():
        try:
            index_records = _jsonl_records(index_path.read_bytes(), index_path.name)
            blocks: list[dict[str, Any]] = []
            issues: list[str] = []
            for record in index_records:
                if record.get("record_type") != "block":
                    continue
                start = record.get("byte_start")
                end = record.get("byte_end")
                block_id = record.get("block_id")
                digest = record.get("content_sha256")
                if not isinstance(start, int) or not isinstance(end, int):
                    issues.append(f"invalid byte range in {index_path.name}")
                    continue
                raw = content[start:end]
                actual = sha256_bytes(raw)
                if isinstance(digest, str) and actual != digest.casefold():
                    issues.append(f"index block hash mismatch: {block_id}")
                blocks.append(
                    {
                        "id": block_id,
                        "kind": record.get("kind"),
                        "scene_id": record.get("scene_id"),
                        "hash": actual,
                        "lines": f"{record.get('line_start')}-{record.get('line_end')}",
                        "text": raw.decode("utf-8"),
                    }
                )
            return {
                "kind": "screenplay-blocks",
                "blocks": blocks,
                "block_count": len(blocks),
                "index_hash": sha256_file(index_path),
            }, issues
        except (OSError, ValueError, UnicodeError) as error:
            return {"kind": "raw", "content": content.decode("utf-8")}, [
                f"screenplay index unusable for {relative}: {error}"
            ]
    return {"kind": "markdown-sections", "sections": _markdown_sections(content, relative)}, []


def _bundle_bound_inputs(
    root: Path, record: Mapping[str, Any], *, accepted: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve the artifact's bound inputs into the exact referenced records."""

    prefix = "accepted" if accepted else "candidate"
    plain = _input_bindings(record, f"{prefix}_inputs")
    bindings = _input_record_bindings(record, f"{prefix}_input_records")
    issues: list[str] = []
    entries_by_path: dict[str, dict[str, Any]] = {}
    for relative, digest in plain.items():
        entries_by_path[relative] = {"path": relative, "hash": digest, "extract": None}
    for relative, selectors in bindings.items():
        entry = entries_by_path.setdefault(
            relative, {"path": relative, "hash": None, "extract": None}
        )
        source = _project_path(root, relative)
        if not source.is_file():
            issues.append(f"record source is unavailable: {relative}")
            continue
        content = source.read_bytes()
        suffix = PurePosixPath(relative).suffix.lower()
        extracted: list[dict[str, Any]] = []
        for selector in sorted(selectors):
            try:
                if suffix == ".jsonl":
                    matches = [
                        candidate
                        for candidate in _jsonl_records(content, relative)
                        if any(
                            key.endswith("_id") and value == selector
                            for key, value in candidate.items()
                            if isinstance(value, str)
                        )
                    ]
                    if len(matches) != 1:
                        raise ValueError(
                            f"selector must resolve exactly once: {relative} {selector}"
                        )
                    bound = matches[0]
                else:
                    bound = _resolve_json_pointer(
                        _json_loads(content.decode("utf-8")), selector, relative
                    )
                actual = sha256_bytes(_canonical_record_bytes(bound))
                if actual != selectors[selector]:
                    issues.append(f"record hash mismatch: {relative} {selector}")
                extracted.append({"selector": selector, "hash": actual, "record": bound})
            except (ValueError, UnicodeError, json.JSONDecodeError) as error:
                issues.append(str(error))
        entry["extract"] = {"kind": "bound-records", "records": extracted}
    return sorted(entries_by_path.values(), key=lambda item: item["path"]), issues


def _accepted_or_status(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "unset"}
    status = value.get("status")
    if status == "accepted":
        return dict(value)
    return {"status": status if isinstance(status, str) else "unset"}


def _creator_authority_summary(root: Path) -> dict[str, Any]:
    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    authority = project.get("creator_authority")
    if not isinstance(authority, dict):
        authority = {}
    constraints = authority.get("constraints")
    return {
        "title": project.get("title"),
        "language": project.get("language"),
        "prompt_language": _effective_prompt_language(project),
        "format": project.get("format"),
        "constraints": constraints if isinstance(constraints, list) else [],
        "visual_direction": _accepted_or_status(authority.get("visual_direction")),
        "production_profile": _accepted_or_status(authority.get("production_profile")),
        "delivery_surface": _accepted_or_status(authority.get("delivery_surface")),
    }


def _episode_targets(
    artifacts: Mapping[str, Any], episode: str
) -> dict[str, str]:
    prefixes = tuple(
        f"{root_name}/{episode}/"
        for root_name in (CANONICAL_ROOTS["episodes"], LEGACY_ROOTS["episodes"])
    )
    targets: dict[str, str] = {}
    for record in artifacts.values():
        if not isinstance(record, dict):
            continue
        for relative, digest in _current_record_targets(record).items():
            if relative.startswith(prefixes):
                targets[relative] = digest
    if not targets:
        raise ValueError(f"no lifecycle targets found for {episode}")
    return dict(sorted(targets.items()))


def _review_scope_matches(relative: str, scope: str) -> bool:
    if scope in {"full_episode", "delivery_privacy", "project_calibration"}:
        return True
    normalized = _relative_path(relative)
    owner = _expected_path_owner(normalized)
    parts = PurePosixPath(normalized).parts
    if scope == "source_analysis":
        return "source-analysis" in parts or "source_analysis" in parts
    if scope == "story_script":
        return owner in {"short-drama-develop", "short-drama-write"}
    if scope == "assets_continuity":
        return owner == "short-drama-assets"
    if scope == "image_prompts":
        return owner == "short-drama-image-prompts"
    if scope == "storyboard_keyframes":
        return owner == "short-drama-storyboard"
    if scope == "video_prompts":
        return owner == "short-drama-video-prompts"
    return False


def _delta_review_targets(
    root: Path,
    expected: Mapping[str, str | None],
    verdict_relative: str,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    relative = _relative_path(verdict_relative)
    verdict_path = _project_path(root, relative)
    verdict = _json_loads(verdict_path.read_text(encoding="utf-8"))
    if not isinstance(verdict, dict):
        raise ValueError("delta verdict must be a JSON object")
    reviewed = verdict.get("reviewed_artifacts")
    if not isinstance(reviewed, list):
        raise ValueError("delta verdict lacks reviewed_artifacts")
    previous: dict[str, str] = {}
    for item in reviewed:
        if not isinstance(item, dict):
            raise ValueError("delta verdict reviewed_artifacts are invalid")
        path = item.get("path") or item.get("artifact")
        digest = item.get("hash")
        if isinstance(path, str) and isinstance(digest, str):
            previous[_relative_path(path)] = digest
    resolved = {
        path: digest if digest is not None else _live_hash(_project_path(root, path))
        for path, digest in expected.items()
    }
    changed = {
        path: digest
        for path, digest in resolved.items()
        if previous.get(path) != digest
    }
    if not changed:
        raise ValueError("delta review has no changed targets")
    return changed, {
        "verdict_path": relative,
        "verdict_hash": sha256_file(verdict_path),
        "review_id": verdict.get("review_id"),
        "previous_target_count": len(previous),
    }


def build_review_bundle(
    path: Path,
    *,
    targets: Mapping[str, str | None],
    episode: str | None = None,
    label: str | None = None,
    output: str | None = None,
    mechanical_reports: Iterable[str] = (),
    scope: str | None = None,
    delta_from: str | None = None,
    compact: bool = False,
) -> dict[str, Any]:
    """Collect verified evidence for a reviewer into one compact file.

    The bundle is a review working artifact: it verifies every target's live
    hash against the requested or lifecycle hash, extracts the exact records
    (or screenplay blocks, via the index) with per-record hashes, resolves
    bound inputs to the exact referenced records, and carries the accepted
    creator authority plus any mechanical reports the caller ran. The fresh
    or cold_read reviewer reads this one file instead of hunting raw project
    files; the bundle itself is never part of a delivery package.
    """

    root = find_project(path)
    state = _read_state(root)
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    normalized_scope = scope.strip().casefold() if isinstance(scope, str) else None
    if normalized_scope is not None and normalized_scope not in REVIEW_SCOPES:
        raise ValueError("review scope is invalid")
    expected: dict[str, str | None] = dict(targets)
    if episode:
        for relative, digest in _episode_targets(artifacts, episode).items():
            expected.setdefault(relative, digest)
    if normalized_scope is not None:
        expected = {
            relative: digest
            for relative, digest in expected.items()
            if _review_scope_matches(relative, normalized_scope)
        }
        if not expected:
            raise ValueError(f"review scope has no matching targets: {normalized_scope}")
    delta_basis: dict[str, Any] | None = None
    if delta_from is not None:
        expected, delta_basis = _delta_review_targets(root, expected, delta_from)
    if not expected:
        raise ValueError("review bundle needs at least one --target or --episode")

    records_by_path: dict[str, tuple[str, dict[str, Any]]] = {}
    for artifact_id, record in artifacts.items():
        if not isinstance(record, dict):
            continue
        for key in ("candidate_targets", "accepted_targets"):
            mapping = record.get(key)
            if not isinstance(mapping, dict):
                continue
            for relative in mapping:
                if relative in expected:
                    records_by_path.setdefault(relative, (artifact_id, record))

    mechanical_issues: list[str] = []
    bundle_targets: list[dict[str, Any]] = []
    for relative, requested_hash in sorted(expected.items()):
        project_path = _project_path(root, relative)
        if not project_path.is_file():
            raise ValueError(f"review target is unavailable: {relative}")
        live = _live_hash(project_path)
        if requested_hash is not None and requested_hash != live:
            raise ValueError(
                f"review target hash does not match live file: {relative}"
            )
        paired = records_by_path.get(relative)
        state_label = "unregistered"
        if paired is not None:
            artifact_id, record = paired
            accepted_targets = record.get("accepted_targets")
            accepted_digest = (
                accepted_targets.get(relative)
                if isinstance(accepted_targets, dict)
                else None
            )
            state_label = "accepted" if accepted_digest == live else "candidate"
            snapshot = accepted_digest
            if snapshot is None:
                candidate_targets = record.get("candidate_targets")
                if isinstance(candidate_targets, dict):
                    snapshot = candidate_targets.get(relative)
            if snapshot != live:
                mechanical_issues.append(
                    f"target hash drifted from lifecycle snapshot: {relative}"
                )
        content = project_path.read_bytes()
        suffix = PurePosixPath(relative).suffix.lower()
        extract: dict[str, Any]
        extract_issues: list[str]
        try:
            if suffix in {".json", ".jsonl"}:
                extract, extract_issues = _extract_structured_target(content, relative)
            elif suffix in {".md", ".markdown"}:
                extract, extract_issues = _extract_markdown_target(
                    project_path, content, relative
                )
            else:
                extract = {"kind": "raw", "content": content.decode("utf-8")}
                extract_issues = []
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
            extract = {"kind": "raw", "content": content.decode("utf-8", errors="replace")}
            extract_issues = [f"{relative}: {error}"]
        mechanical_issues.extend(extract_issues)
        entry: dict[str, Any] = {
            "path": relative,
            "hash": live,
            "state": state_label,
            "extract": extract,
        }
        if paired is not None:
            artifact_id, record = paired
            entry["artifact_id"] = artifact_id
            entry["owner"] = record.get("owner")
            entry["lifecycle"] = {
                axis: record.get(axis) for axis in LIFECYCLE_STATES
            }
            inputs, input_issues = _bundle_bound_inputs(
                root, record, accepted=(state_label == "accepted")
            )
            mechanical_issues.extend(input_issues)
            if inputs:
                entry["inputs"] = inputs
        bundle_targets.append(entry)

    reports: list[dict[str, Any]] = []
    supplied_report_issues: list[str] = []
    for relative in mechanical_reports:
        normalized = _relative_path(relative)
        report_path = _project_path(root, normalized)
        if not report_path.is_file():
            raise ValueError(f"mechanical report is unavailable: {normalized}")
        try:
            content = _json_loads(report_path.read_text(encoding="utf-8"))
            reports.append({"source": normalized, "content": content})
            if isinstance(content, dict) and (
                content.get("status") == "fail"
                or content.get("review_status") == "review_required"
            ):
                supplied_report_issues.append(
                    f"mechanical report did not pass: {normalized}"
                )
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"mechanical report must be valid JSON: {normalized}"
            ) from error
    reports.extend(_live_mechanical_reports(root, expected))

    identity_material = _json_dumps(
        {target["path"]: target["hash"] for target in bundle_targets},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    review_id = "RB-" + hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:12]
    mechanical_issues.extend(supplied_report_issues)
    mechanical = {
        "status": "pass" if not mechanical_issues else "issues",
        "issues": sorted(set(mechanical_issues)),
        "reports": reports,
    }
    bundle = {
        "schema": REVIEW_BUNDLE_SCHEMA,
        "version": REVIEW_BUNDLE_VERSION,
        "review_id": review_id,
        "label": label,
        "generated_at": utc_now(),
        "project": _creator_authority_summary(root),
        "targets": bundle_targets,
        "mechanical": mechanical,
    }
    if normalized_scope is not None:
        bundle["review_scope"] = normalized_scope
    if delta_basis is not None:
        bundle["delta_basis"] = delta_basis
    bundle["serialization"] = "compact" if compact else "pretty"
    output_relative = output or f".short-drama/review-bundles/{review_id}.json"
    output_path = _project_path(root, output_relative)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        _json_dumps(
            bundle,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if compact
        else _json_dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True)
    ) + "\n"
    payload_bytes = payload.encode("utf-8")
    _atomic_bytes(output_path, payload_bytes)
    return {
        "review_id": review_id,
        "bundle_path": output_relative,
        "bundle_hash": sha256_bytes(payload_bytes),
        "byte_size": len(payload_bytes),
        "targets": [
            {"path": target["path"], "hash": target["hash"], "state": target["state"]}
            for target in bundle_targets
        ],
        "mechanical": {
            "status": mechanical["status"],
            "issues": len(mechanical["issues"]),
        },
        "review_scope": normalized_scope,
        "delta": delta_basis is not None,
        "serialization": bundle["serialization"],
    }


PIPELINE_VERSION = "2.0.2"
SUITE_VERSION = "0.7.0"
CONTRACT_VERSION = "1.3.3-draft"
PRODUCTION_OBSERVATIONS_FILE = ".short-drama/evidence/production-observations.jsonl"
PRODUCTION_FLOW_DEFAULTS: dict[str, Any] = {
    "pipeline_version": PIPELINE_VERSION,
    "enforcement": "strict",
    "allow_script_first": True,
    "image_result_gate": "prompt_only",
}
MILESTONE_ORDER = ("M0", "M1", "M1.5a", "M1.5b", "M2", "M3", "M4a", "M4b", "M5", "M6", "M7")
SCENE_SHEET_PROFILES = frozenset({"scene_orthographic", "scene_top_view"})
TASK_PACKET_SCHEMA = "short-drama-task-packet"
TASK_PACKET_VERSION = 1
TASK_STAGE_ALIASES = {
    "novel": "novel-analyze",
    "novel-analyze": "novel-analyze",
    "develop": "develop",
    "write": "write",
    "assets": "assets",
    "image": "image-prompts",
    "image-prompts": "image-prompts",
    "storyboard": "storyboard",
    "video": "video-prompts",
    "video-prompts": "video-prompts",
    "review": "review",
}
TASK_STAGE_SPECS: dict[str, dict[str, Any]] = {
    "novel-analyze": {
        "owner": "short-drama-novel-analyze",
        "milestone": "M0",
        "source_owners": (),
        "references": (
            "short-drama-novel-analyze/references/adaptation-triage.md",
            "short-drama-novel-analyze/references/chapter-extraction.md",
        ),
        "outputs": (),
    },
    "develop": {
        "owner": "short-drama-develop",
        "milestone": "M1",
        "source_owners": ("short-drama-novel-analyze",),
        "references": (
            "short-drama-develop/references/story-craft.md",
            "short-drama-develop/references/episode-design.md",
        ),
        "outputs": (
            ("development", "creative-brief.md", "short-drama-develop/assets/creative-brief.md"),
            ("development", "story-engine.md", "short-drama-develop/assets/story-engine.md"),
            ("development", "episode-map.jsonl", "short-drama-develop/assets/episode-map.jsonl"),
        ),
    },
    "write": {
        "owner": "short-drama-write",
        "milestone": "M2",
        "source_owners": (
            "short-drama-develop",
            "short-drama-assets",
            "short-drama-image-prompts",
        ),
        "references": (
            "short-drama-write/references/writing-quality-loop.md",
            "short-drama-write/references/script-craft.md",
            "short-drama-write/references/dialogue-craft.md",
        ),
        "outputs": (
            ("episode", "episode-card.json", "short-drama-write/assets/episode-card.json"),
            ("episode", "beats.jsonl", "short-drama-write/assets/beats.jsonl"),
            ("episode", "screenplay.md", "short-drama-write/assets/screenplay.md"),
            ("episode", "screenplay-index.jsonl", None),
        ),
    },
    "assets": {
        "owner": "short-drama-assets",
        "milestone": "M3",
        "source_owners": ("short-drama-develop", "short-drama-write", "short-drama-assets"),
        "references": (
            "short-drama-assets/references/occurrence-extraction.md",
            "short-drama-assets/references/identity-vs-variant.md",
            "short-drama-assets/references/continuity-delta.md",
        ),
        "outputs": (
            ("episode", "assets/occurrences.jsonl", "short-drama-assets/assets/occurrences.example.jsonl"),
            ("episode", "assets/decisions.jsonl", "short-drama-assets/assets/decisions.example.jsonl"),
            ("episode", "assets/continuity.jsonl", "short-drama-assets/assets/continuity.example.jsonl"),
        ),
    },
    "image-prompts": {
        "owner": "short-drama-image-prompts",
        "milestone": "M4a",
        "source_owners": ("short-drama-write", "short-drama-assets"),
        "references": (
            "short-drama-image-prompts/references/common-recipe.md",
            "short-drama-image-prompts/references/production-sheet-recipes.md",
        ),
        "outputs": (
            ("episode", "assets/image-prompt-specs.jsonl", "short-drama-image-prompts/assets/image-prompt-spec.jsonl.md"),
            ("episode", "assets/image-prompts.md", None),
        ),
    },
    "storyboard": {
        "owner": "short-drama-storyboard",
        "milestone": "M4b",
        "source_owners": (
            "short-drama-write",
            "short-drama-assets",
            "short-drama-image-prompts",
        ),
        "references": (
            "short-drama-storyboard/references/production-shot-grammar.md",
            "short-drama-storyboard/references/keyframe-craft.md",
        ),
        "outputs": (
            ("episode", "storyboard/coverage.json", "short-drama-storyboard/assets/coverage-template.json"),
            ("episode", "storyboard/shots.jsonl", "short-drama-storyboard/assets/shot-template.jsonl"),
            ("episode", "storyboard/keyframes.jsonl", "short-drama-storyboard/assets/keyframe-template.jsonl"),
            ("episode", "storyboard/keyframe-prompts.md", "short-drama-storyboard/assets/keyframe-prompts.md"),
        ),
    },
    "video-prompts": {
        "owner": "short-drama-video-prompts",
        "milestone": "M5",
        "source_owners": (
            "short-drama-write",
            "short-drama-assets",
            "short-drama-image-prompts",
            "short-drama-storyboard",
        ),
        "references": (
            "short-drama-video-prompts/references/motion-recipe.md",
            "short-drama-video-prompts/references/performance-action-timing.md",
            "short-drama-video-prompts/references/camera-audio-continuity.md",
        ),
        "outputs": (
            ("episode", "storyboard/motion-specs.jsonl", "short-drama-video-prompts/assets/motion-spec.jsonl.md"),
            ("episode", "storyboard/generation-clips.jsonl", "short-drama-video-prompts/assets/generation-clip.jsonl.md"),
            ("episode", "storyboard/delivery-containers.jsonl", "short-drama-video-prompts/assets/delivery-container.jsonl.md"),
            ("episode", "storyboard/video-prompts.md", "short-drama-video-prompts/assets/video-prompts.md"),
        ),
    },
    "review": {
        "owner": "short-drama-review",
        "milestone": "M6",
        "source_owners": (
            "short-drama-novel-analyze",
            "short-drama-develop",
            "short-drama-write",
            "short-drama-assets",
            "short-drama-image-prompts",
            "short-drama-storyboard",
            "short-drama-video-prompts",
        ),
        "references": (
            "short-drama-review/references/review-method.md",
            "short-drama-review/references/production-quality-gates.md",
        ),
        "outputs": (
            ("review", "{episode}-findings.jsonl", "short-drama-review/assets/finding-template.jsonl"),
            ("review", "{episode}-verdict.json", "short-drama-review/assets/verdict-template.json"),
        ),
    },
}


def _effective_production_flow(root: Path) -> dict[str, Any]:
    """Return the project's production flow config, defaults when absent."""

    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    raw = project.get("production_flow")
    flow = dict(PRODUCTION_FLOW_DEFAULTS)
    if isinstance(raw, dict):
        for key in PRODUCTION_FLOW_DEFAULTS:
            if key in raw:
                flow[key] = raw[key]
        if "pipeline_version" not in raw:
            flow["pipeline_version"] = "legacy"
    else:
        flow["pipeline_version"] = "legacy"
    if flow.get("enforcement") not in {"strict", "guided"}:
        flow["enforcement"] = "strict"
    if not isinstance(flow.get("allow_script_first"), bool):
        flow["allow_script_first"] = True
    if flow.get("image_result_gate") not in {"prompt_only", "observed"}:
        flow["image_result_gate"] = "prompt_only"
    return flow


def _form_status(root: Path) -> tuple[bool, list[str]]:
    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    authority = project.get("creator_authority")
    if not isinstance(authority, dict):
        authority = {}
    issues: list[str] = []
    for key in ("visual_direction", "production_profile"):
        value = authority.get(key)
        status = value.get("status") if isinstance(value, dict) else None
        if status != "accepted":
            label = "unset" if status is None else str(status)
            issues.append(f"{key} 未接受（{label}）")
    return not issues, issues


def _flow_artifacts(
    state: Mapping[str, Any],
    *,
    owner: str | None = None,
    prefixes: Iterable[str] = (),
) -> list[tuple[str, dict[str, Any], list[str]]]:
    """Return (artifact_id, record, matching paths) for the given owner/roots."""

    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    prefix_list = [str(p).rstrip("/") + "/" for p in prefixes]
    out: list[tuple[str, dict[str, Any], list[str]]] = []
    for artifact_id, record in artifacts.items():
        if not isinstance(record, dict):
            continue
        if owner is not None and record.get("owner") != owner:
            continue
        paths: list[str] = []
        for key in ("accepted_targets", "candidate_targets"):
            mapping = record.get(key)
            if isinstance(mapping, dict):
                paths.extend(str(p) for p in mapping)
        if prefix_list:
            paths = [p for p in paths if any(p.startswith(prefix) for prefix in prefix_list)]
        if paths:
            out.append((artifact_id, record, sorted(set(paths))))
    return sorted(out, key=lambda item: item[0])


def _episode_dirs(root: Path) -> list[str]:
    layout = project_layout(root)
    roots = layout.get("roots")
    episodes_root = roots.get("episodes") if isinstance(roots, dict) else None
    base = _project_path(root, str(episodes_root or CANONICAL_ROOTS["episodes"]))
    if not base.is_dir():
        return []
    return sorted(
        (
            entry.name
            for entry in base.iterdir()
            if entry.is_dir() and re.fullmatch(r"EP\d{3,}", entry.name)
        ),
        # 数值排序而不是字典序：EP1000 必须排在 EP100 之后。
        key=lambda name: int(name[2:]),
    )


def _episode_duration_estimate(
    root: Path, state: Mapping[str, Any], episode: str
) -> dict[str, Any] | None:
    """Best-effort on-screen time estimate for one episode's accepted script.

    target_seconds_per_episode is a creator decision accepted at M0, yet the
    first verification point is storyboard SHT-16 (M4b) — an under-dense
    script can pass the whole writing and assets stages unseen. Reporting the
    same rough estimate here (pipeline) gives the creator a look before M4b.
    Returns None when the project declares no target, the episode has no
    accepted screenplay, or its target file is unavailable.
    """

    target = _target_seconds_per_episode(root)
    if target is None:
        return None
    # Match the flow report's dual-family tolerance: published targets record
    # whichever episodes root was canonical at publish time, and a mixed or
    # legacy project may resolve to either spelling. Try both instead of
    # silently skipping an accepted script recorded under the other family.
    script_relatives = [
        f"{root_name}/{episode}/screenplay.md"
        for root_name in (
            CANONICAL_ROOTS["episodes"],
            LEGACY_ROOTS["episodes"],
        )
    ]
    prefixes = [
        f"{root_name}/{episode}"
        for root_name in (
            CANONICAL_ROOTS["episodes"],
            LEGACY_ROOTS["episodes"],
        )
    ]
    accepted_relative: str | None = None
    for _, record, paths in _flow_artifacts(
        state, owner="short-drama-write", prefixes=prefixes
    ):
        if record.get("creator_acceptance") != "accepted":
            continue
        for candidate in script_relatives:
            if candidate in paths:
                accepted_relative = candidate
                break
        if accepted_relative is not None:
            break
    if accepted_relative is None:
        return None
    script_path = _project_path(root, accepted_relative)
    if not script_path.is_file():
        return None
    estimated = _estimate_screenplay_seconds(script_path.read_bytes())
    return {
        "target_seconds": target,
        "estimated_seconds": estimated,
        "delta_seconds": estimated - target,
    }


def _m2_generation_binding_issues(
    root: Path,
    *,
    target_paths: Iterable[str],
    input_records: Mapping[str, Mapping[str, str]],
) -> list[str]:
    targets = set(_normalize_path_values(target_paths, label="M2 target"))
    episode_cards = [path for path in targets if PurePosixPath(path).name.casefold() == "episode-card.json"]
    if len(episode_cards) != 1:
        return ["M2 needs exactly one episode-card.json in the screenplay artifact"]
    try:
        card = _json_loads(_project_path(root, episode_cards[0]).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["episode-card.json is unavailable or invalid"]
    declarations = card.get("generation_asset_bindings") if isinstance(card, dict) else None
    if not isinstance(declarations, list) or not declarations:
        return ["episode-card.json needs a non-empty generation_asset_bindings array"]

    generation_files = {
        "scope": "设定集/generation/asset-scope.jsonl",
        "models": "设定集/generation/asset-models.jsonl",
        "spatial": "设定集/generation/spatial-models.jsonl",
        "variants": "设定集/generation/variant-models.jsonl",
        "views": "设定集/generation/view-contracts.jsonl",
        "fragments": "设定集/generation/canonical-fragments.jsonl",
    }
    primary_ids = {
        "scope": "asset_id",
        "models": "model_id",
        "spatial": "model_id",
        "variants": "variant_id",
        "views": "view_id",
        "fragments": "fragment_id",
    }
    records: dict[str, dict[str, dict[str, Any]]] = {}
    issues: list[str] = []
    for key, relative in generation_files.items():
        path = _project_path(root, relative)
        try:
            values = _jsonl_records(path.read_bytes(), relative)
        except (OSError, UnicodeError, ValueError):
            issues.append(f"generation input is unavailable or invalid: {relative}")
            records[key] = {}
            continue
        indexed: dict[str, dict[str, Any]] = {}
        for value in values:
            record_id = value.get(primary_ids[key])
            if not isinstance(record_id, str) or not record_id:
                issues.append(f"generation record has no {primary_ids[key]}: {relative}")
                continue
            if record_id in indexed:
                issues.append(f"generation record id is ambiguous: {relative} {record_id}")
            indexed[record_id] = value
        records[key] = indexed

    bound = {
        relative: set(selectors)
        for relative, selectors in input_records.items()
        if relative.startswith("设定集/generation/")
    }
    seen_assets: set[str] = set()
    for number, declaration in enumerate(declarations, 1):
        label = f"generation_asset_bindings[{number}]"
        if not isinstance(declaration, dict):
            issues.append(f"{label} must be an object")
            continue
        asset_id = declaration.get("asset_id")
        model_id = declaration.get("model_id")
        view_ids = declaration.get("view_ids")
        variant_ids = declaration.get("variant_ids", [])
        fragment_ids = declaration.get("fragment_ids")
        if not isinstance(asset_id, str) or not asset_id:
            issues.append(f"{label} needs asset_id")
            continue
        if asset_id in seen_assets:
            issues.append(f"duplicate generation asset declaration: {asset_id}")
        seen_assets.add(asset_id)
        if not isinstance(model_id, str) or not model_id:
            issues.append(f"{asset_id} needs model_id")
            continue
        if not isinstance(view_ids, list) or not view_ids or any(not isinstance(item, str) or not item for item in view_ids):
            issues.append(f"{asset_id} needs non-empty view_ids")
            continue
        if not isinstance(variant_ids, list) or any(not isinstance(item, str) or not item for item in variant_ids):
            issues.append(f"{asset_id} has invalid variant_ids")
            continue
        if not isinstance(fragment_ids, list) or not fragment_ids or any(not isinstance(item, str) or not item for item in fragment_ids):
            issues.append(f"{asset_id} needs non-empty fragment_ids")
            continue
        if len(view_ids) != len(set(view_ids)):
            issues.append(f"{asset_id} has duplicate view_ids")
        if len(variant_ids) != len(set(variant_ids)):
            issues.append(f"{asset_id} has duplicate variant_ids")
        if len(fragment_ids) != len(set(fragment_ids)):
            issues.append(f"{asset_id} has duplicate fragment_ids")
        if asset_id not in bound.get(generation_files["scope"], set()):
            issues.append(f"{asset_id} scope record is not bound")
        scope_record = records["scope"].get(asset_id)
        if scope_record is None:
            issues.append(f"{asset_id} scope record does not resolve")
        model_file = "spatial" if model_id in records["spatial"] else "models"
        model = records[model_file].get(model_id)
        if model is None or (model.get("asset_id") or model.get("location_id")) != asset_id:
            issues.append(f"{asset_id} model_id does not resolve to this asset: {model_id}")
        elif model_id not in bound.get(generation_files[model_file], set()):
            issues.append(f"{asset_id} model record is not bound: {model_id}")
        for view_id in view_ids:
            view = records["views"].get(view_id)
            if view is None or view.get("asset_id") != asset_id or view.get("model_ref", {}).get("record_id") != model_id:
                issues.append(f"{asset_id} view does not resolve to the bound model: {view_id}")
            if view_id not in bound.get(generation_files["views"], set()):
                issues.append(f"{asset_id} view record is not bound: {view_id}")
        for variant_id in variant_ids:
            variant = records["variants"].get(variant_id)
            if variant is None or variant.get("base_asset_id") != asset_id:
                issues.append(f"{asset_id} variant does not resolve to this asset: {variant_id}")
            if variant_id not in bound.get(generation_files["variants"], set()):
                issues.append(f"{asset_id} variant record is not bound: {variant_id}")
        selected_fragments = [records["fragments"].get(fragment_id) for fragment_id in fragment_ids]
        if any(fragment is None for fragment in selected_fragments):
            issues.append(f"{asset_id} references an unknown fragment")
            continue
        if any(fragment_id not in bound.get(generation_files["fragments"], set()) for fragment_id in fragment_ids):
            issues.append(f"{asset_id} has fragment records that are not bound")
        asset_fragments = [fragment for fragment in selected_fragments if fragment.get("asset_id") == asset_id]
        foreign_fragments = [
            fragment
            for fragment in selected_fragments
            if fragment.get("fragment_kind") != "style_core"
            and fragment.get("asset_id") != asset_id
        ]
        if foreign_fragments:
            issues.append(f"{asset_id} declaration includes fragments owned by another asset")
        kind_counts: dict[str, int] = {}
        for fragment in asset_fragments:
            kind = str(fragment.get("fragment_kind"))
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        missing = sorted(
            kind
            for kind in {"identity_full", "continuity_lock", "view_projection", "negative_lock"}
            if kind_counts.get(kind, 0) == 0
        )
        if missing:
            issues.append(f"{asset_id} is missing fragment kinds: {', '.join(missing)}")
        for kind in ("identity_full", "continuity_lock", "negative_lock"):
            if kind_counts.get(kind, 0) != 1:
                issues.append(f"{asset_id} needs exactly one {kind} fragment")
        style_fragments = [
            fragment
            for fragment in selected_fragments
            if fragment.get("fragment_kind") == "style_core" and not fragment.get("asset_id")
        ]
        if len(style_fragments) != 1:
            issues.append(f"{asset_id} needs exactly one project style_core fragment")
        for fragment in asset_fragments:
            kind = fragment.get("fragment_kind")
            record_ids = {
                reference.get("record_id")
                for reference in fragment.get("model_refs", [])
                if isinstance(reference, dict) and isinstance(reference.get("record_id"), str)
            }
            if kind in {"identity_full", "continuity_lock", "negative_lock"} and model_id not in record_ids:
                issues.append(f"{asset_id} {kind} fragment does not bind model {model_id}")
        fragment_views = {
            fragment.get("scope", {}).get("view_id")
            for fragment in asset_fragments
            if fragment.get("fragment_kind") == "view_projection"
            and fragment.get("scope", {}).get("sheet_profile") is None
        }
        if set(view_ids) != fragment_views:
            issues.append(
                f"{asset_id} view_ids do not exactly match view_projection fragments"
            )
        for fragment in asset_fragments:
            if fragment.get("fragment_kind") != "view_projection":
                continue
            scope = fragment.get("scope", {})
            view_id = scope.get("view_id")
            sheet_profile = scope.get("sheet_profile")
            record_ids = {
                reference.get("record_id")
                for reference in fragment.get("model_refs", [])
                if isinstance(reference, dict)
            }
            if isinstance(view_id, str) and view_id not in record_ids:
                issues.append(f"{asset_id} view_projection does not bind its scoped View")
            elif sheet_profile in SCENE_SHEET_PROFILES and model_id not in record_ids:
                issues.append(
                    f"{asset_id} {sheet_profile} projection does not bind spatial model {model_id}"
                )
            elif view_id is None and sheet_profile not in SCENE_SHEET_PROFILES:
                issues.append(f"{asset_id} has invalid view_projection scope")
        sheet_profiles = [
            fragment.get("scope", {}).get("sheet_profile")
            for fragment in asset_fragments
            if fragment.get("fragment_kind") == "view_projection"
            and fragment.get("scope", {}).get("sheet_profile") is not None
        ]
        if len(sheet_profiles) != len(set(sheet_profiles)):
            issues.append(f"{asset_id} has duplicate scene sheet projection fragments")
        fragment_variants = {
            fragment.get("variant_id")
            for fragment in asset_fragments
            if fragment.get("fragment_kind") == "variant_delta"
        }
        if set(variant_ids) != fragment_variants:
            issues.append(f"{asset_id} variant_ids do not match variant_delta fragments")
        for fragment in asset_fragments:
            if fragment.get("fragment_kind") != "variant_delta":
                continue
            variant_id = fragment.get("variant_id")
            record_ids = {
                reference.get("record_id")
                for reference in fragment.get("model_refs", [])
                if isinstance(reference, dict)
            }
            if variant_id not in record_ids:
                issues.append(f"{asset_id} variant_delta does not bind its variant record")
            if model_id not in record_ids:
                issues.append(f"{asset_id} variant_delta does not bind base model {model_id}")
    return sorted(set(issues))


def _m2_generation_binding_map(
    root: Path, target_paths: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """Return the episode-level generation allowance declared by M2."""

    cards = [
        _relative_path(path)
        for path in target_paths
        if PurePosixPath(path).name.casefold() == "episode-card.json"
    ]
    if len(cards) != 1:
        return {}
    try:
        document = _json_loads(_project_path(root, cards[0]).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    declarations = document.get("generation_asset_bindings") if isinstance(document, dict) else None
    if not isinstance(declarations, list):
        return {}
    scope_records: dict[str, dict[str, Any]] = {}
    fragment_records: dict[str, dict[str, Any]] = {}
    try:
        scope_records = {
            str(record["asset_id"]): record
            for record in _jsonl_records(
                _project_path(root, "设定集/generation/asset-scope.jsonl").read_bytes(),
                "设定集/generation/asset-scope.jsonl",
            )
            if isinstance(record.get("asset_id"), str)
        }
        fragment_records = {
            str(record["fragment_id"]): record
            for record in _jsonl_records(
                _project_path(root, "设定集/generation/canonical-fragments.jsonl").read_bytes(),
                "设定集/generation/canonical-fragments.jsonl",
            )
            if isinstance(record.get("fragment_id"), str)
        }
    except (OSError, UnicodeError, ValueError):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for declaration in declarations:
        if not isinstance(declaration, dict):
            continue
        asset_id = declaration.get("asset_id")
        model_id = declaration.get("model_id")
        view_ids = declaration.get("view_ids")
        variant_ids = declaration.get("variant_ids", [])
        fragment_ids = declaration.get("fragment_ids")
        if not isinstance(asset_id, str) or not isinstance(model_id, str):
            continue
        if not isinstance(view_ids, list) or not isinstance(variant_ids, list) or not isinstance(fragment_ids, list):
            continue
        result[asset_id] = {
            "model_id": model_id,
            "asset_kind": scope_records.get(asset_id, {}).get("asset_kind"),
            # M2 authorizes episode-level projections. M4b owns the actual
            # per-shot choice and must select from this set.
            "view_ids": {item for item in view_ids if isinstance(item, str)},
            "variant_ids": {item for item in variant_ids if isinstance(item, str)},
            "fragment_ids": {item for item in fragment_ids if isinstance(item, str)},
            "fragments": {
                item: fragment_records[item]
                for item in fragment_ids
                if isinstance(item, str) and item in fragment_records
            },
        }
    return result


def _accepted_stage_file(
    group: Iterable[tuple[str, dict[str, Any], list[str]]], suffix: str
) -> tuple[str | None, list[str]]:
    """Resolve one accepted stage file and report ambiguous/missing providers."""

    matches: list[str] = []
    normalized_suffix = suffix.casefold()
    for _artifact_id, record, _paths in group:
        if (
            record.get("build_state") != "materialized"
            or record.get("creator_acceptance") != "accepted"
        ):
            continue
        targets = record.get("accepted_targets")
        if not isinstance(targets, dict):
            continue
        matches.extend(
            str(path)
            for path in targets
            if str(PurePosixPath(path)).casefold().endswith(normalized_suffix)
        )
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0], []
    if not unique:
        return None, [f"missing accepted stage file: {suffix}"]
    return None, [f"accepted stage file is ambiguous: {suffix}"]


def _stage_jsonl_records(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
    suffix: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    relative, issues = _accepted_stage_file(group, suffix)
    if relative is None:
        return [], issues
    try:
        return _jsonl_records(_project_path(root, relative).read_bytes(), relative), []
    except (OSError, UnicodeError, ValueError) as error:
        return [], [f"invalid accepted stage file {suffix}: {error}"]


def _m2_screenplay_index_evidence(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
) -> tuple[tuple[str, str, dict[str, str]] | None, list[str]]:
    relative, issues = _accepted_stage_file(group, "/screenplay-index.jsonl")
    if relative is None:
        return None, issues
    try:
        content = _project_path(root, relative).read_bytes()
        records = _jsonl_records(content, relative)
    except (OSError, UnicodeError, ValueError) as error:
        return None, [f"invalid accepted screenplay index: {error}"]
    hashes: dict[str, str] = {}
    for record in records:
        if record.get("record_type") != "block":
            continue
        block_id = record.get("block_id")
        if not isinstance(block_id, str) or not block_id:
            issues.append("accepted screenplay index contains a block without block_id")
            continue
        if block_id in hashes:
            issues.append(f"accepted screenplay index has duplicate block_id: {block_id}")
            continue
        hashes[block_id] = _record_digest(relative, record)
    if not hashes:
        issues.append("accepted screenplay index contains no block records")
    return ((relative, sha256_bytes(content), hashes) if not issues else None), issues


def _exact_screenplay_ref(
    reference: Any,
    evidence: tuple[str, str, Mapping[str, str]] | None,
) -> bool:
    if not isinstance(reference, dict) or evidence is None:
        return False
    relative, file_hash, hashes = evidence
    record_id = reference.get("record_id")
    digest = reference.get("hash")
    artifact = reference.get("artifact")
    try:
        normalized_artifact = _relative_path(artifact) if isinstance(artifact, str) else None
    except ValueError:
        return False
    return (
        reference.get("owner") == "short-drama-write"
        and normalized_artifact == relative
        and isinstance(record_id, str)
        and record_id in hashes
        and digest == file_hash
    )


def _ref_record_id(reference: Any) -> str | None:
    if not isinstance(reference, dict):
        return None
    value = reference.get("record_id")
    return value if isinstance(value, str) and value else None


def _binding_value(binding: Mapping[str, Any], direct: str, ref: str) -> str | None:
    value = binding.get(direct)
    if isinstance(value, str) and value:
        return value
    return _ref_record_id(binding.get(ref))


def _normalized_generation_binding(binding: Any) -> dict[str, str | None] | None:
    if not isinstance(binding, dict):
        return None
    asset_id = binding.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        return None
    return {
        "asset_id": asset_id,
        "model_id": _binding_value(binding, "model_id", "model_ref"),
        "view_id": _binding_value(binding, "view_id", "view_ref"),
        "variant_id": _binding_value(binding, "variant_id", "variant_ref"),
    }


def _prompt_fragment_ids(record: Mapping[str, Any]) -> set[str]:
    components = record.get("prompt_components")
    refs = components.get("fragment_refs") if isinstance(components, dict) else None
    if not isinstance(refs, list):
        return set()
    return {
        fragment_id
        for reference in refs
        if isinstance(reference, dict)
        and isinstance((fragment_id := reference.get("fragment_id")), str)
        and fragment_id
    }


def _prompt_fragment_refs(
    record: Mapping[str, Any],
) -> tuple[tuple[str, str], ...] | None:
    components = record.get("prompt_components")
    refs = components.get("fragment_refs") if isinstance(components, dict) else None
    if not isinstance(refs, list):
        return None
    normalized: list[tuple[str, str]] = []
    for reference in refs:
        if not isinstance(reference, dict):
            return None
        fragment_id = reference.get("fragment_id")
        digest = reference.get("hash")
        if (
            not isinstance(fragment_id, str)
            or not fragment_id
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            return None
        normalized.append((fragment_id, digest))
    return tuple(normalized)


def _binding_fragment_refs(
    binding: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    sheet_profile: str | None = None,
) -> tuple[tuple[str, str], ...] | None:
    fragments = expected.get("fragments")
    if not isinstance(fragments, dict):
        return None
    asset_id = binding.get("asset_id")
    view_id = binding.get("view_id")
    variant_id = binding.get("variant_id")
    selected: list[dict[str, Any]] = []

    def one(kind: str, *, match: str | None = None) -> bool:
        matches = [
            record
            for record in fragments.values()
            if isinstance(record, dict)
            and record.get("fragment_kind") == kind
            and (
                kind == "style_core"
                or record.get("asset_id") == asset_id
            )
            and (
                match is None
                or (
                    record.get("scope", {}).get("view_id") == match
                    if kind == "view_projection"
                    else record.get("variant_id") == match
                )
            )
        ]
        if len(matches) != 1:
            return False
        selected.append(matches[0])
        return True

    if not one("style_core"):
        return None
    if not one("identity_full") or not one("continuity_lock"):
        return None
    if variant_id is not None and not one("variant_delta", match=str(variant_id)):
        return None
    if sheet_profile is None:
        if not isinstance(view_id, str) or not one("view_projection", match=view_id):
            return None
    else:
        matches = [
            record
            for record in fragments.values()
            if isinstance(record, dict)
            and record.get("fragment_kind") == "view_projection"
            and record.get("asset_id") == asset_id
            and record.get("scope", {}).get("sheet_profile") == sheet_profile
        ]
        if len(matches) != 1:
            return None
        selected.append(matches[0])
    if not one("negative_lock"):
        return None
    result: list[tuple[str, str]] = []
    for record in selected:
        fragment_id = record.get("fragment_id")
        digest = record.get("fragment_hash")
        if not isinstance(fragment_id, str) or not isinstance(digest, str):
            return None
        result.append((fragment_id, digest))
    return tuple(result)


def _record_expected_fragment_refs(
    bindings: list[dict[str, str | None]],
    m2_bindings: Mapping[str, Mapping[str, Any]],
    *,
    sheet_profile: str | None = None,
) -> tuple[tuple[str, str], ...] | None:
    local: list[tuple[tuple[str, str], ...]] = []
    for binding in bindings:
        expected = m2_bindings.get(str(binding["asset_id"]))
        if expected is None:
            return None
        refs = _binding_fragment_refs(
            binding,
            expected,
            sheet_profile=sheet_profile,
        )
        if refs is None:
            return None
        local.append(refs)
    if not local:
        return None
    result: list[tuple[str, str]] = [local[0][0]]
    for expected_kind in (
        "identity_full",
        "continuity_lock",
        "variant_delta",
        "view_projection",
        "negative_lock",
    ):
        for binding, refs in zip(bindings, local):
            expected = m2_bindings[str(binding["asset_id"])]
            fragment_records = expected.get("fragments", {})
            match = next(
                (
                    reference
                    for reference in refs
                    if isinstance(fragment_records.get(reference[0]), dict)
                    and fragment_records[reference[0]].get("fragment_kind")
                    == expected_kind
                ),
                None,
            )
            if match is not None:
                result.append(match)
    return tuple(result)


def _binding_against_m2_issues(
    binding: dict[str, str | None],
    m2_bindings: Mapping[str, Mapping[str, Any]],
    *,
    label: str,
    require_view: bool = True,
) -> list[str]:
    asset_id = str(binding["asset_id"])
    expected = m2_bindings.get(asset_id)
    if expected is None:
        return [f"{label} introduces asset not declared by M2: {asset_id}"]
    issues: list[str] = []
    if binding.get("model_id") != expected.get("model_id"):
        issues.append(f"{label} model does not match M2 for {asset_id}")
    view_id = binding.get("view_id")
    if require_view and (
        not isinstance(view_id, str) or view_id not in expected.get("view_ids", set())
    ):
        issues.append(f"{label} View is not authorized by M2 for {asset_id}")
    variant_id = binding.get("variant_id")
    allowed_variants = expected.get("variant_ids", set())
    if variant_id is not None and variant_id not in allowed_variants:
        issues.append(f"{label} variant is not declared by M2 for {asset_id}")
    return issues


def _m3_asset_consumption_issues(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
    m2_bindings: Mapping[str, Mapping[str, Any]],
    screenplay_index: tuple[str, str, Mapping[str, str]] | None = None,
) -> list[str]:
    group = list(group)
    occurrences, occurrence_issues = _stage_jsonl_records(
        root, group, "/assets/occurrences.jsonl"
    )
    decisions, decision_issues = _stage_jsonl_records(
        root, group, "/assets/decisions.jsonl"
    )
    continuity, continuity_issues = _stage_jsonl_records(
        root, group, "/assets/continuity.jsonl"
    )
    issues = occurrence_issues + decision_issues + continuity_issues
    if issues:
        return sorted(set(issues))
    if not occurrences:
        issues.append("M3 occurrences.jsonl cannot be empty")

    occurrence_ids: set[str] = set()
    occurrence_by_id: dict[str, dict[str, Any]] = {}
    allowed_asset_kinds = {"character", "creature", "location", "prop", "vehicle", "effect"}
    for occurrence in occurrences:
        occurrence_id = occurrence.get("occurrence_id")
        if not isinstance(occurrence_id, str) or not occurrence_id:
            issues.append("M3 occurrence needs occurrence_id")
            continue
        if occurrence_id in occurrence_ids:
            issues.append(f"duplicate M3 occurrence_id: {occurrence_id}")
        occurrence_ids.add(occurrence_id)
        occurrence_by_id[occurrence_id] = occurrence
        if occurrence.get("asset_kind") not in allowed_asset_kinds:
            issues.append(f"M3 occurrence has invalid asset_kind: {occurrence_id}")
        source_ref = occurrence.get("source_ref")
        if not _exact_screenplay_ref(source_ref, screenplay_index):
            issues.append(f"M3 occurrence needs exact screenplay source_ref: {occurrence_id}")
        source_blocks = occurrence.get("source_blocks")
        screenplay_hashes = screenplay_index[2] if screenplay_index is not None else {}
        source_record_id = _ref_record_id(source_ref)
        if (
            not isinstance(source_blocks, list)
            or not source_blocks
            or any(not isinstance(item, str) or item not in screenplay_hashes for item in source_blocks)
            or len(source_blocks) != len(set(source_blocks))
            or source_record_id not in source_blocks
        ):
            issues.append(f"M3 occurrence has invalid screenplay source_blocks: {occurrence_id}")

    decided_occurrences: dict[str, int] = {}
    consumed_assets: set[str] = set()
    allowed_kinds = {"reuse", "new_variant", "new_asset", "unresolved"}
    decision_ids: set[str] = set()
    for decision in decisions:
        raw_decision_id = decision.get("decision_id")
        if not isinstance(raw_decision_id, str) or not raw_decision_id:
            issues.append("M3 decision needs decision_id")
            decision_id = "<unknown>"
        else:
            decision_id = raw_decision_id
            if decision_id in decision_ids:
                issues.append(f"duplicate M3 decision_id: {decision_id}")
            decision_ids.add(decision_id)
        kind = decision.get("decision_kind")
        if kind not in allowed_kinds:
            issues.append(f"M3 decision has invalid kind: {decision_id}")
        if kind in {"new_asset", "new_variant"}:
            issues.append(f"M3 {kind} requires M1.5a/M1.5b and M2 rebind: {decision_id}")
        if kind == "unresolved":
            issues.append(f"M3 unresolved decision blocks downstream consumption: {decision_id}")
        decision_asset_kind = decision.get("asset_kind")
        if decision_asset_kind not in allowed_asset_kinds:
            issues.append(f"M3 decision has invalid asset_kind: {decision_id}")
        refs = decision.get("occurrence_refs")
        if not isinstance(refs, list) or not refs:
            issues.append(f"M3 decision needs occurrence_refs: {decision_id}")
        else:
            for reference in refs:
                occurrence_id = _ref_record_id(reference)
                if occurrence_id not in occurrence_ids:
                    issues.append(f"M3 decision references unknown occurrence: {decision_id}")
                    continue
                decided_occurrences[occurrence_id] = decided_occurrences.get(occurrence_id, 0) + 1
                occurrence = occurrence_by_id[occurrence_id]
                if occurrence.get("asset_kind") != decision_asset_kind:
                    issues.append(f"M3 decision asset_kind differs from occurrence: {decision_id}")
        cause_ref = decision.get("cause_ref")
        if cause_ref is not None and not _exact_screenplay_ref(cause_ref, screenplay_index):
            issues.append(f"M3 decision has stale screenplay cause_ref: {decision_id}")
        proposed = decision.get("proposed_binding")
        identity_id = proposed.get("identity_id") if isinstance(proposed, dict) else None
        if kind in {"reuse", "new_variant"}:
            if not isinstance(identity_id, str) or not identity_id:
                issues.append(f"M3 resolved decision needs identity_id: {decision_id}")
            else:
                consumed_assets.add(identity_id)
                expected = m2_bindings.get(identity_id)
                generation_model_id = proposed.get("generation_model_id")
                if expected is None or generation_model_id != expected.get("model_id"):
                    issues.append(f"M3 decision generation model does not match M2: {decision_id}")
                if "generation_variant_id" not in proposed:
                    issues.append(f"M3 decision must explicitly select base or generation variant: {decision_id}")
                else:
                    generation_variant_id = proposed.get("generation_variant_id")
                    if expected is None:
                        pass
                    elif generation_variant_id is not None and (
                        not isinstance(generation_variant_id, str)
                        or generation_variant_id not in expected.get("variant_ids", set())
                    ):
                        issues.append(f"M3 decision generation variant is not declared by M2: {decision_id}")
                for reference in refs if isinstance(refs, list) else []:
                    occurrence_id = _ref_record_id(reference)
                    occurrence = occurrence_by_id.get(str(occurrence_id))
                    occurrence_binding = occurrence.get("proposed_binding") if isinstance(occurrence, dict) else None
                    occurrence_identity = (
                        occurrence_binding.get("identity_id")
                        if isinstance(occurrence_binding, dict)
                        else None
                    )
                    if occurrence_identity is not None and occurrence_identity != identity_id:
                        issues.append(f"M3 decision identity differs from occurrence proposal: {decision_id}")

    for occurrence_id in sorted(occurrence_ids):
        count = decided_occurrences.get(occurrence_id, 0)
        if count != 1:
            issues.append(f"M3 occurrence needs exactly one decision: {occurrence_id}")
    expected_assets = set(m2_bindings)
    missing = sorted(expected_assets - consumed_assets)
    unexpected = sorted(consumed_assets - expected_assets)
    if missing:
        issues.append("M3 does not reconcile M2 assets: " + ", ".join(missing))
    if unexpected:
        issues.append("M3 consumes assets not declared by M2: " + ", ".join(unexpected))
    seen_deltas: set[str] = set()
    for delta in continuity:
        delta_id = delta.get("delta_id")
        if not isinstance(delta_id, str) or not delta_id:
            issues.append("M3 continuity delta needs delta_id")
            continue
        if delta_id in seen_deltas:
            issues.append(f"duplicate M3 continuity delta_id: {delta_id}")
        seen_deltas.add(delta_id)
        subject_id = _ref_record_id(delta.get("subject_ref"))
        if subject_id not in m2_bindings:
            issues.append(f"M3 continuity subject is not declared by M2: {delta_id}")
            continue
        for field in ("before", "after", "effective_range"):
            if not isinstance(delta.get(field), dict) or not delta[field]:
                issues.append(f"M3 continuity delta needs non-empty {field}: {delta_id}")
        cause_ref = delta.get("cause_ref")
        if not _exact_screenplay_ref(cause_ref, screenplay_index):
            issues.append(f"M3 continuity delta needs screenplay cause_ref: {delta_id}")
        affected = delta.get("affected_binding_refs")
        affected_ids = {
            _ref_record_id(reference)
            for reference in affected
        } if isinstance(affected, list) else set()
        if subject_id not in affected_ids:
            issues.append(f"M3 continuity delta does not affect its subject binding: {delta_id}")
        after = delta.get("after")
        if isinstance(after, dict):
            if "generation_variant_id" not in after:
                issues.append(f"M3 continuity after must select base or generation variant: {delta_id}")
            else:
                generation_variant_id = after.get("generation_variant_id")
                if generation_variant_id is not None and (
                    not isinstance(generation_variant_id, str)
                    or generation_variant_id
                    not in m2_bindings[subject_id].get("variant_ids", set())
                ):
                    issues.append(f"M3 continuity generation variant is not declared by M2: {delta_id}")
    return sorted(set(issues))


def _m4a_asset_consumption_issues(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
    m2_bindings: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    records, issues = _stage_jsonl_records(
        root, group, "/assets/image-prompt-specs.jsonl"
    )
    if issues:
        return issues
    consumed: set[str] = set()
    covered_views: dict[str, set[str]] = {}
    covered_variants: dict[str, set[str]] = {}
    base_covered: set[str] = set()
    spec_ids: set[str] = set()
    for record in records:
        spec_id = record.get("spec_id")
        if not isinstance(spec_id, str) or not spec_id:
            issues.append("M4a prompt spec needs spec_id")
        elif spec_id in spec_ids:
            issues.append(f"duplicate M4a spec_id: {spec_id}")
        else:
            spec_ids.add(spec_id)
        components = record.get("prompt_components")
        if not isinstance(components, dict) or components.get("profile") != "asset_board":
            issues.append("M4a prompt spec must use profile asset_board")
        bindings = record.get("asset_bindings")
        if not isinstance(bindings, list) or not bindings:
            issues.append("M4a prompt spec needs asset_bindings")
            continue
        if len(bindings) != 1:
            issues.append("M4a asset_board prompt spec must bind exactly one asset")
        sheet = record.get("sheet_profile")
        sheet_profile = sheet.get("name") if isinstance(sheet, dict) else None
        if sheet_profile is not None and sheet_profile not in SCENE_SHEET_PROFILES:
            issues.append(f"M4a has unsupported sheet_profile: {sheet_profile}")
            sheet_profile = None
        normalized_bindings: list[dict[str, str | None]] = []
        for raw in bindings:
            binding = _normalized_generation_binding(raw)
            if binding is None:
                issues.append("M4a has invalid generation asset binding")
                continue
            normalized_bindings.append(binding)
            asset_id = str(binding["asset_id"])
            consumed.add(asset_id)
            view_id = binding.get("view_id")
            if sheet_profile is None and isinstance(view_id, str):
                covered_views.setdefault(asset_id, set()).add(view_id)
            variant_id = binding.get("variant_id")
            if isinstance(variant_id, str):
                covered_variants.setdefault(asset_id, set()).add(variant_id)
            else:
                base_covered.add(asset_id)
            issues.extend(
                _binding_against_m2_issues(
                    binding,
                    m2_bindings,
                    label="M4a",
                    require_view=sheet_profile is None,
                )
            )
        actual_refs = _prompt_fragment_refs(record)
        expected_refs = _record_expected_fragment_refs(
            normalized_bindings,
            m2_bindings,
            sheet_profile=sheet_profile,
        )
        if actual_refs is None or expected_refs is None or actual_refs != expected_refs:
            issues.append("M4a prompt fragment fingerprint does not match its asset binding")
    missing = sorted(set(m2_bindings) - consumed)
    if missing:
        issues.append("M4a does not cover M2 assets: " + ", ".join(missing))
    for asset_id, expected in m2_bindings.items():
        if asset_id not in base_covered:
            issues.append(f"M4a has no base asset board for {asset_id}")
        missing_views = sorted(
            set(expected.get("view_ids", set())) - covered_views.get(asset_id, set())
        )
        if missing_views:
            issues.append(
                f"M4a does not cover Views for {asset_id}: " + ", ".join(missing_views)
            )
        missing_variants = sorted(
            set(expected.get("variant_ids", set()))
            - covered_variants.get(asset_id, set())
        )
        if missing_variants:
            issues.append(
                f"M4a does not cover variants for {asset_id}: "
                + ", ".join(missing_variants)
            )
    return sorted(set(issues))


def _m4a_image_result_observation_issues(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
) -> list[str]:
    """Require exact active generated-result observations without claiming approval."""

    relative, issues = _accepted_stage_file(group, "/assets/image-prompt-specs.jsonl")
    if relative is None:
        return issues
    try:
        spec_content = _project_path(root, relative).read_bytes()
        specs = _jsonl_records(spec_content, relative)
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid accepted M4a prompt specs: {error}"]

    observation_path = _project_path(root, PRODUCTION_OBSERVATIONS_FILE)
    if not observation_path.is_file():
        return [
            "observed image_result_gate needs project-private production observations at "
            + PRODUCTION_OBSERVATIONS_FILE
        ]
    try:
        observations = _jsonl_records(
            observation_path.read_bytes(), PRODUCTION_OBSERVATIONS_FILE
        )
    except (OSError, UnicodeError, ValueError) as error:
        return [f"invalid production observations: {error}"]

    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    project_id = project.get("project_id")
    authority = project.get("creator_authority")
    production_profile = (
        authority.get("production_profile") if isinstance(authority, dict) else None
    )
    production_profile_hash = sha256_bytes(
        _canonical_record_bytes(production_profile)
    )
    spec_file_hash = sha256_bytes(spec_content)

    active = [
        observation
        for observation in observations
        if observation.get("observation_kind") == "generated_result"
        and observation.get("evidence_state") == "active"
    ]
    result: list[str] = []
    for spec in specs:
        spec_id = spec.get("spec_id")
        if not isinstance(spec_id, str) or not spec_id:
            continue
        spec_hash = _record_digest(relative, spec)
        reference_bindings = spec.get("reference_bindings", [])
        if not isinstance(reference_bindings, list):
            reference_bindings = []
        reference_slot_set_hash = sha256_bytes(
            _canonical_record_bytes(reference_bindings)
        )

        def matches(observation: Mapping[str, Any]) -> bool:
            media_hash = observation.get("observed_media_sha256")
            if (
                not isinstance(media_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", media_hash) is None
            ):
                return False
            refs = observation.get("prompt_or_spec_refs")
            if not isinstance(refs, list) or not any(
                isinstance(reference, dict)
                and reference.get("owner") == "short-drama-image-prompts"
                and reference.get("artifact") == relative
                and reference.get("hash") == spec_file_hash
                and reference.get("record_id") == spec_id
                and reference.get("field") == "/generic_prompt"
                for reference in refs
            ):
                return False
            valid_only_for = observation.get("valid_only_for")
            if not isinstance(valid_only_for, dict):
                return False
            prompt_hashes = valid_only_for.get("prompt_or_spec_hashes")
            if (
                valid_only_for.get("project_id") != project_id
                or not isinstance(prompt_hashes, list)
                or spec_hash not in prompt_hashes
                or valid_only_for.get("reference_slot_set_hash")
                != reference_slot_set_hash
                or valid_only_for.get("production_profile_hash")
                != production_profile_hash
            ):
                return False
            configuration = observation.get("production_configuration")
            profile_ref = (
                configuration.get("profile_ref")
                if isinstance(configuration, dict)
                else None
            )
            return bool(
                isinstance(profile_ref, dict)
                and profile_ref.get("owner") == "creator"
                and profile_ref.get("artifact") == PROJECT_FILE
                and profile_ref.get("field") == "/creator_authority/production_profile"
                and profile_ref.get("hash") == production_profile_hash
            )

        if not any(matches(observation) for observation in active):
            result.append(
                f"M4a spec {spec_id} needs an exact active generated_result observation"
            )
    return sorted(set(result))


def _m4a_result_gate_issues(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
) -> list[str]:
    if _effective_production_flow(root)["image_result_gate"] == "prompt_only":
        return []
    return _m4a_image_result_observation_issues(root, group)


def _shot_generation_bindings(record: Mapping[str, Any]) -> list[dict[str, str | None]]:
    raw = record.get("generation_asset_bindings")
    if not isinstance(raw, list):
        return []
    return [
        binding
        for item in raw
        if (binding := _normalized_generation_binding(item)) is not None
    ]


def _binding_signature(
    bindings: Iterable[Mapping[str, Any]],
    m2_bindings: Mapping[str, Mapping[str, Any]],
) -> tuple[
    tuple[
        str,
        str | None,
        str | None,
        str | None,
        tuple[tuple[str, str], ...] | None,
    ],
    ...,
]:
    return tuple(
        (
            str(binding.get("asset_id")),
            binding.get("model_id") if isinstance(binding.get("model_id"), str) else None,
            binding.get("view_id") if isinstance(binding.get("view_id"), str) else None,
            binding.get("variant_id") if isinstance(binding.get("variant_id"), str) else None,
            _binding_fragment_refs(
                binding,
                m2_bindings.get(str(binding.get("asset_id")), {}),
            ),
        )
        for binding in bindings
    )


def _m4b_asset_consumption_issues(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
    m2_bindings: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], dict[str, tuple[Any, ...]]]:
    shots, shot_issues = _stage_jsonl_records(root, group, "/storyboard/shots.jsonl")
    keyframes, keyframe_issues = _stage_jsonl_records(root, group, "/storyboard/keyframes.jsonl")
    issues = shot_issues + keyframe_issues
    shot_signatures: dict[str, tuple[Any, ...]] = {}
    if issues:
        return sorted(set(issues)), shot_signatures

    consumed: set[str] = set()
    seen_shot_ids: set[str] = set()
    for shot in shots:
        shot_id = shot.get("shot_id")
        if not isinstance(shot_id, str) or not shot_id:
            issues.append("M4b shot needs shot_id")
            continue
        if shot_id in seen_shot_ids:
            issues.append(f"duplicate M4b shot_id: {shot_id}")
        seen_shot_ids.add(shot_id)
        raw_generation_bindings = shot.get("generation_asset_bindings")
        if not isinstance(raw_generation_bindings, list):
            raw_generation_bindings = []
        bindings: list[dict[str, str | None]] = []
        binding_sources: list[tuple[dict[str, Any], dict[str, str | None]]] = []
        for raw in raw_generation_bindings:
            binding = _normalized_generation_binding(raw)
            if not isinstance(raw, dict) or binding is None:
                issues.append(f"M4b shot has invalid generation binding: {shot_id}")
                continue
            bindings.append(binding)
            binding_sources.append((raw, binding))
        if not bindings:
            issues.append(f"M4b shot needs generation_asset_bindings: {shot_id}")
            continue
        if len({binding["asset_id"] for binding in bindings}) != len(bindings):
            issues.append(f"M4b shot has duplicate asset bindings: {shot_id}")
        if len(bindings) != len(raw_generation_bindings):
            issues.append(f"M4b shot has malformed generation bindings: {shot_id}")
        shot_signatures[shot_id] = _binding_signature(bindings, m2_bindings)
        for raw, binding in binding_sources:
            asset_id = str(binding["asset_id"])
            consumed.add(asset_id)
            issues.extend(
                _binding_against_m2_issues(binding, m2_bindings, label=f"M4b shot {shot_id}")
            )
            expected = m2_bindings.get(asset_id)
            fragment_refs = raw.get("fragment_refs") if isinstance(raw, dict) else None
            actual_refs = None
            if isinstance(fragment_refs, list):
                actual_refs = _prompt_fragment_refs(
                    {"prompt_components": {"fragment_refs": fragment_refs}}
                )
            expected_refs = (
                _binding_fragment_refs(binding, expected)
                if expected is not None
                else None
            )
            if actual_refs is None or expected_refs is None or actual_refs != expected_refs:
                issues.append(
                    f"M4b shot fragment fingerprint does not match binding: {shot_id} {asset_id}"
                )

        location_assets = {
            asset_id
            for asset_id, expected in m2_bindings.items()
            if expected.get("asset_kind") == "location"
        }
        if location_assets:
            location_bindings = [
                binding
                for binding in bindings
                if str(binding["asset_id"]) in location_assets
            ]
            if len(location_bindings) != 1:
                issues.append(f"M4b shot needs exactly one location generation binding: {shot_id}")
            else:
                location = shot.get("location_binding")
                identity_id = _ref_record_id(location.get("identity_ref")) if isinstance(location, dict) else None
                view_id = _ref_record_id(location.get("view_ref")) if isinstance(location, dict) else None
                if (
                    identity_id != location_bindings[0].get("model_id")
                    or view_id != location_bindings[0].get("view_id")
                ):
                    issues.append(f"M4b shot location_binding disagrees with generation binding: {shot_id}")

    start_keyframes: dict[str, int] = {}
    seen_keyframe_ids: set[str] = set()
    for keyframe in keyframes:
        keyframe_id = keyframe.get("keyframe_id")
        if not isinstance(keyframe_id, str) or not keyframe_id:
            issues.append("M4b keyframe needs keyframe_id")
        elif keyframe_id in seen_keyframe_ids:
            issues.append(f"duplicate M4b keyframe_id: {keyframe_id}")
        else:
            seen_keyframe_ids.add(keyframe_id)
        shot_id = _ref_record_id(keyframe.get("shot_ref")) or _ref_record_id(keyframe.get("boundary_ref"))
        if shot_id not in shot_signatures:
            issues.append(f"M4b keyframe references unknown or unbound shot: {keyframe.get('keyframe_id', '<unknown>')}")
            continue
        if keyframe.get("boundary_role") == "start":
            start_keyframes[shot_id] = start_keyframes.get(shot_id, 0) + 1
        components = keyframe.get("prompt_components")
        if not isinstance(components, dict) or components.get("profile") != "keyframe":
            issues.append(f"M4b keyframe must use profile keyframe: {shot_id}")
        raw_bindings = keyframe.get("asset_bindings")
        if not isinstance(raw_bindings, list):
            raw_bindings = []
        normalized = [
            binding
            for raw in raw_bindings
            if (binding := _normalized_generation_binding(raw)) is not None
        ]
        if len(normalized) != len(raw_bindings):
            issues.append(f"M4b keyframe has malformed asset bindings: {shot_id}")
        if _binding_signature(normalized, m2_bindings) != shot_signatures[shot_id]:
            issues.append(f"M4b keyframe binding chain differs from shot: {shot_id}")
        actual_refs = _prompt_fragment_refs(keyframe)
        expected_refs = _record_expected_fragment_refs(normalized, m2_bindings)
        if actual_refs is None or expected_refs is None or actual_refs != expected_refs:
            issues.append(f"M4b keyframe fragment fingerprint differs from shot: {shot_id}")
    for shot_id in shot_signatures:
        if start_keyframes.get(shot_id, 0) != 1:
            issues.append(f"M4b shot needs exactly one start keyframe: {shot_id}")
    missing = sorted(set(m2_bindings) - consumed)
    if missing:
        issues.append("M4b shots do not consume M2 assets: " + ", ".join(missing))
    return sorted(set(issues)), shot_signatures


def _m5_asset_consumption_issues(
    root: Path,
    group: Iterable[tuple[str, dict[str, Any], list[str]]],
    shot_signatures: Mapping[str, tuple[Any, ...]],
    m2_bindings: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    motions, issues = _stage_jsonl_records(root, group, "/storyboard/motion-specs.jsonl")
    if issues:
        return issues
    covered: set[str] = set()
    seen_motion_ids: set[str] = set()
    for motion in motions:
        raw_motion_id = motion.get("motion_id")
        if not isinstance(raw_motion_id, str) or not raw_motion_id:
            issues.append("M5 motion needs motion_id")
            motion_id = "<unknown>"
        else:
            motion_id = raw_motion_id
            if motion_id in seen_motion_ids:
                issues.append(f"duplicate M5 motion_id: {motion_id}")
            seen_motion_ids.add(motion_id)
        shot_id = _ref_record_id(motion.get("shot_ref"))
        if shot_id not in shot_signatures:
            issues.append(f"M5 motion references unknown or unbound shot: {motion_id}")
            continue
        covered.add(str(shot_id))
        components = motion.get("prompt_components")
        if not isinstance(components, dict) or components.get("profile") != "motion":
            issues.append(f"M5 motion must use profile motion: {motion_id}")
        raw_bindings = motion.get("asset_bindings")
        if not isinstance(raw_bindings, list):
            raw_bindings = []
        normalized = [
            binding
            for raw in raw_bindings
            if (binding := _normalized_generation_binding(raw)) is not None
        ]
        if len(normalized) != len(raw_bindings):
            issues.append(f"M5 motion has malformed asset bindings: {motion_id}")
        if _binding_signature(normalized, m2_bindings) != shot_signatures[str(shot_id)]:
            issues.append(f"M5 motion binding chain differs from shot: {motion_id}")
        actual_refs = _prompt_fragment_refs(motion)
        expected_refs = _record_expected_fragment_refs(normalized, m2_bindings)
        if actual_refs is None or expected_refs is None or actual_refs != expected_refs:
            issues.append(f"M5 motion fragment fingerprint differs from shot: {motion_id}")
    missing = sorted(set(shot_signatures) - covered)
    if missing:
        issues.append("M5 has no motion spec for shots: " + ", ".join(missing))
    return sorted(set(issues))


def _m5_generation_clip_issues(
    root: Path, group: Iterable[tuple[str, dict[str, Any], list[str]]]
) -> list[str]:
    """Validate model-call clips without changing editorial shot identity."""

    group = list(group)
    clips, issues = _stage_jsonl_records(root, group, "/storyboard/generation-clips.jsonl")
    if issues:
        return issues
    target_paths = [path for _, _, paths in group for path in paths]
    episode = _episode_from_targets(target_paths)
    if episode is None:
        return ["M5 generation clips need one episode-scoped target"]
    prefix = next(
        "/".join(PurePosixPath(path).parts[:2])
        for path in target_paths
        if len(PurePosixPath(path).parts) >= 2
        and PurePosixPath(path).parts[1] == episode
    )
    shots_path = _project_path(root, f"{prefix}/storyboard/shots.jsonl")
    motions_path = _project_path(root, f"{prefix}/storyboard/motion-specs.jsonl")
    if not shots_path.is_file() or not motions_path.is_file():
        return ["M5 generation clips require accepted shots and motion specs"]
    checker_path = (
        Path(__file__).resolve().parents[2]
        / "short-drama-video-prompts/scripts/generation_clip_check.py"
    )
    module = _load_check_module("short_drama_generation_clip_runtime", checker_path)
    result = module.check(
        clips,
        module._load_jsonl(shots_path),
        module._load_jsonl(motions_path),
        module._load_json(root / PROJECT_FILE),
    )
    return [
        f"{finding.get('code', 'GCLIP_INVALID')}: {finding.get('message', 'invalid generation clip')}"
        for finding in result.get("findings", [])
    ]


def _episode_from_targets(target_paths: Iterable[str]) -> str | None:
    episodes: set[str] = set()
    for path in target_paths:
        parts = PurePosixPath(path).parts
        if len(parts) >= 2 and _root_role(parts[0]) == "episodes" and EPISODE_ID_RE.fullmatch(parts[1]):
            episodes.add(parts[1])
    return next(iter(episodes)) if len(episodes) == 1 else None


def _synthetic_accepted_group(
    artifact_id: str, owner: str, target_paths: Mapping[str, str]
) -> list[tuple[str, dict[str, Any], list[str]]]:
    record = {
        "owner": owner,
        "build_state": "materialized",
        "creator_acceptance": "accepted",
        "accepted_targets": dict(target_paths),
    }
    return [(artifact_id, record, sorted(target_paths))]


def _fixed_stage_acceptance_issues(
    root: Path,
    state: Mapping[str, Any],
    *,
    artifact_id: str,
    owner: str,
    target_paths: Mapping[str, str],
) -> tuple[str, list[str]] | None:
    """Validate a complete fixed-pipeline stage before creator acceptance."""

    episode = _episode_from_targets(target_paths)
    if episode is None:
        return None
    required = {
        "short-drama-assets": {
            "assets/occurrences.jsonl",
            "assets/decisions.jsonl",
            "assets/continuity.jsonl",
        },
        "short-drama-image-prompts": {
            "assets/image-prompt-specs.jsonl",
            "assets/image-prompts.md",
        },
        "short-drama-storyboard": {
            "storyboard/coverage.json",
            "storyboard/shots.jsonl",
            "storyboard/keyframes.jsonl",
            "storyboard/keyframe-prompts.md",
        },
        "short-drama-video-prompts": {
            "storyboard/motion-specs.jsonl",
            "storyboard/generation-clips.jsonl",
            "storyboard/video-prompts.md",
        },
    }
    if owner not in required:
        return None

    prefixes = [
        f"{root_name}/{episode}"
        for root_name in (CANONICAL_ROOTS["episodes"], LEGACY_ROOTS["episodes"])
    ]
    raw_artifacts = state.get("artifacts")
    effective_state = dict(state)
    effective_state["artifacts"] = _effective_lifecycle_records(
        root,
        raw_artifacts if isinstance(raw_artifacts, dict) else {},
    )
    accepted_stage = [
        item
        for item in _flow_artifacts(
            effective_state, owner=owner, prefixes=prefixes
        )
        if item[0] != artifact_id
        and item[1].get("build_state") == "materialized"
        and item[1].get("creator_acceptance") == "accepted"
    ]
    candidate_group = [
        *accepted_stage,
        *_synthetic_accepted_group(artifact_id, owner, target_paths),
    ]
    suffixes = {
        "/".join(PurePosixPath(path).parts[2:])
        for _, _, paths in candidate_group
        for path in paths
        if len(PurePosixPath(path).parts) >= 3
    }
    if not required[owner] <= suffixes:
        return None

    m2 = _flow_artifacts(
        effective_state, owner="short-drama-write", prefixes=prefixes
    )
    m2_targets: set[str] = set()
    m2_records: dict[str, dict[str, str]] = {}
    for _candidate_id, record, _paths in m2:
        if record.get("creator_acceptance") != "accepted" or record.get("build_state") != "materialized":
            continue
        targets = record.get("accepted_targets")
        if isinstance(targets, dict):
            m2_targets.update(str(path) for path in targets)
        try:
            for path, selectors in _input_record_bindings(record, "accepted_input_records").items():
                m2_records.setdefault(path, {}).update(selectors)
        except ValueError:
            continue
    m2_issues = _m2_generation_binding_issues(
        root, target_paths=m2_targets, input_records=m2_records
    )
    if m2_issues:
        return "BLK-M2-ASSET-REF", m2_issues
    m2_bindings = _m2_generation_binding_map(root, m2_targets)

    if owner == "short-drama-assets":
        screenplay_index, screenplay_issues = _m2_screenplay_index_evidence(root, m2)
        issues = screenplay_issues + _m3_asset_consumption_issues(
            root,
            candidate_group,
            m2_bindings,
            screenplay_index,
        )
        return ("BLK-M3-ASSETS", issues) if issues else None
    if owner == "short-drama-image-prompts":
        issues = _m4a_asset_consumption_issues(root, candidate_group, m2_bindings)
        return ("BLK-M4A-ASSET-CONSUME", issues) if issues else None
    if owner == "short-drama-storyboard":
        image_prompts = _flow_artifacts(
            effective_state,
            owner="short-drama-image-prompts",
            prefixes=prefixes,
        )
        observation_issues = _m4a_result_gate_issues(root, image_prompts)
        if observation_issues:
            return "BLK-M4A-RESULT-OBSERVED", observation_issues
        issues, _signatures = _m4b_asset_consumption_issues(
            root, candidate_group, m2_bindings
        )
        return ("BLK-M4B-ASSET-CONSUME", issues) if issues else None

    storyboard = _flow_artifacts(
        effective_state, owner="short-drama-storyboard", prefixes=prefixes
    )
    storyboard_issues, signatures = _m4b_asset_consumption_issues(
        root, storyboard, m2_bindings
    )
    if storyboard_issues:
        return "BLK-M4B-ASSET-CONSUME", storyboard_issues
    issues = _m5_asset_consumption_issues(
        root, candidate_group, signatures, m2_bindings
    )
    if issues:
        return "BLK-M5-ASSET-CONSUME", issues
    clip_issues = _m5_generation_clip_issues(root, candidate_group)
    return ("BLK-M5-GENERATION-CLIP", clip_issues) if clip_issues else None


def _episode_flow_report(
    root: Path, state: Mapping[str, Any], episode: str
) -> dict[str, Any]:
    """Per-episode milestone state: which M2..M7 stages are done/used."""

    episode_prefixes = [
        f"{CANONICAL_ROOTS['episodes']}/{episode}",
        f"{LEGACY_ROOTS['episodes']}/{episode}",
    ]
    m2 = _flow_artifacts(state, owner="short-drama-write", prefixes=episode_prefixes)
    m3 = _flow_artifacts(state, owner="short-drama-assets", prefixes=episode_prefixes)
    m4a = _flow_artifacts(state, owner="short-drama-image-prompts", prefixes=episode_prefixes)
    m4b = _flow_artifacts(state, owner="short-drama-storyboard", prefixes=episode_prefixes)
    m5 = _flow_artifacts(state, owner="short-drama-video-prompts", prefixes=episode_prefixes)
    used = [m2, m3, m4a, m4b, m5]

    required = {
        "m2": {"episode-card.json", "beats.jsonl", "screenplay.md", "screenplay-index.jsonl"},
        "m3": {"assets/occurrences.jsonl", "assets/decisions.jsonl", "assets/continuity.jsonl"},
        "m4a": {"assets/image-prompt-specs.jsonl", "assets/image-prompts.md"},
        "m4b": {"storyboard/coverage.json", "storyboard/shots.jsonl", "storyboard/keyframes.jsonl", "storyboard/keyframe-prompts.md"},
        "m5": {
            "storyboard/motion-specs.jsonl",
            "storyboard/generation-clips.jsonl",
            "storyboard/video-prompts.md",
        },
    }

    def accepted_required(
        group: list[tuple[str, dict[str, Any], list[str]]], names: set[str]
    ) -> bool:
        accepted_paths = {
            "/".join(PurePosixPath(path).parts[2:])
            for _, record, paths in group
            if record.get("build_state") == "materialized"
            and record.get("creator_acceptance") == "accepted"
            for path in paths
            if len(PurePosixPath(path).parts) >= 3
        }
        return names <= accepted_paths

    def reviewed(groups: Iterable[list[tuple[str, dict[str, Any], list[str]]]]) -> bool:
        for group in groups:
            if group and any(
                record.get("independent_review")
                not in {"approve", "approve_with_notes"}
                for _, record, _ in group
            ):
                return False
        return True

    def delivered(groups: Iterable[list[tuple[str, dict[str, Any], list[str]]]]) -> bool:
        for group in groups:
            if group and any(
                record.get("delivery_gate") != "delivered"
                for _, record, _ in group
            ):
                return False
        return True

    m2_done = accepted_required(m2, required["m2"])
    m2_generation_inputs: set[str] = set()
    m2_generation_records: dict[str, dict[str, str]] = {}
    m2_target_paths: set[str] = set()
    for _, record, _ in m2:
        accepted_inputs = record.get("accepted_inputs")
        if isinstance(accepted_inputs, dict):
            m2_generation_inputs.update(
                path for path in accepted_inputs if path.startswith("设定集/generation/")
            )
        try:
            for path, selectors in _input_record_bindings(record, "accepted_input_records").items():
                m2_generation_records.setdefault(path, {}).update(selectors)
        except ValueError:
            pass
        targets = record.get("accepted_targets")
        if isinstance(targets, dict):
            m2_target_paths.update(targets)
    m2_asset_ref_issues = _m2_generation_binding_issues(
        root,
        target_paths=m2_target_paths,
        input_records=m2_generation_records,
    ) if m2_done else ["M2 screenplay artifact is incomplete"]
    m2_asset_refs = not m2_asset_ref_issues
    m2_bindings = _m2_generation_binding_map(root, m2_target_paths) if m2_asset_refs else {}
    m3_new_assets: list[str] = []
    for _, record, paths in m3:
        if record.get("creator_acceptance") != "accepted":
            continue
        for relative in paths:
            if PurePosixPath(relative).name.casefold() != "decisions.jsonl":
                continue
            try:
                m3_new_assets.extend(
                    str(item.get("decision_id") or item.get("proposed_binding", {}).get("identity_id") or "<unknown>")
                    for item in _jsonl_records(_project_path(root, relative).read_bytes(), relative)
                    if item.get("decision_kind") == "new_asset"
                )
            except (OSError, UnicodeError, ValueError):
                m3_new_assets.append("<invalid-decisions.jsonl>")
    screenplay_index, screenplay_index_issues = _m2_screenplay_index_evidence(root, m2)
    m3_consumption_issues = (
        screenplay_index_issues
        + _m3_asset_consumption_issues(
            root,
            m3,
            m2_bindings,
            screenplay_index,
        )
        if m2_asset_refs and accepted_required(m3, required["m3"])
        else ["M3 assets are incomplete"]
    )
    m3_done = accepted_required(m3, required["m3"]) and not m3_new_assets and not m3_consumption_issues
    # 主线必须逐级：M4a / M4b / M5 全部必经，未产出即未完成。
    m4a_consumption_issues = (
        _m4a_asset_consumption_issues(root, m4a, m2_bindings)
        if m3_done and accepted_required(m4a, required["m4a"])
        else ["M4a image prompt assets are incomplete"]
    )
    m4a_observation_issues = (
        _m4a_result_gate_issues(root, m4a)
        if (
            accepted_required(m4a, required["m4a"])
            and not m4a_consumption_issues
        )
        else []
    )
    m4a_done = (
        accepted_required(m4a, required["m4a"])
        and not m4a_consumption_issues
        and not m4a_observation_issues
    )
    m4b_consumption_issues: list[str]
    shot_signatures: dict[str, tuple[Any, ...]]
    if m4a_done and accepted_required(m4b, required["m4b"]):
        m4b_consumption_issues, shot_signatures = _m4b_asset_consumption_issues(root, m4b, m2_bindings)
    else:
        m4b_consumption_issues = ["M4b storyboard assets are incomplete"]
        shot_signatures = {}
    m4b_done = accepted_required(m4b, required["m4b"]) and not m4b_consumption_issues
    m5_consumption_issues = (
        _m5_asset_consumption_issues(root, m5, shot_signatures, m2_bindings)
        if m4b_done and accepted_required(m5, required["m5"])
        else ["M5 motion asset bindings are incomplete"]
    )
    m5_clip_issues: list[str] = []
    if m4b_done and accepted_required(m5, required["m5"]):
        m5_clip_issues = _m5_generation_clip_issues(root, m5)
    m5_done = (
        accepted_required(m5, required["m5"])
        and not m5_consumption_issues
        and not m5_clip_issues
    )
    m6_done = reviewed(used)
    m7_done = delivered(used)
    return {
        "episode": episode,
        "m2_done": m2_done,
        "m2_asset_refs": m2_asset_refs,
        "m2_asset_ref_issues": m2_asset_ref_issues,
        "m3_done": m3_done,
        "m3_new_assets": sorted(set(m3_new_assets)),
        "m3_consumption_issues": m3_consumption_issues,
        "m4a_done": m4a_done,
        "m4a_consumption_issues": m4a_consumption_issues,
        "m4a_observation_issues": m4a_observation_issues,
        "m4b_done": m4b_done,
        "m4b_consumption_issues": m4b_consumption_issues,
        "m5_done": m5_done,
        "m5_consumption_issues": m5_consumption_issues,
        "m5_clip_issues": m5_clip_issues,
        "m6_done": m6_done,
        "m7_done": m7_done,
        "artifacts": {
            "write": len(m2),
            "assets": len(m3),
            "image_prompts": len(m4a),
            "storyboard": len(m4b),
            "video_prompts": len(m5),
        },
    }


def _episode_asset_consumption_summary(
    root: Path, state: Mapping[str, Any], episode: str
) -> dict[str, Any]:
    """Summarize declared versus actual generation asset use for delivery."""

    prefixes = [
        f"{root_name}/{episode}"
        for root_name in (CANONICAL_ROOTS["episodes"], LEGACY_ROOTS["episodes"])
    ]
    groups = {
        "m2": _flow_artifacts(state, owner="short-drama-write", prefixes=prefixes),
        "m3": _flow_artifacts(state, owner="short-drama-assets", prefixes=prefixes),
        "m4a": _flow_artifacts(state, owner="short-drama-image-prompts", prefixes=prefixes),
        "m4b": _flow_artifacts(state, owner="short-drama-storyboard", prefixes=prefixes),
        "m5": _flow_artifacts(state, owner="short-drama-video-prompts", prefixes=prefixes),
    }
    m2_targets: set[str] = set()
    for _artifact_id, record, _paths in groups["m2"]:
        if record.get("creator_acceptance") != "accepted" or record.get("build_state") != "materialized":
            continue
        targets = record.get("accepted_targets")
        if isinstance(targets, dict):
            m2_targets.update(str(path) for path in targets)
    m2_binding_map = _m2_generation_binding_map(root, m2_targets)
    declared = set(m2_binding_map)

    stages: dict[str, set[str]] = {
        "m2_declared": set(declared),
        "m3_reconciled": set(),
        "m4a_prompts": set(),
        "m4b_shots": set(),
        "m5_motions": set(),
    }

    def serialize_signature(signature: tuple[Any, ...]) -> list[dict[str, Any]]:
        return [
            {
                "asset_id": item[0],
                "model_id": item[1],
                "view_id": item[2],
                "variant_id": item[3],
                "fragment_refs": [
                    {"fragment_id": fragment_id, "hash": digest}
                    for fragment_id, digest in (item[4] or ())
                ],
            }
            for item in signature
        ]

    decisions, _ = _stage_jsonl_records(root, groups["m3"], "/assets/decisions.jsonl")
    m3_binding_chains: dict[str, dict[str, Any]] = {}
    binding_chain_differences: list[dict[str, str]] = []
    for decision in decisions:
        if decision.get("decision_kind") != "reuse":
            continue
        proposed = decision.get("proposed_binding")
        identity_id = proposed.get("identity_id") if isinstance(proposed, dict) else None
        if isinstance(identity_id, str) and identity_id:
            stages["m3_reconciled"].add(identity_id)
            decision_id = str(decision.get("decision_id") or "<unknown>")
            model_id = proposed.get("generation_model_id")
            variant_id = proposed.get("generation_variant_id")
            m3_binding_chains[decision_id] = {
                "asset_id": identity_id,
                "model_id": model_id,
                "variant_id": variant_id,
                "occurrence_ids": [
                    record_id
                    for reference in decision.get("occurrence_refs", [])
                    if (record_id := _ref_record_id(reference)) is not None
                ],
            }
            expected = m2_binding_map.get(identity_id)
            if (
                expected is None
                or model_id != expected.get("model_id")
                or (
                    variant_id is not None
                    and variant_id not in expected.get("variant_ids", set())
                )
            ):
                binding_chain_differences.append(
                    {
                        "stage": "m3",
                        "record_id": decision_id,
                        "reason": "resolved binding differs from M2",
                    }
                )
    prompts, _ = _stage_jsonl_records(
        root, groups["m4a"], "/assets/image-prompt-specs.jsonl"
    )
    m4a_binding_chains: dict[str, dict[str, Any]] = {}
    for number, record in enumerate(prompts, 1):
        bindings = record.get("asset_bindings")
        if isinstance(bindings, list):
            normalized = [
                binding
                for raw in bindings
                if (binding := _normalized_generation_binding(raw)) is not None
            ]
            stages["m4a_prompts"].update(str(binding["asset_id"]) for binding in normalized)
            record_id = str(record.get("spec_id") or f"asset-board-{number}")
            actual_refs = _prompt_fragment_refs(record)
            sheet = record.get("sheet_profile")
            sheet_profile = sheet.get("name") if isinstance(sheet, dict) else None
            expected_refs = _record_expected_fragment_refs(
                normalized,
                m2_binding_map,
                sheet_profile=(
                    str(sheet_profile)
                    if sheet_profile in SCENE_SHEET_PROFILES
                    else None
                ),
            )
            m4a_binding_chains[record_id] = {
                "bindings": serialize_signature(
                    _binding_signature(normalized, m2_binding_map)
                ),
                "sheet_profile": sheet_profile,
                "fragment_refs": [
                    {"fragment_id": fragment_id, "hash": digest}
                    for fragment_id, digest in (actual_refs or ())
                ],
            }
            if (
                len(normalized) != len(bindings)
                or actual_refs is None
                or expected_refs is None
                or actual_refs != expected_refs
            ):
                binding_chain_differences.append(
                    {
                        "stage": "m4a",
                        "record_id": record_id,
                        "reason": "asset board binding or fragment fingerprint differs from M2",
                    }
                )
    shots, _ = _stage_jsonl_records(root, groups["m4b"], "/storyboard/shots.jsonl")
    shot_binding_chains: dict[str, list[dict[str, Any]]] = {}

    for shot in shots:
        bindings = _shot_generation_bindings(shot)
        stages["m4b_shots"].update(str(binding["asset_id"]) for binding in bindings)
        shot_id = shot.get("shot_id")
        if isinstance(shot_id, str) and shot_id:
            shot_binding_chains[shot_id] = serialize_signature(
                _binding_signature(bindings, m2_binding_map)
            )
            raw_bindings = shot.get("generation_asset_bindings")
            if not isinstance(raw_bindings, list) or len(raw_bindings) != len(bindings):
                binding_chain_differences.append(
                    {"stage": "m4b-shot", "record_id": shot_id, "reason": "malformed bindings"}
                )
            else:
                for raw, binding in zip(raw_bindings, bindings):
                    expected = m2_binding_map.get(str(binding["asset_id"]))
                    actual_refs = None
                    if isinstance(raw, dict) and isinstance(raw.get("fragment_refs"), list):
                        actual_refs = _prompt_fragment_refs(
                            {"prompt_components": {"fragment_refs": raw["fragment_refs"]}}
                        )
                    if (
                        expected is None
                        or actual_refs is None
                        or actual_refs != _binding_fragment_refs(binding, expected)
                    ):
                        binding_chain_differences.append(
                            {
                                "stage": "m4b-shot",
                                "record_id": shot_id,
                                "reason": f"fragment fingerprint differs for {binding['asset_id']}",
                            }
                        )
    keyframes, _ = _stage_jsonl_records(
        root, groups["m4b"], "/storyboard/keyframes.jsonl"
    )
    keyframe_binding_chains: dict[str, dict[str, Any]] = {}
    for number, keyframe in enumerate(keyframes, 1):
        keyframe_id = str(keyframe.get("keyframe_id") or f"keyframe-{number}")
        shot_id = _ref_record_id(keyframe.get("shot_ref")) or _ref_record_id(keyframe.get("boundary_ref"))
        raw_bindings = keyframe.get("asset_bindings")
        normalized = [
            binding
            for raw in raw_bindings or []
            if (binding := _normalized_generation_binding(raw)) is not None
        ] if isinstance(raw_bindings, list) else []
        serialized = serialize_signature(_binding_signature(normalized, m2_binding_map))
        actual_refs = _prompt_fragment_refs(keyframe)
        expected_refs = _record_expected_fragment_refs(normalized, m2_binding_map)
        keyframe_binding_chains[keyframe_id] = {
            "shot_id": shot_id,
            "bindings": serialized,
            "fragment_refs": [
                {"fragment_id": fragment_id, "hash": digest}
                for fragment_id, digest in (actual_refs or ())
            ],
        }
        if (
            not isinstance(raw_bindings, list)
            or len(normalized) != len(raw_bindings)
            or not isinstance(shot_id, str)
            or shot_binding_chains.get(shot_id) != serialized
            or actual_refs is None
            or expected_refs is None
            or actual_refs != expected_refs
        ):
            binding_chain_differences.append(
                {
                    "stage": "m4b-keyframe",
                    "record_id": keyframe_id,
                    "reason": "binding chain or fragment fingerprint differs from shot",
                }
            )
    motions, _ = _stage_jsonl_records(root, groups["m5"], "/storyboard/motion-specs.jsonl")
    motion_binding_chains: dict[str, dict[str, Any]] = {}
    for motion in motions:
        bindings = motion.get("asset_bindings")
        if isinstance(bindings, list):
            normalized = [
                binding
                for raw in bindings
                if (binding := _normalized_generation_binding(raw)) is not None
            ]
            stages["m5_motions"].update(str(binding["asset_id"]) for binding in normalized)
            motion_id = motion.get("motion_id")
            shot_id = _ref_record_id(motion.get("shot_ref"))
            if isinstance(motion_id, str) and motion_id:
                serialized = serialize_signature(
                    _binding_signature(normalized, m2_binding_map)
                )
                motion_binding_chains[motion_id] = {
                    "shot_id": shot_id,
                    "bindings": serialized,
                    "fragment_refs": [
                        {"fragment_id": fragment_id, "hash": digest}
                        for fragment_id, digest in (_prompt_fragment_refs(motion) or ())
                    ],
                }
                actual_refs = _prompt_fragment_refs(motion)
                expected_refs = _record_expected_fragment_refs(normalized, m2_binding_map)
                if (
                    not isinstance(shot_id, str)
                    or shot_binding_chains.get(shot_id) != serialized
                    or actual_refs is None
                    or expected_refs is None
                    or actual_refs != expected_refs
                ):
                    binding_chain_differences.append(
                        {
                            "stage": "m5-motion",
                            "record_id": motion_id,
                            "reason": f"binding chain or fragment fingerprint differs from shot {shot_id or '<missing>'}",
                        }
                    )

    clips, clip_record_issues = _stage_jsonl_records(
        root, groups["m5"], "/storyboard/generation-clips.jsonl"
    )
    generation_clip_chains: dict[str, dict[str, Any]] = {}
    for issue in clip_record_issues:
        binding_chain_differences.append(
            {"stage": "m5-generation-clip", "record_id": "<file>", "reason": issue}
        )
    for number, clip in enumerate(clips, 1):
        clip_id = str(clip.get("clip_id") or f"generation-clip-{number}")
        shot_id = _ref_record_id(clip.get("shot_ref"))
        motion_id = _ref_record_id(clip.get("motion_ref"))
        handoff = clip.get("handoff")
        generation_clip_chains[clip_id] = {
            "shot_id": shot_id,
            "motion_id": motion_id,
            "order": clip.get("order"),
            "source_window": clip.get("source_window"),
            "duration_seconds": clip.get("duration_seconds"),
            "execution_mode": clip.get("execution_mode"),
            "start_source": clip.get("start_source"),
            "from_clip_id": (
                handoff.get("from_clip_id") if isinstance(handoff, dict) else None
            ),
            "planned_boundary": (
                handoff.get("planned_boundary") if isinstance(handoff, dict) else None
            ),
            "observation_bound": bool(
                isinstance(handoff, dict) and handoff.get("observation_ref")
            ),
        }
        motion_chain = motion_binding_chains.get(str(motion_id))
        if (
            not isinstance(shot_id, str)
            or not isinstance(motion_id, str)
            or motion_chain is None
            or motion_chain.get("shot_id") != shot_id
        ):
            binding_chain_differences.append(
                {
                    "stage": "m5-generation-clip",
                    "record_id": clip_id,
                    "reason": "clip does not resolve through motion to the same shot",
                }
            )

    generation_clip_issues = _m5_generation_clip_issues(root, groups["m5"])
    for issue in generation_clip_issues:
        binding_chain_differences.append(
            {
                "stage": "m5-generation-clip",
                "record_id": "<coverage>",
                "reason": issue,
            }
        )

    container_chains: dict[str, dict[str, Any]] = {}
    container_relative, container_path_issues = _accepted_stage_file(
        groups["m5"], "/storyboard/delivery-containers.jsonl"
    )
    has_container_target = any(
        str(PurePosixPath(path)).casefold().endswith(
            "/storyboard/delivery-containers.jsonl"
        )
        for _, _, paths in groups["m5"]
        for path in paths
    )
    if container_relative is not None:
        try:
            containers = _jsonl_records(
                _project_path(root, container_relative).read_bytes(), container_relative
            )
        except (OSError, UnicodeError, ValueError) as error:
            containers = []
            container_path_issues = [f"invalid accepted delivery containers: {error}"]
        for number, container in enumerate(containers, 1):
            container_id = str(container.get("container_id") or f"container-{number}")
            members = container.get("members")
            container_chains[container_id] = {
                "order": container.get("order"),
                "container_duration": container.get("container_duration"),
                "member_shot_ids": [
                    _ref_record_id(member.get("shot_ref"))
                    for member in members
                    if isinstance(member, dict)
                ]
                if isinstance(members, list)
                else [],
            }
    elif has_container_target:
        for issue in container_path_issues:
            binding_chain_differences.append(
                {
                    "stage": "m5-delivery-container",
                    "record_id": "<file>",
                    "reason": issue,
                }
            )

    deltas: dict[str, dict[str, list[str]]] = {}
    for stage, assets in stages.items():
        if stage == "m2_declared":
            continue
        deltas[stage] = {
            "missing_from_m2_declared": sorted(declared - assets),
            "not_declared_by_m2": sorted(assets - declared),
        }
    status = "pass" if declared and generation_clip_chains and not binding_chain_differences and all(
        not detail["missing_from_m2_declared"] and not detail["not_declared_by_m2"]
        for detail in deltas.values()
    ) else "incomplete"
    return {
        "status": status,
        "stages": {stage: sorted(assets) for stage, assets in stages.items()},
        "deltas": deltas,
        "binding_chains": {
            "m3_decisions": m3_binding_chains,
            "m4a_asset_boards": m4a_binding_chains,
            "m4b_shots": shot_binding_chains,
            "m4b_keyframes": keyframe_binding_chains,
            "m5_motions": motion_binding_chains,
            "m5_generation_clips": generation_clip_chains,
            "m5_delivery_containers": container_chains,
        },
        "binding_chain_differences": binding_chain_differences,
    }


def _generation_baseline_status(root: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the project-level M1.5a/M1.5b gate from live files and state."""

    required_a = {
        "设定集/generation/asset-scope.jsonl",
        "设定集/generation/asset-models.jsonl",
        "设定集/generation/spatial-models.jsonl",
        "设定集/generation/variant-models.jsonl",
        "设定集/generation/view-contracts.jsonl",
        "设定集/generation/asset-baseline.md",
    }
    required_b = {
        "设定集/generation/canonical-fragments.jsonl",
        "设定集/generation/canonical-prompt-library.md",
    }
    effective = _effective_lifecycle_records(
        root,
        state.get("artifacts", {}) if isinstance(state.get("artifacts"), dict) else {},
    )

    def accepted(paths: set[str], owner: str) -> bool:
        for relative in paths:
            matches: list[dict[str, Any]] = []
            for candidate in effective.values():
                if not isinstance(candidate, dict) or candidate.get("owner") != owner:
                    continue
                targets = candidate.get("accepted_targets")
                if isinstance(targets, dict) and relative in targets:
                    matches.append(candidate)
            if len(matches) != 1:
                return False
            record = matches[0]
            if (
                record.get("build_state") != "materialized"
                or record.get("creator_acceptance") != "accepted"
            ):
                return False
        return True

    result = {
        "m15a_paths": sorted(required_a),
        "m15b_paths": sorted(required_b),
        "m15a_accepted": accepted(required_a, "short-drama-assets"),
        "m15b_accepted": accepted(required_b, "short-drama-image-prompts"),
        "validation": None,
    }
    try:
        checker_path = Path(__file__).resolve().parents[2] / "short-drama-assets" / "scripts" / "asset_baseline_check.py"
        spec = importlib.util.spec_from_file_location("asset_baseline_check_runtime", checker_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load asset baseline checker")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
        prompt_language = _effective_prompt_language(project)
        result["validation"] = module.check(root / "设定集/generation", prompt_language=prompt_language)
    except (OSError, UnicodeError, ValueError, ImportError, AttributeError) as error:
        result["validation"] = {"status": "error", "error": str(error)}
    result["m15a_ready"] = bool(result["m15a_accepted"] and result["validation"] and result["validation"].get("m15a", {}).get("status") == "pass")
    result["m15b_ready"] = bool(result["m15b_accepted"] and result["validation"] and result["validation"].get("m15b", {}).get("status") == "pass")
    return result


def upgrade_project_flow(path: Path) -> dict[str, Any]:
    """Upgrade an existing project to pipeline 2.0 after M1.5 is complete."""

    root = find_project(path)
    project = _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8"))
    state = _read_state(root)
    baseline = _generation_baseline_status(root, state)
    if not baseline["m15a_ready"] or not baseline["m15b_ready"]:
        raise ValueError("cannot upgrade flow before accepted M1.5a and M1.5b baseline")
    flow = dict(PRODUCTION_FLOW_DEFAULTS)
    existing = project.get("production_flow")
    if isinstance(existing, dict):
        flow.update({key: existing[key] for key in PRODUCTION_FLOW_DEFAULTS if key in existing})
    flow["pipeline_version"] = PIPELINE_VERSION
    project["production_flow"] = flow
    project["suite_version"] = SUITE_VERSION
    project["contract_version"] = CONTRACT_VERSION
    atomic_json(root / PROJECT_FILE, project)
    return {"project_root": str(root), "pipeline_version": PIPELINE_VERSION, "status": "upgraded"}


def production_flow_status(
    path: Path, *, episode: str | None = None
) -> dict[str, Any]:
    """Report the fixed M0..M1.5a..M7 production flow position and blockers.

    Gates are strict by default: a blocker is reported for every missing entry
    or exit condition of the current milestone. The report is derived from
    state.json's five lifecycle axes and the artifact pointers, so "where are
    we and what is next" is a deterministic tool output, not model memory.
    """

    root = find_project(path)
    flow = _effective_production_flow(root)
    state = _read_state(root)
    raw_artifacts = state.get("artifacts")
    state["artifacts"] = _effective_lifecycle_records(
        root, raw_artifacts if isinstance(raw_artifacts, dict) else {}
    )
    form_ok, form_issues = _form_status(root)

    completed: list[str] = []
    blockers: list[dict[str, str]] = []
    current: dict[str, Any] = {"milestone": None, "episode": None, "next_action": None}

    if not form_ok:
        blockers.extend(
            {"code": "BLK-M0-FORM", "milestone": "M0", "message": issue}
            for issue in form_issues
        )
        current.update(
            {
                "milestone": "M0",
                "next_action": (
                    "定制作形态：接受 short-drama.json#/creator_authority 的 "
                    "visual_direction 与 production_profile（形态卡见本技能路由）"
                ),
            }
        )
    else:
        completed.append("M0")

    development_prefixes = [CANONICAL_ROOTS["development"], LEGACY_ROOTS["development"]]
    develop = _flow_artifacts(state, owner="short-drama-develop", prefixes=development_prefixes)
    required_m1 = {"creative-brief.md", "story-engine.md", "episode-map.jsonl"}
    accepted_m1_paths = {
        "/".join(PurePosixPath(path).parts[1:])
        for _, record, paths in develop
        if record.get("build_state") == "materialized"
        and record.get("creator_acceptance") == "accepted"
        for path in paths
        if len(PurePosixPath(path).parts) >= 2
    }
    m1_ok = required_m1 <= accepted_m1_paths
    missing_m1 = sorted(required_m1 - accepted_m1_paths)
    m1_skipped = flow["allow_script_first"] and not develop
    if current["milestone"] is None and not m1_ok and not m1_skipped:
        if not develop:
            blockers.append(
                {
                    "code": "BLK-M1-NONE",
                    "milestone": "M1",
                    "message": "无已接受的开发产物（creative-brief / story-engine / episode-map）",
                }
            )
        else:
            blockers.append(
                {
                    "code": "BLK-M1-PENDING",
                    "milestone": "M1",
                    "message": "开发阶段缺少已接受的必需产物：" + ", ".join(missing_m1),
                }
            )
        current.update(
            {
                "milestone": "M1",
                "next_action": (
                    "产出并接受开发产物：creative-brief.md、story-engine.md、"
                    "episode-map.jsonl（$short-drama-develop）"
                ),
            }
        )
    elif current["milestone"] is None:
        if m1_skipped:
            completed.append("M1（script-first 跳过）")
        else:
            completed.append("M1")

    baseline = _generation_baseline_status(root, state)
    if current["milestone"] is None and not baseline["m15a_ready"]:
        blockers.append(
            {
                "code": "BLK-M15-MODEL" if baseline.get("validation", {}).get("m15a", {}).get("status") != "pass" else "BLK-M15-SCOPE",
                "milestone": "M1.5a",
                "message": "项目级生成资产模型未完成：接受 asset-scope、模型、空间拓扑、变体、视图契约与 asset-baseline",
            }
        )
        current.update(
            {
                "milestone": "M1.5a",
                "next_action": "建立并接受设定集/generation 的资产分级与生成模型（$short-drama-assets）",
            }
        )
    elif current["milestone"] is None:
        completed.append("M1.5a")

    if current["milestone"] is None and not baseline["m15b_ready"]:
        blockers.append(
            {
                "code": "BLK-M15-FRAGMENT",
                "milestone": "M1.5b",
                "message": "项目级标准提示片段未完成、未接受或与 prompt_language/模型哈希不一致",
            }
        )
        current.update(
            {
                "milestone": "M1.5b",
                "next_action": "编译并接受设定集/generation/canonical-fragments 与提示片段库（$short-drama-image-prompts）",
            }
        )
    elif current["milestone"] is None:
        completed.append("M1.5b")

    if current["milestone"] is None and flow.get("pipeline_version") != PIPELINE_VERSION:
        blockers.append(
            {
                "code": "BLK-FLOW-UPGRADE",
                "milestone": "M1.5b",
                "message": f"项目仍使用 pipeline {flow.get('pipeline_version')}；M1.5 已就绪后必须执行 upgrade-flow",
            }
        )
        current.update(
            {
                "milestone": "M1.5b",
                "next_action": f"运行 project_tool.py upgrade-flow <project> 切换到 pipeline {PIPELINE_VERSION}",
            }
        )

    episodes = [episode] if episode else _episode_dirs(root)
    if not episodes and current["milestone"] is None:
        episodes = ["EP001"]

    episode_reports: dict[str, dict[str, Any]] = {}
    for ep in episodes:
        report = _episode_flow_report(root, state, ep)
        episode_reports[ep] = {"current": "pending"}
        estimate = _episode_duration_estimate(root, state, ep)
        if estimate is not None:
            episode_reports[ep]["duration_estimate"] = estimate
        if current["milestone"] is not None:
            episode_reports[ep]["current"] = "pending"
            continue
        if not report["m2_done"]:
            blockers.append(
                {
                    "code": "BLK-M2-SCRIPT",
                    "milestone": "M2",
                    "message": f"{ep} 尚无已接受剧本产物（episode-card/beats/screenplay + 索引）",
                }
            )
            current.update(
                {
                    "milestone": "M2",
                    "episode": ep,
                    "next_action": (
                        f"写 {ep} 剧本：单集卡、节拍、screenplay 与索引，"
                        "发布并接受（$short-drama-write）"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M2"
            continue
        if not report["m2_asset_refs"]:
            blockers.append(
                {
                    "code": "BLK-M2-ASSET-REF",
                    "milestone": "M2",
                    "message": f"{ep} 剧本未记录实际消费的资产范围、模型/空间、视图与标准片段输入",
                }
            )
            current.update(
                {
                    "milestone": "M2",
                    "episode": ep,
                    "next_action": f"重新发布 {ep} 剧本并用 --input/记录级 refs 绑定设定集/generation 中实际消费的记录",
                }
            )
            episode_reports[ep]["current"] = "M2"
            continue
        if not report["m3_done"]:
            if not form_ok:
                blockers.append(
                    {
                        "code": "BLK-M3-FORM",
                        "milestone": "M3",
                        "message": f"{ep} 进入资产拆解前必须先接受制作形态",
                    }
                )
            blockers.append(
                {
                    "code": "BLK-M15-SCOPE" if report.get("m3_new_assets") else "BLK-M3-ASSETS",
                    "milestone": "M3",
                    "message": (
                        f"{ep} 的 M3 含 new_asset，必须回到 M1.5a/M1.5b 建立基线并重新绑定 M2："
                        + ", ".join(report["m3_new_assets"])
                        if report.get("m3_new_assets")
                        else f"{ep} 的资产拆解或消费对账未完成："
                        + "; ".join(report.get("m3_consumption_issues", []))
                    ),
                }
            )
            current.update(
                {
                    "milestone": "M3",
                    "episode": ep,
                    "next_action": (
                        f"拆 {ep} 资产：occurrence → decision → 设定集/连续性，"
                        "发布并接受（$short-drama-assets）"
                        if not report.get("m3_new_assets")
                        else f"先为 {ep} 的 new_asset 补齐 M1.5a/M1.5b，再重新绑定并接受剧本"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M3"
            continue
        if not report["m4a_done"]:
            observation_issues = report.get("m4a_observation_issues", [])
            blockers.append(
                {
                    "code": (
                        "BLK-M4A-RESULT-OBSERVED"
                        if observation_issues
                        else "BLK-M4A-ASSET-CONSUME"
                    ),
                    "milestone": "M4a",
                    "message": (
                        f"{ep} 外部图片结果尚未形成精确授权观察："
                        + "; ".join(observation_issues)
                        if observation_issues
                        else f"{ep} 图片提示词未完整消费 M2/M3 资产："
                        + "; ".join(report.get("m4a_consumption_issues", []))
                    ),
                }
            )
            current.update(
                {
                    "milestone": "M4a",
                    "episode": ep,
                    "next_action": (
                        f"在外部生成 {ep} 资产图，并由授权观察者写入 "
                        f"{PRODUCTION_OBSERVATIONS_FILE}"
                        if observation_issues
                        else f"写 {ep} 图片提示词并接受（$short-drama-image-prompts）"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M4a"
            continue
        if not report["m4b_done"]:
            blockers.append(
                {
                    "code": "BLK-M4B-ASSET-CONSUME",
                    "milestone": "M4b",
                    "message": (
                        f"{ep} 分镜/关键帧绑定链未闭合："
                        + "; ".join(report.get("m4b_consumption_issues", []))
                    ),
                }
            )
            current.update(
                {
                    "milestone": "M4b",
                    "episode": ep,
                    "next_action": (
                        f"做 {ep} 分镜：coverage/shots/keyframes 并接受"
                        "（$short-drama-storyboard）"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M4b"
            continue
        if not report["m5_done"]:
            clip_issues = report.get("m5_clip_issues", [])
            blockers.append(
                {
                    "code": (
                        "BLK-M5-GENERATION-CLIP"
                        if clip_issues
                        else "BLK-M5-ASSET-CONSUME"
                    ),
                    "milestone": "M5",
                    "message": (
                        f"{ep} generation clip 未满足模型调用上限或连续覆盖："
                        + "; ".join(clip_issues)
                        if clip_issues
                        else f"{ep} 视频提示词未复用完整镜头资产链："
                        + "; ".join(report.get("m5_consumption_issues", []))
                    ),
                }
            )
            current.update(
                {
                    "milestone": "M5",
                    "episode": ep,
                    "next_action": (
                        f"写 {ep} 视频提示词并接受（$short-drama-video-prompts）"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M5"
            continue
        if not report["m6_done"]:
            blockers.append(
                {
                    "code": "BLK-M6-REVIEW",
                    "milestone": "M6",
                    "message": f"{ep} 存在未获审查通过的产物",
                }
            )
            current.update(
                {
                    "milestone": "M6",
                    "episode": ep,
                    "next_action": (
                        f"对 {ep} 做审查：类型基准与交付终审 L1 fresh，例行首审 "
                        "L1.5 cold_read，修订复查 L2 delta_verify（$short-drama-review）"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M6"
            continue
        if not report["m7_done"]:
            delivery_surface = (
                (_json_loads((root / PROJECT_FILE).read_text(encoding="utf-8")))
                .get("creator_authority", {})
                .get("delivery_surface")
            )
            if not isinstance(delivery_surface, dict) or delivery_surface.get("status") != "accepted":
                blockers.append(
                    {
                        "code": "BLK-M7-SURFACE",
                        "milestone": "M7",
                        "message": f"{ep} 交付前需声明并接受 delivery_surface（播放面避让核验）",
                    }
                )
            blockers.append(
                {
                    "code": "BLK-M7-DELIVERY",
                    "milestone": "M7",
                    "message": f"{ep} 交付门未就绪（未 package 或产物未标记 delivered）",
                }
            )
            current.update(
                {
                    "milestone": "M7",
                    "episode": ep,
                    "next_action": (
                        f"交付 {ep}：L1 fresh 终审 → package → verify"
                    ),
                }
            )
            episode_reports[ep]["current"] = "M7"
            continue
        episode_reports[ep]["current"] = "complete"
        completed.append(f"{ep}（M2–M7 完成）")

    if current["milestone"] is None:
        current.update(
            {
                "milestone": "complete",
                "next_action": "全部里程碑完成；如需新增剧集继续 M2–M7 循环（资产基线保持不变，仅新增变体）",
            }
        )
    return {
        "pipeline_version": flow["pipeline_version"],
        "enforcement": flow["enforcement"],
        "allow_script_first": flow["allow_script_first"],
        "image_result_gate": flow["image_result_gate"],
        "current_milestone": current["milestone"],
        "episode": current["episode"],
        "next_action": current["next_action"],
        "blockers": blockers,
        "completed": completed,
        "episodes": episode_reports,
        "fresh_baselines": _fresh_baselines(
            _effective_lifecycle_records(
                root,
                state.get("artifacts", {})
                if isinstance(state.get("artifacts"), dict)
                else {},
            )
        ),
    }


def _task_stage(value: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    stage = TASK_STAGE_ALIASES.get(normalized)
    if stage is None:
        raise ValueError(
            "stage must be one of: " + ", ".join(sorted(TASK_STAGE_SPECS))
        )
    return stage


def _task_output_target(
    roots: Mapping[str, str], kind: str, suffix: str, episode: str | None
) -> str:
    label = episode or "project"
    rendered = suffix.format(episode=label)
    if kind == "development":
        return f"{roots['development']}/{rendered}"
    if kind == "episode":
        if episode is None:
            raise ValueError("this stage requires --episode")
        return f"{roots['episodes']}/{episode}/{rendered}"
    if kind == "review":
        return f"{roots['reviews']}/{rendered}"
    raise ValueError(f"unknown task output kind: {kind}")


def _task_path_matches_episode(relative: str, episode: str | None) -> bool:
    parts = PurePosixPath(relative).parts
    if not parts or _root_role(parts[0]) != "episodes":
        return True
    return episode is not None and len(parts) >= 2 and parts[1] == episode


def _task_sources(
    root: Path,
    state: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    episode: str | None,
    intent: str,
) -> list[dict[str, Any]]:
    raw_artifacts = state.get("artifacts")
    artifacts = _effective_lifecycle_records(
        root, raw_artifacts if isinstance(raw_artifacts, dict) else {}
    )
    source_owners = set(spec["source_owners"])
    if intent in {"revise", "continue", "preview"}:
        source_owners.add(str(spec["owner"]))
    sources: list[dict[str, Any]] = []
    for artifact_id, record in sorted(artifacts.items()):
        owner = record.get("owner")
        if owner not in source_owners:
            continue
        accepted = record.get("accepted_targets")
        candidate = record.get("candidate_targets")
        snapshot: Mapping[str, Any] | None = None
        authority = "accepted"
        if (
            intent in {"revise", "continue", "preview"}
            and owner == spec["owner"]
            and isinstance(candidate, dict)
            and candidate
        ):
            snapshot = candidate
            authority = "candidate"
        elif isinstance(accepted, dict) and accepted:
            snapshot = accepted
        if snapshot is None:
            continue
        for relative, digest in sorted(snapshot.items()):
            if (
                not isinstance(relative, str)
                or not isinstance(digest, str)
                or not _task_path_matches_episode(relative, episode)
            ):
                continue
            sources.append(
                {
                    "artifact_id": artifact_id,
                    "owner": owner,
                    "path": relative,
                    "hash": digest,
                    "authority": authority,
                }
            )
    return sources


def _task_template_bytes(target: str, template: Path | None) -> bytes:
    suffix = PurePosixPath(target).suffix.casefold()
    if template is not None and template.is_file():
        if not (suffix in {".json", ".jsonl"} and template.suffix.casefold() == ".md"):
            return template.read_bytes()
    if suffix == ".json":
        return b"{}\n"
    if suffix == ".jsonl":
        return b""
    return b"# TODO\n"


def prepare_task_packet(
    path: Path,
    *,
    stage: str,
    episode: str | None = None,
    intent: str = "create",
    output: str | None = None,
    materialize: bool = True,
) -> dict[str, Any]:
    """Create a bounded model-facing packet without changing lifecycle state."""

    root = find_project(path)
    normalized_stage = _task_stage(stage)
    normalized_intent = intent.strip().casefold().replace("_", "-")
    if normalized_intent not in {"create", "revise", "continue", "preview", "review"}:
        raise ValueError("intent must be create, revise, continue, preview or review")
    if episode is not None and EPISODE_ID_RE.fullmatch(episode) is None:
        raise ValueError("episode must use EP001 form")
    spec = TASK_STAGE_SPECS[normalized_stage]
    needs_episode = any(item[0] == "episode" for item in spec["outputs"])
    if needs_episode and episode is None:
        episode = "EP001"

    recovery = recover_project(root)
    if recovery.get("blocked"):
        raise ValueError("project has blocked recovery transactions")
    state = _read_state(root)
    layout = project_layout(root)
    if layout.get("mode") == "mixed":
        raise ValueError("project layout is mixed; resolve it before preparing work")
    roots = layout["roots"]
    sources = _task_sources(
        root,
        state,
        spec=spec,
        episode=episode,
        intent=normalized_intent,
    )
    project_hash = sha256_file(root / PROJECT_FILE)
    state_hash = sha256_file(root / STATE_FILE)
    identity = _json_dumps(
        {
            "project": project_hash,
            "state": state_hash,
            "stage": normalized_stage,
            "episode": episode,
            "intent": normalized_intent,
            "sources": [(item["path"], item["hash"]) for item in sources],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    task_id = "TASK-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    packet_relative = output or f".short-drama/work/task-packets/{task_id}.json"
    work_root = f".short-drama/work/prepared/{task_id}"
    skills_root = Path(__file__).resolve().parents[2]
    outputs: list[dict[str, Any]] = []
    for kind, suffix, template_relative in spec["outputs"]:
        target = _task_output_target(roots, kind, suffix, episode)
        work_path = f"{work_root}/{target}"
        template = skills_root / template_relative if template_relative else None
        if materialize and PurePosixPath(target).name != "screenplay-index.jsonl":
            destination = _project_path(root, work_path)
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                _atomic_bytes(destination, _task_template_bytes(target, template))
        outputs.append(
            {
                "target": target,
                "work_path": work_path,
                "template": template_relative,
                "derived": PurePosixPath(target).name in {
                    "screenplay-index.jsonl",
                    "image-prompts.md",
                    "keyframe-prompts.md",
                    "video-prompts.md",
                },
            }
        )

    flow = production_flow_status(root, episode=episode)
    packet = {
        "schema": TASK_PACKET_SCHEMA,
        "version": TASK_PACKET_VERSION,
        "task_id": task_id,
        "created_at": utc_now(),
        "stage": normalized_stage,
        "owner": spec["owner"],
        "milestone": spec["milestone"],
        "episode": episode,
        "intent": normalized_intent,
        "snapshot": {
            "project": {"path": PROJECT_FILE, "hash": project_hash},
            "state": {"path": STATE_FILE.as_posix(), "hash": state_hash},
        },
        "project": _creator_authority_summary(root),
        "pipeline": {
            "current_milestone": flow["current_milestone"],
            "next_action": flow["next_action"],
            "blockers": flow["blockers"],
        },
        "sources": sources,
        "outputs": outputs,
        "references": [
            {"path": relative, "load": "only_when_needed"}
            for relative in spec["references"]
        ],
        "execution": {
            "read_policy": "Read this packet first; open only listed sources and references needed for the current decision.",
            "write_policy": "Edit only work_path files. Do not hand-edit lifecycle state or accepted project files.",
            "finish": f"project_tool.py finalize <project> --packet {packet_relative}",
        },
    }
    packet_path = _project_path(root, packet_relative)
    atomic_json(packet_path, packet)
    packet_bytes = packet_path.read_bytes()
    return {
        "task_id": task_id,
        "packet_path": packet_relative,
        "packet_hash": sha256_bytes(packet_bytes),
        "packet_chars": len(packet_bytes.decode("utf-8")),
        "stage": normalized_stage,
        "episode": episode,
        "sources": len(sources),
        "outputs": len(outputs),
        "materialized": materialize,
    }


def _load_task_packet(root: Path, packet_relative: str) -> tuple[Path, dict[str, Any]]:
    relative = _relative_path(packet_relative, allow_operations=True)
    packet_path = _project_path(root, relative)
    packet = _json_loads(packet_path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("task packet must be a JSON object")
    if packet.get("schema") != TASK_PACKET_SCHEMA or packet.get("version") != TASK_PACKET_VERSION:
        raise ValueError("task packet schema/version is unsupported")
    snapshot = packet.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("task packet has no snapshot")
    for key in ("project", "state"):
        reference = snapshot.get(key)
        if not isinstance(reference, dict):
            raise ValueError(f"task packet snapshot lacks {key}")
        live = sha256_file(_project_path(root, str(reference.get("path"))))
        if live != reference.get("hash"):
            raise ValueError(f"task packet is stale: {key} changed")
    for source in packet.get("sources", []):
        if not isinstance(source, dict):
            raise ValueError("task packet source is invalid")
        if _live_hash(_project_path(root, str(source.get("path")))) != source.get("hash"):
            raise ValueError(f"task packet is stale: source changed: {source.get('path')}")
    return packet_path, packet


def _task_compile_prompt_records(
    root: Path, packet: Mapping[str, Any], outputs: Mapping[str, Path]
) -> list[str]:
    stage = packet.get("stage")
    profiles = {
        "image-prompts": ("image-prompt-specs.jsonl", "asset_board"),
        "storyboard": ("keyframes.jsonl", "keyframe"),
        "video-prompts": ("motion-specs.jsonl", "motion"),
    }
    selected = profiles.get(str(stage))
    if selected is None:
        return []
    source_name, profile = selected
    source = next((path for target, path in outputs.items() if PurePosixPath(target).name == source_name), None)
    if source is None or not source.is_file():
        return [f"missing prompt source: {source_name}"]
    layout = project_layout(root)
    fragments = _project_path(
        root, f"{layout['roots']['bible']}/generation/canonical-fragments.jsonl"
    )
    if not fragments.is_file():
        return ["canonical-fragments.jsonl is unavailable"]
    compiler_path = (
        Path(__file__).resolve().parents[2]
        / "short-drama-image-prompts/scripts/prompt_compile.py"
    )
    module = _load_check_module("prompt_compile_task", compiler_path)
    try:
        fragment_records = module.load_fragments(fragments)
        records = _jsonl_records(source.read_bytes(), source.name)
        compiled = [
            module.compile_record(record, fragment_records, expected_profile=profile)
            for record in records
        ]
        payload = "\n".join(
            _json_dumps(item, ensure_ascii=False, sort_keys=True) for item in compiled
        ) + "\n"
        _atomic_bytes(source, payload.encode("utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [f"prompt compilation failed: {error}"]
    return []


def _render_task_prompt_markdown(
    packet: Mapping[str, Any], outputs: Mapping[str, Path]
) -> list[str]:
    stage = str(packet.get("stage"))
    definitions = {
        "image-prompts": ("image-prompt-specs.jsonl", "image-prompts.md", "spec_id"),
        "storyboard": ("keyframes.jsonl", "keyframe-prompts.md", "keyframe_id"),
        "video-prompts": ("motion-specs.jsonl", "video-prompts.md", "motion_id"),
    }
    selected = definitions.get(stage)
    if selected is None:
        return []
    source_name, markdown_name, identity_key = selected
    source = next((path for target, path in outputs.items() if PurePosixPath(target).name == source_name), None)
    destination = next((path for target, path in outputs.items() if PurePosixPath(target).name == markdown_name), None)
    if source is None or destination is None or not source.is_file():
        return [f"cannot render {markdown_name}: source or destination is missing"]
    try:
        source_bytes = source.read_bytes()
        records = _jsonl_records(source_bytes, source.name)
        lines = [f"# {markdown_name}", "", f"source_sha256: `{sha256_bytes(source_bytes)}`", ""]
        for record in records:
            identity = record.get(identity_key)
            prompt = record.get("generic_prompt")
            if not isinstance(identity, str) or not isinstance(prompt, str):
                raise ValueError(f"record lacks {identity_key} or generic_prompt")
            lines.extend((f"## {identity}", "", prompt, ""))
        if stage == "video-prompts":
            for sibling_name, sibling_id in (
                ("generation-clips.jsonl", "clip_id"),
                ("delivery-containers.jsonl", "container_id"),
            ):
                sibling = next(
                    (
                        path
                        for target, path in outputs.items()
                        if PurePosixPath(target).name == sibling_name
                    ),
                    None,
                )
                if sibling is None or not sibling.is_file():
                    if sibling_name == "generation-clips.jsonl":
                        raise ValueError("generation-clips.jsonl is missing")
                    continue
                sibling_bytes = sibling.read_bytes()
                lines.extend((f"## {sibling_name}", ""))
                if sibling_name == "generation-clips.jsonl":
                    lines.append(f"source_sha256: `{sha256_bytes(sibling_bytes)}`")
                for record in _jsonl_records(sibling_bytes, sibling.name):
                    lines.append(f"- {record.get(sibling_id, '<unknown>')}")
                lines.append("")
        _atomic_bytes(destination, ("\n".join(lines).rstrip() + "\n").encode("utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        return [f"derived Markdown rendering failed: {error}"]
    return []


def _task_mechanical_issues(
    root: Path, packet: Mapping[str, Any], outputs: Mapping[str, Path]
) -> list[str]:
    stage = str(packet.get("stage"))
    by_name = {PurePosixPath(target).name: path for target, path in outputs.items()}
    findings: list[dict[str, Any]] = []
    try:
        if stage == "storyboard":
            module = _load_check_module(
                "storyboard_check_task",
                Path(__file__).resolve().parents[2]
                / "short-drama-storyboard/scripts/storyboard_check.py",
            )
            result = module.check(
                by_name["coverage.json"],
                by_name["shots.jsonl"],
                by_name.get("keyframes.jsonl"),
                root / PROJECT_FILE,
            )
            findings.extend(result.get("findings", []))
        elif stage == "video-prompts":
            shots_source = next(
                (
                    _project_path(root, str(source["path"]))
                    for source in packet.get("sources", [])
                    if isinstance(source, dict)
                    and PurePosixPath(str(source.get("path"))).name == "shots.jsonl"
                ),
                None,
            )
            if shots_source is None or not shots_source.is_file():
                return ["video mechanical checks require an accepted shots.jsonl source"]
            shots = _jsonl_records(shots_source.read_bytes(), shots_source.name)
            motions = _jsonl_records(
                by_name["motion-specs.jsonl"].read_bytes(), "motion-specs.jsonl"
            )
            clips = _jsonl_records(
                by_name["generation-clips.jsonl"].read_bytes(),
                "generation-clips.jsonl",
            )
            timing = _load_check_module(
                "motion_timing_task",
                Path(__file__).resolve().parents[2]
                / "short-drama-video-prompts/scripts/motion_timing_check.py",
            ).check(motions, shots)
            findings.extend(timing.get("findings", []))
            clip_result = _load_check_module(
                "generation_clip_task",
                Path(__file__).resolve().parents[2]
                / "short-drama-video-prompts/scripts/generation_clip_check.py",
            ).check(
                clips,
                shots,
                motions,
                _json_loads((root / PROJECT_FILE).read_text(encoding="utf-8")),
            )
            findings.extend(clip_result.get("findings", []))
            containers_path = by_name.get("delivery-containers.jsonl")
            if containers_path is not None and containers_path.is_file():
                containers = _jsonl_records(
                    containers_path.read_bytes(), "delivery-containers.jsonl"
                )
                if containers:
                    container_result = _load_check_module(
                        "container_check_task",
                        Path(__file__).resolve().parents[2]
                        / "short-drama-video-prompts/scripts/container_check.py",
                    ).reconcile(containers, shots, motions)
                    findings.extend(container_result.get("findings", []))
    except (KeyError, OSError, UnicodeError, ValueError) as error:
        return [f"mechanical validation failed: {error}"]
    return [
        f"{finding.get('code', 'CHECK')}: {finding.get('message', 'validation failed')}"
        for finding in findings
        if isinstance(finding, dict)
    ]


def finalize_task_packet(
    path: Path,
    *,
    packet_relative: str,
    artifact_id: str | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    """Compile and validate prepared outputs, optionally publishing one candidate."""

    root = find_project(path)
    _packet_path, packet = _load_task_packet(root, packet_relative)
    output_entries = packet.get("outputs")
    if not isinstance(output_entries, list):
        raise ValueError("task packet outputs are invalid")
    output_paths: dict[str, Path] = {}
    for entry in output_entries:
        if not isinstance(entry, dict):
            raise ValueError("task packet output entry is invalid")
        target = _relative_path(str(entry.get("target")))
        work_path = _relative_path(str(entry.get("work_path")), allow_operations=True)
        output_paths[target] = _project_path(root, work_path)

    issues: list[str] = []
    if packet.get("stage") == "write":
        screenplay = next(
            (
                source
                for target, source in output_paths.items()
                if PurePosixPath(target).name == "screenplay.md"
            ),
            None,
        )
        index_entry = next(
            (
                (target, source)
                for target, source in output_paths.items()
                if PurePosixPath(target).name == "screenplay-index.jsonl"
            ),
            None,
        )
        if screenplay is not None and screenplay.is_file() and index_entry is not None:
            module = _load_check_module(
                "screenplay_index_task",
                Path(__file__).resolve().parents[2]
                / "short-drama-write/scripts/screenplay_index.py",
            )
            try:
                module.build_index(
                    screenplay,
                    index_entry[1],
                    source_ref=index_entry[0].replace("screenplay-index.jsonl", "screenplay.md"),
                    authority="candidate",
                )
            except (OSError, UnicodeError, ValueError) as error:
                issues.append(f"screenplay index failed: {error}")

    issues.extend(_task_compile_prompt_records(root, packet, output_paths))
    issues.extend(_render_task_prompt_markdown(packet, output_paths))
    candidate_outputs: dict[str, bytes] = {}
    owner = str(packet.get("owner"))
    for target, source in output_paths.items():
        if not source.is_file():
            issues.append(f"missing prepared output: {source.relative_to(root).as_posix()}")
            continue
        try:
            content = source.read_bytes()
            _validate_publication_layout(target, owner=owner)
            _validate_candidate_content(target, content)
            candidate_outputs[target] = content
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(f"{target}: {error}")
    if not issues:
        try:
            _validate_compiled_prompt_outputs(root, candidate_outputs)
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(str(error))
    if not issues:
        issues.extend(_task_mechanical_issues(root, packet, output_paths))

    result: dict[str, Any] = {
        "task_id": packet.get("task_id"),
        "stage": packet.get("stage"),
        "episode": packet.get("episode"),
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "outputs": [
            {"target": target, "work_path": source.relative_to(root).as_posix()}
            for target, source in sorted(output_paths.items())
        ],
    }
    if publish:
        if issues:
            raise ValueError("cannot publish a task packet with validation issues")
        if not artifact_id:
            raise ValueError("--artifact-id is required with --publish")
        input_hashes = {
            str(source["path"]): str(source["hash"])
            for source in packet.get("sources", [])
            if isinstance(source, dict)
        }
        result["publication"] = publish_candidate(
            root,
            owner=owner,
            artifact_id=artifact_id,
            outputs=candidate_outputs,
            input_hashes=input_hashes,
        )
    return result


def set_production_flow(
    path: Path, changes: Mapping[str, str]
) -> dict[str, Any]:
    """Persist a validated production flow override in short-drama.json."""

    root = find_project(path)
    project_path = root / PROJECT_FILE
    project = _json_loads(project_path.read_text(encoding="utf-8"))
    flow = dict(PRODUCTION_FLOW_DEFAULTS)
    existing = project.get("production_flow")
    if isinstance(existing, dict):
        for key in PRODUCTION_FLOW_DEFAULTS:
            if key in existing:
                flow[key] = existing[key]
    for key, raw in changes.items():
        if key not in {"enforcement", "allow_script_first", "image_result_gate"}:
            raise ValueError(f"unknown production flow setting: {key}")
        if key == "enforcement":
            if raw not in {"strict", "guided"}:
                raise ValueError("enforcement must be strict or guided")
            flow[key] = raw
        elif key == "allow_script_first":
            if raw not in {"true", "false"}:
                raise ValueError(f"{key} must be true or false")
            flow[key] = raw == "true"
        else:
            if raw not in {"prompt_only", "observed"}:
                raise ValueError("image_result_gate must be prompt_only or observed")
            flow[key] = raw
    project["production_flow"] = flow
    atomic_json(project_path, project)
    return {"production_flow": flow}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a short-drama filesystem project.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize a project without creative content.")
    init.add_argument("path", type=Path)
    init.add_argument("--title", default="未命名短剧")
    init.add_argument("--language", default="zh-CN")
    init.add_argument("--aspect-ratio", default="9:16")
    init.add_argument(
        "--prompt-language",
        default=DEFAULT_PROMPT_LANGUAGE,
        help=(
            "Language for prompt bodies handed to image, video and voice "
            f"generators (default {DEFAULT_PROMPT_LANGUAGE!r}); distinct from "
            "--language, which governs what the creator reads."
        ),
    )
    init.add_argument(
        "--max-clip-seconds",
        type=float,
        default=DEFAULT_MAX_CLIP_SECONDS,
        help=(
            "Maximum duration of one video-model generation clip in seconds "
            f"(default {DEFAULT_MAX_CLIP_SECONDS:g}); this does not change editorial shot boundaries."
        ),
    )

    status = subparsers.add_parser("status", help="Print a creator-safe project summary.")
    status.add_argument("path", type=Path, nargs="?", default=Path.cwd())

    preflight = subparsers.add_parser(
        "preflight",
        help=(
            "Suite verify + recover + status in one process; the single entry "
            "gate for starting a session."
        ),
    )
    preflight.add_argument("path", type=Path, nargs="?", default=Path.cwd())

    pipeline = subparsers.add_parser(
        "pipeline",
        help=(
            "Report the fixed M0..M7 production flow position and blockers; "
            "--set adjusts per-project flow switches."
        ),
    )
    pipeline.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    pipeline.add_argument("--episode", default=None)
    pipeline.add_argument(
        "--set",
        action="append",
        default=[],
        dest="flow_settings",
        help=(
            "KEY=VALUE override; repeat. Keys: enforcement, allow_script_first, "
            "image_result_gate."
        ),
    )

    prepare = subparsers.add_parser(
        "prepare",
        help=(
            "Create a compact, hash-bound task packet and optional working "
            "skeletons so the model reads only the current stage slice."
        ),
    )
    prepare.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    prepare.add_argument("--stage", required=True, choices=sorted(TASK_STAGE_SPECS))
    prepare.add_argument("--episode", default=None)
    prepare.add_argument(
        "--intent",
        default="create",
        choices=("create", "revise", "continue", "preview", "review"),
    )
    prepare.add_argument("--output", default=None)
    prepare.add_argument(
        "--materialize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create working skeleton files beside the packet (default on).",
    )

    finalize = subparsers.add_parser(
        "finalize",
        help=(
            "Compile deterministic derivatives and validate prepared task "
            "outputs; optionally publish them as one candidate."
        ),
    )
    finalize.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    finalize.add_argument("--packet", required=True)
    finalize.add_argument("--artifact-id", default=None)
    finalize.add_argument("--publish", action="store_true")

    upgrade_flow = subparsers.add_parser(
        "upgrade-flow",
        help=(
            "Upgrade an existing project to pipeline 2.0 after accepted M1.5a "
            "asset models and M1.5b canonical fragments pass validation."
        ),
    )
    upgrade_flow.add_argument("path", type=Path, nargs="?", default=Path.cwd())

    recover = subparsers.add_parser("recover", help="Recover interrupted publications.")
    recover.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    recover.add_argument("--transaction")

    publish = subparsers.add_parser(
        "publish", help="Publish a text/JSON candidate through the recovery WAL."
    )
    publish.add_argument("path", type=Path)
    publish.add_argument("--owner", required=True)
    publish.add_argument("--artifact-id", required=True)
    publish.add_argument(
        "--output",
        action="append",
        required=True,
        dest="outputs",
        help="Bind PROJECT_TARGET=PROJECT_SOURCE; repeat for multiple files.",
    )
    publish.add_argument(
        "--input",
        action="append",
        dest="inputs",
        help="Bind an additional exact project input as PATH=SHA256.",
    )
    publish.add_argument(
        "--allow-unregistered-path",
        action="store_true",
        help=(
            "Publish outside the standard stage directories. Ad-hoc creator "
            "files stay possible; without this flag a mistyped stage directory "
            "is refused instead of building a parallel tree status never reports."
        ),
    )
    publish.add_argument(
        "--input-record",
        action="append",
        dest="input_records",
        help=(
            "Narrow one input to the records actually used, as PATH=SELECTOR; "
            "repeat per record. A selector is a JSONL record ID or a JSON "
            "RFC 6901 pointer. Unrelated edits to the rest of that file then "
            "leave this artifact current."
        ),
    )
    publish.add_argument(
        "--input-record-auto",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="input_record_auto",
        help=(
            "Auto-narrow declared inputs to the record IDs carried by "
            "structured refs in the candidate output (default on); "
            "--no-input-record-auto restores whole-file binding for inputs "
            "without an explicit --input-record."
        ),
    )

    accept = subparsers.add_parser(
        "accept", help="Record creator acceptance for exact candidate hashes."
    )
    accept.add_argument("path", type=Path)
    accept.add_argument("--artifact-id", required=True)
    accept.add_argument("--decision", required=True, choices=("accepted", "rejected"))
    accept.add_argument(
        "--target",
        action="append",
        default=[],
        dest="targets",
        help=(
            "Candidate target PATH, optionally PATH=SHA256; repeat. Without a "
            "hash the exact candidate snapshot is resolved from project state "
            "and still re-checked against live bytes before recording."
        ),
    )
    accept.add_argument("--evidence-artifact", required=True)
    accept.add_argument(
        "--evidence-hash",
        help=(
            "Optional SHA256 of the evidence file; when omitted the tool "
            "hashes the evidence artifact itself, with the exact same "
            "live-bytes check downstream."
        ),
    )
    accept.add_argument("--evidence-record-id")
    accept.add_argument("--evidence-field")

    accept_batch = subparsers.add_parser(
        "accept-batch",
        help=(
            "Apply creator acceptance records already written to disk in one "
            "process, instead of one accept call per artifact."
        ),
    )
    accept_batch.add_argument("path", type=Path)
    accept_batch.add_argument("--decisions-dir", default=None)
    accept_batch.add_argument(
        "--evidence",
        action="append",
        default=[],
        dest="evidence",
        help="Extra evidence file to scan; repeat.",
    )

    decide = subparsers.add_parser(
        "decide",
        help=(
            "Write one compliant artifact_acceptance decision file for a "
            "candidate, so accept-batch can apply it. Never decides for the "
            "creator: the decision content is still whatever the creator "
            "confirms; this only writes the file in the required format."
        ),
    )
    decide.add_argument("path", type=Path)
    decide.add_argument("--artifact-id", required=True)
    decide.add_argument(
        "--decision", required=True, choices=("accepted", "rejected")
    )
    decide.add_argument("--decided-by", default="creator")
    decide.add_argument("--delegation-artifact")
    decide.add_argument("--delegation-hash")
    decide.add_argument("--delegation-record-id")
    decide.add_argument("--output", default=None)
    decide.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite an existing decision file for the same artifact; the "
            "superseded decision_id is kept in supersedes_decision_id. Does "
            "not bypass the check that refuses decisions for already accepted "
            "artifacts (they no longer carry candidate targets)."
        ),
    )

    unpublish = subparsers.add_parser(
        "unpublish",
        help=(
            "Remove a published-but-unaccepted artifact record (candidate "
            "stage), so a mis-published direction can be revoked without "
            "hand-editing state. Accepted artifacts are protected."
        ),
    )
    unpublish.add_argument("path", type=Path)
    unpublish.add_argument("--artifact-id", required=True)

    review = subparsers.add_parser(
        "review", help="Record an independent verdict for exact accepted hashes."
    )
    review.add_argument("path", type=Path)
    review.add_argument("--artifact-id", required=True)
    review.add_argument(
        "--verdict",
        required=True,
        choices=("approve", "approve_with_notes", "revise", "provisional"),
    )
    review.add_argument(
        "--target",
        action="append",
        default=[],
        dest="targets",
        help=(
            "Accepted target PATH, optionally PATH=SHA256; repeat. Without a "
            "hash the exact accepted snapshot is resolved from project state "
            "and still re-checked against live bytes before recording."
        ),
    )
    review.add_argument("--verdict-owner", required=True)
    review.add_argument("--verdict-artifact", required=True)
    review.add_argument(
        "--verdict-hash",
        help=(
            "Optional SHA256 of the verdict file; when omitted the tool "
            "hashes the verdict artifact itself, with the exact same "
            "live-bytes check downstream."
        ),
    )
    review.add_argument("--verdict-record-id")

    review_bundle = subparsers.add_parser(
        "review-bundle",
        help=(
            "Collect verified evidence for a fresh or cold_read reviewer into "
            "one compact file: targets, hashes, extracted records, bound "
            "inputs and creator authority."
        ),
    )
    review_bundle.add_argument("path", type=Path)
    review_bundle.add_argument("--artifact-id", dest="label")
    review_bundle.add_argument(
        "--target",
        action="append",
        default=[],
        dest="targets",
        help="Project target path, optionally PATH=SHA256; repeat.",
    )
    review_bundle.add_argument(
        "--episode",
        default=None,
        help="Expand to every lifecycle target under 剧集/<EP>/.",
    )
    review_bundle.add_argument("--output", default=None)
    review_bundle.add_argument("--scope", choices=sorted(REVIEW_SCOPES), default=None)
    review_bundle.add_argument(
        "--delta-from",
        default=None,
        help="Only include targets whose live hash differs from this prior verdict.",
    )
    review_bundle.add_argument(
        "--compact",
        action="store_true",
        help="Write minified JSON without removing review evidence.",
    )
    review_bundle.add_argument(
        "--mechanical-report",
        action="append",
        default=[],
        dest="mechanical_reports",
        help="Embed one JSON mechanical report file; repeat.",
    )

    review_batch = subparsers.add_parser(
        "review-batch",
        help=(
            "Apply review verdict documents already written to disk in one "
            "process, instead of one review call per artifact."
        ),
    )
    review_batch.add_argument("path", type=Path)
    review_batch.add_argument("--verdicts-dir", default=None)
    review_batch.add_argument(
        "--episode",
        default=None,
        help=(
            "Only apply verdicts whose artifact_id targets this episode "
            "(e.g. EP001); other verdicts in the directory are skipped. "
            "One episode's conclusions are applied in a single pass."
        ),
    )
    review_batch.add_argument(
        "--evidence",
        action="append",
        default=[],
        dest="evidence",
        help="Extra verdict file to scan; repeat.",
    )

    package = subparsers.add_parser("package", help="Package approved text/JSON artifacts.")
    package.add_argument("path", type=Path)
    package.add_argument("--episode", required=True)
    package.add_argument("--include", action="append", required=True, dest="includes")
    package.add_argument(
        "--omit",
        action="append",
        dest="omissions",
        help=(
            "Acknowledge one accepted episode file that is deliberately left out; "
            "repeat per file. The manifest records it and why."
        ),
    )
    package.add_argument(
        "--omission-evidence",
        action="append",
        default=[],
        dest="omission_evidence",
        help=(
            "Creator-owned accepted delivery_omission JSON evidence; repeat. "
            "Its paths and reasons must exactly cover every --omit path."
        ),
    )
    package.add_argument("--text-exceptions", type=Path)

    verify = subparsers.add_parser(
        "verify", help="Re-check a delivered package against its own checksums."
    )
    verify.add_argument("path", type=Path)
    verify.add_argument("--episode", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize_project(
                args.path,
                title=args.title,
                language=args.language,
                aspect_ratio=args.aspect_ratio,
                prompt_language=args.prompt_language,
                max_clip_seconds=args.max_clip_seconds,
            )
        elif args.command == "status":
            result = project_status(args.path)
        elif args.command == "preflight":
            result = preflight_project(args.path)
            print(_stdout_json(result))
            return 3 if result["recovery"]["blocked"] else 0
        elif args.command == "pipeline":
            changes: dict[str, str] = {}
            for raw in args.flow_settings:
                key, separator, value = raw.partition("=")
                if not separator or not key or not value:
                    raise ValueError("--set must use KEY=VALUE")
                changes[key] = value
            if changes:
                set_production_flow(args.path, changes)
            result = production_flow_status(args.path, episode=args.episode)
            print(_stdout_json(result))
            if result["enforcement"] == "strict" and result["blockers"]:
                return 3
            return 0
        elif args.command == "prepare":
            result = prepare_task_packet(
                args.path,
                stage=args.stage,
                episode=args.episode,
                intent=args.intent,
                output=args.output,
                materialize=args.materialize,
            )
        elif args.command == "finalize":
            result = finalize_task_packet(
                args.path,
                packet_relative=args.packet,
                artifact_id=args.artifact_id,
                publish=args.publish,
            )
        elif args.command == "upgrade-flow":
            result = upgrade_project_flow(args.path)
        elif args.command == "recover":
            result = (
                recover_transaction(args.path, args.transaction)
                if args.transaction
                else recover_project(args.path)
            )
        elif args.command == "publish":
            result = _publish_from_cli(args)
        elif args.command == "accept":
            evidence_ref = {
                "owner": "creator",
                "artifact": args.evidence_artifact,
                "hash": args.evidence_hash
                or sha256_file(
                    _project_path(
                        find_project(args.path), args.evidence_artifact
                    )
                ),
            }
            if args.evidence_record_id:
                evidence_ref["record_id"] = args.evidence_record_id
            if args.evidence_field:
                evidence_ref["field"] = args.evidence_field
            result = record_creator_acceptance(
                args.path,
                artifact_id=args.artifact_id,
                decision=args.decision,
                target_hashes=_resolve_snapshot_targets(
                    find_project(args.path),
                    args.artifact_id,
                    args.targets,
                    snapshot_key="candidate_targets",
                ),
                evidence_ref=evidence_ref,
            )
        elif args.command == "accept-batch":
            result = accept_decisions_batch(
                args.path,
                decisions_dir=args.decisions_dir,
                extra_evidence=args.evidence,
            )
            print(_stdout_json(result))
            return 2 if result["failed"] else 0
        elif args.command == "decide":
            result = write_creator_decision(
                args.path,
                artifact_id=args.artifact_id,
                decision=args.decision,
                decided_by=args.decided_by,
                delegation_artifact=args.delegation_artifact,
                delegation_hash=args.delegation_hash,
                delegation_record_id=args.delegation_record_id,
                output=args.output,
                force=args.force,
            )
        elif args.command == "unpublish":
            result = unpublish_artifact(
                args.path,
                artifact_id=args.artifact_id,
            )
        elif args.command == "review":
            verdict_ref = {
                "owner": args.verdict_owner,
                "artifact": args.verdict_artifact,
                "hash": args.verdict_hash
                or sha256_file(
                    _project_path(
                        find_project(args.path), args.verdict_artifact
                    )
                ),
            }
            if args.verdict_record_id:
                verdict_ref["record_id"] = args.verdict_record_id
            result = record_independent_review(
                args.path,
                artifact_id=args.artifact_id,
                verdict=args.verdict,
                reviewed_targets=_resolve_snapshot_targets(
                    find_project(args.path),
                    args.artifact_id,
                    args.targets,
                    snapshot_key="accepted_targets",
                ),
                verdict_ref=verdict_ref,
            )
        elif args.command == "review-bundle":
            raw_targets: dict[str, str | None] = {}
            for raw in args.targets:
                relative, separator, digest = raw.partition("=")
                relative = _relative_path(relative)
                if separator and not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError(f"review target hash is invalid: {raw}")
                if relative in raw_targets:
                    raise ValueError(f"duplicate review target: {relative}")
                raw_targets[relative] = digest if separator else None
            result = build_review_bundle(
                args.path,
                targets=raw_targets,
                episode=args.episode,
                label=args.label,
                output=args.output,
                mechanical_reports=args.mechanical_reports,
                scope=args.scope,
                delta_from=args.delta_from,
                compact=args.compact,
            )
        elif args.command == "review-batch":
            result = review_verdicts_batch(
                args.path,
                verdicts_dir=args.verdicts_dir,
                extra_evidence=args.evidence,
                episode=args.episode,
            )
            print(_stdout_json(result))
            return 2 if result["failed"] else 0
        elif args.command == "verify":
            result = verify_delivery_package(args.path, episode=args.episode)
        elif args.command == "package":
            exceptions = None
            if args.text_exceptions:
                exceptions = _json_loads(args.text_exceptions.read_text(encoding="utf-8"))
                if not isinstance(exceptions, list):
                    raise ValueError("text exceptions file must contain a JSON array")
            result = build_delivery_package(
                args.path,
                episode=args.episode,
                selected_paths=args.includes,
                text_exceptions=exceptions,
                omitted_paths=args.omissions,
                omission_evidence=args.omission_evidence,
            )
        print(_stdout_json(result))
        # `verify` is the only subcommand that reports a verdict in its payload
        # instead of raising, so it needs the same exit convention the check
        # scripts use: a tampered package must fail a CI step or an && chain.
        if result.get("status") == "tampered":
            return 1
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        TransactionError,
        PackageBlockedError,
    ) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
