# video.skills — 短剧创作技能套件

一套符合 [Agent Skills](https://agentskills.io) 标准的中文短剧 / 漫剧创作技能套件，
覆盖从长篇原著分析或点子开发到交付的完整流水线：原著分析（可选）→ 开发 → 生成资产基线 → 写作 → 单集资产增量 → 图片提示词 → 分镜 →
视频提示词 → 审查，外加一个项目路由 / 初始化 / 交付的主技能。

套件基于文件系统工作：所有项目产物（剧本、设定集、分镜、提示词、审查结论）都是
磁盘上的 Markdown / JSON / JSONL 文件，带候选发布（candidate）、创作者接受
（acceptance）、独立审查与交付打包的生命周期管理。纯文本推理，不调用任何
图片 / 视频 / 音频生成模型或供应商 API。

## 最新更新

### 2026-08-14 — 0.5.1

- 修复固定流程闭环：M1 必须逐项接受三份开发产物，`package` 必须在 M2–M6 全部完成后执行，
  经创作者批准省略的产物会作为已结算交付推进 M7。
- M3 剧本引用统一使用 index 文件 hash 与 block ID，分拆发布的 occurrences、decisions、
  continuity 可在一次批量接受中完成，并与 pipeline 使用同一套门禁。
- 未改动的剧本 block 不再因其它段落修订、位置移动或父文件 hash 更新而连锁失效；自动记录
  绑定无法唯一解析时安全退回整文件绑定，显式绑定仍保持严格校验。
- `accept-batch` 会按依赖关系多轮推进；`decide --force` 保留旧决定并写入可审计的替代证据，
  不再因覆盖证据文件导致下游 hash 漂移。
- 支持直接发布已位于目标路径的候选文件；资产基线允许明确为空的可选特征集合；标准提示
  片段库可由结构化源确定性导出，不再需要手工拼装 Markdown。
- 派生 Markdown 现在绑定当前结构化源 hash，并逐项包含编译文本/片段、generation clip 与容器 ID；
  自由改写、漏项、换版或过期缓存会在发布前阻断。
- generation clip 的 planned boundary 必须包含姿态、位置、视线、双手持物和可见状态；真实
  continuation 必须绑定上一片段的授权输出观察。clip 单文件审查也会运行 VID-22 机械校验。
- `asset-baseline-bundle.json` 新增 shot → motion → generation clip 和可选 delivery container
  执行链摘要。pipeline 升至 2.0.1，套件升至 0.5.1，契约升至 `1.3.1-draft`。
- 文档按入口、流程、数据流、命令、契约和维护重新分层；新增长篇输入到交付、结构化权威到
  派生 Markdown、长 shot 到 15 秒 generation clip 的端到端消费说明。
- 写作阶段新增私有写前包与可持久化质量报告：连续项目从已接受的分集地图读取合同与近期剧本，
  `write_standalone` 从单集卡读取；报告随 `review-bundle` 交给独立审查。连续地图同时可用
  故事引擎的 Hook 账本核对稳定 ID、兑现计划与终态，避免地图和账本分别漂移。

完整记录见 [发布说明](docs/releases/release-notes.md)。

## 技能清单

| 技能 | 职责 |
|---|---|
| `short-drama` | 主路由：项目初始化 / 恢复 / 状态 / 交付打包、本地创作台 Dashboard、制作形态与视觉方向决定、生命周期工具（`project_tool.py`） |
| `short-drama-novel-analyze` | 长篇原著分析：章节索引、抽样改编快评、逐章功能提取、剧情单元、改编价值与分集候选 |
| `short-drama-develop` | 把小说、想法或梗概发展成改编方案、故事引擎、导演阐述、分集地图与连载义务账本 |
| `short-drama-write` | 编剧：单集契约、因果节拍、私有写前包、可拍摄 Markdown 剧本、质量检查、剧本索引与配音本 |
| `short-drama-assets` | 生成资产基线：人物/生物/场景/道具/载具/效果模型、空间拓扑与视图；单集增量和连续性 |
| `short-drama-image-prompts` | 标准提示片段、确定性提示编译器、资产图片提示词与 Look Development 文本规格 |
| `short-drama-storyboard` | 原文覆盖、镜头设计、连续性边界与冻结关键帧提示词 |
| `short-drama-video-prompts` | 逐镜视频提示词与运动规格（表演、运镜、声音、时长） |
| `short-drama-review` | 独立审查：结构校验、模板感诊断、修订请求与交付终审 |

## 目录结构

每个技能都是一个标准 skill 包：`SKILL.md`（YAML frontmatter：`name` /
`description` / `license`）+ 可选的 `scripts/`、`references/`、`assets/`。

```text
video.skills/
├── skills/                       # 标准 skills 仓库容器：9 个技能包
│   ├── short-drama/              # 主技能（core）
│   │   ├── SKILL.md
│   │   ├── suite-manifest.json   # 套件清单：全部文件的 SHA-256
│   │   ├── scripts/              # project_tool.py / suite_verify.py / dashboard_server.py
│   │   ├── references/           # 执行速查、固定生产流程、批量生产、生命周期命令等
│   │   └── assets/
│   ├── short-drama-novel-analyze/
│   │   ├── SKILL.md
│   │   └── scripts/novel_index.py
│   ├── short-drama-develop/
│   │   ├── SKILL.md
│   │   ├── suite-ref.json        # 指向 core 清单及其 hash
│   │   └── ...
│   ├── short-drama-write/
│   ├── short-drama-assets/
│   ├── short-drama-image-prompts/
│   ├── short-drama-storyboard/
│   ├── short-drama-video-prompts/
│   └── short-drama-review/
├── tests/                        # Python 回归测试 + Dashboard Node 测试
├── docs/                         # 文档导航、发布说明与仓库维护手册
├── .github/workflows/suite.yml   # CI：三平台 × Python 3.10/3.14，含固定 Ruff 与 Node 20
└── tools/
    └── update_suite_manifest.py  # 改动技能文件后重建清单（仓库级维护工具，不进套件）
```

9 个技能构成一个版本锁定的套件：`suite-manifest.json` 钉住全部文件的 SHA-256，
各子技能的 `suite-ref.json` 钉住清单自身 hash；混装、缺件或改动都会被运行时
预检拒绝。

## 文档导航

- [文档总入口](docs/README.md)：按第一次使用、日常执行、契约查询和仓库维护分类。
- [端到端工作流与数据流](skills/short-drama/references/workflow-dataflow.md)：长篇输入、
  M0-M7 生产/消费关系、结构化权威、15 秒 generation clip、审查与交付闭环。
- [执行速查](skills/short-drama/references/execution-quickstart.md)：例行命令和高频错误。
- [固定生产流程](skills/short-drama/references/production-pipeline.md)：里程碑顺序与强制门禁。
- [生命周期命令](skills/short-drama/references/lifecycle-commands.md)：命令参数、接受、审查、打包和恢复。
- [契约与所有权](skills/short-drama/references/contract-and-ownership.md)：权威、引用、stale、隐私与恢复。

## 安装

仓库采用标准 skills 仓库布局：9 个技能包放在 `skills/` 容器下。安装时复制
`skills/` 内的 9 个技能目录本身（不带 `skills/` 容器）到任一 skills 发现路径：

```bash
# 用户级（任选其一）
cp -r skills/short-drama* ~/.config/agents/skills/
cp -r skills/short-drama* ~/.kimi/skills/
cp -r skills/short-drama* ~/.claude/skills/

# 项目级
cp -r skills/short-drama* <project>/.agents/skills/
```

或使用支持 `--skills-dir` 的运行时，将本仓库根目录（标准 `skills/` 容器布局）或
`skills/` 目录作为技能发现根，取决于运行时的解析约定。

## 完整性校验

安装或修改后运行套件自带校验器（需要 Python 3.10+）：

```bash
python3 skills/short-drama/scripts/suite_verify.py
```

通过时输出已校验技能和文件的摘要；hash 不一致、缺件或混入额外
可执行文件时会失败并拒绝写入项目。

校验器每次都重算全部文件的 SHA-256；文本先规范化为 LF，二进制按原始字节计算，因此
LF/CRLF 安装等价而二进制变化仍会失败。大小与 mtime 不再作为缓存信任依据，避免等长修改
并恢复时间戳后复用旧摘要。`--full` 与 `--no-cache` 仍为旧调用保留兼容，但都执行全量哈希。

日常入口推荐单进程 `preflight`：`python3 skills/short-drama/scripts/project_tool.py
preflight <project>` 在一次解释器运行内完成套件校验、事务恢复与状态摘要，替代三次
独立命令并输出一份紧凑 JSON（退出码 0 可继续、2 套件失败、3 有阻塞事务）。

改动任意技能文件后，用仓库自带的工具重建清单，保持版本锁定：

```bash
python3 tools/update_suite_manifest.py
```

它重算全部发布技能文件的 SHA-256，写回 `suite-manifest.json` 并同步子技能的
`suite-ref.json`；噪声规则与 `suite_verify.py` 保持一致，未改动时输出与当前清单
完全相同的 hash（幂等）。

维护者应按 [仓库维护手册](docs/maintenance.md) 运行 compileall、Ruff、Python/Node
测试、清单重建与全量校验。`__pycache__/`、`*.pyc`、`.ruff_cache/`、`.DS_Store`
和 `.zcode/` 是本地噪声，不应提交。

## 测试与持续集成

仓库自带 stdlib-only Python 测试套件；Dashboard 前端另有一组无 npm
依赖的 Node 测试。Windows 上部分 Dashboard POSIX-dirfd `ProjectStore` 用例按设计跳过，
真实 HTTP handler 测试仍在 Windows 执行：

- **一致性测试**（`test_noise_consistency.py`）：噪声集一致性、清单与磁盘内容一致性、
  清单重建幂等、套件校验与 9 个技能契约；
- **生命周期冒烟测试**（`test_lifecycle_smoke.py`）：真实驱动 CLI 走完整条链路——
  零手工 hash 的 accept/review、`review-batch --episode` 过滤、输出语言契约
  （默认值 / 自定义 / 畸形 tag 拒绝 / 旧项目回退）、`--input-record-auto` 自动收集、
  `unpublish` 撤销与已接受保护、review-batch 排序（fresh 最后）、verdict 聚合报错、
  `accept-batch` 幂等重放、依赖拓扑重试与篡改决定拒绝、`decide --force` 不可变替代决定与 `--output` 路径
  约束、剧本索引过期与时长不足警告、`pipeline` 的 `duration_estimate` 报告、带
  `previous_source_ref` 血缘的修订索引发布。
  另覆盖委托创作者决定、M2 完整文件门禁、外部编辑实时失效、delivery_surface 硬门禁、
  交付省略证据和 review bundle 绑定。
- **校验脚本测试**（`test_check_scripts.py`）：驱动六个"机械账"校验器的真实函数——
  分镜时长加总（SHT-16）、运动显式计时（VID-04）、交付容器调和（VID-13/15）、
  generation clip 模型调用上限与完整覆盖（VID-22）、配音稿一致性、剧本索引——各自覆盖通过与失败路径。
- **资产基线与编译测试**：六类资产的 full/compact 通过和缺字段失败，视图/片段哈希失效，
  编译顺序、幂等、片段篡改、重排与输出篡改。
- **Dashboard 测试**（`test_dashboard_server.py`）：回环 / Host / Origin 判定、字节范围
  解析、路径遍历与百分号编码拒绝、真实会话 / Cookie / API 前缀、安全响应头与 PUT 路由，
  以及项目发现 / 读 / 写 / 版本冲突 / 只读保护 / 非法 JSON 拒绝；
- **安全回归测试**（`test_security_regressions.py`）：可移植路径碰撞、事务 manifest
  碰撞、路径置换检测、严格 JSON、画幅比例和版本一致性；
- **多集整稿测试**（`test_episode_intake.py`）：自动/手工边界、中文集号、CRLF 字节切片、
  非连续断点、批量合并、幂等重放、严格 JSON 和异常时不覆盖旧候选；
- **原著分析测试**（`test_novel_index.py`）：中文章号、目录识别、分卷重号、来源复验、
  全书抽样、覆盖率、所有权、旧代码页输出和严格 JSON；
- **Dashboard 前端测试**（`test_dashboard_app.js`）：内容分组、创作者可见投影、状态文案、
  JSONL 容错和保存状态等纯函数。

```bash
python3 -m unittest discover -s tests -v
node --check skills/short-drama/assets/dashboard/app.js
node tests/test_dashboard_app.js
```

CI（`.github/workflows/suite.yml`）在 Ubuntu / macOS / Windows × Python 3.10 / 3.14
矩阵上执行：编译全部工具脚本、运行 Python 测试、使用 Node 20 检查 Dashboard 前端，
并用 `--no-cache` 全量校验套件清单；独立 lint job 使用固定版本 Ruff。

## 文件系统与数据安全

- 项目路径以 Unicode NFC + 大小写折叠后的身份判断冲突。`Foo.md` / `foo.md`、正反斜杠
  和组合字符别名在所有平台统一拒绝，避免项目移动到 Windows 或 macOS 后覆盖文件。
- 路径分量同时拒绝 Windows 保留设备名、`< > : " | ? *`、控制字符以及尾随空格/句点。
- 所有 JSON/JSONL 入口拒绝 `NaN`、`Infinity` 和 `-Infinity`；分镜、运动与容器时长必须是
  有限数字，输出也不会生成非标准 JSON。
- `init --aspect-ratio` 只接受正数 `宽:高`，例如 `9:16`、`16:9`、`2.39:1`。
- `init --max-clip-seconds` 设置单次视频模型调用上限，默认 15 秒；长镜头由
  `generation-clips.jsonl` 连续覆盖，不需要为了模型上限改写剪辑边界。
- POSIX 发布和恢复使用固定目录描述符与 `O_NOFOLLOW`；Windows CLI 在读取候选源时复核
  打开句柄的文件身份。未知外部编辑仍保留冲突副本并阻断事务。
- Dashboard 继续只在 macOS/Linux 启动，不提供不安全的 Windows 路径降级；Windows 使用 CLI。

详细命令约束见 [项目命令与审核记录](skills/short-drama/references/lifecycle-commands.md)，
维护和回归要求见 [仓库维护手册](docs/maintenance.md)。

## 使用入口

意图不明确或涉及项目初始化 / 恢复 / 交付时从 `short-drama` 进入；明确的写作、
资产、提示词、分镜或审查请求可直接使用对应子技能。剧本引入设定集之外的新元素时，
资产技能支持从 candidate 剧本做候选播种；确认后按身份播种 → M1.5a → M1.5b →
重发布并接受 M2 的顺序推进，不会形成双向等待或越级接受。

长篇小说先由 `short-drama-novel-analyze` 建立唯一章节索引并做抽样快评；确认值得全量拆解后，
再完成逐章提取、聚合和分集候选，交给 `short-drama-develop` 形成真正的改编契约。已有多集
完整剧本则由 develop 的 `episode_intake.py` 建一次索引，之后只读取当前集并从磁盘断点续跑。

跨阶段内容如何生产、被谁消费和何时失效，先看
`skills/short-drama/references/workflow-dataflow.md`。逐集生产按
`skills/short-drama/references/production-pipeline.md` 的 pipeline 2.0 固定流程执行：
`python3 skills/short-drama/scripts/project_tool.py pipeline <project>` 报告当前位置、
下一步与阻塞项；`enforcement: strict` 下存在阻塞项退出码 3，图片提示词与分镜的形态
依赖在发布时直接拦停。`script-first` 只跳过 M1；M1.5a/M1.5b 必须完成。旧项目先完成并接受
M1.5，再运行 `upgrade-flow` 才能推进 M2–M7。

输出语言契约：`init` 写入两个独立字段——`#/language` 管创作者可读内容（默认 `zh-CN`），
`#/format/prompt_language` 管提示词正文（默认 `en`），均在 init 校验 BCP 47 形态并由
`status` 报告；改动一个不得静默改另一个（见 `contract-and-ownership.md`）。
确定性编译生成的章节标题同样跟随 `prompt_language`；语义顺序始终为任务/固定基线/
状态增量/View/当前任务/排除项。

记录级绑定默认自动：`publish` 的 `--input-record-auto`（默认开）从候选输出里指向已声明
输入的结构化 refs 自动收集 `record_id`，一个 8 角色的文件不用手写 8 条
`--input-record`——设定集追加新身份不会让引用它的产物连锁 `stale`。无法唯一解析的自动
selector 会静默退回整文件绑定；显式 `--input-record` 仍严格报错。新版剧本索引使用
`screenplay-block-v1` 稳定摘要，父剧本文件 hash、行字节偏移和 revision mapping 变化不会
让内容未变的 block 绑定失效。

例行单集执行的 CLI 命令不需要手工 hash（`--target`、`--evidence-hash`、`--verdict-hash`
由工具从快照/磁盘现算，仍逐 hash 核对）；写 verdict 时其内部 `findings_ref.hash`
需对 findings 文件现算；`review_bundle_ref.hash` 直接使用 `review-bundle` 输出的
`bundle_hash`。
审查全程当前上下文（首审冷读 → REVISE 一次改全 → delta_verify 反审，
`review-batch --episode` 一次应用）；fresh 子 agent 只保留类型基准首审、越界大改、
交付终审三事件，且终审整集一次覆盖。
例行单集创作 + 审查约 35–40 分钟（不含交付终审，后者另需 10–20 分钟）。

创作台 Dashboard 仅支持 macOS/Linux；Windows 上使用下面的 CLI 工作流。

### 常用命令速查

统一入口（每次会话一次）：

```text
python3 skills/short-drama/scripts/project_tool.py preflight <project>   # 套件校验 + 事务恢复 + 状态
python3 skills/short-drama/scripts/project_tool.py pipeline <project>    # pipeline 2.0 位置与阻塞项
```

生命周期命令（全部在 `project_tool.py` 下）：

| 命令 | 用途 |
|---|---|
| `init` | 初始化最小项目 |
| `status` | 生命周期与恢复摘要 |
| `recover` | 恢复中断事务 |
| `upgrade-flow` | 旧项目完成 M1.5 后升级到 pipeline 2.0 |
| `publish` | 发布 candidate |
| `accept` | 记录创作者接受（单个产物；`--target` 与 `--evidence-hash` 可省略，工具从快照/磁盘现算） |
| `decide` | 从候选快照生成合规的接受决定文件；委托决定必须绑定 creator delegation evidence |
| `unpublish` | 撤销发布但未接受的 artifact 记录（已接受产物受保护） |
| `accept-batch` | 一次应用磁盘上全部已记录的接受决定（整批生产） |
| `review-bundle` | L1 审查前打包已验证证据，fresh reviewer 只读一份文件 |
| `review` | 记录独立审查结论（L1 fresh / L1.5 冷读 / L2 delta_verify；`--verdict-hash` 可省略） |
| `review-batch` | 一次应用磁盘上全部已写入的审查结论（`--episode` 限定单集） |
| `package` | 交付打包（只收 accepted + L1 fresh 终审；要求 accepted delivery_surface，省略项须 creator evidence） |
| `verify` | 复核交付包校验和（跨平台） |

完整参数与纪律见 `skills/short-drama/references/lifecycle-commands.md`；例行命令形态见
`skills/short-drama/references/execution-quickstart.md`；整批生产见
`skills/short-drama/references/batch-production.md`；批量执行的固定节奏（记录级绑定、
候选目录生命周期、拓扑规划、base/delta 分离与错误恢复）见
`skills/short-drama/references/production-sop.md`。

## 许可

[MIT](LICENSE)
