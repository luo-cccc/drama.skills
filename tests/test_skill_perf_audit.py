from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO_ROOT / "tools" / "skill_perf_audit.py"


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
        for skill_path in sorted((REPO_ROOT / "skills").glob("short-drama-*/SKILL.md")):
            content = skill_path.read_text(encoding="utf-8")
            with self.subTest(skill=skill_path.parent.name):
                self.assertNotIn("从本技能目录读取 `suite-ref.json`", content)
                self.assertIn("不要读取套件清单", content)


if __name__ == "__main__":
    unittest.main()
