---
name: short-drama
description: 仅在用户明确调用 $short-drama 时触发；未点名不得触发。管理文件系统短剧或漫剧项目的初始化、恢复、状态、路由、Dashboard 与交付；调用后缺少 short-drama.json 时只初始化，不自动调用子技能。
---

# 短剧项目路由

负责项目状态和跨阶段调度，不代替各阶段创作 owner。

## 显式调用门禁

先确认当前请求明确调用 `$short-drama`；否则立即停止，不读取项目、不执行命令。调用后从用户
指定路径或当前目录向上查找 `short-drama.json`。缺失时确认目标不是技能安装目录，再运行
`project_tool.py init <project> ...`；只完成初始化。不得自动加载未被当前请求明确点名的子技能。

## 快速入口

1. 每个项目会话首次运行：

   ```text
   python3 <core>/scripts/project_tool.py preflight <project>
   ```

2. 逐集生产再运行 `pipeline <project> [--episode EP001]`。
3. 不打开 `suite-manifest.json`。完整性由 `preflight` 验证。
4. 明确阶段后运行 `prepare --stage ...`，只把任务胶囊和列明的来源交给模型。
5. 编辑胶囊的 `work_path`，再运行 `finalize --packet ...`；需要发布时显式加
   `--publish --artifact-id <id>`。

命令报错或处理 Dashboard 时才读
[lifecycle-commands.md](references/lifecycle-commands.md)。首次理解跨阶段数据消费时读
[workflow-dataflow.md](references/workflow-dataflow.md)。`prepare` 不可用或需要人工速查时读
[execution-quickstart.md](references/execution-quickstart.md)。

只在对应问题出现时读：创作者决定与修订见
[creator-workflow.md](references/creator-workflow.md)，所有权/过期/隐私见
[contract-and-ownership.md](references/contract-and-ownership.md)，制作形态见
[production-form-profiles.md](references/production-form-profiles.md)，手工批量故障见
[production-sop.md](references/production-sop.md)，规则 owner 定位见
[knowhow-index.md](references/knowhow-index.md)。参考媒体、观众揭示和补拍边界分别见
[reference-roles.md](references/reference-roles.md)、[audience-reveal.md](references/audience-reveal.md)、
[pickup-and-alternate.md](references/pickup-and-alternate.md)；Look Development 决策见
[look-development.md](references/look-development.md)。

## 意图路由

以下路由表只在用户已显式调用本技能或表中对应技能时生效；不得根据请求语义自动加载表中技能。

| 请求 | 路由 |
|---|---|
| 长篇小说拆解、改编价值、分集候选 | `$short-drama-novel-analyze` |
| 点子、梗概、系列规划、已有多集完整剧本/散稿 | `$short-drama-develop` |
| 创建或修改单集卡、节拍、剧本 | `$short-drama-write` |
| 资产基线、人物场景道具、状态与连续性 | `$short-drama-assets` |
| 资产图、Look Development 图片提示词 | `$short-drama-image-prompts` |
| coverage、镜头、关键帧 | `$short-drama-storyboard` |
| 逐镜动作、表演、运镜、声音、generation clip | `$short-drama-video-prompts` |
| 只检查、诊断、出 finding 或 verdict | `$short-drama-review` |
| 定制作形态、视觉方向、交付面 | 本技能记录创作者决定 |

“先检查再修改”先进入 review，得到带证据 findings 后再交对应 owner；不要同时加载两份
完整技能正文。

## 固定流程

主线为：

```text
M0 → M1 → M1.5a → M1.5b → M2 → M3 → M4a → M4b → M5 → M6 → M7
```

- `script-first` 只能跳过 M1，不能跳过 M1.5。
- 单项请求只产出该项，不声称后续里程碑完成。
- 全链预览默认使用 candidate/provisional 链，一次展示关键创作者决定；确认后再按依赖接受。
- 批量生产读 [batch-production.md](references/batch-production.md)，把机械步骤和接受记录合并执行。
- 当前里程碑、阻断和唯一下一步以 `pipeline` 输出为准，不靠对话记忆推断。

完整流程门禁只在需要解释阻断时读
[production-pipeline.md](references/production-pipeline.md)。

## 审查与交付

- 类型首次审查、越界大改和交付终审使用 L1 fresh。
- 例行首审使用 scoped compact `review-bundle` 冷读。
- 已派发范围内的修订使用 `review-bundle --delta-from` 和 L2 `delta_verify`。
- 交付终审必须整集全量，不使用 compact/delta 代替。
- `package` 只收 accepted 且通过交付门的文本、JSON 与 JSONL。

## Dashboard

用户明确要求打开创作台时，按
[lifecycle-commands.md](references/lifecycle-commands.md#dashboard-启动) 启动并返回完整回环地址。
Dashboard 仅支持安全目录文件描述符可用的平台；Windows 使用 CLI。

## 边界

- 不生成或上传图片、视频、音频。
- 不手改 `.short-drama/**`、接受记录、审查状态或交付校验和。
- owner 不批准自己的产物。
- 运行时不读取外部私有来源，除非用户明确提供并授权。
