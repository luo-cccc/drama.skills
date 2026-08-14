# 创作者工作流

本页只说明创作者决定、预览、修订和交付边界。里程碑顺序以
[production-pipeline.md](production-pipeline.md) 为准，命令参数以
[lifecycle-commands.md](lifecycle-commands.md) 为准，文件所有权以
[contract-and-ownership.md](contract-and-ownership.md) 为准。

## 创作者权威

`short-drama.json#/creator_authority` 保存已接受的创作者限制、视觉方向、制作形态和交付面。
`创作者决策/<artifact-id>.json` 保存针对准确 candidate hash 的接受、拒绝、委托或省略决定。
不要从对话记忆、提示词缓存或 owner 自述恢复这些事实。

`decided_by` 只允许：

- `creator`：项目创作者直接承担决定后果；
- `<role>:<stable-id>`：创作者以已接受 delegation 决定授权的稳定委托身份。

技能名、agent、owner 或 reviewer 都不能作为决定者。委托决定必须精确限制可执行操作和
artifact 范围；创作者可以撤销委托决定，委托人不能反向覆盖创作者决定。

同一批候选可以向创作者合并展示，一次确认后再逐 artifact 写决定并运行 `accept-batch`。
展示层可以合并，证据层仍保持每个 artifact 的准确 target hash。

## 入口与里程碑

按创作者实际任务路由，不要求为了形式补造上游文件：

| 创作者任务 | Owner | 固定流程位置 |
|---|---|---|
| 定视觉方向、制作形态、交付面 | `short-drama` | M0 |
| 原著分析 | `short-drama-novel-analyze` | M0 前的可选来源分析 |
| 故事开发与分集地图 | `short-drama-develop` | M1 |
| 生成资产模型与视图 | `short-drama-assets` | M1.5a |
| 标准提示片段 | `short-drama-image-prompts` | M1.5b |
| 单集卡、节拍、剧本 | `short-drama-write` | M2 |
| 单集资产出现、复用决定和连续性 | `short-drama-assets` | M3 |
| 单集资产图提示词 | `short-drama-image-prompts` | M4a |
| coverage、镜头与关键帧 | `short-drama-storyboard` | M4b |
| motion、generation clip 与视频提示词 | `short-drama-video-prompts` | M5 |
| 独立审查 | `short-drama-review` | M6 |
| 文本/JSON 交付包 | `short-drama` | M7 |

固定主线是 `M0 → M1 → M1.5a → M1.5b → M2 → M3 → M4a → M4b → M5 → M6 → M7`。
`script-first` 只跳过 M1。明确的单项请求可以直入对应 owner，但不会推进未完成的主线里程碑。

每个里程碑同时保留五个独立状态：build、structural validation、creator acceptance、
independent review、delivery gate。任何一个 `accepted` 都不能代替其余四项。

## 任务执行

1. 会话首次运行 core `preflight`，再用 `pipeline` 读取当前位置和阻断项。
2. 对明确阶段运行 `prepare`，只读取任务胶囊列出的来源和按需参考。
3. 只编辑胶囊的 `work_path`，运行 `finalize` 生成派生产物并执行机械校验。
4. 需要形成生命周期 candidate 时显式使用 `finalize --publish --artifact-id <id>`。
5. 向创作者展示语义变化与影响范围；确认后写决定并接受准确 candidate。
6. 下游只消费已接受来源；例行审查使用 scoped bundle，交付终审使用整集 full bundle。

创作者带入现成剧本时，原始字节保存在 `输入/`，owner 只创建规范化候选和语义差异。
不为了满足 pipeline 伪造开发记录；采用 `script-first` 后仍须完成 M1.5a/M1.5b。

## 无法即时接受时的全链预览

“把完整流程先做出来”授权起草，不等于接受所有故事、资产、镜头和提示词决定。无法逐阶段
取得确认时，只建立 provisional preview chain：

- 下游可以绑定同一预览链中的准确 candidate hash，并标记 `authority: candidate`；
- creator acceptance 保持 pending，independent review 保持 provisional，delivery 保持 blocked；
- 未解决的身份、剧情含义或信息权限仍阻断相关分支；
- 不生成虚假的 creator decision，不把 candidate 写成 accepted；
- 创作者确认后按依赖顺序接受上游，并刷新下游引用后再接受。

## 修订

1. 确认准确 artifact、owner 和当前 hash。
2. 只读取该 owner 的必要 craft 参考和直接上游事实。
3. 展示语义 diff、保留项和下游 stale 范围。
4. owner 在新的任务胶囊中定点修改，重新 `finalize` 并发布。
5. 创作者一次确认修订；例行复核用 `delta_verify`，越界大改或交付终审回到 fresh review。
6. 外部编辑与生命周期快照冲突时提供 adopt、restore、merge，不静默覆盖。

结构化规格是权威，编译出的 prompt Markdown 是缓存。创作者直接编辑缓存时：

- `restore`：从当前结构化规格重新生成；
- `adopt`：把文本变化解析为规格候选并请求接受；
- `merge`：把两边差异合并为新的结构化候选。

## 产品与交付边界

- 只使用文本推理创建和修改项目文件，不调用图片、视频或音频生成服务。
- 不要求外部私有数据库或旧平台 schema 才能完成项目。
- owner 不批准自己的产物，reviewer 不修改 owner 来源。
- M7 只交付已接受并通过 fresh 终审的文本、JSON、JSONL 与校验文件。
- 排除原始私有材料、绝对路径、凭据、事务状态、维护证据和二进制媒体。
