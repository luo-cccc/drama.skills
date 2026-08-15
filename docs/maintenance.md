# 仓库维护手册

本文是仓库维护者的唯一操作入口。创作流程、生命周期命令和产物所有权仍分别以
`skills/short-drama/references/production-pipeline.md`、`lifecycle-commands.md` 和
`contract-and-ownership.md` 为准；跨阶段生产和消费关系以 `workflow-dataflow.md` 为准。

## 权威来源

| 内容 | 权威来源 |
|---|---|
| 套件、契约与 pipeline 版本 | `project_tool.py` 常量、`suite-manifest.json`、项目模板；三者由测试约束一致 |
| 项目命令及参数 | `python skills/short-drama/scripts/project_tool.py --help` |
| 技能文件集合与 SHA-256（文本规范化 LF，二进制按原始字节） | `skills/short-drama/suite-manifest.json` |
| 子技能绑定的 core 清单 | 各子技能 `suite-ref.json` |
| 测试矩阵 | `.github/workflows/suite.yml` |
| Dashboard 平台边界与保存语义 | `skills/short-drama/references/lifecycle-commands.md` 的“Dashboard 启动”章节 |
| 用户可见变更 | `docs/releases/release-notes.md` 与 README 的“最新更新” |
| 文档入口与权威路由 | `docs/README.md`；发布套件内的数据流入口为 `workflow-dataflow.md` |
| 模型侧技能上下文预算 | `tools/skill_perf_audit.py` 与 `tests/test_skill_perf_audit.py` |
| 技能触发边界 | 各技能 `SKILL.md` frontmatter；未被用户显式调用时不得触发 |

不要在文档中手写一份独立命令列表或版本表后让它自行漂移。参数以 `--help` 为准，
版本由自动化测试核对，文件哈希由清单生成器维护。

## 修改边界

- `skills/**` 是发布套件内容。修改其中任何脚本、文档、模板或示例后，都必须重建清单。
- `tests/**`、`tools/**`、`docs/**` 和 `.github/**` 是仓库级维护内容，不进入发布套件清单。
- 不提交 `__pycache__/`、`*.pyc`、`.ruff_cache/`、`.DS_Store` 或 `.zcode/`。
- 不手改 `suite-manifest.json` 或 `suite-ref.json` 中的哈希；统一运行生成器。

## 本地验证

推荐从仓库根目录执行：

```bash
python tools/update_suite_manifest.py
python -m compileall -q skills tools tests
ruff check skills tools tests
python -m unittest discover -s tests -v
python tools/skill_perf_audit.py
node --check skills/short-drama/assets/dashboard/app.js
node tests/test_dashboard_app.js
python skills/short-drama/scripts/suite_verify.py --no-cache
```

清单生成器对未改动的套件是幂等的，因此这组命令可以原样运行；若改过 `skills/**`，先
重建清单也能确保 Python 测试中的磁盘一致性检查针对最新内容执行。

Windows PowerShell 若默认编码不是 UTF-8，可先设置：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

测试数量随功能演进，不在维护文档中手工维护；以 CI 与 `unittest discover` 输出为准。
Dashboard 的 `ProjectStore` 行为测试在 POSIX 与 Windows 后端都执行；Windows 还覆盖
junction/symlink、嵌套 reparse、ADS/设备名、父目录和项目根置换、媒体句柄、跨进程保存冲突、
CLI 锁互斥、长文件名、重复操作句柄计数、临时文件清理及不支持卷/API 的启动拒绝。前端测试
使用 Node 标准库，无 npm 依赖。

Windows 后端专项可单独运行：

```powershell
python -m unittest tests.test_windows_dashboard -v
```

## 安全回归范围

修改项目文件系统或 JSON 处理时，至少保持以下行为：

- 项目相对路径按 Unicode NFC + 大小写折叠建立可移植身份；斜杠别名、大小写别名和
  组合字符别名必须在写 WAL 前拒绝。
- 路径分量拒绝 Windows 保留设备名、`< > : " | ? *`、控制字符和尾随空格/句点。
- JSON/JSONL 只接受标准 JSON 数字；`NaN`、`Infinity` 和 `-Infinity` 必须拒绝，输出
  也不得产生非有限数字。
- `--aspect-ratio` 只接受两个大于零的十进制数，以 `:` 分隔，例如 `9:16`、`2.39:1`。
- `--max-clip-seconds` 只接受正有限秒数；默认 15，并由 generation clip 校验器执行。
- POSIX 发布与恢复通过固定目录描述符和 `O_NOFOLLOW` 替换/删除文件；Windows 读取在
  打开句柄后复核文件身份，检测路径置换。
- Windows Dashboard 只允许普通盘符下的本地固定 NTFS，从卷根逐级拒绝全部 reparse point；
  UNC、设备命名空间、网络盘、非 NTFS 和 OneDrive 占位必须在绑定或访问前失败关闭。
- Windows Dashboard 保存必须持有固定父句柄、项目事务锁和目标首字节锁，临时写入刷新后
  再次核对目标 hash，再以父句柄相对原子替换；失败路径不得遗留临时文件或覆盖普通外部编辑。
- 正文替换成功后，生命周期状态写入失败不得伪装成保存失败；响应必须返回新版本和
  `stateWarning`，前端清除已提交内容的 dirty 状态并提示运行项目预检。
- Dashboard 的 API 必须要求一次性会话，限制回环 Host/Origin，并持续发送 CSP、
  `X-Frame-Options: DENY` 和 `X-Content-Type-Options: nosniff`。

这些行为由 `tests/test_security_regressions.py`、`tests/test_dashboard_server.py`、
`tests/test_windows_dashboard.py`、`tests/test_check_scripts.py` 和
`tests/test_dashboard_app.js` 覆盖。

## 清单与版本

修改 `skills/**` 后运行：

```bash
python tools/update_suite_manifest.py
python skills/short-drama/scripts/suite_verify.py --no-cache
```

生成器重算全部发布技能文件，写回 core 清单并同步子技能引用。它是幂等的：
没有技能文件变化时，清单 hash 不应变化。

版本升级时同步检查：

1. `project_tool.py` 的 `SUITE_VERSION`、`CONTRACT_VERSION`、`PIPELINE_VERSION`。
2. `suite-manifest.json` 的 suite/contract 版本。
3. `assets/project-template/short-drama.json` 的 schema 与 pipeline 版本。
4. README“最新更新”和 `docs/releases/release-notes.md`。

`tests/test_security_regressions.py` 会在常量、清单和模板不一致时失败。

## CI 与发布检查

CI 在 Ubuntu、macOS、Windows 和 Python 3.10/3.14 组合上执行 Python 编译、完整测试、
Node 20 前端检查及套件全量哈希验证；独立 lint job 使用固定版本 Ruff。

发布前确认：

1. 全部本地验证命令通过。
2. 新行为有回归测试，用户可见变化已写入发布说明。
3. 文档中的相对链接可解析，项目命令说明与 `project_tool.py --help` 一致。
4. README“最新更新”只保留最新日期块；完整历史只写入 release notes。
5. 清单已在最后一次 `skills/**` 修改之后生成。
6. 工作区不包含应忽略的生成缓存或临时项目产物。
7. `rg` 未发现已经失效的 Dashboard 平台限制、Windows 降级或测试跳过说明。
