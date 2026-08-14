---
name: short-drama-write
description: 仅在用户明确调用 $short-drama-write 时触发；未点名不得触发，且项目须含 short-drama.json。创建或修改单集卡、因果节拍和可拍摄 Markdown 剧本；只检查不修改时不使用本技能。
---

# 短剧写作

## 快速入口

1. 当前请求须明确调用 `$short-drama-write`，否则停止。再查 `short-drama.json`；缺失时提示用户调用 `$short-drama` 初始化；否则 `preflight`，不要读取套件清单。
2. 运行 `prepare <project> --stage write --episode EP001 --intent create|revise`。
3. 先读任务胶囊，只打开列明的单集契约、必要资产记录和当前剧本块。
4. 所有权或契约缺失时才读 [stage-contract.md](references/stage-contract.md)。

## 工作流

1. 确认单集契约唯一 owner。已有 accepted episode map 时只投影；没有开发记录时使用
   `write_standalone` 单集卡，不同时激活两种权威。
2. 新写、续写或大修时按
   [writing-quality-loop.md](references/writing-quality-loop.md) 运行
   `writer_quality.py build-brief`，只带本集合同和最多三份邻近剧本差异。
3. 建立因果节拍：行动改变局面，结果制造下一步压力；不要用情绪标签代替事件。
4. 逐场确定议程、对抗、可见动作、方向性转折和退出状态。需要时才读
   [script-craft.md](references/script-craft.md) 与
   [dialogue-craft.md](references/dialogue-craft.md)。
5. 只在 `screenplay.md` 写正文。剧本不决定景别、机位、逐镜 View 或镜头时长。
6. 新元素标记待播种，不静默改写设定集。固定主线在 episode-card 中绑定实际消费的
   generation asset/model/view/fragment 记录。
7. 运行 `finalize --packet ...`：它生成 candidate screenplay index、校验结构，并可显式发布。
8. 新写、续写或大修再运行 `writer_quality.py check`；只修相关块，然后重新 finalize。

专项写作只在命中时读取：基础格式见
[screenplay-format.md](references/screenplay-format.md)，制作方言见
[production-format-dialect.md](references/production-format-dialect.md)，声音组织见
[scene-sound-dramaturgy.md](references/scene-sound-dramaturgy.md)，场间交接见
[scene-handoff-capsule.md](references/scene-handoff-capsule.md)，避免可替换实现见
[substitutable-realization.md](references/substitutable-realization.md)。

## 产物

- `剧集/<EP>/episode-card.json`
- `剧集/<EP>/beats.jsonl`
- `剧集/<EP>/screenplay.md`
- `剧集/<EP>/screenplay-index.jsonl`（由 finalize 确定性生成）
- `剧集/<EP>/voice-record-sheet.jsonl`（需要配音本时）

## 修订纪律

- 修订已有剧本时基于当前文件和稳定 block ID，不凭对话记忆重写整集。
- 保留已接受合同和不相关块；映射歧义必须显式处理。
- owner 可以自检和修改，但不能给自己签发 review 通过。
- “只检查再决定是否修改”先交 `$short-drama-review`；收到 findings 后再定点修订。
