# 文档导航

本页是仓库文档入口。创作项目运行时使用 `skills/short-drama/references/` 内随套件
发布的文档；仓库维护、测试和发布使用 `docs/` 下的维护文档。

## 按任务开始

| 目标 | 先读 | 需要时再读 |
|---|---|---|
| 第一次了解套件 | [项目 README](../README.md) | [端到端工作流与数据流](../skills/short-drama/references/workflow-dataflow.md) |
| 开始或继续一个项目 | [执行速查](../skills/short-drama/references/execution-quickstart.md) | [固定生产流程](../skills/short-drama/references/production-pipeline.md) |
| 理解长篇、单集与 15 秒视频调用的关系 | [端到端工作流与数据流](../skills/short-drama/references/workflow-dataflow.md) | [固定生产流程](../skills/short-drama/references/production-pipeline.md) |
| 查命令、接受、审查、打包 | [生命周期命令](../skills/short-drama/references/lifecycle-commands.md) | [创作者决定、预览与修订](../skills/short-drama/references/creator-workflow.md) |
| 查谁拥有事实、谁能消费、何时 stale | [契约与所有权](../skills/short-drama/references/contract-and-ownership.md) | 各技能的 `references/stage-contract.md` |
| 提升单集写作质量或排查模板感 | [写作质量闭环](../skills/short-drama-write/references/writing-quality-loop.md) | [剧本审查量表](../skills/short-drama-review/references/rubric-story-script.md) |
| 核对跨集 Hook、铺垫与兑现 | [连载叙事义务账本](../skills/short-drama-develop/references/serial-obligation-ledger.md) | [故事引擎模板](../skills/short-drama-develop/assets/story-engine.md) |
| 多集批量执行 | [生产 SOP](../skills/short-drama/references/production-sop.md) | [批量生产手册](../skills/short-drama/references/batch-production.md) |
| 维护仓库或准备发布 | [仓库维护手册](maintenance.md) | [发布说明](releases/release-notes.md) |

## 权威边界

同一主题只保留一个权威正文，其他文档只做导航或操作摘要：

| 主题 | 权威文档 |
|---|---|
| M0-M7 顺序、入口和出门条件 | `production-pipeline.md` |
| 跨阶段输入、输出和消费关系 | `workflow-dataflow.md` |
| 命令参数与生命周期行为 | `project_tool.py --help`、`lifecycle-commands.md` |
| 文件所有权、引用、过期和隐私 | `contract-and-ownership.md` |
| 创作者决定、预览链与修订边界 | `creator-workflow.md` |
| 规则 ID 与负责技能 | `knowhow-index.md`、各技能 `stage-contract.md` |
| 写前派生包、质量报告与连载义务校验 | `short-drama-write/references/writing-quality-loop.md`、`short-drama-develop/references/serial-obligation-ledger.md` |
| 仓库验证、清单和发布纪律 | `docs/maintenance.md` |
| 用户可见版本变化 | `docs/releases/release-notes.md` |

当摘要与权威正文冲突时，以表中权威来源和工具实际校验结果为准；不要在多个入口文档
各维护一份独立规则表。
