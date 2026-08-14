---
name: short-drama-novel-analyze
description: 将长篇小说、连载网文或大量散稿做只读、可追溯的章节索引、改编快评、逐章功能提取、剧情聚合、人物设定归并和分集候选。用户要求导入、拆解、分析原著，判断是否值得改短剧，或提供长篇文件路径时使用；不写剧本、不决定改编方案、不生成媒体。
---

# 长篇原著分析

## 快速入口

1. 每个项目会话首次运行 core `preflight`；不要读取套件清单。
2. 运行 `prepare <project> --stage novel-analyze --intent create`，先读任务胶囊。
3. 只读用户提供的原著和胶囊列出的项目来源，不把整部长篇一次塞入上下文。
4. 需要所有权或异常规则时才读 [stage-contract.md](references/stage-contract.md)。

## 工作流

1. 用 `scripts/novel_index.py` 建立唯一章节索引，保留原文件字节和章节跨度。
2. 先做抽样快评，再决定是否值得全量拆解。方法见
   [adaptation-triage.md](references/adaptation-triage.md)。
3. 获得继续确认后，按索引逐章提取剧情功能、人物行动、信息变化和可改编事件；方法见
   [chapter-extraction.md](references/chapter-extraction.md)。
4. 分批聚合剧情单元、节奏、人物和世界设定，不凭相似名称静默合并身份；见
   [aggregation-and-entities.md](references/aggregation-and-entities.md)。
5. 依据可见冲突、回报密度、生产负担和长线价值形成改编判断与分集候选；见
   [adaptation-value.md](references/adaptation-value.md)。
6. 将候选交给 `$short-drama-develop` 建立真正的改编契约。

## 产物

- `项目开发/source-analysis/_index.json`
- `项目开发/source-analysis/_progress.md`
- `项目开发/source-analysis/triage.md`
- `项目开发/source-analysis/chapters/*.jsonl`
- `项目开发/source-analysis/story-units.md`
- `项目开发/source-analysis/rhythm-and-emotion.md`
- `项目开发/source-analysis/characters.md`
- `项目开发/source-analysis/world.md`
- `项目开发/source-analysis/adaptation-value.md`
- `项目开发/source-analysis/episode-candidates.jsonl`

## 完成条件

- 每项判断可追溯到章节 ID 和来源跨度。
- 抽样与全量结论明确区分。
- 未读章节不被写成已分析事实。
- 使用 `finalize --packet ...` 校验工作文件；发布后由独立 review 审查。

## 边界

- 不为提高改编价值而补写原著不存在的事件。
- 不替创作者选择改编方向。
- 不写剧本、资产、分镜或媒体提示词。
