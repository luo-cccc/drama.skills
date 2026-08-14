---
name: short-drama-video-prompts
description: 仅在用户明确调用 $short-drama-video-prompts 时触发；未点名不得触发，且项目须含 short-drama.json。为已接受镜头编写运动、表演、运镜、声音、generation clip 与交付容器规格；不生成视频。
---

# 短剧视频提示词

## 快速入口

1. 当前请求须明确调用 `$short-drama-video-prompts`，否则停止。再查 `short-drama.json`；缺失时提示用户调用 `$short-drama` 初始化；否则 `preflight`，不要读取套件清单。
2. 运行 `prepare <project> --stage video-prompts --episode EP001 --intent create|revise`。
3. 先读任务胶囊，只打开当前 shots、keyframes、声音引用和连续性边界。
4. 参考媒体、容器或所有权异常时才读
   [stage-contract.md](references/stage-contract.md)。

## 工作流

1. 冻结 shot ID、起始关键帧、时长、起止状态和排除项；运动规格只能实现这些边界。
2. 明确镜头真正发生的故事变化，保证动作量可在时长内完成。
3. 按 [motion-recipe.md](references/motion-recipe.md) 写主体动作、表演弧、摄影、环境、声音、
   timing plan 和结束报告。表演与动作时机需要细化时读
   [performance-action-timing.md](references/performance-action-timing.md)。
4. 不重复参考帧已说明的完整外貌、场景和光线，只保留运动中容易漂移的局部事实。
5. 根据项目 `max_clip_seconds` 将长 shot 连续覆盖为 generation clips；片段无间隙、无重叠，
   continuation 必须绑定上一片段授权输出观察。
6. 只有创作者声明多镜容器时才建立 delivery container；切换只发生在成员 shot 边界。
7. 运行 `finalize --packet ...`，确定性编译 motion prompt 和 `video-prompts.md`。
8. 再运行 `motion_timing_check.py`、`generation_clip_check.py`；有容器时运行
   `container_check.py`。

跨镜摄影、声桥和口型连续性需要时读
[camera-audio-continuity.md](references/camera-audio-continuity.md)。
需要完整字段语法、交付容器规则或审查样例时才读
[production-prompt-grammar.md](references/production-prompt-grammar.md)、
[delivery-profile.md](references/delivery-profile.md)、
[review-and-fixtures.md](references/review-and-fixtures.md)。

## 产物

- `剧集/<EP>/storyboard/motion-specs.jsonl`
- `剧集/<EP>/storyboard/generation-clips.jsonl`
- `剧集/<EP>/storyboard/delivery-containers.jsonl`（可选）
- `剧集/<EP>/storyboard/video-prompts.md`（由结构化源派生）

## 边界

- 不在镜头内部偷藏切镜，不改变 shot 开始或结束边界。
- 不补写台词、资产身份或剧情事件。
- 文本准备度不等于生成成片质量。
- 不生成媒体、上传参考帧、创建远程任务或轮询供应商。
- 本技能不自行终审。
