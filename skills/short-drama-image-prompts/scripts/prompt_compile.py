#!/usr/bin/env python3
"""Deterministically compile accepted canonical fragments into prompt records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("short-drama needs Python 3.10 or newer")

COMPILER_VERSION = "1.0"
HASH_RE = re.compile(r"[0-9a-f]{64}")


def _reject_json_constant(value: str) -> Any:
    raise json.JSONDecodeError(f"non-finite JSON number is not allowed: {value}", value, 0)


def _json_loads(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_json_constant)
PROFILE_ORDER = {
    "asset_board": ("style_core", "identity_full", "continuity_lock", "variant_delta", "view_projection", "negative_lock"),
    "keyframe": ("style_core", "identity_full", "continuity_lock", "variant_delta", "view_projection", "negative_lock"),
    "motion": ("style_core", "identity_full", "continuity_lock", "variant_delta", "view_projection", "negative_lock"),
}
REQUIRED_FRAGMENT_KINDS = frozenset(
    {"style_core", "identity_full", "continuity_lock", "view_projection", "negative_lock"}
)
ASSET_FRAGMENT_KINDS = frozenset(
    {"identity_full", "continuity_lock", "variant_delta", "view_projection", "negative_lock"}
)
SECTION_TITLES = {
    "en": {
        "task": "Task and format",
        "baseline": "Fixed asset baseline",
        "variant": "State delta",
        "view": "View and spatial projection",
        "current": "Current task",
        "negative": "Exclusions",
    },
    "zh": {
        "task": "任务与格式",
        "baseline": "固定资产基线",
        "variant": "状态增量",
        "view": "观察方向与空间投影",
        "current": "当前任务",
        "negative": "排除项",
    },
}


class CompileError(ValueError):
    """A prompt cannot be compiled without guessing or rewriting authority."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def fragment_hash(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "fragment_hash"}
    return hashlib.sha256(_canonical_bytes(material)).hexdigest()


def load_fragments(path: Path) -> dict[str, dict[str, Any]]:
    fragments: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = _json_loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("fragment_id"), str):
            raise CompileError(f"invalid fragment record at {path.name}:{number}")
        fragment_id = value["fragment_id"]
        if fragment_id in fragments:
            raise CompileError(f"duplicate fragment_id: {fragment_id}")
        if value.get("fragment_hash") != fragment_hash(value):
            raise CompileError(f"fragment hash mismatch: {fragment_id}")
        fragments[fragment_id] = value
    return fragments


def _strings(value: Any, *, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise CompileError(f"{label} must be an array of non-empty strings")
    return [item.strip() for item in value]


def _ref_id(reference: Any) -> tuple[str, str]:
    if not isinstance(reference, dict):
        raise CompileError("fragment_refs entries must be objects")
    fragment_id = reference.get("fragment_id")
    digest = reference.get("hash")
    if not isinstance(fragment_id, str) or not isinstance(digest, str) or HASH_RE.fullmatch(digest) is None:
        raise CompileError("fragment ref needs fragment_id and sha256 hash")
    return fragment_id, digest


def _binding_id(binding: Mapping[str, Any], key: str, ref_key: str) -> str | None:
    direct = binding.get(key)
    reference = binding.get(ref_key)
    record_id = reference.get("record_id") if isinstance(reference, dict) else None
    if (
        isinstance(direct, str)
        and direct
        and isinstance(record_id, str)
        and record_id
        and direct != record_id
    ):
        raise CompileError(f"{key} does not match {ref_key}.record_id")
    if isinstance(direct, str) and direct:
        return direct
    return record_id if isinstance(record_id, str) and record_id else None


def _model_record_ids(fragment: Mapping[str, Any]) -> set[str]:
    refs = fragment.get("model_refs")
    if not isinstance(refs, list):
        return set()
    return {
        record_id
        for reference in refs
        if isinstance(reference, dict)
        and isinstance((record_id := reference.get("record_id")), str)
        and record_id
    }


def _validate_binding_fragments(
    bindings: list[Any], resolved: list[Mapping[str, Any]], *, profile: str
) -> None:
    normalized: dict[str, dict[str, str | None]] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            raise CompileError("asset_bindings entries must be objects")
        asset_id = binding.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            raise CompileError("asset_bindings entries need asset_id")
        if asset_id in normalized:
            raise CompileError(f"asset_bindings contain duplicate asset_id: {asset_id}")
        model_id = _binding_id(binding, "model_id", "model_ref")
        view_id = _binding_id(binding, "view_id", "view_ref")
        variant_id = _binding_id(binding, "variant_id", "variant_ref")
        if model_id is None or view_id is None:
            raise CompileError(f"asset binding needs model and view: {asset_id}")
        normalized[asset_id] = {
            "model_id": model_id,
            "view_id": view_id,
            "variant_id": variant_id,
        }

    by_asset: dict[str, list[Mapping[str, Any]]] = {asset_id: [] for asset_id in normalized}
    style_count = 0
    for fragment in resolved:
        kind = fragment.get("fragment_kind")
        if kind not in PROFILE_ORDER[profile]:
            raise CompileError(f"unsupported fragment kind: {kind}")
        scope = fragment.get("scope")
        if not isinstance(scope, dict) or not scope:
            raise CompileError(f"fragment scope is invalid: {fragment.get('fragment_id')}")
        jobs = scope.get("jobs")
        if kind == "style_core":
            style_count += 1
            if fragment.get("asset_id") not in {None, ""}:
                raise CompileError("style_core must be project-level")
            if jobs is not None and (not isinstance(jobs, list) or profile not in jobs):
                raise CompileError(f"fragment is not valid for profile {profile}: {fragment.get('fragment_id')}")
            continue
        asset_id = fragment.get("asset_id")
        if not isinstance(asset_id, str) or asset_id not in normalized:
            raise CompileError(f"fragment asset does not match asset_bindings: {fragment.get('fragment_id')}")
        if kind != "view_projection" and (
            not isinstance(jobs, list) or profile not in jobs
        ):
            raise CompileError(f"fragment is not valid for profile {profile}: {fragment.get('fragment_id')}")
        by_asset[asset_id].append(fragment)

    if style_count != 1:
        raise CompileError("fragment_refs need exactly one project style_core")

    for asset_id, binding in normalized.items():
        fragments = by_asset[asset_id]
        kinds: dict[str, list[Mapping[str, Any]]] = {}
        for fragment in fragments:
            kinds.setdefault(str(fragment.get("fragment_kind")), []).append(fragment)
        required = {"identity_full", "continuity_lock", "view_projection", "negative_lock"}
        missing = sorted(kind for kind in required if len(kinds.get(kind, [])) != 1)
        if missing:
            raise CompileError(
                f"asset {asset_id} needs exactly one fragment for: " + ", ".join(missing)
            )
        model_id = str(binding["model_id"])
        for kind in ("identity_full", "continuity_lock", "negative_lock"):
            if model_id not in _model_record_ids(kinds[kind][0]):
                raise CompileError(f"{kind} fragment does not reference bound model for {asset_id}")
        view_fragment = kinds["view_projection"][0]
        view_id = str(binding["view_id"])
        if view_fragment.get("scope", {}).get("view_id") != view_id:
            raise CompileError(f"view_projection scope does not match bound view for {asset_id}")
        if view_id not in _model_record_ids(view_fragment):
            raise CompileError(f"view_projection does not reference bound view for {asset_id}")
        variant_id = binding.get("variant_id")
        variants = kinds.get("variant_delta", [])
        if variant_id is None and variants:
            raise CompileError(f"asset {asset_id} has variant fragments without a bound variant")
        if variant_id is not None:
            if len(variants) != 1:
                raise CompileError(f"asset {asset_id} needs exactly one bound variant fragment")
            variant = variants[0]
            variant_record_ids = _model_record_ids(variant)
            if variant.get("variant_id") != variant_id or variant_id not in variant_record_ids:
                raise CompileError(f"variant_delta does not match bound variant for {asset_id}")
            if model_id not in variant_record_ids:
                raise CompileError(
                    f"variant_delta does not reference bound base model for {asset_id}"
                )


def compile_record(
    record: Mapping[str, Any],
    fragments: Mapping[str, Mapping[str, Any]],
    *,
    expected_profile: str | None = None,
) -> dict[str, Any]:
    bindings = record.get("asset_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise CompileError("asset_bindings must be a non-empty array")
    components = record.get("prompt_components")
    if not isinstance(components, dict):
        raise CompileError("prompt_components is required")
    profile = components.get("profile")
    if profile not in PROFILE_ORDER:
        raise CompileError(f"unsupported prompt profile: {profile}")
    if expected_profile is not None and profile != expected_profile:
        raise CompileError(
            f"prompt profile must be {expected_profile}, got {profile}"
        )
    refs = components.get("fragment_refs")
    if not isinstance(refs, list) or not refs:
        raise CompileError("fragment_refs must be a non-empty array")

    resolved: list[Mapping[str, Any]] = []
    fragment_hashes: dict[str, str] = {}
    for reference in refs:
        fragment_id, digest = _ref_id(reference)
        fragment = fragments.get(fragment_id)
        if fragment is None:
            raise CompileError(f"unknown fragment_id: {fragment_id}")
        if fragment.get("fragment_hash") != fragment_hash(fragment):
            raise CompileError(f"fragment hash mismatch: {fragment_id}")
        if fragment.get("fragment_hash") != digest:
            raise CompileError(f"fragment ref hash mismatch: {fragment_id}")
        resolved.append(fragment)
        fragment_hashes[fragment_id] = digest

    rank = {kind: index for index, kind in enumerate(PROFILE_ORDER[str(profile)])}
    asset_order = {
        str(binding.get("asset_id")): index
        for index, binding in enumerate(bindings)
        if isinstance(binding, dict) and isinstance(binding.get("asset_id"), str)
    }
    order_keys = [
        (
            rank.get(str(fragment.get("fragment_kind")), 999),
            -1
            if fragment.get("fragment_kind") == "style_core"
            else asset_order.get(str(fragment.get("asset_id")), 999),
        )
        for fragment in resolved
    ]
    if order_keys != sorted(order_keys):
        raise CompileError("fragment_refs are not in canonical order")
    if len(set(fragment_hashes)) != len(resolved):
        raise CompileError("fragment_refs contain duplicates")
    present_kinds = {str(fragment.get("fragment_kind")) for fragment in resolved}
    missing_kinds = sorted(REQUIRED_FRAGMENT_KINDS - present_kinds)
    if missing_kinds:
        raise CompileError("fragment_refs missing required kinds: " + ", ".join(missing_kinds))
    languages = {fragment.get("language") for fragment in resolved}
    if len(languages) != 1 or not all(isinstance(value, str) and value for value in languages):
        raise CompileError("fragment_refs must use one non-empty language")
    language = str(next(iter(languages)))
    _validate_binding_fragments(bindings, resolved, profile=str(profile))

    local = _strings(components.get("local_instructions", []), label="local_instructions")
    negatives = _strings(
        components.get("local_negative_constraints", []),
        label="local_negative_constraints",
    )
    task = record.get("task_and_format")
    if not isinstance(task, str) or not task.strip():
        raise CompileError("task_and_format is required")

    titles = SECTION_TITLES["zh" if language.casefold().startswith("zh") else "en"]
    sections: list[tuple[str, list[str]]] = [(titles["task"], [task.strip()])]
    fixed = [str(fragment.get("text", "")).strip() for fragment in resolved if fragment.get("fragment_kind") not in {"variant_delta", "view_projection", "negative_lock"}]
    variants = [str(fragment.get("text", "")).strip() for fragment in resolved if fragment.get("fragment_kind") == "variant_delta"]
    views = [str(fragment.get("text", "")).strip() for fragment in resolved if fragment.get("fragment_kind") == "view_projection"]
    fragment_negatives = [str(fragment.get("text", "")).strip() for fragment in resolved if fragment.get("fragment_kind") == "negative_lock"]
    sections.append((titles["baseline"], [value for value in fixed if value]))
    if variants:
        sections.append((titles["variant"], variants))
    if views:
        sections.append((titles["view"], views))
    if local:
        sections.append((titles["current"], local))
    combined_negatives = [value for value in fragment_negatives if value] + negatives
    if combined_negatives:
        sections.append((titles["negative"], combined_negatives))
    prompt = "\n\n".join(
        f"{title}:\n" + "\n".join(f"- {line}" for line in lines)
        for title, lines in sections
        if lines
    )
    output_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    result = dict(record)
    result["compilation_manifest"] = {
        "compiler_version": COMPILER_VERSION,
        "fragment_hashes": fragment_hashes,
        "output_hash": output_hash,
    }
    result["generic_prompt"] = prompt
    return result


def validate_compiled_record(
    record: Mapping[str, Any],
    fragments: Mapping[str, Mapping[str, Any]],
    *,
    expected_profile: str | None = None,
) -> None:
    compiled = compile_record(record, fragments, expected_profile=expected_profile)
    if record.get("generic_prompt") != compiled["generic_prompt"]:
        raise CompileError("generic_prompt does not match deterministic compilation")
    if record.get("compilation_manifest") != compiled["compilation_manifest"]:
        raise CompileError("compilation_manifest does not match deterministic compilation")


def _records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        value = _json_loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise CompileError("JSON input must contain one object")
        return [value]
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = _json_loads(line)
        if not isinstance(value, dict):
            raise CompileError(f"JSONL input must contain objects: line {number}")
        records.append(value)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--fragments", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--expected-profile", choices=sorted(PROFILE_ORDER))
    args = parser.parse_args(argv)
    try:
        fragments = load_fragments(args.fragments)
        records = _records(args.input)
        if args.check:
            for record in records:
                validate_compiled_record(
                    record,
                    fragments,
                    expected_profile=args.expected_profile,
                )
            result = {"status": "pass", "checked": len(records)}
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
            return 0
        compiled = [
            compile_record(
                record,
                fragments,
                expected_profile=args.expected_profile,
            )
            for record in records
        ]
        text = (
            "\n".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
                for record in compiled
            )
            + "\n"
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, CompileError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
