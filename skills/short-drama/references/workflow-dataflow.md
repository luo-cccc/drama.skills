# 端到端工作流与数据流

本页回答四个跨阶段问题：内容从哪里来、每一步产出什么、下游实际消费什么，以及内容
变化后哪些结果必须重做。里程碑的强制入口和出门条件以
[production-pipeline.md](production-pipeline.md) 为准；命令行为以
[lifecycle-commands.md](lifecycle-commands.md) 为准；所有权和引用形态以
[contract-and-ownership.md](contract-and-ownership.md) 为准。

## 总图

```mermaid
flowchart LR
    Z["M0 项目与制作基线"] --> B["M1 开发契约"]
    A["长篇原著 / 点子 / 多集整稿"] --> B
    A --> X["可选原著分析或整稿索引"]
    X --> B
    B --> C["M1.5a 生成资产模型"]
    C --> D["M1.5b 标准提示片段"]
    D --> E["M2 单集剧本与资产消费声明"]
    E --> F["M3 occurrence / decision / continuity"]
    F --> G["M4a 资产图片规格"]
    G --> H["M4b shot / keyframe"]
    H --> I["M5 motion / generation clip / container"]
    I --> J["M6 独立审查"]
    J --> K["M7 package / verify"]
```

流程里有三种不同边界，不能混为一谈：

1. **叙事与剪辑边界**：scene、beat、shot，决定观众看到的结构和镜头起止。
2. **模型执行边界**：generation clip，只解决单次视频模型调用上限，不改写 shot。
3. **交付封装边界**：delivery container，只描述若干镜头或片段如何送入特定交付路由。

## 三种长内容入口

| 输入 | 处理方式 | 进入固定主线的位置 |
|---|---|---|
| 长篇小说或连载 | `short-drama-novel-analyze` 建唯一章节索引，先抽样快评，再逐章提取、聚合剧情单元和分集候选；正文不一次性塞入上下文 | 候选交给 develop，形成 M1 的创作契约 |
| 点子、梗概或创作者口述 | develop 建 `creative-brief.md`、`story-engine.md`、`episode-map.jsonl` | M1，三份文件必须分别 accepted |
| 已有多集完整剧本 | develop 的 `episode_intake.py` 建精确索引、逐集切片并从磁盘断点续跑；不反复加载整季 | 可先补齐 M1；明确启用 script-first 时只跳过 M1，仍必须完成 M1.5a/M1.5b |

原著分析、整稿索引和抽样结论都是**输入整理层**，不自动成为剧本、资产或镜头权威。
真正进入固定主线前，仍需形成已接受的开发契约，或由创作者明确选择 script-first。

## M0-M7 的生产与消费

| 阶段 | 主要生产者 | 直接消费 | 权威产出 | 主要下游 |
|---|---|---|---|---|
| M0 | core / 创作者 | 项目初始化值、制作选择 | `short-drama.json` 中语言、画幅、目标时长、生成上限、制作形态与交付面 | 全部阶段 |
| M1 | develop | 原著分析、点子或整稿索引 | creative brief、story engine、episode map | M1.5、M2 |
| M1.5a | assets | M0 形态、M1 范围、设定播种 | asset scope、身份模型、空间拓扑、variant、View 契约 | M1.5b、M2-M5 |
| M1.5b | image-prompts | M1.5a 模型与项目 prompt language | canonical fragments 结构化记录；Markdown 仅为绑定源哈希的投影 | M2、M4a-M5 |
| M2 | write | episode map、资产模型和片段允许集合 | episode card、beats、screenplay、screenplay index、实际 generation asset bindings | M3、M4b、M6 |
| M3 | assets | 当前剧本块与 M2 资产声明 | occurrence、reuse decision、continuity/state delta | M4a、M4b、交付摘要 |
| M4a | image-prompts | M2 允许资产、M3 决定、M1.5 模型与片段 | image prompt specs；Markdown 为可复制投影；`observed` 模式另需项目私有 generated-result observation | 外部资产图生成、授权观察、M4b/M6 |
| M4b | storyboard | 剧本索引、M3 连续性、M4a 资产覆盖 | coverage、shots、start keyframes；每镜选择实际 View 并冻结边界 | M5、M6 |
| M5 | video-prompts | accepted shot/keyframe 与同一资产指纹 | motion specs、generation clips、可选 delivery containers；Markdown 为可复制投影 | 视频模型调用、M6、M7 |
| M6 | review | 冻结的 accepted 目标和 review bundle | findings、verdict、修订范围 | owner 修订或 M7 |
| M7 | core | M2-M6 完整状态、delivery surface、实际选择/省略决定 | manifest、checksums、asset baseline bundle | 制作交接与归档 |

下游消费的不是文件名相似或一段复制文本，而是明确的 owner、路径、文件 hash、记录 ID，
必要时还包括字段指针。上游记录换版、删除或失去唯一 accepted provider 时，消费者会变为
`stale`，必须重新发布、接受和审查。

## 结构化权威与 Markdown 投影

以下 Markdown 是面向人和模型复制使用的**派生视图**，不是第二份可自由编辑的权威：

| Markdown | 结构化权威 |
|---|---|
| `canonical-prompt-library.md` | `canonical-fragments.jsonl` |
| `image-prompts.md` | `image-prompt-specs.jsonl` |
| `keyframe-prompts.md` | `keyframes.jsonl` |
| `video-prompts.md` | `motion-specs.jsonl`，并绑定 `generation-clips.jsonl` |

发布时会校验当前源 hash、每条记录 ID 和按顺序编译的正文。`video-prompts.md` 还必须列出
generation clip ID、可选 container ID，并绑定 generation clip 文件 hash。人工可改善排版，
但不能省略记录、调换编译语义或把旧缓存当成当前版本。

## 长镜头与 15 秒模型上限

影视 shot 可以长于 15 秒。M4b 仍按叙事和剪辑需要决定 shot 的完整时长；M5 再把它拆成
一个或多个连续 generation clip：

```text
SHOT-001  0s ------------------------------------------- 38s
CLIP-001  0s -------- 15s
CLIP-002              15s -------- 30s
CLIP-003                            30s ---- 38s
```

机械检查要求：

- 每个 clip 不超过 `short-drama.json#/format/generation_limits/max_clip_seconds`；默认 15 秒。
- 同一 shot 的 clips 从 0 开始连续覆盖到 shot 结束，不得有间隙、重叠或改变 shot 时长。
- 第一个 clip 独立从 `shot_start` 开始；后续 clip 指向紧邻的上一 clip。
- 每次 planned handoff 都携带 `pose`、`position`、`gaze`、`hands_and_props`、
  `visible_state` 五项边界状态。
- `independent` 表示按计划边界重新起一次生成；`continuation` 只有在项目明确支持时可用，
  且必须把上一 clip 的 `output_observation_ref` 原样绑定为当前 handoff 的
  `observation_ref`。

因此这不是留给人工临时判断的隐含步骤。项目已经能表达和校验拆分计划；真正调用外部视频
模型、保存每次输出观察并把观察引用写回项目，仍由执行者或外部生成系统完成。

## 生命周期与失效

```mermaid
flowchart LR
    A["本地候选内容"] --> B["publish: candidate"]
    B --> C["creator decision"]
    C --> D["accept: accepted"]
    D --> E["review: approve / revise"]
    E -->|"revise"| A
    E -->|"approve + L1 fresh final"| F["package"]
    F --> G["verify: 校验和与包内容复核"]
```

- `accepted` 表示创作者采用准确版本，不等于已经通过独立审查。
- M6 覆盖本集 M2-M5 的 accepted 产物；`package` 会再次确认 M2-M6 全部闭合，并在成功
  写包时推进交付状态；`verify` 只复核已交付包。
- 合法 omission 只决定交付包中不携带哪个**已经纳入本集覆盖范围**的路径，必须有 creator
  evidence。它不能替代未生产的阶段，也不能绕过 M6。
- 当一个 artifact 的全部目标都被选择或被合法省略，它会在 manifest 中完成结算并推进
  `delivered`，避免 M7 因已批准的省略永久悬空。
- 修改已接受上游后，所有精确绑定旧 hash/记录的下游都应视为 stale；按 owner 从最早失效点
  向后重建，不在交付层补写解释。

## 交付包实际携带什么

`asset-baseline-bundle.json` 不是整个设定集的复制品，而是本集**实际消费集合**及其证据：

- M1.5 的资产、模型、variant、View 和 canonical fragment 当前记录与 hash；
- M2 的允许集合与实际 generation asset bindings；
- M3 occurrence、decision 和 continuity/state delta；
- M4a asset board 覆盖；
- M4b shot、keyframe 和有序资产指纹；
- M5 motion → generation clip → shot 的窗口、顺序、执行模式和 handoff；
- 存在时的 delivery container 成员关系；
- 各层差异和未闭合问题。

这份摘要供交付接收方回答“这一镜到底消费了哪个版本的什么内容”，不替代源 artifact。

## 日常检查顺序

1. `preflight <project>`：校验套件、恢复事务、读取状态。
2. `pipeline <project> [--episode EP001]`：定位最早未闭合里程碑。
3. 只读取该里程碑的 accepted 输入和负责技能文档，生产候选并运行机械检查。
4. `publish` → creator decision → `accept`，再由下游消费。
5. M6 使用 review bundle 完成冷读、修订和终审。
6. M2-M6 全部完成后执行 `package`，最后执行 `verify`。

命令速查见 [execution-quickstart.md](execution-quickstart.md)，批量节奏见
[production-sop.md](production-sop.md) 和 [batch-production.md](batch-production.md)。
