# skills.sh 技能加载

技能配置页通过登录后的 API / 设备通道调用本机 Sidecar：搜索 skills.sh 公开目录，安装、列出和卸载对应 Agent 的技能。安装状态以本机实际文件为准，不以浏览器缓存中的 skill_ids 作为执行依据。

```text
.dp-work/workspace/
  general/skills/<skill-name>/
    SKILL.md
    scripts/             # 来源技能存在时一同保留
    references/
    .dp-work-skill.json   # 来源仓库记录
  product/skills/<skill-name>/
```

开发使用项目根目录 `.dp-work`，安装版使用用户主目录 `~/.dp-work`。不同 Agent 分别安装与卸载，互不影响。

Agent 使用 `create_deep_agent(skills=["/skills/"])`，通过独立 WorkspaceBackend 将虚拟路径映射到本机。框架先加载名称和描述，在需要时读取完整 SKILL.md 及附件；每次运行重新创建 Agent，后续请求可以读取最新安装状态。

支持 `https://skills.sh/owner/repo/skill-name` 或 `owner/repo@skill-name`。搜索使用 skills.sh 的公开目录接口，内容从公开 GitHub 仓库下载，按 SKILL.md 的 name 匹配目标技能。仅复制技能目录及附件，不执行安装脚本，也不修改用户其他工具的全局技能目录，不依赖用户安装 Node / Git / skills CLI。

下载、解压大小和文件数量有限制；拒绝路径越界及压缩包软链接，临时目录验证完成后原子移动到目标目录。SKILL.md 必须包含合法 name、description。同名不同来源需先卸载，重复安装同一来源直接返回现有安装结果。依赖额外 CLI 或软件的技能仍需本机具备对应运行环境。

RPC：`skills.search`、`skills.list`、`skills.descriptions`、`skills.install`、`skills.uninstall`，方法声明集中在 `packages/protocols/protocol.json`。

详情弹窗直接复用列表元信息，展示完整简介、来源和安装状态，不下载仓库。安装时才下载技能目录。

公开 API：GET `/api/skills/search?q=...`、GET `/api/skills?agent_code=...`、POST `/api/skills/install`、POST `/api/skills/uninstall`。均需要登录和可用执行设备；业务结果统一返回 200，错误返回对应状态和消息。

卡片简介优先读取已安装 SKILL.md 的 description；市场简介通过 `skills.descriptions` 批量读取公开页面元数据，缓存到 `.dp-work/cache/skills-descriptions`（成功 24 小时，缺失 2 分钟）。页面最多展示三行，详情弹窗展示未折叠的简介。

安装、卸载和列表读取的文件操作通过线程执行，不阻塞 Sidecar 事件循环。取消请求会等待文件线程收尾后再释放 Agent 锁；损坏安装记录单项跳过并记录日志。前端保留 30 秒缓存，进入页面或重新聚焦时检查是否过期；设备通道重连成功会使缓存失效并刷新正在展示的列表，没有定时轮询。安装或卸载成功但列表刷新失败会单独提示。
