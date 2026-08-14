from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/short-drama-assets/scripts/asset_baseline_check.py"
SPEC = importlib.util.spec_from_file_location("asset_baseline_check_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def digest(record: dict) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AssetBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        for name in (
            "asset-scope.jsonl",
            "asset-models.jsonl",
            "spatial-models.jsonl",
            "variant-models.jsonl",
            "view-contracts.jsonl",
        ):
            (self.directory / name).write_text("", encoding="utf-8")
        (self.directory / "asset-baseline.md").write_text("# baseline\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, name: str, records: list[dict]) -> None:
        text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        (self.directory / name).write_text(text, encoding="utf-8")

    def _scope(self, asset_id: str, kind: str, tier: str) -> dict:
        return {
            "asset_id": asset_id,
            "asset_kind": kind,
            "tier": tier,
            "classification_reasons": ["reused and narratively visible"],
            "reuse_scope": {"episodes": ["EP001"], "jobs": ["asset_board"]},
            "creator_acceptance": {"status": "accepted"},
        }

    def _compact(self, asset_id: str, kind: str) -> dict:
        return {
            "model_id": f"MODEL-{asset_id}",
            "asset_id": asset_id,
            "asset_kind": kind,
            "tier": "compact",
            "scale": "one metre reference scale",
            "silhouette": "stable asymmetric silhouette",
            "materials": ["matte material"],
            "intrinsic_colors": ["black", "white"],
            "recognition_anchors": ["left notch", "three-part outline"],
            "state_boundary": "pose and temporary damage may change",
            "forbidden_drift": ["do not mirror the notch"],
            "standard_view": "front three-quarter view",
        }

    def _full(self, asset_id: str, kind: str) -> dict:
        common = {
            "model_id": f"MODEL-{asset_id}",
            "asset_id": asset_id,
            "asset_kind": kind,
            "tier": "full",
            "scale": "one metre reference scale",
            "proportions": "stable 2:1 height-width relation",
            "silhouette": "stable asymmetric silhouette",
            "materials": ["matte material"],
            "intrinsic_colors": ["black", "white"],
            "structure_layers": ["base", "variant"],
            "permanent_marks": ["left notch"],
            "asymmetry": ["left notch stays left"],
            "allowed_changes": ["pose", "temporary damage"],
            "forbidden_drift": ["do not mirror"],
            "text_policy": {"mode": "no_readable_text"},
        }
        kind_fields = {
            "character": {"head_face": "narrow", "body": "lean", "hair": "short", "limbs": "four", "neutral_pose": "standing", "relative_scale": "adult"},
            "creature": {"head_face": "long", "body": "low", "covering": "short fur", "limbs": "four", "neutral_pose": "standing", "relative_scale": "waist high"},
            "prop": {"orthographic_forms": "front side back", "part_connections": "hinged", "moving_parts": "lid", "function_interfaces": "handle", "handling": "right hand", "permanent_wear": "left corner"},
            "vehicle": {"orthographic_forms": "front side back", "part_connections": "fixed chassis", "moving_parts": "doors", "function_interfaces": "controls", "occupancy": "two seats", "permanent_wear": "left panel"},
            "effect": {"emission_source": "left palm", "targets": "door", "shape": "arc", "effect_scale": "two metres", "color_hierarchy": "white core blue rim", "material_response": "wet reflection", "start_state": "spark", "peak_state": "arc", "end_state": "embers", "preserve_set": "door remains intact"},
        }
        common.update(kind_fields[kind])
        return common

    def _location_full(self, asset_id: str) -> dict:
        value = self._full(asset_id, "character")
        for field in ("head_face", "body", "hair", "limbs", "neutral_pose", "relative_scale"):
            value.pop(field)
        value.update({
            "model_id": f"MODEL-{asset_id}", "location_id": asset_id,
            "asset_kind": "location", "tier": "full",
            "coordinate_system": {"north": "door", "origin": "southwest floor"},
            "dimensions": {"width_m": 4, "depth_m": 6, "height_m": 3},
            "functional_zones": ["entry", "work"], "entrances": ["north door"],
            "connections": ["north door to hall"], "fixed_anchors": ["door", "desk"],
            "pairwise_relations": ["desk east of door"], "movement_paths": ["door to desk"],
            "occlusions": ["desk hides legs"], "fixed_light_sources": ["east window"],
            "dressing_boundary": "chairs may move", "forbidden_drift": ["door stays north"],
        })
        value.pop("asset_id", None)
        return value

    def _view(self, model: dict, asset_id: str) -> dict:
        return {
            "view_id": f"VIEW-{asset_id}", "asset_id": asset_id,
            "model_ref": {
                "artifact": "设定集/generation/spatial-models.jsonl" if model["asset_kind"] == "location" else "设定集/generation/asset-models.jsonl",
                "record_id": model["model_id"], "record_hash": digest(model),
            },
            "orientation": "front", "must_show": ["all anchors"],
            "must_preserve": ["scale"], "must_not_change": ["asymmetry"],
        }

    def test_six_asset_kinds_pass_full_and_compact(self) -> None:
        scopes: list[dict] = []
        models: list[dict] = []
        spatial: list[dict] = []
        views: list[dict] = []
        for kind in sorted(CHECKER.ASSET_KINDS):
            for tier in ("full", "compact"):
                asset_id = f"{kind.upper()}-{tier.upper()}"
                scope = self._scope(asset_id, kind, tier)
                if kind == "location" and tier == "full":
                    model = self._location_full(asset_id)
                else:
                    model = self._compact(asset_id, kind) if tier == "compact" else self._full(asset_id, kind)
                scopes.append(scope)
                (spatial if kind == "location" else models).append(model)
                views.append(self._view(model, asset_id))
        self._write("asset-scope.jsonl", scopes)
        self._write("asset-models.jsonl", models)
        self._write("spatial-models.jsonl", spatial)
        self._write("view-contracts.jsonl", views)
        result = CHECKER.validate_m15a(self.directory)
        self.assertEqual(result["status"], "pass", result["findings"])

    def test_missing_nested_placeholder_and_anchor_count_fail(self) -> None:
        scope = self._scope("CHAR-BAD", "character", "compact")
        model = self._compact("CHAR-BAD", "character")
        model["materials"] = ["待定"]
        model["recognition_anchors"] = ["only one"]
        self._write("asset-scope.jsonl", [scope])
        self._write("asset-models.jsonl", [model])
        self._write("view-contracts.jsonl", [self._view(model, "CHAR-BAD")])
        result = CHECKER.validate_m15a(self.directory)
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("M15_MODEL_FIELD", codes)
        self.assertIn("M15_MODEL_ANCHORS", codes)

    def test_explicitly_empty_optional_collections_are_not_missing(self) -> None:
        scope = self._scope("CHAR-CLEAN", "character", "full")
        model = self._full("CHAR-CLEAN", "character")
        model["permanent_marks"] = []
        model["asymmetry"] = []
        model["text_policy"] = {"mode": "no_readable_text", "surfaces": []}
        model["limbs"] = {"hands": "five fingers", "attachments": []}
        self._write("asset-scope.jsonl", [scope])
        self._write("asset-models.jsonl", [model])
        self._write("view-contracts.jsonl", [self._view(model, "CHAR-CLEAN")])
        result = CHECKER.validate_m15a(self.directory)
        self.assertEqual(result["status"], "pass", result["findings"])

    def test_view_rejects_stale_model_record_hash(self) -> None:
        scope = self._scope("PROP-ONE", "prop", "compact")
        model = self._compact("PROP-ONE", "prop")
        view = self._view(model, "PROP-ONE")
        view["model_ref"]["record_hash"] = "0" * 64
        self._write("asset-scope.jsonl", [scope])
        self._write("asset-models.jsonl", [model])
        self._write("view-contracts.jsonl", [view])
        result = CHECKER.validate_m15a(self.directory)
        self.assertIn("M15_VIEW_MODEL_STALE", {finding["code"] for finding in result["findings"]})

    def test_full_location_and_variant_base_are_strict(self) -> None:
        scope = self._scope("LOCATION-ONE", "location", "full")
        model = self._location_full("LOCATION-ONE")
        model.pop("materials")
        self._write("asset-scope.jsonl", [scope])
        self._write("spatial-models.jsonl", [model])
        self._write("view-contracts.jsonl", [self._view(model, "LOCATION-ONE")])
        self._write("variant-models.jsonl", [{
            "variant_id": "VAR-MISSING", "base_asset_id": "PROP-MISSING",
            "changes": ["wet"], "preserve": ["shape"], "validity": {"from": "EP001"},
        }])
        result = CHECKER.validate_m15a(self.directory)
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("M15_MODEL_FIELD", codes)
        self.assertIn("M15_VARIANT_BASE", codes)

    def test_duplicate_view_id_is_rejected(self) -> None:
        scope = self._scope("CHAR-ONE", "character", "compact")
        model = self._compact("CHAR-ONE", "character")
        view = self._view(model, "CHAR-ONE")
        self._write("asset-scope.jsonl", [scope])
        self._write("asset-models.jsonl", [model])
        self._write("view-contracts.jsonl", [view, dict(view)])
        result = CHECKER.validate_m15a(self.directory)
        self.assertIn("M15_VIEW_DUPLICATE", {finding["code"] for finding in result["findings"]})

    def test_variant_pins_the_current_base_model(self) -> None:
        scope = self._scope("CHAR-ONE", "character", "compact")
        model = self._compact("CHAR-ONE", "character")
        view = self._view(model, "CHAR-ONE")
        variant = {
            "variant_id": "VAR-CHAR-ONE-WET",
            "base_asset_id": "CHAR-ONE",
            "base_model_ref": {
                "artifact": "设定集/generation/asset-models.jsonl",
                "record_id": model["model_id"],
                "record_hash": "0" * 64,
            },
            "changes": ["wet coat"],
            "preserve": ["identity"],
            "validity": {"from": "EP001"},
        }
        self._write("asset-scope.jsonl", [scope])
        self._write("asset-models.jsonl", [model])
        self._write("variant-models.jsonl", [variant])
        self._write("view-contracts.jsonl", [view])
        result = CHECKER.validate_m15a(self.directory)
        self.assertIn("M15_VARIANT_MODEL_STALE", {finding["code"] for finding in result["findings"]})

    def test_each_variant_and_view_need_one_canonical_fragment(self) -> None:
        project = self.directory / "project"
        generation = project / "设定集" / "generation"
        generation.mkdir(parents=True)
        visual_direction = {"status": "accepted", "value": "restrained realism"}
        project_data = {
            "creator_authority": {"visual_direction": visual_direction},
            "format": {"prompt_language": "en"},
        }
        (project / "short-drama.json").write_text(
            json.dumps(project_data, ensure_ascii=False),
            encoding="utf-8",
        )
        scope = self._scope("CHAR-ONE", "character", "compact")
        model = self._compact("CHAR-ONE", "character")
        model_hash = digest(model)
        view = self._view(model, "CHAR-ONE")
        view_hash = digest(view)
        variant = {
            "variant_id": "VAR-CHAR-ONE-WET",
            "base_asset_id": "CHAR-ONE",
            "base_model_ref": {
                "artifact": "设定集/generation/asset-models.jsonl",
                "record_id": model["model_id"],
                "record_hash": model_hash,
            },
            "changes": ["wet coat"],
            "preserve": ["identity"],
            "validity": {"from": "EP001"},
        }
        variant_hash = digest(variant)

        def write(name: str, records: list[dict]) -> None:
            (generation / name).write_text(
                "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
                encoding="utf-8",
            )

        write("asset-scope.jsonl", [scope])
        write("asset-models.jsonl", [model])
        write("spatial-models.jsonl", [])
        write("variant-models.jsonl", [variant])
        write("view-contracts.jsonl", [view])
        (generation / "canonical-prompt-library.md").write_text("# fragments\n", encoding="utf-8")

        def fragment(
            fragment_id: str,
            kind: str,
            refs: list[tuple[str, str, str]],
            *,
            scope_value: dict,
            variant_id: str | None = None,
            asset_id: str | None = "CHAR-ONE",
        ) -> dict:
            record = {
                "fragment_id": fragment_id,
                "fragment_kind": kind,
                "asset_id": asset_id,
                "language": "en",
                "scope": scope_value,
                "model_refs": [
                    {"artifact": artifact, "record_id": record_id, "record_hash": record_hash}
                    for artifact, record_id, record_hash in refs
                ],
                "input_hashes": {record_id: record_hash for _, record_id, record_hash in refs},
                "text": fragment_id,
            }
            if variant_id is not None:
                record["variant_id"] = variant_id
            record["fragment_hash"] = CHECKER.record_hash(record, hash_field="fragment_hash")
            return record

        visual_hash = digest(visual_direction)
        language_hash = digest("en")
        style = fragment(
            "FRAG-STYLE",
            "style_core",
            [],
            scope_value={"project": "all_visual_generation"},
            asset_id=None,
        )
        style["model_refs"] = [
            {
                "artifact": "short-drama.json",
                "field": "/creator_authority/visual_direction",
                "record_hash": visual_hash,
            },
            {
                "artifact": "short-drama.json",
                "field": "/format/prompt_language",
                "record_hash": language_hash,
            },
        ]
        style["input_hashes"] = {
            "/creator_authority/visual_direction": visual_hash,
            "/format/prompt_language": language_hash,
        }
        style["fragment_hash"] = CHECKER.record_hash(style, hash_field="fragment_hash")
        model_ref = [("设定集/generation/asset-models.jsonl", model["model_id"], model_hash)]
        view_ref = [("设定集/generation/view-contracts.jsonl", view["view_id"], view_hash)]
        variant_refs = [
            ("设定集/generation/variant-models.jsonl", variant["variant_id"], variant_hash),
            ("设定集/generation/asset-models.jsonl", model["model_id"], model_hash),
        ]
        fragments = [
            style,
            fragment("FRAG-ID", "identity_full", model_ref, scope_value={"jobs": sorted(CHECKER.PROMPT_PROFILES)}),
            fragment("FRAG-CONT", "continuity_lock", model_ref, scope_value={"jobs": sorted(CHECKER.PROMPT_PROFILES)}),
            fragment("FRAG-VIEW-A", "view_projection", view_ref, scope_value={"view_id": view["view_id"]}),
            fragment("FRAG-VIEW-B", "view_projection", view_ref, scope_value={"view_id": view["view_id"]}),
            fragment("FRAG-VAR-A", "variant_delta", variant_refs, scope_value={"jobs": sorted(CHECKER.PROMPT_PROFILES)}, variant_id=variant["variant_id"]),
            fragment("FRAG-VAR-B", "variant_delta", variant_refs, scope_value={"jobs": sorted(CHECKER.PROMPT_PROFILES)}, variant_id=variant["variant_id"]),
            fragment("FRAG-NEG", "negative_lock", model_ref, scope_value={"jobs": sorted(CHECKER.PROMPT_PROFILES)}),
        ]
        write("canonical-fragments.jsonl", fragments)
        result = CHECKER.validate_fragments(generation, prompt_language="en")
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("M15_FRAGMENT_VARIANT", codes)
        self.assertIn("M15_FRAGMENT_VIEW", codes)


if __name__ == "__main__":
    unittest.main()
