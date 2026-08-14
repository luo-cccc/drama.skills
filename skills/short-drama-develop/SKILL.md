---
name: short-drama-develop
description: 仅在用户明确调用 $short-drama-develop 时触发；未点名不得触发，且项目须含 short-drama.json。把小说、点子或多集剧本发展为创作简报、故事引擎、导演阐述和分集地图。
---

# 短剧开发

## 快速入口

1. 当前请求须明确调用 `$short-drama-develop`，否则停止。再查 `short-drama.json`；缺失时提示用户调用 `$short-drama` 初始化；否则 `preflight`，不要读取套件清单。
2. 运行 `prepare <project> --stage develop --intent create|revise`。
3. 只读任务胶囊和其中列出的来源；需要所有权异常时才读
   [stage-contract.md](references/stage-contract.md)。

## 入口判断

- 点子或梗概：建立创作者契约，再探索真正不同的方向。
- 已有原著分析：只消费已确认的分析结论和准确来源。
- 已有简报或故事引擎：直接修订缺失层，不重建已接受部分。
- 已有多集完整剧本/散稿：读
  [multi-episode-intake.md](references/multi-episode-intake.md)，用 `episode_intake.py` 建一次索引，
  之后逐集切片、分批合并并从磁盘恢复进度。
- 已有单集剧本且无需系列规划：不强制补开发文件。

## 工作流

1. 锁定受众、时长、题材边界、不可改事实和本轮需要创作者决定的选择。
2. 比较少量真正不同的戏剧方向；需要完整方法时读
   [story-craft.md](references/story-craft.md)。
3. 建立人物追求、阻力、代价、升级机制、信息权限和长线回报组成的故事引擎。
4. 将系列运动落到分集地图；读取
   [episode-design.md](references/episode-design.md)。
5. 连续项目同时维护稳定义务 ID；需要时读
   [serial-obligation-ledger.md](references/serial-obligation-ledger.md)，并运行
   `scripts/episode_map_check.py`。
6. 用 `finalize --packet ...` 一次校验并形成发布候选。

专项开发只在命中时读取：改编见 [adaptation-craft.md](references/adaptation-craft.md)，
创意参考见 [creative-reference-intake.md](references/creative-reference-intake.md)，导演阐述见
[director-brief-craft.md](references/director-brief-craft.md)，类型与 Hook 见
[genre-and-hook-playbook.md](references/genre-and-hook-playbook.md) 和
[genre-cards.md](references/genre-cards.md)，高概念机制见
[premise-devices.md](references/premise-devices.md)，揭示/反转/兑现见
[reveal-reversal-payoff.md](references/reveal-reversal-payoff.md)，跨集角色记忆见
[serial-character-and-memory.md](references/serial-character-and-memory.md)。

## 产物

- `项目开发/creative-brief.md`
- `项目开发/story-engine.md`
- `项目开发/director-brief.md`（需要时）
- `项目开发/episode-map.jsonl`
- `项目开发/adaptation-map.jsonl`、`series-arc.json`（适用时）

## 规则

- 开发层拥有规划契约，不拥有剧本执行、资产模型、镜头或提示词。
- 形态和题材词不能代替具体压力、行动、转折和回报。
- 创作者接受后才能作为下游权威。
- owner 自检不等于终审；质量结论交 `$short-drama-review`。
