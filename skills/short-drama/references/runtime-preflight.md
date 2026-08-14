# 运行时预检与发布纪律

无论从主技能还是子技能进入，都先完成同一套轻量预检。它只检查安装完整性、项目事务状态和已记录的精确引用，不评价创作内容。

## 0. 会话内状态复用

同一会话中，以下结果可复用，不重复全量执行：

- 同一项目的 `recover` + `status` 已执行且此后所有写入都经过公开生命周期命令时，后续入口直接复用已读状态；发生外部编辑冲突、`recover` 报告 blocked、切换项目或跨会话时重新执行。

`suite_verify.py` 每次都对清单内全部文件重算 SHA-256。文件大小与 mtime 可以在篡改后
恢复，因此不再作为复用旧摘要的信任依据。`--full` / `--no-cache` 为旧调用保留兼容，
二者当前都走同一条全量哈希路径，输出的 `verify_cache.mode` 为 `full`。

## 0b. 推荐入口：单进程 preflight

日常入口用一条命令完成全部预检，替代三次独立进程调用：

```bash
python3 <core>/scripts/project_tool.py preflight <project>
```

它在一个解释器进程内依次执行套件全量校验、事务恢复与状态读取，
输出一份紧凑 JSON：`suite`（校验的技能/文件数与全量哈希统计）、`recovery`（是否需要恢复、
阻塞事务数）、`status`（生命周期摘要）。退出码 0 表示可继续；2 表示套件校验失败或
命令错误；3 表示存在阻塞事务，需要先处理再继续。

只有需要诊断细节（具体事务 ID、完整状态字段）时才分别运行 `recover` / `status`；
日常入口不再依赖模型在上下文中拼接三次命令的输出。

## 1. 验证当前安装

需要单独核验安装或查看 `verify_cache` 详情时，从 `suite-ref.json` 解析到逻辑安装路径
中的 core 后，用当前可用的 Python 3 解释器运行：

```bash
python3 <core>/scripts/suite_verify.py <core>
# 需要强制全量重算时：
python3 <core>/scripts/suite_verify.py <core> --full  # 兼容旧调用；仍执行全量哈希
```

若环境的 Python 3 命令名不同，使用该环境已经提供的等价解释器。验证器必须沿逻辑安装路径逐一检查清单中的九个技能；混装、缺件、额外可执行文件或 hash 不一致时停止写入。不要退回源码检出目录“借用”通过验证的兄弟技能。
输出 JSON 摘要中的 `verify_cache` 字段给出本次 `hashed_files`；`cached_files` 固定为 0。

## 2. 恢复事务，再读状态

定位项目根目录后，`preflight` 已包含这两步；需要单独执行或查看完整输出时运行：

```bash
python3 <core>/scripts/project_tool.py recover <project>
python3 <core>/scripts/project_tool.py status <project>
```

Windows 环境通常没有 `python3` 命令，使用 `python` 或环境提供的等价解释器。

`recover` 可重复执行。若它报告 blocked，保持创作者文件原样并先处理冲突；不要绕过 WAL、手改状态文件或假定上次写入成功。`status` 中的 accepted/candidate 指针和阻断项是后续工作的当前事实。

同时读取 `status.layout`。`mode=canonical` 使用返回的中文 `roots`，`mode=legacy`
使用返回的旧版英文 `roots`；`mode=mixed` 时停止发布，先合并平行目录。所有负责技能都沿用
同一份 `roots`，不得根据自身模板另建另一种语言的阶段目录。`pinned=false` 的空项目使用
返回的中文根，第一次阶段发布会把布局固定进项目状态。

## 3. 只通过公开生命周期写入

- 负责人用 `publish` 原子发布候选，并给每个外部结构化引用提供精确 input hash。
- 上游接受引用不继承候选状态；`authority:candidate` 只用于同次发布的目标或明确的
  候选预览链，后者在接受前必须已由同 hash 的上游接受快照闭合。
- 创作者接受、独立审查和内容修订是不同动作；审查者发布 finding/verdict，不改负责人的来源。
- 每次修订后重新运行适用的结构校验，并让下游刷新旧 hash。
- `package` 是最终文本/JSON 交付闸门，不是接受或审查命令；任何阻断项仍在时不打包。

完整命令参数见 [lifecycle-commands.md](lifecycle-commands.md)，权威边界见 [contract-and-ownership.md](contract-and-ownership.md)。

## 3a. 路径与结构化数据先过机器边界

- 同一调用中的所有项目路径必须在 Unicode NFC + 大小写折叠后保持唯一；大小写、正反
  斜杠或组合字符别名不是两个产物。发现碰撞时停止，不要换到大小写敏感平台绕过。
- 每个路径分量还必须避开 Windows 保留设备名、`< > : " | ? *`、控制字符和尾随空格/句点。
- JSON/JSONL 必须是标准 JSON；`NaN`、`Infinity`、`-Infinity` 和未填模板占位符都不能
  进入 candidate、决定、verdict 或项目状态。未知数值使用 `null`。
- `init --aspect-ratio` 使用正数 `WIDTH:HEIGHT`。比例是项目契约，不接受斜杠、零或负值。
- `init --max-clip-seconds` 使用正有限秒数，默认 15；它是 generation clip 上限，不是影视镜头上限。
- 发布和恢复检测符号链接与路径置换。出现 `project path changed while opening`、
  `publication parent` 或类似事务冲突时保留现场并运行 `recover`，不要手工改 WAL/state。

## 3b. 读共享 JSON/JSONL 时声明记录绑定

`设定集/*.jsonl` 与项目文件是全项目共享输入：只按整文件 `hash` 绑定会让后续任何一次
增补把此前引用过它的产物全部标为 `stale`。发布时对这类输入补
`--input-record <path>=<selector>`（JSONL 用记录 ID，JSON 用 RFC 6901 指针，每条一次），
此后只有被绑定的记录变化才会影响本产物。Markdown 没有可机器校验的记录身份，仍按整文件
绑定。引用剧本时一律经 `screenplay-index.jsonl` 的记录 ID 绑定，不直接绑定
`screenplay.md` 整文件；这样逐句改剧本只会让实际改动波及的记录使下游标 `stale`。
审查方核对剧本来源引用时，同样确认绑定的是 `screenplay-index.jsonl` 记录 ID 而非
`screenplay.md` 整文件。这是九个技能共享的预检纪律，各技能 `stage-contract.md` 不再
逐份重复，只保留本技能特有的补充。

`publish` 的 `--input-record-auto` **默认开启**：候选输出里指向已声明 `--input` 文件的
结构化 refs（JSON/JSONL 内 `{owner, artifact, hash, record_id}`）会自动把其 `record_id`
并入记录绑定——一个 8 角色的文件不需要手写 8 条 `--input-record`。ref 无 `record_id`
或无法唯一解析时静默跳过，退化为整文件绑定；显式 `--input-record` 始终优先。
`--no-input-record-auto` 恢复手写模式。
