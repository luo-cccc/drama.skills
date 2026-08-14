from __future__ import annotations

import importlib.util
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

    def test_compile_is_ordered_and_idempotent(self) -> None:
        first = COMPILER.compile_record(self.record, self.fragments)
        second = COMPILER.compile_record(first, self.fragments)
        self.assertEqual(first, second)
        prompt = first["generic_prompt"]
        headings = ["Task and format:", "Fixed asset baseline:", "State delta:", "View and spatial projection:", "Current task:", "Exclusions:"]
        self.assertEqual([prompt.index(value) for value in headings], sorted(prompt.index(value) for value in headings))
        COMPILER.validate_compiled_record(first, self.fragments)

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
        record = {**self.record, "prompt_components": {**self.record["prompt_components"], "fragment_refs": [
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


if __name__ == "__main__":
    unittest.main()
