"""Fast lifecycle smoke test: the whole EP loop with zero manual hashes.

Drives the real `project_tool.py` CLI in a throwaway project and asserts the
shortest pass through the pipeline works without any hand-computed SHA256:

    init → publish → decide → accept-batch → review (no --evidence-hash,
    no --verdict-hash, no target hashes)

plus the `review-batch --episode` scoping. This is the path a creator actually
runs, so it must stay green with zero model-side hashing.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TOOL = (
    REPO_ROOT / "skills" / "short-drama" / "scripts" / "project_tool.py"
)
SCREENPLAY_INDEX = (
    REPO_ROOT / "skills" / "short-drama-write" / "scripts" / "screenplay_index.py"
)
PROMPT_COMPILER_PATH = (
    REPO_ROOT / "skills" / "short-drama-image-prompts" / "scripts" / "prompt_compile.py"
)


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(PROJECT_TOOL), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def load_state(root: Path) -> dict:
    return json.loads(
        (root / ".short-drama" / "state.json").read_text(encoding="utf-8")
    )


def load_project(root: Path) -> dict:
    return json.loads((root / "short-drama.json").read_text(encoding="utf-8"))


class LifecycleSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name) / "proj"
        init = run_tool("init", str(self.root), "--title", "冒烟测试")
        self.assertEqual(init.returncode, 0, init.stderr)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _publish_candidate(self, *, generation_bindings: bool = False) -> subprocess.CompletedProcess[str]:
        (self.root / "输入").mkdir(exist_ok=True)
        candidate = self.root / "输入" / "s.md"
        candidate.write_text(
            "## EP001-SC001 内 · 客厅 · 夜\n\n葛晴（打量游森）：你回来了。\n",
            encoding="utf-8",
        )
        index = self.root / "输入" / "screenplay-index.jsonl"
        indexed = subprocess.run(
            [
                sys.executable,
                str(SCREENPLAY_INDEX),
                str(candidate),
                "--output",
                str(index),
                "--source-ref",
                "剧集/EP001/screenplay.md",
                "--authority",
                "candidate",
                "--speaker",
                "葛晴",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(indexed.returncode, 0, indexed.stderr)
        args = [
            "publish", str(self.root), "--owner", "short-drama-write",
            "--artifact-id", "EP001:script",
            "--output", "剧集/EP001/screenplay.md=输入/s.md",
            "--output", "剧集/EP001/screenplay-index.jsonl=输入/screenplay-index.jsonl",
        ]
        if generation_bindings:
            bindings = {
                "asset-scope.jsonl": "CHAR-TEST",
                "asset-models.jsonl": "MODEL-CHAR-TEST-V1",
                "view-contracts.jsonl": "GVIEW-CHAR-TEST-FRONT-V1",
                "canonical-fragments.jsonl": "FRAG-ID",
            }
            for name, selector in bindings.items():
                relative = f"设定集/generation/{name}"
                digest = hashlib.sha256((self.root / relative).read_bytes()).hexdigest()
                args.extend(["--input", f"{relative}={digest}", "--input-record", f"{relative}={selector}"])
        published = run_tool(*args)
        self.assertEqual(published.returncode, 0, published.stderr)
        return published

    def _install_generation_baseline(self, root: Path | None = None) -> None:
        root = root or self.root
        source = root / "输入" / "baseline"
        source.mkdir(parents=True, exist_ok=True)
        generation = "设定集/generation"
        scope = {
            "record_type": "asset_scope",
            "asset_id": "CHAR-TEST",
            "asset_kind": "character",
            "tier": "compact",
            "classification_reasons": ["主要测试人物"],
            "reuse_scope": {"episodes": "series", "jobs": ["keyframe"]},
            "creator_acceptance": {"status": "accepted"},
        }
        model = {
            "record_type": "asset_model",
            "model_id": "MODEL-CHAR-TEST-V1",
            "asset_id": "CHAR-TEST",
            "asset_kind": "character",
            "tier": "compact",
            "scale": "168cm",
            "silhouette": "short hair and narrow shoulders",
            "materials": ["cotton"],
            "intrinsic_colors": ["black hair"],
            "recognition_anchors": ["narrow face", "left brow notch"],
            "state_boundary": "clothing and injury are variants",
            "forbidden_drift": ["move brow notch", "change height"],
            "standard_view": "front orthographic",
        }
        model_record_hash = hashlib.sha256(
            json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        view = {
            "record_type": "view_contract",
            "view_id": "GVIEW-CHAR-TEST-FRONT-V1",
            "asset_id": "CHAR-TEST",
            "model_ref": {
                "owner": "short-drama-assets",
                "artifact": f"{generation}/asset-models.jsonl",
                "record_id": "MODEL-CHAR-TEST-V1",
                "record_hash": model_record_hash,
            },
            "orientation": "front orthographic",
            "must_show": ["head to feet", "left brow notch"],
            "must_preserve": ["body ratio", "hair silhouette"],
            "must_not_change": ["no perspective", "no props"],
        }
        view_record_hash = hashlib.sha256(
            json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        files = {
            "asset-scope.jsonl": json.dumps(scope, ensure_ascii=False) + "\n",
            "asset-models.jsonl": json.dumps(model, ensure_ascii=False) + "\n",
            "spatial-models.jsonl": "",
            "variant-models.jsonl": "",
            "view-contracts.jsonl": json.dumps(view, ensure_ascii=False) + "\n",
            "asset-baseline.md": "# 测试资产基线\n",
        }
        for name, content in files.items():
            (source / name).write_text(content, encoding="utf-8")
        args = [
            "publish", str(root), "--owner", "short-drama-assets",
            "--artifact-id", "project:asset-baseline",
        ]
        for name in files:
            args.extend(["--output", f"{generation}/{name}=输入/baseline/{name}"])
        published_fragments = run_tool(*args)
        self.assertEqual(
            published_fragments.returncode, 0, published_fragments.stderr
        )
        self.assertEqual(run_tool("decide", str(root), "--artifact-id", "project:asset-baseline", "--decision", "accepted").returncode, 0)
        self.assertEqual(run_tool("accept-batch", str(root)).returncode, 0)

        def fragment(
            fragment_id: str,
            kind: str,
            text: str,
            asset_id: str | None,
            *,
            model_refs: list[dict],
            input_hashes: dict,
            scope: dict | None = None,
        ) -> dict:
            value = {
                "record_type": "canonical_fragment",
                "fragment_id": fragment_id,
                "fragment_kind": kind,
                "asset_id": asset_id,
                "language": "en",
                "scope": scope or {"jobs": ["asset_board", "keyframe", "motion"]},
                "model_refs": model_refs,
                "input_hashes": input_hashes,
                "text": text,
            }
            material = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            value["fragment_hash"] = hashlib.sha256(material).hexdigest()
            return value

        project = load_project(root)
        visual_hash = hashlib.sha256(json.dumps(project["creator_authority"]["visual_direction"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        language_hash = hashlib.sha256(json.dumps(project["format"]["prompt_language"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        project_refs = [
            {"owner": "creator", "artifact": "short-drama.json", "field": "/creator_authority/visual_direction", "record_hash": visual_hash},
            {"owner": "creator", "artifact": "short-drama.json", "field": "/format/prompt_language", "record_hash": language_hash},
        ]
        model_ref = {"owner": "short-drama-assets", "artifact": f"{generation}/asset-models.jsonl", "record_id": "MODEL-CHAR-TEST-V1", "record_hash": model_record_hash}
        view_ref = {"owner": "short-drama-assets", "artifact": f"{generation}/view-contracts.jsonl", "record_id": "GVIEW-CHAR-TEST-FRONT-V1", "record_hash": view_record_hash}
        fragments = [
            fragment("FRAG-STYLE", "style_core", "accepted project style", None, model_refs=project_refs, input_hashes={"/creator_authority/visual_direction": visual_hash, "/format/prompt_language": language_hash}, scope={"project": "all_visual_generation"}),
            fragment("FRAG-ID", "identity_full", "stable identity", "CHAR-TEST", model_refs=[model_ref], input_hashes={"MODEL-CHAR-TEST-V1": model_record_hash}),
            fragment("FRAG-CONT", "continuity_lock", "keep identity", "CHAR-TEST", model_refs=[model_ref], input_hashes={"MODEL-CHAR-TEST-V1": model_record_hash}),
            fragment("FRAG-VIEW", "view_projection", "front view", "CHAR-TEST", model_refs=[view_ref], input_hashes={"GVIEW-CHAR-TEST-FRONT-V1": view_record_hash}, scope={"view_id": "GVIEW-CHAR-TEST-FRONT-V1"}),
            fragment("FRAG-NEG", "negative_lock", "do not drift", "CHAR-TEST", model_refs=[model_ref], input_hashes={"MODEL-CHAR-TEST-V1": model_record_hash}),
        ]
        fragment_text = "\n".join(json.dumps(item, ensure_ascii=False) for item in fragments) + "\n"
        fragment_path = source / "canonical-fragments.jsonl"
        fragment_path.write_text(fragment_text, encoding="utf-8")
        fragment_digest = hashlib.sha256(fragment_path.read_bytes()).hexdigest()
        library_lines = ["# 测试标准片段", f"> 来源：`{fragment_digest}`"]
        for item in fragments:
            library_lines.extend(
                [
                    f"## {item['fragment_id']}",
                    f"- fragment_hash: `{item['fragment_hash']}`",
                    item["text"],
                ]
            )
        (source / "canonical-prompt-library.md").write_text(
            "\n\n".join(library_lines) + "\n", encoding="utf-8"
        )
        args = [
            "publish", str(root), "--owner", "short-drama-image-prompts",
            "--artifact-id", "project:canonical-fragments",
            "--output", f"{generation}/canonical-fragments.jsonl=输入/baseline/canonical-fragments.jsonl",
            "--output", f"{generation}/canonical-prompt-library.md=输入/baseline/canonical-prompt-library.md",
            "--input", f"short-drama.json={hashlib.sha256((root / 'short-drama.json').read_bytes()).hexdigest()}",
            "--input-record", "short-drama.json=/creator_authority/visual_direction",
            "--input-record", "short-drama.json=/format/prompt_language",
            "--input", f"{generation}/asset-scope.jsonl={hashlib.sha256((root / generation / 'asset-scope.jsonl').read_bytes()).hexdigest()}",
            "--input-record", f"{generation}/asset-scope.jsonl=CHAR-TEST",
            "--input", f"{generation}/asset-models.jsonl={hashlib.sha256((root / generation / 'asset-models.jsonl').read_bytes()).hexdigest()}",
            "--input-record", f"{generation}/asset-models.jsonl=MODEL-CHAR-TEST-V1",
            "--input", f"{generation}/view-contracts.jsonl={hashlib.sha256((root / generation / 'view-contracts.jsonl').read_bytes()).hexdigest()}",
            "--input-record", f"{generation}/view-contracts.jsonl=GVIEW-CHAR-TEST-FRONT-V1",
        ]
        published_fragments = run_tool(*args)
        self.assertEqual(
            published_fragments.returncode, 0, published_fragments.stderr
        )
        self.assertEqual(run_tool("decide", str(root), "--artifact-id", "project:canonical-fragments", "--decision", "accepted").returncode, 0)
        self.assertEqual(run_tool("accept-batch", str(root)).returncode, 0)

    def _review_bundle_ref(self, record: dict) -> dict:
        args = ["review-bundle", str(self.root)]
        for path, digest in record["accepted_targets"].items():
            args.extend(["--target", f"{path}={digest}"])
        built = run_tool(*args)
        self.assertEqual(built.returncode, 0, built.stderr)
        result = json.loads(built.stdout)
        bundle_path = result["bundle_path"]
        self.assertEqual(
            result["bundle_hash"],
            hashlib.sha256((self.root / bundle_path).read_bytes()).hexdigest(),
        )
        return {
            "owner": "short-drama-review",
            "artifact": bundle_path,
            "hash": result["bundle_hash"],
        }

    def _approve_artifact(self, artifact_id: str = "EP001:script") -> dict:
        record = load_state(self.root)["artifacts"][artifact_id]
        findings = self.root / "审查" / f"{artifact_id.replace(':', '-')}-findings.jsonl"
        findings.write_bytes(b"")
        verdict = {
            "review_id": f"REV-{artifact_id}",
            "artifact_id": artifact_id,
            "reviewed_artifacts": [
                {"owner": record["owner"], "artifact": path, "hash": digest}
                for path, digest in record["accepted_targets"].items()
            ],
            "findings_ref": {
                "owner": "short-drama-review",
                "artifact": findings.relative_to(self.root).as_posix(),
                "hash": hashlib.sha256(findings.read_bytes()).hexdigest(),
            },
            "review_bundle_ref": self._review_bundle_ref(record),
            "requested_review_mode": "independent_agent",
            "effective_review_mode": "fresh_agent",
            "delta_basis": None,
            "reviewer": {
                "owner": "short-drama-review",
                "kind": "independent_agent",
                "independent": True,
                "excluded_owner_skills": [record["owner"]],
                "provenance": {
                    "context_id": "TEST-FRESH",
                    "fresh_context": True,
                    "authored_reviewed_artifacts": False,
                },
            },
            "structural_validation": "pass",
            "verdict": "approve",
            "blocking_findings": [],
            "open_blocker_count": 0,
            "required_reviewer_independence": True,
        }
        verdict_path = self.root / "审查" / f"{artifact_id.replace(':', '-')}-verdict.json"
        verdict_path.write_text(json.dumps(verdict, ensure_ascii=False), encoding="utf-8")
        reviewed = run_tool(
            "review", str(self.root), "--artifact-id", artifact_id,
            "--verdict", "approve", "--verdict-owner", "short-drama-review",
            "--verdict-artifact", verdict_path.relative_to(self.root).as_posix(),
        )
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        return load_state(self.root)["artifacts"][artifact_id]

    def test_accept_without_evidence_hash(self) -> None:
        self._publish_candidate()
        decided = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(decided.returncode, 0, decided.stderr)
        # No --evidence-hash: the tool hashes the decision file itself.
        accepted = run_tool("accept-batch", str(self.root))
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        state = load_state(self.root)
        record = state["artifacts"]["EP001:script"]
        self.assertEqual(record["creator_acceptance"], "accepted")

    def test_creator_authority_rejects_skill_and_accepts_scoped_delegate(self) -> None:
        self._publish_candidate()
        refused = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
            "--decided-by",
            "short-drama-write",
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("delegation-artifact", refused.stderr)

        delegation = self.root / "创作者决策" / "delegation.json"
        delegation.write_text(
            json.dumps(
                {
                    "decision_id": "CD-DELEGATION-001",
                    "decision_kind": "delegation",
                    "status": "accepted",
                    "delegate": "producer:LI-001",
                    "scope": {
                        "operations": ["artifact_acceptance"],
                        "artifacts": ["EP001:script"],
                    },
                    "decided_by": "creator",
                }
            ),
            encoding="utf-8",
        )
        decided = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
            "--decided-by",
            "producer:LI-001",
            "--delegation-artifact",
            "创作者决策/delegation.json",
        )
        self.assertEqual(decided.returncode, 0, decided.stderr)
        accepted = run_tool("accept-batch", str(self.root))
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        authority = load_state(self.root)["artifacts"]["EP001:script"][
            "creator_decision"
        ]["authority"]
        self.assertEqual(authority["mode"], "delegated")

    def test_pipeline_requires_every_m2_file_and_uses_live_staleness(self) -> None:
        project = load_project(self.root)
        for key in ("visual_direction", "production_profile"):
            project["creator_authority"][key] = {"status": "accepted"}
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._install_generation_baseline()
        self._publish_candidate()
        run_tool(
            "decide", str(self.root), "--artifact-id", "EP001:script",
            "--decision", "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        partial = json.loads(run_tool("pipeline", str(self.root)).stdout)
        self.assertEqual(partial["current_milestone"], "M2")

        # A second project with all four required M2 files advances to M3,
        # then an external edit immediately sends the effective flow back.
        other = Path(self._tempdir.name) / "full"
        self.assertEqual(run_tool("init", str(other), "--title", "完整 M2").returncode, 0)
        other_project = load_project(other)
        for key in ("visual_direction", "production_profile"):
            other_project["creator_authority"][key] = {"status": "accepted"}
        (other / "short-drama.json").write_text(
            json.dumps(other_project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._install_generation_baseline(other)
        (other / "输入").mkdir(exist_ok=True)
        for name, content in (
            ("episode-card.json", json.dumps({"generation_asset_bindings": [{
                "asset_id": "CHAR-TEST", "model_id": "MODEL-CHAR-TEST-V1",
                "view_ids": ["GVIEW-CHAR-TEST-FRONT-V1"], "variant_ids": [],
                "fragment_ids": ["FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG"],
            }]}, ensure_ascii=False) + "\n"),
            ("beats.jsonl", "{}\n"),
            ("screenplay.md", "## EP001-SC001 内 · 客厅 · 夜\n\n葛晴：回来。\n"),
        ):
            (other / "输入" / name).write_text(content, encoding="utf-8")
        indexed = subprocess.run(
            [sys.executable, str(SCREENPLAY_INDEX), str(other / "输入/screenplay.md"),
             "--output", str(other / "输入/screenplay-index.jsonl"), "--source-ref",
             "剧集/EP001/screenplay.md", "--authority", "candidate", "--speaker", "葛晴"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(indexed.returncode, 0, indexed.stderr)
        generation_inputs = {
            "asset-scope.jsonl": "CHAR-TEST",
            "asset-models.jsonl": "MODEL-CHAR-TEST-V1",
            "view-contracts.jsonl": "GVIEW-CHAR-TEST-FRONT-V1",
            "canonical-fragments.jsonl": ["FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG"],
        }
        args = ["publish", str(other), "--owner", "short-drama-write", "--artifact-id", "EP001:full"]
        for name in ("episode-card.json", "beats.jsonl", "screenplay.md", "screenplay-index.jsonl"):
            args.extend(["--output", f"剧集/EP001/{name}=输入/{name}"])
        for name, selectors in generation_inputs.items():
            baseline = other / "设定集" / "generation" / name
            args.extend(["--input", f"设定集/generation/{name}={hashlib.sha256(baseline.read_bytes()).hexdigest()}"])
            for selector in selectors if isinstance(selectors, list) else [selectors]:
                args.extend(["--input-record", f"设定集/generation/{name}={selector}"])
        self.assertEqual(run_tool(*args).returncode, 0)
        self.assertEqual(run_tool("decide", str(other), "--artifact-id", "EP001:full", "--decision", "accepted").returncode, 0)
        self.assertEqual(run_tool("accept-batch", str(other)).returncode, 0)
        self.assertEqual(json.loads(run_tool("pipeline", str(other)).stdout)["current_milestone"], "M3")

        def republish_asset_baseline() -> None:
            revision = other / "输入/baseline-revision"
            revision.mkdir(parents=True, exist_ok=True)
            names = (
                "asset-scope.jsonl", "asset-models.jsonl", "spatial-models.jsonl",
                "variant-models.jsonl", "view-contracts.jsonl", "asset-baseline.md",
            )
            args = ["publish", str(other), "--owner", "short-drama-assets", "--artifact-id", "project:asset-baseline"]
            for name in names:
                (revision / name).write_bytes((other / "设定集/generation" / name).read_bytes())
                args.extend(["--output", f"设定集/generation/{name}=输入/baseline-revision/{name}"])
            republished = run_tool(*args)
            self.assertEqual(republished.returncode, 0, republished.stderr)
            self.assertEqual(run_tool("decide", str(other), "--artifact-id", "project:asset-baseline", "--decision", "accepted", "--force").returncode, 0)
            self.assertEqual(run_tool("accept-batch", str(other)).returncode, 0)

        def republish_fragments() -> None:
            revision = other / "输入/fragment-revision"
            revision.mkdir(parents=True, exist_ok=True)
            fragment_revision = revision / "canonical-fragments.jsonl"
            fragment_revision.write_bytes(
                (other / "设定集/generation/canonical-fragments.jsonl").read_bytes()
            )
            fragment_records = [
                json.loads(line)
                for line in fragment_revision.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            library_lines = [
                "# 测试标准片段",
                f"> 来源：`{hashlib.sha256(fragment_revision.read_bytes()).hexdigest()}`",
            ]
            for item in fragment_records:
                library_lines.extend(
                    [
                        f"## {item['fragment_id']}",
                        f"- fragment_hash: `{item['fragment_hash']}`",
                        item["text"],
                    ]
                )
            (revision / "canonical-prompt-library.md").write_text(
                "\n\n".join(library_lines) + "\n", encoding="utf-8"
            )
            args = [
                "publish", str(other), "--owner", "short-drama-image-prompts",
                "--artifact-id", "project:canonical-fragments",
                "--output", "设定集/generation/canonical-fragments.jsonl=输入/fragment-revision/canonical-fragments.jsonl",
                "--output", "设定集/generation/canonical-prompt-library.md=输入/fragment-revision/canonical-prompt-library.md",
                "--input", f"short-drama.json={hashlib.sha256((other / 'short-drama.json').read_bytes()).hexdigest()}",
                "--input-record", "short-drama.json=/creator_authority/visual_direction",
                "--input-record", "short-drama.json=/format/prompt_language",
            ]
            for name, selector in (
                ("asset-scope.jsonl", "CHAR-TEST"),
                ("asset-models.jsonl", "MODEL-CHAR-TEST-V1"),
                ("view-contracts.jsonl", "GVIEW-CHAR-TEST-FRONT-V1"),
            ):
                path = other / "设定集/generation" / name
                args.extend(["--input", f"设定集/generation/{name}={hashlib.sha256(path.read_bytes()).hexdigest()}"])
                args.extend(["--input-record", f"设定集/generation/{name}={selector}"])
            republished_fragments = run_tool(*args)
            self.assertEqual(
                republished_fragments.returncode, 0, republished_fragments.stderr
            )
            self.assertEqual(run_tool("decide", str(other), "--artifact-id", "project:canonical-fragments", "--decision", "accepted", "--force").returncode, 0)
            self.assertEqual(run_tool("accept-batch", str(other)).returncode, 0)

        scope_path = other / "设定集/generation/asset-scope.jsonl"
        unused_scope = {
            "asset_id": "PROP-UNUSED", "asset_kind": "prop", "tier": "compact",
            "classification_reasons": ["background reusable prop"],
            "reuse_scope": {"episodes": ["EP999"], "jobs": ["asset_board"]},
            "creator_acceptance": {"status": "accepted"},
        }
        scope_path.write_text(
            scope_path.read_text(encoding="utf-8") + json.dumps(unused_scope) + "\n",
            encoding="utf-8",
        )
        model_path = other / "设定集/generation/asset-models.jsonl"
        unused_model = {
            "model_id": "MODEL-PROP-UNUSED-V1", "asset_id": "PROP-UNUSED",
            "asset_kind": "prop", "tier": "compact", "scale": "20 cm",
            "silhouette": "flat rectangle", "materials": ["steel"],
            "intrinsic_colors": ["grey"], "recognition_anchors": ["left notch", "two hinges"],
            "state_boundary": "open state may vary", "forbidden_drift": ["no handle"],
            "standard_view": "front three-quarter",
        }
        model_path.write_text(
            model_path.read_text(encoding="utf-8") + json.dumps(unused_model) + "\n",
            encoding="utf-8",
        )
        unused_model_hash = hashlib.sha256(json.dumps(unused_model, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        view_path = other / "设定集/generation/view-contracts.jsonl"
        unused_view = {
            "view_id": "GVIEW-PROP-UNUSED-FRONT-V1", "asset_id": "PROP-UNUSED",
            "model_ref": {"owner": "short-drama-assets", "artifact": "设定集/generation/asset-models.jsonl", "record_id": "MODEL-PROP-UNUSED-V1", "record_hash": unused_model_hash},
            "orientation": "front", "must_show": ["left notch", "two hinges"],
            "must_preserve": ["flat rectangle"], "must_not_change": ["no handle"],
        }
        view_path.write_text(
            view_path.read_text(encoding="utf-8") + json.dumps(unused_view) + "\n",
            encoding="utf-8",
        )
        republish_asset_baseline()
        fragments_path = other / "设定集/generation/canonical-fragments.jsonl"
        fragments = [json.loads(line) for line in fragments_path.read_text(encoding="utf-8").splitlines()]
        unused_view_hash = hashlib.sha256(json.dumps(unused_view, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        for fragment_id, kind, model_ref, scope in (
            ("FRAG-UNUSED-ID", "identity_full", {"owner": "short-drama-assets", "artifact": "设定集/generation/asset-models.jsonl", "record_id": "MODEL-PROP-UNUSED-V1", "record_hash": unused_model_hash}, {"jobs": ["asset_board", "keyframe", "motion"]}),
            ("FRAG-UNUSED-CONT", "continuity_lock", {"owner": "short-drama-assets", "artifact": "设定集/generation/asset-models.jsonl", "record_id": "MODEL-PROP-UNUSED-V1", "record_hash": unused_model_hash}, {"jobs": ["asset_board", "keyframe", "motion"]}),
            ("FRAG-UNUSED-VIEW", "view_projection", {"owner": "short-drama-assets", "artifact": "设定集/generation/view-contracts.jsonl", "record_id": "GVIEW-PROP-UNUSED-FRONT-V1", "record_hash": unused_view_hash}, {"view_id": "GVIEW-PROP-UNUSED-FRONT-V1"}),
            ("FRAG-UNUSED-NEG", "negative_lock", {"owner": "short-drama-assets", "artifact": "设定集/generation/asset-models.jsonl", "record_id": "MODEL-PROP-UNUSED-V1", "record_hash": unused_model_hash}, {"jobs": ["asset_board", "keyframe", "motion"]}),
        ):
            record_id = model_ref["record_id"]
            value = {
                "fragment_id": fragment_id, "fragment_kind": kind, "asset_id": "PROP-UNUSED",
                "language": "en", "scope": scope, "model_refs": [model_ref],
                "input_hashes": {record_id: model_ref["record_hash"]}, "text": fragment_id,
            }
            value["fragment_hash"] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            fragments.append(value)
        fragments_path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in fragments), encoding="utf-8")
        republish_fragments()
        self.assertEqual(json.loads(run_tool("pipeline", str(other)).stdout)["current_milestone"], "M3")
        records = [json.loads(line) for line in model_path.read_text(encoding="utf-8").splitlines()]
        records[0]["silhouette"] = "changed consumed record"
        model_path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
        model_hash = hashlib.sha256(json.dumps(records[0], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        views = [json.loads(line) for line in view_path.read_text(encoding="utf-8").splitlines()]
        views[0]["model_ref"]["record_hash"] = model_hash
        view_path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in views), encoding="utf-8")
        republish_asset_baseline()
        fragments = [json.loads(line) for line in fragments_path.read_text(encoding="utf-8").splitlines()]
        view_hash = hashlib.sha256(json.dumps(views[0], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        for fragment in fragments:
            if "MODEL-CHAR-TEST-V1" in fragment.get("input_hashes", {}):
                fragment["input_hashes"]["MODEL-CHAR-TEST-V1"] = model_hash
                for reference in fragment.get("model_refs", []):
                    if reference.get("record_id") == "MODEL-CHAR-TEST-V1":
                        reference["record_hash"] = model_hash
            if "GVIEW-CHAR-TEST-FRONT-V1" in fragment.get("input_hashes", {}):
                fragment["input_hashes"]["GVIEW-CHAR-TEST-FRONT-V1"] = view_hash
                for reference in fragment.get("model_refs", []):
                    if reference.get("record_id") == "GVIEW-CHAR-TEST-FRONT-V1":
                        reference["record_hash"] = view_hash
            material = {key: value for key, value in fragment.items() if key != "fragment_hash"}
            fragment["fragment_hash"] = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        fragments_path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in fragments), encoding="utf-8")
        republish_fragments()
        self.assertEqual(json.loads(run_tool("pipeline", str(other)).stdout)["current_milestone"], "M2")
        # Restore M2, then prove direct target drift also returns to M2.
        snapshot_relative = load_state(other)["artifacts"]["project:asset-baseline"]["accepted_snapshots"]["设定集/generation/asset-models.jsonl"]
        model_path.write_text((other / snapshot_relative).read_text(encoding="utf-8"), encoding="utf-8")
        (other / "剧集/EP001/screenplay.md").write_text("外部修改\n", encoding="utf-8")
        self.assertEqual(json.loads(run_tool("pipeline", str(other)).stdout)["current_milestone"], "M2")

    def test_script_first_stops_at_m15_and_legacy_requires_upgrade(self) -> None:
        project = load_project(self.root)
        for key in ("visual_direction", "production_profile"):
            project["creator_authority"][key] = {"status": "accepted"}
        (self.root / "short-drama.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        before = json.loads(run_tool("pipeline", str(self.root)).stdout)
        self.assertEqual(before["current_milestone"], "M1.5a")
        self._install_generation_baseline()
        project = load_project(self.root)
        project["production_flow"]["pipeline_version"] = "1.0.0"
        (self.root / "short-drama.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        legacy = json.loads(run_tool("pipeline", str(self.root)).stdout)
        self.assertEqual(legacy["current_milestone"], "M1.5b")
        self.assertEqual(legacy["blockers"][0]["code"], "BLK-FLOW-UPGRADE")
        upgraded = run_tool("upgrade-flow", str(self.root))
        self.assertEqual(upgraded.returncode, 0, upgraded.stderr)
        self.assertEqual(load_project(self.root)["production_flow"]["pipeline_version"], "2.0.1")

    def test_prompt_publication_rejects_free_rewrite(self) -> None:
        self._install_generation_baseline()
        fragments_path = self.root / "设定集/generation/canonical-fragments.jsonl"
        fragments = {
            item["fragment_id"]: item
            for item in (json.loads(line) for line in fragments_path.read_text(encoding="utf-8").splitlines())
        }
        refs = [fragments[key] for key in ("FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG")]
        record = {
            "spec_id": "IMG-TEST",
            "asset_bindings": [{"asset_id": "CHAR-TEST", "model_id": "MODEL-CHAR-TEST-V1", "view_id": "GVIEW-CHAR-TEST-FRONT-V1"}],
            "task_and_format": "Generate a character board.",
            "prompt_components": {
                "profile": "asset_board",
                "fragment_refs": [{"fragment_id": item["fragment_id"], "hash": item["fragment_hash"]} for item in refs],
                "local_instructions": ["front full-body view"],
                "local_negative_constraints": [],
            },
        }
        spec = importlib.util.spec_from_file_location("prompt_compile_lifecycle", PROMPT_COMPILER_PATH)
        assert spec is not None and spec.loader is not None
        compiler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compiler)
        compiled = compiler.compile_record(record, fragments)
        compiled["generic_prompt"] += "\nfree rewrite"
        source = self.root / "输入/image-prompt-specs.jsonl"
        source.write_text(json.dumps(compiled, ensure_ascii=False) + "\n", encoding="utf-8")
        published = run_tool(
            "publish", str(self.root), "--owner", "short-drama-image-prompts",
            "--artifact-id", "EP001:image-prompts",
            "--output", "剧集/EP001/assets/image-prompt-specs.jsonl=输入/image-prompt-specs.jsonl",
        )
        self.assertNotEqual(published.returncode, 0)
        self.assertIn("BLK-PROMPT-COMPILE", published.stderr)

    def test_prompt_publication_auto_binds_fragment_records(self) -> None:
        self._install_generation_baseline()
        project = load_project(self.root)
        for key in ("visual_direction", "production_profile"):
            project["creator_authority"][key] = {"status": "accepted"}
        (self.root / "short-drama.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        fragments_path = self.root / "设定集/generation/canonical-fragments.jsonl"
        fragments = {
            item["fragment_id"]: item
            for item in (json.loads(line) for line in fragments_path.read_text(encoding="utf-8").splitlines())
        }
        keys = ("FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG")
        record = {
            "spec_id": "IMG-BOUND", "asset_bindings": [{
                "asset_id": "CHAR-TEST", "model_id": "MODEL-CHAR-TEST-V1",
                "view_id": "GVIEW-CHAR-TEST-FRONT-V1",
            }],
            "task_and_format": "Generate a character board.",
            "prompt_components": {
                "profile": "asset_board",
                "fragment_refs": [{"fragment_id": key, "hash": fragments[key]["fragment_hash"]} for key in keys],
                "local_instructions": ["front full-body view"], "local_negative_constraints": [],
            },
        }
        spec = importlib.util.spec_from_file_location("prompt_compile_bound", PROMPT_COMPILER_PATH)
        assert spec is not None and spec.loader is not None
        compiler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compiler)
        source = self.root / "输入/image-prompt-specs.jsonl"
        source.write_text(json.dumps(compiler.compile_record(record, fragments), ensure_ascii=False) + "\n", encoding="utf-8")
        digest = hashlib.sha256(fragments_path.read_bytes()).hexdigest()
        published = run_tool(
            "publish", str(self.root), "--owner", "short-drama-image-prompts",
            "--artifact-id", "EP001:image-prompts",
            "--output", "剧集/EP001/assets/image-prompt-specs.jsonl=输入/image-prompt-specs.jsonl",
            "--input", f"设定集/generation/canonical-fragments.jsonl={digest}",
        )
        self.assertEqual(published.returncode, 0, published.stderr)
        bound = load_state(self.root)["artifacts"]["EP001:image-prompts"]["candidate_input_records"]
        self.assertEqual(sorted(bound["设定集/generation/canonical-fragments.jsonl"]), sorted(keys))

    def test_shot_publication_auto_binds_fragment_records(self) -> None:
        self._install_generation_baseline()
        project = load_project(self.root)
        for key in ("visual_direction", "production_profile"):
            project["creator_authority"][key] = {"status": "accepted"}
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        fragments_path = self.root / "设定集/generation/canonical-fragments.jsonl"
        fragments = {
            item["fragment_id"]: item
            for item in (
                json.loads(line)
                for line in fragments_path.read_text(encoding="utf-8").splitlines()
            )
        }
        keys = ("FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG")
        shot = {
            "shot_id": "SHOT-1",
            "generation_asset_bindings": [
                {
                    "asset_id": "CHAR-TEST",
                    "model_id": "MODEL-CHAR-TEST-V1",
                    "view_id": "GVIEW-CHAR-TEST-FRONT-V1",
                    "fragment_refs": [
                        {"fragment_id": key, "hash": fragments[key]["fragment_hash"]}
                        for key in keys
                    ],
                }
            ],
        }
        source = self.root / "输入/shots.jsonl"
        source.write_text(json.dumps(shot, ensure_ascii=False) + "\n", encoding="utf-8")
        published = run_tool(
            "publish", str(self.root), "--owner", "short-drama-storyboard",
            "--artifact-id", "EP001:shots",
            "--output", "剧集/EP001/storyboard/shots.jsonl=输入/shots.jsonl",
            "--input",
            f"设定集/generation/canonical-fragments.jsonl={hashlib.sha256(fragments_path.read_bytes()).hexdigest()}",
        )
        self.assertEqual(published.returncode, 0, published.stderr)
        bound = load_state(self.root)["artifacts"]["EP001:shots"]["candidate_input_records"]
        self.assertEqual(
            sorted(bound["设定集/generation/canonical-fragments.jsonl"]),
            sorted(keys),
        )

    def test_complete_m2_rejects_missing_asset_records(self) -> None:
        self._install_generation_baseline()
        (self.root / "输入").mkdir(exist_ok=True)
        card = {
            "generation_asset_bindings": [
                {
                    "asset_id": "CHAR-TEST",
                    "model_id": "MODEL-CHAR-TEST-V1",
                    "view_ids": ["GVIEW-CHAR-TEST-FRONT-V1"],
                    "variant_ids": [],
                    "fragment_ids": ["FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG"],
                },
                {
                    "asset_id": "CHAR-MISSING",
                    "model_id": "MODEL-CHAR-MISSING-V1",
                    "view_ids": ["GVIEW-CHAR-MISSING-FRONT-V1"],
                    "variant_ids": [],
                    "fragment_ids": ["FRAG-STYLE"],
                },
            ]
        }
        (self.root / "输入/episode-card.json").write_text(json.dumps(card), encoding="utf-8")
        (self.root / "输入/beats.jsonl").write_text("{}\n", encoding="utf-8")
        (self.root / "输入/screenplay.md").write_text("## EP001-SC001 内 · 客厅 · 夜\n\n葛晴：回来。\n", encoding="utf-8")
        indexed = subprocess.run(
            [sys.executable, str(SCREENPLAY_INDEX), str(self.root / "输入/screenplay.md"),
             "--output", str(self.root / "输入/screenplay-index.jsonl"), "--source-ref",
             "剧集/EP001/screenplay.md", "--authority", "candidate", "--speaker", "葛晴"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(indexed.returncode, 0, indexed.stderr)
        args = ["publish", str(self.root), "--owner", "short-drama-write", "--artifact-id", "EP001:m2-missing"]
        for name in ("episode-card.json", "beats.jsonl", "screenplay.md", "screenplay-index.jsonl"):
            args.extend(["--output", f"剧集/EP001/{name}=输入/{name}"])
        bindings = {
            "asset-scope.jsonl": ["CHAR-TEST"],
            "asset-models.jsonl": ["MODEL-CHAR-TEST-V1"],
            "view-contracts.jsonl": ["GVIEW-CHAR-TEST-FRONT-V1"],
            "canonical-fragments.jsonl": ["FRAG-STYLE", "FRAG-ID", "FRAG-CONT", "FRAG-VIEW", "FRAG-NEG"],
        }
        for name, selectors in bindings.items():
            relative = f"设定集/generation/{name}"
            args.extend(["--input", f"{relative}={hashlib.sha256((self.root / relative).read_bytes()).hexdigest()}"])
            for selector in selectors:
                args.extend(["--input-record", f"{relative}={selector}"])
        self.assertEqual(run_tool(*args).returncode, 0)
        self.assertEqual(run_tool("decide", str(self.root), "--artifact-id", "EP001:m2-missing", "--decision", "accepted").returncode, 0)
        accepted = run_tool("accept-batch", str(self.root))
        self.assertNotEqual(accepted.returncode, 0)
        self.assertIn("BLK-M2-ASSET-REF", accepted.stdout)

    def test_pipeline_20_rejects_m3_new_asset(self) -> None:
        self._install_generation_baseline()
        source = self.root / "输入/decisions-new-asset.jsonl"
        source.parent.mkdir(exist_ok=True)
        source.write_text(json.dumps({
            "decision_id": "DEC-NEW",
            "decision_kind": "new_asset",
            "proposed_binding": {"identity_id": "PROP-NEW"},
        }) + "\n", encoding="utf-8")
        published = run_tool(
            "publish", str(self.root), "--owner", "short-drama-assets",
            "--artifact-id", "EP001:assets",
            "--output", "剧集/EP001/assets/decisions.jsonl=输入/decisions-new-asset.jsonl",
        )
        self.assertNotEqual(published.returncode, 0)
        self.assertIn("BLK-M15-SCOPE", published.stderr)

    def test_pipeline_20_rejects_m3_new_variant(self) -> None:
        self._install_generation_baseline()
        source = self.root / "输入/decisions-new-variant.jsonl"
        source.parent.mkdir(exist_ok=True)
        source.write_text(json.dumps({
            "decision_id": "DEC-NEW-VARIANT",
            "decision_kind": "new_variant",
            "proposed_binding": {"identity_id": "CHAR-TEST", "variant_id": "VAR-NEW"},
        }) + "\n", encoding="utf-8")
        published = run_tool(
            "publish", str(self.root), "--owner", "short-drama-assets",
            "--artifact-id", "EP001:assets-variant",
            "--output", "剧集/EP001/assets/decisions.jsonl=输入/decisions-new-variant.jsonl",
        )
        self.assertNotEqual(published.returncode, 0)
        self.assertIn("BLK-M15-MODEL", published.stderr)

    def test_m15_provider_ambiguity_blocks_pipeline(self) -> None:
        self._install_generation_baseline()
        project = load_project(self.root)
        for key in ("visual_direction", "production_profile"):
            project["creator_authority"][key] = {"status": "accepted"}
        (self.root / "short-drama.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        state = load_state(self.root)
        original = state["artifacts"]["project:asset-baseline"]
        duplicate = json.loads(json.dumps(original))
        duplicate["owner"] = "short-drama-assets"
        state["artifacts"]["project:asset-baseline-duplicate"] = duplicate
        (self.root / ".short-drama/state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        report = json.loads(run_tool("pipeline", str(self.root)).stdout)
        self.assertEqual(report["current_milestone"], "M1.5a")

    def test_package_requires_delivery_surface_and_complete_fixed_pipeline(self) -> None:
        self._install_generation_baseline()
        self._publish_candidate(generation_bindings=True)
        self.assertEqual(run_tool("decide", str(self.root), "--artifact-id", "EP001:script", "--decision", "accepted").returncode, 0)
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        self._approve_artifact()
        package_args = [
            "package", str(self.root), "--episode", "EP001",
            "--include", "剧集/EP001/screenplay.md",
            "--omit", "剧集/EP001/screenplay-index.jsonl",
        ]
        blocked_surface = run_tool(*package_args)
        self.assertNotEqual(blocked_surface.returncode, 0)
        self.assertIn("delivery_surface", blocked_surface.stderr)

        project = load_project(self.root)
        project["creator_authority"]["delivery_surface"] = {
            "status": "accepted",
            "safe_zones": {"top": 0.1, "bottom": 0.2},
        }
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._approve_artifact()
        incomplete = run_tool(*package_args)
        self.assertNotEqual(incomplete.returncode, 0)
        self.assertIn("fixed pipeline is incomplete", incomplete.stderr)

    def test_review_without_verdict_hash(self) -> None:
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        state = load_state(self.root)
        record = state["artifacts"]["EP001:script"]
        targets = record["accepted_targets"]
        findings = self.root / "审查" / "f.jsonl"
        findings.write_bytes(b"")
        findings_hash = hashlib.sha256(
            findings.read_bytes()
        ).hexdigest()
        review_bundle_ref = self._review_bundle_ref(record)
        verdict = {
            "review_id": "REV-SMOKE-001",
            "artifact_id": "EP001:script",
            "reviewed_artifacts": [
                {"owner": record["owner"], "artifact": p, "hash": h}
                for p, h in targets.items()
            ],
            "findings_ref": {
                "owner": "short-drama-review",
                "artifact": "审查/f.jsonl",
                "hash": findings_hash,
            },
            "review_bundle_ref": review_bundle_ref,
            "requested_review_mode": "independent_agent",
            "effective_review_mode": "fresh_agent",
            "delta_basis": None,
            "reviewer": {
                "owner": "short-drama-review",
                "kind": "independent_agent",
                "independent": True,
                "excluded_owner_skills": [record["owner"]],
                "provenance": {
                    "context_id": "SMOKE-CTX",
                    "fresh_context": True,
                    "authored_reviewed_artifacts": False,
                },
            },
            "structural_validation": "pass",
            "verdict": "approve",
            "blocking_findings": [],
            "open_blocker_count": 0,
            "required_reviewer_independence": True,
        }
        (self.root / "审查" / "verdict.json").write_text(
            json.dumps(verdict, ensure_ascii=False), encoding="utf-8"
        )
        # No --verdict-hash and no target hash: both are resolved by the tool.
        reviewed = run_tool(
            "review",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--verdict",
            "approve",
            "--verdict-owner",
            "short-drama-review",
            "--verdict-artifact",
            "审查/verdict.json",
        )
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        state = load_state(self.root)
        self.assertEqual(
            state["artifacts"]["EP001:script"]["independent_review"], "approve"
        )

    def test_review_batch_episode_scoping(self) -> None:
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        # Verdict for EP001 plus one that belongs to a different episode.
        state = load_state(self.root)
        record = state["artifacts"]["EP001:script"]
        targets = record["accepted_targets"]
        findings = self.root / "审查" / "f.jsonl"
        findings.write_bytes(b"")
        review_bundle_ref = self._review_bundle_ref(record)

        def verdict_doc(artifact_id: str, findings_hash: str) -> dict:
            return {
                "review_id": f"REV-{artifact_id}",
                "artifact_id": artifact_id,
                "reviewed_artifacts": [
                    {"owner": record["owner"], "artifact": p, "hash": h}
                    for p, h in targets.items()
                ],
                "findings_ref": {
                    "owner": "short-drama-review",
                    "artifact": "审查/f.jsonl",
                    "hash": findings_hash,
                },
                "review_bundle_ref": review_bundle_ref,
                "requested_review_mode": "independent_agent",
                "effective_review_mode": "fresh_agent",
                "delta_basis": None,
                "reviewer": {
                    "owner": "short-drama-review",
                    "kind": "independent_agent",
                    "independent": True,
                    "excluded_owner_skills": [record["owner"]],
                    "provenance": {
                        "context_id": "SMOKE-CTX",
                        "fresh_context": True,
                        "authored_reviewed_artifacts": False,
                    },
                },
                "structural_validation": "pass",
                "verdict": "approve",
                "blocking_findings": [],
                "open_blocker_count": 0,
                "required_reviewer_independence": True,
            }

        findings_hash = hashlib.sha256(
            findings.read_bytes()
        ).hexdigest()
        (self.root / "审查" / "ep001.json").write_text(
            json.dumps(verdict_doc("EP001:script", findings_hash), ensure_ascii=False),
            encoding="utf-8",
        )
        (self.root / "审查" / "other.json").write_text(
            json.dumps(verdict_doc("EP999:script", findings_hash), ensure_ascii=False),
            encoding="utf-8",
        )
        batched = run_tool("review-batch", str(self.root), "--episode", "EP001")
        self.assertEqual(batched.returncode, 0, batched.stderr)
        summary = json.loads(batched.stdout)
        self.assertEqual(summary["applied"], 1)
        self.assertEqual(summary["skipped"], 1)
        skipped_reasons = {
            result["reason"] for result in summary["results"] if result["status"] == "skipped"
        }
        self.assertIn("verdict is not for episode EP001", skipped_reasons)

    def test_language_contract_defaults(self) -> None:
        # setUp already initialized with defaults: creator-facing zh-CN,
        # prompt bodies en, as two independent fields.
        project = load_project(self.root)
        self.assertEqual(project["language"], "zh-CN")
        self.assertEqual(project["format"]["prompt_language"], "en")
        status = json.loads(run_tool("status", str(self.root)).stdout)
        self.assertEqual(status["project_language"], "zh-CN")
        self.assertEqual(status["prompt_language"], "en")

    def test_language_contract_custom_prompt_language(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "p2"
            init = run_tool(
                "init",
                str(root),
                "--title",
                "语言测试",
                "--language",
                "zh-CN",
                "--prompt-language",
                "zh-CN",
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            project = json.loads(
                (root / "short-drama.json").read_text(encoding="utf-8")
            )
            self.assertEqual(project["language"], "zh-CN")
            self.assertEqual(project["format"]["prompt_language"], "zh-CN")

    def test_language_contract_rejects_malformed_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "p3"
            init = run_tool(
                "init",
                str(root),
                "--title",
                "畸形语言",
                "--prompt-language",
                "zh CN",  # space breaks the BCP 47 shape
            )
            self.assertNotEqual(init.returncode, 0)
            self.assertIn("not a well-formed language tag", init.stderr)
            self.assertFalse((root / "short-drama.json").exists())

    def test_language_contract_rejects_malformed_project_language(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "p4"
            init = run_tool(
                "init",
                str(root),
                "--title",
                "畸形项目语言",
                "--language",
                "en_US",  # underscore breaks the BCP 47 shape
            )
            self.assertNotEqual(init.returncode, 0)
            self.assertIn("not a well-formed language tag", init.stderr)
            self.assertFalse((root / "short-drama.json").exists())

    def test_legacy_project_prompt_language_defaults_to_en(self) -> None:
        # A project written before prompt_language existed has no such field;
        # status must report the same default init would have chosen.
        project = load_project(self.root)
        del project["format"]["prompt_language"]
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        status = json.loads(run_tool("status", str(self.root)).stdout)
        self.assertEqual(status["project_language"], "zh-CN")
        self.assertEqual(status["prompt_language"], "en")

    def test_input_record_auto_collection(self) -> None:
        # A JSONL candidate whose structured refs carry record_ids narrows its
        # declared input automatically — no hand-written --input-record.
        (self.root / "设定集").mkdir(exist_ok=True)
        characters = self.root / "设定集" / "characters.jsonl"
        characters.write_text(
            '{"record_type":"character","character_id":"CHAR-A","display_name":"甲"}\n'
            '{"record_type":"character","character_id":"CHAR-B","display_name":"乙"}\n',
            encoding="utf-8",
        )
        char_hash = hashlib.sha256(characters.read_bytes()).hexdigest()
        (self.root / "输入").mkdir(exist_ok=True)
        spec = self.root / "输入" / "spec.jsonl"
        spec.write_text(
            json.dumps(
                {
                    "owner": "short-drama-assets",
                    "artifact": "剧集/EP001/assets/occurrences.jsonl",
                    "refs": [
                        {
                            "owner": "short-drama-assets",
                            "artifact": "设定集/characters.jsonl",
                            "hash": char_hash,
                            "record_id": "CHAR-A",
                        },
                        {
                            "owner": "short-drama-assets",
                            "artifact": "设定集/characters.jsonl",
                            "hash": char_hash,
                            "record_id": "CHAR-B",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        published = run_tool(
            "publish",
            str(self.root),
            "--owner",
            "short-drama-assets",
            "--artifact-id",
            "EP001:occurrences",
            "--output",
            "剧集/EP001/assets/occurrences.jsonl=输入/spec.jsonl",
            "--input",
            f"设定集/characters.jsonl={char_hash}",
        )
        self.assertEqual(published.returncode, 0, published.stderr)
        state = load_state(self.root)
        record = state["artifacts"]["EP001:occurrences"]
        bound = record.get("candidate_input_records", {})
        self.assertIn("设定集/characters.jsonl", bound)
        self.assertEqual(
            sorted(bound["设定集/characters.jsonl"]), ["CHAR-A", "CHAR-B"]
        )

    def test_unpublish_candidate_and_protects_accepted(self) -> None:
        self._publish_candidate()
        # Candidate can be revoked.
        revoked = run_tool(
            "unpublish", str(self.root), "--artifact-id", "EP001:script"
        )
        self.assertEqual(revoked.returncode, 0, revoked.stderr)
        self.assertNotIn("EP001:script", load_state(self.root)["artifacts"])
        # Accepted artifact is protected.
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        refused = run_tool(
            "unpublish", str(self.root), "--artifact-id", "EP001:script"
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("refusing to unpublish an accepted artifact", refused.stderr)
        self.assertIn("EP001:script", load_state(self.root)["artifacts"])

    def test_review_batch_fresh_applied_after_cold_read(self) -> None:
        # cold_read file sorts before the fresh one by name; the mode ordering
        # must still land fresh last so the delivery gate stays ready.
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        state = load_state(self.root)
        record = state["artifacts"]["EP001:script"]
        targets = record["accepted_targets"]
        findings = self.root / "审查" / "f.jsonl"
        findings.write_bytes(b"")
        findings_hash = hashlib.sha256(findings.read_bytes()).hexdigest()
        review_bundle_ref = self._review_bundle_ref(record)

        def verdict_doc(mode: str) -> dict:
            return {
                "review_id": f"REV-{mode}",
                "artifact_id": "EP001:script",
                "reviewed_artifacts": [
                    {"owner": record["owner"], "artifact": p, "hash": h}
                    for p, h in targets.items()
                ],
                "findings_ref": {
                    "owner": "short-drama-review",
                    "artifact": "审查/f.jsonl",
                    "hash": findings_hash,
                },
                "review_bundle_ref": review_bundle_ref,
                "requested_review_mode": mode,
                "effective_review_mode": (
                    "fresh_agent" if mode == "independent_agent" else mode
                ),
                "delta_basis": None,
                "reviewer": (
                    {
                        "owner": "short-drama-review",
                        "kind": "cold_reader",
                        "independent": False,
                        "excluded_owner_skills": [record["owner"]],
                        "provenance": None,
                    }
                    if mode == "cold_read"
                    else {
                        "owner": "short-drama-review",
                        "kind": "independent_agent",
                        "independent": True,
                        "excluded_owner_skills": [record["owner"]],
                        "provenance": {
                            "context_id": "FRESH-SORT",
                            "fresh_context": True,
                            "authored_reviewed_artifacts": False,
                        },
                    }
                ),
                "structural_validation": "pass",
                "verdict": "approve",
                "blocking_findings": [],
                "open_blocker_count": 0,
                "required_reviewer_independence": True,
            }

        # Filenames deliberately sort cold before fresh.
        (self.root / "审查" / "z-cold.json").write_text(
            json.dumps(verdict_doc("cold_read"), ensure_ascii=False),
            encoding="utf-8",
        )
        (self.root / "审查" / "a-fresh.json").write_text(
            json.dumps(verdict_doc("independent_agent"), ensure_ascii=False),
            encoding="utf-8",
        )
        batched = run_tool("review-batch", str(self.root))
        self.assertEqual(batched.returncode, 0, batched.stderr)
        summary = json.loads(batched.stdout)
        self.assertEqual(summary["applied"], 2, summary)
        evidence = load_state(self.root)["artifacts"]["EP001:script"][
            "review_evidence"
        ]
        self.assertEqual(
            evidence["reviewer_independence"]["effective_review_mode"],
            "fresh_agent",
        )
        self.assertEqual(
            load_state(self.root)["artifacts"]["EP001:script"]["delivery_gate"],
            "ready",
        )

    def test_verdict_aggregated_errors(self) -> None:
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        # A verdict missing every structural field reports them all at once.
        (self.root / "审查").mkdir(exist_ok=True)
        (self.root / "审查" / "bad.json").write_text(
            json.dumps({"review_id": "REV-BAD", "verdict": "approve"}),
            encoding="utf-8",
        )
        reviewed = run_tool(
            "review",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--verdict",
            "approve",
            "--verdict-owner",
            "short-drama-review",
            "--verdict-artifact",
            "审查/bad.json",
        )
        self.assertNotEqual(reviewed.returncode, 0)
        for fragment in (
            "requested_review_mode",
            "effective_review_mode",
            "reviewer",
            "required_reviewer_independence",
            "structural_validation",
            "findings_ref",
            "reviewed_artifacts",
            "blocking_findings",
            "open_blocker_count",
        ):
            self.assertIn(fragment, reviewed.stderr, reviewed.stderr)

    def test_accept_batch_is_idempotent(self) -> None:
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        first = json.loads(run_tool("accept-batch", str(self.root)).stdout)
        self.assertEqual(first["applied"], 1)
        self.assertEqual(first["failed"], 0)
        # Replaying the same decision against an already accepted artifact is a
        # skipped record, not a fake failure: exit code stays 0.
        replay = json.loads(run_tool("accept-batch", str(self.root)).stdout)
        self.assertEqual(replay["applied"], 0)
        self.assertEqual(replay["failed"], 0)
        skipped_reasons = {
            result["reason"]
            for result in replay["results"]
            if result["status"] == "skipped"
        }
        self.assertIn("already accepted with identical targets", skipped_reasons)
        state = load_state(self.root)
        self.assertEqual(
            state["artifacts"]["EP001:script"]["creator_acceptance"], "accepted"
        )

    def test_decide_force_replaces_decision(self) -> None:
        self._publish_candidate()
        first = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        decision_path = self.root / "创作者决策" / "EP001-script.json"
        self.assertTrue(decision_path.is_file())
        old_doc = json.loads(decision_path.read_text(encoding="utf-8"))
        self.assertEqual(old_doc["supersedes_decision_id"], None)
        # Plain decide refuses to overwrite.
        refused = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("decision file already exists", refused.stderr)
        # --force replaces the file and records the superseded decision_id.
        replaced = json.loads(
            run_tool(
                "decide",
                str(self.root),
                "--artifact-id",
                "EP001:script",
                "--decision",
                "accepted",
                "--force",
            ).stdout
        )
        new_doc = json.loads(decision_path.read_text(encoding="utf-8"))
        self.assertEqual(new_doc["decision_id"], replaced["decision_id"])
        self.assertEqual(new_doc["supersedes_decision_id"], old_doc["decision_id"])
        # The replaced decision still applies cleanly.
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        state = load_state(self.root)
        self.assertEqual(
            state["artifacts"]["EP001:script"]["creator_acceptance"], "accepted"
        )

    def test_publish_warns_stale_screenplay_index(self) -> None:
        (self.root / "输入").mkdir(exist_ok=True)
        script = self.root / "输入" / "s.md"
        script.write_text(
            "## EP001-SC001 内 · 客厅 · 夜\n\n葛晴（打量游森）：你回来了。\n",
            encoding="utf-8",
        )
        (self.root / "剧集" / "EP001").mkdir(parents=True, exist_ok=True)
        stale_index = self.root / "剧集" / "EP001" / "screenplay-index.jsonl"
        stale_index.write_text(
            json.dumps(
                {
                    "record_type": "screenplay_index_meta",
                    "schema_version": "1.0.0",
                    "source_ref": {
                        "owner": "short-drama-write",
                        "artifact": "剧集/EP001/screenplay.md",
                        "hash": "0" * 64,
                    },
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        published = run_tool(
            "publish",
            str(self.root),
            "--owner",
            "short-drama-write",
            "--artifact-id",
            "EP001:script",
            "--output",
            "剧集/EP001/screenplay.md=输入/s.md",
        )
        self.assertEqual(published.returncode, 0, published.stderr)
        self.assertIn(
            "screenplay index is stale for 剧集/EP001/screenplay.md", published.stdout
        )
        # A matching index hash produces no warning.
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "p2"
            init = run_tool("init", str(root), "--title", "索引匹配")
            self.assertEqual(init.returncode, 0, init.stderr)
            (root / "输入").mkdir(exist_ok=True)
            script2 = root / "输入" / "s.md"
            script2.write_text(
                "## EP001-SC001 内 · 客厅 · 夜\n\n葛晴（打量游森）：你回来了。\n",
                encoding="utf-8",
            )
            script_hash = hashlib.sha256(script2.read_bytes()).hexdigest()
            (root / "剧集" / "EP001").mkdir(parents=True, exist_ok=True)
            matching_index = root / "剧集" / "EP001" / "screenplay-index.jsonl"
            matching_index.write_text(
                json.dumps(
                    {
                        "record_type": "screenplay_index_meta",
                        "schema_version": "1.0.0",
                        "source_ref": {
                            "owner": "short-drama-write",
                            "artifact": "剧集/EP001/screenplay.md",
                            "hash": script_hash,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            clean = run_tool(
                "publish",
                str(root),
                "--owner",
                "short-drama-write",
                "--artifact-id",
                "EP001:script",
                "--output",
                "剧集/EP001/screenplay.md=输入/s.md",
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertNotIn("warnings", clean.stdout)

    def test_publish_warns_under_target_duration(self) -> None:
        project = load_project(self.root)
        project["format"]["target_seconds_per_episode"] = 300
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        published = self._publish_candidate()
        self.assertIn(
            "estimated on-screen time for 剧集/EP001/screenplay.md is ~2s, "
            "below target_seconds_per_episode 300s",
            published.stdout,
        )

    def test_pipeline_reports_duration_estimate(self) -> None:
        project = load_project(self.root)
        project["format"]["target_seconds_per_episode"] = 300
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        report = json.loads(run_tool("pipeline", str(self.root)).stdout)
        estimate = report["episodes"]["EP001"]["duration_estimate"]
        self.assertEqual(estimate["target_seconds"], 300)
        self.assertEqual(estimate["estimated_seconds"], 2)
        self.assertEqual(estimate["delta_seconds"], -298)

    def test_pipeline_m1_requires_the_three_declared_outputs(self) -> None:
        project = load_project(self.root)
        for key in ("visual_direction", "production_profile"):
            project["creator_authority"][key] = {"status": "accepted"}
        (self.root / "short-drama.json").write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        source = self.root / "输入" / "director-brief.md"
        source.parent.mkdir(exist_ok=True)
        source.write_text("# 导演阐述\n", encoding="utf-8")
        published = run_tool(
            "publish",
            str(self.root),
            "--owner",
            "short-drama-develop",
            "--artifact-id",
            "project:director-brief",
            "--output",
            "项目开发/director-brief.md=输入/director-brief.md",
        )
        self.assertEqual(published.returncode, 0, published.stderr)
        self.assertEqual(
            run_tool(
                "decide",
                str(self.root),
                "--artifact-id",
                "project:director-brief",
                "--decision",
                "accepted",
            ).returncode,
            0,
        )
        self.assertEqual(run_tool("accept-batch", str(self.root)).returncode, 0)
        report = json.loads(run_tool("pipeline", str(self.root)).stdout)
        self.assertEqual(report["current_milestone"], "M1")
        message = report["blockers"][0]["message"]
        self.assertIn("creative-brief.md", message)
        self.assertIn("story-engine.md", message)
        self.assertIn("episode-map.jsonl", message)

    def test_accept_batch_does_not_skip_tampered_decision(self) -> None:
        self._publish_candidate()
        run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
        )
        first = json.loads(run_tool("accept-batch", str(self.root)).stdout)
        self.assertEqual(first["applied"], 1)
        # Rewrite the consumed decision file: same targets, new hash. The
        # idempotent skip must not hide this — the recorded evidence ref no
        # longer matches, so the strict path reports a failure instead.
        decision_path = self.root / "创作者决策" / "EP001-script.json"
        doc = json.loads(decision_path.read_text(encoding="utf-8"))
        doc["decided_at"] = "tampered"
        decision_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        replay = json.loads(run_tool("accept-batch", str(self.root)).stdout)
        self.assertEqual(replay["applied"], 0)
        self.assertEqual(replay["failed"], 1)
        failed_reasons = {
            r["reason"] for r in replay["results"] if r["status"] == "failed"
        }
        self.assertIn("creator decision does not match exact candidate targets", failed_reasons)
        skipped_reasons = {
            r["reason"] for r in replay["results"] if r["status"] == "skipped"
        }
        self.assertNotIn("already accepted with identical targets", skipped_reasons)

    def test_decide_output_must_stay_in_decisions_root(self) -> None:
        self._publish_candidate()
        # A protected root (delivery tree) is refused by the layout guard.
        refused = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
            "--output",
            "交付/evil.json",
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("delivery tree is written by the packaging gate", refused.stderr)
        # A publishable-but-wrong root (bible) is refused by the decisions-root
        # confinement.
        refused2 = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
            "--output",
            "设定集/x.json",
        )
        self.assertNotEqual(refused2.returncode, 0)
        self.assertIn("decision output must live under the creator-decisions root", refused2.stderr)
        # An explicit target inside the decisions root still works.
        ok = run_tool(
            "decide",
            str(self.root),
            "--artifact-id",
            "EP001:script",
            "--decision",
            "accepted",
            "--output",
            "创作者决策/alt.json",
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue((self.root / "创作者决策" / "alt.json").is_file())

    def test_publish_revision_index_with_previous_source_ref(self) -> None:
        # A screenplay-index rebuilt with --previous-index --previous-source
        # carries previous_source_ref (a full ArtifactRef pointing at the
        # *previous* screenplay revision) in its meta record. That is revision
        # lineage, not a consumed input — publishing it must not fail with
        # "candidate input has no matching candidate provider" because the old
        # hash has no provider anymore.
        (self.root / "输入").mkdir(exist_ok=True)
        script = self.root / "输入" / "s.md"
        script.write_text(
            "## EP001-SC001 内 · 客厅 · 夜\n\n葛晴（打量游森）：你回来了。\n",
            encoding="utf-8",
        )
        published = run_tool(
            "publish",
            str(self.root),
            "--owner",
            "short-drama-write",
            "--artifact-id",
            "EP001:script",
            "--output",
            "剧集/EP001/screenplay.md=输入/s.md",
        )
        self.assertEqual(published.returncode, 0, published.stderr)
        old_hash = hashlib.sha256(script.read_bytes()).hexdigest()
        # Revise the screenplay and rebuild the index with lineage refs.
        script.write_text(
            "## EP001-SC001 内 · 客厅 · 夜\n\n葛晴（打量游森）：你回来了。\n"
            "游森（点头）：路上顺利。\n",
            encoding="utf-8",
        )
        new_hash = hashlib.sha256(script.read_bytes()).hexdigest()
        index = self.root / "输入" / "screenplay-index.jsonl"
        index.write_text(
            json.dumps(
                {
                    "record_type": "screenplay_index_meta",
                    "schema_version": "1.0.0",
                    "source_ref": {
                        "owner": "short-drama-write",
                        "artifact": "剧集/EP001/screenplay.md",
                        "hash": new_hash,
                        "authority": "candidate",
                    },
                    "previous_source_ref": {
                        "owner": "short-drama-write",
                        "artifact": "剧集/EP001/screenplay.md",
                        "hash": old_hash,
                        "authority": "candidate",
                    },
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        revised = run_tool(
            "publish",
            str(self.root),
            "--owner",
            "short-drama-write",
            "--artifact-id",
            "EP001:script",
            "--output",
            "剧集/EP001/screenplay.md=输入/s.md",
        )
        self.assertEqual(revised.returncode, 0, revised.stderr)
        index_pub = run_tool(
            "publish",
            str(self.root),
            "--owner",
            "short-drama-write",
            "--artifact-id",
            "EP001:index",
            "--output",
            "剧集/EP001/screenplay-index.jsonl=输入/screenplay-index.jsonl",
            "--input",
            f"剧集/EP001/screenplay.md={new_hash}",
        )
        self.assertEqual(index_pub.returncode, 0, index_pub.stderr)
        self.assertNotIn(
            "no matching candidate provider", index_pub.stderr
        )


if __name__ == "__main__":
    unittest.main()
