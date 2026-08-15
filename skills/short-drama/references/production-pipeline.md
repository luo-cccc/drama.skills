# 固定生产流程（Pipeline 2.0）

这是套件默认的**逐集生产 SOP**，由 `short-drama.json#/production_flow` 固定
（`pipeline_version` 2.0.2）。`project_tool.py pipeline <project>` 报告当前位置、
下一步与阻塞项；`enforcement: strict` 下当前里程碑存在阻塞项时退出码为 3，且图片提示词
与分镜的形态依赖在发布时直接拦停。

本页只定义里程碑顺序和门禁。每一步生产什么、下游消费什么、长篇和 generation clip
如何进入同一条链，见 [workflow-dataflow.md](workflow-dataflow.md)。

**主线必须逐级**：M0 → M1 → M1.5a → M1.5b → M2 → M3 → M4a → M4b → M5 → M6 → M7。
M1.5、M4a、M4b、M5 全部必经；唯一捷径是 script-first 跳过 M1，不能跳过 M1.5。单分支请求
（只出图片、只出分镜等）只有在用户显式调用对应技能时才可执行，不属于固定主线。
**M0 即要求形态已定**：`visual_direction` 与 `production_profile` 未接受时 `pipeline`
报告 `BLK-M0-FORM`，strict 下退出码 3；即使 script-first，也必须先定形态再动笔。

## 主线

| 里程碑 | 阶段 | 入口条件 | 负责人 | 产物 | 出门条件 |
|---|---|---|---|---|---|
| M0 | 基线 | 项目已 `init` | `$short-drama` | 形态（`visual_direction` / `production_profile` accepted）；建议完成设定播种与交付面声明 | 形态已接受 |
| M1 | 开发 | M0 | `short-drama-develop` | `creative-brief.md` / `story-engine.md` / `episode-map.jsonl`（accepted） | 产物全部接受；script-first 项目可跳过 |
| M1.5a | 生成资产模型 | M1（或 script-first） | `short-drama-assets` | `设定集/generation/asset-scope.jsonl`、资产/空间/变体模型、视图契约、基线总览（accepted） | 分级、模型、空间拓扑和视图完整且创作者接受 |
| M1.5b | 标准提示片段 | M1.5a | `short-drama-image-prompts` | `canonical-fragments.jsonl` / `canonical-prompt-library.md`（accepted） | 五类片段覆盖完整，语言与输入哈希当前 |
| M2 | 写作 | M1.5b | `short-drama-write` | 单集卡、节拍、剧本与索引（accepted），记录实际资产和本集允许消费的 generation 记录 | 剧本类产物接受、索引存在且资产引用完整 |
| M3 | 单集资产增量 | M2 | `short-drama-assets` | occurrence、复用决定、连续性/状态增量（accepted） | occurrence/decision 身份与类型一致，显式选择 generation model/variant；delta 映射回 M2 |
| M4a | 单集资产图提示词 | M3 | `short-drama-image-prompts` | 图片规格与 Markdown（accepted） | `asset_board` 逐资产覆盖基线、全部允许 View/variant 并通过确定性编译；`observed` 模式还需逐规格精确生产观察（必经） |
| M4b | 分镜与关键帧 | M4a | `short-drama-storyboard` | coverage、shots、keyframes 与 Markdown（accepted） | 每镜 Location 完整，asset/model/variant/View/fragment hash fingerprint 与首关键帧一致（必经） |
| M5 | 视频提示词 | M4b | `short-drama-video-prompts` | motion specs、generation clips 与 Markdown（accepted） | 每镜至少一条 `motion` profile，逐项复用 shot/keyframe fingerprint；每镜模型调用片段完整覆盖且不超过项目上限（必经） |
| M6 | 审查 | M2–M5 已接受的产物 | `short-drama-review` | `审查/<id>-findings.jsonl` / `审查/<id>-verdict.json`（approve） | 全部产物审查通过（首审默认冷读，交付终审须 L1 fresh） |
| M7 | 交付 | M2–M5 完成、M6 全部通过 + `delivery_surface` accepted | `short-drama` | manifest、checksums、`asset-baseline-bundle.json` | 包含本集基线记录、片段、哈希，以及 M3 decision、M4a board、shot/keyframe/motion/generation clip/container 的逐层绑定证据和差异报告 |

M3 正常完成只允许已经解析并绑定到 M2 基线的 `reuse`。`unresolved` 可以保留为候选诊断，
但会阻断 M4a；若拆解发现 `new_variant` 或 `new_asset`，当前 M3 阻断并回退：
M1.5a 建范围/模型/Variant/View → M1.5b 建标准片段 →
重新发布并接受 M2 的 `generation_asset_bindings` → 再进入 M3。不得先接受含
基线扩展的 M3，再把生成模型和标准片段作为后补说明。

M2 的 `view_ids` 是本集允许下游选择的 View 契约集合，不是写作阶段决定的景别或机位；
M4b 为每镜从该集合选择实际 `view_id`。M4a 的可选场景正交/俯视附加板绑定 spatial model 与
`scope.sheet_profile` projection fragment，不创建 View，也不替代该集合中的普通 View plate。
M4a/M4b/M5 使用由 asset/model/variant/View（空间附加板为 sheet_profile）与按规范顺序排列的
fragment ID+hash 组成的 binding fingerprint；`pipeline` 逐层对账，漏资产、
越权新增、View/Variant 越界、片段换版或 shot/keyframe/motion fingerprint 不一致都会阻断。

`production_flow.image_result_gate` 默认 `prompt_only`，兼容只交付提示词的项目。质量优先生产
可切换为 `observed`：套件仍不调用媒体服务，外部生成后由授权观察者将逐规格结果证据写入
`.short-drama/evidence/production-observations.jsonl`。缺失或规格/参考槽/production profile
hash 过期时以 `BLK-M4A-RESULT-OBSERVED` 阻断 M4b；`active` 观察不等于质量接受。

## 时长预算：配置在 M0，唯一正式兑现点是 M4b

`short-drama.json#/format/target_seconds_per_episode`（权威配置）与决定记录里的集长选择
都存在且被接受，但**中途没有强制校验点**：分集地图、单集卡、节拍与剧本模板都不承载时长字段
（剧本格式规范明令不写时长）。唯一正式兑现点是 M4b 分镜的 SHT-16——分镜按
`target_seconds_per_episode` 核对本集 `duration_seconds` 加总并报告带符号差值，
`storyboard_check.py` 只核对这笔账算得对不对，**从不阻断**。

为把"密度不足"提前暴露（而不等到 M4b），工具在两个写作端位置给出**非阻断**提示：

- `publish` 剧本时按剧本文本粗估可演时长（对白 ~0.25s/字、动作行 ~2.5s/行、场景标题与
  生产标签各 ~1s），明显低于目标时在输出的 `warnings` 里报
  `estimated on-screen time ... below target_seconds_per_episode`。估算刻意粗糙、
  只对明显缺口警告，不替代 SHT-16 的精确账；
- `pipeline <project>` 对已有已接受剧本的每集报告 `duration_estimate`：
  `target_seconds / estimated_seconds / delta_seconds`，写作文档期间随时可看。

两个设计特性要注意：

- 地图阶段的容量量级估算（develop 的 STY-16）要求从本项目已接受集取样，**首集无基准时
  设计上跳过**——所以"63 集 × 2–3 分钟"这类匹配问题在首集必然拖到 M4b 才可测；
- 执行密度不足（剧本短、对白少）同样要到分镜报负差值才暴露；SHT-16 只报告不强制，
  放任会带病进入 M5 视频提示词。发现负差值后应回到写作层补密度（改剧本 → 重建 index →
  重新发布接受），而不是在分镜层凑时长。

详见 develop 的 `episode-design.md` 9.4（STY-16）与分镜的 `production-shot-grammar.md`
七之二（SHT-16）。

模型调用上限是另一笔账：`short-drama.json#/format/generation_limits/max_clip_seconds` 默认为
15 秒，由 M5 的 `generation_clip_check.py` 按镜头逐片段核对。它不改变 SHT-16 的影视镜头
边界；一个长镜头可以由多个 generation clip 连续覆盖。planned boundary 必须完整记录姿态、
位置、视线、双手持物和可见状态；真实 continuation 在通过 M5 前必须绑定上一片段的授权输出观察。

## 强制语义（enforcement: strict）

- `pipeline` 命令列出当前里程碑的全部阻塞项；strict 下存在阻塞项退出码 3，guided 下
  只报告不退出非零。
- 工具层直接拦停：图片提示词与分镜产物发布时，若 `visual_direction` /
  `production_profile` 未接受，`publish` 报错（视频提示词允许 unset 并保持
  `provisional`，与技能文档一致）。
- 接受 / 审查 / 交付闸门沿用生命周期命令既有强制：下游只消费 accepted，`package`
  只收 accepted + L1 fresh 终审，`verify` 复核交付包。
- M3 的形态门由 `pipeline` 阻塞项 `BLK-M3-FORM` 保证；设定播种不受此限。
- **形态接受是流程层动作，不是工具命令**：`project_tool.py` 的生命周期命令都不能把
  `visual_direction` / `production_profile` 置为 `accepted`——形态卡选择经创作者确认后，
  由模型按本技能路由把决定写入 `short-drama.json#/creator_authority`（状态置 `accepted`），
  再以 `pipeline` 确认 `BLK-M0-FORM` 解除。这是唯一的提升路径。
- `delivery_surface` 是实际打包门禁：未接受时 `pipeline` 报 `BLK-M7-SURFACE`，`package`
  同时直接拒绝；它不再只是流程提示。
- `BLK-M15-SCOPE`：资产未分级或未接受；`BLK-M15-MODEL`：模型、空间拓扑或视图不完整；
  `BLK-M15-FRAGMENT`：片段缺失、未接受或过期；`BLK-M2-ASSET-REF`：剧本未绑定基线资产；
  `BLK-PROMPT-COMPILE`：提示词自由改写或 manifest 不符；
  `BLK-M4A-ASSET-CONSUME` / `BLK-M4B-ASSET-CONSUME` / `BLK-M5-ASSET-CONSUME`：
  跨阶段资产覆盖或绑定链未闭合；`BLK-M5-GENERATION-CLIP`：单次模型调用超限、镜头覆盖
  有缺口/重叠、交接五槽位不完整、continuation 缺少观察证据，或片段续接与 shot/motion 引用不成立；
  `BLK-DERIVED-MARKDOWN`：可复制 Markdown 未绑定当前结构化源 hash、漏记录或编译文本漂移。
- `package` 自身复核本集 M2–M6，不接受“先打包、让 pipeline 继续报未完成”的半流程交付。
  经创作者决定省略的路径仍写入 manifest，并在该 artifact 的全部目标都已选择或省略后推进 delivered。
- 旧 pipeline 项目在 M2–M7 统一阻断。先完成并接受 M1.5a/M1.5b，再运行
  `project_tool.py upgrade-flow <project>`；没有 legacy 开关，也不自动迁移旧项目内容。

## 捷径（配置开关）

- **script-first**：`allow_script_first: true` 时只跳过 M1，然后进入 M1.5a；完成 M1.5b 后
  才进 M2，单集卡使用 `write_standalone`。
- **批量生产**：多集走 `batch-production.md`；接受回合一次确认 + `accept-batch`。

固定主线不提供“分支跳过”；用户显式调用单分支技能时只产出该项，不套用主线里程碑。

## 修订回环

`REVISE` → 对应 owner 定点修订 → 重新发布并接受 → L2 `delta_verify`（例行）或 L1 fresh
（越界大改 / 交付终审）。M6 首审默认 L1.5 冷读（`cold_read`）；类型基准（该项目该产物
类型的首次审查）仍走 L1。`pipeline` 的 M6 阻塞项在修订闭环完成前持续存在。

**例行审查全程当前上下文**：首审冷读 → REVISE 一次改全 → delta_verify 反审，零子
agent；`review-batch --episode <EP>` 一次应用整集结论。fresh 子 agent 只保留类型基准
首审、越界大改、交付终审三事件，且终审整集一次覆盖（`review-bundle --episode` + 一个
fresh reviewer）。`pipeline --episode` 报告整集 M6 是否全部 approve。

## 配置与命令

`short-drama.json#/production_flow`：

- `pipeline_version`：由套件管理，不可手工修改；
- `enforcement`：`strict` | `guided`；
- `allow_script_first`：`true` | `false`（唯一捷径开关）。
- `image_result_gate`：`prompt_only` | `observed`；后者要求外部结果的精确授权观察。

```text
python3 <core>/scripts/project_tool.py pipeline <project>              # 报告
python3 <core>/scripts/project_tool.py pipeline <project> --episode EP001
python3 <core>/scripts/project_tool.py pipeline <project> --set enforcement=guided
python3 <core>/scripts/project_tool.py pipeline <project> --set image_result_gate=observed
python3 <core>/scripts/project_tool.py upgrade-flow <project>            # 旧项目完成 M1.5 后升级
```

`pipeline` 输出 `current_milestone / next_action / blockers / completed / episodes`，
另附 `fresh_baselines`（已有非临时 fresh 审查结论的 owner 技能列表，五个已审产物类型各对应
唯一 owner，用于 L1 全量 vs L1.5 冷读的路由决策），来源是 state.json 的五轴与产物指针，
不依赖模型记忆。退出码：0 可继续；2 命令或配置错误；
3 strict 模式下当前里程碑存在阻塞项。
