from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/short-drama-write/scripts/writer_quality.py"
SPEC = importlib.util.spec_from_file_location("writer_quality_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
QUALITY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = QUALITY
SPEC.loader.exec_module(QUALITY)


def episode() -> dict[str, object]:
    return {
        "episode_id": "EP003",
        "incoming_state": {"knowledge": ["葛晴知道船票日期不对"]},
        "active_pressure": "渡口马上封锁",
        "objective": {"desired_change": "让游森交出钥匙"},
        "opposition": {"leverage": "游森掌握账本"},
        "causal_escalation": [
            {
                "choice": "葛晴扣下船票",
                "countermove": "游森撕开账本封条",
                "state_change": "钥匙落到柜台上",
            }
        ],
        "local_dramatic_result": {"state_change": "葛晴拿到钥匙"},
        "outgoing_pressure": {"started_decision_danger_or_question": "封锁前必须开门"},
        "hook_operations": [
            {
                "hook_id": "H001",
                "operation": "advance",
                "evidence": "账本封条被撕开",
                "action_effect": "游森必须选择交出账本",
            }
        ],
        "handoff_state": {"physical": ["钥匙在葛晴手中"]},
    }


SCREENPLAY = """# EP003

## EP003-SC001 内 · 渡口售票室 · 夜

渡口马上封锁。葛晴扣下船票，逼游森交出钥匙。

游森撕开账本封条，钥匙落到柜台上。

葛晴拿到钥匙，盯着封锁前必须开门的闸机。

游森（交换）：我必须交出账本，才有资格让你开门。
"""


class WriterQualityTests(unittest.TestCase):
    def test_contract_with_visible_carriers_passes(self) -> None:
        findings = QUALITY.check_screenplay(episode(), SCREENPLAY, [])
        self.assertEqual(findings, [])

    def test_missing_contract_carrier_is_reported(self) -> None:
        screenplay = SCREENPLAY.replace("游森撕开账本封条，钥匙落到柜台上。", "游森转过身。")
        findings = QUALITY.check_screenplay(episode(), screenplay, [])
        codes = [finding["code"] for finding in findings]
        self.assertIn("WRQ_CONTRACT_NO_CARRIER", codes)
        self.assertIn("WRQ_HOOK_NO_CARRIER", codes)

    def test_emotion_only_delivery_is_reported(self) -> None:
        findings = QUALITY.check_screenplay(episode(), SCREENPLAY.replace("（交换）", "（愤怒）"), [])
        self.assertIn("WRQ_EMOTION_ONLY_DELIVERY", [finding["code"] for finding in findings])

    def test_repeated_recent_actions_are_reported(self) -> None:
        repeated = "葛晴扣下船票。游森撕开账本封条。钥匙落到柜台上。"
        findings = QUALITY.check_screenplay(episode(), SCREENPLAY, [("EP002", repeated)])
        self.assertIn("WRQ_RECENT_ACTION_REPEAT", [finding["code"] for finding in findings])

    def test_brief_contains_contract_and_voice_samples(self) -> None:
        brief = QUALITY.build_brief(episode(), [("EP002", "游森：别碰账本。")])
        self.assertIn("本集不可改写的合同", brief)
        self.assertIn("因果执行链", brief)
        self.assertIn("游森", brief)

    def test_generic_overlap_does_not_count_as_contract_carrier(self) -> None:
        contract = episode()
        contract["causal_escalation"] = [{
            "choice": "对方必须选择解决问题",
            "countermove": "有人开始处理事情",
            "state_change": "现在出现结果",
        }]
        screenplay = "对方现在必须做选择。有人开始处理事情，最后有了结果。"
        findings = QUALITY.check_screenplay(contract, screenplay, [])
        self.assertTrue(any(finding["code"] == "WRQ_CONTRACT_NO_CARRIER" for finding in findings))
        self.assertTrue(all("expected_carrier" in finding for finding in findings if finding["code"] == "WRQ_CONTRACT_NO_CARRIER"))

    def test_standalone_card_is_normalized(self) -> None:
        card = {
            "episode_id": "EP003",
            "owned_contract": episode() | {
                "outgoing_pressure": {"decision_danger_or_question_already_in_motion": "封锁前必须开门"},
            },
        }
        normalized = QUALITY.normalize_standalone_card(card)
        self.assertEqual(normalized["episode_id"], "EP003")
        self.assertEqual(normalized["outgoing_pressure"]["started_decision_danger_or_question"], "封锁前必须开门")

    def test_private_output_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / ".short-drama/work/writer-briefs/EP003.md"
            self.assertEqual(QUALITY.validate_private_output(root, private), private.resolve())
            with self.assertRaises(QUALITY.WriterQualityError):
                QUALITY.validate_private_output(root, root / "剧集/EP003/writer-brief.md")

    def test_recent_scripts_must_be_accepted_and_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "剧集/EP001/screenplay.md"
            second = root / "剧集/EP002/screenplay.md"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("葛晴：先走。\n", encoding="utf-8")
            second.write_text("游森：等等。\n", encoding="utf-8")
            state_dir = root / ".short-drama"
            state_dir.mkdir()
            state_dir.joinpath("state.json").write_text(json.dumps({"artifacts": {
                "EP001:script": {"owner": "short-drama-write", "accepted_targets": {"剧集/EP001/screenplay.md": QUALITY._sha256_file(first)}},
                "EP002:script": {"owner": "short-drama-write", "accepted_targets": {"剧集/EP002/screenplay.md": QUALITY._sha256_file(second)}},
            }}), encoding="utf-8")
            recent = QUALITY.validate_recent_scripts(root, "EP003", [first, second])
            self.assertEqual([label for label, _ in recent], ["EP001", "EP002"])
            with self.assertRaises(QUALITY.WriterQualityError):
                QUALITY.validate_recent_scripts(root, "EP003", [second, first])


if __name__ == "__main__":
    unittest.main()
