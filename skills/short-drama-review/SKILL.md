---
name: short-drama-review
description: 独立校验与审查文件系统短剧项目中的原著分析层、故事、剧本、资产、连续性、资产图片提示词、分镜、关键帧和视频提示词，并消费有界授权生产观察做当前项目校准。用户提出“审稿/检查剧本”“检查原著分析或分集候选”“检查资产或连续性”“检查图片/视频提示词”“审查或诊断模板感”“根据生产观察做项目校准”，或判断一集能否交付文本或 JSON 时使用；只发布审查问题、审查结论和修订要求，不代替负责人修改来源文件。
license: MIT
---

# 短剧独立审查

独立审查并引用产物证据。只写审查问题、审查结论和按负责人分组的修订要求；
不在同一次审查中替负责人修改创作来源，也不接受负责人自审。默认使用创作者语言；
中文项目的审查问题、影响和修订要求使用中文，稳定的规则编号和 ID 保持原样。

## 先定位套件

从本技能目录读取 `suite-ref.json`，按其中相对 `core_manifest` 定位唯一同级主技能与
套件清单；确认声明的 core、contract、recipe 和清单 hash 一致后再读写项目。
随后执行 [阶段契约](references/stage-contract.md) 的运行时预检：先恢复事务、读取状态，再进入本阶段。
该文件同时给出本阶段的所有权边界、需要从制作形态取得哪些输入，以及本阶段规则表；除核心套件元数据与执行速查（`execution-quickstart.md`）外，本技能不读取其他技能的文件。
例行命令速查见核心技能的 `references/execution-quickstart.md`；其余参考按需加载。

## 选择审查范围

声明一个或多个范围：

- `source_analysis`
- `story_script`
- `assets_continuity`
- `image_prompts`
- `storyboard_keyframes`
- `video_prompts`
- `full_episode`
- `delivery_privacy`
- `project_calibration`

只读对应的审查表。`source_analysis` 只读
[rubric-source-analysis.md](references/rubric-source-analysis.md)，审查索引、快评、逐章提取、
聚合、人物候选、改编价值和分集候选，不审剧本，也不替 `$short-drama-develop` 决定改编方案。
完整审查先读
[review-method.md](references/review-method.md)，再读三份审查表；制作端常见缺陷
与各环节判据见 [production-quality-gates.md](references/production-quality-gates.md)。
有创作者提供或授权形成的生产观察，需要绑定准确版本、诊断并路由项目内校准时读
[project-calibration.md](references/project-calibration.md)；没有观察记录时只报文字风险。
涉及参考图权限、遮挡式揭示或补拍版与替代版关系时加读
[阶段契约](references/stage-contract.md) 的参考媒体与补拍一节。
不预先加载所有创作资料。
证据来自项目产物和已接受限制，而非负责人的自我解释。
只有审查问题涉及“模板感、重复手法或 AI 味”时才读
[anti-template-repair.md](references/anti-template-repair.md)，用其诊断、修订示范与误报反例。

## 工作流

### 1. 先按分级确定审查方式

审查分三级，fresh agent 只花在必须独立判断的地方：

- **L1 全量审查（fresh reviewer agent/context）**：只在以下三个事件使用——
  ① 建立类型基准：本项目中该产物类型（剧本、资产、图片提示词、分镜/关键帧、
  视频提示词）的首次审查；② 交付打包前的终审；③ 上次结论后发生超出已派发
  修订范围的大改。
  启动时只传目标路径与 hash、已接受限制、当前范围需要的审查表和输出模板。
  不要传负责人的自检结论、预期答案或打算采用的修法。新审查者必须确认自己没有
  创作这些目标，重新读取当前字节后再判断。
  一个 fresh reviewer 会话可以一次覆盖同一目标集的多个范围（剧本、资产、提示词、
  分镜、视频提示词），不要按范围各起一个 agent。
- **L1.5 冷读审查（`cold_read`，不用 fresh agent）**：类型基准已建立后，例行
  首次审查默认走冷读。在当前上下文执行严格输入节食：只读 `review-bundle`
  证据文件、已接受限制、审查表与输出模板；不引用、不采信创作过程中的推理、
  自检结论或拟议修法——去锚定靠输入隔离，不靠角色扮演。冷读结论可以签发
  `APPROVE` / `APPROVE_WITH_NOTES` / `REVISE` 并推进阶段闸门，但审查者保持
  `independent:false`，绝不放开交付闸门。
- **L2 增量复核（`delta_verify`，不用 fresh agent）**：例行修订后的复查。
  前提是同一目标集已有一条非临时 base 结论（`fresh_agent` 或 `cold_read`，
  可以是 `REVISE`），且本次修订属于
  该结论派发的修订范围。复核在当前上下文完成：批准的合法性继承自 base 结论，
  复核动作本身只是对照 base 写下的"必须达到的修订结果"逐条核销证据，
  不是负责人自评。L2 中发现改动越出已派发范围、新增创作内容或 base 结论
  引用的目标集与本次不一致时，停止 L2，升级回 L1 fresh 审查。

### L1 派发契约（控制子 agent 成本）

fresh reviewer 是整条流水线里最贵的一步，成本几乎全部来自启动与重新阅读，不是哈希或
文件 IO。它只在上面三个 L1 事件触发；派发时把它的工作压到最小：

1. 先在本上下文跑完全部机械检查（结构校验、目标 hash 核对、时长/覆盖/容器算术、剧本
   索引、配音投影），再运行 `project_tool.py review-bundle` 把目标集打包成一份已验证的
   证据文件（逐记录/逐 block 提取、绑定输入解析、creator authority 与机械检查结果）；
   只把打包已通过或已列明问题之外的目标集交给 fresh agent。fresh agent 只做语义判断，
   不重复机械核账，也不需要翻找原始项目文件。
2. 用最小上下文启动：不携带本对话历史、负责人的自检结论或拟议修法；只传
   `review-bundle` 输出的文件路径与紧凑指针、已接受限制、审查表与输出模板的路径。
3. 同一目标集的多个范围合并进一个 fresh 会话，不按范围各起一个 agent。
4. 例行首审走 L1.5 冷读、例行修订复查走 L2 `delta_verify`，不重新派发；只有类型基准、
   越出派发范围的大改或交付终审才走 L1。

在结论中记录 `requested_review_mode` 与 `effective_review_mode`。只有运行环境实际提供 fresh
context，且审查者没有写过目标产物时，`effective_review_mode` 才能写 `fresh_agent`，并记录该
context 的运行时标识。冷读审查写 `requested_review_mode` / `effective_review_mode` 为
`cold_read`，审查者 `kind` 写 `cold_reader`、`independent:false`、`provenance:null`。
L2 复核写 `delta_verify`，并在 `delta_basis` 中引用 base 结论的
`review_id`、结论文件 ref 与 hash；base 可以是 `fresh_agent` 或 `cold_read` 的非临时结论；
复核者 `kind` 写 `delta_verifier`、`independent:false`、
`provenance:null`。若当前运行环境不能启动 agent、启动失败、上下文已经受创作过程污染，
或冷读输入节食无法维持，
可以做所有者自检和列问题，但必须写 `self_check` 或 `unattested`，保持 `independent:false`，
结论只能是 `PROVISIONAL`，不能签发 `APPROVE` / `APPROVE_WITH_NOTES`。

三个字段的命名映射（一处说清，避免 `fresh` / `independent` 两个词混用）：

- L1 fresh：`requested_review_mode: independent_agent` → `effective_review_mode: fresh_agent`
  → `reviewer.kind: independent_agent`（`independent:true`）；
- L1.5 冷读：三处分别写 `cold_read` / `cold_read` / `cold_reader`（`independent:false`）；
- L2 增量复核：三处分别写 `delta_verify` / `delta_verify` / `delta_verifier`（`independent:false`）；
- 无法独立时：`effective_review_mode` 写 `self_check` 或 `unattested`，`reviewer.kind` 同名，
  结论只能是 `PROVISIONAL`。

`review` verdict 必须带 `review_bundle_ref`；工具会重新哈希 bundle、核对完整目标集，并
重新运行适用的本地机械检查。`project_tool.py` 仍不能从 JSON 密码学证明
某个上下文真的 fresh 或真的执行了输入节食。实际隔离与节食必须由宿主和执行者建立；状态记录
按方式分别使用 `verification_scope: declared_provenance_structure`（fresh）或
`cold_read_structure`（冷读），不得把结构通过描述成运行时身份已验证。
对 `delta_verify` 结论，工具额外复验 base 结论确实是 `fresh_agent` 或 `cold_read`、
目标集一致、且 base 的
全部阻断问题在当前 findings 中已关闭或被取代；复验记录使用
`verification_scope: delta_closure_structure`。

### 2. 冻结审查目标

记录产物路径和 `hash`、创作者限制、审查范围与上游 `hash`。目标文件变化后，
旧审查问题变为 `stale`。状态为 `provisional` 或尚未接受的输入不能获得最终批准。

### 3. 先跑结构校验

先检查可证明事实：

- 数据结构、JSONL 和稳定 ID；
- 来源与资产引用；
- M1.5a 的分级接受、六类资产 full/compact 字段、空间拓扑和视图到模型记录哈希；
- M1.5b 的固定片段覆盖、语言、输入记录哈希和片段自身哈希；
- 图片规格、关键帧和运动规格的编译顺序、`asset_bindings`、manifest 与 `generic_prompt`；
- 原文落实情况；
- 准确资产版本，以及来源文字政策与本次呈现方法的对应关系；
- 明确时间段的总和；
- 生命周期与事务状态；
- 派生规格和配方的 `hash`；
- 负责人权限与隐私边界。

缺少前置资料而无法审查目标时，停止后续内容审查；其他互不依赖的结构问题可以一次汇总。

### 4. 带证据审查内容与创作方法

重新查看当前资料，不采用负责人的自我辩解。每个审查问题包含：

- 稳定的问题编号、做法编号、问题类别和检查方式；
- 准确的文件、记录、段落、镜头或提示词及其 `hash`；
- `target_ref` 以及来源端和使用端的 `evidence_refs[]`；
- 必要的短引文或冲突字段；
- 对观众理解或制作的影响；
- 必须达到的修订结果，而不是藏在审查问题里的代写稿；
- 负责技能、严重程度和状态。

校准 finding 还要区分 `input_reference` 与 `generated_result`，绑定准确 prompt/spec、参考槽位、
制作配置与观察限制，并给出 `change_set` / `preserve_set`；它只在该项目与版本条件下有效。

分类必须使用：

- `structural_invariant`：能够直接证明的结构错误；
- `reviewed_invariant`：证据成立时给出 `REVISE`；
- `craft_default`：说明影响的警告，可由创作者明确改写；
- `taste_option`：备选意见，不能单独阻断。

### 5. 跨层综合

优先守住剧本原意与连续性，而不是奖励华丽提示词。追踪：

```text
剧本事实 -> 资产决定 -> 镜头目的与边界
-> 冻结关键帧 -> 有序动作 -> 下一状态
```

造型版本错误、遗漏对白、改变动机、发明动作或破坏下一镜衔接时，提示词写得再详细也不能弥补。

### 6. 给出审查结论并分派修订

- `APPROVE`：没有阻断问题，常用做法符合已接受的创作意图；
- `APPROVE_WITH_NOTES`：没有阻断问题，只有可选改进；
- `REVISE`：存在结构错误、内容错误或违反已接受限制；
- `PROVISIONAL`：合规审查方式（fresh / 冷读）不可行，或缺少已接受的前置资料。

按故事开发、剧本、资产、图片提示词、分镜和视频提示词分组。负责人修改后列出所有
变为 `stale` 的下游产物，并审查新 `hash`；审查者不编辑来源文件。

L2 增量复核按以下顺序执行，全部满足才能签发 `APPROVE` / `APPROVE_WITH_NOTES`：

1. 冻结新 `hash`，确认目标集与 base 结论的 `reviewed_artifacts` 完全一致（路径相同、`hash` 为当前值）；
2. 逐条核销 base 结论的全部阻断问题：语义 diff 达到了 finding 要求的修订结果，
   `preserve_set` 保持完整，每条 finding 明确关闭、取代或保留；
3. 确认改动未越出已派发的修订范围、没有新增创作内容；越界即停止并升级 L1；
4. 重跑适用的结构校验（REV-09）；
5. 结论写 `requested_review_mode` / `effective_review_mode: delta_verify`，
   `delta_basis` 绑定 base 结论，复核者写 `kind: delta_verifier`、`independent:false`。

审查结论必须以结构化方式绑定准确的 `reviewed_artifacts`、当前 `findings_ref`、审查者
独立性和未关闭阻断问题数量。`findings_ref` 的 JSONL 中，每个未关闭的致命、错误或阻断
问题 ID 必须且只能出现一次，并与审查结论中的 `blocking_findings` 和数量完全一致。
隐藏未关闭问题、列入已关闭问题或引用不存在的 ID 都不能批准。没有这些证据时只能给
`PROVISIONAL`；一个状态字符串本身不能放行交付。模板故意以 `unattested` / `independent:false`
开始；fresh 审查者完成工作后才填写准确的运行时 provenance、被排除的负责人并改为
`independent:true`；冷读审查者填写 `kind: cold_reader` 并保持 `independent:false`，
其批准只推进阶段闸门、不放开交付闸门。L2 复核保持 `independent:false`，改为填写
`delta_basis` 绑定 base 结论（`fresh_agent` 或 `cold_read`）。
只写一个审查者名称或手改布尔值都不能证明独立性。

### 记录结论（review / review-batch）

结论文件必须声明 `artifact_id` 指明它审的是哪个产物（`review-batch` 据此路由），并在
`reviewed_artifacts` 中绑定准确的受审目标与 `hash`。单个产物用
`project_tool.py review` 记录（`--verdict-hash` 可省略，工具现算）；多份结论已经写在
磁盘上时用一次 `review-batch <project> --episode EP001` 按集全部应用——它逐条执行与
`review` 完全相同的校验（accepted targets、创作者接受证据、verdict 证据与 findings
对账），只应用**已经写下的结论**，不代替审查者下结论，任何一条失败整体退出非零。
例行 CLI 不需要手工 hash：target、verdict/evidence 文件的 hash 全部由工具从快照与
磁盘现算。写 verdict 文档时仍需提供内部引用 hash：`reviewed_artifacts[].hash`
（从 `review-bundle` 输出的 targets 抄写或从已接受快照取）、`review_bundle_ref.hash`
（直接使用 bundle 输出的 `bundle_hash`）与 `findings_ref.hash`（写结论前对 findings
文件现算——空 findings 是空文件 hash，非空必须先算）；这些值写错会在应用时被工具按
磁盘活 hash 复核拒绝。`pipeline --episode` 报告整集 M6 是否
全部 approve。结构字段校验**一次列出全部缺失/非法项**（`verdict has invalid fields:`），
修一轮即可跑通，不需要逐步猜错。

**例行审查的执行顺序（零子 agent）**：首审冷读（L1.5，只读 `review-bundle`）→ 一次
列全 findings → owner 一次改全 → `delta_verify` 反审（当前上下文）。fresh 子 agent 只
保留类型基准首审、越出派发范围的大改、交付终审三事件，且终审整集一次覆盖
（`review-bundle --episode` + 一个 fresh reviewer），不按产物类型各起一个。

## 审查表

- 故事承诺、因果、场景、行动、对白：
  [rubric-story-script.md](references/rubric-story-script.md)
- 资产身份/变体、连续性、资产图片提示词：
  [rubric-assets-prompts.md](references/rubric-assets-prompts.md)
- 原文落实、镜头、关键帧、视频提示词和跨镜状态：
  [rubric-visual-motion.md](references/rubric-visual-motion.md)

## 审查问题与严重程度

从 [finding-template.jsonl](assets/finding-template.jsonl) 建立审查问题，从
[verdict-template.json](assets/verdict-template.json) 建立审查结论。问题目录提供编号、类别、
默认检查方式、严重程度和负责人；审查问题记录本次目标的证据和状态。

- `fatal`：不安全或非公开内容被交付、事务损坏、缺少授权；
- `error`：阻断当前检查的结构或内容错误；
- `warning`：有具体影响的常用做法问题；
- `note`：创作选择、问题或不阻断交付的润色建议。

没有证据不要打分。不能只说“AI 味”；必须定位重复手法、用套话代替具体内容，或没有铺垫的文句模式，
并解释它伤害什么。

## 边界

- 不生成或查看已渲染媒体。
- 不从文字产物声称脸部一致、表演、口型、混音、剪辑或市场表现；只能引用授权文字观察中
  直接记录的现象，并保留其范围与限制。
- 不把非公开制作观察变成通用审查标准。
- 报告 `BLK-M15-SCOPE`、`BLK-M15-MODEL`、`BLK-M15-FRAGMENT`、
  `BLK-M2-ASSET-REF`、`BLK-PROMPT-COMPILE`，不替 owner 补写模型或片段。
- 审查问题只带创作者修订所需的必要证据；不泄露非公开输入、完整创作文本、
  网址或机器路径。
