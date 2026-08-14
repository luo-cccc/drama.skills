from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/short-drama-develop/scripts/episode_map_check.py"
SPEC = importlib.util.spec_from_file_location("episode_map_check_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


def operation(hook_id: str, action: str, **overrides: str) -> dict[str, str]:
    fields = {
        "hook_id": hook_id,
        "operation": action,
        "evidence": "她交出账本。",
        "action_effect": "对手必须决定是否公开账本。",
    }
    if action == "seed":
        fields.update(
            current_question="账本是谁留下的？",
            planned_payoff="找到签名页时兑现。",
        )
    if action == "defer":
        fields.update(
            reason="本集先结算更紧迫的追捕。",
            review_condition="追捕结束后重审。",
        )
    fields.update(overrides)
    return fields


def episode(number: int, *operations: dict[str, str]) -> dict[str, object]:
    return {
        "_line_number": number,
        "episode_id": f"EP{number:03d}",
        "hook_operations": list(operations),
    }


class EpisodeMapCheckTests(unittest.TestCase):
    def test_valid_hook_lifecycle_passes(self) -> None:
        findings = CHECKER.check(
            [
                episode(1, operation("H001", "seed")),
                episode(2, operation("H001", "advance")),
                episode(3, operation("H001", "resolve")),
            ]
        )
        self.assertEqual(findings, [])

    def test_operations_require_a_seed_and_cannot_resume_after_resolution(self) -> None:
        findings = CHECKER.check(
            [
                episode(1, operation("H001", "advance")),
                episode(2, operation("H002", "seed")),
                episode(3, operation("H002", "resolve")),
                episode(4, operation("H002", "advance")),
            ]
        )
        self.assertEqual(
            [finding["code"] for finding in findings],
            ["HOOK_OPERATION_WITHOUT_SEED", "HOOK_OPERATION_AFTER_RESOLVE"],
        )

    def test_operations_require_their_actionable_evidence(self) -> None:
        findings = CHECKER.check(
            [
                episode(
                    1,
                    operation(
                        "H001",
                        "seed",
                        current_question="",
                        action_effect="",
                    ),
                )
            ]
        )
        self.assertEqual(findings[0]["code"], "HOOK_OPERATION_EVIDENCE_MISSING")
        self.assertIn("current_question", findings[0]["detail"])
        self.assertIn("action_effect", findings[0]["detail"])

    def test_repeated_hook_operation_in_one_episode_is_rejected(self) -> None:
        findings = CHECKER.check(
            [episode(1, operation("H001", "seed"), operation("H001", "advance"))]
        )
        self.assertEqual(findings[0]["code"], "HOOK_OPERATION_DUPLICATE")

    def test_story_engine_ledger_rejects_unknown_hook_and_state_drift(self) -> None:
        ledger = {"H001": {"planned_payoff": "第三集找到签名页", "status": "resolved"}}
        unknown = CHECKER.check([episode(1, operation("H999", "seed"))], ledger)
        self.assertIn("HOOK_NOT_IN_LEDGER", [finding["code"] for finding in unknown])
        drift = CHECKER.check([episode(1, operation("H001", "seed"))], ledger)
        self.assertIn("HOOK_LEDGER_STATE_DRIFT", [finding["code"] for finding in drift])

    def test_story_engine_ledger_accepts_matching_lifecycle(self) -> None:
        ledger = {"H001": {"planned_payoff": "第三集找到签名页", "status": "resolved"}}
        findings = CHECKER.check([
            episode(1, operation("H001", "seed")),
            episode(2, operation("H001", "advance")),
            episode(3, operation("H001", "resolve")),
        ], ledger)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
