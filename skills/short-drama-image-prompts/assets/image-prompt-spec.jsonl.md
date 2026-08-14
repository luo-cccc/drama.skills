# `image-prompt-specs.jsonl` 填写模板

每行一个候选规格对象，用于接受前预览；示例值不是默认答案。删除不适用字段，不要添加
媒体任务、供应商或接口字段。上游引用默认绑定准确的已接受快照；与本对象同次发布的目标、以及
`设定集` 中的 `proposed` 播种记录，可写 `authority:candidate`，此时对象保持 provisional、
不接受、不交付，直到被绑定记录接受。对象接受状态由事务生命周期记录，不能靠改状态字样伪造。

```json
{
  "spec_id": "IMG-<stable-id>",
  "status": "candidate",
  "purpose": "character_sheet | location_plate | prop_plate | look_state_variant | edit_delta",
  "asset_bindings": [
    {
      "asset_id": "CHAR/CREATURE/LOC/PROP/VEHICLE/EFFECT-<id>",
      "model_ref": {
        "owner": "short-drama-assets",
        "artifact": "设定集/generation/asset-models.jsonl | 设定集/generation/spatial-models.jsonl",
        "hash": "<sha256>",
        "record_id": "MODEL/SPATIAL-<id>"
      },
      "variant_ref": {
        "owner": "short-drama-assets",
        "artifact": "设定集/generation/variant-models.jsonl",
        "hash": "<sha256>",
        "record_id": "VAR-<id>"
      },
      "view_ref": {
        "owner": "short-drama-assets",
        "artifact": "设定集/generation/view-contracts.jsonl",
        "hash": "<sha256>",
        "record_id": "GVIEW-<id>"
      },
      "identity_ref": {
      "owner": "short-drama-assets",
      "artifact": "设定集/<identity-owner-file>.jsonl",
      "hash": "<sha256>",
      "record_id": "CHAR/LOC/PROP-<id>"
      }
    }
  ],
  "source_refs": [
    {
      "artifact": "设定集/<owner-file>.jsonl",
      "hash": "<sha256>",
      "field": "/<field>",
      "role": "identity_anchor | variant_delta | geography | scale | text_policy",
      "owner": "short-drama-assets",
      "record_id": "<record>"
    }
  ],
  "reference_bindings": [
    {
      "slot_id": "REF-<stable-slot>",
      "order": 1,
      "artifact_ref": {
        "owner": "short-drama-assets",
        "artifact": "设定集/<owner-file>.jsonl",
        "hash": "<sha256>",
        "record_id": "<accepted-reference-record>"
      },
      "role": "composition",
      "may_control": [
        "<本次允许借用的构图事实>"
      ],
      "must_not_control": [
        "<身份/内容/文字/状态等禁入事实>"
      ],
      "admission_status": "unverified | creator_described | visually_inspected",
      "reference_observation_ref": null,
      "unresolved_risks": [
        "<没有观察证据时保留的文字/水印/裁切风险>"
      ]
    }
  ],
  "recipe": {
    "name": "<type-recipe>",
    "version": "<suite recipe version>",
    "hash": "<sha256>"
  },
  "intent": {
    "reuse_job": "<这张参考图后续保持什么>",
    "audience": "<使用者/阶段>"
  },
  "identity_or_form_anchors": [
    "<稳定、可见、可比较的锚点>"
  ],
  "variant_deltas": [
    {
      "field": "<变化对象>",
      "observable_change": "<位置/范围/结果>",
      "valid_range": "<接受的有效范围>"
    }
  ],
  "composition": {
    "view": "<观察方向/视图>",
    "framing": "<主体占比或板式>",
    "orientation": "<方向定义>",
    "scale_relation": "<尺度参照>",
    "spatial_relations": [
      "<锚点之间的关系>"
    ]
  },
  "appearance": {
    "materials": [
      "<识别所需材质>"
    ],
    "palette": "<主次色关系>",
    "lighting": "<光源、方向、用途>",
    "atmosphere": "<有事实依据的气氛>"
  },
  "background": {
    "policy": "clean | contextual | empty_stage",
    "details": "<背景与允许出现内容>"
  },
  "text_handling": {
    "source_policy_ref": {
      "artifact": "设定集/props.jsonl",
      "hash": "<sha256>",
      "field": "/text_policy",
      "owner": "short-drama-assets",
      "record_id": "PROP-<id>"
    },
    "source_mode": "exact_readable | graphic_only | no_readable_text | pending_creator_text",
    "render_treatment": {
      "mode": "readable | symbolic | blank | postproduction",
      "surface": "<承载面>",
      "exact_text": "<仅 readable 且来自接受源时填写>",
      "layout_or_reserved_area": "<方向/区域/行数>"
    },
    "mapping_rationale": "<为何本次呈现保持 source policy>"
  },
  "constraints": [
    "<必须出现/保持>"
  ],
  "negative_constraints": [
    "<仅当前高风险且不矛盾的排除>"
  ],
  "edit": {
    "changes": [
      "<有边界变化>"
    ],
    "preserve": [
      "<身份/构图/光线/未影响区域>"
    ],
    "continuity_impact": "<影响的 accepted variant/binding 或 none>",
    "target_ref": {
      "owner": "short-drama-image-prompts",
      "artifact": "<精确目标>",
      "hash": "<sha256>",
      "record_id": "IMG-<target-id>",
      "field": "/generic_prompt"
    },
    "entity_or_region": "<区域>"
  },
  "creator_overrides": [
    {
      "rule_id": "<IMG-*>",
      "choice": "<覆盖选择>",
      "rationale": "<原因>"
    }
  ],
  "task_and_format": "<任务类型、板式、数量、画幅与输出要求>",
  "prompt_components": {
    "profile": "asset_board",
    "fragment_refs": [
      {"fragment_id": "FRAG-STYLE-<id>", "hash": "<sha256>"},
      {"fragment_id": "FRAG-IDENTITY-<id>", "hash": "<sha256>"},
      {"fragment_id": "FRAG-CONTINUITY-<id>", "hash": "<sha256>"},
      {"fragment_id": "FRAG-VARIANT-<id>", "hash": "<sha256>"},
      {"fragment_id": "FRAG-VIEW-<id>", "hash": "<sha256>"},
      {"fragment_id": "FRAG-NEGATIVE-<id>", "hash": "<sha256>"}
    ],
    "local_instructions": ["<当前板式、构图、光线与文字处理>"],
    "local_negative_constraints": ["<只属于本任务的排除项>"]
  },
  "compilation_manifest": {
    "compiler_version": "1.0",
    "fragment_hashes": {"FRAG-<id>": "<sha256>"},
    "output_hash": "<sha256>"
  },
  "generic_prompt": "<prompt_compile.py 的确定性编译结果，不得自由改写>",
  "provenance": "creator_project"
}
```


复制后按 `purpose` 删除不适用字段和悬空引用。先写绑定与本任务字段，再运行
`scripts/prompt_compile.py` 生成 `compilation_manifest` 与 `generic_prompt`；禁止手写或改写编译结果。
编译器逐个 `asset_bindings[].asset_id` 校验片段：identity/continuity/negative 必须引用同一
`model_ref.record_id`，View 片段的 scope 与引用必须匹配 `view_ref.record_id`。声明 variant 时
必须且只能有匹配的 variant_delta，且该片段同时引用 variant 记录和当前基础 model；所有片段
必须允许当前 profile。M4a 文件固定使用 `asset_board`，每条规格只绑定一个资产，并分别覆盖
基线、全部 M2 View 和全部 M2 generation variant。对应 Markdown 保持
“固定资产基线 / 状态增量 / 当前任务 / 排除项”的语义顺序，标题跟随 `prompt_language`。
Look Development 不使用本超集模板，改读
[`lookdev-frame-spec.jsonl.md`](lookdev-frame-spec.jsonl.md)，避免普通人物、地点和道具规格加载
风格帧专属字段。
每条参考只声明一个用途，多参考的 `slot_id` 稳定且 `order` 显式。类型取舍、文字政策与
参考准入由技能按 `references/common-recipe.md` 判断。候选与已接受对象分开发布；自然语言修改先形成
候选和内容差异，不直接覆盖原记录。
