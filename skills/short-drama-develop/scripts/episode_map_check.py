#!/usr/bin/env python3
"""Check deterministic hook-operation transitions in an episode map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VALID_OPERATIONS = frozenset({"seed", "advance", "resolve", "defer"})
VALID_HOOK_STATES = frozenset({"open", "progressing", "deferred", "resolved"})
REQUIRED_FIELDS = {
    "seed": ("current_question", "evidence", "action_effect", "planned_payoff"),
    "advance": ("evidence", "action_effect"),
    "resolve": ("evidence", "action_effect"),
    "defer": ("reason", "review_condition"),
}


class EpisodeMapError(ValueError):
    pass


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise EpisodeMapError(f"line {line_number}: invalid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise EpisodeMapError(f"line {line_number}: record must be an object")
        record["_line_number"] = line_number
        records.append(record)
    return records


def load_story_engine_ledger(path: Path) -> dict[str, dict[str, str]]:
    """Read the authoritative hook table without treating arbitrary tables as a ledger."""
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = next((index for index, line in enumerate(lines) if line.strip() == "### 铺垫与兑现义务"), None)
    if heading is None:
        raise EpisodeMapError("story-engine has no '铺垫与兑现义务' ledger section")
    header: list[str] | None = None
    ledger: dict[str, dict[str, str]] = {}
    for line in lines[heading + 1:]:
        stripped = line.strip()
        if stripped.startswith("### ") or stripped.startswith("## "):
            break
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if header is None or len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        hook_id = row.get("hook_id", "")
        if not hook_id or hook_id.startswith("【"):
            continue
        if hook_id in ledger:
            raise EpisodeMapError(f"story-engine ledger repeats hook_id: {hook_id}")
        ledger[hook_id] = {
            "planned_payoff": row.get("计划兑现条件/位置", "").strip(),
            "status": row.get("状态", "").strip(),
        }
    return ledger


def check(
    records: list[dict[str, Any]],
    ledger: dict[str, dict[str, str]] | None = None,
    *,
    allow_inherited_ledger: bool = False,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    episode_ids: set[str] = set()
    hook_states: dict[str, str] = {}

    def finding(code: str, record: dict[str, Any], detail: str) -> None:
        findings.append({
            "code": code,
            "line": record["_line_number"],
            "episode_id": record.get("episode_id"),
            "detail": detail,
        })

    if ledger is not None:
        for hook_id, entry in ledger.items():
            status = entry.get("status", "")
            if status not in VALID_HOOK_STATES:
                findings.append({"code": "LEDGER_STATUS_INVALID", "line": None, "episode_id": None, "detail": f"ledger {hook_id} has invalid status: {status!r}"})
            if not entry.get("planned_payoff", "").strip():
                findings.append({"code": "LEDGER_PAYOFF_MISSING", "line": None, "episode_id": None, "detail": f"ledger {hook_id} has no planned payoff condition or position"})

    for record in records:
        episode_id = record.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id.strip():
            finding("EPISODE_ID_MISSING", record, "episode_id must be a non-empty string")
        elif episode_id in episode_ids:
            finding("EPISODE_ID_DUPLICATE", record, f"duplicate episode_id: {episode_id}")
        else:
            episode_ids.add(episode_id)

        operations = record.get("hook_operations", [])
        if not isinstance(operations, list):
            finding("HOOK_OPERATIONS_INVALID", record, "hook_operations must be a list when present")
            continue
        seen_in_episode: set[str] = set()
        for operation in operations:
            if not isinstance(operation, dict):
                finding("HOOK_OPERATION_INVALID", record, "each hook operation must be an object")
                continue
            hook_id = operation.get("hook_id")
            action = operation.get("operation")
            if not isinstance(hook_id, str) or not hook_id.strip():
                finding("HOOK_ID_MISSING", record, "hook operation requires a non-empty hook_id")
                continue
            if hook_id in seen_in_episode:
                finding("HOOK_OPERATION_DUPLICATE", record, f"hook {hook_id} is operated twice in one episode")
                continue
            seen_in_episode.add(hook_id)
            if action not in VALID_OPERATIONS:
                finding("HOOK_OPERATION_UNKNOWN", record, f"hook {hook_id} has unknown operation: {action!r}")
                continue
            missing = [field for field in REQUIRED_FIELDS[action] if not isinstance(operation.get(field), str) or not operation[field].strip()]
            if missing:
                finding("HOOK_OPERATION_EVIDENCE_MISSING", record, f"{action} for {hook_id} is missing: {', '.join(missing)}")
            previous = hook_states.get(hook_id)
            if ledger is not None and hook_id not in ledger:
                finding("HOOK_NOT_IN_LEDGER", record, f"hook {hook_id} is not registered in story-engine ledger")
                continue
            if previous is None and action != "seed" and ledger is not None and allow_inherited_ledger:
                # Imported episode maps may start after the hook's seed. The ledger remains
                # the authority, but the first local operation has a defined open baseline.
                previous = "open"
                hook_states[hook_id] = previous
            if action == "seed":
                if previous is not None:
                    finding("HOOK_ALREADY_EXISTS", record, f"cannot seed {hook_id}; current state is {previous}")
                    continue
                hook_states[hook_id] = "open"
                continue
            if previous is None:
                finding("HOOK_OPERATION_WITHOUT_SEED", record, f"cannot {action} {hook_id} before seed")
                continue
            if previous == "resolved":
                finding("HOOK_OPERATION_AFTER_RESOLVE", record, f"cannot {action} {hook_id} after resolve")
                continue
            hook_states[hook_id] = {
                "advance": "progressing",
                "resolve": "resolved",
                "defer": "deferred",
            }[action]
    if ledger is not None:
        for hook_id, map_state in hook_states.items():
            entry = ledger.get(hook_id)
            if entry is not None and entry.get("status") in VALID_HOOK_STATES and entry["status"] != map_state:
                findings.append({
                    "code": "HOOK_LEDGER_STATE_DRIFT",
                    "line": None,
                    "episode_id": None,
                    "detail": f"hook {hook_id} ends as {map_state} in episode-map but ledger says {entry['status']}",
                })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_map", type=Path)
    parser.add_argument("--story-engine", type=Path, help="Authoritative story-engine.md hook ledger.")
    parser.add_argument("--allow-inherited-ledger", action="store_true", help="Allow a partial imported map to operate an existing ledger hook without its seed.")
    args = parser.parse_args()
    try:
        ledger = load_story_engine_ledger(args.story_engine) if args.story_engine else None
        findings = check(load_jsonl(args.episode_map), ledger, allow_inherited_ledger=args.allow_inherited_ledger)
    except (OSError, EpisodeMapError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "pass" if not findings else "fail", "findings": findings}, ensure_ascii=False))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
