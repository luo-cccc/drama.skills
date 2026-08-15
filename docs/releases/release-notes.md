# 发布说明

### 2026-08-15 — 0.7.0

- Dashboard 新增 Windows 10/11 x64 原生安全后端，保持原启动命令、前端 API、Cookie、
  Host/Origin 校验和既有响应字段不变；Windows 自动选择新后端，项目发现、状态、文本编辑和
  媒体 Range 预览均可用。正文已提交但生命周期状态更新失败时，保存响应会附加
  `stateWarning: "lifecycle_update_failed"`，前端保留新版本并提示运行项目预检。
- Windows 文件访问从盘符卷根开始使用 `NtCreateFile(RootDirectory=...)` 逐级固定句柄并拒绝
  全部 reparse point；仅允许本地固定 NTFS，UNC、设备路径、映射网络盘、ReFS/exFAT、
  OneDrive 占位、junction 和 symlink 均 fail closed。
- Windows 保存通过固定父句柄创建和刷新短名临时文件，持有目标首字节锁并执行两次目标
  SHA-256 复核，再使用 `NtSetInformationFile(FileRenameInformationEx)` 相对父句柄原子替换；
  媒体流持有已验证句柄到响应结束，临时文件失败清理也通过句柄完成。
- Dashboard 与 Windows CLI 共用 `.short-drama/locks/transaction.lock`。新增跨进程保存冲突、
  CLI 锁互斥、父目录/项目根/媒体置换、写入与替换失败、句柄关闭及不支持卷/API 启动拒绝测试；
  Windows 不再跳过 `ProjectStore` 行为测试。
- 文档将 Dashboard 启动、平台边界、原子保存和部分成功语义收拢到生命周期命令章节；README、
  文档导航与维护手册只保留入口和回归摘要，并移除暗示 Windows 路径版或只读降级的旧说法。
- 套件升级到 0.7.0；契约保持 `1.3.3-draft`、提示配方保持 `1.3.2-draft`，pipeline 保持 2.0.2。

#### 0.6.3

- 完整 Location 的方向基准现在明确 Front 与左右手性；正交板和俯视板使用独立的 16:9
  规划画幅与安全边距，不再继承项目成片比例或依赖提示词口头约定。
- 空间证据继续逐项绑定完整来源，同时按建筑壳体、门窗、固定家具和功能区域汇总提示词表达，
  大型场景不再把审计清单原样塞进生成正文。
- 新增可选的外部结果观察门禁。质量优先流程可要求每条 M4a 资产图规格在进入分镜前具有精确、
  当前且经授权的结果观察；默认模式保持只交付提示词。观察不等于质量通过或创作者接受。
- 图片规格与 Look Development 规格统一服从项目提示词语言；编译器持久化语言声明并拒绝与
  标准片段不一致的记录，不通过猜测正文语种制造误判。
- 套件升级到 0.6.3、契约升级到 `1.3.3-draft`、提示配方升级到 `1.3.2-draft`；pipeline
  升级到 2.0.2，编译器输出格式升级到 1.2。

#### 0.6.2

- canonical structured ref 新增闭合校验：技能所有的 accepted ref 必须存在同 owner、同路径、
  同 hash 的 accepted 生命周期 provider；同批 candidate ref 必须绑定同 owner 的同批目标。
  仅 creator 所有的输入、创作者决策，以及 creator/short-drama 所有的项目文件属于明确的
  intrinsic authority 例外。
- JSONL `record_id` 必须在目标文件中唯一解析，JSON `field` 必须是可解析的 RFC 6901 指针，
  JSON 顶层 `record_id` 必须匹配顶层 `*_id`；Markdown 和其它文件不能声明记录级身份。
  `--no-input-record-auto` 只关闭失效范围自动收窄，不关闭引用真实性校验。
- 场景板 `evidence_bindings` 必须逐项引用绑定 spatial model 的
  `/evidence_elements/<key>`，发布时核对 `element_id`、`status` 并要求无遗漏、无额外元素。
  spatial model 的证据元素同时要求有效、非空且带 canonical `source_refs`。
- 套件升级到 0.6.2、契约升级到 `1.3.2-draft`、提示配方升级到
  `1.3.1-draft`；pipeline 保持 2.0.1，编译器输出格式保持 1.1。

#### 0.6.1

- 图片提示词新增 `scene_orthographic` 场景正交板 profile。它绑定单一 accepted Location 的
  spatial model，不创建复合 View；固定 Front/Left/Right/Back 顺序、统一尺度、坐标基准、
  正交投影和只隐藏当前阻挡墙的切墙政策。
- 新增 `scene_top_view` 严格 90 度俯视地理底板 profile。摄影机、视野锥、镜头编号与演员路线
  由下游 storyboard 拥有，M4a 不消费 M4b 记录，也不形成生命周期反向依赖。
- 两种板式都新增逐元素 `evidence_bindings`，确认、推定和未知不再只声明空图例；未知标签固定
  由后期排版添加，生成画面不得绘制可读注释文字。
- `prompt_compile.py` 1.1 新增板式几何、spatial model 坐标引用、证据映射与后期注释校验，
  并增加编译和跨阶段消费回归测试。由 1.0 编译的候选记录必须在再次发布前运行 `finalize`
  或 `prompt_compile.py` 重新生成 manifest；已接受且未修改的快照不要求原地改写。
- 套件升级到 0.6.1、提示配方升级到 `1.3.0-draft`；契约保持 `1.3.1-draft`，pipeline
  保持 2.0.1。

#### 0.6.0

- 新增严格显式调用门禁：当前请求未点名对应 `$short-drama*` 技能时，九个技能均不得
  自动触发；子技能显式调用后仍以 `short-drama.json` 作为项目初始化门禁。
- 整理现行入口文档，统一“显式调用 → 项目标记 → `preflight`”顺序，移除会暗示自动
  路由的旧表述；历史版本说明继续保留。
- 将九个公共技能重写为 51–92 行的渐进加载入口；技能正文总字节从约 140 KB 降至约
  28 KB，明确阶段任务不再要求模型读取 suite manifest、完整速查或阶段契约；专项参考仍从
  各技能入口按需可发现。
- 新增 `project_tool.py prepare`：按 stage/episode/intent 生成 hash 绑定任务胶囊和工作骨架，
  汇总唯一下一动作、creator authority、精确来源、按需参考和输出目标。
- 新增 `project_tool.py finalize`：拒绝陈旧胶囊，生成 screenplay index，确定性编译 prompt
  记录与 Markdown 投影，执行 storyboard/video 机械检查，并支持显式 candidate 发布。
- `review-bundle` 新增 scope 过滤、基于旧 verdict 的差量目标和 minified JSON；compact 模式
  不删除证据，交付终审继续使用 full episode。
- 新增模型上下文性能审计及回归预算。套件升级到 0.6.0、提示配方升级到
  `1.2.0-draft`；契约保持 `1.3.1-draft`，pipeline 保持 2.0.1。
- 文档入口统一到 M0–M7 和任务胶囊工作流；移除旧 C0–C5 检查点、重复的公共预检正文、
  已失效的发布限制与固定分钟数，并增加链接和文档一致性回归。

### 2026-08-14 — 0.5.1

- 套件升级到 0.5.1，契约升级到 `1.3.1-draft`，固定流程升级到 pipeline 2.0.1。
- `package` 现在硬性要求本集 M2–M6 全部完成；不完整资产消费或未通过审查不再能生成正式交付包。
- M1 按 `creative-brief.md`、`story-engine.md`、`episode-map.jsonl` 三项逐一判断，不再由任意单个开发产物代替。
- M3 剧本引用统一使用 index 文件 hash 与 block ID，发布、接受和 pipeline 不再要求互相冲突的
  两种 hash；分拆发布的 occurrences、decisions、continuity 可在同一批次完成完整门禁。
- 未改动的剧本 block 在其它段落修订或位置移动后保持有效，显著缩小下游重新发布范围。
- 自动记录绑定只在 selector 唯一解析时收窄范围，否则安全退回整文件绑定；手工指定的 selector
  仍严格校验，避免静默绑定错误记录。
- `accept-batch` 可按依赖关系多轮推进反向文件名链；`decide --force` 保留旧证据并生成带审计
  关系的新决定，避免决定文件被覆盖后触发整条生产链 stale。
- 发布器支持直接读取已在目标位置的候选文件；M1.5a 接受明确为空的可选特征集合；标准提示
  片段库新增确定性导出能力，减少手工 Markdown 格式错误。
- `canonical-prompt-library.md`、`image-prompts.md`、`keyframe-prompts.md` 和 `video-prompts.md`
  发布时核对结构化源 hash、记录身份和编译文本，派生缓存不能再自由漂移。
- generation clip 的 planned boundary 改为完整五槽位结构；continuation 必须绑定上一片段的
  `output_observation_ref`，单独审查 clip 文件也会运行 VID-22。
- 交付消费摘要新增 generation clip 和 delivery container 执行链；经创作者批准省略的整个
  artifact 会作为已在 manifest 中结算，不再让 pipeline 永久停在 M7。
- 新增端到端工作流与数据流文档及仓库文档导航，统一说明长篇输入、M0-M7 生产/消费、
  结构化权威与 Markdown 投影、长 shot 的 15 秒拆分、失效传播和交付包内容。
- 写作阶段新增私有写前包与可持久化质量报告；连续项目从已接受的地图读取合同和近期剧本，
  `write_standalone` 从单集卡读取，报告随审阅包交给独立审查。
- 连续地图新增与故事引擎 Hook 账本的一致性校验，稳定 ID、兑现计划和终态不能分别漂移。
- 清理 README 与维护手册中会随测试或清单增长而失真的静态数量，改为指向实际校验输出。

#### 0.5.0

- 套件升级到 0.5.0，契约升级到 `1.3.0-draft`，提示配方保持 `1.1.0-draft`，固定流程保持 pipeline 2.0.0。
- 新增 `generation-clips.jsonl` 与 `generation_clip_check.py`：项目默认单次模型调用上限 15 秒，
  长影视镜头可保持原剪辑边界并拆为多个连续生成片段；间隙、重叠、超限、错误引用和未授权续接会阻断 M5。
- 新增第 9 个公共技能 `short-drama-novel-analyze`：章节索引、可复现抽样快评、逐章功能提取、
  剧情单元/人物归并、改编价值、分集候选及独立 `source_analysis` 审查范围。
- `$short-drama-develop` 新增多集整稿精确索引、自动/手工边界、逐集切片、磁盘断点、
  原子幂等合并与中文路径/CRLF 回归。
- Windows 路径新增保留设备名、非法字符、控制字符和尾随空格/句点拒绝；机器 JSON 输出
  在旧代码页下保持 ASCII-safe，套件文本哈希兼容 LF/CRLF 安装。
- 新增不可跳过的 M1.5 生成资产基线层：六类资产的 `full/compact` 分级、结构模型、场景空间拓扑、状态变体和视图契约。
- 新增标准提示片段库与确定性 `prompt_compile.py`，图片规格、关键帧和运动规格统一使用绑定、组件与编译 manifest，发布时拒绝自由改写。
- `script-first` 只跳过故事开发；旧项目必须完成并接受 M1.5 后运行 `upgrade-flow`，没有 legacy 放行开关。
- 单集交付新增 `asset-baseline-bundle.json`，递归收集并复验本集实际消费的基线记录、片段和哈希。
- `asset-baseline-bundle.json` 现在同时列出 M3 decision、M4a 资产板、M4b shot/keyframe 和
  M5 motion 的记录级绑定链与差异；资产 ID 相同但 View、variant、片段版本或顺序变化也会被识别。
- M2 拒绝重复 ID、多余 View 片段和不闭合的允许集合；M3 occurrence/source blocks、decision cause
  与 continuity cause 必须解析到当前已接受 screenplay-index 记录哈希，各阶段记录 ID 必须唯一。
- 新增资产种类/等级、引用哈希、编译幂等与篡改、流程升级、记录级失效、跨资产片段顺序和交付证据测试。
- 项目路径新增统一的可移植身份校验：大小写、正反斜杠和 Unicode NFC 别名在发布、
  读集、记录绑定、事务清单、恢复和交付选择中都会提前拒绝，不再发生静默覆盖或不可恢复阻塞。
- 发布与恢复的 POSIX 文件操作改用固定目录描述符与 `O_NOFOLLOW`；Windows 候选读取增加
  文件句柄身份复核，路径置换会作为事务冲突停止。
- 全套 JSON/JSONL 入口改为严格 JSON，拒绝 `NaN` / `Infinity`；分镜、运动与容器检查器
  同时要求有限数值。`init --aspect-ratio` 只接受正数 `WIDTH:HEIGHT`。
- Dashboard 新增真实 HTTP session/Cookie/API、Host/Origin、安全响应头与 PUT 路由测试，
  前端纯函数加入无依赖 Node 测试并进入 CI。
- Python 测试增至 181 项，新增路径安全、安装兼容、文本/二进制哈希边界、多集整稿、原著分析、generation clip、严格 JSON 和版本一致性回归。

### 2026-08-13

- 创作者接受现在强制验证决定主体：直接决定必须来自 creator，委托决定必须绑定创作者签发且范围准确的 delegation evidence。
- 固定生产流程按 M2–M5 的完整必需文件集合判断里程碑，并实时识别磁盘外部修改导致的 stale 状态。
- 审查结论必须绑定精确 review bundle；bundle 会返回可直接引用的 hash，并运行适用的机械检查，避免自报结构通过。
- 交付打包现在要求已接受的 delivery surface；省略任何已接受产物都必须提供创作者决定和逐路径理由。
- 套件完整性校验改为每次全量重算 SHA-256，消除等长修改并恢复 mtime 后复用旧摘要的风险。
- Windows 与 CI 的 Python 输出统一为 UTF-8，并补充权限、缓存、流程、审查和交付回归测试。
