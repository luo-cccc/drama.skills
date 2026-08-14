---
name: short-drama-assets
description: "为短剧建立并维护可稳定还原的人物、生物、场景、道具、载具和效果生成资产基线，也从剧本拆解角色/造型、场景/视图、道具/状态和跨场连续性。用户说‘做资产基线/角色三视图设定/场景空间模型/道具或载具设定/效果状态’、‘拆角色/场景/道具’、‘判断复用还是新变体’或拿现成剧本做视觉资产准备时使用；只产出文本/JSON/JSONL，不写最终资产图提示词，不生成图片或视频。"
license: MIT
---

# 短剧资产拆解

把剧本文字变成**可追溯、可复用、能接续状态**的生产资产。重点不是数出
多少人名和名词，而是回答：屏幕上具体需要什么、它与已有资产是不是同一个、
此刻是哪种造型/视图/状态，以及变化怎样传到下一场和下一集。

## 先定位套件

从本技能目录读取 `suite-ref.json`，按其中相对 `core_manifest` 定位唯一同级主技能与
套件清单；确认声明的 core、contract、recipe 和清单 hash 一致后再读写项目。
随后执行 [阶段契约](references/stage-contract.md) 的运行时预检：先恢复事务、读取状态，再进入本阶段。
该文件同时给出本阶段的所有权边界、需要从制作形态取得哪些输入，以及本阶段规则表；除核心套件元数据与执行速查（`execution-quickstart.md`）外，本技能不读取其他技能的文件。
例行命令速查见核心技能的 `references/execution-quickstart.md`；其余参考按需加载。

## 边界

- **M1.5a 强制基线**：M0 后、任何 M2 剧本接受前，先在 `设定集/generation/` 建立并接受
  资产范围、资产/空间/变体模型、视图契约与资产基线总览。`script-first` 只能跳过 M1。
- 按跨集复用、近景需要、空间调度和叙事关键性提出 `full/compact`，创作者最终接受；
  必需字段不得写“待定/未知/TBD”。按项目实际存在创建 `CREATURE/CSTATE`、
  `VEHICLE/VSTATE`、`EFFECT/ESTATE`，不为不存在的类别造空档。
- 资产事实只来自已接受剧本、已有 设定集、连续性和创作者补充；不擅改剧情。
- **设定播种例外**：在已接受剧本存在之前，身份层记录（Character/Location/Prop 及各自的
  基础 Look/View/State）可以从**已接受的 develop 产物**（故事引擎、创作简报中的人物、
  地点、关键道具）或**创作者直接描述**播种；播种记录的 `source_refs` 必须指向这些
  出处并标 `creator_acceptance.status: proposed`，不得伪装成剧本提取事实。
  播种只写身份层，不写单集 occurrence、decision 或连续性 delta。
- **剧本候选播种例外**：剧本首次引入 设定集 之外的新角色、地点或关键道具，而剧本
  本身尚未接受时，身份层记录也可以从 **candidate 剧本的精确 index 记录**播种：
  `source_refs` 绑定 screenplay-index 记录 ID/hash 并标 `authority: candidate`，
  `creator_acceptance.status: proposed`，以 candidate 发布。这打破“剧本等 设定集
  接受、设定集 等剧本接受”的双向等待——两者可在同轮作为 candidate 呈现；确认后先接受
  身份播种，再完成并接受资产等级、模型/View 和标准片段，最后由 write owner 重发布并接受
  带准确 generation 绑定的剧本。同样只写身份层，不补造单集证据，也不伪装成已接受剧本的
  提取事实。
- 始终读取 `short-drama.json#/creator_authority/{visual_direction,production_profile}` 中状态为
  `accepted` 的视觉方向与制作形态：形态决定哪些身份锚点在本项目里根本可被表达——以剪影为
  识别通道的形态与以面部结构为识别通道的形态需要不同的锚点集合；若状态为 `unset`，就向
  创作者给出选择，不从对话记忆补造。形态可以改变锚点的表达通道与颗粒度，不得反过来改写
  已接受的身份、地理、持物归属、可读文字政策或故事状态。
- 只拥有 Character/Look、Location/View、Prop/State、occurrence reconciliation
  和资产状态 delta。知识/信念/目标/关系/情绪等 story-state 可以在连续性
  ledger 中被追踪，但只是带 write/develop source pointer 的投影，不是 assets
  的第二份真相。剧本语义归 `short-drama-write`，镜头手位/走位归
  `short-drama-storyboard`，图片提示词归 `short-drama-image-prompts`。
- 同时拥有 `设定集/generation/asset-scope.jsonl`、`asset-models.jsonl`、
  `spatial-models.jsonl`、`variant-models.jsonl`、`view-contracts.jsonl` 和
  `asset-baseline.md`；标准提示片段与浏览库由图片提示词技能拥有。
- 可直接接收现成剧本，不强迫补创意开发、故事引擎或集纲。
- 只产出文本/JSONL；不调用图片、视频、音频模型或 provider API。

所有权边界见 [阶段契约](references/stage-contract.md)；只在需要时加载
下列专项参考，不要一次读完所有文件。

## 入口判断

0. **设定播种（剧本前）**：已有已接受的 develop 产物或创作者直接描述，而 设定集 缺少
   对应身份 → 进入播种模式：只写身份层记录（Character + 基础 Look、Location + 基础
   View、Prop + 基础 State），`source_refs` 指向 develop 产物或创作者决定记录，
   `creator_acceptance.status: proposed`，以 candidate 发布至 `设定集/*.jsonl`。
   播种让第一集写作和拆解就有可比对、可复用的身份库；不接受、不补造单集证据，
   也不把播种记录冒充为已接受资产。
0b. **剧本 candidate 引入了 设定集 之外的新元素**：剧本尚未接受且包含待播种身份 →
   按第 0b 节从 candidate 剧本的精确 index 记录播种身份层记录，与剧本 candidate
   同轮呈现给创作者；接受顺序是身份播种 → M1.5a 范围/模型/View → M1.5b 标准片段 →
   重发布并接受 M2 剧本，不让任何一边伪造已接受依赖。
1. **已有已接受的 `screenplay.md` 与 index**：直接拆解。
2. **已有资产 设定集，只需补集内出现与状态**：读取旧 ID（含 proposed 播种记录），先判复用，再提新项。
   拆解确认了播种身份在本集的呈现后，把对应记录的接受推进交给创作者决定；
   未接受的播种身份继续以 proposed 存在，下游按 candidate 引用规则临时消费。
3. **只有非 canonical 的中文剧本**：保留原字节到 `输入/`；调用 write owner
   产生最小规范化预览、语义 diff 和未映射片段。创作者接受前不发布
   `screenplay.md`，拒绝也不改变原稿。接受后直接回来拆资产，不虚构 development。
4. **用户只要局部结果**（如“拆本场道具”）：仍执行 occurrence → decision，
   但只呈现所问范围及它依赖的连续性，不用强迫走完整项目流程。

缺少 index 时，不凭行号冒充稳定来源；先请 write owner 对剧本建立 block ID/hash。

## 工作流

### M1.5a. 建立生成资产模型（强制）

1. 从已接受视觉方向、develop 产物、创作者描述或 candidate 剧本列出资产范围；
2. 为每项提出 `full/compact` 与依据，先让创作者接受范围；
3. `full` 固定通用字段与类型专属结构；`compact` 至少固定尺度、主轮廓、主材质/颜色、
   2–4 个识别锚点、状态边界、禁止漂移和标准观察方向；
4. 场景建立坐标、尺寸、区域、入口连接、锚点关系、动线、遮挡、固定光源和陈设边界；
   每项资产至少有一个绑定准确模型记录哈希的视图契约；
5. 运行 `scripts/asset_baseline_check.py <project>/设定集/generation --prompt-language <tag>`，
   按“资产等级 → 模型/视图”发布并接受，再交图片提示词技能建立标准片段。

### 0. 设定播种（剧本前，可选但推荐）

系列创作在第一集剧本之前先建立身份库，后续每集只做增量：

1. 读取已接受的 develop 产物（故事引擎/创作简报中的人物、地点、关键道具）或
   创作者直接描述；没有这些输入时不凭空播种。
2. 只写身份层：Character + 基础 Look、Location + 基础 View、Prop + 基础 State，
   字段从简——识别锚点、空间地理、形制/功能足以再次认出即可，不写单集状态。
3. `source_refs` 指向 develop 产物记录或创作者决定记录；`creator_acceptance.status`
   写 `proposed`，以 candidate 发布至 `设定集/*.jsonl`。
4. 向创作者呈现播种清单（见第 6 节的呈现顺序），一次确认可批量接受；
   接受后对应记录在原位硬化为 accepted，hash 刷新，下游引用随生命周期更新。
5. 播种不替代单集拆解：每集仍按第 1–5 步提取 occurrence 并判定
   reuse/new_variant/new_asset/unresolved；播种身份被剧本确认为新事实来源后，
   记录追加剧本 `source_refs`，不删除 develop 出处。

### 0b. 剧本候选播种（同轮打破双向等待）

剧本写了 设定集 之外的新元素时，剧本接受依赖新身份记录、身份记录又看似依赖
已接受剧本——按以下顺序解开，不让任何一边停摆：

1. 确认剧本已以 candidate 发布并有当前 index；只从 index 记录提取身份层事实，
   不凭对话记忆或整文件印象。
2. 只写身份层：Character + 基础 Look、Location + 基础 View、Prop + 基础 State，
   字段从简；`source_refs` 绑定精确 index 记录 ID/hash 并标 `authority: candidate`，
   `creator_acceptance.status: proposed`，以 candidate 发布至 `设定集/*.jsonl`。
3. 把播种记录与剧本 candidate 合并为一张审查清单呈现创作者（第 6 节顺序）；确认后按
   既有批量接受机制逐层执行：先接受播种身份，再建立并接受 M1.5a 范围/模型/View，交给
   image-prompts owner 建立并接受 M1.5b 标准片段，最后由 write owner 以这些准确记录级输入
   重发布并接受剧本。一个 `accept-batch` 只推进当前已就绪层，需要按依赖序重复运行。
4. 剧本 candidate 在接受前被修订：只重新发布受改动 block 波及的播种记录
   candidate，未波及记录不动；创作者暂缓的条目保持未决，不混入接受。
5. 剧本接受后仍按第 1–5 步做正式单集拆解；播种身份被确认后追加剧本
   `source_refs`（accepted authority），不删除候选播种的出处记录。

### 1. 先读事实边界

读取本集剧本/index、已有 设定集、上集 outgoing、创作者参考与文本政策，以及已接受的
视觉方向与制作形态。标记哪个版本已被接受。不要把旧 prompt、旧分镜或文件名当成资产真相。

### 2. 逐块提 occurrence，暂不创建资产

按 source block 收集出镜或生产必需的角色、地点、道具及其显式状态：造型、伤污、
所有者、持物手、位置、损坏、内容物、开闭、可读文字、时段、天气、光态和剧情作用。
每条 occurrence 先保持“剧本怎样写”的颗粒度，再与资产表对齐。

- 不猜“她”“那个人”“另一把钥匙”指谁；保留原称谓和证据，状态设为 unresolved。
- 区分出镜、画外声、屏幕/照片呈现、仅被提及；被提及不等于要做视觉资产。
- 不把每个名词都建档。只保留影响识别、复用、提示词、镜头或连续性的事实。
- occurrence 不反向 hash 引用未来 decisions；先写 locator，decision 再单向引用
  occurrence 的 exact snapshot。

方法与反例见 `references/occurrence-extraction.md`，记录形状见
`assets/occurrences.example.jsonl`。

### 3. 再做身份判断

把 occurrence 与已有 设定集 逐项比对，只给四种提案：

- `reuse`：持续身份和本次所需变体均已存在；
- `new_variant`：同一身份，但发现尚未进入 M1.5a/M1.5b 与 M2 的新 Look/View/State；
- `new_asset`：持续身份、空间地理或物体功能/形制确实不同；
- `unresolved`：证据不足或多个候选都成立，等待创作者选择。

先问“同一个东西什么没变”，再问“这次什么变了、为何变、何时有效”。服装、伤势、
湿污、灯光、道具开合通常不是新身份；相机角度和瞬时姿势通常连新变体都不是。
不要为了少建记录而合并真正不同的资产。详见
`references/identity-vs-variant.md` 与 `assets/decisions.example.jsonl`。

### 4. 写最小可识别 设定集

按类别沉淀，身份锚点与临时状态绝不混写：

- Character / Look：`references/character-and-look.md`；例见
  `assets/character-look.example.jsonl`
- Location / View：`references/location-and-view.md`；例见
  `assets/location-view.example.jsonl`
- Prop / State：`references/prop-and-state.md`；例见
  `assets/prop-state.example.jsonl`

每个新变体记录 base、变化、原因与有效范围。只写能帮助再次认出、复用、提示词
编写或连续性检查的事实；不堆砌“高级、精致、电影感”等泛化修饰。

### 5. 写变化，不复制整本 设定集

为交接所需的资产状态变化记录 before、after、剧本原因、开始/结束边界和受影响 binding。
重点检查造型/伤势、持物/所有权、道具状态、地点时段/天气/光态以及跨集 outgoing。
若为审查需要把知识或关系状态放进 ledger，只保存权威字段的 artifact/hash/
field pointer 及必要投影；修订仍路由到 develop/write owner。
镜头内部姿势、视线、左右手和站位由 storyboard 边界拥有；资产记录只引用，不抢写。
M3 只记录 occurrence、复用决定和相对基线的状态增量，不得重新定义基础外观。
每条已解析 decision 的 `proposed_binding` 必须同时写明与 occurrence 一致的 `identity_id`、
M2 当前 `generation_model_id`，以及显式 `generation_variant_id`；没有稳定变体时写 `null`，
不得用旧 Look/View/State ID 冒充 generation variant。每条 continuity after 采用同一规则。
Pipeline 2.0 中如果本步判断为 `new_asset` 或 `new_variant`，不得发布或接受该 M3 decision：
回退到 M1.5a 建立 scope/model/Variant/View，交给图片提示词 owner 建 M1.5b 片段，再让 write owner 重新发布并接受
包含该资产的 M2 `generation_asset_bindings`。完成后重做本集 occurrence/decision；这是前置资产遗漏，
不是允许 M3 扩写基线的例外。

详见 `references/continuity-delta.md` 与 `assets/continuity.example.jsonl`。

### 6. 给创作者看“决定”，而非只给清单

提交接受预览，按以下顺序呈现：

1. 建议复用（为什么是同一个）；
2. 建议新增变体（没变什么、变了什么、原因与有效期）；
3. 建议新增身份（区分它的持久证据）；
4. 未决项（原文证据、候选、每个选择的下游影响）；
5. 连续性变化与需带入下一集的 outgoing。

创作者可逐项接受、改名、合并、拆分或暂缓。**creator acceptance 是独立事实**：
抽取完成、结构校验通过、review 通过都不能替代创作者接受。单集拆解只发布被接受的
身份和变体；任何 unresolved 都不得进入 M4a，也不得编译到图片提示词或分镜 binding。
设定播种是例外：身份层记录可以 `proposed` 状态以 candidate 发布，下游按
`authority:candidate` 临时消费且产物保持 provisional，接受前不得硬化或交付。
剧本候选播种同样适用，并与剧本 candidate 同轮呈现；接受仍按身份播种 → M1.5a →
M1.5b → 重发布 M2 的依赖序推进。
若用户要求一次查看全链而中间没有接受回合，可生成 candidate 预览链：下游必须
标 `provisional`，ArtifactRef 加 `authority:candidate`，不得伪造 creator decision/
accepted snapshot，且不得交付。

### 7. 发布与修订

发布至 `设定集/*.jsonl` 及 `剧集/<EP>/assets/{occurrences,decisions,continuity}.jsonl`。
每个非权威重复值都携带 owner artifact/hash/field pointer。资产修改后只标记依赖该
ID/variant 的提示词、镜头和 review 为 stale；不要重写无关资产或 screenplay。

## 规则分类与阻断

- `structural_invariant`：occurrence 必有 source block/hash；decision 必属四类；
  variant 有 base/cause/validity；binding 必须解析到已接受 ID，或以 `authority:candidate`
  解析到 proposed 播种记录且消费产物保持 provisional。可机械阻断。
- `reviewed_invariant`：不可猜含混指代；不可把临时状态混入身份；delta 的剧情原因
  必须由证据支持。独立 reviewer 引用证据判定，owner 不自批。
- `craft_default`：身份不变时优先复用/变体；只跟踪下游有用事实。创作者可说明覆盖。
- `taste_option`：群演建为个体还是群组、同址空间拆分颗粒度、蒙太奇式跳变方式，
  由制作策略选择，不单独阻断。

## 完成条件

发布 C2 前使用 `references/asset-review-checklist.md`：来源和引用可解析；每个
occurrence 有明确 decision；未决项保持未决；身份/变体边界可信；连续性能够从
incoming 走到 outgoing；创作者已经接受本次变更（设定播种与剧本候选播种记录例外，保持 proposed
直到创作者确认）。最终 approval 必须交给
`short-drama-review`，本 skill 只修订自己拥有的资产事实。
固定主线还要求 M1.5a 已接受并通过机械校验；基线变化只使实际消费相关记录的下游失效。
