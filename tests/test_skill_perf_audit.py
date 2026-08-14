from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO_ROOT / "tools" / "skill_perf_audit.py"
CORE_SKILL = REPO_ROOT / "skills" / "short-drama"
CHILD_SKILLS = sorted((REPO_ROOT / "skills").glob("short-drama-*"))


def _frontmatter(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    return content.split("---", 2)[1]


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


class SkillPerformanceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module(AUDIT_PATH)

    def test_audit_covers_every_public_skill(self) -> None:
        report = self.module.audit(REPO_ROOT)
        self.assertEqual(report["skill_count"], 9)
        self.assertEqual(len(report["skills"]), 9)
        self.assertGreater(report["shared_startup_chars"], 0)

    def test_audit_is_deterministic(self) -> None:
        self.assertEqual(
            self.module.audit(REPO_ROOT),
            self.module.audit(REPO_ROOT),
        )

    def test_public_skills_stay_within_model_context_budget(self) -> None:
        report = self.module.audit(REPO_ROOT)
        self.assertLess(report["totals"]["skill_bytes"], 30_000)
        for skill in report["skills"]:
            with self.subTest(skill=skill["skill"]):
                self.assertLessEqual(skill["skill_lines"], 100)
                self.assertLess(skill["literal_startup_chars"], 10_000)

    def test_child_skills_delegate_suite_validation_to_preflight(self) -> None:
        for skill_dir in CHILD_SKILLS:
            skill_path = skill_dir / "SKILL.md"
            content = skill_path.read_text(encoding="utf-8")
            with self.subTest(skill=skill_path.parent.name):
                self.assertNotIn("从本技能目录读取 `suite-ref.json`", content)
                self.assertIn("不要读取套件清单", content)

    def test_core_skill_requires_explicit_invocation(self) -> None:
        frontmatter = _frontmatter(CORE_SKILL / "SKILL.md")
        content = (CORE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("仅在用户明确调用 $short-drama 时触发", frontmatter)
        self.assertIn("未点名不得触发", frontmatter)
        self.assertIn("## 显式调用门禁", content)
        self.assertIn("否则立即停止，不读取项目、不执行命令", content)
        self.assertIn("不得自动加载未被当前请求明确点名的子技能", content)

    def test_child_skills_require_explicit_invocation_and_project(self) -> None:
        for skill_dir in CHILD_SKILLS:
            content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            frontmatter = _frontmatter(skill_dir / "SKILL.md")
            with self.subTest(skill=skill_dir.name):
                self.assertIn(f"仅在用户明确调用 ${skill_dir.name} 时触发", frontmatter)
                self.assertIn("未点名不得触发", frontmatter)
                self.assertIn("项目须含 short-drama.json", frontmatter)
                self.assertIn(f"当前请求须明确调用 `${skill_dir.name}`，否则停止", content)
                self.assertIn("缺失时提示用户调用 `$short-drama` 初始化", content)

    def test_openai_prompts_preserve_explicit_invocation_gate(self) -> None:
        core_prompt = (CORE_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("short-drama.json", core_prompt)
        self.assertIn("$short-drama", core_prompt)
        self.assertIn("未点名不触发", core_prompt)
        for skill_dir in CHILD_SKILLS:
            prompt = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            with self.subTest(skill=skill_dir.name):
                self.assertIn("short-drama.json", prompt)
                self.assertIn(f"${skill_dir.name}", prompt)
                self.assertIn("$short-drama", prompt)
                self.assertIn("仅响应", prompt)


if __name__ == "__main__":
    unittest.main()
