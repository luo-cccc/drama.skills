# 批量生产操作手册（模型侧执行）

目标：整批生产（多集、多阶段）时把模型回合和创作者等待压到最少，同时不破坏接受与
审查纪律。生产操作的大部分耗时来自创作生成本身；本页压缩的是**编排回合**：指令重读、
逐产物命令、逐产物接受等待。

## 原则

1. **长会话内连续生产**：`SKILL.md` 与执行速查只在会话内读一次，不要每集重新读；
   状态用 `preflight` 一次读取，之后的步骤直接复用，不重复跑。
2. **机械步骤合并**：`preflight` 一次；决定文件用 `decide` 逐产物生成（一条命令写一份
   合规记录，不手写 JSON）；接受用 `accept-batch` 一次应用全部决定；审查结论写好后用
   `review-batch` 一次应用；每个机械检查脚本每个产物只跑一次。
3. **接受回合合并**：整批先出全部 candidate + 一张合并接受清单（每产物一行：
   artifact、目标 hash、语义差异一句话），创作者一次确认后批量接受，不逐产物等待。
4. **例行审查不派 fresh agent**：首审走 L1.5 冷读（`cold_read`），修订复查走 L2
   `delta_verify`，都在当前上下文完成；只有类型基准（第一集 / 新产物类型首审）、
   越界大改、交付终审才派 L1（派发前先 `review-bundle`，一个 fresh reviewer 覆盖全部范围）。

## 推荐批次流程（以“写 5 集”为例）

1. `project_tool.py preflight <project>`（一次）。
2. 读取分集地图，先批量提出并接受资产等级，再接受模型/视图，再接受标准片段。
3. 读取已接受 generation 基线（一次，不逐集重读）。
4. 同一上下文连续写 5 集的单集卡、节拍与剧本；每集建索引（candidate authority）并
   `publish`（每集一个 artifact，可连续执行）。
5. 汇总一张接受清单给创作者（一屏内列完 5 集的候选与差异）。
6. 创作者一次确认后：对每集跑一次
   `decide <project> --artifact-id <id> --decision accepted`（自动从候选快照生成合规
   记录，默认写到 `创作者决策/<净化id>.json`，冒号→连字符），再跑一次
   `accept-batch <project>` 全部接受。
7. 审查结论（verdict JSON 含 `artifact_id`，findings 由 `findings_ref` 绑定）写好并核对
   证据 hash 后，按集一次 `review-batch <project> --episode EP001`（整集结论一次应用）；
   整批首审走 L1.5 冷读、例行修订循环走 L2 `delta_verify`（全程当前上下文，不派子 agent）；
   交付前做一次 L1 fresh 终审（`review-bundle --episode` + 一个 fresh reviewer 覆盖全部
   范围），再 `package`。

## 接受回合可以这样合并，但决定本身不能合并

- `accept-batch` 只应用**已经写在磁盘上的决定记录**，不代替创作者做决定；`review-batch`
  同样只应用**已经写下的审查结论**，不代替审查者下结论。记录缺失、target 与
  candidate/accepted 不一致、证据 hash 不匹配都会失败并退出非零。
- 同一 target 只能接受一次：接受成功后 candidate 字段归档，重复应用会失败；修订流程是
  重新发布新 candidate 再接受。
- 同一文件 hash 绑定要求决定与 verdict 按产物分文件（`创作者决策/<净化id>.json` 与
  `审查/<id>-verdict.json` 各一份一个产物），多份文件用 `decide` 逐条生成、或一次编辑
  全部创建。
- 全链预览用 candidate 预览链一次呈现（下游标 `provisional` / `authority: candidate`），
  避免逐阶段等待；未接受内容不得交付。

## 各阶段机械检查合并示例

| 阶段 | 每产物跑一次的命令 |
|---|---|
| 资产基线 | `asset_baseline_check.py` |
| 图片/关键帧/运动提示词 | `prompt_compile.py --check` |
| 写作 | `screenplay_index.py`（有配音本再加 `voice_sheet_check.py`） |
| 分镜 | `storyboard_check.py` |
| 视频 | `motion_timing_check.py`、`generation_clip_check.py`、`container_check.py` |
| 审查 | `review-bundle` 一次打包，fresh / 冷读审查者只读一份文件 |

同一会话内不需要重复 `preflight`；文件被外部编辑或状态报 blocked 时才重新执行。

批量执行的固定节奏（记录级绑定、候选目录生命周期、拓扑规划、base/delta 分离与错误
恢复速查）见 [production-sop.md](production-sop.md)——它规定每一步的前置条件，本页
只规定回合如何合并。
