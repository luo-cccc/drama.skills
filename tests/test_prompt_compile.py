from __future__ import annotations

import importlib.util
import copy
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/short-drama-image-prompts/scripts/prompt_compile.py"
SPEC = importlib.util.spec_from_file_location("prompt_compile_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
COMPILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPILER)


def fragment(fragment_id: str, kind: str, text: str) -> dict:
    record_id = {
        "variant_delta": "VAR-1",
        "view_projection": "VIEW-1",
    }.get(kind, "MODEL-1")
    value = {
        "fragment_id": fragment_id,
        "fragment_kind": kind,
        "asset_id": None if kind == "style_core" else "CHAR-1",
        "language": "en",
        "scope": {"view_id": "VIEW-1"} if kind == "view_projection" else {"jobs": ["keyframe"]},
        "model_refs": [] if kind == "style_core" else (
            [{"record_id": record_id}, {"record_id": "MODEL-1"}]
            if kind == "variant_delta"
            else [{"record_id": record_id}]
        ),
        "input_hashes": {record_id: "a" * 64},
        "text": text,
    }
    if kind == "variant_delta":
        value["variant_id"] = "VAR-1"
    value["fragment_hash"] = COMPILER.fragment_hash(value)
    return value


class PromptCompileTests(unittest.TestCase):
    def setUp(self) -> None:
        records = [
            fragment("STYLE", "style_core", "style"),
            fragment("ID", "identity_full", "identity"),
            fragment("CONT", "continuity_lock", "continuity"),
            fragment("VAR", "variant_delta", "wet coat"),
            fragment("VIEW", "view_projection", "front view"),
            fragment("NEG", "negative_lock", "no drift"),
        ]
        self.fragments = {record["fragment_id"]: record for record in records}
        self.record = {
            "language": "en",
            "asset_bindings": [{"asset_id": "CHAR-1", "model_id": "MODEL-1", "variant_id": "VAR-1", "view_id": "VIEW-1"}],
            "task_and_format": "Generate one keyframe.",
            "prompt_components": {
                "profile": "keyframe",
                "fragment_refs": [
                    {"fragment_id": record["fragment_id"], "hash": record["fragment_hash"]}
                    for record in records
                ],
                "local_instructions": ["medium shot", "character raises the right hand"],
                "local_negative_constraints": ["no readable text"],
            },
        }

    def _scene_record(self, name: str) -> tuple[dict, dict[str, dict]]:
        fragments = copy.deepcopy(self.fragments)
        for value in fragments.values():
            if value.get("fragment_kind") != "style_core":
                value["asset_id"] = "LOC-1"
            if value.get("fragment_kind") == "view_projection":
                value["scope"] = {"sheet_profile": name}
                value["model_refs"] = [{"record_id": "SPATIAL-LOC-1"}]
            else:
                value["scope"] = {"jobs": ["asset_board"]}
                if value.get("fragment_kind") not in {"style_core", "variant_delta"}:
                    value["model_refs"] = [{"record_id": "SPATIAL-LOC-1"}]
            if value.get("fragment_kind") == "variant_delta":
                value["model_refs"] = [
                    {"record_id": "VAR-1"},
                    {"record_id": "SPATIAL-LOC-1"},
                ]
            value["fragment_hash"] = COMPILER.fragment_hash(value)
        record = copy.deepcopy(self.record)
        record["purpose"] = "location_plate"
        record["asset_bindings"] = [{
            "asset_id": "LOC-1",
            "model_id": "SPATIAL-LOC-1",
            "variant_id": "VAR-1",
        }]
        record["prompt_components"]["profile"] = "asset_board"
        record["prompt_components"]["fragment_refs"] = [
            {"fragment_id": ref["fragment_id"], "hash": fragments[ref["fragment_id"]]["fragment_hash"]}
            for ref in record["prompt_components"]["fragment_refs"]
        ]
        common = {
            "name": name,
            "shared_scale": True,
            "board_aspect_ratio": "16:9",
            "safe_margin": True,
            "orientation_basis_ref": {
                "owner": "short-drama-assets",
                "artifact": "设定集/generation/spatial-models.jsonl",
                "hash": "b" * 64,
                "record_id": "SPATIAL-LOC-1",
                "field": "/coordinate_system",
            },
            "evidence_display": dict(COMPILER.SHEET_PROFILE_EVIDENCE_DISPLAY),
            "evidence_bindings": [
                {
                    "element_id": "north door",
                    "status": "confirmed",
                    "prompt_group": "opening",
                    "source_ref": {
                        "owner": "short-drama-assets",
                        "artifact": "设定集/generation/spatial-models.jsonl",
                        "hash": "b" * 64,
                        "record_id": "SPATIAL-LOC-1",
                        "field": "/evidence_elements/north_door",
                    },
                },
                {
                    "element_id": "unseen rear service recess",
                    "status": "unknown",
                    "prompt_group": "region",
                    "source_ref": {
                        "owner": "short-drama-assets",
                        "artifact": "设定集/generation/spatial-models.jsonl",
                        "hash": "b" * 64,
                        "record_id": "SPATIAL-LOC-1",
                        "field": "/evidence_elements/unseen_rear_service_recess",
                    },
                },
            ],
            "annotation_treatment": {
                "mode": "postproduction",
                "generated_text": "none",
                "unknown_label": "needs_confirmation",
            },
        }
        if name == "scene_orthographic":
            common.update(
                {
                    "projection": "orthographic",
                    "panels": ["front", "left", "right", "back"],
                    "layout": "horizontal_4_panel",
                    "cutaway_policy": "hide_obstructing_wall_only",
                }
            )
        else:
            common.update(
                {
                    "projection": "orthographic_top_down_90",
                    "panels": ["top"],
                    "layout": "single_top_panel",
                    "roof_policy": "remove_roof_and_ceiling",
                }
            )
        record["sheet_profile"] = common
        return record, fragments

    def test_compile_is_ordered_and_idempotent(self) -> None:
        first = COMPILER.compile_record(self.record, self.fragments)
        second = COMPILER.compile_record(first, self.fragments)
        self.assertEqual(first, second)
        prompt = first["generic_prompt"]
        headings = ["Task and format:", "Fixed asset baseline:", "State delta:", "View and spatial projection:", "Current task:", "Exclusions:"]
        self.assertEqual([prompt.index(value) for value in headings], sorted(prompt.index(value) for value in headings))
        COMPILER.validate_compiled_record(first, self.fragments)

    def test_record_language_is_persisted_and_declared_mismatch_fails(self) -> None:
        derived = copy.deepcopy(self.record)
        del derived["language"]
        self.assertEqual(COMPILER.compile_record(derived, self.fragments)["language"], "en")
        mismatch = copy.deepcopy(self.record)
        mismatch["language"] = "zh-CN"
        with self.assertRaisesRegex(COMPILER.CompileError, "record language"):
            COMPILER.compile_record(mismatch, self.fragments)

    def test_fragment_library_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "canonical-fragments.jsonl"
            source.write_text(
                "".join(
                    json.dumps(record, ensure_ascii=False) + "\n"
                    for record in self.fragments.values()
                ),
                encoding="utf-8",
            )
            first = COMPILER.render_fragment_library(source)
            second = COMPILER.render_fragment_library(source)
            self.assertEqual(first, second)
            self.assertIn(COMPILER.hashlib.sha256(source.read_bytes()).hexdigest(), first)
            for fragment_id, record in self.fragments.items():
                self.assertIn(fragment_id, first)
                self.assertIn(record["fragment_hash"], first)
                self.assertIn(record["text"], first)

    def test_reordered_or_tampered_fragments_fail(self) -> None:
        reordered = {**self.record, "prompt_components": dict(self.record["prompt_components"])}
        reordered["prompt_components"]["fragment_refs"] = list(reversed(self.record["prompt_components"]["fragment_refs"]))
        with self.assertRaisesRegex(COMPILER.CompileError, "canonical order"):
            COMPILER.compile_record(reordered, self.fragments)
        tampered = {key: dict(value) if isinstance(value, dict) else value for key, value in self.fragments.items()}
        tampered["ID"]["text"] = "changed identity"
        with self.assertRaisesRegex(COMPILER.CompileError, "fragment hash mismatch"):
            COMPILER.compile_record(self.record, tampered)

    def test_output_or_manifest_tampering_fails(self) -> None:
        compiled = COMPILER.compile_record(self.record, self.fragments)
        changed_prompt = dict(compiled)
        changed_prompt["generic_prompt"] += " free rewrite"
        with self.assertRaisesRegex(COMPILER.CompileError, "generic_prompt"):
            COMPILER.validate_compiled_record(changed_prompt, self.fragments)
        changed_manifest = dict(compiled)
        changed_manifest["compilation_manifest"] = dict(compiled["compilation_manifest"])
        changed_manifest["compilation_manifest"]["output_hash"] = "0" * 64
        with self.assertRaisesRegex(COMPILER.CompileError, "compilation_manifest"):
            COMPILER.validate_compiled_record(changed_manifest, self.fragments)

    def test_asset_bindings_are_required(self) -> None:
        record = dict(self.record)
        record.pop("asset_bindings")
        with self.assertRaisesRegex(COMPILER.CompileError, "asset_bindings"):
            COMPILER.compile_record(record, self.fragments)

    def test_wrong_asset_profile_view_or_variant_fail(self) -> None:
        wrong_asset = {key: dict(value) for key, value in self.fragments.items()}
        wrong_asset["ID"]["asset_id"] = "CHAR-OTHER"
        wrong_asset["ID"]["fragment_hash"] = COMPILER.fragment_hash(wrong_asset["ID"])
        refs = self.record["prompt_components"]["fragment_refs"]
        record = {**self.record, "prompt_components": {**self.record["prompt_components"], "fragment_refs": [
            {"fragment_id": ref["fragment_id"], "hash": wrong_asset[ref["fragment_id"]]["fragment_hash"]}
            for ref in refs
        ]}}
        with self.assertRaisesRegex(COMPILER.CompileError, "asset does not match"):
            COMPILER.compile_record(record, wrong_asset)

        wrong_profile = {key: dict(value) for key, value in self.fragments.items()}
        wrong_profile["ID"]["scope"] = {"jobs": ["motion"]}
        wrong_profile["ID"]["fragment_hash"] = COMPILER.fragment_hash(wrong_profile["ID"])
        record = {**self.record, "prompt_components": {**self.record["prompt_components"], "fragment_refs": [
            {"fragment_id": ref["fragment_id"], "hash": wrong_profile[ref["fragment_id"]]["fragment_hash"]}
            for ref in refs
        ]}}
        with self.assertRaisesRegex(COMPILER.CompileError, "profile"):
            COMPILER.compile_record(record, wrong_profile)

        wrong_view = {**self.record, "asset_bindings": [{**self.record["asset_bindings"][0], "view_id": "VIEW-OTHER"}]}
        with self.assertRaisesRegex(COMPILER.CompileError, "bound view"):
            COMPILER.compile_record(wrong_view, self.fragments)

        wrong_variant = {**self.record, "asset_bindings": [{**self.record["asset_bindings"][0], "variant_id": "VAR-OTHER"}]}
        with self.assertRaisesRegex(COMPILER.CompileError, "bound variant"):
            COMPILER.compile_record(wrong_variant, self.fragments)

    def test_chinese_language_uses_chinese_sections(self) -> None:
        fragments = {key: dict(value) for key, value in self.fragments.items()}
        for value in fragments.values():
            value["language"] = "zh-CN"
            value["fragment_hash"] = COMPILER.fragment_hash(value)
        record = {**self.record, "language": "zh-CN", "prompt_components": {**self.record["prompt_components"], "fragment_refs": [
            {"fragment_id": ref["fragment_id"], "hash": fragments[ref["fragment_id"]]["fragment_hash"]}
            for ref in self.record["prompt_components"]["fragment_refs"]
        ]}}
        self.assertIn("任务与格式:", COMPILER.compile_record(record, fragments)["generic_prompt"])

    def test_expected_profile_is_enforced(self) -> None:
        with self.assertRaisesRegex(COMPILER.CompileError, "must be motion"):
            COMPILER.compile_record(
                self.record,
                self.fragments,
                expected_profile="motion",
            )

    def test_same_kind_fragments_follow_asset_binding_order(self) -> None:
        second = {
            key: dict(value)
            for key, value in self.fragments.items()
        }
        for fragment_id, value in list(second.items()):
            if value.get("fragment_kind") == "style_core":
                continue
            copy = dict(value)
            copy["fragment_id"] = "B-" + fragment_id
            copy["asset_id"] = "CHAR-2"
            copy["model_refs"] = [
                {"record_id": "VAR-2"},
                {"record_id": "MODEL-2"},
            ] if copy["fragment_kind"] == "variant_delta" else [{
                "record_id": "VIEW-2" if copy["fragment_kind"] == "view_projection" else "MODEL-2"
            }]
            if copy["fragment_kind"] == "variant_delta":
                copy["variant_id"] = "VAR-2"
            if copy["fragment_kind"] == "view_projection":
                copy["scope"] = {"view_id": "VIEW-2"}
            copy["fragment_hash"] = COMPILER.fragment_hash(copy)
            second[copy["fragment_id"]] = copy
        merged = {**self.fragments, **second}
        by_kind: dict[str, list[dict]] = {}
        for value in merged.values():
            by_kind.setdefault(value["fragment_kind"], []).append(value)
        ordered = [self.fragments["STYLE"]]
        for kind in ("identity_full", "continuity_lock", "variant_delta", "view_projection", "negative_lock"):
            ordered.extend(sorted(by_kind[kind], key=lambda item: item["asset_id"]))
        record = {
            "asset_bindings": [
                {"asset_id": "CHAR-1", "model_id": "MODEL-1", "variant_id": "VAR-1", "view_id": "VIEW-1"},
                {"asset_id": "CHAR-2", "model_id": "MODEL-2", "variant_id": "VAR-2", "view_id": "VIEW-2"},
            ],
            "task_and_format": "Generate one keyframe.",
            "prompt_components": {
                "profile": "keyframe",
                "fragment_refs": [
                    {"fragment_id": item["fragment_id"], "hash": item["fragment_hash"]}
                    for item in ordered
                ],
            },
        }
        COMPILER.compile_record(record, merged)
        swapped = {**record, "prompt_components": dict(record["prompt_components"])}
        refs = list(record["prompt_components"]["fragment_refs"])
        refs[1], refs[2] = refs[2], refs[1]
        swapped["prompt_components"]["fragment_refs"] = refs
        with self.assertRaisesRegex(COMPILER.CompileError, "canonical order"):
            COMPILER.compile_record(swapped, merged)

    def test_scene_sheet_profiles_compile(self) -> None:
        orthographic, fragments = self._scene_record("scene_orthographic")
        compiled = COMPILER.compile_record(orthographic, fragments, expected_profile="asset_board")
        self.assertEqual(compiled["sheet_profile"]["panels"], ["front", "left", "right", "back"])
        self.assertIn("Scene sheet profile:", compiled["generic_prompt"])
        self.assertIn("Front, Left, Right, Back", compiled["generic_prompt"])
        self.assertIn("16:9 horizontal four-panel", compiled["generic_prompt"])
        self.assertNotIn("north door", compiled["generic_prompt"])
        self.assertEqual(len(compiled["sheet_profile"]["evidence_bindings"]), 2)

        top_view, fragments = self._scene_record("scene_top_view")
        compiled = COMPILER.compile_record(top_view, fragments, expected_profile="asset_board")
        self.assertIn("geography base plate", compiled["generic_prompt"])
        self.assertIn("postproduction", compiled["generic_prompt"])
        self.assertNotIn("storyboard", compiled["generic_prompt"])

    def test_scene_sheet_profiles_reject_invalid_ownership_or_geometry(self) -> None:
        wrong_asset, fragments = self._scene_record("scene_orthographic")
        wrong_asset["asset_bindings"][0]["asset_id"] = "CHAR-1"
        with self.assertRaisesRegex(COMPILER.CompileError, "LOC- id"):
            COMPILER.compile_record(wrong_asset, fragments)

        wrong_order, fragments = self._scene_record("scene_orthographic")
        wrong_order["sheet_profile"]["panels"] = ["front", "right", "left", "back"]
        with self.assertRaisesRegex(COMPILER.CompileError, "canonical order"):
            COMPILER.compile_record(wrong_order, fragments)

        wrong_layout, fragments = self._scene_record("scene_orthographic")
        wrong_layout["sheet_profile"]["layout"] = "vertical_4_panel"
        with self.assertRaisesRegex(COMPILER.CompileError, "horizontal_4_panel"):
            COMPILER.compile_record(wrong_layout, fragments)

        missing_margin, fragments = self._scene_record("scene_top_view")
        missing_margin["sheet_profile"]["safe_margin"] = False
        with self.assertRaisesRegex(COMPILER.CompileError, "safe_margin"):
            COMPILER.compile_record(missing_margin, fragments)

        wrong_overlay, fragments = self._scene_record("scene_top_view")
        wrong_overlay["sheet_profile"]["overlay_refs"] = {}
        with self.assertRaisesRegex(COMPILER.CompileError, "do not accept storyboard overlays"):
            COMPILER.compile_record(wrong_overlay, fragments)

        wrong_orientation, fragments = self._scene_record("scene_top_view")
        wrong_orientation["sheet_profile"]["orientation_basis_ref"]["record_id"] = "SPATIAL-OTHER"
        with self.assertRaisesRegex(COMPILER.CompileError, "bound spatial model"):
            COMPILER.compile_record(wrong_orientation, fragments)

        wrong_evidence, fragments = self._scene_record("scene_top_view")
        wrong_evidence["sheet_profile"]["evidence_bindings"] = []
        with self.assertRaisesRegex(COMPILER.CompileError, "evidence_bindings"):
            COMPILER.compile_record(wrong_evidence, fragments)

        missing_evidence_field, fragments = self._scene_record("scene_top_view")
        del missing_evidence_field["sheet_profile"]["evidence_bindings"][0]["source_ref"]["field"]
        with self.assertRaisesRegex(COMPILER.CompileError, "evidence_elements"):
            COMPILER.compile_record(missing_evidence_field, fragments)

        wrong_evidence_model, fragments = self._scene_record("scene_top_view")
        wrong_evidence_model["sheet_profile"]["evidence_bindings"][0]["source_ref"]["record_id"] = "SPATIAL-OTHER"
        with self.assertRaisesRegex(COMPILER.CompileError, "bound spatial model"):
            COMPILER.compile_record(wrong_evidence_model, fragments)

        generated_label, fragments = self._scene_record("scene_top_view")
        generated_label["sheet_profile"]["annotation_treatment"]["mode"] = "readable"
        with self.assertRaisesRegex(COMPILER.CompileError, "postproduction"):
            COMPILER.compile_record(generated_label, fragments)


if __name__ == "__main__":
    unittest.main()
