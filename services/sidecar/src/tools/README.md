# Deep Agents 默认能力

Agent 由 `create_deep_agent` 创建，所有 Agent 默认使用相同的文件与命令工具，不依赖知识库、技能安装或连接器配置。`agent_backend(agent_code)` 将 Backend 绑定到各 Agent 的独立工作目录。

| 工具         | 实现                           | 功能                                  |
| ------------ | ------------------------------ | ------------------------------------- |
| `ls`         | Deep Agents                    | 列目录                                |
| `read_file`  | Deep Agents                    | 分页读取文件                          |
| `write_file` | Deep Agents                    | 新建文件，已有文件通过 edit_file 修改 |
| `edit_file`  | Deep Agents                    | 替换并调整已有内容                    |
| `glob`       | Deep Agents                    | 按文件路径通配符查找                  |
| `grep`       | Deep Agents                    | 按字面文本搜索正文                    |
| `execute`    | Deep Agents + WorkspaceBackend | 执行本机 Bash 命令                    |

文件工具直接使用 Deep Agents 的 FilesystemMiddleware；原 community FileManagementToolkit 与手写 grep 已移除。RAG 等业务工具通过 `create_deep_agent(tools=...)` 追加，不覆盖默认工具。

工作目录与 Electron 一致：开发使用仓库 `.dp-work/workspace/<agent_code>/`，安装版使用 `~/.dp-work/workspace/<agent_code>/`，由 Sidecar 的 `DP_DATA_DIR` 推导。每次运行分别绑定 Backend，不修改进程全局 cwd。

`WorkspaceBackend` 继承 `LocalShellBackend`，设置 `virtual_mode=True`。文件工具的 `/notes.md` 对应当前 workspace 中的文件，路径越界由 Backend 校验。命令由独立系统沙箱执行，cwd 本身不构成沙箱。

`execute` 的模型工具由 Deep Agents 提供；Backend 的异步执行适配保留 30 秒超时、32 KB 输出上限和取消时清理进程树。指定更长 timeout 也不会超过当前上限；进程只继承基础环境变量，不传入模型和 ASR 密钥。macOS / Linux 使用本机 Bash；Windows 使用 Linux 容器中的 Bash/Python。

版本固定为 `deepagents==0.7.32`。桌面打包收集 Deep Agents 程序资源及元数据，并验证冻结后的模型调用和文件操作。

项目目录：Electron 原生文件夹选择器登记到 `.dp-work/data/projects.json`，项目元信息和会话关系保存在本机。Sidecar 以本机登记及账号为准解析路径，未授权或已移动的目录直接报错。未关联项目时继续使用 Agent 默认工作目录。项目中的文件工具和 execute 均绑定所选目录；AGENT.md 和技能仍保留在 Agent 管理目录，技能通过 `/__agent_skills__/` 挂载。

运行中及等待审批时不能切换或移除项目，审批继续使用原运行的目录。移除项目仅解除会话归属，不删除文件和历史消息。侧栏“项目”按项目组织会话，“最近”展示所有 Agent 和项目的会话。

文件修改展示：WorkspaceBackend 在 write_file / edit_file 前保存快照，并在操作后比较实际文件；可能修改文件的 Bash/Python 命令同样比较执行前后状态。sessions 将差异保存在消息 context.file_changes 中，并记录到本地 JSONL/SQLite。界面复用 assistant-ui FileTree + CodeDiff，鼠标移入文件查看每次修改与撤销入口，统计为历史累计增删。预览只处理不超过 256 KB、5000 行的 UTF-8 文件，差异最多展示 400 行；超限时提示而不伪造差异。

## 文件快照和撤销

快照保存在 `.dp-work/data/file-snapshots/<账号 ID>/`，完全留在本机：

- `blobs/<sha256>`：按内容去重的文件备份，POSIX 文件权限 0600、目录 0700；含原始字节，可恢复小型二进制文件。
- `batches/<id>.json`：命令开始前已落盘的文件基线，区分不存在与空文件，保存权限和目录身份。
- `changes/<id>.json`：每次文件变更的前后指纹及撤销状态。
- `runs/<run_id>.json`：运行关联的修改 ID，停止或断流后由 sessions 补齐尚未送达界面的 Diff。

`sessions.files.undo` 通过 Electron 本地路由调用；只接受会话和变更 ID，不接受网页提交的恢复路径或内容。账号、会话归属、项目授权、目录身份及运行状态均需匹配。撤销新增文件会删除它，撤销修改会恢复原字节和 POSIX 权限，撤销删除会重建原文件。使用临时文件原子替换；POSIX 恢复使用目录句柄逐层拒绝软链接。目录结构只为恢复文件按需重建，不回滚空目录、目录权限、软链接或目录联接。

撤销前比较当前内容/权限与这次修改完成时的状态；如果用户或后续工具又改过文件，返回冲突并保持当前文件。同文件应按修改顺序倒序撤销；不提供强制覆盖和重做。文件操作、Bash 和撤销在相同工作目录内串行；外部编辑器不参与此锁，不能把它描述为跨进程文件事务。磁盘恢复和会话元数据不能跨文件系统做同一个事务，恢复请求可重试，避免再次执行文件修改。

Bash 跟踪范围为当前工作目录内的普通文件；文件移动按删除/新增展示，失败和超时也记录已产生的变化。只读白名单命令不做无意义的全目录备份。命令启动的、未纳入受控生命周期的后台进程后续修改不保证捕获。技能挂载目录、目录外文件及 `.git`、`node_modules`、`.venv`、`venv`、`__pycache__`、`.dp-work`、`.next`、`dist`、`build` 不纳入 Bash 扫描。

限制：单文件可恢复备份最多 2 MB，单次基线最多 32 MB、3000 个文件、20000 个目录项。启动前超出扫描/总量预算会阻止命令；大文件、软链接、特殊文件会标记不支持撤销。后置扫描失败会明确标记“操作已执行、扫描失败”，不能为获取 Diff 自动重复执行操作。扫描和磁盘读写在线程执行；目前快照没有自动过期回收，需随本机数据一同备份，后续可增加按保留期清理。旧消息没有修改前快照时不显示撤销按钮。

## 命令隔离与依赖

统一入口为 `isolation.py` / `shell.py`；依赖缺失时返回 126，启动失败不降级为普通 Bash。所有平台只授权所选工作目录和命令临时目录写入，不传模型密钥、SSH_AUTH_SOCK、BASH_ENV、宿主 Docker 配置或 socket。审批不解除隔离。磁盘根目录、用户主目录及其父目录、系统目录不能作为执行范围。

| 平台    | 实现与前提                                                                 | 资源范围                                                                              |
| ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| macOS   | 系统 sandbox-exec（已弃用，发布时须验证目标系统）                          | 系统与 Python 运行库只读，其他业务目录和网络默认拒绝                                  |
| Linux   | Bubblewrap，支持用户/网络/PID namespace 和 `--disable-userns` 的内核及版本 | 仅白名单系统运行库只读；不挂载宿主 /run、主目录、根文件系统；独立网络和 PID namespace |
| Windows | Docker Desktop，启用 Linux 容器；配置本机镜像 ID                           | 仅项目映射为 /workspace；系统只读、无外部网络、不共享宿主 PID；禁止能力提升           |

macOS / Linux 在用户命令开始前设置 Bash 硬限制：不生成 core、256 个文件描述符、单文件写入上限（`ulimit -f 65536`）、每进程 30 秒 CPU。保留 30 秒墙钟超时和 32 KB 输出截断；当前没有原生整组内存/进程数配额，不应描述为防 fork bomb 的完整资源沙箱。Linux 的系统库挂载按目录授权；若需更窄的只读范围，应使用独立运行镜像。网络 namespace 不等同于通用 syscall 过滤，项目目录中不要放宿主服务 socket。

macOS 子进程清理基于 POSIX 进程组，没有独立 PID namespace；恶意程序自行脱离进程组的情况不具备容器级生命周期保证。文件与网络限制仍由继承的 sandbox profile 生效。

容器限制为 512 MB 内存（禁额外 swap）、1 CPU、128 个进程、64 MB 单文件、临时文件系统共 160 MB。每条命令使用独立容器和 HOME；正常完成、失败、超时、取消均通过宿主 `docker rm --force` 清理；容器内还有独立超时，避免仅断开客户端后任务继续运行。引擎不可达时记录清理失败，不能保证立即清理；恢复引擎后可检查 `dp-work-exec-*` 容器。

Windows 一次性准备（在仓库根目录执行，创建镜像时需要网络）：

```sh
docker build -t dp-work-sandbox:local services/sidecar/sandbox
docker image inspect dp-work-sandbox:local --format '{{.Id}}'
```

把完整的 `sha256:...` 写入 `services/sidecar/.env` 的 `AGENT_SANDBOX_IMAGE`，重启 Sidecar。执行时固定连接本机 Docker 引擎，`--pull=never`，不自动下载镜像。项目需允许 Docker Desktop 共享。镜像含 Bash、Python、Git、ripgrep；其他依赖需用户预装进镜像，命令运行时禁止联网安装。容器不执行 Windows 原生 EXE，不直接使用宿主虚拟环境，模型上下文会给出 `/workspace` 路径规则。

## 审批与脚本

`harness/tool_policy.py:evaluate_permission` 是当前 Permission Manager，给出是否审批和判断原因；`approvals.py` 将其接到 LangChain HITL，在实际工具执行前暂停。只读命令及普通文件变更自动允许；未知命令、Bash/Python 脚本、重定向、敏感文件变更需要审批。批准只允许检查点保存的这一次参数。

不把静态扫描脚本当作安全证明。脚本可以动态导入或启动新进程，批准后的代码仍由内核/容器限制文件与网络访问。工作目录内的文件是已授权数据，其中的凭证仍可能被脚本读取；沙箱不保护用户授权目录中的数据，也不提供文件修改回滚。工具本身及 Sidecar 仍是可信代码。

## 验证

```sh
# Sidecar 环境中执行普通回归
.venv/bin/pytest tests/tools tests/agents/test_tool_policy.py
# 真实 Linux（须先安装 Bubblewrap 并启用用户 namespace），无第三方 Python 依赖
python tests/tools/sandbox_linux_smoke.py
# 容器实测，指定本机 endpoint 与已构建镜像 ID；--basetemp 须位于 Docker 可共享的目录
DP_TEST_SANDBOX_IMAGE=sha256:... DP_TEST_DOCKER_HOST=unix:///var/run/docker.sock \
  .venv/bin/pytest tests/tools/test_sandbox_platforms.py --basetemp=/path/to/shared/test-temp
```

容器实测可验证 Linux 容器策略，但不能替代 Windows 本机的 named pipe、路径映射和 Docker Desktop 共享权限验证。

本轮验证：macOS 完整 Sidecar 回归通过，容器后端的真实越界/网络/超时/取消测试通过且无残留执行容器。Linux ARM64 虚拟机中的 Bubblewrap 0.12 根用户隔离测试通过；外层容器需允许嵌套 namespace，普通 UID 在当前虚拟机中创建网络 namespace 被拒绝，因此 Linux 普通用户部署仍需目标机实测。Windows 原生 named pipe 和目录共享尚未实机验证。不能把平台参数单元测试视作这些部署验证完成。
