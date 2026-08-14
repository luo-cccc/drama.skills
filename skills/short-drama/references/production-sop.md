# 生产 SOP（批量生产执行纪律）

把真实生产里反复踩的坑固化为四条固定节奏。它们不改变任何命令语义，只规定**执行的
顺序与何时该做什么**，让批量的每一步都有确定的前置条件。

## 1. 第一集起就用记录级绑定（默认已自动）

`publish` 的 `--input-record-auto` 默认开启：候选输出里指向已声明 `--input` 文件的结构化
refs 会自动把 `record_id` 并入绑定，不需要手写。使用者的义务只剩两条：

- 结构化 refs 必须带 `record_id`（JSONL 用记录 ID、JSON 用 RFC 6901 指针），且指向的
  输入必须出现在 `--input` 里；
- 纯 Markdown 依赖仍必须显式 `--input`（工具不猜）。

效果：设定集追加一个新身份，只有真正引用它的产物可能 `stale`，前 47 集的绑定不受影响。

## 2. 临时候选目录的生命周期

`_*-candidates/*.candidate.*` 与 `输入/*.candidate.md` 是发布时被快照的源文件，
`accepted_inputs` 在 accept/review/package 阶段**仍会复验它们的 live hash**。纪律：

- **发布 → 接受 → 审查 → 打包完成前不要清理**任何候选源；清理 = 触发
  `accepted input hash does not match live file … (live <missing>)`。
- 建立固定节奏：一整批（一集或一个阶段）全部 accept/review/package 通过后再统一清理，
  且只清不再被任何 `accepted_inputs` 引用的文件（用 `status` 或脚本核对）。
- 误清后从 `.short-drama/accepted-snapshots/` 按 hash 恢复，而不是手改 state。

## 3. 拓扑规划后再批量发布

依赖必须无环且逐层推进：资产等级 → 模型/视图 → 标准片段 → 剧本 → 单集资产增量 →
图片提示词 → 分镜/关键帧 → 视频提示词。具体：

- 新增身份先并入**原有** artifact 的修订（`SEED:locations`/`SEED:props`），不要为每个
  身份发独立 artifact——否则共享文件被多个 artifact 声明，所有下游报
  `accepted input provider is ambiguous`；
- 剧本必须绑定实际消费的 generation 记录，但正文不复制视觉说明；候选剧本新增资产时，
  按身份播种 → 资产范围 → 模型/View → 标准片段 → 重发布并接受剧本的无环顺序推进；
- `episode-card.json#generation_asset_bindings` 为机器消费清单：每项显式列出
  `asset_id`、`model_id`、`view_ids`、`variant_ids`、`fragment_ids`；接受门禁逐项对照
  记录级输入，不允许重复 ID、多余 View 片段或未覆盖 View/variant，不再以“引用过四类文件”
  推断完整性；`view_ids` 是本集允许 View 集合，逐镜实际选择由 M4b 拥有；
- M3 若判断为 `new_asset` 或 `new_variant`，说明 M2 前置资产识别不完整，立即回退补齐
  M1.5a/M1.5b 并重新接受 M2；M3 不得创建或接受新的生成身份/变体基线；
- M3 的每个 occurrence 必须恰有一个 decision，identity/asset kind 必须一致，并显式写出
  M2 `generation_model_id` 与 `generation_variant_id`（可为 `null`）；continuity delta 的 after
  同样显式映射 generation variant；
- M4a 每条 `asset_board` 只绑定一个资产，覆盖 M2 每个资产的基线、全部 View 和 variant；
  M4b 每镜包含并对齐 Location generation 绑定及一张首关键帧；M5 每镜至少一条 `motion`，
  并由 `generation-clips.jsonl` 按项目单次模型时长上限完整覆盖，
  三阶段复用完全相同的 asset/model/variant/View/fragment ID+hash fingerprint；
- `accept-batch` 一次只推进已就绪的一层，依赖未就绪就反复运行直到全绿——这是预期行为，
  不是故障（已接受且目标一致的决定重跑记为 `skipped`，退出码 0，不污染输出）；
- **接受与重发布都按自底向上的依赖序**：一次上游 hash 变更（改决定记录、设定集、变体）
  会让所有引用它的候选在 accept 时报 `accepted input hash does not match live file`。
  处置是自底向上重发：先重发布引用旧 hash 的全部候选（`--input` 指向新 hash），再逐层
  `decide --force` 写 superseding 决定并 `accept-batch`——不要只改源头、不重发中间层。

## 4. base 与 delta 结论分离存放

- base verdict（fresh / cold_read 初审）**保留**，delta 结论另写新文件；
- 不要覆盖 base 成 delta——`delta_basis` 需要引用 base 文件的 `review_id` 与 hash；
- 修订产物命名带区分（如 `EP001-delta-…` vs `EP001-fresh-…`）；`review-batch` 按
  模式排序（delta → cold_read → fresh），文件名顺序不影响结果，但清晰命名便于人读。

## 附：错误恢复速查

| 报错 | 原因 | 处置 |
|---|---|---|
| `accepted input provider is ambiguous` | 共享文件被多个 artifact 声明 | `unpublish` 掉多余的 candidate，重新合并发布 |
| `accepted input hash does not match live file … (live <missing>)` | 候选源被清理 | 从 `.short-drama/accepted-snapshots/` 恢复，或 `unpublish` + 重发 |
| `record binding has no matching input` | 记录绑定缺整文件 hash | 补 `--input <path>=<hash>` |
| `BLK-PROMPT-COMPILE` | 下游自由改写提示词或 manifest 过期 | 从绑定和当前任务重新运行 `prompt_compile.py` |
| `BLK-FLOW-UPGRADE` | 旧 pipeline 尚未完成升级 | 接受 M1.5a/M1.5b 后运行 `upgrade-flow` |
| `verdict has invalid fields: …` | verdict 结构字段缺失 | 按聚合列表一次补齐后重试 |
| 依赖循环 | 脚本/资产互相绑定 | 移除多余的 `--input` 声明（只绑真正读了的） |
