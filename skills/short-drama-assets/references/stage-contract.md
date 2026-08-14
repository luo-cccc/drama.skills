# 资产阶段契约

## 目录

- [运行时预检](#运行时预检)
- [所有权边界](#所有权边界)
- [制作形态需要什么](#制作形态需要什么)
- [本阶段规则](#本阶段规则)

本文件是本技能的所有权、形态输入与规则表；公共运行时预检见同一套件 core 的
`references/runtime-preflight.md`，本文件只保留本阶段特有的预检补充，不逐份重复公共段落。

## 运行时预检

进入本阶段前先完成这套轻量预检。它只检查安装完整性、项目事务状态和已记录的精确引用，
不评价创作内容。公共预检（验证安装、恢复事务再读状态、只通过公开生命周期写入、读共享
JSON/JSONL 时声明记录绑定，含剧本经 `screenplay-index.jsonl` 记录 ID 绑定）见
`references/runtime-preflight.md`，不在本文件重复。

## 所有权边界

- **本阶段拥有**：人物/生物/地点/道具/载具/效果的身份与变体；M1.5a 的资产范围、
  资产/空间/变体模型、视图契约和资产基线总览；资产状态变化记录与场景/单集资产台账；
  出现证据的提取；剧本前从已接受 develop 产物或创作者描述播种的身份层记录，以及
  剧本 candidate 首次引入新元素时从其精确 index 记录候选播种的身份层记录。
- **本阶段继承**：剧本给出的身份、地理与文字政策；故事状态条目是开发/剧本的只读投影。
- **本阶段不越权**：不决定镜头构图与动作终态，不改写剧情事实。台账里的故事状态只带来源
  指针，不构成第二个取值权威；播种记录不伪装成已接受剧本的提取事实，不补造单集证据。

## 制作形态需要什么

视觉风格不是贴在提示词前面的标签。创作者已接受的视觉方向与制作形态由项目层决定并传入，
**本技能不加载形态卡，也不自行选择形态**；本节只说明本阶段需要形态回答什么、以及拿到
答案后投影成哪些字段。

形态决定属于 `craft_default`：创作者说明理由即可覆盖。形态不能创造新的
`structural_invariant`，也不能改写身份、地理、持物归属与可读文字政策。审查者不得单凭
形态偏好阻断交付。

不要用“加一句风格前缀”处理形态差异。前缀只改变检索标签；形态改变的是**必须出现和
可以省略的字段**，只有后者会被执行，也只有后者能被审查。

本阶段要向形态决定问四件事：

- **身份锚点载体**：靠什么让人物跨镜可辨认——轮廓、线条、比例、结构差异还是材质。
- **层级拆分**：身份层、环境层、可动层、效果层各包含什么，同一事实由谁负责。
- **材质与光色**：材料怎样响应光，色彩关系承担什么信息；不罗列质量词。
- **连续性必带项**：本形态下哪些字段必须逐镜传递、哪些可以省。不同形态答案差别很大，
  不要照抄别的形态的必带串。

本阶段新增：轮廓、材料、层拆、稳定比例与版本差异。

## 本阶段规则

### `AST`

| ID | 分级 | 规则 |
|---|---|---|
| AST-01 | structural_invariant | 先按来源 block/hash 提取 occurrence，再创建或绑定资产。 |
| AST-02 | structural_invariant | 每条 occurrence 必须判定为 `reuse`、`new_asset`、`new_variant` 或 `unresolved` 之一——不得猜测含混的称谓或代词。occurrence/decision/delta ID 各自在本集唯一；occurrence 的 `source_ref` 与 `source_blocks`、decision/continuity 的剧本 cause 必须解析到当前已接受 screenplay-index 记录及其准确记录哈希。Pipeline 2.0 只有已解析到 M2 基线的 `reuse` 可以完成 M3；decision 的 asset kind/identity 必须与 occurrence 一致，并显式声明匹配 M2 的 `generation_model_id` 与 `generation_variant_id`（`null` 表示基线）。`new_asset/new_variant` 回退 M1.5/M2，`unresolved` 保持阻断。 |
| AST-03 | craft_default | Character/Look、Location/View、Prop/State 分开建表。 |
| AST-04 | reviewed_invariant | 持久识别锚点与可变状态不得混写。 |
| AST-05 | structural_invariant | 每个下游绑定必须解析到已接受身份与有效变体；仅当消费产物保持 provisional、引用标记 `authority:candidate`、且在被绑定记录接受前不得接受时，才允许绑定 proposed（candidate 权威）播种记录。 |
| AST-06 | craft_default | 只跟踪识别、复用、提示词编写或连续性所需的资产事实。 |
| AST-07 | reviewed_invariant | 持久的声音身份与读音引用以参考音频为音色载体（`voice_direction.reference_ref`；无参考时保持 `null` 并写明待选型，不用文字冒充音色），文字只承担选型判据与专名发音；同场级的呼吸、情绪、音量与表达状态分开保存。 |
| AST-08 | reviewed_invariant | 剧本前播种记录只覆盖身份层（Character/Look、Location/View、Prop/State），`source_refs` 引用已接受的 develop 产物或创作者决定，`creator_acceptance.status` 保持 `proposed` 直到创作者接受；播种不得补造单集证据，也不得声称剧本出处。 |
| AST-09 | structural_invariant | 剧本首次引入 设定集 之外的元素且剧本本身仍是 candidate 时，身份层播种记录可以把该 candidate 剧本的精确 screenplay-index 记录 ID/hash 作为 `source_refs` 并标 `authority: candidate`，`creator_acceptance.status` 保持 `proposed`，以 candidate 发布；确认后严格按“身份播种 → M1.5a → M1.5b → 重发布并接受 M2”推进。被绑定剧本 block 在接受前发生变化时，受影响的播种、基线和片段重新发布；单集 occurrence、decision 与连续性 delta 仍等待已接受剧本。 |
| AST-10 | structural_invariant | Pipeline 2.0 的 M3 不得发布或接受 `new_asset` decision。若拆解仍发现新身份，回退补齐 M1.5a/M1.5b，重新发布并接受含准确 generation 绑定的 M2，再重做 M3。 |
| AST-11 | structural_invariant | `continuity.jsonl` 每条 delta 必须绑定 M2 内 subject、精确剧本 cause、before/after/effective range 与受影响绑定；`after.generation_variant_id` 必须显式为 M2 变体或 `null`。空对象、未映射旧 Look/View/State 或只写自然语言变化不能完成 M3。 |

> 记录层的 `creator_acceptance.status: proposed` 是**播种状态**，与项目层五轴之一的
> `creator_acceptance`（枚举 `not_requested / pending / accepted / rejected`）同名但取值集不同：
> `proposed` 只出现在身份层播种记录里；项目层“待创作者接受”用 `pending`，不要混写。

### `CON`

| ID | 分级 | 规则 |
|---|---|---|
| CON-01 | structural_invariant | 相衔接的结束状态与下一开始状态一致，或有明确的负责人修订。 |
| CON-02 | reviewed_invariant | 知识、伤势、归属、天气、光线或物理状态不得在没有剧情原因的情况下瞬移或倒退。 |
| CON-03 | craft_default | 只跟踪与下游相关的变化，不把整本 设定集 复制到每一镜。 |
| CON-04 | structural_invariant | 一条变化记录必须写明 before、after、原因/来源、有效范围与受影响绑定。 |
| CON-05 | taste_option | 已声明的蒙太奇、省略、梦境或主观画面可以有意打破普通连续性。 |
| CON-06 | structural_invariant | 一条变化的受影响引用覆盖全部现有消费方；未来消费方在落实前保持 locator。 |

规则分级由高到低：`structural_invariant`（结构缺陷，阻断）、
`reviewed_invariant`（需证据判断）、`craft_default`（常用做法，可覆盖）、
`taste_option`（创作者选择，不作缺陷）。创作者已接受的事实优先于本表。
