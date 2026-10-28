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

`WorkspaceBackend` 继承 `LocalShellBackend`，设置 `virtual_mode=True`。文件工具的 `/notes.md` 对应当前 workspace 中的文件，路径越界由 Backend 校验。命令执行仍是本机用户权限，cwd 不构成沙箱。

`execute` 的模型工具由 Deep Agents 提供；Backend 的异步执行适配保留 30 秒超时、32 KB 输出上限和取消时清理进程树。指定更长 timeout 也不会超过当前上限；进程只继承基础环境变量，不主动传入模型和 ASR 密钥。Windows 需要安装 Bash 并加入 PATH，macOS / Linux 使用本机 Bash。

版本固定为 `deepagents==0.7.32`。桌面打包收集 Deep Agents 程序资源及元数据，并验证冻结后的模型调用和文件操作。

项目目录：Electron 原生文件夹选择器登记到 `.dp-work/data/projects.json`，PG 只保存项目元信息和会话的 `project_id`。API 将会话所属项目 ID、认证用户 ID 发给对应设备，Sidecar 以本机登记为准解析路径，未授权或已移动的目录直接报错。未关联项目时继续使用 Agent 默认工作目录。项目中的文件工具和 execute 均绑定所选目录；AGENT.md 和技能仍保留在 Agent 管理目录，技能通过 `/__agent_skills__/` 挂载。

运行中及等待审批时不能切换或移除项目，审批继续使用原运行的目录。移除项目仅解除会话归属，不删除文件和历史消息。侧栏“项目”按项目组织会话，“最近”展示所有 Agent 和项目的会话。
