---
name: short-drama-review
description: 只读检查和独立审查短剧原著分析、开发、剧本、资产、连续性、图片提示词、分镜、关键帧和视频提示词，并输出带证据 findings、verdict 与修订要求。用户要求审稿、检查、诊断模板感或 AI 味、判断能否交付时使用；不修改来源正文，明确要求修改时将 findings 交回对应 owner。
---

# 短剧审查

只发布审查问题、结论和按 owner 分组的修订要求，不在同一次审查中修改来源。

## 快速入口

1. 每个项目会话首次运行 core `preflight`；不要读取套件清单。
2. 先确定唯一 scope，再运行：

   ```text
   project_tool.py review-bundle <project> --episode EP001 --scope <scope> --compact
   ```

3. 例行修订复核使用 `--delta-from <base-verdict>`，只读改变目标。
4. 交付终审使用 `--scope full_episode`，不得使用 compact/delta 替代全量证据。
5. 所有权、参考媒体或审查记录异常时才读
   [stage-contract.md](references/stage-contract.md)。

## Scope

- `source_analysis`
- `story_script`
- `assets_continuity`
- `image_prompts`
- `storyboard_keyframes`
- `video_prompts`
- `full_episode`
- `delivery_privacy`
- `project_calibration`

只读当前 scope 对应量表。完整审查方法见
[review-method.md](references/review-method.md)，制作质量门见
[production-quality-gates.md](references/production-quality-gates.md)。只有问题确实涉及模板感、
重复手法或 AI 味时才读 [anti-template-repair.md](references/anti-template-repair.md)。
按 scope 只加载一份量表：source analysis、story/script、assets/prompts、visual/motion 分别见
[rubric-source-analysis.md](references/rubric-source-analysis.md)、
[rubric-story-script.md](references/rubric-story-script.md)、
[rubric-assets-prompts.md](references/rubric-assets-prompts.md)、
[rubric-visual-motion.md](references/rubric-visual-motion.md)。只有使用授权生产观察时才读
[project-calibration.md](references/project-calibration.md)。

## 审查方式

- L1 fresh：项目内该产物类型首次审查、越出派发范围的大改、交付终审。
- L1.5 cold_read：类型基准已建立后的例行首审；当前上下文只读 review bundle、量表和模板。
- L2 delta_verify：只核销 base findings 的修订结果和 preserve set；发现越界改动立即回到 L1。

同一目标集的多个范围合并为一个 fresh 会话，不按产物类型重复启动。

## 工作流

1. 冻结目标路径、hash、创作者限制、scope 和审查方式。
2. 先看 bundle 中的机械检查；结构失败时一次列出全部互不依赖问题。
3. 对内容 finding 记录准确位置、短证据、影响、必须达到的修订结果、owner 和严重程度。
4. 区分 structural invariant、reviewed invariant、craft default 和 taste option。
5. 跨层追踪：剧本事实 → 资产决定 → 镜头边界 → 关键帧 → 运动 → 下一状态。
6. 写 findings JSONL 与 verdict JSON，使用 `review` 或 `review-batch` 应用。

## 结论

- `APPROVE`：无阻断问题。
- `APPROVE_WITH_NOTES`：只有非阻断改进。
- `REVISE`：存在结构或内容错误。
- `PROVISIONAL`：审查隔离不可证明或前置资料不足。

## 边界

- 不编辑开发、剧本、资产、提示词或分镜来源。
- 不从文字产物声称成片身份、表演、口型、混音或市场效果。
- 没有证据不打分，不把口味选择单独作为阻断。
- 生产观察只在其授权项目、版本和条件内有效。
