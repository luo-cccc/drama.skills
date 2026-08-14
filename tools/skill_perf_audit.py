#!/usr/bin/env python3
"""Measure model-facing context cost for the short-drama skill suite."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
DESCRIPTION_RE = re.compile(r"^description:\s*(.*)$", re.MULTILINE)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)")
MANDATORY_READ_RE = re.compile(r"始终读取|必须读取|先读|随后执行|每次.{0,12}读取")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _description(content: str) -> str:
    match = FRONTMATTER_RE.match(content)
    if match is None:
        return ""
    description = DESCRIPTION_RE.search(match.group(1))
    return description.group(1).strip() if description else ""


def audit(root: Path) -> dict[str, object]:
    skills_root = root / "skills"
    core = skills_root / "short-drama"
    manifest = core / "suite-manifest.json"
    quickstart = core / "references" / "execution-quickstart.md"
    shared_chars = len(_text(manifest)) + len(_text(quickstart))
    repeated_lines: Counter[str] = Counter()
    reports: list[dict[str, object]] = []

    for skill_dir in sorted(skills_root.glob("short-drama*")):
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            continue
        content = _text(skill_path)
        stage_path = skill_dir / "references" / "stage-contract.md"
        stage_chars = len(_text(stage_path)) if stage_path.is_file() else 0
        mandatory_reference_chars = 0
        mandatory_paths: set[str] = set()
        for line in content.splitlines():
            if "才读" in line or MANDATORY_READ_RE.search(line) is None:
                continue
            for raw_link in MARKDOWN_LINK_RE.findall(line):
                relative = raw_link.split("#", 1)[0]
                target = (skill_dir / relative).resolve()
                if target.is_file() and str(target) not in mandatory_paths:
                    mandatory_paths.add(str(target))
                    mandatory_reference_chars += len(_text(target))
        literal_startup = len(content) + mandatory_reference_chars
        for source in (skill_path, stage_path):
            if not source.is_file():
                continue
            for line in _text(source).splitlines():
                normalized = line.strip()
                if len(normalized) >= 24:
                    repeated_lines[normalized] += 1
        reports.append(
            {
                "skill": skill_dir.name,
                "skill_bytes": skill_path.stat().st_size,
                "skill_chars": len(content),
                "skill_lines": len(content.splitlines()),
                "description_chars": len(_description(content)),
                "markdown_links": len(MARKDOWN_LINK_RE.findall(content)),
                "stage_contract_chars": stage_chars,
                "mandatory_reference_chars": mandatory_reference_chars,
                "literal_startup_chars": literal_startup,
            }
        )

    duplicates = [
        {"count": count, "text": text}
        for text, count in repeated_lines.most_common()
        if count >= 3
    ]
    return {
        "schema": "short-drama-skill-performance-audit",
        "version": 1,
        "skill_count": len(reports),
        "shared_startup_chars": shared_chars,
        "totals": {
            "skill_bytes": sum(int(item["skill_bytes"]) for item in reports),
            "skill_chars": sum(int(item["skill_chars"]) for item in reports),
            "description_chars": sum(
                int(item["description_chars"]) for item in reports
            ),
            "duplicate_lines_repeated_three_plus": len(duplicates),
        },
        "skills": reports,
        "top_duplicate_lines": duplicates[:25],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit(args.root.resolve())
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
