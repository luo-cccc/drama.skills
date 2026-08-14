"""Check-script smoke tests (stdlib-only).

The six mechanical "bookkeeping" scripts (storyboard duration/boundary,
motion timing, generation-clip planning, delivery-container reconciliation, voice-sheet consistency and
screenplay indexing) previously had no execution coverage beyond `compileall`.
Each test drives the real check function through a minimal pass and fail case,
so the arithmetic stays wired even though the checks never need a full project.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STORYBOARD_CHECK = REPO_ROOT / "skills/short-drama-storyboard/scripts/storyboard_check.py"
MOTION_TIMING_CHECK = REPO_ROOT / "skills/short-drama-video-prompts/scripts/motion_timing_check.py"
CONTAINER_CHECK = REPO_ROOT / "skills/short-drama-video-prompts/scripts/container_check.py"
GENERATION_CLIP_CHECK = REPO_ROOT / "skills/short-drama-video-prompts/scripts/generation_clip_check.py"
VOICE_SHEET_CHECK = REPO_ROOT / "skills/short-drama-write/scripts/voice_sheet_check.py"
SCREENPLAY_INDEX = REPO_ROOT / "skills/short-drama-write/scripts/screenplay_index.py"
PROJECT_TOOL = REPO_ROOT / "skills/short-drama/scripts/project_tool.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


storyboard = _load_module(STORYBOARD_CHECK, "storyboard_check_under_test")
motion = _load_module(MOTION_TIMING_CHECK, "motion_timing_check_under_test")
container = _load_module(CONTAINER_CHECK, "container_check_under_test")
generation_clip = _load_module(GENERATION_CLIP_CHECK, "generation_clip_check_under_test")
voice = _load_module(VOICE_SHEET_CHECK, "voice_sheet_check_under_test")
indexer = _load_module(SCREENPLAY_INDEX, "screenplay_index_under_test")
project_tool = _load_module(PROJECT_TOOL, "project_tool_check_scripts_test")


def _finding_codes(result: dict) -> list[str]:
    return [finding.get("code") for finding in result.get("findings", [])]


class StoryboardCheckTests(unittest.TestCase):
    def _shots(self) -> list[dict]:
        return [{"shot_id": "S001", "duration_seconds": 5.0}]

    def _coverage(self, total: float) -> dict:
        return {
            "episode_id": "EP001",
            "episode_duration": {
                "counted_shot_ids": ["S001"],
                "unresolved_durations": [],
                "shot_seconds_total": total,
            },
            "dispositions": [{"shot_refs": [{"record_id": "S001"}]}],
        }

    def test_duration_total_matches_the_sum(self) -> None:
        result = storyboard.check_episode_duration(self._coverage(5.0), self._shots(), None)
        self.assertEqual(result, [])

    def test_duration_total_does_not_match_the_sum(self) -> None:
        result = storyboard.check_episode_duration(self._coverage(99.0), self._shots(), None)
        self.assertIn("SHT16_TOTAL_IS_NOT_THE_SUM", [f["code"] for f in result])

    def test_non_finite_duration_cannot_disappear_from_the_total(self) -> None:
        shots = [{"shot_id": "S001", "duration_seconds": float("nan")}]
        result = storyboard.check_episode_duration(self._coverage(float("nan")), shots, None)
        codes = [finding["code"] for finding in result]
        self.assertIn("SHT16_COUNTED_SHOT_HAS_NO_DURATION", codes)
        self.assertIn("SHT16_TOTAL_MISSING", codes)

    def test_fixed_pipeline_shot_needs_start_keyframe(self) -> None:
        findings = storyboard.check_keyframe_boundaries([], self._shots())
        self.assertIn("SHT17_START_KEYFRAME_MISSING", [finding["code"] for finding in findings])


class MotionTimingCheckTests(unittest.TestCase):
    def _shots(self, duration: float) -> list[dict]:
        return [{"shot_id": "S001", "duration_seconds": duration}]

    def _spec(self, value: str) -> dict:
        return {
            "motion_id": "M001",
            "shot_ref": {"record_id": "S001"},
            "timing_plan": {"mode": "explicit", "declares_overlap": False},
            "ordered_subject_motion": [
                {"timing": {"mode": "explicit", "value": value}},
            ],
        }

    def test_explicit_timing_matches_shot_duration(self) -> None:
        result = motion.check([self._spec("0.0-4.0")], self._shots(4.0))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])

    def test_explicit_timing_overflow_is_reported(self) -> None:
        result = motion.check([self._spec("0.0-5.0")], self._shots(4.0))
        self.assertEqual(result["status"], "fail")
        self.assertIn("VID_EXPLICIT_TIMING_OVERFLOW", _finding_codes(result))


class ContainerReconcileTests(unittest.TestCase):
    def _shots(self) -> list[dict]:
        return [{"shot_id": "S001", "duration_seconds": 5.0}]

    def _member(self) -> dict:
        return {
            "shot_ref": {"record_id": "S001"},
            "accepted_duration_ref": {"record_id": "S001", "field": "/duration_seconds"},
            "accepted_duration": 5.0,
            "order": 1,
        }

    def _container(self, container_id: str) -> dict:
        return {
            "container_id": container_id,
            "members": [self._member()],
            "container_duration": 5.0,
        }

    def test_empty_episode_is_clean(self) -> None:
        result = container.reconcile([], [], None)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])

    def test_shot_packed_twice_is_reported(self) -> None:
        result = container.reconcile(
            [self._container("C1"), self._container("C2")],
            self._shots(),
            None,
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("VID15_SHOT_PACKED_TWICE", _finding_codes(result))


class GenerationClipCheckTests(unittest.TestCase):
    def _project(self, *, maximum: float = 15.0, continuation: bool = False) -> dict:
        return {
            "format": {
                "generation_limits": {
                    "max_clip_seconds": maximum,
                    "continuation_supported": continuation,
                }
            }
        }

    def _shots(self, duration: float = 28.0) -> list[dict]:
        return [{"shot_id": "S001", "duration_seconds": duration}]

    def _motions(self) -> list[dict]:
        return [{"motion_id": "M001", "shot_ref": {"record_id": "S001"}}]

    def _clip(
        self,
        clip_id: str,
        order: int,
        start: float,
        end: float,
        previous: str | None,
    ) -> dict:
        return {
            "clip_id": clip_id,
            "shot_ref": {"record_id": "S001"},
            "motion_ref": {"record_id": "M001"},
            "order": order,
            "source_window": {"start_seconds": start, "end_seconds": end},
            "duration_seconds": end - start,
            "execution_mode": "independent",
            "start_source": "shot_start" if previous is None else "previous_clip_end",
            "output_observation_ref": None,
            "handoff": None
            if previous is None
            else {
                "from_clip_id": previous,
                "planned_boundary": {
                    "pose": "standing",
                    "position": "beside the table",
                    "gaze": "toward the door",
                    "hands_and_props": "right hand holds the cup",
                    "visible_state": f"boundary at {start}s",
                },
                "observation_ref": None,
            },
        }

    def test_long_editorial_shot_can_be_covered_by_model_sized_clips(self) -> None:
        clips = [
            self._clip("C1", 1, 0.0, 10.0, None),
            self._clip("C2", 2, 10.0, 20.0, "C1"),
            self._clip("C3", 3, 20.0, 28.0, "C2"),
        ]
        result = generation_clip.check(
            clips, self._shots(), self._motions(), self._project()
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])

    def test_clip_over_limit_and_coverage_gap_are_rejected(self) -> None:
        clips = [
            self._clip("C1", 1, 0.0, 16.0, None),
            self._clip("C2", 2, 17.0, 28.0, "C1"),
        ]
        result = generation_clip.check(
            clips, self._shots(), self._motions(), self._project()
        )
        codes = _finding_codes(result)
        self.assertIn("GCLIP_DURATION_EXCEEDS_LIMIT", codes)
        self.assertIn("GCLIP_COVERAGE_GAP_OR_OVERLAP", codes)

    def test_continuation_needs_project_support(self) -> None:
        first = self._clip("C1", 1, 0.0, 5.0, None)
        second = self._clip("C2", 2, 5.0, 10.0, "C1")
        second["execution_mode"] = "continuation"
        result = generation_clip.check(
            [first, second], self._shots(10.0), self._motions(), self._project()
        )
        self.assertIn("GCLIP_CONTINUATION_UNSUPPORTED", _finding_codes(result))

    def test_continuation_requires_the_previous_output_observation(self) -> None:
        first = self._clip("C1", 1, 0.0, 5.0, None)
        second = self._clip("C2", 2, 5.0, 10.0, "C1")
        second["execution_mode"] = "continuation"
        missing = generation_clip.check(
            [first, second],
            self._shots(10.0),
            self._motions(),
            self._project(continuation=True),
        )
        self.assertIn(
            "GCLIP_CONTINUATION_OBSERVATION_MISSING", _finding_codes(missing)
        )

        observation = {
            "owner": "creator",
            "artifact": "项目私有/observations/C1.json",
            "hash": "a" * 64,
        }
        first["output_observation_ref"] = observation
        second["handoff"]["observation_ref"] = observation
        passed = generation_clip.check(
            [first, second],
            self._shots(10.0),
            self._motions(),
            self._project(continuation=True),
        )
        self.assertEqual(passed["status"], "pass")

    def test_handoff_boundary_requires_all_continuity_fields(self) -> None:
        first = self._clip("C1", 1, 0.0, 5.0, None)
        second = self._clip("C2", 2, 5.0, 10.0, "C1")
        second["handoff"]["planned_boundary"] = {"visible_state": "still waiting"}
        result = generation_clip.check(
            [first, second], self._shots(10.0), self._motions(), self._project()
        )
        self.assertIn("GCLIP_HANDOFF_BOUNDARY_INCOMPLETE", _finding_codes(result))


class VoiceSheetCheckTests(unittest.TestCase):
    def test_empty_sheet_is_clean(self) -> None:
        result = voice.check([], [], b"")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])


class ScreenplayIndexTests(unittest.TestCase):
    def _run(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "screenplay.md"
            source.write_text(text, encoding="utf-8")
            output = directory / "screenplay-index.jsonl"
            return indexer.build_index(source, output)

    def test_empty_source_is_clean(self) -> None:
        result = self._run("")
        self.assertEqual(result["review_status"], "clean")
        self.assertEqual(result["block_count"], 0)

    def test_scene_heading_produces_one_clean_block(self) -> None:
        result = self._run("## EP001-SC001 内 · 客厅 · 夜\n")
        self.assertEqual(result["review_status"], "clean")
        self.assertEqual(result["block_count"], 1)
        self.assertEqual(result["source_issue_count"], 0)

    def test_index_pins_source_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "screenplay.md"
            source.write_text("## EP001-SC001 内 · 客厅 · 夜\n", encoding="utf-8")
            output = directory / "screenplay-index.jsonl"
            result = indexer.build_index(source, output)
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            meta = records[0]
            self.assertEqual(meta["record_type"], "screenplay_index_meta")
            self.assertEqual(meta["source_ref"]["hash"], result["source_sha256"])

    def test_unchanged_block_keeps_record_digest_across_unrelated_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            previous_source = directory / "screenplay-v1.md"
            current_source = directory / "screenplay-v2.md"
            previous_index = directory / "screenplay-index-v1.jsonl"
            current_index = directory / "screenplay-index-v2.jsonl"
            previous_source.write_text(
                "## EP001-SC001 内 · 客厅 · 夜\n\n他推开门。\n",
                encoding="utf-8",
            )
            current_source.write_text(
                "## EP001-SC001 内 · 客厅 · 夜\n\n风吹窗帘。\n\n他推开门。\n",
                encoding="utf-8",
            )
            source_ref = "剧集/EP001/screenplay.md"
            indexer.build_index(previous_source, previous_index, source_ref=source_ref)
            indexer.build_index(
                current_source,
                current_index,
                previous_index_path=previous_index,
                previous_source_path=previous_source,
                source_ref=source_ref,
            )
            previous_records = [
                json.loads(line)
                for line in previous_index.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            unchanged = next(
                record
                for record in previous_records
                if record.get("record_type") == "block"
                and record.get("kind") == "action"
            )
            selector = unchanged["block_id"]
            old_digest = project_tool._record_digests(
                previous_index.read_bytes(),
                "剧集/EP001/screenplay-index.jsonl",
                [selector],
            )[selector]
            new_digest = project_tool._record_digests(
                current_index.read_bytes(),
                "剧集/EP001/screenplay-index.jsonl",
                [selector],
            )[selector]
            self.assertEqual(old_digest, new_digest)
            self.assertNotEqual(previous_index.read_bytes(), current_index.read_bytes())


class StrictJsonInputTests(unittest.TestCase):
    def test_checkers_reject_non_standard_json_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text('{"duration_seconds":NaN}\n', encoding="utf-8")
            for module in (storyboard, motion, container, generation_clip, voice):
                with self.subTest(module=module.__name__), self.assertRaises(
                    module.CheckError
                ):
                    module._load_jsonl(path)


if __name__ == "__main__":
    unittest.main()
