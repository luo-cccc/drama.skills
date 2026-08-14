# 短剧套件执行速查（模型侧例行任务用）

例行任务优先使用 `prepare` 生成的任务胶囊，不默认读取本页。只有 `prepare` 不可用、
命令报错或需要人工核对命令形态时才读本页；不要让模型打开 `suite-manifest.json`。

第一次处理长篇输入、跨阶段消费链或长镜头拆分时，先读
[workflow-dataflow.md](workflow-dataflow.md)；它解释内容如何从输入流到交付，本页只负责操作。

## 入口（每次会话一次）

```text
python3 <core>/scripts/project_tool.py preflight <project>
```

- 退出码 0 可继续；2 套件校验失败；3 有阻塞事务需先处理。
- 套件校验每次对清单文件全量重算 SHA-256；日常入口不需要单独跑 `suite_verify.py`，
  需要查看明细时可使用 `--full` / `--no-cache`（两者均保持全量校验）。
- 需要诊断细节时才分别跑 `recover` / `status`；没有待恢复事务时 `recover` 是空操作。
- 逐集生产先跑 `pipeline <project>`：固定流程（含 M1.5a/M1.5b）的当前位置、下一步与阻塞项见
  `production-pipeline.md`；strict 模式下有阻塞项退出码 3。

## 模型任务胶囊

```text
python3 <core>/scripts/project_tool.py prepare <project> --stage write --episode EP001 --intent create
python3 <core>/scripts/project_tool.py finalize <project> --packet .short-drama/work/task-packets/<TASK>.json
```

- `prepare` 只读取项目状态和精确生命周期来源，生成不进入交付包的私有工作胶囊与骨架。
- 模型先读胶囊，只编辑其中的 `work_path`，参考文件继续按需加载。
- 项目、状态或来源 hash 变化后，`finalize` 拒绝旧胶囊。
- `finalize --publish --artifact-id <id>` 才发布 candidate；不带 `--publish` 只编译和校验。

## 命令速查

| 命令 | 常用形态 | 说明 |
|---|---|---|
| `init` | `init <project> --title ... [--language zh-CN] [--prompt-language en] [--aspect-ratio 9:16] [--max-clip-seconds 15]` | 初始化，不生成创作内容；语言与画幅各自独立；`--max-clip-seconds` 设置单次视频模型调用上限，默认 15 秒，不改变影视镜头边界 |
| `upgrade-flow` | `upgrade-flow <project>` | 旧项目完成并接受 M1.5a/M1.5b 后切换到 pipeline 2.0；升级前 M2–M7 阻断 |
| `publish` | `publish <project> --owner <技能> --artifact-id <id> --output 目标=来源 [--input 依赖=hash] [--input-record 文件=记录ID]` | 发布 candidate；来源可位于工作区或已是目标文件，目标与来源相同时不会把自身登记为输入 |
| `accept` | `accept <project> --artifact-id <id> --decision accepted [--target 路径[=hash]] --evidence-artifact 创作者决策/<净化id>.json [--evidence-hash <hash>] [--evidence-record-id <id>]` | 创作者接受；`--target` 与 `--evidence-hash` 都可省（工具从快照/磁盘现算，仍逐 hash 核对）。文件名用净化后的 artifact id（冒号→连字符：`EP001:script` → `EP001-script.json`；Windows 不允许冒号） |
| `decide` | `decide <project> --artifact-id <id> --decision accepted [--force] [--decided-by <role:id> --delegation-artifact <path>]` | 从候选快照生成合规决定文件；默认直接由 creator 决定，委托必须绑定 creator delegation evidence；不代替创作者做决定 |
| `accept-batch` | `accept-batch <project> [--decisions-dir 创作者决策]` | 一次应用磁盘上全部已记录的接受决定；幂等——已接受且目标一致的决定记为 `skipped`（退出码 0），不是失败；整批生产用 |
| `review-bundle` | `review-bundle <project> --episode EP001 [--scope 范围] [--compact] [--delta-from 旧verdict]` | 按整集或范围打包证据；例行冷读可 compact，修订复核可只含变化目标，交付终审使用完整整集 |
| `review` | `review <project> --artifact-id <id> --verdict ... [--target 路径[=hash]] --verdict-owner short-drama-review --verdict-artifact ... [--verdict-hash ...]` | 记录审查结论（fresh / 冷读 / 增量复核） |
| `review-batch` | `review-batch <project> [--verdicts-dir 审查] [--episode EP001]` | 一次应用磁盘上全部已写入的审查结论；`--episode` 限定单集，verdict 文件须含 `artifact_id` |
| `package` | `package <project> --episode EP001 --include 路径... [--omit 路径 --omission-evidence 决定文件]` | 交付打包；要求 M2–M6 完成并先过 L1 fresh 终审；省略项必须有 creator evidence，且 delivery_surface 已接受 |
| `verify` | `verify <project> --episode EP001` | 复核交付包校验和 |

## 已知坑位速查

从真实项目跑下来的高频坑位，先在这里对答案，再翻大文档：

- **路径按可移植身份去重**：同一命令或事务中不能同时出现 `Foo.md` / `foo.md`、
  `a/b.md` / `a\b.md`，也不能使用 NFC 组合前后等价的两个 Unicode 路径。即使当前
  Linux 文件系统能区分，工具也会在写 WAL 前拒绝，保证项目可移动到 Windows/macOS。
- **路径分量必须能跨平台创建**：不能使用 Windows 保留设备名、`< > : " | ? *`、
  控制字符或以空格/句点结尾的名称。
- **JSON 必须是标准 JSON**：所有 `.json` / `.jsonl` 输入都拒绝 `NaN`、`Infinity`、
  `-Infinity`。时长、合计和 delta 使用普通有限数字；未定值写 `null`，不要使用非标准常量。
- **发布源文件保留到打包完成**：`publish --output 目标=来源` 的接受校验按来源路径现算
  hash，接受/审查/打包**都会复验它**——接受前删除源文件会让 `accept-batch` 报
  `accepted input hash does not match live file: <源路径> (…, live <missing>)`，接受后
  删除也会让后续 `review` / `package` 复验失败。临时源统一放 `_seed_candidates/` 这类
  自建快照目录，**整个 batch 全部 accept/review/package 完成后再统一清理**（被
  `accepted_inputs` 引用的文件都不能删）。
- **accept-batch 幂等**：已接受且目标一致的决定重跑记为 `skipped`（退出码 0），不再报
  假失败。依赖未就绪的层仍然失败——按依赖序自底向上分轮跑，用
  `state.json#/artifacts/*/creator_acceptance` 做最终判据，不看 batch 输出。
- **Markdown 输入用 `--no-input-record-auto`**：`source_refs` 指向 `.md` 等文本输入时，
  自动记录级绑定报 `record-level input binding needs a .json or .jsonl input`；凡混合
  Markdown 输入一律显式 `--no-input-record-auto`（整文件绑定）。
- **改版后 `decide --force`**：重新发布引用旧决定文件的候选后，旧决定文件存在会让
  `decide` 报 `decision file already exists`；加 `--force` 覆盖，旧 `decision_id` 记入
  `supersedes_decision_id`。已接受产物仍被拒绝（不再有 candidate targets）。
- **每次修订剧本后重建 index**：任务胶囊流程由 `finalize` 自动重建 candidate index。
  只有绕过任务胶囊直接 `publish` 时，才手工运行 `screenplay_index.py --previous-index
  --previous-source`；旧 index 会导致警告并让下游 block 绑定失效。
- **时长预算提前看**：`target_seconds_per_episode` 的唯一正式兑现点在 M4b 分镜
  （SHT-16），但剧本密度不足不必等到那一步——`publish` 剧本时会报
  `estimated on-screen time ... below target_seconds_per_episode` 警告，
  `pipeline <project>` 会为每集报告 `duration_estimate`（target/estimated/delta）。
  发现负差值回写作层补密度，不要在分镜层凑时长。
- **长 shot 不等于超限调用**：M4b 保留真实剪辑边界，M5 用连续的
  `generation-clips.jsonl` 覆盖该 shot，每段不超过项目 `max_clip_seconds`。后续段必须携带
  五项 planned boundary；使用 `continuation` 时还要得到项目支持并绑定上一段的
  `output_observation_ref`。不要人工把一个 shot 偷改成多个镜头来规避模型上限。

## 各阶段最小产物与机械检查

| 阶段 | 技能 | 产出 | 机械检查 |
|---|---|---|---|
| 原著分析（可选） | `short-drama-novel-analyze` | `项目开发/source-analysis/*` | `novel_index.py verify`、`sample`、`coverage` |
| 开发 | `short-drama-develop` | `项目开发/creative-brief.md`、`story-engine.md`、`episode-map.jsonl` | 连续项目运行 `episode_map_check.py --story-engine` |
| 写作 | `short-drama-write` | `剧集/EP001/episode-card.json`、`beats.jsonl`、`screenplay.md`、`screenplay-index.jsonl` | `screenplay_index.py`；新写/续写/大修运行 `writer_quality.py`；有配音本时 `voice_sheet_check.py` |
| 资产 | `short-drama-assets` | `设定集/*.jsonl`、`剧集/EP001/assets/*.jsonl` | — |
| 图片提示词 | `short-drama-image-prompts` | `剧集/EP001/assets/image-prompt-specs.jsonl`、`image-prompts.md` | — |
| 分镜 | `short-drama-storyboard` | `剧集/EP001/storyboard/coverage.json`、`shots.jsonl`、`keyframes.jsonl`、`keyframe-prompts.md` | `storyboard_check.py` |
| 视频提示词 | `short-drama-video-prompts` | `剧集/EP001/storyboard/{motion-specs,generation-clips,delivery-containers}.jsonl`、`video-prompts.md` | `motion_timing_check.py`、`generation_clip_check.py`、`container_check.py` |
| 审查 | `short-drama-review` | `审查/<id>-findings.jsonl`、`审查/<id>-verdict.json` | 先 `review-bundle` 打包 |

## 接受与审查纪律（不可跳过）

- 每个阶段的 candidate 必须先经创作者接受（`accept`），才能作为下游来源。
- 例行首审走 L1.5 冷读（`cold_read`），例行修订复查走 L2 `delta_verify`；只有类型基准
  （该项目该产物类型的首次审查）、越出派发范围的大改、交付终审才派 L1 fresh reviewer
  （派发前先 `review-bundle`，冷读同样只读 bundle）。
- 交付前必须完成 M2–M5 并让 M6 全部通过 L1 fresh 终审，再 `package`；`package` 会复核整条
  固定流程，只收 accepted 文件，不能用省略清单把尚未生产的阶段伪装成交付完成。
- 创作者要求全链预览时，用 candidate 预览链一次展示（下游标 `provisional` /
  `authority: candidate`），避免逐阶段等待接受回合。
- 整批生产（多集/多阶段）先读 `batch-production.md`，把接受回合和机械步骤合并执行。

## 何时才读完整参考

- 命令报错或行为不符 → `lifecycle-commands.md`
- 所有权、过期、隐私或恢复疑问 → `contract-and-ownership.md`（或本技能的 `stage-contract.md`）
- 首次做某类产物或需要完整方法 → 对应技能 `SKILL.md` 的按需加载表
- 多集批量生产 → `batch-production.md`
- 跨阶段输入、输出、消费、失效或长镜头拆分 → `workflow-dataflow.md`
- 长篇原著分析 → `short-drama-novel-analyze/SKILL.md`
- 多集整稿断点接入 → `short-drama-develop/references/multi-episode-intake.md`
- 其余例行任务不需要读上述大文件。
