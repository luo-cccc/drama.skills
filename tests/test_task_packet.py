from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TOOL = REPO_ROOT / "skills/short-drama/scripts/project_tool.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("project_tool_task_packet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TaskPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = _load_module(PROJECT_TOOL)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.tool.initialize_project(
            self.root,
            title="任务胶囊测试",
            language="zh-CN",
            aspect_ratio="9:16",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_prepare_materializes_a_bounded_develop_packet(self) -> None:
        result = self.tool.prepare_task_packet(self.root, stage="develop")
        self.assertLess(result["packet_chars"], 10_000)
        packet_path = self.root / result["packet_path"]
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        self.assertEqual(packet["schema"], self.tool.TASK_PACKET_SCHEMA)
        self.assertEqual(packet["stage"], "develop")
        self.assertEqual(len(packet["outputs"]), 3)
        for output in packet["outputs"]:
            self.assertTrue((self.root / output["work_path"]).is_file())

        finalized = self.tool.finalize_task_packet(
            self.root,
            packet_relative=result["packet_path"],
        )
        self.assertEqual(finalized["status"], "pass", finalized["issues"])

    def test_packet_fails_closed_when_project_contract_changes(self) -> None:
        result = self.tool.prepare_task_packet(self.root, stage="develop")
        project_path = self.root / "short-drama.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["title"] = "变化后的标题"
        project_path.write_text(
            json.dumps(project, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "task packet is stale"):
            self.tool.finalize_task_packet(
                self.root,
                packet_relative=result["packet_path"],
            )

    def test_write_packet_defaults_to_ep001_and_derives_index(self) -> None:
        result = self.tool.prepare_task_packet(self.root, stage="write")
        packet = json.loads(
            (self.root / result["packet_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(packet["episode"], "EP001")
        finalized = self.tool.finalize_task_packet(
            self.root,
            packet_relative=result["packet_path"],
        )
        index = next(
            item for item in finalized["outputs"] if item["target"].endswith("screenplay-index.jsonl")
        )
        self.assertTrue((self.root / index["work_path"]).is_file())

    def test_review_bundle_supports_scope_compaction_and_delta(self) -> None:
        target = self.root / "项目开发" / "creative-brief.md"
        target.write_text("# 当前简报\n", encoding="utf-8")
        first = self.tool.build_review_bundle(
            self.root,
            targets={"项目开发/creative-brief.md": None},
            scope="story_script",
            compact=True,
        )
        self.assertEqual(first["serialization"], "compact")
        bundle_text = (self.root / first["bundle_path"]).read_text(encoding="utf-8")
        self.assertNotIn("\n  ", bundle_text)

        verdict = self.root / "审查" / "base-verdict.json"
        verdict.write_text(
            json.dumps(
                {
                    "review_id": "BASE-1",
                    "reviewed_artifacts": [
                        {
                            "path": "项目开发/creative-brief.md",
                            "hash": self.tool.sha256_file(target),
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "no changed targets"):
            self.tool.build_review_bundle(
                self.root,
                targets={"项目开发/creative-brief.md": None},
                delta_from="审查/base-verdict.json",
            )
        target.write_text("# 已修订简报\n", encoding="utf-8")
        delta = self.tool.build_review_bundle(
            self.root,
            targets={"项目开发/creative-brief.md": None},
            delta_from="审查/base-verdict.json",
        )
        self.assertTrue(delta["delta"])
        self.assertEqual(len(delta["targets"]), 1)


if __name__ == "__main__":
    unittest.main()
