# 项目命令与审核记录

## 目录

1. 初始化与 Dashboard
2. 发布与创作者确认
3. 独立审查记录
4. 过期影响与依赖检查（含把共享文件的失效半径收窄到记录）
5. 恢复与打包（含交付完整性枚举与交付后复核）

只在实际调用 `project_tool.py`、诊断命令失败或核对审核记录时读取本文。
从 `short-drama` 技能安装目录调用脚本，不依赖当前工作目录：

```text
python3 <short-drama-skill-dir>/scripts/project_tool.py init <project> --title <title> [--language <zh-CN|...>] [--prompt-language <en|...>] [--aspect-ratio 9:16] [--max-clip-seconds 15]
python3 <short-drama-skill-dir>/scripts/project_tool.py status <project>
python3 <short-drama-skill-dir>/scripts/project_tool.py recover <project>
python3 <short-drama-skill-dir>/scripts/project_tool.py publish <project> --owner short-drama-write --artifact-id EP001:script --output 剧集/EP001/screenplay.md=输入/EP001-screenplay.candidate.md [--input <upstream-path>=<sha256> ...] [--input-record <upstream-path>=<record-id> ...]
python3 <short-drama-skill-dir>/scripts/project_tool.py decide <project> --artifact-id EP001:script --decision accepted
python3 <short-drama-skill-dir>/scripts/project_tool.py accept-batch <project>
python3 <short-drama-skill-dir>/scripts/project_tool.py unpublish <project> --artifact-id EP001:script
python3 <short-drama-skill-dir>/scripts/project_tool.py review-batch <project> --episode EP001
python3 <short-drama-skill-dir>/scripts/project_tool.py accept <project> --artifact-id EP001:script --decision accepted [--target 剧集/EP001/screenplay.md] --evidence-artifact 创作者决策/EP001-script.json [--evidence-hash <decision-file-sha256>] --evidence-record-id <decision-id>
python3 <short-drama-skill-dir>/scripts/project_tool.py review <project> --artifact-id EP001:script --verdict approve [--target 剧集/EP001/screenplay.md] --verdict-owner short-drama-review --verdict-artifact 审查/EP001-verdict.json [--verdict-hash <verdict-file-sha256>]
python3 <short-drama-skill-dir>/scripts/project_tool.py package <project> --episode EP001 --include <accepted-path> [...] [--omit <accepted-path> ...] [--omission-evidence <creator-decision.json> ...]
python3 <short-drama-skill-dir>/scripts/project_tool.py verify <project> --episode EP001
```

### `init` 的输入约束

- `--language` 与 `--prompt-language` 分别控制创作者可读内容和生成提示词正文，均校验
  BCP 47 形态，互不联动。
- `--aspect-ratio` 只接受两个大于零的十进制数，以 `:` 分隔，例如 `9:16`、`16:9`、
  `2.39:1`。空值、`9/16`、`-1:1`、`1:0` 均拒绝。
- `--max-clip-seconds` 只接受正有限秒数，写入
  `short-drama.json#/format/generation_limits/max_clip_seconds`；默认 15 秒，限制单次模型调用，
  不强迫 storyboard 拆影视镜头。
- 所有参数先校验再创建目录；非法参数不会留下只有部分机器目录的项目。

## Dashboard 启动

`$short-drama dashboard` 将下列命令作为长时运行进程启动。`--port 0` 由操作系统选择
未占用的回环端口，`--open` 在绑定成功后打开默认浏览器：

```text
python3 <short-drama-skill-dir>/scripts/dashboard_server.py --workspace <workspace> --port 0 --open
```

如果需要固定地址，可省略 `--port 0`，默认端口为 `8765`。`--host` 只接受回环
主机；服务会检查 Host 与 Origin，拒绝符号链接、路径越界和超出大小限制的文件。
脚本打印的地址包含本次启动专属的会话片段；浏览器用它建立独立 API 路径及
`HttpOnly`、`SameSite=Strict` 会话，所有项目 API 都要求该会话。
Dashboard 只提供一个创作页面：左侧目录按项目与剧集整理故事、人物场景、分镜和生成
文案，右侧正文始终可见并在打开项目后自动载入；不使用多页签或内容浮层，也不展示
文件树、真实路径、结构化格式或生命周期轴。待办和导出只在正文下方给出简短提示。
文本保存仍携带读取时的 SHA-256 版本；文件被其他页面或工具修改后，旧页面保存会
返回冲突而不是覆盖。Markdown 预览不执行项目 HTML；结构化内容以卡片呈现，保存时仍由
浏览器和服务端分别按标准 JSON 解析，任一层发现格式错误或 `NaN` / `Infinity` 等
非标准数字都拒绝替换原文件。媒体状态只使用“预演、
待确认、已采用”等创作者语言。
创作台要求运行平台支持安全目录文件描述符（macOS/Linux）；不支持时服务直接拒绝启动
并说明原因，不使用存在符号链接竞态的降级路径。

## 发布与创作者确认

`publish --output <target>=<source>` 可以重复使用；来源文件必须是项目内的 UTF-8
Markdown、JSON 或 JSONL。命令把来源文件和 `--input` 依赖的准确路径与 `hash` 写入
预写日志，只发布 `candidate`，且只检查文件格式；`validation_state` 保持 `not_run`，不能同时写入创作者确认
或独立审查结论。

### `publish` 拒绝写入的目标

以下目标在发布阶段直接报错，不进入预写日志，创作者文件保持原样。全部按**忽略大小写**
比对：旧版工程常运行在大小写不敏感的文件系统上，`Delivery/x` 与 `delivery/x` 是同一个
文件，区分大小写的判断在那里等于没有判断。

| 目标 | 原因 |
|---|---|
| `输入/**` | 创作者交来的来源材料不可变 |
| `.short-drama/**` | 机器状态，只由工具自身维护 |
| 任意位置的 `short-drama.json` | 承载 `creator_authority`。按**文件名**拦截而不只是根目录那一份：`find_project` 向上查找，被放进子目录的同名文件会让该子目录冒充项目根 |
| `交付/**` | 只由 `package` 闸门写入；否则已交付的 `manifest.json` 可被事后替换 |

**只能发布到标准阶段目录**：`项目开发`、`设定集`、`剧集`、`创作者决策`、
`审查`。旧版英文目录继续兼容。`status.layout.roots` 给出当前项目采用的完整目录映射；
第一次阶段发布会固定布局，之后创建另一种语言的平行阶段树会被拒绝。`mode=mixed`
表示已有平行树，需要先迁移合并。
确实需要放在别处的临时文件加 `--allow-unregistered-path`：仍然可行，但不再是静默的。

**同一批路径必须具有唯一的可移植身份**：工具先把分隔符统一为 `/`，再按 Unicode NFC
和大小写折叠比较。`项目开发/Foo.md` 与 `项目开发/foo.md`、`a/b.md` 与 `a\b.md`、
以及组合字符前后等价的两个 Unicode 名称都会在写 WAL 前拒绝。该规则同时覆盖输出、
输入、记录绑定、目标映射、事务 manifest 和恢复路径，避免在当前文件系统上成功、移动到
Windows/macOS 后才发生覆盖。

**分集目录必须写成 `剧集/<EP>/`，`<EP>` 是 `EP` + 三位数字**（`EP001`；超过
`EP999` 之后不再补零，写 `EP1000`）。`ep1`、`EP1`、`EP0001` 都会被拒绝——`EP0001`
被拒是因为它会成为 `EP001` 的第二种拼写，而交付完整性闸门按 `剧集/<EP>/` 前缀
枚举本集产物，另一种拼写下的产物会被静默跳过，于是闸门在一个它从未清点过的分集上通过。
`package --include` 同样按这条规则校验。同一形式也用于剧本的 `# EP001` 集标题。

**结构化引用里的 `hash` 必须是 64 位小写十六进制**。直接发布还带 `<sha256>` 占位符的
模板会报 `structured ref hash is unfilled or invalid`。此前这类引用被静默丢弃，导致
填得越少、依赖检查越宽松——正好与 hash 绑定的目的相反。

**JSON/JSONL 只接受标准 JSON 数字**：`NaN`、`Infinity`、`-Infinity` 在项目文件、候选
输出、审核记录、机械检查输入和 Dashboard 请求中全部拒绝。时长未知时写 `null`；已声明的
时长、总计与 delta 必须是有限数字。工具输出使用同一约束，不会生成浏览器无法解析的 JSON。

**已声明产物的负责技能是固定的**：`剧集/<EP>/screenplay.md` 只能由
`short-drama-write` 发布，`storyboard/motion-specs.jsonl` 与
`storyboard/generation-clips.jsonl` 只能由
`short-drama-video-prompts` 发布，其余见
[contract-and-ownership.md](contract-and-ownership.md) 的单一负责人登记表。表里没有
点名的路径不受此限——契约为自己的产物指定负责人，不为创作者可能放进去的每个文件指定。

以上是**发布**时的规则。已经写进预写日志的路径不受影响：对旧 manifest 套用今天的
布局政策会让回滚直接报错而不是还原创作者的上一版，`recover` 每次都重复报阻塞，项目
再也退不出来。所以布局只在新路径产生的地方校验。

**已有不合规目录的项目怎么迁移**：`剧集/ep1/` 里的产物仍可 `accept`，但不能再发布
新版本，也不能打包交付。把内容按 `剧集/EP001/` 重新发布一次并重新接受即可；交付枚举
按 `剧集/<EP>/` 前缀匹配，旧路径本来就不在 `EP001` 的清点范围内，磁盘上的旧文件
不会被自动删除，确认新版本无误后自行清理。

`accept` 使用创作者决定记录，把所有准确的 `candidate` 目标 `hash` 推进为
`accepted`；记录的负责人固定为 `creator`。

`--target` 可以省略 `=<sha256>`：`accept` 从项目状态取该产物的 `candidate_targets`
快照回填，`review` 取 `accepted_targets` 快照——命令收到后本来就要与磁盘实况逐 hash
核对，省略的 hash 只是"意图声明"，不是安全边界；显式 `--target 路径=<sha256>` 保留为
严格形式并仍然核对相等。完全不传 `--target` 时绑定快照中的全部目标。

`--evidence-hash`（`accept`）与 `--verdict-hash`（`review`）同样可以省略：工具从
`--evidence-artifact` / `--verdict-artifact` 指定的文件现算 SHA-256，校验链与传值
完全一致（`_normalize_artifact_ref` 仍以磁盘活 hash 为准复核）。例行执行时不需要
任何手工 hash——写路径，工具算字节。

证据引用可用 `--evidence-record-id`（JSONL 记录定位）与 `--evidence-field`
（RFC 6901 字段指针，如 `/accepted_value/composition`）收窄到证据文件内的具体记录；
不传时按整文件绑定。`--verdict-record-id`（`review`）用于定位结论记录。
`--decided-by`（`decide`）声明决定主体：默认只能是 `creator`；委托人使用
`<role>:<stable-id>`，并同时提供 `--delegation-artifact`（可选
`--delegation-hash` / `--delegation-record-id`）绑定创作者签发、范围准确的委托决定。

### accept-batch：批量应用已记录的接受决定

整批生产（多集、多阶段）时，逐产物 `accept` 会变成每产物一次模型回合。决定已经写在
磁盘上后，用一条命令全部应用：

```text
python3 <core>/scripts/project_tool.py accept-batch <project>
```

命令扫描项目布局中的创作者决策目录（可用 `--decisions-dir` 覆盖，或
`--evidence <path>` 追加单个文件），读取每条 `decision_kind: artifact_acceptance`
且 `decision`/`status` 为 `accepted` 的记录，逐条执行与 `accept` 完全相同的校验
（candidate targets 一致、目标 hash 与磁盘一致、输入闭包、证据文件 hash 与
`decision_id` 定位），通过后推进为 `accepted`。任何一条失败整体退出非零，并逐条报告
`applied / skipped / failed` 与原因。它只应用**已经写下的决定**，不代替创作者做决定。
文件名不决定依赖顺序：工具先解析全部决定，再在每轮应用当前输入闭包已满足的记录；只要
本轮有进展就重试尚缺 accepted provider 的记录，直到全部推进或不再有进展。被更新决定的
`supersedes_decision_id` 指向的旧记录会直接记为 `skipped`，不会先应用过期决定。
接受成功后 candidate 字段归档，同一 target 只能接受一次；对已接受且目标完全一致的
决定，重复应用记为 `skipped`（reason `already accepted with identical targets`），退出码
仍为 0——重跑批次不是失败，决定文件不需要删除。目标不一致的旧决定仍会失败：修订流程是
重新发布新 candidate、`decide --force` 写替代决定后再接受，而不是重复接受旧 target。

批量生产的回合合并策略见 `batch-production.md`。

### decide：写下合规的接受决定文件

`accept-batch` 读的是磁盘上的决定记录，但这些记录过去要手工写 JSON（`decision_id`、
`target_hashes`、证据自引用 hash），任何字段不符整批失败。`decide` 从项目状态取当前
`candidate` 快照，写出一份 `accept-batch` 与 `accept` 都接受的记录——它不代替创作者
做决定，只免除文件格式的手工劳动：

```text
python3 <core>/scripts/project_tool.py decide <project> \
  --artifact-id EP001:script --decision accepted
```

默认写到 `创作者决策/<artifact-id 冒号→连字符>.json`（`--output` 可覆盖）。文件已存在时
报错不覆盖，除非加 `--force`：旧文件保持原字节，新决定写到同目录的
`<stem>.superseding-<decision-id>.json`，并用 `supersedes_decision_id` 形成不可变审计链。
因此旧决定即使已被其它产物引用也不会发生 hash 漂移；已接受产物没有 candidate targets，
`decide` 本身仍会拒绝。`--output` 只能写到
`创作者决策/` 根下：受保护目录（`交付/`、`输入/`、`.short-drama/`）与决策目录之外的
其他阶段根会被拒绝——决定文件是 `accept-batch` 从决策根扫描的生命周期证据，写到别处
既逃过布局保护，也会让决定永远不被应用。**不写项目状态**，应用仍由 `accept-batch`
完成。决定内容仍然来自创作者确认。

委托接受示例：

```text
python3 <core>/scripts/project_tool.py decide <project> \
  --artifact-id EP001:script --decision accepted \
  --decided-by producer:LI-001 \
  --delegation-artifact 创作者决策/delegation.json
```

委托证据必须由 `creator` 决定，`decision_kind` 为 `delegation`、状态为 `accepted`，
且 `delegate`、`scope.operations`、`scope.artifacts` 精确许可本次操作和 artifact。

### unpublish：撤销发布但未接受的产物

发布方向错了（例如把共享设定集的一个片段发成独立 artifact，造成 provider 歧义）时，
没有任何工具路径可撤销——`recover` 只修中断的事务，已提交的记录只能手改状态文件。
`unpublish` 移除一条 `creator_acceptance` 不是 `accepted` 的 artifact 记录：

```text
python3 <core>/scripts/project_tool.py unpublish <project> --artifact-id SET:LOC-SUWAN-HOME
```

- **只撤销未接受（candidate 阶段）的记录**；已接受产物被拒绝（`refusing to unpublish an
  accepted artifact`），因为下游已接受的证据链依赖它。
- 若其它 artifact 的输入引用了本产物（`candidate_inputs`/`accepted_inputs` 命中），
  一并列出依赖者并拒绝——先撤销依赖方或等它们重发后再撤销。
- 只删 `state.json` 里的记录；快照文件保留（孤儿无害），内容文件不动——修正后的候选
  可以直接重新发布、重新接受，不需要手改状态。

**决定与审查证据按产物分文件存放**：默认约定是 `创作者决策/<artifact-id>.json`
与 `审查/<EP>-findings.jsonl`，**一个产物一份**。文件名的 `<artifact-id>` 使用净化后的
拼写：把冒号写成连字符（`EP001:script` → `EP001-script.json`），因为 Windows 等文件系统
不允许 artifact id 里的冒号，按原名写会被静默当成备用数据流、`accept-batch` 扫描不到。
原因是证据引用默认绑定的是**整文件 hash**：把全项目的决定追加进同一个
`creator-decisions.jsonl` 时，接受第二集会改变该文件的 hash，于是第一集那条已经冻结的
证据引用永久指向一个不再存在的字节状态。

`review` 与 `package` 会重新校验存量引用，因此共享文件一旦追加，旧接受记录会变 stale 并
阻断后续流程。JSONL 虽可用 `record_id` 定位记录，但引用仍绑定文件 hash；推荐继续使用
一产物一文件，保持证据稳定且便于审计。

JSONL 记录必须用 `--evidence-record-id` 唯一定位同名 `decision_id`；JSON 证据必须是对象；所定位记录的
`status` 或 `decision` 必须与命令的 `accepted/rejected` 一致。用于产物生命周期的记录
还必须声明 `decision_kind:"artifact_acceptance"`、当前 `artifact_id` 和与全部 `--target`
完全相同的 `target_hashes`；其他已接受决定不能代替本次接受。

## 独立审查记录

`review` 的审查结论 JSON 必须列出同一组结构化的受审 `ArtifactRef`；`review-batch`
批量应用时结论文件还必须声明 `artifact_id` 指明它审的是哪个产物（`review-batch`
据此路由）。`reviewer` 至少包含
与审查结论负责人一致的 `owner`、`kind`、`independent`，并在
`excluded_owner_skills` 中准确排除被审文件的负责人：fresh 审查写 `kind: independent_agent`、
`independent:true` 与 fresh 上下文 provenance；冷读审查写 `kind: cold_reader`、
`independent:false`、`provenance:null`。`findings_ref` 必须由审查者所有，
绑定当前有效的 `hash`，并指向可解析的 JSONL；其中所有未关闭的致命、错误或阻断问题 ID 必须与 `blocking_findings` 完全一致，
`open_blocker_count` 再与之对齐。

字段校验**一次列出全部缺失/非法项**（`verdict has invalid fields: …`），而不是逐步报错：
`requested_review_mode`、`effective_review_mode`、`reviewer`（kind / independent /
provenance / excluded_owner_skills）、`required_reviewer_independence`、
`structural_validation`、`findings_ref`、`review_bundle_ref`、`reviewed_artifacts`、`blocking_findings`、
`open_blocker_count` 全部独立检查后一次性给出，修一轮即可跑通。

增量复核结论（`requested_review_mode` / `effective_review_mode` 为 `delta_verify`）改用
`kind: delta_verifier`、`independent:false`、`provenance:null`，并附 `delta_basis` 绑定
base 结论（`base_review_id` 与 `base_verdict_ref`）：base 必须是同一目标集上的
`fresh_agent` 或 `cold_read` 非临时结论，且其全部阻断问题在当前 findings 中已关闭或被取代。
`delta_verify` 与 `cold_read` 批准推进审查状态但不放开交付闸门；交付打包仍要求 `fresh_agent` 终审结论。

注意状态轴语义：`independent_review` 轴会记录 `independent:false` 的 `delta_verify` / `cold_read`
批准（合法性分别继承自 base 结论与冷读输入节食协议），判断交付能力以 `delivery_gate` 与打包闸门的复核为准，
不以该轴的批准字样单独放行。

命令示例统一写作 `python3`；Windows 环境通常只有 `python`，使用环境提供的等价解释器即可。

`structural_validation` 必须是 `pass | pass_with_warnings | fail`，并由这份准确的审查结论
更新校验状态；结构校验未通过或仍有阻断问题时不能批准。后续目标文件或任一
审核记录的 `hash` 改变，都要重新确认或审查。

### review-batch：批量应用已写入的审查结论

与 `accept-batch` 对称：verdict 结论 JSON（含 `artifact_id`）已经写在磁盘上后，用一条
命令全部应用，逐条执行与 `review` 完全相同的校验（accepted targets、创作者接受证据、
输入闭包、live hash、verdict 证据与 findings 对账）：

```text
python3 <core>/scripts/project_tool.py review-batch <project>
python3 <core>/scripts/project_tool.py review-batch <project> --episode EP001
```

命令扫描项目布局中的审查目录（默认 `审查`，可用 `--verdicts-dir` 覆盖，或
`--evidence <path>` 追加单个文件）下的 JSON 文件，只处理带 `review_id` 的 verdict
文档（无 `review_id` 的文件记为 `skipped` 并计入统计，与 accept-batch 跳过非接受
决定的思路一致，但不是失败）。**应用顺序与文件名无关**：`delta_verify` →
`cold_read` → `independent_agent`（fresh）按此稳定排序——只有独立结论能放开交付闸门，
所以它最后应用，避免被先应用的 delta/cold_read 覆盖。`--episode <EP>` 时只应用
`artifact_id` 以
`<EP>:` 开头的 verdict（**大小写严格**：`ep001:script` 不匹配 `--episode EP001`，
会被当作其他集的结论跳过），其余记为 `skipped`——整集的全部结论一次应用，其他集的
结论不受影响（整集是否全部 approve 由 `pipeline --episode` 报告）。
每条 verdict 必须声明 `artifact_id` 指明它审的是哪个
产物（与
`创作者决策/<id>.json` 的 `artifact_id` 对称）；`findings_ref` 在 verdict 文档内部
绑定自己的 findings 文件，所以批量应用不需要每产物一条命令传 findings。任何一条失败
整体退出非零（退出码 2），并逐条报告 `applied / skipped / failed` 与原因。它只应用
**已经写下的结论**，不代替审查者下结论；同一产物重复应用**相同**的 verdict 是幂等的
（每次对当前 state 全量重验，重复运行不报错也不误报），targets 已变更的旧 verdict 才会
失败——修订流程是重新发布新 candidate、重新接受、再写新 verdict。

### review-bundle：审查证据打包（L1 派发与冷读共用）

派发 fresh reviewer 或开始冷读审查前，用单条命令把目标集打包成一份已验证的证据文件：

```text
python3 <core>/scripts/project_tool.py review-bundle <project> --episode EP001 \
  --artifact-id EP001:L1
# 或显式指定目标（可带 PATH=SHA256 精确绑定）：
python3 <core>/scripts/project_tool.py review-bundle <project> \
  --target 剧集/EP001/screenplay.md \
  --target 剧集/EP001/storyboard/shots.jsonl
```

打包结果写到 `.short-drama/review-bundles/<review-id>.json`（机器工作区，不进交付包），
stdout 输出紧凑指针：bundle 路径与 `bundle_hash`、目标清单（path/hash/state）、机械检查状态。打包器会：

- 核对每个目标的当前 hash 与请求值或生命周期快照一致，不一致直接报错；
- 按类型提取证据：JSONL 逐记录（含记录 ID 与规范哈希）、JSON 全文、Markdown 按标题
  分段；剧本存在 `screenplay-index.jsonl` 时按索引逐 block 切出原文并核对 block hash；
- 把绑定输入解析到被引用的精确记录（`--input-record` 的选择器），审查者无需再翻共享文件；
- 自动运行目标族适用的内置机械检查，并附带已接受的 creator authority（约束、视觉方向、
  制作形态、交付面）；`--mechanical-report` 可重复传入外部补充报告，明确失败的报告会使
  bundle 状态变为 `issues`。

fresh reviewer 或冷读审查者只读这份文件即可获得全部事实与引用锚点；`review_id` 由目标与哈希
确定性生成，同一目标集重复生成不会产生新文件（机械报告或内容变化会覆盖同名文件，
以当前字节为准）。bundle 本身不是审查结论，也不能代替 `review` 命令记录 verdict。
`review` 的 verdict 必须带 `review_bundle_ref`，并且工具会重新运行适用的本地机械检查；
复核者自报 `structural_validation: pass` 或上传伪造的 pass JSON 不能绕过这一绑定。

## 过期影响与依赖检查

接受时把 `candidate` 的准确输入清单保存为 `accepted_inputs`。发布新 `candidate` 时，
同一预写日志清单会找出直接和间接受影响的下游文件：保留旧的创作者确认记录，
但把受影响的下游构建状态标为 `stale`，清空校验与审查就绪状态，并阻止交付。

### 把共享文件的失效半径收窄到记录

`设定集/*.jsonl` 这类文件是全项目共享输入。只按整文件 `hash` 绑定时，第 48 集新增一个
配角会把此前 47 集引用过该文件的产物全部标为 `stale`——它们其实一个字都没受影响。

发布时用 `--input-record <path>=<selector>` 声明**这份候选实际读了哪几条记录**
（可重复；仍需同时用 `--input` 绑定该文件的整文件 `hash`）：

```text
--input 设定集/characters.jsonl=<sha256> \
--input-record 设定集/characters.jsonl=CHAR-GUHE \
--input-record 设定集/characters.jsonl=CHAR-LINYE
```

此后该文件的其余部分怎么改都不影响这份产物；只有被绑定的记录本身变化、消失或变得
不唯一时，它才会被标为 `stale`。`review` 与 `package` 的逐层复验同样改为核对这几条
记录，所以文件 `hash` 前进之后产物依然可以交付。

**`--input-record-auto`（默认开启）免写手动的记录清单**：发布时，候选输出里指向已声明
`--input` 文件的结构化 refs（JSON/JSONL 内 `{owner, artifact, hash, record_id}`）会
自动把它们的 `record_id` 并入记录绑定——一个 8 角色的文件不用手写 8 条
`--input-record`，漏一条也不会报错。`--no-input-record-auto` 恢复整文件绑定
（无手写记录时）。auto 收集只收窄**已声明**的输入，不推断新依赖；ref 里没有
`record_id` 或它在该文件中无法唯一解析时静默跳过，退化为与手写漏掉一致的整文件绑定。
显式 `--input-record` 始终优先，与 auto 收集结果取并集。

- **JSONL 选择器是记录 ID**：取值为某个以 `_id` 结尾的顶层字段，且在该文件中只出现
  一次。出现零次或多次一律拒绝，不做猜测。
- **JSON 选择器是 RFC 6901 指针**，例如 `/creator_authority/production_profile`。
- 记录 `hash` 按键名排序后的规范形式计算，所以重排字段或改动缩进不会误判为变化。
- screenplay-index 1.1 的 block 以 `record_hash_version: screenplay-block-v1` 明确采用稳定
  摘要：保留 block ID、类型、场景、内容 hash 和语义字段，排除父剧本文件 hash、行/字节
  偏移与 revision mapping。1.0 索引继续使用 legacy 全记录摘要，重建到 1.1 时显式迁移一次。
- **Markdown 不能做记录级绑定**：它没有可机器校验的记录身份，收窄只会变成一句无法
  验证的承诺。剧本类依赖仍按整文件绑定，需要更小半径就先拆文件。

`accepted_inputs` 中保留的整文件 `hash` 此时是**绑定当时的快照**，用于按 `hash` 取回
那一版字节；判断是否仍然有效的依据是被绑定的那几条记录。

`review` 和 `package` 会逐层复验输入的当前 `hash`、唯一且状态为 `accepted` 的提供方，
以及提供方本身的构建、确认状态和输入。外部编辑、循环或含糊依赖不能靠手改状态字符串
绕过。若多文件产物的新 `candidate` 不再包含旧的 `accepted/candidate` 目标，该路径也会
被列入受影响的下游清单；旧文件不会被静默删除，但新版本接受后，它不再拥有已接受权限，
也不能被单独打包。

`publish` 会读取 JSON 或 JSONL 候选文件中带 `owner/artifact/hash` 的引用：
指向同次输出时，`hash` 必须匹配该候选文件内容；其他引用必须以相同路径和 `hash` 出现在
`--input`。遗漏或不一致会在写预写日志前被拒绝；Markdown 依赖无法可靠推断，仍必须由
负责人明确声明。

## 恢复与打包

`recover --transaction <txid>` 只处理指定事务。`package` 会重新验证状态文件中保存的创作者
决定和独立审查记录，只打包当前 `hash` 与已接受快照一致、并且各项交付状态都已就绪的
Markdown、JSON 或 JSONL。

`package` 先复验本集固定流程的 M2–M5 已完成、M6 全部通过，再复验五轴中的 build、
validation、creator_acceptance、independent_review 与 delivery_gate，并要求
`short-drama.json#/creator_authority/delivery_surface` 已由创作者接受。只有剧本或只有某一分支
的项目不能生成固定主线正式交付包。

`--text-exceptions <file>` 声明需要读原文才能判断安全性的例外文件：文件内容是 JSON
数组（每条为项目相对路径），这些文件仍会被扫描完整性，但允许以未批准文本进入交付。
`--omit <path>` 则从本集完整性枚举中显式排除已接受路径，但每个省略项还必须由
`--omission-evidence <creator-decision.json>` 提供一条 `decision_kind: delivery_omission`、
`status: accepted`、逐路径 `reasons` 的创作者决定；裸路径或通用默认理由会被拒绝。

### `verify`：复核已交付的包

```text
python3 <short-drama-skill-dir>/scripts/project_tool.py verify <project> --episode EP001
```

`package` 会写出 `checksums.sha256`，但在此之前没有任何命令再读它——交付目录被事后
改动仍然"看起来已交付"。结果 `status` 为 `intact` 或 `tampered`，后者由四个字段说明原因：

| 字段 | 含义 |
|---|---|
| `checksum_list_authentic` | 校验和清单本身是否仍等于打包时记录在 `.short-drama/state.json` 里的 hash。**能改产物的人同样能重算清单**，所以先验证清单，再信任其中任何一行；这一项单独为 `false` 时，其余三项可能全是空的。注意它只是同一棵树内的第二个锚点：连状态文件一起改仍能骗过它，要防这一类需要把 hash 留在项目之外 |
| `mismatched` | 已登记文件的内容变了 |
| `missing` | 已登记文件不在了，或被换成了符号链接（指向交付树之外的字节不予采信） |
| `unlisted` | 交付目录里有清单上没有的文件或符号链接目录——**校验和清单对新增是盲的**，只核对已登记项永远发现不了它 |

命令在 `tampered` 时退出码为 1，可以直接用在 `&&` 链或流水线闸门里。

### 完整性由工具枚举，取舍由创作者声明

手写的 `--include` 清单**漏了东西时和没漏时长得一模一样**。状态文件里已经记着本集有哪些
已接受文件，所以这份枚举由 `package` 来做：本集 `剧集/<EP>/` 下每一个已接受路径，
要么在 `--include` 里，要么在 `--omit` 里，否则拒绝打包并逐条列出。

`--omit` 不是绕过，是留痕：清单的 `omitted` 段会记下每条被排除的路径、它的负责产物、
创作者决定引用和逐路径理由。后者尤其重要——正在返工的产物
是最容易被无声绕过的，而收件方从一份看不出缺件的交付包里读不出这件事。
当一个 artifact 的全部目标都已进入 `--include` 或带证据的 `--omit`，该 artifact 视为已在
本次 manifest 中结算并推进 `delivered`；因此合法省略整个 artifact 不会让 M7 永久悬空。

`--omit` 只接受本集的已接受路径：多文件产物换掉旧目标后，旧路径不再有已接受负责人，
既不能交付也不能被声明省略。其他分集的产物不进入本集的枚举范围。故事中确实需要交付屏显网址或屏显机器路径时，要有明确的例外
文件，绑定准确的文字、路径、字段、来源和文字呈现方法；其他网址与机器路径默认阻断。
例外只释放它逐字声明的那一个字符串：路径必须写到完整的那一条，只写盘符或目录开头会被
拒绝，整段文档也不能当作一条例外。文件协议网址、私钥与结构化凭据字段无条件阻断，
没有例外通道。

每条例外必须写齐七个字段，缺一即整体拒绝：`exact_text`（逐字原文）、`path`（绑定到哪个
交付文件）、`field`（该文字在产物中的字段位置）、`purpose`（固定为 `on_screen_text`）、
`provenance`（`creator_supplied` 或 `story_world_authored`）、`text_policy`
（`visible_on_screen` 或 `fictional_interface_text`）、`allow_delivery`（必须为 `true`）。

## 例行 EP 的执行预算

单集从创作到交付的例行时间分配（在命令都已自动化后）：
批量执行的固定节奏（记录级绑定、候选目录生命周期、拓扑规划、base/delta 分离）与
错误恢复速查见 [production-sop.md](production-sop.md)。

- **创作与发布**（约 20 分钟）：写作 → `publish` → 索引/机械检查。CLI 全程不需要
  手工 hash：`--target` 省略 hash、`--evidence-hash`/`--verdict-hash` 省略由工具现算。
- **例行审查**（约 15–20 分钟，全程当前上下文，零子 agent）：
  1. 首审默认 L1.5 冷读（类型基准已建立后），只读 `review-bundle` 证据文件；
  2. 审查一次列全所有 findings（一个 findings JSONL），owner 一次改完所有问题再发布接受；
  3. 反审走 L2 `delta_verify`（当前上下文对照 base 结论逐条核销）；
  4. 结论写好后 `review-batch --episode EP001` 一次应用整集。
  verdict 文档内部引用仍需提供准确 hash：`reviewed_artifacts[].hash` 从 bundle targets
  抄写，`review_bundle_ref.hash` 使用输出的 `bundle_hash`，`findings_ref.hash` 写结论前
  对 findings 文件现算（空 findings 是空文件 hash）——写错会被磁盘活 hash 复核拒绝。
- **交付终审**（唯一子 agent 时刻，整集一次）：`review-bundle --episode EP001` + 一个
  fresh reviewer 覆盖全部范围（不按产物类型各起一个），再 `package` / `verify`。

关键纪律：**不要**为"例行首审/反审"派 fresh 子 agent（冷读与 delta_verify 已覆盖）；
fresh 只用于类型基准首审、越出派发范围的大改、交付终审三事件。一次 REVISE 就改全，
把修订轮数压到 1——每多一轮就多一次反审成本。
