#!/usr/bin/env python3
"""Validate model-call generation clips against accepted shots and motions."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


MINIMUM_PYTHON = (3, 10)
if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        "short-drama needs Python {}.{} or newer; this interpreter is {}.{}".format(
            *MINIMUM_PYTHON, sys.version_info.major, sys.version_info.minor
        )
    )

SCHEMA_VERSION = "1.0.0"
DEFAULT_MAX_CLIP_SECONDS = 15.0
TOLERANCE_SECONDS = 1e-6
EXECUTION_MODES = frozenset({"independent", "continuation"})
BOUNDARY_FIELDS = (
    "pose",
    "position",
    "gaze",
    "hands_and_props",
    "visible_state",
)


class CheckError(ValueError):
    """The input files cannot be checked at all."""


def _reject_json_constant(value: str) -> Any:
    raise json.JSONDecodeError(
        f"non-finite JSON number is not allowed: {value}", value, 0
    )


def _json_loads(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_json_constant)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = _json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckError(f"unreadable JSON: {path}") from error
    if not isinstance(document, dict):
        raise CheckError(f"expected a JSON object: {path}")
    return document


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CheckError(f"unreadable JSONL: {path}") from error
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = _json_loads(line)
        except json.JSONDecodeError as error:
            raise CheckError(f"invalid JSONL at {path.name}:{line_number}") from error
        if not isinstance(record, dict):
            raise CheckError(
                f"JSONL needs one object per line: {path.name}:{line_number}"
            )
        records.append(record)
    return records


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _record_id(reference: Any) -> str | None:
    if not isinstance(reference, dict):
        return None
    value = reference.get("record_id")
    return value if isinstance(value, str) and value else None


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def _observation_ref(reference: Any) -> dict[str, Any] | None:
    if not isinstance(reference, dict):
        return None
    owner = reference.get("owner")
    artifact = reference.get("artifact")
    digest = reference.get("hash")
    if (
        not isinstance(owner, str)
        or not owner
        or not isinstance(artifact, str)
        or not artifact
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return None
    return reference


def _finding(code: str, message: str, **detail: Any) -> dict[str, Any]:
    return {
        "code": code,
        "rule": "VID-22",
        "severity": "error",
        "message": message,
        **detail,
    }


def _generation_limits(
    project: dict[str, Any],
) -> tuple[float | None, bool, str]:
    format_block = project.get("format")
    limits = (
        format_block.get("generation_limits")
        if isinstance(format_block, dict)
        else None
    )
    if limits is None:
        return DEFAULT_MAX_CLIP_SECONDS, False, "default"
    if not isinstance(limits, dict):
        return None, False, "invalid"
    maximum = _finite_number(limits.get("max_clip_seconds"))
    if maximum is None or maximum <= 0:
        return None, False, "invalid"
    continuation = limits.get("continuation_supported", False)
    if not isinstance(continuation, bool):
        return None, False, "invalid"
    return maximum, continuation, "project"


def check(
    clips: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    motions: list[dict[str, Any]],
    project: dict[str, Any],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    maximum, continuation_supported, limit_source = _generation_limits(project)
    if maximum is None:
        findings.append(
            _finding(
                "GCLIP_CONFIG_INVALID",
                "format.generation_limits needs a positive max_clip_seconds and "
                "a boolean continuation_supported",
            )
        )
        maximum = DEFAULT_MAX_CLIP_SECONDS

    shots_by_id = {
        shot["shot_id"]: shot
        for shot in shots
        if isinstance(shot.get("shot_id"), str) and shot.get("shot_id")
    }
    motions_by_id = {
        motion["motion_id"]: motion
        for motion in motions
        if isinstance(motion.get("motion_id"), str) and motion.get("motion_id")
    }
    clips_by_shot: dict[str, list[dict[str, Any]]] = {}
    seen_clip_ids: set[str] = set()

    for index, clip in enumerate(clips):
        clip_id = clip.get("clip_id")
        if not isinstance(clip_id, str) or not clip_id:
            findings.append(
                _finding(
                    "GCLIP_ID_MISSING",
                    "a generation clip has no clip_id",
                    record_index=index,
                )
            )
            clip_id = f"<record-{index}>"
        elif clip_id in seen_clip_ids:
            findings.append(
                _finding(
                    "GCLIP_ID_DUPLICATE",
                    "generation clip IDs must be unique",
                    clip_id=clip_id,
                )
            )
        seen_clip_ids.add(clip_id)

        shot_id = _record_id(clip.get("shot_ref"))
        if shot_id not in shots_by_id:
            findings.append(
                _finding(
                    "GCLIP_SHOT_REF_UNRESOLVED",
                    "generation clip does not reference an accepted episode shot",
                    clip_id=clip_id,
                    shot_id=shot_id,
                )
            )
            continue

        motion_id = _record_id(clip.get("motion_ref"))
        motion = motions_by_id.get(motion_id or "")
        if motion is None:
            findings.append(
                _finding(
                    "GCLIP_MOTION_REF_UNRESOLVED",
                    "generation clip does not reference an episode motion spec",
                    clip_id=clip_id,
                    motion_id=motion_id,
                )
            )
        elif _record_id(motion.get("shot_ref")) != shot_id:
            findings.append(
                _finding(
                    "GCLIP_MOTION_SHOT_MISMATCH",
                    "generation clip motion_ref belongs to a different shot",
                    clip_id=clip_id,
                    shot_id=shot_id,
                    motion_id=motion_id,
                )
            )
        clips_by_shot.setdefault(shot_id, []).append(clip)

    for shot_id, shot in shots_by_id.items():
        shot_duration = _finite_number(shot.get("duration_seconds"))
        if shot_duration is None or shot_duration <= 0:
            findings.append(
                _finding(
                    "GCLIP_SHOT_DURATION_INVALID",
                    "a shot needs a positive duration before generation clips can be planned",
                    shot_id=shot_id,
                )
            )
            continue
        shot_clips = clips_by_shot.get(shot_id, [])
        if not shot_clips:
            findings.append(
                _finding(
                    "GCLIP_SHOT_UNCOVERED",
                    "an accepted shot has no generation clips",
                    shot_id=shot_id,
                )
            )
            continue

        valid_orders = [
            clip.get("order")
            for clip in shot_clips
            if isinstance(clip.get("order"), int)
            and not isinstance(clip.get("order"), bool)
        ]
        if sorted(valid_orders) != list(range(1, len(shot_clips) + 1)):
            findings.append(
                _finding(
                    "GCLIP_ORDER_INVALID",
                    "clip order must be unique and contiguous from 1 within each shot",
                    shot_id=shot_id,
                    orders=valid_orders,
                )
            )
        ordered = sorted(
            shot_clips,
            key=lambda clip: (
                clip.get("order")
                if isinstance(clip.get("order"), int)
                and not isinstance(clip.get("order"), bool)
                else 10**9
            ),
        )
        cursor = 0.0
        previous_id: str | None = None
        for position, clip in enumerate(ordered, start=1):
            clip_id = str(clip.get("clip_id") or f"<shot-{shot_id}-{position}>")
            window = clip.get("source_window")
            start = (
                _finite_number(window.get("start_seconds"))
                if isinstance(window, dict)
                else None
            )
            end = (
                _finite_number(window.get("end_seconds"))
                if isinstance(window, dict)
                else None
            )
            duration = _finite_number(clip.get("duration_seconds"))
            if start is None or end is None or duration is None or end <= start:
                findings.append(
                    _finding(
                        "GCLIP_WINDOW_INVALID",
                        "clip needs a positive source_window and duration_seconds",
                        clip_id=clip_id,
                        shot_id=shot_id,
                    )
                )
                continue
            if abs((end - start) - duration) > TOLERANCE_SECONDS:
                findings.append(
                    _finding(
                        "GCLIP_DURATION_MISMATCH",
                        "duration_seconds does not equal source_window length",
                        clip_id=clip_id,
                        stated=duration,
                        computed=round(end - start, 6),
                    )
                )
            if duration - maximum > TOLERANCE_SECONDS:
                findings.append(
                    _finding(
                        "GCLIP_DURATION_EXCEEDS_LIMIT",
                        "generation clip exceeds the project model-call limit",
                        clip_id=clip_id,
                        duration_seconds=duration,
                        max_clip_seconds=maximum,
                    )
                )
            if abs(start - cursor) > TOLERANCE_SECONDS:
                findings.append(
                    _finding(
                        "GCLIP_COVERAGE_GAP_OR_OVERLAP",
                        "generation clips must cover the shot without gaps or overlaps",
                        clip_id=clip_id,
                        expected_start=round(cursor, 6),
                        actual_start=start,
                    )
                )

            execution_mode = clip.get("execution_mode")
            if execution_mode not in EXECUTION_MODES:
                findings.append(
                    _finding(
                        "GCLIP_EXECUTION_MODE_INVALID",
                        "execution_mode must be independent or continuation",
                        clip_id=clip_id,
                    )
                )
            elif execution_mode == "continuation" and not continuation_supported:
                findings.append(
                    _finding(
                        "GCLIP_CONTINUATION_UNSUPPORTED",
                        "clip requests continuation but the project profile disables it",
                        clip_id=clip_id,
                    )
                )

            start_source = clip.get("start_source")
            handoff = clip.get("handoff")
            if position == 1:
                if (
                    start_source != "shot_start"
                    or handoff not in (None, {})
                    or execution_mode != "independent"
                ):
                    findings.append(
                        _finding(
                            "GCLIP_FIRST_START_INVALID",
                            "the first clip must independently start from shot_start "
                            "without a handoff",
                            clip_id=clip_id,
                        )
                    )
            else:
                from_clip_id = (
                    handoff.get("from_clip_id")
                    if isinstance(handoff, dict)
                    else None
                )
                planned_boundary = (
                    handoff.get("planned_boundary")
                    if isinstance(handoff, dict)
                    else None
                )
                if (
                    start_source != "previous_clip_end"
                    or from_clip_id != previous_id
                    or not isinstance(planned_boundary, dict)
                    or not planned_boundary
                ):
                    findings.append(
                        _finding(
                            "GCLIP_HANDOFF_INVALID",
                            "later clips must bind the immediate previous clip and a "
                            "non-empty planned boundary",
                            clip_id=clip_id,
                            expected_from_clip_id=previous_id,
                        )
                    )
                elif any(
                    field not in planned_boundary
                    or not _meaningful(planned_boundary.get(field))
                    for field in BOUNDARY_FIELDS
                ):
                    findings.append(
                        _finding(
                            "GCLIP_HANDOFF_BOUNDARY_INCOMPLETE",
                            "planned_boundary must carry pose, position, gaze, "
                            "hands_and_props and visible_state",
                            clip_id=clip_id,
                        )
                    )
                if execution_mode == "continuation":
                    observation = (
                        _observation_ref(handoff.get("observation_ref"))
                        if isinstance(handoff, dict)
                        else None
                    )
                    previous_observation = _observation_ref(
                        ordered[position - 2].get("output_observation_ref")
                    )
                    if observation is None or previous_observation != observation:
                        findings.append(
                            _finding(
                                "GCLIP_CONTINUATION_OBSERVATION_MISSING",
                                "continuation must bind the immediate previous clip's "
                                "authorized output observation",
                                clip_id=clip_id,
                                previous_clip_id=previous_id,
                            )
                        )
            cursor = end
            previous_id = clip_id

        if abs(cursor - shot_duration) > TOLERANCE_SECONDS:
            findings.append(
                _finding(
                    "GCLIP_SHOT_COVERAGE_INCOMPLETE",
                    "generation clips do not end at the accepted shot duration",
                    shot_id=shot_id,
                    covered_until=round(cursor, 6),
                    shot_duration_seconds=shot_duration,
                )
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "generation_clips": len(clips),
        "covered_shots": len(clips_by_shot),
        "max_clip_seconds": maximum,
        "limit_source": limit_source,
        "continuation_supported": continuation_supported,
        "findings": findings,
        "status": "pass" if not findings else "fail",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generation clips against shots, motions and project limits."
    )
    parser.add_argument("generation_clips", type=Path)
    parser.add_argument("--shots", type=Path, required=True)
    parser.add_argument("--motions", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = check(
            _load_jsonl(args.generation_clips),
            _load_jsonl(args.shots),
            _load_jsonl(args.motions),
            _load_json(args.project),
        )
    except CheckError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
