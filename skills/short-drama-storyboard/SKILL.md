---
name: short-drama-storyboard
description: 仅在用户明确调用 $short-drama-storyboard 时触发；未点名不得触发，且项目须含 short-drama.json。把已接受剧本和资产转换为原文落实表、镜头设计、连续性边界与冻结关键帧规格。
---

# 分镜与关键帧

## 快速入口

1. 当前请求须明确调用 `$short-drama-storyboard`，否则停止。再查 `short-drama.json`；缺失时提示用户调用 `$short-drama` 初始化；否则 `preflight`，不要读取套件清单。
2. 运行 `prepare <project> --stage storyboard --episode EP001 --intent create|revise`。
3. 先读任务胶囊，只打开本集 screenplay blocks、实际资产绑定和连续性。
4. 参考媒体、补拍关系或所有权异常时才读
   [stage-contract.md](references/stage-contract.md)。

## 工作流

1. 建 coverage：每个生产相关剧本块明确由哪些镜头落实、为何省略或如何在声音中落实。
2. 关键场次需要比较方案时，先做 scene visual plan 或 Coverage Audition；普通场次不强制。
3. 每镜先写观众注意点、戏剧目的、起始状态和结束边界，再决定构图与调度。
4. 绑定 accepted asset/model/view/variant、空间锚点、文字政策和连续性；不得自由描述替代 ID。
5. 按 [production-shot-grammar.md](references/production-shot-grammar.md) 设计可制作镜头，
   一个 shot 保持一个剪辑边界。
6. 每个固定主线镜头建立一个冻结首关键帧。关键帧只描述时刻，不写“先、再、最后”或运动过程；
   方法见 [keyframe-craft.md](references/keyframe-craft.md)。
7. 运行 `finalize --packet ...` 确定性编译关键帧 prompt 和 Markdown，再运行
   `scripts/storyboard_check.py`。

专项分镜只在命中时读取：方案试镜与场次计划见
[coverage-audition.md](references/coverage-audition.md)、
[scene-visual-plan.md](references/scene-visual-plan.md)，调度与镜头 craft 见
[blocking-playbooks.md](references/blocking-playbooks.md)、[shot-craft.md](references/shot-craft.md)，
修订身份、完整示例和审查样例见
[shot-revision-identity.md](references/shot-revision-identity.md)、
[screenplay-to-keyframe-example.md](references/screenplay-to-keyframe-example.md)、
[review-and-fixtures.md](references/review-and-fixtures.md)。

## 产物

- `剧集/<EP>/storyboard/coverage.json`
- `剧集/<EP>/storyboard/shots.jsonl`
- `剧集/<EP>/storyboard/keyframes.jsonl`
- `剧集/<EP>/storyboard/keyframe-prompts.md`（由 keyframes 派生）
- `coverage-auditions/<SC>.jsonl`、`scene-visual-plans/<SC>.jsonl`（可选）

## 边界

- 不新增、删除或改变故事事实；需要时退回 write owner。
- 不改变资产身份或状态权威。
- 镜头时长是剪辑意图，不是 generation clip 上限。
- 本技能不自行终审。
