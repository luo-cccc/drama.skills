#!/usr/bin/env python3
"""Validate the text-only generation asset baseline (M1.5a/M1.5b inputs).

The check is deliberately mechanical. It proves that every scoped asset has a
usable model and view contract, and that canonical prompt fragments are bound
to current model hashes. Visual quality remains an independent review concern.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit("short-drama needs Python 3.10 or newer")

ASSET_KINDS = frozenset(
    {"character", "creature", "location", "prop", "vehicle", "effect"}
)
TIERS = frozenset({"full", "compact"})
FRAGMENT_KINDS = frozenset(
    {
        "style_core",
        "identity_full",
        "continuity_lock",
        "variant_delta",
        "view_projection",
        "negative_lock",
    }
)
PROMPT_PROFILES = frozenset({"asset_board", "keyframe", "motion"})
HASH_RE = re.compile(r"[0-9a-f]{64}")


def _reject_json_constant(value: str) -> Any:
    raise json.JSONDecodeError(f"non-finite JSON number is not allowed: {value}", value, 0)


def _json_loads(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_json_constant)
AMBIGUOUS = frozenset(
    {"待定", "待确认", "未知", "unknown", "tbd", "todo", "n/a", "na"}
)

GENERATION_FILES = {
    "scope": "asset-scope.jsonl",
    "models": "asset-models.jsonl",
    "spatial": "spatial-models.jsonl",
    "variants": "variant-models.jsonl",
    "views": "view-contracts.jsonl",
    "summary": "asset-baseline.md",
    "fragments": "canonical-fragments.jsonl",
    "library": "canonical-prompt-library.md",
}


class BaselineCheckError(ValueError):
    """The baseline cannot be inspected."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def record_hash(record: Mapping[str, Any], *, hash_field: str) -> str:
    material = {key: value for key, value in record.items() if key != hash_field}
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def _load_jsonl(path: Path, *, required: bool = True) -> list[dict[str, Any]]:
    if not path.is_file():
        if required:
            raise BaselineCheckError(f"missing baseline file: {path}")
        return []
    records: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BaselineCheckError(f"cannot read baseline file: {path}") from error
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = _json_loads(line)
        except json.JSONDecodeError as error:
            raise BaselineCheckError(f"invalid JSONL at {path.name}:{number}") from error
        if not isinstance(value, dict):
            raise BaselineCheckError(f"JSONL record must be an object: {path.name}:{number}")
        records.append(value)
    return records


def _nonempty(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped.casefold() not in AMBIGUOUS
    if isinstance(value, list):
        return bool(value) and all(_nonempty(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(
            (isinstance(item, list) and not item) or _nonempty(item)
            for item in value.values()
        )
    return True


def _id(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _finding(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _require_fields(
    findings: list[dict[str, Any]],
    record: Mapping[str, Any],
    record_id: str,
    fields: Iterable[str],
    *,
    code: str,
    allow_empty: Iterable[str] = (),
) -> None:
    empty_allowed = set(allow_empty)
    for field in fields:
        value = record.get(field)
        if field in empty_allowed and isinstance(value, list):
            valid = all(_nonempty(item) for item in value)
        else:
            valid = _nonempty(value)
        if not valid:
            findings.append(
                _finding(code, f"{record_id} missing non-ambiguous field: {field}", record_id=record_id)
            )


def validate_m15a(directory: Path) -> dict[str, Any]:
    directory = directory.resolve()
    findings: list[dict[str, Any]] = []
    scope = _load_jsonl(directory / GENERATION_FILES["scope"])
    models = _load_jsonl(directory / GENERATION_FILES["models"])
    spatial = _load_jsonl(directory / GENERATION_FILES["spatial"])
    variants = _load_jsonl(directory / GENERATION_FILES["variants"])
    views = _load_jsonl(directory / GENERATION_FILES["views"])
    summary = directory / GENERATION_FILES["summary"]
    if not summary.is_file() or not summary.read_text(encoding="utf-8").strip():
        findings.append(_finding("M15_SUMMARY_MISSING", "asset-baseline.md is missing or empty"))

    scope_by_asset: dict[str, dict[str, Any]] = {}
    for record in scope:
        asset_id = _id(record, "asset_id")
        kind = record.get("asset_kind")
        tier = record.get("tier")
        if not asset_id:
            findings.append(_finding("M15_SCOPE_ID", "scope record has no asset_id"))
            continue
        if asset_id in scope_by_asset:
            findings.append(_finding("M15_SCOPE_DUPLICATE", f"duplicate scope asset_id: {asset_id}"))
            continue
        scope_by_asset[asset_id] = record
        if kind not in ASSET_KINDS:
            findings.append(_finding("M15_SCOPE_KIND", f"{asset_id} has unsupported asset_kind: {kind}"))
        if tier not in TIERS:
            findings.append(_finding("M15_SCOPE_TIER", f"{asset_id} has unsupported tier: {tier}"))
        _require_fields(
            findings,
            record,
            asset_id,
            ("classification_reasons", "reuse_scope", "creator_acceptance"),
            code="M15_SCOPE_FIELD",
        )
        acceptance = record.get("creator_acceptance")
        if not isinstance(acceptance, dict) or acceptance.get("status") != "accepted":
            findings.append(_finding("M15_SCOPE_ACCEPTANCE", f"{asset_id} scope is not creator accepted"))
    if not scope_by_asset:
        findings.append(_finding("M15_SCOPE_EMPTY", "asset-scope.jsonl must contain at least one accepted asset"))

    model_records = [(record, "asset-models.jsonl") for record in models] + [
        (record, "spatial-models.jsonl") for record in spatial
    ]
    model_by_asset: dict[str, dict[str, Any]] = {}
    models_by_id: dict[str, tuple[str, str, str]] = {}
    for record, filename in model_records:
        asset_id = _id(record, "asset_id", "location_id")
        model_id = _id(record, "model_id")
        if not asset_id:
            findings.append(_finding("M15_MODEL_ID", "model record has no asset_id/location_id"))
            continue
        if not model_id:
            findings.append(_finding("M15_MODEL_ID", f"{asset_id} model has no model_id"))
        else:
            if model_id in models_by_id:
                findings.append(_finding("M15_MODEL_ID", f"duplicate model_id: {model_id}"))
            models_by_id[model_id] = (
                asset_id,
                hashlib.sha256(canonical_json_bytes(record)).hexdigest(),
                filename,
            )
        if asset_id in model_by_asset:
            findings.append(_finding("M15_MODEL_DUPLICATE", f"duplicate model for {asset_id}"))
        model_by_asset[asset_id] = record
        if asset_id not in scope_by_asset:
            findings.append(_finding("M15_MODEL_SCOPE", f"model exists for unscoped asset: {asset_id}"))
        if record.get("asset_kind") == "location" and filename != "spatial-models.jsonl":
            findings.append(_finding("M15_MODEL_FILE", f"location model must be in spatial-models.jsonl: {asset_id}"))
        if record.get("asset_kind") != "location" and filename != "asset-models.jsonl":
            findings.append(_finding("M15_MODEL_FILE", f"non-location model must be in asset-models.jsonl: {asset_id}"))

    common_full = (
        "scale",
        "proportions",
        "silhouette",
        "materials",
        "intrinsic_colors",
        "structure_layers",
        "permanent_marks",
        "asymmetry",
        "allowed_changes",
        "forbidden_drift",
        "text_policy",
    )
    compact = (
        "scale",
        "silhouette",
        "materials",
        "intrinsic_colors",
        "recognition_anchors",
        "state_boundary",
        "forbidden_drift",
        "standard_view",
    )
    kind_fields = {
        "character": ("head_face", "body", "hair", "limbs", "neutral_pose", "relative_scale"),
        "creature": ("head_face", "body", "covering", "limbs", "neutral_pose", "relative_scale"),
        "prop": ("orthographic_forms", "part_connections", "moving_parts", "function_interfaces", "handling", "permanent_wear"),
        "vehicle": ("orthographic_forms", "part_connections", "moving_parts", "function_interfaces", "occupancy", "permanent_wear"),
        "effect": ("emission_source", "targets", "shape", "effect_scale", "color_hierarchy", "material_response", "start_state", "peak_state", "end_state", "preserve_set"),
    }
    spatial_fields = (
        "coordinate_system",
        "dimensions",
        "functional_zones",
        "entrances",
        "connections",
        "fixed_anchors",
        "pairwise_relations",
        "movement_paths",
        "occlusions",
        "fixed_light_sources",
        "dressing_boundary",
        "forbidden_drift",
    )
    for asset_id, scope_record in scope_by_asset.items():
        model = model_by_asset.get(asset_id)
        if model is None:
            findings.append(_finding("M15_MODEL_MISSING", f"no model for scoped asset {asset_id}"))
            continue
        kind = scope_record.get("asset_kind")
        tier = scope_record.get("tier")
        if model.get("asset_kind") != kind:
            findings.append(_finding("M15_MODEL_KIND", f"{asset_id} model kind does not match scope"))
        if model.get("tier") != tier:
            findings.append(_finding("M15_MODEL_TIER", f"{asset_id} model tier does not match scope"))
        fields = (
            compact
            if tier == "compact"
            else common_full + spatial_fields
            if kind == "location"
            else common_full + kind_fields.get(str(kind), ())
        )
        _require_fields(
            findings,
            model,
            asset_id,
            fields,
            code="M15_MODEL_FIELD",
            allow_empty=("permanent_marks", "asymmetry"),
        )
        if tier == "compact":
            anchors = model.get("recognition_anchors")
            if not isinstance(anchors, list) or not 2 <= len(anchors) <= 4:
                findings.append(
                    _finding(
                        "M15_MODEL_ANCHORS",
                        f"{asset_id} compact model needs 2-4 recognition_anchors",
                        record_id=asset_id,
                    )
                )

    view_assets: set[str] = set()
    seen_views: set[str] = set()
    for record in views:
        view_id = _id(record, "view_id") or "<unknown-view>"
        if view_id in seen_views:
            findings.append(_finding("M15_VIEW_DUPLICATE", f"duplicate view_id: {view_id}"))
        seen_views.add(view_id)
        asset_id = _id(record, "asset_id")
        if not asset_id:
            findings.append(_finding("M15_VIEW_ASSET", f"{view_id} has no asset_id"))
            continue
        view_assets.add(asset_id)
        if asset_id not in scope_by_asset:
            findings.append(_finding("M15_VIEW_ASSET", f"{view_id} references an unscoped asset: {asset_id}"))
        _require_fields(
            findings,
            record,
            view_id,
            ("orientation", "must_show", "must_preserve", "must_not_change"),
            code="M15_VIEW_FIELD",
        )
        model_ref = record.get("model_ref")
        if not isinstance(model_ref, dict):
            findings.append(_finding("M15_VIEW_MODEL_REF", f"{view_id} has no model_ref"))
        else:
            model_id = model_ref.get("record_id")
            expected = models_by_id.get(str(model_id))
            if expected is None or expected[0] != asset_id:
                findings.append(_finding("M15_VIEW_MODEL_REF", f"{view_id} references the wrong model"))
            elif model_ref.get("record_hash") != expected[1]:
                findings.append(_finding("M15_VIEW_MODEL_STALE", f"{view_id} model_ref record_hash is stale"))
            elif Path(str(model_ref.get("artifact", ""))).name != expected[2]:
                findings.append(_finding("M15_VIEW_MODEL_REF", f"{view_id} references the wrong model artifact"))
    for asset_id in scope_by_asset:
        if asset_id not in view_assets:
            findings.append(_finding("M15_VIEW_MISSING", f"no view contract for scoped asset {asset_id}"))

    seen_variants: set[str] = set()
    for record in variants:
        variant_id = _id(record, "variant_id") or "<unknown-variant>"
        if variant_id in seen_variants:
            findings.append(_finding("M15_VARIANT_DUPLICATE", f"duplicate variant_id: {variant_id}"))
        seen_variants.add(variant_id)
        _require_fields(
            findings,
            record,
            variant_id,
            ("base_asset_id", "base_model_ref", "changes", "preserve", "validity"),
            code="M15_VARIANT_FIELD",
        )
        base_asset_id = record.get("base_asset_id")
        if isinstance(base_asset_id, str) and base_asset_id not in scope_by_asset:
            findings.append(
                _finding(
                    "M15_VARIANT_BASE",
                    f"{variant_id} references an unknown or unscoped base asset: {base_asset_id}",
                )
            )
        base_model_ref = record.get("base_model_ref")
        if isinstance(base_asset_id, str) and isinstance(base_model_ref, dict):
            base_model_id = base_model_ref.get("record_id")
            expected = models_by_id.get(str(base_model_id))
            if expected is None or expected[0] != base_asset_id:
                findings.append(
                    _finding(
                        "M15_VARIANT_MODEL_REF",
                        f"{variant_id} references the wrong base model",
                    )
                )
            elif base_model_ref.get("record_hash") != expected[1]:
                findings.append(
                    _finding(
                        "M15_VARIANT_MODEL_STALE",
                        f"{variant_id} base_model_ref record_hash is stale",
                    )
                )
            elif Path(str(base_model_ref.get("artifact", ""))).name != expected[2]:
                findings.append(
                    _finding(
                        "M15_VARIANT_MODEL_REF",
                        f"{variant_id} references the wrong base model artifact",
                    )
                )

    return {
        "status": "pass" if not findings else "fail",
        "findings": findings,
        "counts": {
            "scope": len(scope),
            "models": len(models),
            "spatial_models": len(spatial),
            "variants": len(variants),
            "views": len(views),
        },
    }


def validate_fragments(directory: Path, *, prompt_language: str) -> dict[str, Any]:
    directory = directory.resolve()
    findings: list[dict[str, Any]] = []
    scope = _load_jsonl(directory / GENERATION_FILES["scope"])
    fragments = _load_jsonl(directory / GENERATION_FILES["fragments"])
    library = directory / GENERATION_FILES["library"]
    if not library.is_file() or not library.read_text(encoding="utf-8").strip():
        findings.append(_finding("M15_FRAGMENT_LIBRARY", "canonical-prompt-library.md is missing or empty"))

    scoped = {record.get("asset_id") for record in scope if isinstance(record.get("asset_id"), str)}
    variants = _load_jsonl(directory / GENERATION_FILES["variants"])
    views = _load_jsonl(directory / GENERATION_FILES["views"])
    variant_ids = {
        record.get("variant_id")
        for record in variants
        if isinstance(record.get("variant_id"), str)
    }
    generation_records: dict[str, tuple[str, str, str]] = {}
    for filename in (
        GENERATION_FILES["models"],
        GENERATION_FILES["spatial"],
        GENERATION_FILES["variants"],
        GENERATION_FILES["views"],
    ):
        for model_record in _load_jsonl(directory / filename):
            record_id = _id(model_record, "model_id", "variant_id", "view_id")
            if record_id:
                if record_id in generation_records:
                    findings.append(
                        _finding(
                            "M15_GENERATION_ID_DUPLICATE",
                            f"generation record_id is not globally unique: {record_id}",
                        )
                    )
                generation_records[record_id] = (
                    filename,
                    hashlib.sha256(canonical_json_bytes(model_record)).hexdigest(),
                    str(model_record.get("asset_id") or model_record.get("location_id") or model_record.get("base_asset_id") or ""),
                )
    kinds_by_asset: dict[str, dict[str, int]] = {asset_id: {} for asset_id in scoped}
    global_style_count = 0
    project_root = directory.parent.parent
    fragment_variants: dict[str, int] = {}
    fragment_views: dict[str, int] = {}
    seen: set[str] = set()
    for record in fragments:
        fragment_id = _id(record, "fragment_id")
        kind = record.get("fragment_kind")
        if not fragment_id:
            findings.append(_finding("M15_FRAGMENT_ID", "fragment has no fragment_id"))
            continue
        if fragment_id in seen:
            findings.append(_finding("M15_FRAGMENT_DUPLICATE", f"duplicate fragment_id: {fragment_id}"))
        seen.add(fragment_id)
        if kind not in FRAGMENT_KINDS:
            findings.append(_finding("M15_FRAGMENT_KIND", f"{fragment_id} has unsupported fragment_kind: {kind}"))
        if record.get("language") != prompt_language:
            findings.append(_finding("M15_FRAGMENT_LANGUAGE", f"{fragment_id} language does not match project prompt_language"))
        _require_fields(
            findings,
            record,
            fragment_id,
            ("scope", "input_hashes", "text", "fragment_hash"),
            code="M15_FRAGMENT_FIELD",
        )
        fragment_scope = record.get("scope")
        if not isinstance(fragment_scope, dict) or not fragment_scope:
            findings.append(_finding("M15_FRAGMENT_SCOPE", f"{fragment_id} has invalid scope"))
        elif kind == "style_core":
            if fragment_scope.get("project") != "all_visual_generation":
                findings.append(_finding("M15_FRAGMENT_SCOPE", f"{fragment_id} style_core scope is invalid"))
        elif kind == "view_projection":
            if not isinstance(fragment_scope.get("view_id"), str):
                findings.append(_finding("M15_FRAGMENT_SCOPE", f"{fragment_id} view scope needs view_id"))
        else:
            jobs = fragment_scope.get("jobs")
            if (
                not isinstance(jobs, list)
                or not jobs
                or any(job not in PROMPT_PROFILES for job in jobs)
                or len(jobs) != len(set(jobs))
            ):
                findings.append(_finding("M15_FRAGMENT_SCOPE", f"{fragment_id} has invalid jobs scope"))
            elif kind in {"identity_full", "continuity_lock", "negative_lock"} and set(jobs) != PROMPT_PROFILES:
                findings.append(
                    _finding(
                        "M15_FRAGMENT_SCOPE",
                        f"{fragment_id} must cover asset_board, keyframe, and motion",
                    )
                )
        input_hashes = record.get("input_hashes")
        hashes = input_hashes.values() if isinstance(input_hashes, dict) else input_hashes if isinstance(input_hashes, list) else []
        if not hashes or any(not isinstance(value, str) or HASH_RE.fullmatch(value) is None for value in hashes):
            findings.append(_finding("M15_FRAGMENT_INPUT_HASH", f"{fragment_id} has invalid input_hashes"))
        model_refs = record.get("model_refs")
        if not isinstance(model_refs, list) or not model_refs:
            findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} needs model_refs"))
        else:
            for reference in model_refs:
                if not isinstance(reference, dict):
                    findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} has invalid model_ref"))
                    continue
                artifact = reference.get("artifact")
                record_id = reference.get("record_id")
                if artifact == "short-drama.json":
                    project_file = project_root / artifact
                    if not project_file.is_file():
                        findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} project model_ref is unavailable"))
                        continue
                    try:
                        project = _json_loads(project_file.read_text(encoding="utf-8"))
                        field = reference.get("field")
                        if field == "/creator_authority/visual_direction":
                            value = project["creator_authority"]["visual_direction"]
                        elif field == "/format/prompt_language":
                            value = project["format"]["prompt_language"]
                        else:
                            raise KeyError(str(field))
                    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
                        findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} has an invalid project field ref"))
                        continue
                    live_record_hash = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
                    if reference.get("record_hash") != live_record_hash or (
                        isinstance(input_hashes, dict) and input_hashes.get(str(field)) != live_record_hash
                    ):
                        findings.append(_finding("M15_FRAGMENT_STALE", f"{fragment_id} project record hash is stale: {field}"))
                    continue
                if not isinstance(artifact, str) or not artifact.startswith("设定集/generation/"):
                    findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} references an unsupported model artifact"))
                    continue
                expected = generation_records.get(str(record_id))
                if expected is None or Path(artifact).name != expected[0]:
                    findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} references unknown generation record: {record_id}"))
                    continue
                bound = input_hashes.get(record_id) if isinstance(input_hashes, dict) else None
                if bound != expected[1]:
                    findings.append(_finding("M15_FRAGMENT_STALE", f"{fragment_id} input hash is stale for {record_id}"))
                if reference.get("record_hash") != expected[1]:
                    findings.append(_finding("M15_FRAGMENT_STALE", f"{fragment_id} model_ref record_hash is stale for {record_id}"))
        expected = record_hash(record, hash_field="fragment_hash")
        if record.get("fragment_hash") != expected:
            findings.append(_finding("M15_FRAGMENT_HASH", f"{fragment_id} fragment_hash does not match content"))
        asset_id = record.get("asset_id")
        if kind == "style_core" and not asset_id:
            global_style_count += 1
            project_fields = {
                reference.get("field")
                for reference in model_refs or []
                if isinstance(reference, dict) and reference.get("artifact") == "short-drama.json"
            }
            required_project_fields = {
                "/creator_authority/visual_direction",
                "/format/prompt_language",
            }
            if project_fields != required_project_fields:
                findings.append(
                    _finding(
                        "M15_STYLE_CORE",
                        f"{fragment_id} must bind visual_direction and prompt_language records",
                    )
                )
        if isinstance(asset_id, str) and asset_id in kinds_by_asset and isinstance(kind, str):
            kinds_by_asset[asset_id][kind] = kinds_by_asset[asset_id].get(kind, 0) + 1
        elif kind != "style_core":
            findings.append(_finding("M15_FRAGMENT_ASSET", f"{fragment_id} references an unknown or missing asset_id"))
        if isinstance(asset_id, str):
            resolved_generation_refs = [
                (reference, expected)
                for reference in model_refs or []
                if isinstance(reference, dict)
                and (expected := generation_records.get(str(reference.get("record_id")))) is not None
            ]
            generation_asset_ids = {expected[2] for _, expected in resolved_generation_refs}
            if generation_asset_ids and generation_asset_ids != {asset_id}:
                findings.append(_finding("M15_FRAGMENT_ASSET", f"{fragment_id} model_refs do not belong to {asset_id}"))
            artifacts = {expected[0] for _, expected in resolved_generation_refs}
            expected_artifacts = {
                "identity_full": {GENERATION_FILES["models"], GENERATION_FILES["spatial"]},
                "continuity_lock": {GENERATION_FILES["models"], GENERATION_FILES["spatial"]},
                "negative_lock": {GENERATION_FILES["models"], GENERATION_FILES["spatial"]},
                "variant_delta": {
                    GENERATION_FILES["variants"],
                    GENERATION_FILES["models"],
                    GENERATION_FILES["spatial"],
                },
                "view_projection": {GENERATION_FILES["views"]},
            }.get(str(kind), set())
            if expected_artifacts and (not artifacts or not artifacts <= expected_artifacts):
                findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} references the wrong generation record type"))
            if kind == "view_projection":
                view_id = fragment_scope.get("view_id") if isinstance(fragment_scope, dict) else None
                if not any(reference.get("record_id") == view_id for reference, _ in resolved_generation_refs):
                    findings.append(_finding("M15_FRAGMENT_SCOPE", f"{fragment_id} view scope does not match model_refs"))
                elif isinstance(view_id, str):
                    fragment_views[view_id] = fragment_views.get(view_id, 0) + 1
        variant_id = record.get("variant_id")
        if kind == "variant_delta" and isinstance(variant_id, str):
            fragment_variants[variant_id] = fragment_variants.get(variant_id, 0) + 1
            if not any(
                reference.get("record_id") == variant_id
                for reference in model_refs or []
                if isinstance(reference, dict)
            ):
                findings.append(_finding("M15_FRAGMENT_MODEL_REF", f"{fragment_id} variant_id does not match model_refs"))
            variant_record = next(
                (
                    item
                    for item in variants
                    if item.get("variant_id") == variant_id
                ),
                None,
            )
            base_model_ref = (
                variant_record.get("base_model_ref")
                if isinstance(variant_record, dict)
                else None
            )
            base_model_id = (
                base_model_ref.get("record_id")
                if isinstance(base_model_ref, dict)
                else None
            )
            if not isinstance(base_model_id, str) or not any(
                reference.get("record_id") == base_model_id
                for reference in model_refs or []
                if isinstance(reference, dict)
            ):
                findings.append(
                    _finding(
                        "M15_FRAGMENT_MODEL_REF",
                        f"{fragment_id} does not bind the variant base model",
                    )
                )

    if global_style_count != 1:
        findings.append(_finding("M15_STYLE_CORE", "exactly one project-level style_core fragment is required"))
    required = {"identity_full", "continuity_lock", "view_projection", "negative_lock"}
    for asset_id, counts in kinds_by_asset.items():
        missing = sorted(kind for kind in required if counts.get(kind, 0) == 0)
        if missing:
            findings.append(_finding("M15_FRAGMENT_COVERAGE", f"{asset_id} missing fragments: {', '.join(missing)}"))
        for kind in ("identity_full", "continuity_lock", "negative_lock"):
            if counts.get(kind, 0) != 1:
                findings.append(_finding("M15_FRAGMENT_COVERAGE", f"{asset_id} needs exactly one {kind} fragment"))
    for variant_id in sorted(variant_ids):
        count = fragment_variants.get(variant_id, 0)
        if count != 1:
            findings.append(
                _finding(
                    "M15_FRAGMENT_VARIANT",
                    f"{variant_id} needs exactly one variant_delta fragment",
                )
            )
    view_ids = {
        record.get("view_id")
        for record in views
        if isinstance(record.get("view_id"), str)
    }
    for view_id in sorted(view_ids):
        count = fragment_views.get(view_id, 0)
        if count != 1:
            findings.append(
                _finding(
                    "M15_FRAGMENT_VIEW",
                    f"{view_id} needs exactly one view_projection fragment",
                )
            )
    return {
        "status": "pass" if not findings else "fail",
        "findings": findings,
        "counts": {"fragments": len(fragments), "assets": len(scoped)},
    }


def check(directory: Path, *, prompt_language: str) -> dict[str, Any]:
    m15a = validate_m15a(directory)
    m15b = validate_fragments(directory, prompt_language=prompt_language)
    return {
        "status": "pass" if m15a["status"] == m15b["status"] == "pass" else "fail",
        "m15a": m15a,
        "m15b": m15b,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--prompt-language", default="en")
    args = parser.parse_args(argv)
    try:
        result = check(args.directory, prompt_language=args.prompt_language)
    except BaselineCheckError as error:
        print(
            json.dumps(
                {"status": "error", "error": str(error)},
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
