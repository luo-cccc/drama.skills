---
name: short-drama-assets
description: 建立和维护短剧人物、生物、场景、道具、载具与效果的生成资产基线，并从剧本提取集内出现、复用决定、状态变化和连续性。用户要求资产基线、角色或场景设定、三视图契约、道具状态、复用判断或剧本资产拆解时使用；不写最终图片提示词，不生成媒体。
---

# 短剧资产

## 快速入口

1. 每个项目会话首次运行 core `preflight`；不要读取套件清单。
2. 项目级 M1.5a 或单集 M3 分别运行
   `prepare <project> --stage assets [--episode EP001] --intent create|revise`。
3. 先读任务胶囊，只打开列明的剧本块、既有身份和连续性记录。
4. 所有权、形态或候选引用异常时才读
   [stage-contract.md](references/stage-contract.md)。

## M1.5a 生成资产基线

1. 从 accepted develop、创作者描述或精确 candidate screenplay block 列出资产范围。
2. 为实际资产选择 full/compact，建立稳定 asset/model/variant/view ID。
3. 记录识别锚点、状态边界、禁止漂移、空间拓扑和标准观察方向。
4. 运行 `scripts/asset_baseline_check.py`；通过并由创作者接受后交给 M1.5b。

身份播种可以与剧本 candidate 同轮展示，但接受顺序仍是：身份 → M1.5a → M1.5b →
重发布并接受 M2。未接受记录必须保持 proposed/candidate。

## M3 单集拆解

1. 按 [occurrence-extraction.md](references/occurrence-extraction.md) 从 screenplay index
   逐块提 occurrence，先记录出现事实，不立即创建资产。
2. 按 [identity-vs-variant.md](references/identity-vs-variant.md) 判断 reuse、new variant、
   new asset 或 unresolved。
3. 只写最小可识别身份与本集状态增量，不复制整本设定集。
4. 按 [continuity-delta.md](references/continuity-delta.md) 记录 before、after、原因、范围和
   受影响绑定。
5. Pipeline 2.0 中发现 new asset/new variant 时回退补齐 M1.5a/M1.5b 和 M2，不在 M3
   偷建基线。
6. 运行 `finalize --packet ...`，一次校验 occurrence、decision 和 continuity。

专项细节只在命中时读取：人物/造型见
[character-and-look.md](references/character-and-look.md)，空间/View 见
[location-and-view.md](references/location-and-view.md)，道具/状态见
[prop-and-state.md](references/prop-and-state.md)，接受前审查见
[asset-review-checklist.md](references/asset-review-checklist.md)。

## 产物

- `设定集/generation/{asset-scope,asset-models,spatial-models,variant-models,view-contracts}.jsonl`
- `设定集/generation/asset-baseline.md`
- `设定集/{characters,looks,locations,location-views,props,prop-states}.jsonl`
- `剧集/<EP>/assets/{occurrences,decisions,continuity}.jsonl`

## 边界

- 不猜含混身份，不把临时状态写进永久身份。
- 不产出最终图片提示词、镜头或运动规格。
- unresolved 不进入 M4a。
- 创作者接受和独立审查不能由结构校验替代。
