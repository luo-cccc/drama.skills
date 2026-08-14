---
name: short-drama-image-prompts
description: 为已确认的短剧资产、视图、造型和状态建立标准提示片段、资产图片提示词与 Look Development 文本规格。用户要求角色设定图、三视图、场景板、道具图、状态变体、风格帧或修改图片提示词时使用；只输出结构化规格和确定性 Markdown，不生成图片或调用供应商接口。
---

# 短剧图片提示词

## 快速入口

1. 每个项目会话首次运行 core `preflight`；不要读取套件清单。
2. 运行 `prepare <project> --stage image-prompts --episode EP001 --intent create|revise`。
3. 先读任务胶囊，只读取实际消费的 asset/model/view/variant 和视觉方向。
4. 参考媒体、形态或所有权异常时才读
   [stage-contract.md](references/stage-contract.md)。

## 两种职责

- M1.5b：为 M1.5a 已接受模型建立 canonical fragments 和标准片段库。
- M4a：为 M2/M3 实际消费的资产建立 asset-board 规格和用户可复制 Markdown。

## 工作流

1. 确认用途、资产 ID、模型、View、variant、语言和已接受视觉方向。
2. 只加载当前类型所需方法：通用配方读
   [common-recipe.md](references/common-recipe.md)，批量生产表读
   [production-sheet-recipes.md](references/production-sheet-recipes.md)。
3. 写结构化 `prompt_components`、任务、局部增量和排除项，不重复整份资产描述。
4. M4a 必须覆盖 M2 声明的每个实际资产及全部允许 View/variant，不能用代表性提示词代替。
5. 运行 `finalize --packet ...`。它使用 canonical fragments 确定性生成
   `generic_prompt`、编译 manifest 和 `image-prompts.md`，禁止模型自由改写派生 Markdown。

专项提示词只在命中时读取：人物、场景、道具分别见
[character-and-look.md](references/character-and-look.md)、
[location-plate.md](references/location-plate.md)、[prop-plate.md](references/prop-plate.md)；
Look Development 与状态变体见 [lookdev-frame.md](references/lookdev-frame.md)、
[look-and-state-variant.md](references/look-and-state-variant.md)；定点修订和审查样例见
[edit-and-revision.md](references/edit-and-revision.md)、
[review-and-fixtures.md](references/review-and-fixtures.md)。

## 产物

- `设定集/generation/canonical-fragments.jsonl`
- `设定集/generation/canonical-prompt-library.md`
- `项目开发/lookdev-image-prompt-specs.jsonl`、`lookdev-prompts.md`（需要时）
- `剧集/<EP>/assets/image-prompt-specs.jsonl`
- `剧集/<EP>/assets/image-prompts.md`（由结构化源派生）

## 边界

- 不创建资产身份、模型或 View。
- 不从旧长提示词反向总结身份。
- 不生成、上传或检查图片。
- 参考图可用范围必须来自创作者说明或授权观察记录。
- owner 不自行签发终审结论。
