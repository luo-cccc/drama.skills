---
name: short-drama
description: 基于文件系统初始化、继续、恢复和交付短剧或漫剧项目，并提供面向创作者的本地 Dashboard；也负责组织项目级 Look Development / 风格帧方向与授权生产观察校准。面向编剧、漫剧工作室与编导。用户提出“创建/继续短剧项目”“看进度/下一步”“做 Look Development”“用生产观察校准本项目”“打开 dashboard/短剧创作台”“恢复中断或不完整发布”“导出制作资料”，或任务跨多个环节、意图不明确而需要先判断当前状态与负责技能时使用；明确的写作、资产、提示词、分镜或审查请求由对应子 skill 直接处理。
license: MIT
---

# 短剧创作路由

这是轻量项目路由，不在本技能内代写故事、资产提示词、镜头、视频提示词或终审结论。
创作者可读的内容跟随项目 `short-drama.json#/language`（状态、差异、选择、下一步都算）；
送给图片/视频/语音生成器的提示词正文跟随 `#/format/prompt_language`（默认 `en`）。
两者是分开的字段，不要用其中一个推断另一个——完整规则见
[contract-and-ownership.md](references/contract-and-ownership.md) 的输出语言契约。

首次接触跨阶段项目、长篇输入或长镜头拆分时，先读
[workflow-dataflow.md](references/workflow-dataflow.md)；例行执行读
[execution-quickstart.md](references/execution-quickstart.md) 的命令速查；
只有命令报错、核对记录格式或首次任务时才读 creator-workflow.md 与 lifecycle-commands.md
全文。
多集、多阶段批量生产先读 [batch-production.md](references/batch-production.md)：
接受回合与机械步骤按批合并，创作生成本身不变。
批量执行的固定节奏（记录级绑定、候选目录生命周期、拓扑规划、base/delta 分离）见
[production-sop.md](references/production-sop.md)。
逐集生产按 [production-pipeline.md](references/production-pipeline.md) 的 pipeline 2.0 固定流程
执行，**主线逐级**：M0 → M1 → M1.5a → M1.5b → M2 → M3 → M4a → M4b → M5 → M6 → M7。
script-first 只能跳过 M1，不能跳过 M1.5；`pipeline` 命令给出当前位置、下一步与阻塞项。单分支请求仍可
直接进入对应技能，但不属于固定主线。

## 每次请求的起点

1. 使用用户明确路径，或从当前目录向上寻找最近的 `short-drama.json`。
2. 从本技能安装目录找到同一套件的其他技能，读取 `suite-manifest.json`；缺少技能或版本混用时先停止变更。
3. 只读 `short-drama.json` 与 `.short-drama/state.json` 摘要；不要一次加载全部创作文件。
4. 执行 `status` 或写入前先运行事务恢复。发现外部编辑冲突时保留原文件，提供
   `adopt`、`restore`、`merge` 三种处理，不静默覆盖。
5. 按创作者当前任务路由；不强制补走整条流水线。

入口、检查点、修订和交付见 [creator-workflow.md](references/creator-workflow.md)。
每次入口先执行 [runtime-preflight.md](references/runtime-preflight.md)，统一验证安装、恢复事务并读取项目状态；
同一会话内已通过的项目状态读取按其中的会话缓存规则复用；套件完整性校验始终对清单文件
全量重算 SHA-256，不依赖文件大小或 mtime。
所有权、文件过期标记 `stale`、隐私或恢复有疑问时读
[contract-and-ownership.md](references/contract-and-ownership.md)。
意图含混时读 [routing-examples.md](references/routing-examples.md)。
只在需要把规则 ID 定位到负责技能时读
[knowhow-index.md](references/knowhow-index.md)；路由只负责分派，不代替创作技能判断。
一张参考图可以决定什么、以及首尾帧契约见 [reference-roles.md](references/reference-roles.md)；
观众此刻可以知道什么见 [audience-reveal.md](references/audience-reveal.md)；
补拍与替代版和母版的关系见 [pickup-and-alternate.md](references/pickup-and-alternate.md)。
不同制作形态的执行翻译见 [production-form-profiles.md](references/production-form-profiles.md)。
需要在正式分镜前用人物、地点和高压力代表帧统一视觉语言时读
[look-development.md](references/look-development.md)。

## 意图路由

| 创作者意图 | 路由 |
|---|---|
| 开发点子、故事承诺、系列、分集地图 | `$short-drama-develop` |
| 已有多集完整剧本/散稿，要生成或补充分集地图 | `$short-drama-develop`：建立精确索引，逐集切片，按磁盘状态断点续跑 |
| 判断一本长篇值不值得全量拆解 | `$short-drama-novel-analyze`：建立章节索引并做可复现抽样快评 |
| 导入小说/长材料并做可追溯分集与资产候选预览 | `$short-drama-novel-analyze` → `$short-drama-develop` → 接受改编/分集 → `$short-drama-assets` 设定播种 → `$short-drama-write` → 接受剧本 → `$short-drama-assets` 单集拆解 |
| 设定播种：先把角色/地点/关键道具定下来再写 | `$short-drama-assets` 播种模式：从已接受 develop 产物或创作者直接描述写设定集身份层 proposed 记录，创作者确认后批量接受 |
| 建立可稳定生成的角色/生物/场景/道具/载具/效果资产层 | `$short-drama-assets` 建立并接受 M1.5a 范围、模型、空间拓扑、变体和视图 → `$short-drama-image-prompts` 建立并接受 M1.5b 标准片段 |
| 写/改单集契约、因果节拍、剧本 | `$short-drama-write`（写作前读取设定集作为演员表与世界观约束；新元素标记待播种，由 `$short-drama-assets` 从 candidate 剧本做候选播种，确认后按身份播种 → M1.5a → M1.5b → 重发布并接受 M2 推进） |
| 拆人物/造型、地点/视图、道具/状态 | `$short-drama-assets` |
| 写人物/地点/道具/局部修改的图片提示词 | `$short-drama-image-prompts` |
| 做原文覆盖、镜头或冻结关键帧 | `$short-drama-storyboard` |
| 写动作/表演/运镜/声音视频提示词 | `$short-drama-video-prompts` |
| 定画风、制作形态或视觉方向 | `$short-drama` 本身：按 [production-form-profiles.md](references/production-form-profiles.md) 定位一张形态卡，产出候选并请创作者接受，再提升到 `creator_authority`。资产、图片提示词与分镜要求形态已定；视频提示词在输入镜头/关键帧已编码形态时允许 `unset` 并保持产物 provisional。各环节都不自行选择，所以定形态这一步必须在这里完成 |
| 做 Look Development / 风格帧 | `$short-drama` 先明确并接受可观察视觉方向 → `$short-drama-image-prompts` 写 `lookdev_frame` 文本规格；不生成图片，也不让风格参考接管身份、地理或剧情状态 |
| 用授权生产观察校准本项目 | `$short-drama-review` 绑定准确版本并诊断 → 对应 owner 做有 `preserve_set` 的定点修订 → 重新接受与 `delta_verify` 增量复核（大改或交付前回到 fresh 审查）；没有授权观察时只报文字风险 |
| 校验、审查或发修订请求 | `$short-drama-review` |
| 只检查或诊断模板感、AI 味 | 冷读（类型基准未立时 fresh）`$short-drama-review`，只发带证据 finding |
| 直接去 AI 味、润色或定点改稿 | `$short-drama-write`，保留作者声音并展示语义差异 |
| 先检查再改 | fresh/cold_read 审查 → write owner 定点修订 → `delta_verify` 增量复核（越出派发范围、新增创作内容或交付前回到 fresh re-review） |
| 打开 Dashboard、短剧创作台或管理创作内容 | `$short-drama dashboard`：执行下方“本地 Dashboard”启动契约 |

创作者明确意图优先于名义上的“下一检查点”。Look Development 是可选的项目级分支，不是通用前置。
明确的单项任务可以直接调用图片提示词或分镜技能，但只产出该单项结果，不改变固定主线状态，也不得声称
后续里程碑已经完成。走 [production-pipeline.md](references/production-pipeline.md) 的 pipeline 2.0 项目必须
M1.5 → M2 → M3 → M4a → M4b → M5 严格串行，M4a 与 M4b 不是平行里程碑，不提供分支跳过。

审查分三级：L1 全量审查要求 fresh reviewer agent/context；L1.5 冷读审查（`cold_read`）
在当前上下文按严格输入节食完成；L2 增量复核（`delta_verify`）在当前上下文对照 base
结论逐条核销。L1 只用于三个事件：项目中该产物类型的首次审查（建立类型基准）、
交付终审、越出派发范围的大改；类型基准已建立后的例行首审默认 L1.5 冷读；
例行修订后的复查默认 L2。L1 路由时只传目标、已接受限制和审查表，一个 fresh 会话可覆盖
同一目标集的多个范围；冷读只读 `review-bundle` 证据、已接受限制与审查表，不引用创作
过程推理。运行环境不支持 fresh agent 时透明降级为 `PROVISIONAL`
自检，不能把切换 Skill 名称当成独立审查。

例行执行不派子 agent：首审冷读 → REVISE 一次改全 → delta_verify 反审，全程当前上下文；
fresh 只用于上面三个 L1 事件且整集一次覆盖（`review-bundle --episode` + 一个 fresh
reviewer），不按产物类型各起一个。`accept`/`review` 的 target 与证据/结论 hash 全部可
省略，由工具从快照与磁盘现算；写 verdict 时其内部 `findings_ref.hash` 仍需对 findings
文件现算，`review_bundle_ref.hash` 直接使用 `review-bundle` 输出的 `bundle_hash`。

“像不像模板/AI 写的”是诊断请求；“把它改掉”是 owner 修订请求。不要让 write owner
先自诊断再给自己签发结论，也不要让 reviewer 越权直接改正文。组合请求先冻结目标版本，
由 fresh reviewer（类型基准未立时）或冷读审查（基准已立时）定位证据和损失，再交 write
owner 只改被接受的范围，然后对新 hash 做
`delta_verify` 增量复核：逐条核销 base 结论的阻断问题即可签发批准，无需再换审查
上下文；复核中发现越界改动或进入交付终审时回到 fresh re-review；
任何无法取得独立上下文的 L1 环节都保持 `PROVISIONAL`。

## 初始化

没有项目且用户要初始化时：

1. 仅确认或合理推断可逆格式默认值：标题、语言、提示词语言、画幅、路径；集数/时长未知
   就留空。语言默认取创作者当前使用的语言，提示词语言默认 `en`；创作者明确要求提示词
   也用项目语言时按创作者的，不代为判断质量后果。
2. 复制项目模板，不覆盖已有创作者文件。
3. 建立空阶段目录和非公开输入边界。
4. 在 `short-drama.json#/creator_authority` 建立空的创作者限制、视觉方向和制作配置；
   它们初始为 `unset`，而资产、图片提示词与分镜都要求形态已定——所以初始化后要告知创作者：
   **定制作形态 + 设定播种是接下来最有用的两个动作**：形态入口在本技能（见意图路由表），
   播种入口在 `$short-drama-assets`（从 develop 产物或创作者描述写设定集身份层记录）；
   形态的实际选择写入 [creator-decision.example.jsonl](assets/creator-decision.example.jsonl)
   所示的决定记录。
5. 记录套件版本、契约版本与五项彼此独立的空状态。
6. 告知项目路径和最有用的创作者动作。

初始化不生成故事引擎、剧本或资产设定表。

开发阶段若提交 `项目开发/director-brief.md`，先向创作者展示其相对当前
`visual_direction` / `production_profile` 的语义差异；只有明确接受后，路由才把相应选择
提升到 `short-drama.json#/creator_authority`。候选文件本身不具有 creator authority。

## 本地 Dashboard

当用户调用 `$short-drama dashboard` 时，不再转交子技能，直接启动本技能自带的
本地短剧创作台：

1. 先按 [runtime-preflight.md](references/runtime-preflight.md) 核对套件并恢复未完事务。
2. 工作目录位于某个项目内时，以该项目根为 `workspace`；否则使用用户明确
   给出的容器目录，未给出则使用当前目录。不扫描 workspace 之外。
3. 从本技能安装目录运行：

   ```text
   python3 <short-drama-skill-dir>/scripts/dashboard_server.py --workspace <workspace> --port 0 --open
   ```

4. 保持进程运行，回报脚本打印的完整回环地址（包含本次启动的会话片段）和停止方式。
   浏览器无法自动打开时，保留服务并让用户打开该完整地址。

Dashboard 只有一个创作页面：左侧是按项目与剧集整理的通俗内容目录，右侧是常驻正文；
打开项目后自动载入剧本，切换内容只替换正文，不打开新页面或浮层。待办与导出只作为
正文下方的简短提示。界面不显示文件树、真实路径、结构化格式、生命周期或工程详情入口。
Markdown 作为文稿阅读和编辑；结构化数据转换为卡片；图片和视频只预览。
`short-drama.json`、`.short-drama/**`、创作者决定、检查证据和导出校验均由系统维护，
不成为创作者导航。保存只表示保存修改，不能替代创作者明确采用某个版本。
它不连接外部数据源、不调用媒体生成接口，也不向浏览器注入密钥。
每次启动生成独立会话凭证和 API 路径；浏览器用地址片段换取 `HttpOnly` 本机会话，
项目 API 仅接受该会话。
具体参数见 [lifecycle-commands.md](references/lifecycle-commands.md#dashboard-启动)。

**平台限制**：创作台要求 POSIX 安全目录文件描述符（macOS/Linux）；在不支持的平台上
（含 Windows）`dashboard_server.py` 会直接拒绝启动。此时不要反复重试或寻找降级开关，
改用对话 + `project_tool.py` CLI 工作流：所有项目文件都在磁盘上，播种、写作、拆解、
审查与打包的全部能力都不依赖创作台。

## 确定性工具

从本技能安装目录调用 `scripts/project_tool.py`，不依赖当前工作目录：

| 命令 | 用途 |
|---|---|
| `init` | 初始化最小项目 |
| `status` | 读取生命周期与恢复摘要 |
| `preflight` | 单进程入口：套件校验 + 事务恢复 + 状态摘要一次完成 |
| `pipeline` | 报告固定生产流程（含 M1.5a/M1.5b）当前位置、下一步与阻塞项 |
| `upgrade-flow` | 旧项目完成并接受 M1.5 后升级到 pipeline 2.0 |
| `recover` | 恢复全部或指定事务 |
| `publish` | 通过预写日志发布 `candidate`，不附带接受或审查结论 |
| `accept` | 用创作者决定记录接受准确的 `candidate` 目标（`--target` 可省略 hash，从候选快照解析） |
| `decide` | 从候选快照生成一份合规的创作者接受决定文件，供 `accept-batch` 应用 |
| `unpublish` | 撤销发布但未接受的 artifact 记录（修正发布方向错误；已接受产物受保护） |
| `accept-batch` | 一次应用磁盘上全部已记录的创作者接受决定，供整批生产使用 |
| `review` | 用审查结论（fresh / 冷读 / 增量复核）更新校验与审查状态 |
| `review-bundle` | 把目标集打包成已验证的审查证据文件，供 L1 fresh reviewer 或冷读审查只读一份文件 |
| `review-batch` | 一次应用磁盘上全部已写入的审查结论（verdict JSON），`--episode` 限定单集，供整批生产使用 |
| `package` | 复验五轴、依赖和证据后生成文本交付包 |
| `verify` | 用交付包自带的校验和复核它，并报告未登记的新增文件 |

只有实际调用这些命令、诊断失败或核对记录格式时，才读取
[lifecycle-commands.md](references/lifecycle-commands.md) 中的完整调用示例、预写日志、接受、
审查、下游过期影响与打包约束。

## 状态与下一步

用创作者语言说明：

- 已存在且状态为 `accepted` 的来源；
- 各轴上的未完成内容：`independent_review` 为 `provisional`、`build_state` 为 `stale`、
  `delivery_gate` 为 `blocked`，或 `creator_acceptance` 待创作者接受；
- 当前可并行进入的分支；
- 推动用户所求结果的最小动作。

当 `visual_direction` 或 `production_profile` 为 `unset`，而项目即将进入资产、图片提示词、
分镜或视频提示词环节时，必须提前说明：**形态未定，资产、图片提示词与分镜会停摆**
（视频提示词在输入镜头/关键帧已编码形态时可继续，但产物保持 `provisional`、不声称已接受
形态约束），并给出定形态的最小动作；不要等创作者写到那一步才撞墙。

除非用户要求诊断，不打印 `hash`、事务 ID、内部数据结构或原始状态内容。
五项状态彼此独立：构建、校验、创作者接受、独立审查和交付检查；不得用一个
`accepted` 冒充全部。

## 恢复与修订

恢复用户所问环节内最早未完成的操作，而不是全项目最早阶段。变更已确认内容前：

1. 指明负责修改的技能；
2. 展示拟议的语义变化；
3. 列出准确的下游受影响清单；
4. 在需要时取得创作者接受；
5. 交给负责人修改，并对新 `hash` 重新审查（例行修订走 `delta_verify` 增量复核，越界或交付前回到 fresh 审查）。

没有 `COMMIT` 的不完整事务回滚到已保存的上一版本；已有 `COMMIT` 的不完整事务继续到
`candidate` 并补齐状态。恢复必须先读后写、可重复运行；无法确认来源的外部改动必须标为
`conflict`，不能覆盖。

## 交付

交付前必须经过 `$short-drama-review` 的 L1 fresh 审查上下文终审（`delta_verify` 或 `cold_read` 结论不能替代交付终审），再在交付检查就绪时打包。只包含状态为 `accepted`
的剧本、清单、提示词、审查、创作者备注、实际消费的 `asset-baseline-bundle.json` 与校验和。排除二进制媒体、非公开输入、
机器状态、绝对路径、凭据、非公开来源材料和未批准草稿。

## 边界

- 只使用当前智能体的文本推理；不调用媒体生成或服务接口。
- 运行时不检索外部或非公开生产来源。
- 不把别处见过的案例提升为创作定律。
- 负责人不能审查自己的产物。
- 语义冲突不静默修复。
