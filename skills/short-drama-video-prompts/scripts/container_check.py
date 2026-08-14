#!/usr/bin/env python3
"""Reconcile an episode's delivery containers against its shot set.

Two contracts, one run:

- `VID-15` (episode scope): every container can be correct on its own while the
  episode is wrong — a shot packed into two containers bills its seconds twice,
  and a shot packed into none disappears although its dialogue, bindings, and
  keyframe prompts are already done. Neither error is visible from inside a
  single container, so the check is a set comparison at episode scope.
- `VID-13` (container scope, `delivery-container.jsonl.md` "结构校验点"): the
  container record's own claims are locally provable — member order, member
  `accepted_duration` against the shot it references, container duration
  against the member sum, each member's `motion_ref` chain back to the same
  shot, the `binding_chain_equal` proof across members, and a complete
  `membership_basis`.

The script reads accepted creator files and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
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

SCHEMA_VERSION = "1.0.0"


class CheckError(ValueError):
    """The inputs cannot be checked at all, as opposed to failing a check."""


def _reject_json_constant(value: str) -> Any:
    raise json.JSONDecodeError(f"non-finite JSON number is not allowed: {value}", value, 0)


def _json_loads(value: str) -> Any:
    return json.loads(value, parse_constant=_reject_json_constant)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CheckError(f"unreadable JSONL: {path}") from error
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = _json_loads(line)
        except json.JSONDecodeError as error:
            raise CheckError(f"invalid JSONL at {path.name}:{number}") from error
        if not isinstance(record, dict):
            raise CheckError(f"JSONL needs one object per line: {path.name}:{number}")
        records.append(record)
    return records


def _finding(code: str, message: str, **detail: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **detail}


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    return seconds if math.isfinite(seconds) else None


def _member_shot_id(member: Any) -> str | None:
    if not isinstance(member, dict):
        return None
    ref = member.get("shot_ref")
    if isinstance(ref, dict) and isinstance(ref.get("record_id"), str):
        return ref["record_id"]
    return None


def _shot_by_id(shots: list[dict[str, Any]], shot_id: str) -> dict[str, Any] | None:
    for shot in shots:
        if shot.get("shot_id") == shot_id:
            return shot
    return None


def _ref_record_id(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("record_id"), str):
        return value["record_id"]
    return None


def _ref_field(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("field"), str):
        field = value["field"].lstrip("/")
        return field if field else None
    return None


def _resolve_shot_field(
    shots: list[dict[str, Any]], record_id: str, field: str | None
) -> tuple[bool, Any]:
    """Resolve one JSON-pointer-ish field of a shot record by its record_id.

    The templates use flat `/field` pointers (`/duration_seconds`,
    `/location_binding`, `/asset_bindings`); nested pointers are not expected
    here, so a missing or unrecognized field is reported as unresolved rather
    than silently returning None.
    """

    shot = _shot_by_id(shots, record_id)
    if shot is None:
        return False, None
    if field is None or field not in shot:
        return False, None
    return True, shot[field]


def _check_container_structure(
    container: dict[str, Any],
    shots: list[dict[str, Any]],
    motions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    container_id = container.get("container_id")
    members = container.get("members")
    if not isinstance(members, list):
        return [
            _finding(
                "VID13_CONTAINER_HAS_NO_MEMBERS",
                "a container record has no members list",
                container_id=container_id,
            )
        ]

    # VID-13 check 1: members non-empty, order unique, contiguous, ascending.
    orders: list[Any] = []
    for member in members:
        if isinstance(member, dict) and "order" in member:
            orders.append(member["order"])
    if not orders:
        findings.append(
            _finding(
                "VID13_MEMBER_ORDER_MISSING",
                "members carry no order field",
                container_id=container_id,
            )
        )
    elif orders != sorted(orders) or len(set(orders)) != len(orders):
        findings.append(
            _finding(
                "VID13_MEMBER_ORDER_NOT_ASCENDING_UNIQUE",
                "member order must be unique and ascending",
                container_id=container_id,
                orders=orders,
            )
        )
    elif orders != list(range(1, len(orders) + 1)):
        findings.append(
            _finding(
                "VID13_MEMBER_ORDER_NOT_CONTIGUOUS",
                "member order must be contiguous from 1",
                container_id=container_id,
                orders=orders,
            )
        )

    # VID-13 checks 2/3: member accepted_duration vs the referenced shot value,
    # and container_duration vs the member sum.
    member_durations: list[float] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        shot_id = _member_shot_id(member)
        duration_ref = member.get("accepted_duration_ref")
        recorded_id = _ref_record_id(duration_ref)
        field = _ref_field(duration_ref)
        declared = _seconds(member.get("accepted_duration"))
        if recorded_id is None:
            findings.append(
                _finding(
                    "VID13_MEMBER_HAS_NO_DURATION_REF",
                    "a member does not name its duration source",
                    container_id=container_id,
                )
            )
            continue
        resolved, live_value = _resolve_shot_field(shots, recorded_id, field)
        live_seconds = _seconds(live_value) if resolved else None
        if not resolved or live_seconds is None:
            findings.append(
                _finding(
                    "VID13_MEMBER_DURATION_REF_UNRESOLVED",
                    "accepted_duration_ref does not resolve to a shot duration",
                    container_id=container_id,
                    record_id=recorded_id,
                    field=field,
                )
            )
            continue
        if declared is None:
            findings.append(
                _finding(
                    "VID13_MEMBER_ACCEPTED_DURATION_MISSING",
                    "a member carries no numeric accepted_duration",
                    container_id=container_id,
                    shot_id=shot_id,
                )
            )
            continue
        if abs(declared - live_seconds) > 1e-6:
            findings.append(
                _finding(
                    "VID13_MEMBER_ACCEPTED_DURATION_MISMATCH",
                    "member accepted_duration does not match its referenced shot",
                    container_id=container_id,
                    shot_id=shot_id,
                    declared=declared,
                    referenced=live_seconds,
                )
            )
        member_durations.append(declared)
    if member_durations:
        stated = _seconds(container.get("container_duration"))
        if stated is None:
            findings.append(
                _finding(
                    "VID13_CONTAINER_DURATION_MISSING",
                    "container_duration is not a number",
                    container_id=container_id,
                )
            )
        elif abs(stated - sum(member_durations)) > 1e-6:
            findings.append(
                _finding(
                    "VID13_CONTAINER_DURATION_NOT_SUM_OF_ACCEPTED",
                    "container_duration does not equal the accepted member sum",
                    container_id=container_id,
                    stated=stated,
                    computed=round(sum(member_durations), 6),
                )
            )

    # VID-13 check 4: each member's motion_ref resolves to a motion spec whose
    # shot_ref equals the member's shot_ref. Only run when --motions is given.
    if motions is not None:
        motions_by_id = {
            motion.get("motion_id"): motion
            for motion in motions
            if isinstance(motion.get("motion_id"), str)
        }
        for member in members:
            if not isinstance(member, dict):
                continue
            shot_id = _member_shot_id(member)
            motion_ref = member.get("motion_ref")
            motion_id = _ref_record_id(motion_ref)
            if motion_id is None:
                findings.append(
                    _finding(
                        "VID13_MEMBER_HAS_NO_MOTION_REF",
                        "a member does not name its motion spec",
                        container_id=container_id,
                    )
                )
                continue
            motion = motions_by_id.get(motion_id)
            motion_shot = _ref_record_id(motion.get("shot_ref")) if motion else None
            if motion is None or motion_shot is None:
                findings.append(
                    _finding(
                        "VID13_MOTION_REF_UNRESOLVED",
                        "member motion_ref does not resolve to a motion shot_ref",
                        container_id=container_id,
                        motion_id=motion_id,
                    )
                )
                continue
            if motion_shot != shot_id:
                findings.append(
                    _finding(
                        "VID13_MOTION_SHOT_MISMATCH",
                        "member motion spec references a different shot",
                        container_id=container_id,
                        member_shot_id=shot_id,
                        motion_id=motion_id,
                        motion_shot_id=motion_shot,
                    )
                )

    # VID-13 check 5: binding_chain_equal is only provable when every member
    # resolves its location_binding_ref and asset_bindings_ref to identical
    # values.
    binding_claims: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, dict):
            continue
        shot_id = _member_shot_id(member)
        claim: dict[str, Any] = {"member_shot_id": shot_id}
        for key, ref_key in (("location", "location_binding_ref"), ("assets", "asset_bindings_ref")):
            ref = member.get(ref_key)
            resolved, value = _resolve_shot_field(
                shots,
                _ref_record_id(ref) or "",
                _ref_field(ref),
            )
            claim[key] = (value if resolved else f"<unresolved {_ref_field(ref)}>")
        binding_claims.append(claim)
    basis = container.get("membership_basis")
    declared_equal = (
        isinstance(basis, dict) and basis.get("binding_chain_equal") is True
    )
    if binding_claims:
        location_values = {json.dumps(c["location"], sort_keys=True) for c in binding_claims}
        asset_values = {json.dumps(c["assets"], sort_keys=True) for c in binding_claims}
        actually_equal = len(location_values) <= 1 and len(asset_values) <= 1
        if declared_equal and not actually_equal:
            findings.append(
                _finding(
                    "VID13_BINDING_CHAIN_MISDECLARED",
                    "binding_chain_equal is true but member bindings differ",
                    container_id=container_id,
                    members=binding_claims,
                )
            )
        elif actually_equal and not declared_equal:
            findings.append(
                _finding(
                    "VID13_BINDING_CHAIN_NOT_DECLARED",
                    "member bindings are identical but binding_chain_equal is not true",
                    container_id=container_id,
                )
            )

    # VID-13 check 6: membership_basis has all three conclusions.
    if not isinstance(basis, dict):
        findings.append(
            _finding(
                "VID13_MEMBERSHIP_BASIS_MISSING",
                "container carries no membership_basis",
                container_id=container_id,
            )
        )
    else:
        for key in ("source_order_contiguous", "binding_chain_equal", "scene_boundary_not_crossed"):
            value = basis.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                findings.append(
                    _finding(
                        "VID13_MEMBERSHIP_BASIS_INCOMPLETE",
                        "membership_basis leaves a conclusion blank",
                        container_id=container_id,
                        key=key,
                    )
                )

    return findings


def reconcile(
    containers: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    motions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    durations = {
        shot["shot_id"]: _seconds(shot.get("duration_seconds"))
        for shot in shots
        if isinstance(shot.get("shot_id"), str)
    }
    episode_shots = set(durations)

    owner_of: dict[str, str] = {}
    packed: set[str] = set()
    container_total = 0.0
    for container in containers:
        container_id = container.get("container_id")
        if not isinstance(container_id, str):
            findings.append(
                _finding("VID15_CONTAINER_HAS_NO_ID", "a container record has no id")
            )
            continue
        findings.extend(_check_container_structure(container, shots, motions))
        members = container.get("members")
        if not isinstance(members, list) or not members:
            findings.append(
                _finding(
                    "VID15_CONTAINER_HAS_NO_MEMBERS",
                    "a container carries no members",
                    container_id=container_id,
                )
            )
            continue
        member_total = 0.0
        for member in members:
            shot_id = _member_shot_id(member)
            if shot_id is None:
                findings.append(
                    _finding(
                        "VID15_MEMBER_HAS_NO_SHOT_REF",
                        "a member does not name the shot it packs",
                        container_id=container_id,
                    )
                )
                continue
            if shot_id not in episode_shots:
                findings.append(
                    _finding(
                        "VID15_MEMBER_IS_NOT_AN_EPISODE_SHOT",
                        "a container packs a shot that is not in this episode",
                        container_id=container_id,
                        shot_id=shot_id,
                    )
                )
                continue
            previous = owner_of.get(shot_id)
            if previous is not None:
                findings.append(
                    _finding(
                        "VID15_SHOT_PACKED_TWICE",
                        "a shot belongs to more than one container",
                        shot_id=shot_id,
                        container_ids=sorted({previous, container_id}),
                    )
                )
                continue
            owner_of[shot_id] = container_id
            packed.add(shot_id)
            seconds = durations.get(shot_id)
            if seconds is None:
                findings.append(
                    _finding(
                        "VID15_MEMBER_SHOT_HAS_NO_DURATION",
                        "a packed shot carries no numeric duration",
                        container_id=container_id,
                        shot_id=shot_id,
                    )
                )
                continue
            member_total += seconds
        stated = _seconds(container.get("container_duration"))
        if stated is None:
            findings.append(
                _finding(
                    "VID15_CONTAINER_DURATION_MISSING",
                    "container_duration is not a number",
                    container_id=container_id,
                )
            )
        elif abs(stated - member_total) > 1e-6:
            findings.append(
                _finding(
                    "VID15_CONTAINER_DURATION_IS_NOT_THE_SUM",
                    "container_duration does not equal its members' durations",
                    container_id=container_id,
                    stated=stated,
                    computed=round(member_total, 6),
                )
            )
        container_total += member_total

    loose = sorted(episode_shots - packed)
    # A shot whose duration is still open is a legal state upstream, so it is
    # held out of the arithmetic instead of being reported as an error. Only a
    # shot packed into a container must already have one, because the
    # container's own duration claim depends on it.
    unmeasured = sorted(
        shot_id for shot_id in episode_shots if durations.get(shot_id) is None
    )
    loose_total = sum(
        durations[shot_id] or 0.0 for shot_id in loose if durations.get(shot_id) is not None
    )

    episode_total = sum(value for value in durations.values() if value is not None)
    if abs((container_total + loose_total) - episode_total) > 1e-6:
        findings.append(
            _finding(
                "VID15_EPISODE_TOTAL_DOES_NOT_RECONCILE",
                "containers plus loose shots do not add up to the episode total",
                packed_seconds=round(container_total, 6),
                loose_seconds=round(loose_total, 6),
                episode_seconds=round(episode_total, 6),
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "containers": len(containers),
        "episode_shots": len(episode_shots),
        "packed_shots": len(packed),
        # Loose shots are legal: containers need not cover everything. They are
        # reported so the count is a decision rather than an oversight.
        "loose_shots": loose,
        # Reported, not a finding: these shots are excluded from every total
        # above, so a caller can tell an incomplete episode from a wrong one.
        "unmeasured_shots": unmeasured,
        "packed_seconds": round(container_total, 6),
        "loose_seconds": round(loose_total, 6),
        "episode_seconds": round(episode_total, 6),
        "findings": findings,
        "status": "pass" if not findings else "fail",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile delivery containers with the episode's shot set: "
            "VID-13 container structure claims plus VID-15 episode-scope totals."
        )
    )
    parser.add_argument("containers", type=Path, help="the episode containers JSONL")
    parser.add_argument("--shots", type=Path, required=True)
    parser.add_argument(
        "--motions",
        type=Path,
        default=None,
        help=(
            "the episode motion-specs JSONL; when given, VID-13 check 4 "
            "(motion_ref chains back to the member shot) is also run"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    motions: list[dict[str, Any]] | None = (
        _load_jsonl(args.motions) if args.motions is not None else None
    )
    try:
        result = reconcile(
            _load_jsonl(args.containers),
            _load_jsonl(args.shots),
            motions=motions,
        )
    except CheckError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
