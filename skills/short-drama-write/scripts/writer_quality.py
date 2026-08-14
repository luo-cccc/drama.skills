#!/usr/bin/env python3
"""Build a focused writing brief and check screenplay-level writing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


EMOTION_ONLY = re.compile(
    r"^(?:愤怒|生气|激动|平静|冷静|冷漠|温柔|严肃|委屈|尴尬|得意|轻蔑|嘲讽|"
    r"哽咽|颤抖|震惊|疑惑|害怕|恐惧|紧张|高兴|开心|伤心|难过|崩溃|不耐烦|"
    r"无奈|苦笑|冷笑|淡淡|冷冷|缓缓|低声|轻声|大声|急促|失神|犹豫|坚定|坚决|迟疑)"
    r"[，。！？、\s]*$"
)
DIALOGUE = re.compile(r"^(?P<speaker>[^：:#\[\]（）()]{1,30})(?:[（(](?P<delivery>[^）)]*)[）)])?[：:](?P<text>.+)$")
HAN = re.compile(r"[\u4e00-\u9fff]{2,}")
ENGLISH = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
EPISODE_ID = re.compile(r"^EP(?P<number>\d+)$")
GENERIC_CARRIERS = frozenset({
    "选择", "事情", "问题", "对方", "有人", "现在", "必须", "开始", "出现", "结果",
    "决定", "行动", "变化", "状态", "角色", "对手", "自己", "这里", "那个", "因为",
})


class WriterQualityError(ValueError):
    pass


def strict_json(value: str) -> Any:
    return json.loads(value, parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(constant)))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = strict_json(line)
        except (ValueError, json.JSONDecodeError) as exc:
            raise WriterQualityError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise WriterQualityError(f"{path}:{line_number}: record must be an object")
        records.append(record)
    return records


def find_episode(records: Iterable[dict[str, Any]], episode_id: str) -> dict[str, Any]:
    matches = [record for record in records if record.get("episode_id") == episode_id]
    if len(matches) != 1:
        raise WriterQualityError(f"expected exactly one episode_id {episode_id}, found {len(matches)}")
    return matches[0]


def render_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip() or "（未填写）"
    if isinstance(value, list):
        values = [render_value(item) for item in value if render_value(item) != "（未填写）"]
        return "；".join(values) if values else "（无）"
    if isinstance(value, dict):
        parts = [f"{key}: {render_value(item)}" for key, item in value.items()]
        return "；".join(parts) if parts else "（无）"
    return "（未填写）" if value is None else str(value)


def extract_dialogue_lines(text: str) -> list[tuple[str, str, str | None]]:
    lines: list[tuple[str, str, str | None]] = []
    for line in text.splitlines():
        match = DIALOGUE.match(line.strip())
        if match:
            lines.append((match.group("speaker").strip(), match.group("text").strip(), match.group("delivery")))
    return lines


def extract_action_lines(text: str) -> list[str]:
    actions: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        if DIALOGUE.match(stripped):
            continue
        actions.append(stripped)
    return actions


def carrier_matches(value: Any, surface: str) -> list[str]:
    """Return conservative, human-readable contract anchors found in the script."""
    text = render_value(value)
    if text in {"（无）", "（未填写）"}:
        return []
    normalized = text.lower()
    target = surface.lower()
    if len(normalized) >= 4 and normalized in target:
        return [text]
    matches: set[str] = set()
    for token in ENGLISH.findall(normalized):
        if token not in GENERIC_CARRIERS and token in target:
            matches.add(token)
    for chunk in HAN.findall(normalized):
        for size in range(4, min(8, len(chunk)) + 1):
            for index in range(0, len(chunk) - size + 1):
                candidate = chunk[index:index + size]
                if candidate not in GENERIC_CARRIERS and candidate in target:
                    matches.add(candidate)
        for size in (3,):
            for index in range(0, len(chunk) - size + 1):
                candidate = chunk[index:index + size]
                if candidate not in GENERIC_CARRIERS and candidate in target:
                    matches.add(candidate)
    strong = sorted(match for match in matches if len(match) >= 4)
    if strong:
        return strong
    short = sorted(match for match in matches if len(match) >= 3)
    return short if len(short) >= 2 else []


def has_surface_evidence(value: Any, surface: str) -> bool:
    return bool(carrier_matches(value, surface))


def repeated_ngrams(current: str, previous: str, size: int = 6) -> list[str]:
    current_clean = re.sub(r"\s+", "", current)
    previous_clean = re.sub(r"\s+", "", previous)
    candidates = {
        current_clean[index:index + size]
        for index in range(0, max(0, len(current_clean) - size + 1))
        if re.fullmatch(r"[\u4e00-\u9fff]+", current_clean[index:index + size])
    }
    return sorted(phrase for phrase in candidates if phrase in previous_clean)


def recent_voice_samples(recent_texts: Iterable[tuple[str, str]]) -> list[str]:
    by_speaker: dict[str, list[str]] = defaultdict(list)
    for label, text in recent_texts:
        for speaker, dialogue, _ in extract_dialogue_lines(text):
            if len(by_speaker[speaker]) < 2:
                by_speaker[speaker].append(f"{label}: {dialogue[:80]}")
    return [f"- {speaker}：{' / '.join(samples)}" for speaker, samples in sorted(by_speaker.items())]


def build_brief(episode: dict[str, Any], recent_texts: list[tuple[str, str]]) -> str:
    escalation = episode.get("causal_escalation", [])
    escalation_lines = []
    if isinstance(escalation, list):
        for index, step in enumerate(escalation, 1):
            if isinstance(step, dict):
                escalation_lines.append(
                    f"{index}. 因为 {render_value(step.get('because_of'))}，选择 {render_value(step.get('choice'))}；"
                    f"反制 {render_value(step.get('countermove'))}；状态变化 {render_value(step.get('state_change'))}；"
                    f"下一压力 {render_value(step.get('next_pressure'))}。"
                )
    hook_lines = []
    for operation in episode.get("hook_operations", []) if isinstance(episode.get("hook_operations", []), list) else []:
        if isinstance(operation, dict):
            hook_lines.append(
                f"- {operation.get('hook_id', '未命名')} / {operation.get('operation', '未命名')}："
                f"载体 {render_value(operation.get('evidence'))}；行动后果 {render_value(operation.get('action_effect'))}。"
            )
    recent_actions = []
    for label, text in recent_texts:
        actions = extract_action_lines(text)
        if actions:
            recent_actions.append(f"- {label}：{' / '.join(actions[-3:])[:300]}")
    lines = [
        f"# {episode.get('episode_id', 'EP?')} 写作编译包",
        "",
        "> 此文件由已接受的分集契约和近期剧本派生。先执行合同，再选择场景、动作与对白；不要把它当成新的剧情所有者。",
        "",
        "## 本集不可改写的合同",
        f"- 进入状态：{render_value(episode.get('incoming_state'))}",
        f"- 当前压力：{render_value(episode.get('active_pressure'))}",
        f"- 目标：{render_value(episode.get('objective'))}",
        f"- 反对力量：{render_value(episode.get('opposition'))}",
        f"- 当集兑现：{render_value(episode.get('local_dramatic_result'))}",
        f"- 出去压力：{render_value(episode.get('outgoing_pressure'))}",
        f"- 交接状态：{render_value(episode.get('handoff_state'))}",
        "",
        "## 因果执行链",
        *(escalation_lines or ["- （本集没有填写因果升级；先返回开发层补足。）"]),
        "",
        "## 连载义务",
        *(hook_lines or ["- （本集不操作活跃义务。）"]),
        "",
        "## 近期差异约束",
        "- 不复用下列近期动作、物件处理、对峙几何或台词开合；仅当重复本身是已接受的仪式/喜剧/创伤选择时保留，并让意义或代价改变。",
        *(recent_actions or ["- （没有提供近期剧本。）"]),
        "- 先让对方的反制迫使策略改变，再写情绪反应；不要用同构的质问—否认—加音量替代推进。",
        "",
        "## 近期人物声音样本",
        *(recent_voice_samples(recent_texts) or ["- （没有可解析的近期对白。）"]),
        "",
        "## 提交前自检",
        "- 每个因果选择、反制、状态变化、当集兑现和出去压力，都在动作、对白、声音或明确状态中找到一个可引用落点。",
        "- `advance` / `resolve` 的义务载体让人物必须作不同选择；单纯再次提及不算推进。",
        "- 重要对白提示写策略（试探、逼问、划界、交换），不只写情绪（愤怒、伤心、冷冷）。",
    ]
    return "\n".join(lines) + "\n"


def check_screenplay(episode: dict[str, Any], screenplay: str, recent_texts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    surface = screenplay.lower()

    def require(value: Any, code: str, label: str, path: str) -> None:
        matches = carrier_matches(value, surface)
        if not matches:
            findings.append({
                "code": code,
                "path": path,
                "detail": f"{label} is declared in the episode contract but has no recognizable action, dialogue, sound, or state carrier in screenplay.md.",
                "expected_carrier": render_value(value),
                "repair": "保留合同事实，在受影响场景加入可表演的动作、对白、声音或明确状态后果。",
            })

    for index, step in enumerate(episode.get("causal_escalation", [])):
        if not isinstance(step, dict):
            continue
        for field, label in (("choice", "因果选择"), ("countermove", "对手反制"), ("state_change", "状态变化")):
            require(step.get(field), "WRQ_CONTRACT_NO_CARRIER", label, f"causal_escalation[{index}].{field}")
    local = episode.get("local_dramatic_result")
    if isinstance(local, dict):
        require(local.get("state_change"), "WRQ_CONTRACT_NO_CARRIER", "当集兑现", "local_dramatic_result.state_change")
    outgoing = episode.get("outgoing_pressure")
    if isinstance(outgoing, dict):
        require(outgoing.get("started_decision_danger_or_question"), "WRQ_CONTRACT_NO_CARRIER", "出去压力", "outgoing_pressure.started_decision_danger_or_question")
    for index, operation in enumerate(episode.get("hook_operations", [])):
        if not isinstance(operation, dict) or operation.get("operation") not in {"advance", "resolve"}:
            continue
        require(operation.get("evidence"), "WRQ_HOOK_NO_CARRIER", "连载义务载体", f"hook_operations[{index}].evidence")
        require(operation.get("action_effect"), "WRQ_HOOK_NO_CARRIER", "连载义务行动后果", f"hook_operations[{index}].action_effect")
    for line_number, (_, _, delivery) in enumerate(extract_dialogue_lines(screenplay), 1):
        if delivery and EMOTION_ONLY.fullmatch(delivery.strip()):
            findings.append({
                "code": "WRQ_EMOTION_ONLY_DELIVERY",
                "path": f"dialogue[{line_number}].delivery",
                "detail": f"delivery '{delivery}' only names an emotion and gives no playable strategy.",
                "repair": "把情绪改写成角色想对对方做什么，例如试探、逼问、交换、划界或掩饰。",
            })
    current_actions = "\n".join(extract_action_lines(screenplay))
    for label, previous in recent_texts:
        repeated = repeated_ngrams(current_actions, "\n".join(extract_action_lines(previous)))
        if len(repeated) >= 3:
            findings.append({
                "code": "WRQ_RECENT_ACTION_REPEAT",
                "path": "screenplay.action",
                "detail": f"{len(repeated)} action phrases repeat from {label}: {', '.join(repeated[:3])}.",
                "repair": "换掉重复的动作、道具处理或空间关系；保留重复时写明它新增的意义或代价。",
            })
    return findings


def normalize_standalone_card(card: dict[str, Any]) -> dict[str, Any]:
    """Project the standalone card's owned contract into the map-record shape."""
    contract = card.get("owned_contract")
    if not isinstance(contract, dict):
        raise WriterQualityError("standalone episode card requires owned_contract")
    episode_id = card.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise WriterQualityError("standalone episode card requires a non-empty episode_id")
    projected = dict(contract)
    projected["episode_id"] = episode_id
    outgoing = projected.get("outgoing_pressure")
    if isinstance(outgoing, dict) and "started_decision_danger_or_question" not in outgoing:
        projected["outgoing_pressure"] = {
            **outgoing,
            "started_decision_danger_or_question": outgoing.get(
                "decision_danger_or_question_already_in_motion"
            ),
        }
    projected.setdefault("hook_operations", [])
    return projected


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise WriterQualityError(f"path must be inside project: {path}") from exc


def validate_private_output(project: Path | None, output: Path) -> Path:
    if project is None:
        raise WriterQualityError("--project is required when writing a derived quality artifact")
    root = project.resolve()
    resolved = output.resolve()
    relative = _project_relative(root, resolved)
    if not relative.startswith(".short-drama/"):
        raise WriterQualityError("derived quality artifacts must be written under .short-drama/")
    return resolved


def _episode_number(episode_id: str) -> int:
    match = EPISODE_ID.fullmatch(episode_id)
    if not match:
        raise WriterQualityError(f"episode_id must use EP### form: {episode_id}")
    return int(match.group("number"))


def validate_recent_scripts(project: Path, current_episode: str, recent_paths: list[Path]) -> list[tuple[str, str]]:
    if len(recent_paths) > 3:
        raise WriterQualityError("at most three recent accepted screenplays may be supplied")
    state_path = project / ".short-drama/state.json"
    try:
        state = strict_json(state_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WriterQualityError(f"cannot read lifecycle state: {state_path}") from exc
    artifacts = state.get("artifacts") if isinstance(state, dict) else None
    if not isinstance(artifacts, dict):
        raise WriterQualityError("lifecycle state has no artifacts map")
    current_number = _episode_number(current_episode)
    validated: list[tuple[int, str, str]] = []
    for path in recent_paths:
        relative = _project_relative(project, path)
        parts = Path(relative).parts
        if len(parts) != 3 or parts[0] != "剧集" or parts[2] != "screenplay.md":
            raise WriterQualityError(f"recent script must be 剧集/EP###/screenplay.md: {relative}")
        episode_id = parts[1]
        number = _episode_number(episode_id)
        if number >= current_number:
            raise WriterQualityError(f"recent script must precede {current_episode}: {relative}")
        digest = _sha256_file(path)
        accepted = False
        for record in artifacts.values():
            if not isinstance(record, dict) or record.get("owner") != "short-drama-write":
                continue
            targets = record.get("accepted_targets")
            if isinstance(targets, dict) and targets.get(relative) == digest:
                accepted = True
                break
        if not accepted:
            raise WriterQualityError(f"recent script is not an accepted short-drama-write artifact: {relative}")
        validated.append((number, episode_id, path.read_text(encoding="utf-8")))
    if [number for number, _, _ in validated] != sorted(number for number, _, _ in validated):
        raise WriterQualityError("recent scripts must be supplied in increasing episode order")
    if len({number for number, _, _ in validated}) != len(validated):
        raise WriterQualityError("recent scripts must not repeat an episode")
    return [(episode_id, text) for _, episode_id, text in validated]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    contract = parser.add_mutually_exclusive_group(required=True)
    contract.add_argument("--episode-map", type=Path)
    contract.add_argument("--episode-card", type=Path)
    parser.add_argument("--episode", help="Required with --episode-map; ignored for standalone cards.")
    parser.add_argument("--project", type=Path, help="Project root for lifecycle checks and private derived output.")
    parser.add_argument("--recent", type=Path, action="append", default=[])
    subparsers = parser.add_subparsers(dest="command", required=True)
    brief_parser = subparsers.add_parser("build-brief")
    brief_parser.add_argument("--output", type=Path, required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--screenplay", type=Path, required=True)
    check_parser.add_argument("--output", type=Path, help="Write the JSON report beneath .short-drama/.")
    args = parser.parse_args()
    try:
        if args.episode_map:
            if not args.episode:
                raise WriterQualityError("--episode is required with --episode-map")
            episode = find_episode(load_jsonl(args.episode_map), args.episode)
            contract_path = args.episode_map
        else:
            card = strict_json(args.episode_card.read_text(encoding="utf-8"))
            if not isinstance(card, dict):
                raise WriterQualityError("standalone episode card must be an object")
            episode = normalize_standalone_card(card)
            if args.episode and args.episode != episode["episode_id"]:
                raise WriterQualityError("--episode does not match standalone episode-card")
            contract_path = args.episode_card
        project = args.project.resolve() if args.project else None
        if args.recent and project is None:
            raise WriterQualityError("--project is required with --recent so acceptance can be verified")
        recent = (
            validate_recent_scripts(project, str(episode["episode_id"]), args.recent)
            if args.recent else []
        )
        if args.command == "build-brief":
            output = validate_private_output(project, args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(build_brief(episode, recent), encoding="utf-8")
            print(json.dumps({"status": "pass", "output": str(output), "recent_count": len(recent)}, ensure_ascii=False))
            return 0
        findings = check_screenplay(episode, args.screenplay.read_text(encoding="utf-8"), recent)
        report = {
            "status": "pass",
            "kind": "writer_quality",
            "episode_id": episode["episode_id"],
            "screenplay_sha256": _sha256_file(args.screenplay),
            "contract_sha256": _sha256_file(contract_path),
            "findings": findings,
        }
        if args.output:
            output = validate_private_output(project, args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["output"] = _project_relative(project, output)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, WriterQualityError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
