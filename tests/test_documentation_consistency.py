from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DocumentationConsistencyTests(unittest.TestCase):
    def test_relative_markdown_links_resolve(self) -> None:
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        broken: list[str] = []
        for source in sorted(REPO_ROOT.rglob("*.md")):
            for raw_target in pattern.findall(source.read_text(encoding="utf-8")):
                target = raw_target.strip().strip("<>").split("#", 1)[0]
                if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target):
                    continue
                if not (source.parent / target).resolve().exists():
                    broken.append(f"{source.relative_to(REPO_ROOT)} -> {raw_target}")
        self.assertEqual(broken, [])

    def test_readme_latest_update_contains_only_the_latest_block(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        latest = readme.split("## 最新更新", 1)[1].split("\n## ", 1)[0]
        headings = re.findall(r"^### ", latest, flags=re.MULTILINE)
        self.assertEqual(len(headings), 1)
        self.assertIn("完整历史保留在", latest)

    def test_obsolete_preflight_and_checkpoint_docs_are_gone(self) -> None:
        obsolete = (
            REPO_ROOT
            / "skills"
            / "short-drama"
            / "references"
            / "runtime-preflight.md"
        )
        self.assertFalse(obsolete.exists())
        self.assertFalse(
            (
                REPO_ROOT
                / "skills"
                / "short-drama"
                / "references"
                / "routing-examples.md"
            ).exists()
        )

        stage_contracts = sorted(
            (REPO_ROOT / "skills").glob("short-drama-*/references/stage-contract.md")
        )
        for contract in stage_contracts:
            with self.subTest(contract=contract.parent.parent.name):
                text = contract.read_text(encoding="utf-8")
                self.assertNotIn("runtime-preflight.md", text)
                self.assertNotIn("从本技能目录的 `suite-ref.json`", text)

        current_docs = [
            REPO_ROOT / "skills/short-drama/references/creator-workflow.md",
            REPO_ROOT
            / "skills/short-drama-assets/references/asset-review-checklist.md",
        ]
        old_checkpoint = re.compile(r"\bC(?:0|1|2|3a|3b|4|5)\b")
        for document in current_docs:
            with self.subTest(document=document.name):
                self.assertIsNone(
                    old_checkpoint.search(document.read_text(encoding="utf-8"))
                )

    def test_quickstart_matches_current_task_packet_workflow(self) -> None:
        quickstart = (
            REPO_ROOT
            / "skills"
            / "short-drama"
            / "references"
            / "execution-quickstart.md"
        ).read_text(encoding="utf-8")
        for command in ("preflight", "prepare", "finalize", "--scope", "--delta-from"):
            with self.subTest(command=command):
                self.assertIn(command, quickstart)
        self.assertNotIn("来源与目标必须不同路径", quickstart)
        self.assertNotIn("约 35–40 分钟", quickstart)

    def test_current_docs_require_explicit_skill_invocation(self) -> None:
        creator_workflow = (
            REPO_ROOT / "skills/short-drama/references/creator-workflow.md"
        ).read_text(encoding="utf-8")
        production_pipeline = (
            REPO_ROOT / "skills/short-drama/references/production-pipeline.md"
        ).read_text(encoding="utf-8")
        core_skill = (REPO_ROOT / "skills/short-drama/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("用户显式调用对应 `$skill`", creator_workflow)
        self.assertNotIn("明确的单项请求可以直入对应 owner", creator_workflow)
        self.assertIn("只有在用户显式调用对应技能时才可执行", production_pipeline)
        self.assertNotIn("仍可直接进入对应技能", production_pipeline)
        self.assertIn("不得根据请求语义自动加载表中技能", core_skill)

    def test_each_top_level_reference_is_discoverable_from_its_skill(self) -> None:
        missing: list[str] = []
        for skill_dir in sorted((REPO_ROOT / "skills").glob("short-drama*")):
            skill_path = skill_dir / "SKILL.md"
            references = skill_dir / "references"
            if not skill_path.is_file() or not references.is_dir():
                continue
            skill_text = skill_path.read_text(encoding="utf-8")
            for reference in sorted(references.glob("*.md")):
                if reference.name not in skill_text:
                    missing.append(f"{skill_dir.name}/references/{reference.name}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
