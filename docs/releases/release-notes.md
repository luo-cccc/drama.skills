# 发布说明

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

### 2026-08-14 — 0.5.0

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
