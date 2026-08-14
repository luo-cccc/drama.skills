"""Cross-stage generation asset consumption checks."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TOOL = REPO_ROOT / "skills/short-drama/scripts/project_tool.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_module(PROJECT_TOOL, "project_tool_asset_consumption_test")


class AssetConsumptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        tool.initialize_project(
            self.root,
            title="asset consumption",
            language="zh-CN",
            aspect_ratio="9:16",
            prompt_language="en",
        )
        self.m2 = {
            "CHAR-TEST": {
                "model_id": "MODEL-CHAR-TEST-V1",
                "asset_kind": "character",
                "view_ids": {"GVIEW-CHAR-TEST-FRONT-V1"},
                "variant_ids": set(),
                "fragment_ids": {
                    "FRAG-STYLE",
                    "FRAG-ID",
                    "FRAG-CONT",
                    "FRAG-VIEW",
                    "FRAG-NEG",
                },
                "fragments": self._fragment_records(),
            }
        }
        self.screenplay_index = (
            "剧集/EP001/screenplay-index.jsonl",
            {"BLK-1": "1" * 64},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _group(self, files: dict[str, list[dict]]) -> list[tuple[str, dict, list[str]]]:
        targets: dict[str, str] = {}
        for relative, records in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
                encoding="utf-8",
            )
            targets[relative] = "0" * 64
        record = {
            "build_state": "materialized",
            "creator_acceptance": "accepted",
            "accepted_targets": targets,
        }
        return [("artifact", record, sorted(targets))]

    def _fragments(self) -> list[dict[str, str]]:
        return [
            {"fragment_id": fragment_id, "hash": "0" * 64}
            for fragment_id in ("FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG")
        ]

    def _fragment_records(self) -> dict[str, dict]:
        return {
            "FRAG-STYLE": {
                "fragment_id": "FRAG-STYLE",
                "fragment_kind": "style_core",
                "asset_id": None,
                "fragment_hash": "0" * 64,
            },
            "FRAG-ID": {
                "fragment_id": "FRAG-ID",
                "fragment_kind": "identity_full",
                "asset_id": "CHAR-TEST",
                "fragment_hash": "0" * 64,
            },
            "FRAG-CONT": {
                "fragment_id": "FRAG-CONT",
                "fragment_kind": "continuity_lock",
                "asset_id": "CHAR-TEST",
                "fragment_hash": "0" * 64,
            },
            "FRAG-VIEW": {
                "fragment_id": "FRAG-VIEW",
                "fragment_kind": "view_projection",
                "asset_id": "CHAR-TEST",
                "scope": {"view_id": "GVIEW-CHAR-TEST-FRONT-V1"},
                "fragment_hash": "0" * 64,
            },
            "FRAG-NEG": {
                "fragment_id": "FRAG-NEG",
                "fragment_kind": "negative_lock",
                "asset_id": "CHAR-TEST",
                "fragment_hash": "0" * 64,
            },
        }

    def _binding(self) -> dict:
        return {
            "asset_id": "CHAR-TEST",
            "model_id": "MODEL-CHAR-TEST-V1",
            "view_id": "GVIEW-CHAR-TEST-FRONT-V1",
            "variant_id": None,
        }

    def _screenplay_ref(self, block_id: str = "BLK-1") -> dict:
        return {
            "owner": "short-drama-write",
            "artifact": self.screenplay_index[0],
            "record_id": block_id,
            "hash": self.screenplay_index[1][block_id],
        }

    def test_m3_requires_one_resolved_decision_per_occurrence(self) -> None:
        occurrence = {
            "occurrence_id": "OCC-1",
            "asset_kind": "character",
            "source_ref": self._screenplay_ref(),
            "source_blocks": ["BLK-1"],
            "proposed_binding": {"identity_id": "CHAR-TEST"},
        }
        decision = {
            "decision_id": "DEC-1",
            "decision_kind": "reuse",
            "asset_kind": "character",
            "occurrence_refs": [{"record_id": "OCC-1"}],
            "proposed_binding": {
                "identity_id": "CHAR-TEST",
                "generation_model_id": "MODEL-CHAR-TEST-V1",
                "generation_variant_id": None,
            },
        }
        group = self._group(
            {
                "剧集/EP001/assets/occurrences.jsonl": [occurrence],
                "剧集/EP001/assets/decisions.jsonl": [decision],
                "剧集/EP001/assets/continuity.jsonl": [],
            }
        )
        self.assertEqual(
            tool._m3_asset_consumption_issues(
                self.root,
                group,
                self.m2,
                self.screenplay_index,
            ),
            [],
        )

        decision["decision_kind"] = "new_variant"
        group = self._group(
            {
                "剧集/EP001/assets/occurrences.jsonl": [occurrence],
                "剧集/EP001/assets/decisions.jsonl": [decision],
                "剧集/EP001/assets/continuity.jsonl": [],
            }
        )
        issues = tool._m3_asset_consumption_issues(
            self.root,
            group,
            self.m2,
            self.screenplay_index,
        )
        self.assertTrue(any("requires M1.5a/M1.5b" in issue for issue in issues))

    def test_m4a_must_cover_every_m2_asset(self) -> None:
        record = {
            "spec_id": "IMG-CHAR-TEST-BASE",
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "asset_board", "fragment_refs": self._fragments()},
        }
        group = self._group({"剧集/EP001/assets/image-prompt-specs.jsonl": [record]})
        self.assertEqual(tool._m4a_asset_consumption_issues(self.root, group, self.m2), [])

        expanded = dict(self.m2)
        expanded["PROP-MISSING"] = {
            "model_id": "MODEL-PROP-MISSING-V1",
            "asset_kind": "prop",
            "view_ids": {"GVIEW-PROP-MISSING-FRONT-V1"},
            "variant_ids": set(),
            "fragment_ids": set(),
            "fragments": {},
        }
        issues = tool._m4a_asset_consumption_issues(self.root, group, expanded)
        self.assertTrue(any("does not cover M2 assets" in issue for issue in issues))

        with_variant = {"CHAR-TEST": dict(self.m2["CHAR-TEST"])}
        with_variant["CHAR-TEST"]["variant_ids"] = {"VAR-TEST"}
        with_variant["CHAR-TEST"]["fragment_ids"] = set(
            with_variant["CHAR-TEST"]["fragment_ids"]
        ) | {"FRAG-VAR"}
        with_variant["CHAR-TEST"]["fragments"] = {
            **with_variant["CHAR-TEST"]["fragments"],
            "FRAG-VAR": {
                "fragment_id": "FRAG-VAR",
                "fragment_kind": "variant_delta",
                "asset_id": "CHAR-TEST",
                "variant_id": "VAR-TEST",
                "fragment_hash": "0" * 64,
            },
        }
        issues = tool._m4a_asset_consumption_issues(self.root, group, with_variant)
        self.assertTrue(any("does not cover variants" in issue for issue in issues))

    def test_storyboard_and_motion_reuse_the_shot_binding_chain(self) -> None:
        shot_binding = {**self._binding(), "fragment_refs": self._fragments()}
        shot = {"shot_id": "SHOT-1", "generation_asset_bindings": [shot_binding]}
        keyframe = {
            "keyframe_id": "KEY-1",
            "shot_ref": {"record_id": "SHOT-1"},
            "boundary_role": "start",
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "keyframe", "fragment_refs": self._fragments()},
        }
        storyboard_group = self._group(
            {
                "剧集/EP001/storyboard/shots.jsonl": [shot],
                "剧集/EP001/storyboard/keyframes.jsonl": [keyframe],
            }
        )
        issues, signatures = tool._m4b_asset_consumption_issues(
            self.root, storyboard_group, self.m2
        )
        self.assertEqual(issues, [])

        motion = {
            "motion_id": "MOTION-1",
            "shot_ref": {"record_id": "SHOT-1"},
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "motion", "fragment_refs": self._fragments()},
        }
        motion_group = self._group(
            {"剧集/EP001/storyboard/motion-specs.jsonl": [motion]}
        )
        self.assertEqual(
            tool._m5_asset_consumption_issues(
                self.root, motion_group, signatures, self.m2
            ),
            [],
        )

        motion["prompt_components"]["profile"] = "keyframe"
        motion_group = self._group(
            {"剧集/EP001/storyboard/motion-specs.jsonl": [motion]}
        )
        issues = tool._m5_asset_consumption_issues(
            self.root, motion_group, signatures, self.m2
        )
        self.assertTrue(any("profile motion" in issue for issue in issues))
        motion["prompt_components"]["profile"] = "motion"

        motion["asset_bindings"][0]["view_id"] = "GVIEW-WRONG"
        motion_group = self._group(
            {"剧集/EP001/storyboard/motion-specs.jsonl": [motion]}
        )
        issues = tool._m5_asset_consumption_issues(
            self.root, motion_group, signatures, self.m2
        )
        self.assertTrue(any("differs from shot" in issue for issue in issues))

    def test_m5_generation_clips_cover_long_shot_with_project_limit(self) -> None:
        shot = {"shot_id": "SHOT-LONG", "duration_seconds": 28.0}
        motion = {
            "motion_id": "MOTION-LONG",
            "shot_ref": {"record_id": "SHOT-LONG"},
        }

        def clip(
            clip_id: str,
            order: int,
            start: float,
            end: float,
            previous: str | None,
        ) -> dict:
            return {
                "clip_id": clip_id,
                "shot_ref": {"record_id": "SHOT-LONG"},
                "motion_ref": {"record_id": "MOTION-LONG"},
                "order": order,
                "source_window": {
                    "start_seconds": start,
                    "end_seconds": end,
                },
                "duration_seconds": end - start,
                "execution_mode": "independent",
                "start_source": (
                    "shot_start" if previous is None else "previous_clip_end"
                ),
                "handoff": None
                if previous is None
                else {
                    "from_clip_id": previous,
                    "planned_boundary": {
                        "pose": "standing",
                        "position": "beside the table",
                        "gaze": "toward the door",
                        "hands_and_props": "right hand holds the cup",
                        "visible_state": f"at {start}s",
                    },
                },
            }

        clips = [
            clip("GCLIP-1", 1, 0.0, 10.0, None),
            clip("GCLIP-2", 2, 10.0, 20.0, "GCLIP-1"),
            clip("GCLIP-3", 3, 20.0, 28.0, "GCLIP-2"),
        ]
        group = self._group(
            {
                "剧集/EP001/storyboard/shots.jsonl": [shot],
                "剧集/EP001/storyboard/motion-specs.jsonl": [motion],
                "剧集/EP001/storyboard/generation-clips.jsonl": clips,
            }
        )
        self.assertEqual(tool._m5_generation_clip_issues(self.root, group), [])

        clips[0]["duration_seconds"] = 16.0
        group = self._group(
            {
                "剧集/EP001/storyboard/shots.jsonl": [shot],
                "剧集/EP001/storyboard/motion-specs.jsonl": [motion],
                "剧集/EP001/storyboard/generation-clips.jsonl": clips,
            }
        )
        issues = tool._m5_generation_clip_issues(self.root, group)
        self.assertTrue(any("GCLIP_DURATION_MISMATCH" in issue for issue in issues))

    def test_generation_clip_target_requires_its_own_mechanical_report(self) -> None:
        required = tool._required_mechanical_report_kinds(
            ["剧集/EP001/storyboard/generation-clips.jsonl"]
        )
        self.assertEqual(required, {"generation_clips"})

    def test_omitted_artifact_is_accounted_as_delivered(self) -> None:
        accounted = tool._accounted_delivery_artifacts(
            {"EP001:selected"},
            [{"artifact_id": "EP001:omitted", "source": "剧集/EP001/notes.md"}],
        )
        self.assertEqual(accounted, {"EP001:selected", "EP001:omitted"})

    def test_derived_markdown_binds_source_hash_and_compiled_text(self) -> None:
        source_relative = "剧集/EP001/assets/image-prompt-specs.jsonl"
        markdown_relative = "剧集/EP001/assets/image-prompts.md"
        record = {
            "spec_id": "IMG-ONE",
            "generic_prompt": "Task:\n- stable identity\n\nCurrent task:\n- front view",
        }
        source = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        digest = hashlib.sha256(source).hexdigest()
        valid = (
            f"# prompts\n> 来源：`{digest}`\n## IMG-ONE\n"
            "> Task:\n> - stable identity\n> Current task:\n> - front view\n"
        ).encode("utf-8")
        tool._validate_derived_markdown_outputs(
            self.root,
            {source_relative: source, markdown_relative: valid},
        )

        tampered = valid.replace(b"front view", b"rear view")
        with self.assertRaisesRegex(ValueError, "BLK-DERIVED-MARKDOWN"):
            tool._validate_derived_markdown_outputs(
                self.root,
                {source_relative: source, markdown_relative: tampered},
            )

    def test_storyboard_requires_start_keyframe_and_generation_binding(self) -> None:
        shot = {"shot_id": "SHOT-1", "generation_asset_bindings": [{**self._binding(), "fragment_refs": self._fragments()}]}
        group = self._group(
            {
                "剧集/EP001/storyboard/shots.jsonl": [shot],
                "剧集/EP001/storyboard/keyframes.jsonl": [],
            }
        )
        issues, _ = tool._m4b_asset_consumption_issues(self.root, group, self.m2)
        self.assertTrue(any("start keyframe" in issue for issue in issues))

    def test_m3_rejects_occurrence_mismatch_and_invalid_continuity(self) -> None:
        occurrence = {
            "occurrence_id": "OCC-1",
            "asset_kind": "character",
            "source_ref": self._screenplay_ref(),
            "source_blocks": ["BLK-1"],
            "proposed_binding": {"identity_id": "CHAR-OTHER"},
        }
        decision = {
            "decision_id": "DEC-1",
            "decision_kind": "reuse",
            "asset_kind": "character",
            "occurrence_refs": [{"record_id": "OCC-1"}],
            "proposed_binding": {
                "identity_id": "CHAR-TEST",
                "generation_model_id": "MODEL-CHAR-TEST-V1",
                "generation_variant_id": None,
            },
        }
        group = self._group({
            "剧集/EP001/assets/occurrences.jsonl": [occurrence],
            "剧集/EP001/assets/decisions.jsonl": [decision],
            "剧集/EP001/assets/continuity.jsonl": [{}],
        })
        issues = tool._m3_asset_consumption_issues(
            self.root,
            group,
            self.m2,
            self.screenplay_index,
        )
        self.assertTrue(any("differs from occurrence" in issue for issue in issues))
        self.assertTrue(any("continuity delta needs delta_id" in issue for issue in issues))

    def test_m3_requires_live_screenplay_record_hashes(self) -> None:
        block = {
            "record_type": "block",
            "block_id": "BLK-LIVE",
            "kind": "action",
            "content_sha256": "4" * 64,
        }
        m2_group = self._group({
            "剧集/EP001/screenplay-index.jsonl": [block],
        })
        live_evidence, evidence_issues = tool._m2_screenplay_index_evidence(
            self.root,
            m2_group,
        )
        self.assertEqual(evidence_issues, [])
        self.assertEqual(
            live_evidence[1]["BLK-LIVE"] if live_evidence else None,
            tool.sha256_bytes(tool._canonical_record_bytes(block)),
        )
        occurrence = {
            "occurrence_id": "OCC-1",
            "asset_kind": "character",
            "source_ref": {**self._screenplay_ref(), "hash": "2" * 64},
            "source_blocks": ["BLK-1", "BLK-MISSING"],
            "proposed_binding": {"identity_id": "CHAR-TEST"},
        }
        decision = {
            "decision_id": "DEC-1",
            "decision_kind": "reuse",
            "asset_kind": "character",
            "occurrence_refs": [{"record_id": "OCC-1"}],
            "cause_ref": {**self._screenplay_ref(), "hash": "3" * 64},
            "proposed_binding": {
                "identity_id": "CHAR-TEST",
                "generation_model_id": "MODEL-CHAR-TEST-V1",
                "generation_variant_id": None,
            },
        }
        group = self._group({
            "剧集/EP001/assets/occurrences.jsonl": [occurrence],
            "剧集/EP001/assets/decisions.jsonl": [decision],
            "剧集/EP001/assets/continuity.jsonl": [],
        })
        issues = tool._m3_asset_consumption_issues(
            self.root,
            group,
            self.m2,
            self.screenplay_index,
        )
        self.assertTrue(any("exact screenplay source_ref" in issue for issue in issues))
        self.assertTrue(any("invalid screenplay source_blocks" in issue for issue in issues))
        self.assertTrue(any("stale screenplay cause_ref" in issue for issue in issues))

    def test_stage_profiles_and_fragment_fingerprints_are_exact(self) -> None:
        shot = {"shot_id": "SHOT-1", "generation_asset_bindings": [{**self._binding(), "fragment_refs": self._fragments()}]}
        changed = self._fragments()
        changed[-1] = {"fragment_id": "FRAG-NEG", "hash": "2" * 64}
        keyframe = {
            "keyframe_id": "KEY-1",
            "shot_ref": {"record_id": "SHOT-1"},
            "boundary_role": "start",
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "motion", "fragment_refs": changed},
        }
        group = self._group({
            "剧集/EP001/storyboard/shots.jsonl": [shot],
            "剧集/EP001/storyboard/keyframes.jsonl": [keyframe],
        })
        issues, _ = tool._m4b_asset_consumption_issues(self.root, group, self.m2)
        self.assertTrue(any("profile keyframe" in issue for issue in issues))
        self.assertTrue(any("fragment fingerprint" in issue for issue in issues))

    def test_each_shot_requires_and_reconciles_location_binding(self) -> None:
        location_fragments = {
            "FRAG-STYLE": self._fragment_records()["FRAG-STYLE"],
            "LOC-ID": {"fragment_id": "LOC-ID", "fragment_kind": "identity_full", "asset_id": "LOC-TEST", "fragment_hash": "0" * 64},
            "LOC-CONT": {"fragment_id": "LOC-CONT", "fragment_kind": "continuity_lock", "asset_id": "LOC-TEST", "fragment_hash": "0" * 64},
            "LOC-VIEW": {"fragment_id": "LOC-VIEW", "fragment_kind": "view_projection", "asset_id": "LOC-TEST", "scope": {"view_id": "GVIEW-LOC-TEST"}, "fragment_hash": "0" * 64},
            "LOC-NEG": {"fragment_id": "LOC-NEG", "fragment_kind": "negative_lock", "asset_id": "LOC-TEST", "fragment_hash": "0" * 64},
        }
        m2 = {
            **self.m2,
            "LOC-TEST": {
                "model_id": "SPATIAL-LOC-TEST",
                "asset_kind": "location",
                "view_ids": {"GVIEW-LOC-TEST"},
                "variant_ids": set(),
                "fragment_ids": set(location_fragments),
                "fragments": location_fragments,
            },
        }
        shot = {"shot_id": "SHOT-1", "generation_asset_bindings": [{**self._binding(), "fragment_refs": self._fragments()}]}
        keyframe = {
            "keyframe_id": "KEY-1", "shot_ref": {"record_id": "SHOT-1"},
            "boundary_role": "start", "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "keyframe", "fragment_refs": self._fragments()},
        }
        group = self._group({
            "剧集/EP001/storyboard/shots.jsonl": [shot],
            "剧集/EP001/storyboard/keyframes.jsonl": [keyframe],
        })
        issues, _ = tool._m4b_asset_consumption_issues(self.root, group, m2)
        self.assertTrue(any("location generation binding" in issue for issue in issues))

    def test_multi_asset_keyframe_uses_binding_order_for_same_kind_fragments(self) -> None:
        second_fragments = {
            "FRAG-STYLE": self._fragment_records()["FRAG-STYLE"],
            "PROP-ID": {"fragment_id": "PROP-ID", "fragment_kind": "identity_full", "asset_id": "PROP-TEST", "fragment_hash": "0" * 64},
            "PROP-CONT": {"fragment_id": "PROP-CONT", "fragment_kind": "continuity_lock", "asset_id": "PROP-TEST", "fragment_hash": "0" * 64},
            "PROP-VIEW": {"fragment_id": "PROP-VIEW", "fragment_kind": "view_projection", "asset_id": "PROP-TEST", "scope": {"view_id": "GVIEW-PROP-TEST"}, "fragment_hash": "0" * 64},
            "PROP-NEG": {"fragment_id": "PROP-NEG", "fragment_kind": "negative_lock", "asset_id": "PROP-TEST", "fragment_hash": "0" * 64},
        }
        m2 = {
            **self.m2,
            "PROP-TEST": {
                "model_id": "MODEL-PROP-TEST-V1",
                "asset_kind": "prop",
                "view_ids": {"GVIEW-PROP-TEST"},
                "variant_ids": set(),
                "fragment_ids": set(second_fragments),
                "fragments": second_fragments,
            },
        }
        char_binding = {**self._binding(), "fragment_refs": self._fragments()}
        prop_refs = [
            {"fragment_id": fragment_id, "hash": "0" * 64}
            for fragment_id in ("FRAG-STYLE", "PROP-ID", "PROP-CONT", "PROP-VIEW", "PROP-NEG")
        ]
        prop_binding = {
            "asset_id": "PROP-TEST",
            "model_id": "MODEL-PROP-TEST-V1",
            "view_id": "GVIEW-PROP-TEST",
            "variant_id": None,
            "fragment_refs": prop_refs,
        }
        combined = [
            {"fragment_id": fragment_id, "hash": "0" * 64}
            for fragment_id in (
                "FRAG-STYLE",
                "FRAG-ID",
                "PROP-ID",
                "FRAG-CONT",
                "PROP-CONT",
                "FRAG-VIEW",
                "PROP-VIEW",
                "FRAG-NEG",
                "PROP-NEG",
            )
        ]
        shot = {
            "shot_id": "SHOT-1",
            "generation_asset_bindings": [char_binding, prop_binding],
        }
        keyframe = {
            "keyframe_id": "KEY-1",
            "shot_ref": {"record_id": "SHOT-1"},
            "boundary_role": "start",
            "asset_bindings": [self._binding(), {key: value for key, value in prop_binding.items() if key != "fragment_refs"}],
            "prompt_components": {"profile": "keyframe", "fragment_refs": combined},
        }
        group = self._group({
            "剧集/EP001/storyboard/shots.jsonl": [shot],
            "剧集/EP001/storyboard/keyframes.jsonl": [keyframe],
        })
        issues, _ = tool._m4b_asset_consumption_issues(self.root, group, m2)
        self.assertEqual(issues, [])

        keyframe["prompt_components"]["fragment_refs"][1:3] = reversed(
            keyframe["prompt_components"]["fragment_refs"][1:3]
        )
        group = self._group({
            "剧集/EP001/storyboard/shots.jsonl": [shot],
            "剧集/EP001/storyboard/keyframes.jsonl": [keyframe],
        })
        issues, _ = tool._m4b_asset_consumption_issues(self.root, group, m2)
        self.assertTrue(any("fragment fingerprint differs" in issue for issue in issues))

    def test_m2_rejects_duplicate_and_extra_view_fragment_declarations(self) -> None:
        generation = self.root / "设定集" / "generation"
        scope = {"asset_id": "CHAR-TEST", "asset_kind": "character"}
        model = {"model_id": "MODEL-CHAR-TEST-V1", "asset_id": "CHAR-TEST"}
        views = [
            {"view_id": "VIEW-1", "asset_id": "CHAR-TEST", "model_ref": {"record_id": model["model_id"]}},
            {"view_id": "VIEW-2", "asset_id": "CHAR-TEST", "model_ref": {"record_id": model["model_id"]}},
        ]
        fragments = [
            {"fragment_id": "STYLE", "fragment_kind": "style_core", "asset_id": None},
            {"fragment_id": "ID", "fragment_kind": "identity_full", "asset_id": "CHAR-TEST", "model_refs": [{"record_id": model["model_id"]}]},
            {"fragment_id": "CONT", "fragment_kind": "continuity_lock", "asset_id": "CHAR-TEST", "model_refs": [{"record_id": model["model_id"]}]},
            {"fragment_id": "VIEW-1-FRAG", "fragment_kind": "view_projection", "asset_id": "CHAR-TEST", "scope": {"view_id": "VIEW-1"}, "model_refs": [{"record_id": "VIEW-1"}]},
            {"fragment_id": "VIEW-2-FRAG", "fragment_kind": "view_projection", "asset_id": "CHAR-TEST", "scope": {"view_id": "VIEW-2"}, "model_refs": [{"record_id": "VIEW-2"}]},
            {"fragment_id": "NEG", "fragment_kind": "negative_lock", "asset_id": "CHAR-TEST", "model_refs": [{"record_id": model["model_id"]}]},
        ]
        files = {
            "asset-scope.jsonl": [scope],
            "asset-models.jsonl": [model],
            "spatial-models.jsonl": [],
            "variant-models.jsonl": [],
            "view-contracts.jsonl": views,
            "canonical-fragments.jsonl": fragments,
        }
        for name, records in files.items():
            (generation / name).write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
        card_relative = "剧集/EP001/episode-card.json"
        card = {
            "generation_asset_bindings": [{
                "asset_id": "CHAR-TEST",
                "model_id": model["model_id"],
                "view_ids": ["VIEW-1", "VIEW-1"],
                "variant_ids": [],
                "fragment_ids": [record["fragment_id"] for record in fragments],
            }]
        }
        card_path = self.root / card_relative
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(json.dumps(card), encoding="utf-8")
        primary_fields = {
            "asset-scope.jsonl": "asset_id",
            "asset-models.jsonl": "model_id",
            "spatial-models.jsonl": "model_id",
            "variant-models.jsonl": "variant_id",
            "view-contracts.jsonl": "view_id",
            "canonical-fragments.jsonl": "fragment_id",
        }
        input_records = {
            f"设定集/generation/{name}": {
                str(record[primary_fields[name]]): "0" * 64
                for record in records
            }
            for name, records in files.items()
        }
        issues = tool._m2_generation_binding_issues(
            self.root,
            target_paths=[card_relative],
            input_records=input_records,
        )
        self.assertTrue(any("duplicate view_ids" in issue for issue in issues))
        self.assertTrue(any("do not exactly match view_projection" in issue for issue in issues))

    def test_stage_record_ids_are_required_and_unique(self) -> None:
        board = {
            "spec_id": "IMG-DUP",
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "asset_board", "fragment_refs": self._fragments()},
        }
        group = self._group({
            "剧集/EP001/assets/image-prompt-specs.jsonl": [board, dict(board)],
        })
        issues = tool._m4a_asset_consumption_issues(self.root, group, self.m2)
        self.assertTrue(any("duplicate M4a spec_id" in issue for issue in issues))

        shot_binding = {**self._binding(), "fragment_refs": self._fragments()}
        shot = {"shot_id": "SHOT-DUP", "generation_asset_bindings": [shot_binding]}
        keyframe = {
            "keyframe_id": "KEY-DUP",
            "shot_ref": {"record_id": "SHOT-DUP"},
            "boundary_role": "start",
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "keyframe", "fragment_refs": self._fragments()},
        }
        group = self._group({
            "剧集/EP001/storyboard/shots.jsonl": [shot, dict(shot)],
            "剧集/EP001/storyboard/keyframes.jsonl": [keyframe, dict(keyframe)],
        })
        issues, signatures = tool._m4b_asset_consumption_issues(self.root, group, self.m2)
        self.assertTrue(any("duplicate M4b shot_id" in issue for issue in issues))
        self.assertTrue(any("duplicate M4b keyframe_id" in issue for issue in issues))

        motion = {
            "motion_id": "MOTION-DUP",
            "shot_ref": {"record_id": "SHOT-DUP"},
            "asset_bindings": [self._binding()],
            "prompt_components": {"profile": "motion", "fragment_refs": self._fragments()},
        }
        group = self._group({
            "剧集/EP001/storyboard/motion-specs.jsonl": [motion, dict(motion)],
        })
        issues = tool._m5_asset_consumption_issues(self.root, group, signatures, self.m2)
        self.assertTrue(any("duplicate M5 motion_id" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
