# Agent 默认模板

默认提示词统一维护在 `templates/{general,product,ui}/AGENT.md`。这是 pnpm workspace 中的资源子包，同时作为 Python 包 `dp-work-agent-templates` 分发，不需要 TypeScript 构建。

Sidecar 通过 `read_template(code)` 读取包资源，首次使用 Agent 时初始化 `.dp-work/workspace/<agent>/AGENT.md`。已有工作区文件不会被覆盖；修改默认模板只影响后续新建工作区。

在仓库根目录安装开发依赖：

```sh
services/sidecar/.venv/bin/python -m pip install -e ./packages/agent-templates -e ./services/sidecar
```

独立 Python 部署须同时构建、安装模板包与 Sidecar wheel。桌面 PyInstaller 构建通过 `--collect-all templates` 收集模板和加载代码，运行时无需仓库目录。

Sidecar 的 `pyproject.toml` 同时提供 `[tool.uv.sources]` 本地路径配置。在 `services/sidecar` 目录运行 `uv sync` 时，会从 `../../packages/agent-templates` 可编辑安装模板包，无需发布到 PyPI。此配置只供 uv 项目命令使用；当前开发说明及 CI 仍使用上面的 pip 显式安装方式，pip 不读取 `tool.uv.sources`。
